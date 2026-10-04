#!/usr/bin/env python3
"""CPU-bound request deadlines and Linux drain must release a blocked single core (#234)."""
import os
import platform
import signal
import subprocess
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
from websocket_check import free_port


def run(exe, drain=False):
    port = free_port()
    proc = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1',
                 TIN_DEADLINE_MS='20000' if drain else '200'))
    try:
        eventually(lambda: server_ready(port, proc))
        start = time.monotonic()
        spinning = request(port, '/spin', timeout=5)
        if drain:
            time.sleep(.1)
            start = time.monotonic()
            proc.send_signal(signal.SIGTERM)
            code, _ = response(spinning)
            elapsed = time.monotonic() - start
            assert code == 500, code
            assert .8 < elapsed < 3, elapsed
            proc.wait(timeout=5)
        else:
            # This request queues on the very same core while /spin runs.
            plain = request(port, '/plain', timeout=5)
            code, _ = response(spinning)
            elapsed = time.monotonic() - start
            assert code == 504, code
            assert .1 < elapsed < 1, elapsed
            assert response(plain) == (200, b'ok')
            assert response(request(port, '/count')) == (200, b'1')
            # Reuse the task and its boundary; no stale poll may kill the next request.
            assert response(request(port, '/spin', timeout=5))[0] == 504
            assert response(request(port, '/plain')) == (200, b'ok')
            assert response(request(port, '/count')) == (200, b'2')
            assert proc.poll() is None
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    err = proc.stderr.read().decode(errors='replace')
    want = 'canceled: draining' if drain else 'deadline exceeded'
    assert err.count('request canceled: ' + want) == (1 if drain else 2), err
    assert 'panic:' not in err and 'core 0:' not in err, err
    print('PASS CPU %s: %.3f s, defers and server recovery' %
          ('drain' if drain else 'deadline', elapsed))


def guard_cleanup(exe):
    # A guard's defer may park; it must not suspend polling in another running task.
    port = free_port()
    proc = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_DEADLINE_MS='200'))
    try:
        eventually(lambda: server_ready(port, proc))
        waiting = request(port, '/guard-wait', timeout=5)
        time.sleep(.01)
        spinning = request(port, '/spin', timeout=5)
        start = time.monotonic()
        assert response(spinning)[0] == 504
        assert time.monotonic() - start < 1
        assert response(waiting) == (200, b'guard ok')
        assert response(request(port, '/plain')) == (200, b'ok')
        print('PASS parked guard cleanup: another task still polls and the guard resumes')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main():
    out = ROOT / 'bin/ci/poll'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'server'
    subprocess.run([str(ROOT / 'bin/tinc'), '-polls', '-edition', '1', '-o', str(exe),
                    str(ROOT / 'tools/ci/fixtures/poll.tin')], check=True, cwd=ROOT)
    run(exe)
    guard_cleanup(exe)
    if platform.system() == 'Linux':
        run(exe, drain=True)


if __name__ == '__main__':
    main()
