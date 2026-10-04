#!/usr/bin/env python3
"""Boundary cancellation (#231): a cancel wakes a task parked in each client, and flows down only.

Private probes are appended to a temporary copy of lib/tide, never to the production API.
The drain phase checks that the end of the grace period cancels waiting requests.
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


def checks(port, fifo):
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
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), str(fixtures / 'cancel.tin')],
                       cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(directory)), check=True)
        fifo = directory / 'fifo'
        os.mkfifo(fifo)
        hole = Hole()
        port = ws.free_port()
        with (out / 'server.log').open('wb') as log:
            server = subprocess.Popen([str(exe)], stdout=log, stderr=log,
                env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1',
                         TIN_DEADLINE_MS='20000', HOLE_ADDR='127.0.0.1:%d' % hole.port,
                         FIFO=str(fifo)))
            try:
                eventually(lambda: server_ready(port, server))
                checks(port, str(fifo))
                assert server.poll() is None, 'server exited'
                budget(exe)
                drain(port, server)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == '__main__':
    main()
