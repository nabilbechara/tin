#!/usr/bin/env python3
"""Replay tapes (#241): rt_effect records results and faults, and a replay serves them without
running the live call, keeps fault identity, and stops at the first divergence. Capsules (#241):
lib/replay writes a kept tape as an encrypted capsule into the bounded spool."""
import base64
import hashlib
import hmac
import os
from pathlib import Path
import random
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from suite import ROOT

EXPECTED = '''\
record first: one true ran 1
record fault: redis GET: deadline exceeded true ran 2
record word: 42
record bytes: abc
replay first: one true
replay fault: redis GET: deadline exceeded true
replay word: 42
replay bytes: abc
bodies run while replaying: 0 left: 0 diverged: false
past the end: replay: divergence at effect 4: got test@1 "third", recorded nothing more
sticky: true ran 0
mismatch: replay: divergence at effect 0: got test@1 "other", recorded test@1 "first"
live kind: fresh ran 1
secret handle unkeyed: tin-secret:unkeyed
child shares the tape: true
child panicked: true message on the tape: true
scope: true
'''

CAPSULE_KEY = bytes(range(32))
SECRETS = [b's3cr3t-token', b'c00k1e', b'k-123-secret', b'alice@example.com']


def open_capsule(data, key=CAPSULE_KEY):
    """The body of a capsule (notes/interface_replay.md, section 6), checked with the standard
    library's hmac; None when the tag does not match (a wrong key or a changed byte)."""
    km = hmac.new(key, b'tin replay mac', hashlib.sha256).digest()
    ke = hmac.new(key, b'tin replay enc', hashlib.sha256).digest()
    if data[:8] != b'TINCAP\x01\x00' or len(data) < 56:
        return None
    if not hmac.compare_digest(hmac.new(km, data[:-32], hashlib.sha256).digest(), data[-32:]):
        return None
    nonce, ct = data[8:24], data[24:-32]
    stream = b''.join(hmac.new(ke, nonce + struct.pack('<q', i), hashlib.sha256).digest()
                      for i in range((len(ct) + 31) // 32))
    return bytes(a ^ b for a, b in zip(ct, stream))


def decode_body(body):
    """The fields of a capsule body and its effect records (sections 3.3 and 6)."""
    pos = 0

    def word():
        nonlocal pos
        v = struct.unpack_from('<q', body, pos)[0]
        pos += 8
        return v

    def string():
        nonlocal pos
        n = word()
        s = body[pos:pos + n]
        assert len(s) == n, 'truncated'
        pos += n
        return s

    c = {'schema': word(), 'tin': string(), 'program': string(), 'wall': word(), 'core': word(),
         'status': word(), 'flags': word(), 'request': string(), 'panic': string(), 'count': word()}
    c['effects'] = []
    for _ in range(c['count']):
        c['effects'].append((word(), string().decode(), string().decode(), word(), word(), string()))
    assert pos == len(body), f'{len(body) - pos} bytes after the last effect'
    return c


def secret_handle(text, key=CAPSULE_KEY):
    ks = hmac.new(key, b'tin replay secret', hashlib.sha256).digest()
    return 'tin-secret:' + hmac.new(ks, text, hashlib.sha256).hexdigest()[:32]


def capsules(work, env):
    """Capsules end to end: tapes recorded by a fixture are written by lib/replay, opened here."""
    lib = work / 'lib/replaycapsule'
    lib.mkdir()
    shutil.copy(ROOT / 'tools/ci/fixtures/replay_capsule_probe.tin', lib / 'probe.tin')
    exe = work / 'replay_capsule'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay_capsule.tin'],
                   check=True, env=env, cwd=ROOT, timeout=60)
    failures = []

    def run(case, spool, **extra):
        run_env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_')}
        run_env.update(CAPSULE_CASE=case, TIN_REPLAY_DIR=str(spool), TIN_REPLAY_KEY=CAPSULE_KEY.hex())
        run_env.update(extra)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, env=run_env)
        if r.returncode != 0:
            failures.append(f'{case}: exit {r.returncode}\n{r.stdout}{r.stderr}')
        return r

    def check(name, got, want):
        if got != want:
            failures.append(f'{name}: got {got!r}, want {want!r}')

    def spool_files(spool):
        return sorted(p.name for p in spool.iterdir())

    # A failing request and a panicked one are kept; a 200 is not (no sample).
    spool = work / 'spool-basic'
    r = run('basic', spool, TIN_REPLAY_SECRET_HEADERS=' X-Api-Key ', TIN_REPLAY_DROP_HEADERS='x-email')
    check('basic output', r.stdout, 'on: true true\neffect: 2 books true\neffect fault: true\nword: 1234567\n')
    names = spool_files(spool)
    check('basic names', names, ['01700000000000000001-000-1.tcap', '01700000000000000002-001-1.tcap'])
    if len(names) == 2:
        raw = [(spool / n).read_bytes() for n in names]
        bodies = [open_capsule(d) for d in raw]
        if None in bodies:
            failures.append('basic: a capsule does not open with its key')
        else:
            first, second = decode_body(bodies[0]), decode_body(bodies[1])
            want_req = ('POST /checkout/7?x=1 HTTP/1.1\r\nHost: shop\r\nAuthorization: ' + secret_handle(b'Bearer s3cr3t-token') +
                        '\r\nCookie: ' + secret_handle(b'sid=c00k1e') + '\r\nX-Api-Key: ' + secret_handle(b'k-123-secret') +
                        '\r\nX-Email:\r\nContent-Length: 9\r\n\r\ncart=7&x=').encode()
            check('schema', first['schema'], 1)
            check('tin', first['tin'], b'dev')
            check('program', first['program'], str(exe).encode())
            check('wall, core, status, flags', (first['wall'], first['core'], first['status'], first['flags']),
                  (1700000000000000001, 0, 500, 0))
            check('stored request', first['request'], want_req)
            check('panic', first['panic'], b'')
            check('effects', first['effects'], [
                (0, 'redis@1', '3:GET 6:cart:7\n', 0, 0, b'2 books'),
                (1, 'wire.http@1', 'POST http://payments/charge\nAuthorization: ' + secret_handle(b'Bearer s3cr3t-token') + '\n\ncart=7',
                 1, 2, b'payments: deadline exceeded'),
                (2, 'tide.now@1', '', 0, 0, struct.pack('<q', 1234567)),
            ])
            check('panicked capsule', (second['core'], second['status'], second['flags'], second['panic'], second['count']),
                  (1, 500, 1, b'boom: index 3 out of range', 0))
            for secret in SECRETS:
                for n, data, body in zip(names, raw, bodies):
                    if secret in data or secret in body:
                        failures.append(f'secret text {secret!r} in capsule {n}')
            check('wrong key', open_capsule(raw[0], bytes(32)), None)
            for at in (3, 10, 40, len(raw[0]) - 40, len(raw[0]) - 1):
                damaged = bytearray(raw[0])
                damaged[at] ^= 1
                check(f'changed byte {at}', open_capsule(bytes(damaged)), None)
            check('no .tmp left', [n for n in names if n.endswith('.tmp')], [])
    # TIN_REPLAY_SAMPLE=1 keeps a 200, flagged as sampled.
    spool = work / 'spool-sample'
    run('sample', spool, TIN_REPLAY_SAMPLE='1')
    names = spool_files(spool)
    check('sampled names', names, ['01700000000000000003-001-1.tcap'])
    if names:
        c = decode_body(open_capsule((spool / names[0]).read_bytes()))
        check('sampled flags', (c['status'], c['flags']), (200, 2))
    spool = work / 'spool-unsampled'
    run('sample', spool, TIN_REPLAY_SAMPLE='0.0')
    check('unsampled', spool_files(spool), [])
    # The bound: each of the 2 cores keeps its newest capsules under 1 MiB / 2.
    spool = work / 'spool-bound'
    spool.mkdir()
    for i in range(4):
        (spool / f'0160000000000000000{i}-001-{i}.tcap').write_bytes(b'x' * 400000)
    (spool / 'notes.txt').write_text('not a capsule')
    run('bound', spool, TIN_REPLAY_MAX_MB='1')
    names = spool_files(spool)
    check('bound names', names, ['01700000000000000101-001-2.tcap', '01700000000000000105-000-6.tcap', 'notes.txt'])
    total = sum((spool / n).stat().st_size for n in names if n.endswith('.tcap'))
    if total > 1 << 20:
        failures.append(f'bound: the spool holds {total} bytes, more than 1 MiB')
    # Recording stays off without a valid key, and says so once.
    spool = work / 'spool-off'
    r = run('off', spool, TIN_REPLAY_KEY='abc')
    check('bad key', (r.stdout.splitlines()[:1], r.stderr), (['on: false false'],
          'replay: recording is off: TIN_REPLAY_KEY must be 64 hex digits\n'))
    check('bad key spool', spool.exists(), False)
    (ROOT / 'bin/ci/replay/capsules.log').write_text('\n'.join(failures))
    if failures:
        raise SystemExit('FAIL replay capsules:\n' + '\n'.join(failures))
    print('PASS replay capsules: kept 5xx, panics and samples; secrets as handles, dropped headers; '
          'the envelope opens with the key only; the spool bound deletes the oldest')


def free_port():
    """A free port below the ephemeral ranges (as task_check.py picks one)."""
    for _ in range(500):
        port = random.randint(20000, 30000)
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
            except OSError:
                continue
            return port
    raise RuntimeError('no free port below the ephemeral range')


def http(port, raw):
    s = socket.create_connection(('127.0.0.1', port), timeout=10)
    s.sendall(raw)
    data = b''
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    return data


def recording(work, env):
    """anvil records requests: the capsules of the ones that fail, panic or are sampled are kept,
    with the request as received (secret headers as handles) and its effects in order."""
    lib = work / 'lib/replayrecord'
    lib.mkdir()
    shutil.copy(ROOT / 'tools/ci/fixtures/replay_record_probe.tin', lib / 'probe.tin')
    exe = work / 'replay_record'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay_record.tin'],
                   check=True, env=env, cwd=ROOT, timeout=60)
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f'{name}: got {got!r}, want {want!r}')

    def serve(spool, requests, **extra):
        port = free_port()
        run_env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_')}
        run_env.update(PORT=str(port), TIN_CORES='2', TIN_REPLAY_KEY=CAPSULE_KEY.hex())
        if spool is not None:
            run_env['TIN_REPLAY_DIR'] = str(spool)
        run_env.update(extra)
        server = subprocess.Popen([str(exe)], env=run_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        answers = []
        try:
            for _ in range(200):
                try:
                    socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
                    break
                except OSError:
                    time.sleep(0.05)
            for raw in requests:
                answers.append(http(port, raw))
        finally:
            server.send_signal(signal.SIGTERM)
            out, err = server.communicate(timeout=30)
        return answers, err.decode()

    def request(path, extra=''):
        return (f'GET {path} HTTP/1.1\r\nHost: shop\r\nAuthorization: Bearer s3cr3t-token\r\n{extra}'
                'Connection: close\r\n\r\n').encode()

    def kept(spool):
        out = {}
        for p in sorted(spool.iterdir()):
            body = open_capsule(p.read_bytes())
            if body is None:
                failures.append(f'{p.name}: does not open with the key')
                continue
            c = decode_body(body)
            out[c['request'].split(b' ')[1].decode()] = c
            for secret in SECRETS:
                if secret in p.read_bytes() or secret in body:
                    failures.append(f'secret text {secret!r} in capsule {p.name}')
        return out

    spool = work / 'spool-anvil'
    paths = ['/cart/7', '/cart/7?fail=1', '/cart/8?panic=1', '/cart/9?wait=1&fail=1']
    answers, err = serve(spool, [request(p, 'Cookie: sid=c00k1e\r\n') for p in paths])
    check('statuses', [a.split(b' ')[1] for a in answers], [b'200', b'504', b'500', b'504'])
    caps = kept(spool)
    check('kept', sorted(caps), ['/cart/7?fail=1', '/cart/8?panic=1', '/cart/9?wait=1&fail=1'])
    handle = secret_handle(b'Bearer s3cr3t-token')
    charge = 'POST http://payments/charge\n\ncart=2 books'
    c = caps.get('/cart/7?fail=1')
    if c:
        check('request as received', c['request'],
              ('GET /cart/7?fail=1 HTTP/1.1\r\nHost: shop\r\nAuthorization: ' + handle + '\r\nCookie: ' +
               secret_handle(b'sid=c00k1e') + '\r\nConnection: close\r\n\r\n').encode())
        check('status and flags', (c['status'], c['flags'], c['panic']), (504, 0, b''))
        check('effects in order', [e[1:] for e in c['effects']], [
            ('redis@1', 'GET cart:7', 0, 0, b'2 books'),
            ('wire.http@1', charge, 1, 2, b'payments: deadline exceeded')])
        if abs(c['wall'] - time.time_ns()) > 600 * 10**9:
            failures.append(f'wall clock {c["wall"]} is not now')
        check('program', c['program'], str(exe).encode())
    c = caps.get('/cart/8?panic=1')
    if c:
        check('panicked', (c['status'], c['flags'], c['panic'], len(c['effects'])),
              (500, 1, b'checkout: cart 2 books', 1))
    c = caps.get('/cart/9?wait=1&fail=1')
    if c:
        check('a request that waited', (c['status'], [e[1] for e in c['effects']]), (504, ['redis@1', 'wire.http@1']))
    # TIN_REPLAY_SAMPLE=1 keeps a 200 too.
    spool = work / 'spool-anvil-sample'
    serve(spool, [request('/cart/3')], TIN_REPLAY_SAMPLE='1')
    caps = kept(spool)
    check('sampled', [(k, c['status'], c['flags']) for k, c in caps.items()], [('/cart/3', 200, 2)])
    # Recording off: no spool, and the server answers the same.
    answers, err = serve(None, [request('/cart/7?fail=1')])
    check('off', answers[0].split(b' ')[1], b'504')
    # A malformed key: the server serves, says once that recording is off, and writes nothing.
    spool = work / 'spool-anvil-badkey'
    answers, err = serve(spool, [request('/cart/7?fail=1')], TIN_REPLAY_KEY='zz')
    check('bad key', (answers[0].split(b' ')[1], err.count('recording is off'), spool.exists()), (b'504', 1, False))
    # A process that replays a capsule (TIN_REPLAY_CAPSULE, #242) records nothing.
    spool = work / 'spool-anvil-replaying'
    serve(spool, [], TIN_REPLAY_CAPSULE=str(work / 'none.tcap'))
    check('replaying records nothing', spool.exists(), False)
    (ROOT / 'bin/ci/replay/recording.log').write_text('\n'.join(failures))
    if failures:
        raise SystemExit('FAIL replay recording:\n' + '\n'.join(failures))
    print('PASS replay recording: anvil keeps the capsules of failed, panicked and sampled requests, '
          'with the request (secrets as handles) and its effects in order')


def serve_thread(handler):
    """A local TCP server on a thread: handler(conn, counts) per connection; returns its port and
    a dict counting connections."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen(16)
    counts = {'conns': 0}

    def loop():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            counts['conns'] += 1
            try:
                handler(conn)
            except OSError:
                pass
            conn.close()

    threading.Thread(target=loop, daemon=True).start()
    return sock, counts


def fake_redis(conn):
    data = b''
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            return
        data += chunk
        while b'\r\n' in data:
            parts, rest = parse_resp_command(data)
            if parts is None:
                break
            data = rest
            cmd = parts[0].upper()
            if cmd == b'AUTH':
                conn.sendall(b'+OK\r\n')
            elif cmd == b'GET' and parts[1] == b'cart:7':
                conn.sendall(b'$7\r\n2 books\r\n')
            elif cmd == b'GET':
                conn.sendall(b'$-1\r\n')
            else:
                conn.sendall(b'-ERR unknown\r\n')


def parse_resp_command(data):
    if not data.startswith(b'*'):
        return None, data
    head, _, rest = data.partition(b'\r\n')
    if not _:
        return None, data
    n = int(head[1:])
    parts = []
    for _ in range(n):
        line, sep, rest = rest.partition(b'\r\n')
        if not sep:
            return None, data
        size = int(line[1:])
        if len(rest) < size + 2:
            return None, data
        parts.append(rest[:size])
        rest = rest[size + 2:]
    return parts, rest


def fake_http(conn):
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return
        data += chunk
    head, _, body = data.partition(b'\r\n\r\n')
    length = 0
    for line in head.split(b'\r\n')[1:]:
        name, _, value = line.partition(b':')
        if name.strip().lower() == b'content-length':
            length = int(value)
    while len(body) < length:
        body += conn.recv(4096)
    reply = b'12.50 for ' + body
    conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: ' + str(len(reply)).encode() +
                 b'\r\nConnection: close\r\n\r\n' + reply)


def fake_echo(conn):
    data = conn.recv(4096)
    conn.sendall(b'echo ' + data)


def clients(work, env):
    """Recording in tide, dice, seal, wire and redis: a task's effects against live servers go on
    its tape; the same code replayed from the tape gets the same values with no live call, and a
    changed redis key is a divergence."""
    lib = work / 'lib/replayclients'
    lib.mkdir()
    shutil.copy(ROOT / 'tools/ci/fixtures/replay_clients_probe.tin', lib / 'probe.tin')
    exe = work / 'replay_clients'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay_clients.tin'],
                   check=True, env=env, cwd=ROOT, timeout=60)
    servers = [serve_thread(h) for h in (fake_redis, fake_http, fake_echo)]
    (rsock, rcount), (hsock, hcount), (esock, ecount) = servers
    tape = work / 'clients.tape'
    run_env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_')}
    run_env.update(REDIS_ADDR='127.0.0.1:%d' % rsock.getsockname()[1], HTTP_ADDR='127.0.0.1:%d' % hsock.getsockname()[1],
                   ECHO_ADDR='127.0.0.1:%d' % esock.getsockname()[1], TAPE_OUT=str(tape),
                   TIN_REPLAY_DIR=str(work / 'spool-clients'), TIN_REPLAY_KEY=CAPSULE_KEY.hex())
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, env=run_env)
    for s, _ in servers:
        s.close()
    (ROOT / 'bin/ci/replay/clients.log').write_text(r.stdout + r.stderr)
    failures = []
    lines = r.stdout.splitlines()
    want_effects = ['tide.now@1', 'tide.wall@1', 'dice.seed@1', 'seal.random@1', 'redis@1', 'wire.http@1',
                    'wire.dial@1', 'wire.write@1', 'wire.read@1', 'wire.http@1', 'tide.now@1']
    if r.returncode != 0 or len(lines) < 7:
        failures.append(f'exit {r.returncode}\n{r.stdout}{r.stderr}')
    else:
        recorded = lines[1]
        for part in ['cart 2 books true <nil>', 'price 200 "12.50 for cart=2 books" <nil>',
                     'raw <nil> 12 "echo PING 1\\n" <nil>', 'down wire: connect 127.0.0.1:1: Connection refused']:
            if part not in recorded:
                failures.append(f'recorded summary lacks {part!r}: {recorded}')
        check = lambda name, got, want: got == want or failures.append(f'{name}: got {got!r}, want {want!r}')
        check('setup', lines[0], 'recording on: true')
        check('effects', lines[2], f'effects: {len(want_effects)}')
        check('replay', lines[3], 'replayed same: true left: 0 diverged: ')
        divergence = 'replay: divergence at effect 4: got redis@1 "3:GET 6:cart:8\\n", recorded redis@1 "3:GET 6:cart:7\\n"'
        # Every later effect fails with the divergence; a clock read cannot fail, so it panics (section 3.2).
        check('other key panics at the clock', lines[4], 'task: panic: ' + divergence)
        check('other key', lines[5], 'other key: ' + divergence)
        check('live calls (record only)', (rcount['conns'], hcount['conns'], ecount['conns']), (1, 1, 1))
        data = tape.read_bytes()
        kinds, pos = [], 0
        while pos < len(data):
            pos += 8
            n = struct.unpack_from('<q', data, pos)[0]
            kinds.append(data[pos + 8:pos + 8 + n].decode())
            pos += 8 + n
            n = struct.unpack_from('<q', data, pos)[0]
            key = data[pos + 8:pos + 8 + n]
            pos += 8 + n + 16
            n = struct.unpack_from('<q', data, pos)[0]
            pos += 8 + n
            if kinds[-1] == 'wire.http@1' and b'/price' in key:
                check('wire.http key', key.decode(), 'POST http://%s/price\nAuthorization: %s\nX-Trace: t1\n\ncart=2 books'
                      % (run_env['HTTP_ADDR'], secret_handle(b'Bearer s3cr3t-token')))
        check('kinds in order', kinds, want_effects)
        for secret in (b's3cr3t-token', b'r3d1s-pass'):
            if secret in data:
                failures.append(f'secret text {secret!r} on the tape')
    if failures:
        raise SystemExit('FAIL replay clients:\n' + '\n'.join(failures))
    print('PASS replay clients: tide, dice, seal, wire (http, dial, read, write) and redis record in order, '
          'replay with no live call, and a changed key diverges')


def ws_echo(conn):
    """A WebSocket server for one connection: the handshake, then each text frame echoed, until a close."""
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            return
        buf += chunk
    head, buf = buf.split(b'\r\n\r\n', 1)
    key = [l.split(b':', 1)[1].strip() for l in head.split(b'\r\n') if l.lower().startswith(b'sec-websocket-key:')][0]
    accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
    conn.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                 b'Sec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
    while True:
        while len(buf) < 2:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
        op, n = buf[0] & 15, buf[1] & 127
        at = 2
        if n == 126:
            n, at = struct.unpack('>H', buf[2:4])[0], 4
        while len(buf) < at + 4 + n:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
        mask, data = buf[at:at + 4], buf[at + 4:at + 4 + n]
        buf = buf[at + 4 + n:]
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if op == 8:
            conn.sendall(b'\x88\x02\x03\xe8')
            return
        reply = b'echo: ' + data
        conn.sendall(bytes([0x81, len(reply)]) + reply)


def more_clients(work, env):
    """Recording in mysql, postgres, websocket and quarry: the effects of one task against fake
    servers and real files go on its tape in order; replayed, the same code gets the same values
    with no connection made and no file touched."""
    sys.path.insert(0, str(ROOT / 'tools/ci'))
    import mysql_check
    import postgres_check
    lib = work / 'lib/replaymore'
    lib.mkdir()
    shutil.copy(ROOT / 'tools/ci/fixtures/replay_more_probe.tin', lib / 'probe.tin')
    exe = work / 'replay_more'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay_more.tin'],
                   check=True, env=env, cwd=ROOT, timeout=120)
    my, pg = mysql_check.Fake(), postgres_check.Fake()
    wsock, wcount = serve_thread(ws_echo)
    tape = work / 'more.tape'
    files = work / 'files'
    run_env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_')}
    run_env.update(MYSQL_ADDR='127.0.0.1:%d' % my.port, POSTGRES_ADDR='127.0.0.1:%d' % pg.port,
                   WS_ADDR='127.0.0.1:%d' % wsock.getsockname()[1], FILES_DIR=str(files), TAPE_OUT=str(tape),
                   TIN_REPLAY_DIR=str(work / 'spool-more'), TIN_REPLAY_KEY=CAPSULE_KEY.hex())
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120, env=run_env)
    wsock.close()
    (ROOT / 'bin/ci/replay/more.log').write_text(r.stdout + r.stderr)
    failures = []
    check = lambda name, got, want: got == want or failures.append(f'{name}: got {got!r}, want {want!r}')
    lines = r.stdout.splitlines()
    if r.returncode != 0 or len(lines) < 5:
        failures.append(f'exit {r.returncode}\n{r.stdout}{r.stderr}')
    else:
        recorded = lines[1]
        for part in ['mysql 1 <nil> [1 ada] <nil> | mysql: Error 1146', '<nil> 2 <nil> <nil>',
                     '| postgres 1 <nil> [1 ada] <nil> | <nil> 1 <nil> <nil>',
                     'ws <nil> true "echo: hello ws" <nil>',
                     'files <nil> <nil> <nil> <nil> "alpha+beta" <nil> 10 <nil> <nil> [b.txt sub] <nil> true true <nil> true']:
            if part not in recorded:
                failures.append(f'recorded summary lacks {part!r}: {recorded}')
        check('replay', lines[3], 'replayed same: true left: 0 diverged: ')
        check('no file touched', lines[4], 'replay touched no file: true')
        data = tape.read_bytes()
        kinds, keys, pos = [], [], 0
        while pos < len(data):
            pos += 8
            n = struct.unpack_from('<q', data, pos)[0]
            kinds.append(data[pos + 8:pos + 8 + n].decode())
            pos += 8 + n
            n = struct.unpack_from('<q', data, pos)[0]
            keys.append(data[pos + 8:pos + 8 + n])
            pos += 8 + n + 16
            n = struct.unpack_from('<q', data, pos)[0]
            pos += 8 + n
        check('kinds in order', kinds, ['mysql@1', 'mysql@1', 'mysql@1', 'mysql.tx@1', 'mysql@1', 'mysql.tx@1',
                                        'postgres@1', 'postgres@1', 'postgres.tx@1', 'postgres@1', 'postgres.tx@1',
                                        'websocket.dial@1', 'websocket.write@1', 'websocket.read@1',
                                        'quarry.fs@1', 'quarry.write@1', 'quarry.write@1', 'quarry.fs@1', 'quarry.read@1',
                                        'quarry.stat@1', 'quarry.stat@1', 'quarry.dir@1', 'quarry.stat@1', 'quarry.stat@1',
                                        'quarry.fs@1', 'quarry.read@1'])
        if keys:
            check('mysql key', keys[0], b'E INSERT INTO users (name) VALUES (\nSada\n)\n')
            check('mysql query key', keys[1], b'Q SELECT id, name FROM users WHERE id = \nI1\n\n')
            check('rename key', keys[17], ('mv %s/a.txt\n%s/b.txt' % (files, files)).encode())
        if b'tinpass' in data:
            failures.append('a database password is on the tape')
    if failures:
        raise SystemExit('FAIL replay mysql, postgres, websocket, quarry:\n' + '\n'.join(failures))
    print('PASS replay mysql, postgres, websocket, quarry: recorded in order (transactions too), replayed with no '
          'connection and no file touched')


def main():
    out = ROOT / 'bin/ci/replay'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='replay-', dir=out) as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / 'lib', work / 'lib')
        probe = work / 'lib/replayprobe'
        probe.mkdir()
        shutil.copy(ROOT / 'tools/ci/fixtures/replay_probe.tin', probe / 'probe.tin')
        exe = work / 'replay'
        env = dict(os.environ, TIN_ROOT=str(work))
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay.tin'],
                       check=True, env=env, cwd=ROOT, timeout=60)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30, cwd=ROOT)
        (out / 'replay.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result
        if result.stdout != EXPECTED:
            raise SystemExit('FAIL replay tapes: output differs\n--- want\n' + EXPECTED +
                             '--- got\n' + result.stdout)
        capsules(work, env)
        recording(work, env)
        clients(work, env)
        more_clients(work, env)
    print('PASS replay tapes: record, replay without live calls, fault identity, divergence, live kinds, children share the tape, panics on it')


if __name__ == '__main__':
    main()
