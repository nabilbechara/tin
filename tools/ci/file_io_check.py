#!/usr/bin/env python3
"""File I/O on helper threads (#357): thousands of concurrent reads on one core all succeed (a
core may have 4096 jobs out and the next tasks wait for one instead of failing), the helper threads
scale with the cores (at least 4) or TIN_HELPERS, and tasks waiting for a job end at their
deadline while the core goes on serving."""
import os
import socket
import subprocess
import time

from suite import ROOT
import websocket_check as ws


def get(port, path, timeout=60):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())
    data = b''
    while True:
        part = s.recv(65536)
        if not part:
            break
        data += part
    s.close()
    head, _, body = data.partition(b'\r\n\r\n')
    return int(head.split()[1]), body


def threads(pid):
    status = '/proc/%d/status' % pid
    if os.path.exists(status):
        return int([l for l in open(status) if l.startswith('Threads:')][0].split()[1])
    out = subprocess.run(['ps', '-M', '-p', str(pid)], capture_output=True, text=True).stdout.strip().splitlines()
    return len(out) - 1


def start(exe, cores, **env):
    port = ws.free_port()
    p = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, PORT=str(port), TIN_CORES=str(cores), **env))
    for _ in range(100):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=.1).close()
            return p, port
        except OSError:
            assert p.poll() is None, 'server exited at startup'
            time.sleep(.05)
    raise AssertionError('server did not start')


def main():
    out = ROOT / 'bin/ci/files'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'files'
    subprocess.run([os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc')), '-o', str(exe), 'tools/ci/fixtures/files.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    data = out / 'data.txt'
    data.write_text('hello from a helper thread\n')
    q = '&file=' + str(data)

    # More concurrent reads than the 4096 jobs one core may have out: every one succeeds.
    p, port = start(exe, 1, TIN_DEADLINE_MS='120000')
    try:
        for n in (100, 5000, 9000):
            t0 = time.monotonic()
            status, body = get(port, '/files?n=%d%s' % (n, q), 120)
            assert (status, body) == (200, b'ok=%d bad=0 first=' % n), (n, status, body)
            print('%d concurrent file reads on one core: all ok in %.2f s' % (n, time.monotonic() - t0))
    finally:
        p.kill()
        p.wait()

    # Helper threads: the larger of 4 and the cores, or TIN_HELPERS.
    counts = {}
    for cores, helpers in ((2, '3'), (2, '9'), (8, ''), (1, '')):
        env = {'TIN_HELPERS': helpers} if helpers else {}
        p, port = start(exe, cores, **env)
        try:
            before = threads(p.pid)
            assert get(port, '/files?n=20' + q)[0] == 200
            time.sleep(.3)
            counts[(cores, helpers)] = threads(p.pid) - before
        finally:
            p.kill()
            p.wait()
    assert counts == {(2, '3'): 3, (2, '9'): 9, (8, ''): 8, (1, ''): 4}, counts
    print('helper threads started: TIN_HELPERS=3 -> 3, 9 -> 9; 8 cores -> 8; 1 core -> 4')

    # Reads that never finish (a FIFO nobody writes to) fill every helper thread: the tasks
    # past 4096 jobs wait, all end at the request's deadline, and the core goes on serving.
    fifo = out / 'fifo'
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(fifo)
    p, port = start(exe, 1, TIN_HELPERS='2', TIN_DEADLINE_MS='1500')
    try:
        t0 = time.monotonic()
        status, body = get(port, '/files?n=5000&file=' + str(fifo), 30)
        took = time.monotonic() - t0
        assert (status, body) == (200, b'ok=0 bad=5000 first=deadline exceeded') and 1.2 < took < 6, (status, body[:80], took)
        t0 = time.monotonic()
        assert get(port, '/ok') == (200, b'ok')
        assert time.monotonic() - t0 < 1, 'the core did not serve after the waiting tasks ended'
        print('5000 reads of a FIFO nobody writes: every one ends with "deadline exceeded" after %.1f s, and /ok answers at once' % took)
    finally:
        p.kill()
        p.wait()


if __name__ == '__main__':
    main()
