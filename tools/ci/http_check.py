#!/usr/bin/env python3
"""Bounded HTTP correctness, request-pool RSS, and graceful-shutdown checks."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from suite import ROOT


def check(command, **kwargs):
    subprocess.run(command, cwd=ROOT, check=True, timeout=300, **kwargs)


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    out = ROOT / 'bin/ci/http'
    out.mkdir(parents=True, exist_ok=True)
    check([str(ROOT / 'bin/tinc'), '-o', str(out / 'api'), 'examples/api.tin'])
    check(['go', 'build', '-o', str(out / 'conformance'), './bench/http/conformance/main.go'])
    check(['go', 'build', '-o', str(out / 'graceful'), './tests/graceful/graceful.go'])
    number = port()
    with (out / 'server.log').open('w') as log:
        server = subprocess.Popen([str(out / 'api')], cwd=ROOT, stdout=log, stderr=log,
                                  env=dict(os.environ, PORT=str(number), TIN_CORES='2', TIN_GRACE='2'))
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('HTTP server exited during startup; see server.log')
                try:
                    with socket.create_connection(('127.0.0.1', number), timeout=.1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('HTTP server readiness timed out')
            base = [str(out / 'conformance'), '-addr', f'127.0.0.1:{number}', '-pid', str(server.pid)]
            check(base + ['-heavy=false'])
            # Throughput is informational, not a timing gate. Warm up before measuring RSS.
            check(base + ['-only=rss', '-reqs=2000000'])
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    check([str(out / 'graceful'), str(out / 'api'), str(port())])


if __name__ == '__main__':
    main()
