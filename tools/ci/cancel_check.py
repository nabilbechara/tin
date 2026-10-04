#!/usr/bin/env python3
"""Boundary cancellation (#231): a cancel wakes a task parked in each client, and flows down only.

Private probes are appended to a temporary copy of lib/tide, never to the production API.
The drain phase checks that the end of the grace period cancels waiting requests.
The budget phases check TIN_REQUEST_MEMORY and a limit block inside a handler (#235).
Every client points at a server that accepts connections and never answers, so each request
parks in its client until /cancel/{i} cancels the boundary that request marked.
"""
import os
from pathlib import Path
import select
import signal
import shutil
import socket
import subprocess
import tempfile
import threading
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
import websocket_check as ws


class Hole:
    """Accepts TCP connections and holds them open without a byte of reply."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self.conns = []
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(c)


def pending(s, seconds=.3):
    r, _, _ = select.select([s], [], [], seconds)
    return not r


def cancel(port, i):
    assert response(request(port, '/cancel/%d' % i)) == (200, b'ok')


def finished(s, want, seconds=2):
    r, _, _ = select.select([s], [], [], seconds)
    assert r, 'the cancelled wait did not end within %s s' % seconds
    got = response(s)
    assert got == (200, want), 'got %r, want %r' % (got, want)


def checks(port, fifo, stdin):
    # Each client: the parked request ends with the cancel's fault, not after a timeout.
    for i, kind in enumerate(['tide', 'wire', 'redis', 'mysql', 'postgres', 'websocket', 'file'], 1):
        s = request(port, '/park/%d/%s' % (i, kind), timeout=10)
        assert pending(s), '%s: the wait ended before the cancel' % kind
        start = time.monotonic()
        cancel(port, i)
        finished(s, b'fault: canceled: test reason %d' % i)
        print('%-9s cancelled wait ended in %.1f ms with "canceled: test reason %d"'
              % (kind, (time.monotonic() - start) * 1000, i))
        if kind == 'file':
            # Let the helper thread's blocked open finish; its late result is disposed.
            fd = os.open(fifo, os.O_WRONLY)
            os.close(fd)

    # Waits that used to block the core (#316): a relay receive, stdin and a flume reader on
    # a pipe. Each parks its task; another request is served meanwhile; a cancel ends it.
    for i, kind in enumerate(['relay', 'stdin', 'flume'], 26):
        s = request(port, '/park/%d/%s' % (i, kind), timeout=10)
        assert pending(s), '%s: the wait ended before the cancel' % kind
        assert response(request(port, '/plain', timeout=2)) == (200, b'plain ok'), \
            '%s: the core stopped serving while the task waited' % kind
        assert pending(s, .05), '%s: serving another request ended the wait' % kind
        start = time.monotonic()
        cancel(port, i)
        finished(s, b'fault: canceled: test reason %d' % i)
        print('%-9s cancelled wait ended in %.1f ms with "canceled: test reason %d"; the core '
              'kept serving' % (kind, (time.monotonic() - start) * 1000, i))
        # A within deadline ends the same wait with "deadline exceeded"; the request goes on.
        status, body = response(request(port, '/within/%s' % kind, timeout=10))
        assert status == 200, (kind, status, body)
        parts = dict(p.split(': ', 1) for p in body.decode().split('; '))
        assert parts['inner'] == 'deadline exceeded' and parts['after'] == 'ok', (kind, body)
        assert 40 <= int(parts['ms']) < 1000, (kind, body)
        print('%-9s block deadline: "deadline exceeded" after %s ms' % (kind, parts['ms']))

    # relay.Next still receives: a parked task wakes with the message another request sends.
    s = request(port, '/relay-next', timeout=10)
    assert pending(s)
    assert response(request(port, '/relay-send/hello')) == (200, b'sent')
    finished(s, b'from 0: hello')
    print('relay.Next: a parked task receives a message sent from another request')

    # Input still arrives: a parked flume reader wakes with a line, ReadStdin at the end.
    s = request(port, '/park/29/flume', timeout=10)
    assert pending(s)
    stdin.write(b'hi\n')
    stdin.flush()
    finished(s, b'no fault')
    s = request(port, '/park/29/stdin', timeout=10)
    assert pending(s)
    stdin.write(b'rest')
    stdin.close()
    finished(s, b'no fault')
    print('stdin: a parked flume reader and ReadStdin wake when input comes')

    # A task parked for a pooled connection (mysql Pool 1): the holder stays parked.
    holder = request(port, '/park/20/mysql', timeout=10)
    assert pending(holder)
    waiter = request(port, '/park/21/mysql', timeout=10)
    assert pending(waiter)
    cancel(port, 21)
    finished(waiter, b'fault: canceled: test reason 21')
    assert pending(holder), 'cancelling the pool waiter ended the connection holder'
    cancel(port, 20)
    finished(holder, b'fault: canceled: test reason 20')
    print('pool wait: the parked waiter ends; the holder is untouched until its own cancel')

    # Sideways: cancelling one request leaves another parked request, and new ones, alone.
    a = request(port, '/park/22/tide', timeout=10)
    b = request(port, '/park/23/tide', timeout=10)
    assert pending(a) and pending(b)
    cancel(port, 22)
    finished(a, b'fault: canceled: test reason 22')
    assert pending(b), 'a cancel reached a sibling request'
    assert response(request(port, '/plain')) == (200, b'plain ok')
    cancel(port, 23)
    finished(b, b'fault: canceled: test reason 23')
    print('sideways: a sibling request keeps waiting; new requests are unaffected')

    # Up: cancelling a block inside a request leaves the request's own boundary live.
    s = request(port, '/nested/24', timeout=10)
    assert pending(s)
    cancel(port, 24)
    finished(s, b'inner: canceled: test reason 24; outer: []; after: ok')
    print('up: a cancelled block does not cancel its request; later waits succeed')

    # Down: cancelling the request cancels the block inside it, and stays cancelled.
    s = request(port, '/outer/25', timeout=10)
    assert pending(s)
    cancel(port, 25)
    finished(s, b'inner: canceled: test reason 25; block: test reason 25; '
                b'again: canceled: test reason 25')
    print('down: a cancelled request cancels its blocks; its next wait fails at once')

    # Explicit cancellation also stops code which never reaches another wait.
    start = time.monotonic()
    assert response(request(port, "/cpu-cancel", timeout=5))[0] == 500
    assert time.monotonic() - start < 1
    assert response(request(port, "/plain")) == (200, b"plain ok")
    print("CPU cancel: a self-cancelled spin unwinds; the server keeps serving")

    # A block deadline: the earlier deadline wins and is a deadline, not a cancel.
    status, body = response(request(port, '/within', timeout=10))
    assert status == 200, (status, body)
    parts = dict(p.split(': ', 1) for p in body.decode().split('; '))
    assert parts['inner'] == 'deadline exceeded' and parts['after'] == 'ok', body
    assert 40 <= int(parts['ms']) < 1000, body
    print('block deadline: "deadline exceeded" after %s ms; the request continues' % parts['ms'])


def drain(port, server):
    # At the end of the grace period (TIN_GRACE=1) waiting requests are cancelled with
    # "draining", answer, and the server exits 0 instead of being cut off.
    a = request(port, '/park/30/redis', timeout=10)
    b = request(port, '/park/31/tide', timeout=10)
    assert pending(a) and pending(b)
    start = time.monotonic()
    server.send_signal(signal.SIGTERM)
    for s in (a, b):
        finished(s, b'fault: canceled: draining', seconds=3)
    took = time.monotonic() - start
    assert 0.8 <= took < 2.5, 'cancelled after %.2f s, want about the 1 s grace' % took
    code = server.wait(timeout=3)
    assert code == 0, 'exit %d' % code
    print('drain: waiting requests end with "canceled: draining" after %.2f s; exit 0' % took)


def budget(exe):
    # TIN_REQUEST_MEMORY: a request past its memory budget ends with 500; the server goes on.
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_REQUEST_MEMORY=str(16 << 20)))
    try:
        eventually(lambda: server_ready(port, server))
        got = [response(request(port, p))[0] for p in ('/hog', '/plain', '/hog', '/plain')]
        assert got == [500, 200, 500, 200], got
        assert server.poll() is None, 'server exited'
    finally:
        server.terminate()
        server.wait(timeout=5)
    err = server.stderr.read().decode(errors='replace')
    assert err.count("limit exceeded: the request's memory budget") == 2, err[-1000:]
    print('request budget: requests past TIN_REQUEST_MEMORY get 500; others are served')


def handler_limit(out):
    # A limit block in a handler (#235): past its memory budget it fails with fault.LimitExceeded,
    # the handler answers with that fault, and the server goes on serving.
    exe = out / 'limits'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/limits.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              env=dict(os.environ, PORT=str(port), TIN_CORES='1'))
    limited = (200, b'limited: limit exceeded true')
    try:
        eventually(lambda: server_ready(port, server))
        got = [response(request(port, p)) for p in ('/limited', '/plain', '/fits', '/limited', '/plain')]
        assert got == [limited, (200, b'plain ok'), (200, b'fits 2000000'), limited, (200, b'plain ok')], got
        # Eighteen limit blocks wait on one core at once, then each passes its own budget.
        results = []
        def one(path):
            results.append((path, response(request(port, path, timeout=10))))
        threads = [threading.Thread(target=one, args=('/limited' if i % 4 else '/plain',)) for i in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for path, got in results:
            assert got == (limited if path == '/limited' else (200, b'plain ok')), (path, got)
        assert len(results) == 24, results
        # q.Body() into a bounded type (#240): up to the bound it is the body; past it,
        # fault.LimitExceeded.
        for body, want in ((b'sixteen bytes ok', b'upload 16: sixteen bytes ok'),
                           (b'seventeen bytes!!', b'upload: length 17 is over the bound 16: limit exceeded true'),
                           (b'x' * 100000, b'upload: length 100000 is over the bound 16: limit exceeded true'),
                           (b'', b'upload 0: ')):
            assert post(port, '/upload', body) == (200, want), (len(body), post(port, '/upload', body))
        assert server.poll() is None, 'server exited'
    finally:
        server.terminate()
        server.wait(timeout=5)
    err = server.stderr.read().decode(errors='replace')
    assert 'panic' not in err, err[-1000:]
    # The body's length is checked before it is copied.
    asm = subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-S', 'tools/ci/fixtures/limits.tin'],
                         cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True,
                         capture_output=True, text=True).stdout
    assert 'BodyBound' in asm, 'bound(q.Body()) copies the body before checking its length'
    print('handler limit: a limit block past its budget gives fault.LimitExceeded to its handler; '
          'q.Body() into a bounded str is checked before it is copied; the server keeps serving')


def post(port, path, body):
    with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
        s.sendall(('POST %s HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'
                   % (path, len(body))).encode() + body)
        data = b''
        while True:
            part = s.recv(65536)
            if not part:
                break
            data += part
    head, _, rest = data.partition(b'\r\n\r\n')
    return int(head.split()[1]), rest


def main():
    out = ROOT / 'bin/ci/cancel'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cancel-', dir=out) as tmp:
        directory = Path(tmp)
        shutil.copytree(ROOT / 'lib', directory / 'lib')
        fixtures = ROOT / 'tools/ci/fixtures'
        with (directory / 'lib/tide/tide.tin').open('a') as f:
            f.write('\n' + (fixtures / 'cancel_probe.tin').read_text())
        exe = directory / 'server'
        subprocess.run([str(ROOT / 'bin/tinc'), '-polls', '-o', str(exe), str(fixtures / 'cancel.tin')],
                       cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(directory)), check=True)
        fifo = directory / 'fifo'
        os.mkfifo(fifo)
        hole = Hole()
        port = ws.free_port()
        with (out / 'server.log').open('wb') as log:
            # Stdin is a pipe nothing writes to, for the stdin and flume waits (#316).
            server = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=log, stderr=log,
                env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1',
                         TIN_DEADLINE_MS='20000', HOLE_ADDR='127.0.0.1:%d' % hole.port,
                         FIFO=str(fifo)))
            try:
                eventually(lambda: server_ready(port, server))
                checks(port, str(fifo), server.stdin)
                assert server.poll() is None, 'server exited'
                budget(exe)
                handler_limit(directory)
                drain(port, server)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()

    log = (out / "server.log").read_text()
    assert log.count("cpu cancel deferred") == 1, log[-2000:]
    assert log.count("request canceled: canceled: cpu stop") == 1, log[-2000:]


if __name__ == '__main__':
    main()
