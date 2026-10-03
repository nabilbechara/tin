#!/usr/bin/env python3
"""A routed anvil server (tools/ci/fixtures/router.tin) under concurrent requests: every
response carries its own path parameter and middleware trace although middleware and
handlers wait, on one core and on two; waits through the router overlap on one core; 404,
405 with Allow, HEAD, bodies and pipelined order work through the router; and a routed
handler takes WebSocket connections."""
import os
import random
import socket
import subprocess
import sys
import threading
import time
from suite import ROOT
import websocket_check as ws


def read_response(f):
    """One response from file f: (status, headers, body)."""
    line = f.readline()
    if not line:
        raise EOFError('connection closed')
    status = int(line.split()[1])
    headers = {}
    while True:
        h = f.readline()
        if h in (b'\r\n', b''):
            break
        k, _, v = h.decode().partition(':')
        headers[k.strip().lower()] = v.strip()
    body = f.read(int(headers.get('content-length', '0')))
    return status, headers, body


def request(port, method, path, body=b''):
    with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
        s.sendall(('%s %s HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'
                   % (method, path, len(body))).encode() + body)
        f = s.makefile('rb')
        if method == 'HEAD':
            line = f.readline()
            headers = {}
            while True:
                h = f.readline()
                if h in (b'\r\n', b''):
                    break
                k, _, v = h.decode().partition(':')
                headers[k.strip().lower()] = v.strip()
            return int(line.split()[1]), headers, f.read()
        return read_response(f)


def start(exe, cores):
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES=str(cores),
                                                   TIN_DEADLINE_MS='5000', TIN_GRACE='1'))
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError('the routed server exited during startup')
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
            return server, port
        except OSError:
            time.sleep(0.05)
    raise RuntimeError('the routed server did not start')


def stop(server):
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()


def mixed_load(port, failures, threads=48, per=25):
    """Keep-alive clients send interleaved routes with random waits in middleware and handlers;
    each answer must name its own id and the middleware that ran."""
    errors = []

    def client(k):
        rnd = random.Random(k)
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
                f = s.makefile('rb')
                for i in range(per):
                    n = rnd.randrange(1000000)
                    if i % 3 == 2:
                        path = '/api/items/%d?mw=%d&ms=%d' % (n, rnd.randrange(8), rnd.randrange(8))
                        want = b'item %d stamp>tag>api' % n
                    else:
                        path = '/users/%d?ms=%d' % (n, rnd.randrange(12))
                        want = b'user %d stamp>tag /users/{id}' % n
                    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\n\r\n' % path).encode())
                    status, headers, body = read_response(f)
                    if status != 200 or body != want or headers.get('x-status') != '200':
                        errors.append('%s -> %d %r %r' % (path, status, body, headers.get('x-status')))
        except Exception as e:
            errors.append('client %d: %r' % (k, e))

    ts = [threading.Thread(target=client, args=(k,)) for k in range(threads)]
    t0 = time.time()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    print('%d routed requests from %d connections in %.2f s, %d wrong' % (threads * per, threads, time.time() - t0, len(errors)))
    if errors:
        failures.append('mixed load: %d wrong answers, first %r' % (len(errors), errors[:3]))


def overlap(port, failures):
    """On one core, requests that wait in a routed handler or in middleware do not hold up others."""
    for name, path in [('handler', '/users/1?ms=300'), ('middleware', '/api/items/1?mw=300')]:
        slow = {}

        def one(i):
            t0 = time.time()
            slow[i] = (request(port, 'GET', path), time.time() - t0)

        ts = [threading.Thread(target=one, args=(i,)) for i in range(8)]
        t0 = time.time()
        for t in ts:
            t.start()
        time.sleep(0.05)
        fast = []
        for _ in range(30):
            f0 = time.time()
            status, _, body = request(port, 'GET', '/fast')
            fast.append(time.time() - f0)
            if status != 200 or body != b'fast':
                failures.append('fast request behind %s waits: %d %r' % (name, status, body))
        for t in ts:
            t.join()
        total = time.time() - t0
        print('8 x 300 ms waits in a routed %s: %.3f s; fast meanwhile: max %.1f ms' % (name, total, max(fast) * 1000))
        if total > 1.2:
            failures.append('waits in a routed %s did not overlap (%.3f s)' % (name, total))
        if max(fast) > 0.1:
            failures.append('a fast request waited %.1f ms behind a routed %s' % (max(fast) * 1000, name))
        if any(r[0][0] != 200 for r in slow.values()):
            failures.append('slow %s answers: %r' % (name, [r[0][:2] for r in slow.values()]))


def protocol(port, failures):
    """404, 405 with Allow, HEAD, a body, a catch-all and pipelined order, through the router."""
    want = [
        (('GET', '/nope'), 404, b'Not Found', {'x-status': '404'}),
        (('GET', '/api/nope'), 404, b'Not Found', {'x-status': '404'}),
        (('POST', '/users/7'), 405, b'Method Not Allowed', {'allow': 'GET, HEAD', 'x-status': '405'}),
        (('DELETE', '/users'), 405, b'Method Not Allowed', {'allow': 'POST'}),
        (('POST', '/users'), 201, b'created 5', {}),
        (('GET', '/files/a/b%20c.txt'), 200, b'file a/b c.txt', {}),
        (('GET', '/users/'), 404, b'Not Found', {}),
    ]
    for (method, path), status, body, headers in want:
        got = request(port, method, path, b'hello' if method == 'POST' else b'')
        if got[0] != status or got[2] != body or any(got[1].get(k) != v for k, v in headers.items()):
            failures.append('%s %s -> %r' % (method, path, got))
    status, headers, rest = request(port, 'HEAD', '/users/42')
    if status != 200 or headers.get('content-length') != str(len(b'user 42 stamp>tag /users/{id}')) or rest:
        failures.append('HEAD /users/42 -> %d %r %r' % (status, headers, rest))
    with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
        s.sendall(b'GET /users/1?ms=80 HTTP/1.1\r\nHost: x\r\n\r\nGET /fast HTTP/1.1\r\nHost: x\r\n\r\n'
                  b'GET /nope HTTP/1.1\r\nHost: x\r\n\r\nGET /api/items/2?mw=30 HTTP/1.1\r\nHost: x\r\n\r\n'
                  b'POST /users/3 HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
        f = s.makefile('rb')
        order = [read_response(f)[2] for _ in range(5)]
    print('pipelined through the router:', order)
    if order != [b'user 1 stamp>tag /users/{id}', b'fast', b'Not Found', b'item 2 stamp>tag>api', b'Method Not Allowed']:
        failures.append('pipelined order: %r' % order)


def raw(port, data):
    """Send data, then read until the server closes; the raw bytes."""
    with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
        s.sendall(data)
        out = b''
        while True:
            d = s.recv(65536)
            if not d:
                return out
            out += d


def response_headers(port, failures):
    """#172: header values from the request cannot add header lines or a body, framing headers
    set by a handler are ignored, and 204/304 responses carry no body."""
    got = raw(port, b'GET /echo-head?v=a%0d%0aSet-Cookie:%20x=1%0d%0a%0d%0aINJECTED&t=text/x%0d%0aX-Evil:%201'
                    b' HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
    head, _, body = got.partition(b'\r\n\r\n')
    lines = head.split(b'\r\n')
    names = [l.split(b':', 1)[0].lower() for l in lines[1:]]
    print('response header names:', names)
    if b'set-cookie' in names or b'x-evil' in names or b'bad name' in names:
        failures.append('a header line was injected: %r' % got)
    if names.count(b'content-length') != 1 or names.count(b'connection') != 0 or body != b'echoed':
        failures.append('framing headers from the handler were sent: %r' % got)
    if b'X-Echo: a  Set-Cookie: x=1    INJECTED' not in lines or b'Content-Type: text/x  X-Evil: 1' not in lines:
        failures.append('CR/LF in values were not replaced by spaces: %r' % got)
    for code in (204, 304):
        got = raw(port, b'GET /status/%d HTTP/1.1\r\nHost: x\r\n\r\nGET /fast HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % code)
        first, _, rest = got.partition(b'\r\n\r\n')
        if b'content-length' in first.lower() or not rest.startswith(b'HTTP/1.1 200 OK\r\n') or not rest.endswith(b'\r\n\r\nfast'):
            failures.append('%d response framing: %r' % (code, got))
    print('204/304 without a body, header injection refused:', not failures)


def conformance(port, failures):
    """#183: bare CR, NUL and control bytes are rejected, HTTP/1.1 needs one Host, absolute-form
    targets route on their path, HTTP/1.0 keep-alive is echoed, "close" anywhere in Connection
    wins, and a client that half-closes still gets the answer to a request that waits."""
    def first(data, wait=2.0, shut=False):
        with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
            s.sendall(data)
            if shut:
                s.shutdown(socket.SHUT_WR)
            s.settimeout(wait)
            out = b''
            try:
                while True:
                    d = s.recv(65536)
                    if not d:
                        return out, True
                    out += d
            except socket.timeout:
                return out, False
    cases = [
        (b'GET /fast HTTP/1.1\r\nHost: x\r\nX-A: a\rb\r\n\r\n', b'HTTP/1.1 400 '),
        (b'GET /fast HTTP/1.1\r\nHost: x\r\nX-A: a\x00b\r\n\r\n', b'HTTP/1.1 400 '),
        (b'GET /fa\x01st HTTP/1.1\r\nHost: x\r\n\r\n', b'HTTP/1.1 400 '),
        (b'GET /fast HTTP/1.1\r\n\r\n', b'HTTP/1.1 400 '),
        (b'GET /fast HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n', b'HTTP/1.1 400 '),
        (b'GET /fast HTTP/1.x\r\nHost: x\r\n\r\n', b'HTTP/1.1 400 '),
        (b'GET /fast HTTP/1.0\r\n\r\n', b'HTTP/1.1 200 '),
        (b'GET http://other.example/files/a/b?x=1 HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n', b'HTTP/1.1 200 '),
    ]
    for data, want in cases:
        got, _ = first(data)
        if not got.startswith(want):
            failures.append('%r -> %r' % (data, got[:60]))
    got, _ = first(b'GET http://other.example/files/a/b?x=1 HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
    if not got.endswith(b'file a/b'):
        failures.append('absolute-form target: %r' % got)
    got, closed = first(b'GET /fast HTTP/1.0\r\nConnection: keep-alive\r\n\r\n', wait=0.5)
    if b'\r\nConnection: keep-alive\r\n' not in got or closed:
        failures.append('HTTP/1.0 keep-alive: %r closed=%s' % (got, closed))
    got, closed = first(b'GET /fast HTTP/1.1\r\nHost: x\r\nConnection: keep-alive, close\r\n\r\n')
    if not got.endswith(b'fast') or not closed:
        failures.append('Connection: keep-alive, close: %r closed=%s' % (got, closed))
    got, closed = first(b'GET /users/9?ms=200 HTTP/1.1\r\nHost: x\r\n\r\n', wait=5, shut=True)
    if not got.startswith(b'HTTP/1.1 200 ') or not got.endswith(b'user 9 stamp>tag /users/{id}') or not closed:
        failures.append('half-closed client with a waiting request: %r closed=%s' % (got, closed))
    print('request conformance (#183):', not failures)


def websockets(port, failures):
    """A routed handler upgrades: its path parameter, an echo, and 20 at once on the core."""
    ws.PORT = port
    conns = [ws.connect('/ws/room%d' % i) for i in range(20)]
    ok = True
    for i, c in enumerate(conns):
        ok = ok and ws.recv(c) == (1, b'room room%d' % i)
    for i, c in enumerate(conns):
        ws.send(c, 1, b'hi %d' % i)
    for i, c in enumerate(conns):
        ok = ok and ws.recv(c) == (1, b'echo: hi %d' % i)
    for c in conns:
        ws.send(c, 8, b'\x03\xe8')
        ok = ok and ws.recv(c) == (8, b'\x03\xe8')
        c[0].close()
    print('20 WebSocket connections through a routed handler:', ok)
    if not ok:
        failures.append('websocket through the router')


def main():
    out = ROOT / 'bin/ci/router'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'router'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/router.tin'], cwd=ROOT, check=True,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)))
    failures = []
    for cores in (1, 2):
        server, port = start(exe, cores)
        try:
            print('-- %d core%s' % (cores, '' if cores == 1 else 's'))
            mixed_load(port, failures)
            protocol(port, failures)
            if cores == 1:
                response_headers(port, failures)
                conformance(port, failures)
                overlap(port, failures)
                websockets(port, failures)
            if server.poll() is not None:
                failures.append('the server exited on %d cores' % cores)
        finally:
            stop(server)
    if failures:
        sys.exit('\n'.join(failures))


if __name__ == '__main__':
    main()
