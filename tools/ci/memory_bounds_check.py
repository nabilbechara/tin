#!/usr/bin/env python3
"""Memory bounds by default (#356): the request budget, the soft limit and anvil.Load's memory.

The fixture (tools/ci/fixtures/memory_bounds.tin, edition 1) keeps memory in a global
(/keep/{mb}), holds request pool while it waits (/hold/{mb}), allocates without bound (/hog)
and answers what its admission policy last saw in anvil.Load (/load).

Native phase (every platform): with TIN_MEMORY_SOFT set, Load.Ingot grows by what /keep keeps
and Load.Pool by what /hold holds; while the pool and ingot bytes are past the soft limit new
requests get 503 with Retry-After before their handler runs and on server.overload runs; once
the holds end, requests are served again and on server.recovered runs.

Container phase (Linux; macOS with TIN_DOCKER=1): the fixture runs in a 256 MiB cgroup (a
Docker container built FROM scratch, so nothing is pulled) with neither variable set. /hog
ends at the default request budget (a quarter of the limit per core) with 500 and the server
goes on; /keep then fills the long-lived heap until the default soft limit (90% of the limit)
refuses new requests with 503, well before the cgroup's OOM killer would end the process.
"""
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
import websocket_check as ws

MiB = 1 << 20


def build(out, target=None):
    exe = out / ('memory_bounds' if target is None else 'memory_bounds-' + target)
    cmd = [str(ROOT / 'bin/tinc'), '-edition', '1']
    if target:
        cmd += ['-target', target]
    subprocess.run(cmd + ['-o', str(exe), 'tools/ci/fixtures/memory_bounds.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    return exe


def get(port, path, timeout=10):
    """The status, headers and body of GET path on a connection of its own."""
    s = request(port, path, timeout)
    with s:
        data = b''
        while True:
            part = s.recv(65536)
            if not part:
                break
            data += part
    head, body = data.split(b'\r\n\r\n', 1)
    lines = head.decode().split('\r\n')
    headers = {}
    for line in lines[1:]:
        k, _, v = line.partition(':')
        headers[k.strip().lower()] = v.strip()
    return int(lines[0].split()[1]), headers, body


def load(port):
    status, _, body = get(port, '/load')
    assert status == 200, (status, body)
    words = body.split()
    assert words[0] == b'pool' and words[2] == b'ingot', body
    return int(words[1]), int(words[3])


def native(out):
    exe = build(out)
    port = ws.free_port()
    log = out / 'memory_bounds.out'
    with log.open('wb') as stdout:
        server = subprocess.Popen([str(exe)], stdout=stdout, stderr=subprocess.PIPE,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES='1',
                                           TIN_MEMORY_SOFT=str(64 * MiB)))
    try:
        eventually(lambda: server_ready(port, server), seconds=10)
        pool0, ingot0 = load(port)
        assert get(port, '/keep/16')[2] == b'kept 1'
        _, ingot1 = load(port)
        assert ingot1 - ingot0 >= 16 * MiB, (ingot0, ingot1)
        # A request holding 24 MiB of pool while it waits shows in the next request's Load.
        a = request(port, '/hold/24', timeout=10)
        time.sleep(0.4)
        pool1, _ = load(port)
        assert pool1 - pool0 >= 24 * MiB, (pool0, pool1)
        # Another 48 MiB passes the 64 MiB soft limit: new requests are refused, held ones go on.
        b = request(port, '/hold/48', timeout=10)
        time.sleep(0.4)
        status, headers, body = get(port, '/plain')
        assert (status, body) == (503, b'Service Unavailable'), (status, body)
        assert headers.get('retry-after') == '1', headers
        assert response(a) == (200, b'held %d' % (24 * MiB))
        assert response(b) == (200, b'held %d' % (48 * MiB))
        # The holds' pools are freed with their requests: below the limit, requests are served.
        assert get(port, '/plain')[::2] == (200, b'ok')
        pool2, _ = load(port)
        assert pool2 < 24 * MiB, (pool1, pool2)
        # A second after the last refusal, an admitted request ends the overload.
        time.sleep(1.1)
        assert get(port, '/plain')[::2] == (200, b'ok')
        assert server.poll() is None, 'server exited'
    finally:
        server.terminate()
        server.wait(timeout=15)
    err = server.stderr.read().decode(errors='replace')
    assert 'panic' not in err, err[-1000:]
    events = [l for l in log.read_text().split('\n') if l in ('overload', 'recovered')]
    assert events == ['overload', 'recovered'], (events, log.read_text())
    print('soft limit: Load.Pool and Load.Ingot count held and kept memory; past TIN_MEMORY_SOFT '
          'new requests get 503 with Retry-After; below it they are served; overload, recovered')


def docker_ok():
    if shutil.which('docker') is None:
        return False
    return subprocess.run(['docker', 'info'], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def docker(*args, check=True):
    return subprocess.run(['docker', *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, check=check)


def serving(port):
    # The published port accepts before the server listens: wait for an answer.
    try:
        return get(port, '/plain', timeout=1)[0] == 200
    except (OSError, ValueError, IndexError):
        return False


def container(out):
    target = None
    if sys.platform != 'linux':
        target = 'linux-arm64' if platform.machine() in ('arm64', 'aarch64') else 'linux-amd64'
    exe = build(out, target)
    tag = 'tin-memory-bounds-%d' % os.getpid()
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(exe, Path(d) / 'prog')
        (Path(d) / 'Dockerfile').write_text('FROM scratch\nCOPY prog /prog\nENTRYPOINT ["/prog"]\n')
        docker('build', '-q', '-t', tag, d)
    port = ws.free_port()
    try:
        docker('run', '-d', '--name', tag, '--memory', '256m', '--memory-swap', '256m',
               '-e', 'TIN_CORES=1', '-e', 'PORT=8080', '-p', '127.0.0.1:%d:8080' % port, tag)
        eventually(lambda: serving(port), seconds=20)
        # The default budget is a quarter of 256 MiB: /hog ends with 500, the next request is served.
        assert get(port, '/hog', timeout=30)[0] == 500
        assert get(port, '/plain')[::2] == (200, b'ok')
        assert get(port, '/hog', timeout=30)[0] == 500
        assert get(port, '/plain')[::2] == (200, b'ok')
        # Keep 4 MiB at a time: the default soft limit (90% of 256 MiB) refuses before the cgroup kills.
        kept = 0
        status = 200
        for _ in range(80):
            status, headers, body = get(port, '/keep/4', timeout=30)
            if status != 200:
                break
            kept += 4
        assert status == 503 and headers.get('retry-after') == '1', (status, kept)
        assert 192 <= kept <= 232, 'refused after keeping %d MiB of a 256 MiB container' % kept
        assert get(port, '/plain')[0] == 503
        state = docker('inspect', '-f', '{{.State.Running}} {{.State.OOMKilled}}', tag).stdout.split()
        assert state == ['true', 'false'], state
        # SIGTERM drains and exits 0, which also flushes the fixture's stdout.
        docker('stop', '-t', '10', tag)
        code = docker('inspect', '-f', '{{.State.ExitCode}}', tag).stdout.strip()
        assert code == '0', 'exit %s' % code
        logs = docker('logs', tag)
    finally:
        docker('rm', '-f', tag, check=False)
        docker('rmi', '-f', tag, check=False)
    assert logs.stderr.count("limit exceeded: the request's memory budget") == 2, logs.stderr[-1000:]
    assert 'overload' in logs.stdout.split('\n'), logs.stdout
    print('256 MiB cgroup: /hog ends at the default request budget with 500 and the server goes '
          'on; after %d MiB kept the default soft limit answers 503 and the process lives' % kept)


def main():
    with tempfile.TemporaryDirectory(prefix='tin-memory-bounds-') as d:
        out = Path(d)
        native(out)
        want = sys.platform == 'linux' or os.environ.get('TIN_DOCKER') == '1'
        if want and docker_ok():
            container(out)
        elif sys.platform == 'linux' and os.environ.get('CI'):
            raise SystemExit('the 256 MiB cgroup phase needs Docker on Linux CI runners')
        else:
            print('256 MiB cgroup: skipped (Linux with Docker, or TIN_DOCKER=1)')


if __name__ == '__main__':
    main()
