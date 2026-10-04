#!/usr/bin/env python3
"""Replay tapes (#241): rt_effect records results and faults, and a replay serves them without
running the live call, keeps fault identity, and stops at the first divergence. Capsules (#241):
lib/replay writes a kept tape as an encrypted capsule into the bounded spool."""
import hashlib
import hmac
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
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
    print('PASS replay tapes: record, replay without live calls, fault identity, divergence, live kinds, children share the tape, panics on it')


if __name__ == '__main__':
    main()
