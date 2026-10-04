#!/usr/bin/env python3
"""Structured concurrency in requests (#232): children of a scope overlap their waits on the
request's core, and the first child fault cancels the others at once.

The fixture (tools/ci/fixtures/scopes.tin, edition 1) runs fetchAll from design_semantics
section 6 inside handlers, many requests at a time on one core.
"""
import os
import subprocess
import threading
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
import websocket_check as ws


def timed(port, path):
    start = time.monotonic()
    got = response(request(port, path, timeout=10))
    return got, time.monotonic() - start


ALL = b'[p0 p1 p2 p3] 4 at once'


def checks(port):
    # The children count how many of them are waiting at once, so overlap shows in the body
    # rather than in timings a slow runner can stretch; the time bounds are far from the
    # 5 s a sibling waits when a fault does not cancel it.
    (status, body), took = timed(port, '/all')
    assert (status, body) == (200, ALL), (status, body)
    assert took < 0.5, 'four overlapping 100 ms children took %.3f s' % took
    print('fetchAll: 4 children waiting 100 ms each, all at once, answered in %.0f ms' % (took * 1000))

    (status, body), took = timed(port, '/fail')
    assert (status, body) == (200, b'fault: child 2 failed'), (status, body)
    assert took < 0.5, 'a child fault should cancel the siblings that wait 5 s (%.3f s)' % took
    print('first fault: siblings cancelled, answered in %.1f ms' % (took * 1000))

    # Many requests with scopes on one core: each gets its own children and results.
    results = []
    def one(path):
        results.append((path, timed(port, path)[0]))
    threads = [threading.Thread(target=one, args=('/all' if i % 3 else '/fail',)) for i in range(60)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    took = time.monotonic() - start
    for path, got in results:
        want = (200, ALL) if path == '/all' else (200, b'fault: child 2 failed')
        assert got == want, (path, got)
    assert took < 2, '60 concurrent scoped requests took %.2f s' % took
    print('60 concurrent requests with scopes on one core: all correct in %.2f s' % took)


def main():
    out = ROOT / 'bin/ci/scopes'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'server'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/scopes.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    with (out / 'server.log').open('wb') as log:
        server = subprocess.Popen([str(exe)], stdout=log, stderr=log,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES='1'))
        try:
            eventually(lambda: server_ready(port, server))
            checks(port)
            assert server.poll() is None, 'server exited'
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
