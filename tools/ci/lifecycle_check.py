#!/usr/bin/env python3
"""Server lifecycle (#238): use and on around startup, the drain and the stop.

The fixture (tools/ci/fixtures/lifecycle.tin, edition 1) opens a package-level use on each
core and prints its on handlers. A fault in on app.start (or in a use) ends startup with
status 1 before anything is accepted. SIGTERM drains: a waiting request is cancelled with
"draining" at the end of the grace period, every core runs on core.stop and closes its use,
then on app.stop runs (its own waits still work) and the process exits 0. anvil.Drain(d)
does the same from a handler.
"""
import os
import signal
import socket
import subprocess
import time

from suite import ROOT
from lifetime_check import request, response, eventually, server_ready
from cancel_check import pending, finished
import websocket_check as ws


def start(exe, log, port, **env):
    return subprocess.Popen([str(exe)], stdout=log, stderr=subprocess.STDOUT,
                            env=dict(os.environ, PORT=str(port), TIN_CORES='2', TIN_GRACE='1', **env))


def refused(port):
    try:
        socket.create_connection(('127.0.0.1', port), timeout=1).close()
    except OSError:
        return True
    return False


def startup_fails(exe, out, env, want):
    port = ws.free_port()
    path = out / 'fail.log'
    with path.open('wb') as log:
        server = start(exe, log, port, **env)
        code = server.wait(timeout=5)
    text = path.read_text(errors='replace')
    assert code == 1, 'exit %d, want 1: %s' % (code, text)
    assert want in text, text
    assert 'app.start' not in text.replace('on app.start', ''), text
    assert refused(port), 'the server accepted a connection after a failed start'
    print('startup: %r ends the process with status 1 before accepting' % want)


def lines(path):
    return path.read_text(errors='replace').splitlines()


def stopped(text, how):
    # app.start once, then each core's start; at the end each core stops and closes its
    # store, then app.stop runs last, then the process exits 0 (stdout is flushed at exit).
    assert text.count('app.start') == 1, text
    assert text.count('core.start 0') == 1 and text.count('core.start 1') == 1, text
    assert text.index('app.start') < text.index('core.start'), text
    for core in ('0', '1'):
        assert text.count('core.stop %s' % core) == 1, text
        assert text.count('close store %s' % core) == 1, text
        assert text.index('core.stop %s' % core) < text.index('close store %s' % core), text
    assert text.count('app.stop') == 1 and 'app.stop wait failed' not in text, text
    last = [l for l in text.splitlines() if l.strip()][-1]
    assert last == 'app.stop', 'app.stop must run last, after every core stopped: %s' % text
    print('%s: core.stop and the use closes ran on both cores, then app.stop; exit 0' % how)


def run(exe, out, how):
    port = ws.free_port()
    path = out / ('%s.log' % how)
    with path.open('wb') as log:
        server = start(exe, log, port)
        try:
            eventually(lambda: server_ready(port, server))
            assert response(request(port, '/hello'))[0] == 200
            parked = request(port, '/park', timeout=10)
            assert pending(parked)
            begin = time.monotonic()
            if how == 'SIGTERM':
                server.send_signal(signal.SIGTERM)
                grace = 1
            else:
                assert response(request(port, '/drain')) == (200, b'draining')
                grace = .3
            finished(parked, b'fault: canceled: draining', seconds=3)
            took = time.monotonic() - begin
            assert grace - .1 <= took < grace + 1, 'cancelled after %.2f s, want about %s s' % (took, grace)
            code = server.wait(timeout=3)
            assert code == 0, 'exit %d' % code
        finally:
            if server.poll() is None:
                server.kill()
                server.wait()
    print('%s: the waiting request ended with "canceled: draining" after %.2f s' % (how, took))
    stopped(path.read_text(errors='replace'), how)


def main():
    out = ROOT / 'bin/ci/lifecycle'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'server'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/lifecycle.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    startup_fails(exe, out, {'START_FAIL': '1'}, 'startup failed: on app.start: migration refused')
    startup_fails(exe, out, {'STORE_FAIL': '1'}, 'startup failed: use store: store unreachable')
    run(exe, out, 'SIGTERM')
    run(exe, out, 'anvil.Drain')


if __name__ == '__main__':
    main()
