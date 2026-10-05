#!/usr/bin/env python3
"""wire's HTTP client keeps connections alive (#348).

A client service (tools/ci/fixtures/wire_pool.tin) calls an upstream written here, which counts
the connections it accepts and what happens on them. A hundred sequential calls to one host use
one connection, over http and over https (one TLS handshake); a response that says "close", has
no length, or is a HTTP/1.0 one is not reused; chunked bodies and bodiless responses are; a kept
connection the server drops is replaced without the caller seeing it (for requests that can be
repeated); at most Options.MaxIdle connections stay open after a burst.
"""
import os
from pathlib import Path
import socket
import ssl
import subprocess
import threading
import time
import urllib.request

from suite import ROOT
from lifetime_check import eventually, server_ready
import websocket_check as ws


class Upstream:
    """A small HTTP/1.1 server that counts connections and requests per connection."""

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.lock = threading.Lock()
        self.accepted = 0
        self.open = 0
        self.counts = {}   # connection number -> requests since reset
        self.total = 0
        self.handshakes = 0
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(256)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        with self.lock:
            self.accepted += 1
            self.open += 1
            self.total += 1
            idx = self.total
        try:
            if self.ctx is not None:
                conn = self.ctx.wrap_socket(conn, server_side=True)
                with self.lock:
                    self.handshakes += 1
            conn.settimeout(30)
            buf = b''
            while True:
                while b'\r\n\r\n' not in buf:
                    part = conn.recv(65536)
                    if not part:
                        return
                    buf += part
                head, buf = buf.split(b'\r\n\r\n', 1)
                lines = head.decode().split('\r\n')
                method, path, _ = lines[0].split(' ')
                headers = {l.split(':', 1)[0].lower(): l.split(':', 1)[1].strip() for l in lines[1:]}
                n = int(headers.get('content-length', 0))
                while len(buf) < n:
                    buf += conn.recv(65536)
                buf = buf[n:]
                with self.lock:
                    self.counts[idx] = self.counts.get(idx, 0) + 1
                    nth = self.counts[idx]
                if not self.respond(conn, method, path, nth, headers):
                    return
        except (OSError, ssl.SSLError):
            pass
        finally:
            with self.lock:
                self.open -= 1
            try:
                conn.close()
            except OSError:
                pass

    def respond(self, conn, method, path, nth, headers):
        """Answers one request; False when the connection ends with it."""
        body = b'ok'
        head = b'HTTP/1.1 200 OK\r\nContent-Length: %d\r\n' % len(body)
        if path.startswith('/ok'):
            conn.sendall(head + b'\r\n' + (b'' if method == 'HEAD' else body))
        elif path.startswith('/close'):
            conn.sendall(head + b'Connection: close\r\n\r\n' + body)
            return False
        elif path.startswith('/eof'):
            conn.sendall(b'HTTP/1.1 200 OK\r\n\r\nuntil the end')
            return False
        elif path.startswith('/old'):
            conn.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\nold')
            return False
        elif path.startswith('/chunked'):
            conn.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n')
        elif path.startswith('/nobody'):
            conn.sendall(b'HTTP/1.1 204 No Content\r\n\r\n')
        elif path.startswith('/slow'):
            time.sleep(0.25)
            conn.sendall(head + b'\r\n' + body)
        elif path.startswith('/flaky'):
            # the second request on a connection finds it closed, as after an idle timeout
            if nth >= 2:
                return False
            conn.sendall(head + b'\r\n' + body)
        elif path.startswith('/echo'):
            conn.sendall(head + b'\r\n' + body)
        else:
            conn.sendall(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n')
        return True

    @property
    def requests(self):
        with self.lock:
            return sorted(self.counts.values())

    def reset(self):
        with self.lock:
            self.accepted = 0
            self.counts = {}
            self.handshakes = 0


def get(port, path, timeout=30):
    with urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, path), timeout=timeout) as r:
        return r.read().decode()


def check_http(svc):
    """Each group calls its own upstream (a port of its own), so no kept connection of an earlier
    group answers its first call."""
    def group():
        up = Upstream()
        base = 'http://127.0.0.1:%d' % up.port

        def seq(path, n, **q):
            up.reset()
            extra = ''.join('&%s=%s' % kv for kv in q.items())
            return get(svc, '/seq?n=%d&path=%s&base=%s%s' % (n, path, base, extra))
        return up, seq, base

    srv, seq, base = group()
    out = seq('/ok', 100)
    assert out == 'ok=100 err=0 last=200:ok', out
    assert srv.accepted == 1 and srv.requests == [100], ('100 calls on one connection', srv.accepted, srv.requests)
    # the next burst reuses the connection the last one left
    out = seq('/ok', 5)
    assert srv.accepted == 0 and srv.requests == [5], ('a kept connection serves the next burst', srv.accepted, srv.requests)
    print('keep-alive: 100 sequential calls on 1 connection, and the next 5 on the same one')

    srv, seq, base = group()
    out = seq('/close', 5)
    assert out == 'ok=5 err=0 last=200:ok' and srv.accepted == 5, ('Connection: close is honoured', srv.accepted)
    srv, seq, base = group()
    out = seq('/eof', 3)
    assert out == 'ok=3 err=0 last=200:until the end' and srv.accepted == 3, ('a body that ends with the connection', srv.accepted)
    srv, seq, base = group()
    out = seq('/old', 3)
    assert out == 'ok=3 err=0 last=200:old' and srv.accepted == 3, ('HTTP/1.0 is not kept', srv.accepted)
    print('not kept: Connection: close, a body without a length, HTTP/1.0')

    srv, seq, base = group()
    out = seq('/chunked', 10)
    assert out == 'ok=10 err=0 last=200:abcde' and srv.accepted == 1, ('chunked bodies are reused', srv.accepted)
    srv, seq, base = group()
    out = seq('/nobody', 10)
    assert out == 'ok=10 err=0 last=204:' and srv.accepted == 1, ('204 is reused', srv.accepted)
    srv, seq, base = group()
    out = seq('/ok', 10, method='HEAD')
    assert out == 'ok=10 err=0 last=200:' and srv.accepted == 1, ('HEAD is reused', srv.accepted)
    print('kept: chunked bodies, 204, HEAD')

    # A kept connection the server closes before answering is replaced, for GET; not for POST.
    srv, seq, base = group()
    out = seq('/flaky', 10)
    assert out == 'ok=10 err=0 last=200:ok' and srv.accepted == 10, ('a stale kept connection is retried', out, srv.accepted)
    srv, seq, base = group()
    out = seq('/flaky', 4, method='POST')
    assert out.startswith('ok=2 err=2'), ('a POST is not repeated', out)
    print('stale kept connections: GET retried on a new one, POST not repeated')

    # A burst of 20 at once opens 20; MaxIdle 3 keeps 3 of them.
    srv, seq, base = group()
    out = get(svc, '/par?n=20&path=/slow&idle=3&base=' + base)
    assert out == 'ok=20 err=0', out
    assert srv.accepted == 20, srv.accepted
    eventually(lambda: srv.open == 3, 5)
    srv.reset()
    out = seq('/ok', 6, idle=3)
    assert srv.accepted == 0, ('after the burst the 3 kept connections serve', srv.accepted)
    # a negative MaxIdle keeps none and asks the server to close
    srv, seq, base = group()
    out = seq('/ok', 4, idle=-1)
    assert srv.accepted == 4, ('MaxIdle -1 dials every call', srv.accepted)
    print('MaxIdle: 20 at once, 3 stay open; -1 keeps none')


def main():
    out = ROOT / 'bin/ci/wire_pool'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'wire_pool'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/wire_pool.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)

    def start(upstream, **env):
        port = ws.free_port()
        p = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1',
                                      UPSTREAM=upstream, **env))
        eventually(lambda: server_ready(port, p))
        return p, port

    def stop(p):
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            raise

    p, svc = start('http://127.0.0.1:1')
    try:
        check_http(svc)
    finally:
        stop(p)

    # https: one TCP connection and one TLS handshake for many calls.
    from tls_check import make_certs, openssl3
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory(prefix='wire-pool-', dir=out) as tmp:
        certs = make_certs(openssl3() or shutil.which('openssl'), Path(tmp))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(str(certs['ecdsa'][0]), str(certs['ecdsa'][1]))
        tls_srv = Upstream(ctx)
        p, svc = start('https://127.0.0.1:%d' % tls_srv.port, INSECURE='1')
        try:
            body = get(svc, '/seq?n=50&path=/ok')
            assert body == 'ok=50 err=0 last=200:ok', body
            assert tls_srv.accepted == 1 and tls_srv.handshakes == 1 and tls_srv.requests == [50], \
                ('50 https calls on one TLS connection', tls_srv.accepted, tls_srv.handshakes, tls_srv.requests)
            tls_srv.reset()
            body = get(svc, '/seq?n=10&path=/close')
            # the first call still rides the connection the 50 left; the other nine each dial
            assert body == 'ok=10 err=0 last=200:ok' and tls_srv.accepted == 9, (body, tls_srv.accepted)
            tls_srv.reset()
            body = get(svc, '/seq?n=10&path=/flaky')
            assert body == 'ok=10 err=0 last=200:ok', body
            print('https: 50 calls on 1 TLS connection and 1 handshake; close and a stale connection handled')
        finally:
            stop(p)


if __name__ == '__main__':
    main()
