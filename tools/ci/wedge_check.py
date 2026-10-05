#!/usr/bin/env python3
"""A core held by a handler that never waits (#341): the monitor thread publishes how long its
event loop has not turned (anvil.StuckCores, anvil.StuckFor), and SIGTERM still ends the process
within the grace period when core 0 is the stuck one (Linux, where the signal is a descriptor)."""
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from suite import ROOT
import websocket_check as ws


def get(port, path, timeout=5):
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
    return data.split(b'\r\n\r\n', 1)[-1]


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
    out = ROOT / 'bin/ci/wedge'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'spin'
    # -nopolls: the monitor is the backstop for code that does not poll (@nopoll, the standard
    # library); with polls, which a server program gets by default (#341), the spin would end at
    # its deadline instead of holding the core.
    subprocess.run([str(ROOT / os.environ.get('TIN_COMPILER', 'bin/tinc')), '-nopolls', '-o', str(exe), 'tools/ci/fixtures/spin.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    if not sys.platform.startswith('linux'):
        print('SKIP held cores: on macOS core 0 accepts every connection, so a held core 0 serves nothing (Linux only)')
        return
    # Two cores, one of them held: the other answers, and reports the held one.
    p, port = start(exe, 2, TIN_GRACE='2')
    try:
        assert get(port, '/stuck') == b'0 0', 'no core is stuck at first'
        threading.Thread(target=lambda: get(port, '/spin', 60), daemon=True).start()
        deadline = time.monotonic() + 25  # half the connections land on the held core and time out
        seen = None
        while time.monotonic() < deadline and seen is None:
            time.sleep(.3)
            try:
                body = get(port, '/stuck', .7).split()
            except OSError:
                continue  # that connection went to the held core
            if body and int(body[0]) == 1 and int(body[1]) >= 1500:
                seen = body
        assert seen, 'the held core was not reported'
        print('a core held by a spinning handler: StuckCores %s, StuckFor %s ms' % (seen[0].decode(), seen[1].decode()))
    finally:
        p.kill()
        p.wait()
    if True:  # (Linux only, see above)
        # One core, held: SIGTERM is read by no one, the monitor ends the process after the grace period.
        p, port = start(exe, 1, TIN_GRACE='2', TIN_DEADLINE_MS='1000')
        try:
            assert get(port, '/ok') == b'ok'
            threading.Thread(target=lambda: get(port, '/spin', 60), daemon=True).start()
            time.sleep(.5)
            t0 = time.monotonic()
            p.send_signal(signal.SIGTERM)
            code = p.wait(timeout=12)
            took = time.monotonic() - t0
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
        print('SIGTERM with core 0 held: exit %d after %.1f s (grace 2 s)' % (code, took))
        assert code == 0 and took < 6, (code, took)


if __name__ == '__main__':
    main()
