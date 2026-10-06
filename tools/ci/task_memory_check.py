#!/usr/bin/env python3
"""A 300-request heavy burst releases task pools/stack pages and caps cached tasks (#177)."""
import concurrent.futures
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from suite import ROOT
from task_check import free_port
from treeutil import copy_lib


def fetch(port, path):
    with socket.create_connection(('127.0.0.1', port), timeout=25) as s:
        s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())
        body = b''
        while True:
            part = s.recv(65536)
            if not part:
                break
            body += part
    assert body.startswith(b'HTTP/1.1 200 '), body[:200]
    return body.split(b'\r\n\r\n', 1)[1]


def rss(pid):
    return int(subprocess.check_output(['ps', '-o', 'rss=', '-p', str(pid)]).strip())


def main():
    out = ROOT / 'bin/ci/task-memory'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='burst-', dir=out) as tmp:
        work = Path(tmp)
        copy_lib(ROOT, work / 'lib')
        probe = work / 'lib/memoryprobe'
        probe.mkdir()
        shutil.copy(ROOT / 'tools/ci/fixtures/memory_probe.tin', probe / 'probe.tin')
        exe = work / 'server'
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe),
                        'tools/ci/fixtures/memory_burst.tin'], check=True,
                       env=dict(os.environ, TIN_ROOT=str(work)), cwd=ROOT, timeout=60)
        port = free_port()
        with (out / 'server.log').open('wb') as log:
            server = subprocess.Popen([str(exe)], stdout=log, stderr=log,
                env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_GRACE='1',
                         TIN_DEADLINE_MS='20000'))
            try:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        assert fetch(port, '/stats').split()[0] == b'0'
                        break
                    except OSError:
                        assert server.poll() is None
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.02)
                baseline = rss(server.pid)
                with concurrent.futures.ThreadPoolExecutor(max_workers=300) as pool:
                    pending = [pool.submit(fetch, port, '/heavy') for _ in range(300)]
                    deadline = time.monotonic() + 15
                    while fetch(port, '/stats').split()[0] != b'300':
                        assert server.poll() is None
                        assert time.monotonic() < deadline, '300 requests did not overlap'
                        time.sleep(.02)
                    peak = rss(server.pid)
                    assert fetch(port, '/release') == b'released'
                    answers = [future.result(timeout=25) for future in pending]
                    assert len(set(answers)) == 1 and answers[0].startswith(b'done '), answers[:5]
                for _ in range(300):
                    active, cached = map(int, fetch(port, '/stats').split())
                    assert active == 0 and cached <= 64, (active, cached)
                after = rss(server.pid)
                # RSS acceptance is Linux; macOS still exercises all task/response invariants.
                if sys.platform == 'linux':
                    assert peak > baseline + 300 * 1024, (baseline, peak)
                    assert after < baseline + 32 * 1024, (baseline, peak, after)
                print('PASS #177: 300 overlapping heavy requests, complete responses, cached tasks <= 64')
                print('RSS KiB baseline/peak/after:', baseline, peak, after)
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    main()
