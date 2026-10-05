#!/usr/bin/env python3
"""Server lifecycle (#238): use and on around startup, the drain and the stop.

The fixture (tools/ci/fixtures/lifecycle.tin, edition 1) opens a package-level use on each
core and prints its on handlers. A fault in on app.start (or in a use) ends startup with
status 1 before anything is accepted. SIGTERM drains: a waiting request is cancelled with
"draining" at the end of the grace period, every core runs on core.stop and closes its use,
then on app.stop runs (its own waits still work) and the process exits 0. anvil.Drain(d)
does the same from a handler.
"""
import os
import re
import signal
import socket
import subprocess
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
from cancel_check import pending, finished
import websocket_check as ws


def start(exe, log, port, **env):
    return subprocess.Popen([str(exe)], stdout=log, stderr=subprocess.STDOUT,
                            env=dict(os.environ, PORT=str(port), TIN_CORES='2', TIN_GRACE='1', **env))


def refused(port):
    try:
        socket.create_connection(('127.0.0.1', port), timeout=1).close()
    except OSError:
        return True
    return False


def startup_fails(exe, out, env, want):
    port = ws.free_port()
    path = out / 'fail.log'
    with path.open('wb') as log:
        server = start(exe, log, port, **env)
        code = server.wait(timeout=5)
    text = path.read_text(errors='replace')
    assert code == 1, 'exit %d, want 1: %s' % (code, text)
    assert want in text, text
    assert 'app.start' not in text.replace('on app.start', ''), text
    assert refused(port), 'the server accepted a connection after a failed start'
    print('startup: %r ends the process with status 1 before accepting' % want)


def lines(path):
    return path.read_text(errors='replace').splitlines()


def stopped(text, how):
    # app.start once, then each core's start; at the end each core stops and closes its
    # store, then app.stop runs last, then the process exits 0 (stdout is flushed at exit).
    assert text.count('app.start') == 1, text
    assert text.count('core.start 0') == 1 and text.count('core.start 1') == 1, text
    assert text.index('app.start') < text.index('core.start'), text
    for core in ('0', '1'):
        assert text.count('core.stop %s' % core) == 1, text
        assert text.count('close store %s' % core) == 1, text
        assert text.index('core.stop %s' % core) < text.index('close store %s' % core), text
    assert text.count('app.stop') == 1 and 'app.stop wait failed' not in text, text
    last = [l for l in text.splitlines() if l.strip()][-1]
    assert last == 'app.stop', 'app.stop must run last, after every core stopped: %s' % text
    print('%s: core.stop and the use closes ran on both cores, then app.stop; exit 0' % how)


def run(exe, out, how):
    port = ws.free_port()
    path = out / ('%s.log' % how)
    with path.open('wb') as log:
        server = start(exe, log, port)
        try:
            eventually(lambda: server_ready(port, server))
            assert response(request(port, '/hello'))[0] == 200
            parked = request(port, '/park', timeout=10)
            assert pending(parked)
            begin = time.monotonic()
            if how == 'SIGTERM':
                server.send_signal(signal.SIGTERM)
                grace = 1
            else:
                assert response(request(port, '/drain')) == (200, b'draining')
                grace = .3
            finished(parked, b'fault: canceled: draining', seconds=3)
            took = time.monotonic() - begin
            assert grace - .1 <= took < grace + 1, 'cancelled after %.2f s, want about %s s' % (took, grace)
            code = server.wait(timeout=3)
            assert code == 0, 'exit %d' % code
        finally:
            if server.poll() is None:
                server.kill()
                server.wait()
    print('%s: the waiting request ended with "canceled: draining" after %.2f s' % (how, took))
    stopped(path.read_text(errors='replace'), how)


def http(s, path):
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\n\r\n' % path).encode())


def answer(s):
    """Reads one response from s: (status, headers, body)."""
    f = s.makefile('rb')
    status = int(f.readline().split()[1])
    headers = {}
    while True:
        h = f.readline()
        if h in (b'\r\n', b''):
            break
        k, _, v = h.decode().partition(':')
        headers[k.strip().lower()] = v.strip()
    body = f.read(int(headers.get('content-length', '0')))
    return status, headers, body


def admission(out):
    # A custom admission policy (#238): past two waiting requests on the core, new requests get
    # 503 with Retry-After before their handler runs, the connection stays open, and requests
    # are admitted again once the load drops.
    exe = out / 'admit'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/admit.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    log = out / 'admit.out'
    with log.open('wb') as stdout:
        server = subprocess.Popen([str(exe)], stdout=stdout, stderr=subprocess.PIPE,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES='1'))
    try:
        eventually(lambda: server_ready(port, server))
        conns = [socket.create_connection(('127.0.0.1', port), timeout=10) for _ in range(4)]
        # Each request has started waiting (3 s) before the next arrives, even on a slow runner.
        for s in conns:
            http(s, '/slow')
            time.sleep(0.2)
        got = [answer(s) for s in conns]
        assert [g[0] for g in got] == [200, 200, 503, 503], got
        assert [g[2] for g in got] == [b'slow ok', b'slow ok', b'Service Unavailable', b'Service Unavailable'], got
        assert got[2][1].get('retry-after') == '1' and got[3][1].get('retry-after') == '1', got
        assert 'retry-after' not in got[0][1], got
        # The refused connection stays open; with the load gone it is admitted again.
        http(conns[2], '/fast')
        status, _, body = answer(conns[2])
        assert (status, body) == (200, b'fast ok'), (status, body)
        for s in conns:
            s.close()
        # A second after the last refusal, an admitted request ends the overload.
        time.sleep(1.1)
        s = socket.create_connection(('127.0.0.1', port), timeout=10)
        http(s, '/fast')
        status, _, body = answer(s)
        s.close()
        assert (status, body) == (200, b'fast ok'), (status, body)
        assert server.poll() is None, 'server exited'
    finally:
        server.terminate()
        server.wait(timeout=15)
    err = server.stderr.read().decode(errors='replace')
    assert 'panic' not in err, err[-1000:]
    events = [l for l in lines(log) if l in ('overload', 'recovered')]
    assert events == ['overload', 'recovered'], (events, log.read_text())
    print('admission: past the policy, requests get 503 with Retry-After and no handler; '
          'the connection stays open; on server.overload and server.recovered run once each')


def serve_in_say(out):
    # #347: say.Line(anvil.Serve(...)) with a handler that keeps request data in a global used to
    # segfault at SIGTERM (exit 2): say.Line's formatting frame was open while requests ran.
    exe = out / 'serve_in_say'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/serve_in_say.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1'))
    try:
        eventually(lambda: server_ready(port, server))
        for n in range(1, 4):
            s = socket.create_connection(('127.0.0.1', port), timeout=10)
            s.sendall(b'POST /add HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello')
            status, _, body = answer(s)
            s.close()
            assert (status, body) == (200, b'len=%d' % n), (status, body)
        server.send_signal(signal.SIGTERM)
        stdout, stderr = server.communicate(timeout=30)
    finally:
        if server.poll() is None:
            server.kill()
    assert server.returncode == 0 and stdout == b'<nil>\n', (server.returncode, stdout, stderr[-1000:])
    print('serve in say.Line: three kept requests, then SIGTERM: <nil> and exit 0 (#347)')


def client_addr(out):
    # #355: RemoteAddr is the connection's peer; ClientIP believes X-Forwarded-For and Forwarded
    # only from TrustedProxies, taking the rightmost untrusted address, and formats IPv6 per
    # RFC 5952 (an IPv4-mapped address as IPv4).
    exe = out / 'client_addr'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/client_addr.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)

    def serve(trust, asks):
        port = ws.free_port()
        server = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES='1', TRUST=trust))
        got = []
        try:
            eventually(lambda: server_ready(port, server))
            for header in asks:
                s = socket.create_connection(('127.0.0.1', port), timeout=10)
                local = s.getsockname()[1]
                s.sendall(('GET /addr HTTP/1.1\r\nHost: x\r\n%s\r\n' % header).encode())
                status, _, body = answer(s)
                s.close()
                remote, client = body.decode().split(' ')
                assert status == 200 and remote == '127.0.0.1:%d' % local, (status, body, local)
                got.append(client)
        finally:
            server.terminate()
            _, stderr = server.communicate(timeout=15)
        # The access log of the anvil docs: a herald line per request, in order, with the client.
        logged = re.findall(r' INFO core=0 request method=GET route=/addr status=200 client=(\S+)$',
                            stderr.decode(), re.M)
        assert logged == got, ('the access log carries the client', logged, got)
        return got

    xff = lambda v: 'X-Forwarded-For: %s\r\n' % v
    fwd = lambda v: 'Forwarded: %s\r\n' % v
    got = serve('', ['', xff('203.0.113.7'), fwd('for=192.0.2.60')])
    assert got == ['127.0.0.1'] * 3, ('an untrusted peer: the headers are ignored', got)
    cases = [
        ('', '127.0.0.1'),
        (xff('203.0.113.7'), '203.0.113.7'),
        (xff('198.51.100.1, 203.0.113.7, 10.1.2.3'), '203.0.113.7'),
        (xff('10.0.0.1'), '10.0.0.1'),
        (xff('2001:DB8:0:0:0:0:0:1'), '2001:db8::1'),
        (xff('2001:db8:0:0:1:0:0:1'), '2001:db8::1:0:0:1'),
        (xff('::ffff:192.0.2.5'), '192.0.2.5'),
        (xff('fe80::1:2'), 'fe80::1:2'),
        (xff('garbage, 203.0.113.7'), '203.0.113.7'),
        (xff('203.0.113.7, 01.2.3.4'), '127.0.0.1'),
        (fwd('for="[2001:db8:cafe::17]:4711"'), '2001:db8:cafe::17'),
        (fwd('for=192.0.2.60;proto=http;by=203.0.113.43, for=10.9.9.9'), '192.0.2.60'),
        (fwd('For="192.0.2.61:8080"'), '192.0.2.61'),
    ]
    got = serve('127.0.0.0/8,10.0.0.0/8,fd00::/8', [h for h, _ in cases])
    assert got == [w for _, w in cases], list(zip([w for _, w in cases], got))
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30,
                            env=dict(os.environ, PORT=str(ws.free_port()), TRUST='10.0.0.0/8,10.0.0.0/33'))
    assert 'is not an IP address or network' in result.stdout, result
    print('client address: RemoteAddr, ClientIP behind trusted proxies only (X-Forwarded-For, Forwarded), '
          'RFC 5952 IPv6, mapped IPv4, malformed entries and a bad network refused (#355)')


def per_core_data(out):
    # #343: a global every core needs is built where every core runs. examples/percore.tin reads a
    # file in on core.start; with 2 and 4 cores every core answers with the same table, and the
    # requests on fresh connections reach every core.
    exe = out / 'percore'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'examples/percore.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    rows = out / 'rows.txt'
    rows.write_text('\n'.join('name%d' % i for i in range(1000)))
    for cores in (2, 4):
        port = ws.free_port()
        server = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES=str(cores), ROWS_FILE=str(rows)))
        counts, seen = set(), set()
        try:
            eventually(lambda: server_ready(port, server))
            for _ in range(8 * cores):
                s = socket.create_connection(('127.0.0.1', port), timeout=10)
                s.sendall(b'GET /count HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
                status, _, body = answer(s)
                s.close()
                assert status == 200, (status, body)
                table, _, core = body.decode().partition(' core ')
                counts.add(table)
                seen.add(int(core))
        finally:
            server.terminate()
            server.wait(timeout=15)
        assert counts == {'1000 1000'}, ('every core holds the table', cores, sorted(counts))
        assert seen == set(range(cores)), ('the requests reach every core', cores, sorted(seen))
    print('per-core data: examples/percore.tin builds its table in on core.start; 2 and 4 cores all answer 1000 1000 (#343)')


def main():
    out = ROOT / 'bin/ci/lifecycle'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'server'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/lifecycle.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    startup_fails(exe, out, {'START_FAIL': '1'}, 'startup failed: on app.start: migration refused')
    startup_fails(exe, out, {'STORE_FAIL': '1'}, 'startup failed: use store: store unreachable')
    run(exe, out, 'SIGTERM')
    run(exe, out, 'anvil.Drain')
    admission(out)
    serve_in_say(out)
    client_addr(out)
    per_core_data(out)


if __name__ == '__main__':
    main()
