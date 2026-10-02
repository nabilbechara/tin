#!/usr/bin/env python3
"""Task-local formatting, detached helper deadlines, and WebSocket memory lifetimes.

Private probes are appended to temporary library copies, never to the production API.
Each protocol phase checks actual outputs and server liveness, with bounded waits.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

from suite import ROOT
import websocket_check as ws


def request(port, path, timeout=3):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())
    return s


def response(s):
    with s:
        data = b''
        while True:
            part = s.recv(65536)
            if not part:
                break
            data += part
    head, body = data.split(b'\r\n\r\n', 1)
    return int(head.split()[1]), body


def stats(port):
    status, body = response(request(port, '/stats'))
    assert status == 200
    closed, bad, helpers, saved, scoped = body.split(b'|')
    return int(closed), int(bad), int(helpers), saved, int(scoped)


def eventually(check, seconds=3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(.01)
    assert check(), 'condition did not become true'


def end_ws(c):
    ws.send(c, 8, b'\x03\xe8')
    assert ws.recv(c) == (8, b'\x03\xe8')
    c[0].close()


def checks(port, server, directory):
    # All helpers block on heap-owned dynamic paths. Their callers must return before
    # the FIFO is opened; meanwhile completed task records and pools are reused.
    files = [directory / ('fifo%d' % i) for i in range(4)]
    for f in files:
        os.mkfifo(f)
    started = time.monotonic()
    pending = [request(port, '/file?name=' + f.name) for f in files]
    for s in pending:
        assert response(s) == (504, b'deadline exceeded')
    assert time.monotonic() - started < 1.5
    assert stats(port)[2] == 4
    for _ in range(50):
        assert response(request(port, '/health')) == (200, b'healthy')
    # A queued job also expires without a free helper and is disposed on late completion.
    queued = directory / 'queued'
    queued.write_text('late result')
    assert response(request(port, '/file?name=queued')) == (504, b'deadline exceeded')
    assert stats(port)[2] == 5
    for f in files:
        fd = os.open(f, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
    eventually(lambda: stats(port)[2] == 0)
    assert response(request(port, '/file?name=queued')) == (200, b'late result')

    # An expired write still owns both its path and data until its helper finishes.
    fifo = directory / 'writefifo'
    os.mkfifo(fifo)
    assert response(request(port, '/write?name=writefifo&data=original')) == (504, b'deadline exceeded')
    for _ in range(50):
        assert response(request(port, '/health')) == (200, b'healthy')
    fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        received = bytearray()
        def drain():
            try:
                received.extend(os.read(fd, 4096))
            except BlockingIOError:
                pass
            return received == b'owned:original'
        eventually(drain)
    finally:
        os.close(fd)
    eventually(lambda: stats(port)[2] == 0)
    print('helper deadlines: running/queued reads and writes; late results disposed safely')

    ws.PORT = port
    c = ws.connect('/ws')
    for value in (b'keep', b'wait'):
        ws.send(c, 1, value)
        assert ws.recv(c) == (1, value)
    data = b'x' * 4096
    for _ in range(4000):
        ws.send(c, 2, data)
        assert ws.recv(c) == (2, data)
    # Control traffic and tiny fragments cannot build up temporary pool allocations
    # while one Read is still running, before Each can reset the message pool.
    for _ in range(1000):
        ws.send(c, 9, b'p' * 125)
        assert ws.recv(c) == (10, b'p' * 125)
    ws.send(c, 2, b'abcd', fin=False)
    for _ in range(999):
        ws.send(c, 0, b'abcd', fin=False)
    ws.send(c, 0, b'')
    assert ws.recv(c) == (2, b'abcd' * 1000)
    ws.send(c, 1, b'fault')
    assert ws.recv(c) == (1, b'outer:/ws|callback stopped')
    c[0].close()
    eventually(lambda: stats(port)[0] >= 1)
    assert stats(port)[3] == b'keep'
    assert stats(port)[4] == 4004
    assert stats(port)[1] == 0
    print('WebSocket scope: 4000 messages, pings/fragments, keep, waits, fault and outer objects')

    # Read retains its earlier result across subsequent reads: no hidden pool reset.
    c = ws.connect('/raw')
    ws.send(c, 1, b'first')
    ws.send(c, 1, b'second')
    assert ws.recv(c) == (1, b'first|second')
    c[0].close()
    eventually(lambda: stats(port)[0] >= 2)
    baseline = stats(port)[0]
    for _ in range(300):
        c = ws.connect('/ws')
        ws.send(c, 2, b'z' * 70000)
        assert ws.recv(c) == (2, b'z' * 70000)
        end_ws(c)
    c = ws.connect('/close')
    assert ws.recv(c) == (8, b'\x03\xe8')
    c[0].close()
    eventually(lambda: stats(port)[0] == baseline + 301)
    assert stats(port)[1] == 0, 'connection buffer was not released at task exit'
    assert server.poll() is None
    print('WebSocket cleanup: 300 closed connections, automatic release and repeated Close')


def main():
    out = ROOT / 'bin/ci/lifetime'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lifetime-', dir=out) as tmp:
        directory = Path(tmp)
        shutil.copytree(ROOT / 'lib', directory / 'lib')
        fixtures = ROOT / 'tools/ci/fixtures'
        for library, probe in [('runtime', 'helper_probe'), ('websocket', 'websocket_probe')]:
            with (directory / 'lib' / library / (library + '.tin')).open('a') as f:
                f.write('\n' + (fixtures / (probe + '.tin')).read_text())
        exe = directory / 'server'
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), str(fixtures / 'lifetime.tin')],
                       cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(directory)), check=True)
        port = ws.free_port()
        # Formatting's 300 ms wait needs a longer initial deadline; separate helper
        # requests below run on a second server with a 100 ms request deadline.
        for deadline, run in [('1000', 'format'), ('100', 'all')]:
            with (out / (run + '.log')).open('wb') as log:
                server = subprocess.Popen([str(exe)], stdout=log, stderr=log,
                    env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1',
                             TIN_DEADLINE_MS=deadline, REVIEW_DIR=str(directory)))
                try:
                    eventually(lambda: server_ready(port, server))
                    if run == 'format':
                        a = request(port, '/a'); time.sleep(.025); b = request(port, '/b')
                        assert response(a) == (200, b'A:/a')
                        assert response(b) == (200, b'B:/b')
                        assert server.poll() is None
                        print('overlapping formatting: correct outputs, server alive')
                    else:
                        checks(port, server, directory)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill(); server.wait()


def server_ready(port, server):
    assert server.poll() is None, 'server crashed during startup'
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.1):
            return True
    except OSError:
        return False


if __name__ == '__main__':
    main()
