#!/usr/bin/env python3
"""wire speaks HTTP/2 (#480): the fixture tools/ci/fixtures/wire_h2.tin calls upstreams from its
request handlers, one core, so that calls overlap as streams of one connection.

- Go's net/http (tools/ci/fixtures/h2upstream.go), over TLS (h2 by ALPN) and cleartext (h2c by
  prior knowledge): 100 calls in a row and 50 at once on one connection, 5 MB up and 12 MB down
  through the flow-control windows, trailers, a deadline that resets its stream and leaves the
  connection, MaxBody, and HTTP/1.1 with NoH2.
- anvil's h2 fixture (tools/ci/fixtures/h2.tin), over TLS and h2c: a 3 MB upload, trailers, 20
  calls at once.
- A server written here that sends GOAWAY: the next call takes a new connection, and a stream
  past the GOAWAY's last one is sent again on a new connection.
"""
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.request

from suite import ROOT
from lifetime_check import eventually, server_ready
from tls_check import make_certs, openssl3, free_port, wait_port


def frame(typ, flags, sid, payload=b''):
    return struct.pack('>I', len(payload))[1:] + bytes([typ, flags]) + struct.pack('>I', sid) + payload


def read_frame(c, buf):
    while len(buf) < 9:
        d = c.recv(65536)
        if not d:
            return None, buf
        buf += d
    n = int.from_bytes(buf[:3], 'big')
    while len(buf) < 9 + n:
        d = c.recv(65536)
        if not d:
            return None, buf
        buf += d
    f = (buf[3], buf[4], int.from_bytes(buf[5:9], 'big') & 0x7fffffff, buf[9:9 + n])
    return f, buf[9 + n:]


def request_path(block):
    """The :path of a header block wire wrote: static-table names and plain literals."""
    i = 0

    def integer(mask):
        nonlocal i
        v = block[i] & mask
        i += 1
        if v < mask:
            return v
        m = 0
        while True:
            b = block[i]
            i += 1
            v += (b & 127) << m
            m += 7
            if b < 128:
                return v

    def string():
        nonlocal i
        assert block[i] < 128, 'wire sends no Huffman-coded strings'
        n = integer(127)
        s = block[i:i + n]
        i += n
        return s.decode()

    names = {1: ':authority', 2: ':method', 4: ':path', 6: ':scheme', 58: 'user-agent', 28: 'content-length', 31: 'content-type'}
    while i < len(block):
        b = block[i]
        if b >= 128:
            integer(127)
            continue
        idx = integer(15)
        name = names.get(idx, '?') if idx else string()
        value = string()
        if name == ':path':
            return value
    return ''


class GoawayServer:
    """Cleartext HTTP/2 that answers "<path> on <connection>". It sends GOAWAY after each answer,
    except for /warm; on a connection where /c came, it waits for a second /c, answers the first
    and leaves the second out of the GOAWAY."""

    def __init__(self):
        self.ls = socket.socket()
        self.ls.bind(('127.0.0.1', 0))
        self.ls.listen(16)
        self.port = self.ls.getsockname()[1]
        self.count = 0
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            c, _ = self.ls.accept()
            self.count += 1
            threading.Thread(target=self.serve, args=(c, self.count), daemon=True).start()

    def answer(self, c, sid, text):
        c.sendall(frame(1, 4, sid, b'\x88') + frame(0, 1, sid, text.encode()))

    def serve(self, c, n):
        buf = b''
        with c:
            while len(buf) < 24:
                buf += c.recv(65536)
            assert buf[:24] == b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n', buf[:24]
            buf = buf[24:]
            c.sendall(frame(4, 0, 0))
            pending_c = []
            deadline = None
            done = False
            c.settimeout(0.05)
            while True:
                try:
                    f, buf = read_frame(c, buf)
                except socket.timeout:
                    f = 'timeout'
                if f is None:
                    return
                if f != 'timeout':
                    typ, flags, sid, payload = f
                    if typ == 4 and not flags & 1:
                        c.sendall(frame(4, 1, 0))
                    if typ == 1 and not done:
                        path = request_path(payload)
                        if path == '/c':
                            pending_c.append(sid)
                            deadline = deadline or time.monotonic() + 1.0
                        else:
                            self.answer(c, sid, f'{path} on {n}')
                            if path != '/warm':
                                c.sendall(frame(7, 0, 0, struct.pack('>II', sid, 0)))
                                done = True
                if pending_c and not done and (len(pending_c) >= 2 or time.monotonic() > deadline):
                    first = min(pending_c)
                    self.answer(c, first, f'/c on {n}')
                    c.sendall(frame(7, 0, 0, struct.pack('>II', first, 0)))
                    done = True


def get(port, path, timeout=180):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=timeout) as r:
        return r.read().decode()


def build(src, out, cwd=ROOT):
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(out), src], cwd=cwd, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True, timeout=300)


def main():
    go = shutil.which('go')
    assert go, 'wire_h2_check needs Go (the net/http upstream)'
    openssl = openssl3() or shutil.which('openssl')
    out = ROOT / 'bin/ci/wire_h2'
    out.mkdir(parents=True, exist_ok=True)
    certs = make_certs(openssl, out)
    cert, key = certs['ecdsa']
    build('tools/ci/fixtures/wire_h2.tin', out / 'client')
    build('tools/ci/fixtures/h2.tin', out / 'anvil_h2')
    subprocess.run([go, 'build', '-o', str(out / 'h2upstream'), 'tools/ci/fixtures/h2upstream.go'], cwd=ROOT, check=True, timeout=300)
    procs = []
    logs = []

    def start(cmd, env, name):
        log = (out / f'{name}.log').open('wb')
        logs.append(log)
        p = subprocess.Popen(cmd, stdout=log, stderr=log, env=dict(os.environ, **env))
        procs.append(p)
        return p

    try:
        gtls, gh2c = free_port(), free_port()
        gp = start([str(out / 'h2upstream'), str(gtls), str(gh2c), str(cert), str(key)], {}, 'go')
        atls, ah2c = free_port(), free_port()
        ap1 = start([str(out / 'anvil_h2')], {'PORT': str(atls), 'TIN_CORES': '1', 'TLS_CERT': str(cert), 'TLS_KEY': str(key)}, 'anvil_tls')
        ap2 = start([str(out / 'anvil_h2')], {'PORT': str(ah2c), 'TIN_CORES': '1'}, 'anvil_h2c')
        cport = free_port()
        cp = start([str(out / 'client')], {'PORT': str(cport), 'TIN_CORES': '1', 'CA': str(cert)}, 'client')
        for port, p in ((gtls, gp), (gh2c, gp), (atls, ap1), (ah2c, ap2), (cport, cp)):
            wait_port(port, p)
        gs = GoawayServer()
        lines = []
        for path in (f'/go?base=https://localhost:{gtls}', f'/go?base=http://127.0.0.1:{gh2c}&h2c=1',
                     f'/anvil?base=https://localhost:{atls}', f'/anvil?base=http://127.0.0.1:{ah2c}&h2c=1',
                     f'/goaway?base=http://127.0.0.1:{gs.port}'):
            got = get(cport, path).splitlines()
            print('\n'.join(f'{l}  ({path.split("?")[0][1:]} {"h2c" if "h2c" in path or "goaway" in path else "tls"})' for l in got))
            lines += got
        assert lines and all(l.startswith('ok ') for l in lines), [l for l in lines if not l.startswith('ok ')]
        assert gs.count == 4, f'the GOAWAY server accepted {gs.count} connections, not 4'
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for log in logs:
            log.close()
    print(f'PASS wire HTTP/2: {len(lines)} checks against Go, anvil and a GOAWAY server')


if __name__ == '__main__':
    main()
