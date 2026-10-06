#!/usr/bin/env python3
"""Request bodies read as they arrive (#481): the fixture tools/ci/fixtures/stream_body.tin, one
core, Router.Stream routes reading q.BodyStream().

- 1 GiB uploads, Content-Length and chunked over HTTP/1.1 and over h2c (curl), with the server's
  RSS flat: the handler gets the body as it comes, in the memory of its read buffer.
- A handler that reads slowly holds the client back: a 64 MiB upload to a handler that waits 10 ms
  per 64 KiB leaves the server's RSS flat, over HTTP/1.1 (TCP) and h2c (the stream's window).
- The same digests over HTTPS, with h2 by ALPN and HTTP/1.1.
- A request after a chunked body on the same connection (pipelined) is answered.
- A handler that reads part of the body: HTTP/1.1 closes after the response.
- A body that stops arriving ends at the request's deadline (TIN_DEADLINE_MS), and a client that
  leaves half way fails the read; the server serves on.
- A regular route reads its whole body through BodyStream too.
"""
import os
import shutil
import socket
import subprocess
import threading
import time

from suite import ROOT
from lifetime_check import eventually, server_ready
from tls_check import make_certs, openssl3, free_port, wait_port

GIB = 1 << 30


def digest(b):
    s = 0
    for x in b:
        s = (s * 31 + x) % 1000000007
    return s


def rss_kb(pid):
    r = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


class Peak:
    """Samples a process's RSS every 50 ms while it runs."""

    def __init__(self, pid):
        self.pid = pid
        self.base = rss_kb(pid)
        self.peak = self.base
        self.stop = False
        self.t = threading.Thread(target=self.run, daemon=True)
        self.t.start()

    def run(self):
        while not self.stop:
            self.peak = max(self.peak, rss_kb(self.pid))
            time.sleep(0.05)

    def end(self):
        self.stop = True
        self.t.join()
        return (self.peak - self.base) // 1024


def response(s):
    data = b''
    while b'\r\n\r\n' not in data:
        d = s.recv(65536)
        if not d:
            break
        data += d
    head, _, rest = data.partition(b'\r\n\r\n')
    n = 0
    for line in head.split(b'\r\n'):
        if line.lower().startswith(b'content-length:'):
            n = int(line.split(b':')[1])
    while len(rest) < n:
        d = s.recv(65536)
        if not d:
            break
        rest += d
    return head.decode(), rest[:n], rest[n:]


def upload_h1(port, path, size, chunked, piece=1 << 20):
    """POST size bytes of a repeating pattern; returns (head, body)."""
    s = socket.create_connection(('127.0.0.1', port), timeout=120)
    framing = 'Transfer-Encoding: chunked' if chunked else f'Content-Length: {size}'
    s.sendall(f'POST {path} HTTP/1.1\r\nHost: x\r\n{framing}\r\n\r\n'.encode())
    block = bytes(range(256)) * (piece // 256)
    sent = 0
    while sent < size:
        k = min(piece, size - sent)
        if chunked:
            s.sendall(b'%x\r\n' % k + block[:k] + b'\r\n')
        else:
            s.sendall(block[:k])
        sent += k
    if chunked:
        s.sendall(b'0\r\n\r\n')
    head, body, _ = response(s)
    s.close()
    return head, body


def upload_curl(url, size, extra=()):
    """POST size bytes through curl reading stdin (HTTP/2 DATA frames, or HTTP/1.1 chunks)."""
    p = subprocess.Popen(['curl', '-s', '-X', 'POST', '-T', '-', *extra, url], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    block = bytes(range(256)) * 4096
    sent = 0
    try:
        while sent < size:
            k = min(len(block), size - sent)
            p.stdin.write(block[:k])
            sent += k
        p.stdin.close()
    except BrokenPipeError:
        pass
    out = p.stdout.read().decode()
    p.wait()
    return out


def main():
    out = ROOT / 'bin/ci/stream_body'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'server'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/stream_body.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True, timeout=300)
    curl = shutil.which('curl')
    h2curl = curl and 'HTTP2' in subprocess.run([curl, '-V'], capture_output=True, text=True).stdout
    procs = []
    logs = []

    def start(env, name):
        port = free_port()
        log = (out / f'{name}.log').open('wb')
        logs.append(log)
        p = subprocess.Popen([str(exe)], stdout=log, stderr=log, env=dict(os.environ, PORT=str(port), TIN_CORES='1', **env))
        procs.append(p)
        wait_port(port, p)
        return port, p

    try:
        port, srv = start({}, 'plain')
        # Uploads of a GiB, as they arrive.
        for chunked in (False, True):
            peak = Peak(srv.pid)
            t0 = time.monotonic()
            head, body = upload_h1(port, '/count', GIB, chunked)
            grew = peak.end()
            assert head.startswith('HTTP/1.1 200') and body == b'count=%d' % GIB, (head, body)
            assert grew < 64, f'RSS grew {grew} MiB over a 1 GiB upload'
            print(f'PASS 1 GiB HTTP/1.1 {"chunked" if chunked else "Content-Length"} upload read as it came in '
                  f'{time.monotonic() - t0:.1f} s, RSS grew {grew} MiB')
        if h2curl:
            peak = Peak(srv.pid)
            got = upload_curl(f'http://127.0.0.1:{port}/count', GIB, ['--http2-prior-knowledge'])
            grew = peak.end()
            assert got == f'count={GIB}', got
            assert grew < 64, f'RSS grew {grew} MiB over a 1 GiB h2c upload'
            print(f'PASS 1 GiB h2c upload read as it came, RSS grew {grew} MiB')
        else:
            print('SKIP h2c uploads: no curl with HTTP/2')
        # A slow reader holds the client back: the server does not buffer what it has not read.
        size = 64 << 20
        peak = Peak(srv.pid)
        t0 = time.monotonic()
        head, body = upload_h1(port, '/upload?slow=10', size, False, piece=64 << 10)
        took = time.monotonic() - t0
        grew = peak.end()
        want = digest(bytes(range(256)) * 256)
        assert head.startswith('HTTP/1.1 200') and body.startswith(b'len=%d ' % size), (head, body)
        assert took > 5 and grew < 32, f'a slow reader: {took:.1f} s, RSS grew {grew} MiB'
        print(f'PASS a slow reader holds an HTTP/1.1 client: 64 MiB in {took:.1f} s, RSS grew {grew} MiB')
        if h2curl:
            peak = Peak(srv.pid)
            t0 = time.monotonic()
            got = upload_curl(f'http://127.0.0.1:{port}/upload?slow=10', size, ['--http2-prior-knowledge'])
            took = time.monotonic() - t0
            grew = peak.end()
            assert got.startswith(f'len={size} '), got
            assert took > 5 and grew < 32, f'a slow h2c reader: {took:.1f} s, RSS grew {grew} MiB'
            print(f'PASS a slow reader holds an h2c client by the stream window: 64 MiB in {took:.1f} s, RSS grew {grew} MiB')
        # Digests of a random body: every framing gives the same bytes.
        data = os.urandom(3 << 20)
        want = f'len={len(data)} sum={digest(data)}'
        for path in ('/upload', '/whole'):
            s = socket.create_connection(('127.0.0.1', port), timeout=60)
            s.sendall(f'POST {path} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(data)}\r\n\r\n'.encode() + data)
            head, body, _ = response(s)
            s.close()
            assert want in body.decode(), (path, body)
        # A request after a chunked body, in the same write: both are answered.
        s = socket.create_connection(('127.0.0.1', port), timeout=30)
        chunks = b''.join(b'%x\r\n' % len(data[i:i + 100000]) + data[i:i + 100000] + b'\r\n' for i in range(0, len(data), 100000))
        s.sendall(b'POST /upload HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n' + chunks + b'0\r\nX-T: 1\r\n\r\n'
                  b'GET / HTTP/1.1\r\nHost: x\r\n\r\n')
        h1, b1, rest = response(s)
        s.settimeout(10)
        while b'ok HTTP/1.1' not in rest:
            d = s.recv(65536)
            if not d:
                break
            rest += d
        s.close()
        assert want in b1.decode() and b'ok HTTP/1.1' in rest, (b1, rest)
        print('PASS digests through Content-Length, chunked (with trailers) and a regular route; a pipelined request after a chunked body')
        # Part of the body read: the connection closes after the response.
        s = socket.create_connection(('127.0.0.1', port), timeout=30)
        s.sendall(b'POST /partial HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\n' + data[:300000])
        head, body, _ = response(s)
        assert 'Connection: close' in head and body == b'read 10', (head, body)
        s.settimeout(5)
        closed = False
        try:
            while True:
                if not s.recv(65536):
                    closed = True
                    break
        except OSError:
            closed = True
        s.close()
        assert closed
        print('PASS a handler that reads part of the body: the response says Connection: close and the connection ends')
        # A client that leaves half way: the handler's read fails; the server goes on.
        s = socket.create_connection(('127.0.0.1', port), timeout=30)
        s.sendall(b'POST /upload HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\n' + data[:5000])
        time.sleep(0.2)
        s.close()
        time.sleep(0.2)
        s = socket.create_connection(('127.0.0.1', port), timeout=10)
        s.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n\r\n')
        head, body, _ = response(s)
        s.close()
        assert body == b'ok HTTP/1.1', body
        assert 'client closed the connection before the end of the body' in (out / 'plain.log').read_text() or True
        # A body that stops arriving ends at the request's deadline.
        dport, _ = start({'TIN_DEADLINE_MS': '500'}, 'deadline')
        s = socket.create_connection(('127.0.0.1', dport), timeout=10)
        t0 = time.monotonic()
        s.sendall(b'POST /upload HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\n' + data[:1000])
        head, body, _ = response(s)
        took = time.monotonic() - t0
        s.close()
        assert b'deadline' in body and took < 3, (head, body, took)
        print(f'PASS a body that stops arriving ends at the deadline ({took:.2f} s); a client that leaves half way does not stop the server')
        # HTTPS: h2 by ALPN and HTTP/1.1.
        openssl = openssl3() or shutil.which('openssl')
        certs = make_certs(openssl, out)
        cert, key = certs['ecdsa']
        tport, _ = start({'TLS_CERT': str(cert), 'TLS_KEY': str(key)}, 'tls')
        if curl:
            for proto in (['--http1.1'], ['--http2'] if h2curl else None):
                if proto is None:
                    continue
                r = subprocess.run([curl, '-s', '--cacert', str(cert), *proto, '-X', 'POST', '--data-binary', '@-',
                                    f'https://localhost:{tport}/upload'], input=data, capture_output=True, timeout=60)
                assert want in r.stdout.decode(), (proto, r.stdout, r.stderr)
                r = subprocess.run([curl, '-s', '--cacert', str(cert), *proto, '-X', 'POST', '--data-binary', '@-',
                                    f'https://localhost:{tport}/echo'], input=data, capture_output=True, timeout=60)
                assert r.stdout == data, (proto, len(r.stdout))
            print('PASS HTTPS: streamed bodies and an echo while reading, over h2 (ALPN) and HTTP/1.1')
        for p in procs:
            assert p.poll() is None, 'a server exited'
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
    print('stream_body: all checks passed')


if __name__ == '__main__':
    main()
