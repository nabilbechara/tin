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
    # The handler's "connection: close" is dropped; the one Connection line is anvil's, which
    # says the connection closes because the request asked it to (RFC 9112 9.6).
    if names.count(b'content-length') != 1 or names.count(b'connection') != 1 or b'Connection: close' not in lines or \
            body != b'echoed':
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
    # #103: a client that sends Expect: 100-continue waits for 100 Continue before its body.
    with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
        s.sendall(b'POST /users HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\nExpect: 100-continue\r\nConnection: close\r\n\r\n')
        s.settimeout(1)
        try:
            interim = s.recv(100)
        except socket.timeout:
            interim = b'(nothing within 1 s)'
        s.sendall(b'hello')
        s.settimeout(10)
        rest = b''
        while True:
            d = s.recv(65536)
            if not d:
                break
            rest += d
        if interim != b'HTTP/1.1 100 Continue\r\n\r\n' or not rest.startswith(b'HTTP/1.1 201 ') or not rest.endswith(b'created 5'):
            failures.append('Expect: 100-continue: %r then %r' % (interim, rest))
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


def limits(exe, failures):
    """#173/#174: header, read and idle timeouts close stalled connections, a body over
    TIN_MAX_BODY gets 413, partial requests past the per-core budget get 503, connections past
    TIN_MAX_CONNS are closed at accept, and a waiting handler outlives the header timeout."""
    port = ws.free_port()
    env = dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_DEADLINE_MS='5000', TIN_GRACE='1',
               TIN_HEADER_TIMEOUT_MS='1000', TIN_READ_TIMEOUT_MS='2000', TIN_IDLE_TIMEOUT_MS='1500',
               TIN_MAX_BODY='1000000', TIN_MAX_BUFFERED='3000000', TIN_MAX_CONNS='40')
    server = subprocess.Popen([str(exe)], env=env)
    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)

        def conn():
            return socket.create_connection(('127.0.0.1', port), timeout=10)

        def closed_after(s, limit):
            s.settimeout(limit)
            t = time.time()
            try:
                while s.recv(65536):
                    pass
                return time.time() - t
            except socket.timeout:
                return None
            except ConnectionResetError:
                return time.time() - t

        cases = [
            ('partial headers', b'GET /fast HTTP/1.1\r\nHost: x\r\nX-a: ', 0.5, 4),
            ('nothing sent', b'', 0.5, 4),
            ('unfinished body', b'POST /users HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n0123456789', 1.5, 5),
        ]
        for name, data, low, high in cases:
            s = conn()
            if data:
                s.sendall(data)
            took = closed_after(s, high + 2)
            s.close()
            print('%s: closed after %s s' % (name, took and round(took, 2)))
            if took is None or took < low or took > high:
                failures.append('%s: closed after %r s, want %s to %s' % (name, took, low, high))
        s = conn()
        s.sendall(b'GET /fast HTTP/1.1\r\nHost: x\r\n\r\n')
        time.sleep(0.2)
        s.recv(1000)
        took = closed_after(s, 6)
        s.close()
        print('idle keep-alive: closed after %s s' % (took and round(took, 2)))
        if took is None or took < 1 or took > 4:
            failures.append('idle keep-alive closed after %r s' % took)
        with conn() as s:
            s.sendall(b'POST /users HTTP/1.1\r\nHost: x\r\nContent-Length: 2000000\r\n\r\n')
            got = s.recv(100)
            if not got.startswith(b'HTTP/1.1 413 '):
                failures.append('body over TIN_MAX_BODY: %r' % got)
        # A client still sending the body of a refused request must read the refusal: the
        # server lingers instead of closing with unread input (which would reset the connection).
        with conn() as s:
            try:
                s.sendall(b'POST /users HTTP/1.1\r\nHost: x\r\nContent-Length: 1500000\r\n\r\n' + b'b' * 1500000)
            except OSError:
                pass
            try:
                got = s.recv(100)
            except OSError as e:
                got = repr(e).encode()
            if not got.startswith(b'HTTP/1.1 413 '):
                failures.append('413 while the client sends its body: %r' % got)
        held = []
        for _ in range(4):
            c = conn()
            try:
                c.sendall(b'POST /users HTTP/1.1\r\nHost: x\r\nContent-Length: 900000\r\n\r\n' + b'a' * 800000)
            except OSError:
                pass
            held.append(c)
            time.sleep(0.2)
        refused = 0
        for c in held:
            c.settimeout(0.3)
            try:
                if c.recv(100).startswith(b'HTTP/1.1 503 '):
                    refused += 1
            except (socket.timeout, ConnectionResetError):
                pass
            c.close()
        print('partial 900 kB bodies past a 3 MB budget: %d of 4 refused' % refused)
        if refused != 1:
            failures.append('buffer budget: %d of 4 partial bodies refused, want 1' % refused)
        time.sleep(0.3)
        many = [conn() for _ in range(45)]
        time.sleep(0.5)
        shut = 0
        for c in many:
            c.settimeout(0.01)
            try:
                if c.recv(10) == b'':
                    shut += 1
            except (socket.timeout, ConnectionResetError):
                pass
        for c in many:
            c.close()
        print('45 connections with TIN_MAX_CONNS=40: %d closed at accept' % shut)
        if shut != 5:
            failures.append('connection cap: %d of 45 closed at accept, want 5' % shut)
        time.sleep(0.3)
        status, _, body = request(port, 'GET', '/users/7?ms=1500')
        if status != 200 or not body.startswith(b'user 7'):
            failures.append('a handler waiting past the header timeout: %r %r' % (status, body))
        if server.poll() is not None:
            failures.append('the server exited during the limit checks')
    finally:
        stop(server)


def overflow(exe, failures):
    """#175, #342: a handler that overflows its task stack is a panic of that request: it
    answers 500 with the panic and a backtrace on stderr, and the server, its other requests
    and the next overflow are unaffected."""
    for stack, depth in (('', 1000), ('1048576', 20000)):
        port = ws.free_port()
        env = dict(os.environ, PORT=str(port), TIN_CORES='2')
        if stack:
            env['TIN_TASK_STACK'] = stack
        server = subprocess.Popen([str(exe)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                try:
                    socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                    break
                except OSError:
                    time.sleep(0.05)
            status, _, body = request(port, 'GET', '/recurse?n=%d' % depth)
            if status != 200 or body != b'depth %d' % depth:
                failures.append('shallow recursion (stack %r): %r %r' % (stack, status, body))
            if not stack:
                # 20000 levels do not fit 256 KiB, but fit TIN_TASK_STACK=1 MiB
                status, _, _ = request(port, 'GET', '/recurse?n=20000')
                if status != 500:
                    failures.append('20000 levels in the default stack: %r' % status)
            statuses = []
            for _ in range(6):
                statuses.append(request(port, 'GET', '/recurse?n=100000000')[0])
                ok = request(port, 'GET', '/recurse?n=10')
                if ok[0] != 200:
                    failures.append('a request after an overflow: %r' % (ok,))
            alive = server.poll() is None
        finally:
            server.terminate()
            try:
                code = server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                code = server.wait()
        err = server.stderr.read().decode(errors='replace')
        panics = err.count('panic: stack overflow')
        print('stack overflow in a handler (stack %s): statuses %s, %d panics logged, server alive %s, exit %s' %
              (stack or 'default', statuses, panics, alive, code))
        want_panics = 6 if stack else 7  # the default stack also overflowed on the 20000-level request
        if statuses != [500] * 6 or panics != want_panics or not alive or code != 0:
            failures.append('stack overflow (stack %r): %r panics %d alive %s exit %r' % (stack, statuses, panics, alive, code))
        if '\tdeep\n' not in err:
            failures.append('the backtrace of an overflow names deep: %r' % err[:400])


def overflow_guards(out, failures):
    """#342: a stack overflow in a detached task, a spawned child, an explicit guard, a tick and
    a relay handler is that one's panic, as in a request."""
    exe = out / 'guards'
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES='1'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        child = request(port, 'GET', '/childdeep')[-1]
        guarded = request(port, 'GET', '/guarded')[-1]
        request(port, 'GET', '/laterdeep')
        request(port, 'GET', '/ticknext')
        request(port, 'GET', '/send?m=deep')
        body = b''
        for _ in range(100):
            body = request(port, 'GET', '/overflows')[-1]
            if body == b'tick 1 relay 1 detach 1':
                break
            time.sleep(0.02)
        print('stack overflows in a child, a guard, a detached task, a tick and a relay handler:', child[:60], guarded[:60], body)
        if not child.startswith(b'child fault: panic: stack overflow') or not guarded.startswith(b'guard: panic: stack overflow'):
            failures.append('overflow faults: %r %r' % (child, guarded))
        if body != b'tick 1 relay 1 detach 1':
            failures.append('overflow in a tick, relay handler or detached task: %r' % body)
        if server.poll() is not None:
            failures.append('the server exited after an overflow in a guarded context')
    finally:
        server.terminate()
        try:
            code = server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            code = server.wait()
        err = server.stderr.read().decode(errors='replace')
        if err.count('panic: stack overflow') != 5 or code != 0:
            failures.append('overflow panics on stderr %d, exit %r: %r' % (err.count('panic: stack overflow'), code, err[-600:]))


def panics(exe, failures):
    """#142: a handler that panics, at once or after a wait, answers 500 and closes its
    connection; the panic and its backtrace go to stderr; other requests, including one
    waiting on the same core at the time, are served and the server keeps running. An integer
    overflow on request data (#362) is such a panic."""
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES='1'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        slow = {}
        t = threading.Thread(target=lambda: slow.setdefault('r', request(port, 'GET', '/users/5?ms=400')))
        t.start()
        time.sleep(0.1)
        got = [request(port, 'GET', p)[0] for p in ('/boom', '/boom?ms=100', '/fast', '/boom', '/fast')]
        t.join()
        print('panicking handlers and others:', got, 'waiting request:', slow.get('r', (0,))[0])
        if got != [500, 500, 200, 500, 200] or slow.get('r', (0,))[0] != 200:
            failures.append('panics: %r, waiting request %r' % (got, slow.get('r')))
        # #362: an integer overflow on request data is that request's panic.
        sums = [request(port, 'GET', p) for p in ('/add?a=2&b=3', '/add?a=9223372036854775807&b=1',
                                                   '/add?a=-9223372036854775808&b=-1', '/add?a=40&b=2')]
        print('sums:', [(s[0], s[-1]) for s in sums])
        if [s[0] for s in sums] != [200, 500, 500, 200] or sums[0][-1] != b'sum 5' or sums[3][-1] != b'sum 42':
            failures.append('overflow in a handler: %r' % [(s[0], s[-1]) for s in sums])
        if server.poll() is not None:
            failures.append('the server exited after a handler panicked')
        # #230: each panic ran the deferred calls of the frames it left, innermost first.
        r = request(port, 'GET', '/unwinds')
        body = r[-1]
        print('deferred calls run by the panics:', body)
        if body != b'inner;handler;' * 3:
            failures.append('defers during panics: %r' % body)
        # A panic inside a deferred call while unwinding ends the process.
        try:
            request(port, 'GET', '/double')
        except Exception:
            pass
        try:
            code = server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            code = None
        print('panic while unwinding: exit', code)
        if code != 2:
            failures.append('a panic during unwinding did not end the process: %r' % code)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        err = server.stderr.read().decode(errors='replace')
        if err.count('panic: index out of range [5] with length 3') != 3:
            failures.append('panic messages on stderr: %r' % err[:2000])
        if 'panic: first' not in err or 'panic: second' not in err:
            failures.append('a panic during unwinding must print both messages: %r' % err[-2000:])
        if err.count('panic: integer overflow: +') != 2:
            failures.append('overflow panics on stderr: %r' % err[:2000])


def implicit_guards(out, failures):
    """#230: ticks, relay handlers and detached tasks are guarded implicitly. A tick that
    panics (the first three), relay messages whose handler panics and a detached task that
    panics run their deferred calls and are logged; the core keeps ticking, handles the other
    messages and serves requests."""
    exe = out / 'guards'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/guards.tin'],
                   cwd=ROOT, check=True, env=dict(os.environ, TIN_ROOT=str(ROOT)))
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES='1'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    want = b'ticks true defers true; relay a;boom1;b;boom2;c; defers 5; detach defers 1'
    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        sent = request(port, 'GET', '/send?m=a,boom1,b,boom2,c')
        later = request(port, 'GET', '/later')
        body = b''
        for _ in range(100):
            body = request(port, 'GET', '/state')[-1]
            if body == want:
                break
            time.sleep(0.02)
        print('panicking ticks, relay handlers and detached task:', sent[0], later[0], body)
        if sent[0] != 200 or later[0] != 200 or body != want:
            failures.append('implicit guards: %r %r %r' % (sent, later, body))
        if server.poll() is not None:
            failures.append('the server exited after a tick or relay handler panicked')
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        err = server.stderr.read().decode(errors='replace')
        for msg in ('tick 1', 'tick 2', 'tick 3', 'relay boom1', 'relay boom2', 'detached boom'):
            if err.count('panic: %s\n' % msg) != 1:
                failures.append('panic %r on stderr: %r' % (msg, err[-2000:]))
        if server.returncode != 0:
            failures.append('guards server exit status %r' % server.returncode)


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
    print('-- limits')
    limits(exe, failures)
    print('-- panics')
    panics(exe, failures)
    print('-- stack overflow')
    overflow(exe, failures)
    print('-- implicit guards')
    implicit_guards(out, failures)
    print('-- stack overflow in guarded contexts')
    overflow_guards(out, failures)
    if failures:
        sys.exit('\n'.join(failures))


if __name__ == '__main__':
    main()
