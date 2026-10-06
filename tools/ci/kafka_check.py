#!/usr/bin/env python3
"""Kafka client connections in an event loop (#445): the fixture (tools/ci/fixtures/kafka_conn.tin,
one core) runs a fake broker as tasks beside its handlers, and GET /run checks what needs a
client's waits to overlap with other tasks: Close from another task ends a held fetch at once
(ErrClosed, not retried), one group's held JoinGroup holds up no fetch, and a caller whose own
deadline ends a handshake leaves the callers queued behind it their requests. The rest of #445
(request timeouts, reused connections, more clients, TLS reads, KIP-368) is in the strict suite:
tests/v2/kafka_conn.tin."""
import os
import subprocess
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
import websocket_check as ws


def main():
    out = ROOT / 'bin/ci/kafka'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'server'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/kafka_conn.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    with (out / 'server.log').open('wb') as log:
        server = subprocess.Popen([str(exe)], stdout=log, stderr=log,
                                  env=dict(os.environ, PORT=str(port), TIN_CORES='1'))
        try:
            eventually(lambda: server_ready(port, server))
            start = time.monotonic()
            status, body = response(request(port, '/run', timeout=60))
            took = time.monotonic() - start
            lines = body.decode(errors='replace').splitlines()
            for line in lines:
                print(line)
            assert status == 200, (status, body)
            assert len(lines) == 5 and all(l.startswith('ok ') for l in lines), lines
            assert server.poll() is None, 'server exited'
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
    print('PASS kafka: connections in an event loop (%.1f s)' % took)


if __name__ == '__main__':
    main()
