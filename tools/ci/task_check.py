#!/usr/bin/env python3
"""Request tasks: on one core, waiting requests overlap and do not delay fast ones; deadlines
cut waits short; pipelined responses stay in order behind a waiting request."""
import os
import socket
import subprocess
import sys
import threading
import time
from suite import ROOT


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def fetch(port, raw, timeout=5):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    t0 = time.time()
    s.sendall(raw)
    data = b''
    while True:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
    s.close()
    return time.time() - t0, data


def get(port, path):
    return fetch(port, ('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())


def main():
    out = ROOT / 'bin/ci/tasks'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'tasks'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'examples/tasks.tin'], cwd=ROOT, check=True,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)))
    port = free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_DEADLINE_MS='1500'))
    failures = []
    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        slow = {}

        def one(i):
            slow[i] = get(port, '/slow?ms=400')

        threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
        t0 = time.time()
        for t in threads:
            t.start()
        time.sleep(0.05)
        fast = [get(port, '/fast')[0] for _ in range(30)]
        for t in threads:
            t.join()
        total = time.time() - t0
        bodies = [d.split(b'\r\n\r\n', 1)[-1] for _, d in slow.values()]
        print('8 x 400 ms waits in %.3f s; fast requests meanwhile: max %.1f ms' % (total, max(fast) * 1000))
        if total > 1.2:
            failures.append('waiting requests did not overlap (%.3f s)' % total)
        if max(fast) > 0.1:
            failures.append('a fast request waited %.1f ms' % (max(fast) * 1000))
        if any(not b.startswith(b'slept') for b in bodies):
            failures.append('slow bodies: %r' % bodies)
        prox = {}

        def proxy(i):
            prox[i] = get(port, '/proxy?ms=400')

        threads = [threading.Thread(target=proxy, args=(i,)) for i in range(6)]
        t0 = time.time()
        for t in threads:
            t.start()
        time.sleep(0.05)
        fast = [get(port, '/fast')[0] for _ in range(20)]
        files = [get(port, '/file?n=%d' % i) for i in range(5)]
        for t in threads:
            t.join()
        total = time.time() - t0
        bodies = [d.split(b'\r\n\r\n', 1)[-1] for _, d in prox.values()]
        print('6 proxied 400 ms calls in %.3f s; fast meanwhile: max %.1f ms; file: max %.1f ms' %
              (total, max(fast) * 1000, max(f[0] for f in files) * 1000))
        if total > 1.2:
            failures.append('proxied calls did not overlap (%.3f s)' % total)
        if max(fast) > 0.1:
            failures.append('a fast request waited %.1f ms behind proxies' % (max(fast) * 1000))
        if any(not b.startswith(b'via proxy: slept') for b in bodies):
            failures.append('proxy bodies: %r' % bodies)
        if any(not f[1].endswith(b'file: hello from a helper thread') for f in files):
            failures.append('file bodies: %r' % [f[1][-60:] for f in files])
        dt, d = get(port, '/proxy?ms=1&port=1')
        print('refused upstream: %.3f s, %r' % (dt, d.split(b'\r\n')[0]))
        if not d.startswith(b'HTTP/1.1 502') or dt > 1:
            failures.append('refused upstream: %.3f s %r' % (dt, d[-80:]))
        dt, d = get(port, '/slow?ms=5000')
        print('deadline: %.3f s, %r' % (dt, d.split(b'\r\n')[0]))
        if not d.startswith(b'HTTP/1.1 504') or dt > 2.5:
            failures.append('deadline: %.3f s %r' % (dt, d[:60]))
        _, d = fetch(port, b'GET /slow?ms=100 HTTP/1.1\r\nHost: x\r\n\r\nGET /fast HTTP/1.1\r\nHost: x\r\n\r\n'
                           b'GET /slow?ms=30 HTTP/1.1\r\nHost: x\r\n\r\nGET /fast HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
        order = [p.split(b'\r\n\r\n', 1)[1][:5] for p in d.split(b'HTTP/1.1 ')[1:]]
        print('pipelined order:', order)
        if order != [b'slept', b'fast', b'slept', b'fast']:
            failures.append('pipelined responses out of order: %r' % order)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if failures:
        sys.exit('\n'.join(failures))


if __name__ == '__main__':
    main()
