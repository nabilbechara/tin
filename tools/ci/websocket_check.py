#!/usr/bin/env python3
"""WebSocket server (examples/websocket.tin, one core) and client (examples/websocket_client.tin):
handshake, text and binary, fragments with a ping between them, a 70000-byte message,
UTF-8 and masking rules, the close handshake, 300 idle connections on one core, 20 tick
streams waiting at the same time, and no request deadline on an upgraded connection."""
import os
import random
import socket
import struct
import base64
import hashlib
import subprocess
import sys
import threading
import time
from suite import ROOT

PORT = 0


def connect(path='/echo'):
    s = socket.create_connection(('127.0.0.1', PORT), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (path, key)).encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        buf += s.recv(4096)
    head, rest = buf.split(b'\r\n\r\n', 1)
    acc = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    assert head.startswith(b'HTTP/1.1 101'), head
    assert acc.encode() in head, head
    return [s, rest]
def send(c, op, data, fin=True, mask=True):
    b0 = (0x80 if fin else 0) | op
    n = len(data)
    if n < 126: h = struct.pack('BB', b0, (0x80 if mask else 0) | n)
    elif n < 65536: h = struct.pack('>BBH', b0, (0x80 if mask else 0) | 126, n)
    else: h = struct.pack('>BBQ', b0, (0x80 if mask else 0) | 127, n)
    if mask:
        k = os.urandom(4)
        data = bytes(x ^ k[i % 4] for i, x in enumerate(data))
        h += k
    c[0].sendall(h + data)
def recvn(c, n):
    while len(c[1]) < n:
        d = c[0].recv(65536)
        if not d: raise EOFError
        c[1] += d
    out, c[1] = c[1][:n], c[1][n:]
    return out
def recv(c):
    b0, b1 = recvn(c, 2)
    n = b1 & 127
    if n == 126: n = struct.unpack('>H', recvn(c, 2))[0]
    elif n == 127: n = struct.unpack('>Q', recvn(c, 8))[0]
    assert not b1 & 0x80
    return b0 & 15, recvn(c, n)
def free_port():
    """A free port below the ephemeral ranges (Linux 32768+, macOS 49152+). A port the kernel
    picks for bind(0) is an ephemeral one, which a client connection can take as its source
    port before the server binds it ("cannot bind the address" under load)."""
    for _ in range(500):
        port = random.randint(20000, 30000)
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
            except OSError:
                continue
            return port
    raise RuntimeError('no free port below the ephemeral range')


def checks():
    fails = []
    c = connect()
    send(c, 1, b'hello'); r = recv(c); print('text', r); fails += [] if r == (1, b'echo: hello') else ['text']
    send(c, 2, b'\x00\x01\xff'); r = recv(c); print('binary', r); fails += [] if r == (2, b'\x00\x01\xff') else ['binary']
    send(c, 1, b'frag', fin=False); send(c, 9, b'pp'); send(c, 0, b'ment', fin=False); send(c, 0, b'ed')
    r1 = recv(c); r2 = recv(c); print('ping during fragments', r1, r2); fails += [] if r1 == (10, b'pp') and r2 == (1, b'echo: fragmented') else ['frag']
    big = os.urandom(70000); send(c, 2, big); r = recv(c); print('70000 bytes', r[0], len(r[1]), r[1] == big); fails += [] if r == (2, big) else ['big']
    send(c, 1, 'héllo ✓'.encode()); r = recv(c); fails += [] if r == (1, 'echo: héllo ✓'.encode()) else ['utf8']
    send(c, 1, b'\xff\xfe'); r = recv(c); print('bad utf-8 ->', r); fails += [] if r[0] == 8 and r[1][:2] == b'\x03\xef' else ['badutf8']
    c = connect(); send(c, 1, b'x', mask=False); r = recv(c); print('unmasked ->', r); fails += [] if r[0] == 8 and r[1][:2] == b'\x03\xea' else ['unmasked']
    c = connect(); send(c, 8, b'\x03\xe8bye'); r = recv(c); print('close ->', r); fails += [] if r == (8, b'\x03\xe8') else ['close']
    try:
        d = c[0].recv(10); print('after close, server closed:', d == b'')
    except Exception as e: print('after close', e)
    # many concurrent idle connections + ticks
    conns = [connect() for _ in range(300)]
    t0 = time.time()
    for i, k in enumerate(conns): send(k, 1, b'%d' % i)
    ok = all(recv(k) == (1, b'echo: %d' % i) for i, k in enumerate(conns))
    print('300 connections echo:', ok, '%.3fs' % (time.time() - t0)); fails += [] if ok else ['many']
    res = {}
    def ticker(i):
        k = connect('/ticks'); got = []
        while True:
            op, d = recv(k)
            if op == 8: break
            got.append(d)
        res[i] = got
    t0 = time.time(); ts = [threading.Thread(target=ticker, args=(i,)) for i in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    dt = time.time() - t0
    okt = all(v == [b'tick %d' % j for j in range(1, 11)] for v in res.values())
    print('20 tick streams: %.2fs ok=%s' % (dt, okt)); fails += [] if okt and dt < 1.6 else ['ticks']
    s = socket.create_connection(('127.0.0.1', PORT)); s.sendall(b'GET /echo HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n'); print('plain GET /echo ->', s.recv(200).split(b'\r\n')[0])
    return fails


def main():
    global PORT
    out = ROOT / 'bin/ci/websocket'
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TIN_ROOT=str(ROOT))
    for name in ('websocket', 'websocket_client'):
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(out / name), 'examples/%s.tin' % name], cwd=ROOT, check=True, env=env)
    PORT = free_port()
    # A 300 ms request deadline: upgraded connections must not be subject to it.
    server = subprocess.Popen([str(out / 'websocket')], env=dict(os.environ, PORT=str(PORT), TIN_CORES='1', TIN_DEADLINE_MS='300'))
    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', PORT), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        fails = checks()
        r = subprocess.run([str(out / 'websocket_client'), 'ws://127.0.0.1:%d' % PORT], capture_output=True, text=True, timeout=30)
        print('tin client:', r.stdout.strip().replace('\n', ' | '))
        want = ['true echo: hi from tin', 'false 100000 true', 'tick 1', 'end: websocket: closed (1000) true', 'ticks 10',
                'websocket: the server refused the upgrade: HTTP/1.1 200 OK']
        if r.stdout.split('\n')[:6] != want:
            fails.append('tin client: %r' % r.stdout)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if fails:
        sys.exit('failed: %r' % fails)


if __name__ == '__main__':
    main()
