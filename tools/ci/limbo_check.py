#!/usr/bin/env python3
"""A parked WebSocket task does not hold back reclamation (#358): with one WebSocket connection
waiting on the only core, 10 million overwrites of a cache entry (spread over requests) leave
the counted blocks, their bytes and the limbo small. Before, the connection's task kept every
dropped block in the limbo until it ended, and past 2^20 queued blocks the core pinned (leaked)
what it dropped. Fixture limbo.tin."""
import os
import subprocess
import time

import websocket_check as ws
from suite import ROOT
from router_check import request


def get(port, path):
    status, _, body = request(port, 'GET', path)
    assert status == 200, (path, status, body)
    return body.decode()


def stats(port):
    words = get(port, '/stats').split()
    return int(words[1]), int(words[3]), int(words[5])


def main():
    out = ROOT / 'bin/ci/limbo'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'limbo'
    compiler = os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc'))
    subprocess.run([compiler, '-o', str(exe), 'tools/ci/fixtures/limbo.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    ws.PORT = port
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES='1'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                ws.socket.create_connection(('127.0.0.1', port), timeout=.1).close()
                break
            except OSError:
                time.sleep(.05)
        c = ws.connect('/ws')
        ws.send(c, 1, b'hello')
        assert ws.recv(c) == (1, b'echo: hello')
        base = stats(port)
        t0 = time.monotonic()
        for _ in range(100):
            get(port, '/put?n=100000')
        blocks, nbytes, limbo = stats(port)
        print('parked WebSocket + 10000000 overwrites in %.1f s: counted blocks %d (%d at the start), %d bytes, limbo %d' %
              (time.monotonic() - t0, blocks, base[0], nbytes, limbo))
        assert limbo < 200000 and blocks < 1000 and nbytes < (4 << 20), (base, blocks, nbytes, limbo)
        # The connection still works, and what it reads is intact.
        ws.send(c, 1, b'again')
        assert ws.recv(c) == (1, b'echo: again')
        # A detached loop that waits inside hearth.Quiet holds back nothing either...
        get(port, '/spawn')
        time.sleep(.2)
        for _ in range(20):
            get(port, '/put?n=100000')
        blocks, nbytes, limbo = stats(port)
        print('a detached hearth.Quiet loop and 2000000 more overwrites: counted blocks %d, limbo %d' % (blocks, limbo))
        assert limbo < 200000 and blocks < 1000, (blocks, nbytes, limbo)
        # ...and one that waits plainly holds back everything dropped meanwhile.
        get(port, '/spawnloud')
        time.sleep(.2)
        for _ in range(20):
            get(port, '/put?n=100000')
        blocks, nbytes, limbo = stats(port)
        print('a detached loop with a plain wait and 2000000 more: counted blocks %d, limbo %d (the rule hearth.Quiet exists for)' % (blocks, limbo))
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        err = server.stderr.read().decode(errors='replace')
        assert 'panic' not in err, err[-400:]


if __name__ == '__main__':
    main()
