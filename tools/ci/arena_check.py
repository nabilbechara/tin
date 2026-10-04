#!/usr/bin/env python3
"""arena { } (#236): a batch loop whose steps run in arenas keeps a flat peak RSS, and arenas
in request handlers that wait inside them interleave on one core with correct answers.

The fixture (tools/ci/fixtures/arenas.tin, edition 1) writes every page of about 8 MB per
step. Without arenas the steps pile up in the pool, which the check uses as a control: the
measurement must see that growth, so a flat arena run is not a measurement that sees nothing.
Peak RSS is Linux acceptance (docs/CI.md); macOS runs everything and reports the numbers.
"""
import os
import subprocess
import sys
import threading

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
import websocket_check as ws

MIB = 1024 * 1024


def peak_rss(exe, mode, steps):
    """Runs one batch and returns its peak RSS in bytes (ru_maxrss of that child only)."""
    env = dict(os.environ, ARENA_BATCH=mode, ARENA_STEPS=str(steps), TIN_CORES='1')
    p = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, env=env)
    out = p.stdout.read()
    _, status, usage = os.wait4(p.pid, 0)
    p.stdout.close()
    p.returncode = os.waitstatus_to_exitcode(status)
    assert p.returncode == 0, (mode, steps, p.returncode, out)
    want = b'total %d\n' % (999999 * steps)
    assert out == want, (mode, steps, out)
    kb = usage.ru_maxrss
    return kb if sys.platform == 'darwin' else kb * 1024


def batches(exe):
    small = peak_rss(exe, 'arena', 10)
    large = peak_rss(exe, 'arena', 200)
    plain_small = peak_rss(exe, 'plain', 10)
    plain_large = peak_rss(exe, 'plain', 40)
    print('arena batch: peak RSS %.1f MiB after 10 steps, %.1f MiB after 200 steps (8 MB each)'
          % (small / MIB, large / MIB))
    print('plain batch (control): peak RSS %.1f MiB after 10 steps, %.1f MiB after 40 steps'
          % (plain_small / MIB, plain_large / MIB))
    if sys.platform == 'linux':
        assert plain_large - plain_small > 150 * MIB, 'the control did not grow: %d -> %d' % (plain_small, plain_large)
        assert large - small < 16 * MIB, 'arena batch peak RSS grew: %d -> %d' % (small, large)
        assert large < 64 * MIB, 'arena batch peak RSS %d is more than a few steps' % large
        print('arena batch: peak RSS stays flat (Linux)')


def rss(pid):
    return int(subprocess.check_output(['ps', '-o', 'rss=', '-p', str(pid)]).strip()) * 1024


def handlers(port, server):
    want = b'[' + b' '.join(b'%d:499999' % i for i in range(8)) + b']'
    peaks = []
    for _ in range(4):
        results = []

        def one(i):
            results.append((i, response(request(port, '/work/%d' % i, timeout=20))))
        threads = [threading.Thread(target=one, args=(i,)) for i in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 40
        for i, got in results:
            assert got == (200, b'work %d %s' % (i, want)), (i, got)
        peaks.append(rss(server.pid))
    print('40 concurrent requests x 4 rounds, 8 waiting arenas each on one core: all correct; '
          'RSS after each round %s MiB' % ' '.join('%.1f' % (p / MIB) for p in peaks))
    if sys.platform == 'linux':
        assert peaks[-1] - peaks[0] < 32 * MIB, 'RSS grew across rounds: %s' % peaks


def main():
    out = ROOT / 'bin/ci/arenas'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'arenas'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/arenas.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    batches(exe)
    port = ws.free_port()
    with (out / 'server.log').open('wb') as log:
        server = subprocess.Popen([str(exe)], stdout=log, stderr=log,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES='1'))
        try:
            eventually(lambda: server_ready(port, server))
            handlers(port, server)
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
