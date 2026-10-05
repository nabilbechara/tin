#!/usr/bin/env python3
"""shared let and atomic (#344): a 100 MB table in a shared let is built once and read by every
core, so the process's resident memory does not grow with TIN_CORES (a per-core global would take
100 MB per core), every core sees the same table, and atomic.Int counts exactly under concurrent
requests that land on different cores. Fixture shared.tin."""
import os
import socket
import subprocess
import threading
import time

import websocket_check as ws
from suite import ROOT
from router_check import request


def rss(pid):
    status = '/proc/%d/status' % pid
    if os.path.exists(status):
        return int([l for l in open(status) if l.startswith('VmRSS:')][0].split()[1]) * 1024
    return int(subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True).stdout) * 1024


def get(port, path):
    status, _, body = request(port, 'GET', path)
    assert status == 200, (path, status, body)
    return body.decode()


def run(exe, cores):
    port = ws.free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES=str(cores)),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(400):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=.1).close()
                break
            except OSError:
                assert server.poll() is None, 'server exited at startup'
                time.sleep(.05)
        sums = {get(port, '/sum') for _ in range(40)}
        assert sums == {'12500000 235076008923'}, sums
        lookups = {get(port, '/lookup') for _ in range(40)}
        assert lookups == {'30000 449985000'}, lookups
        bumps = 4000
        errors = []

        def work(n):
            try:
                for _ in range(n):
                    get(port, '/hit')
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=work, args=(bumps // 8,)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors[:2]
        count = int(get(port, '/count'))
        assert count == bumps, (cores, count)
        return rss(server.pid), count
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def main():
    out = ROOT / 'bin/ci/shared'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'shared'
    compiler = os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc'))
    subprocess.run([compiler, '-o', str(exe), 'tools/ci/fixtures/shared.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    one, c1 = run(exe, 1)
    eight, c8 = run(exe, 8)
    print('100 MB shared let: resident %d MiB on 1 core, %d MiB on 8 cores; the atomic counter counted %d and %d' %
          (one >> 20, eight >> 20, c1, c8))
    assert one > 90 << 20, one
    assert eight - one < 40 << 20, (one, eight)


if __name__ == '__main__':
    main()
