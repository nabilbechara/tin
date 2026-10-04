#!/usr/bin/env python3
"""Replay tapes (#241): rt_effect records results and faults, and a replay serves them without
running the live call, keeps fault identity, and stops at the first divergence. Replay mode
(#242): a server given TIN_REPLAY_CAPSULE runs the capsule's request with its effects served from
the capsule, reports, and exits 0, 3 (diverged) or 4 (unreadable capsule)."""
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

KEY = bytes(range(32))
REQUEST = b'POST /checkout/7 HTTP/1.1\r\nHost: shop\r\nContent-Length: 0\r\n\r\n'
CART = ('redis@1', 'GET cart:7', 0, 0, '2 books')
CHARGE = 'POST http://payments/charge\n\ncart=2 books'


def word(v):
    return struct.pack('<q', v)


def string(b):
    b = b.encode() if isinstance(b, str) else b
    return word(len(b)) + b


def capsule_body(effects, status=500, request=REQUEST, schema=1):
    """A capsule body (notes/interface_replay.md, section 6) with these (kind, key, outcome,
    ident, data) effect records (section 3.3)."""
    out = word(schema) + string('dev') + string('replay_serve') + word(1700000000000000000) + word(0)
    out += word(status) + word(0) + string(request) + string('') + word(len(effects))
    for seq, (kind, key, outcome, ident, data) in enumerate(effects):
        out += word(seq) + string(kind) + string(key) + word(outcome) + word(ident) + string(data)
    return out


def seal(body, key=KEY):
    """The capsule envelope: HMAC-SHA256 keystream, encrypt-then-MAC (section 6)."""
    ke = hmac.new(key, b'tin replay enc', hashlib.sha256).digest()
    km = hmac.new(key, b'tin replay mac', hashlib.sha256).digest()
    nonce = os.urandom(16)
    stream = b''.join(hmac.new(ke, nonce + word(i), hashlib.sha256).digest() for i in range((len(body) + 31) // 32))
    head = b'TINCAP\x01\x00' + nonce + bytes(a ^ b for a, b in zip(body, stream))
    return head + hmac.new(km, head, hashlib.sha256).digest()


def replay_mode(work, env):
    """Replay mode end to end: the fixture checkout service replays capsules built here."""
    fixture = work / 'lib/replayserve'
    fixture.mkdir()
    shutil.copy(ROOT / 'tools/ci/fixtures/replay_serve_probe.tin', fixture / 'probe.tin')
    exe = work / 'replay_serve'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay_serve.tin'],
                   check=True, env=env, cwd=ROOT, timeout=60)
    failed = 0
    log = []

    def case(name, data, want_code, want_out, want_err='', extra=None, key=KEY.hex()):
        nonlocal failed
        path = work / (name.replace(' ', '_') + '.tcap')
        path.write_bytes(data)
        run_env = dict(os.environ, TIN_REPLAY_CAPSULE=str(path), TIN_CORES='4', PORT='1')
        run_env.pop('TIN_REPLAY_LIVE', None)
        run_env.pop('CHECKOUT_SWAP', None)
        if key is None:
            run_env.pop('TIN_REPLAY_KEY', None)
        else:
            run_env['TIN_REPLAY_KEY'] = key
        run_env.update(extra or {})
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30, env=run_env)
        log.append(f'== {name}: exit {r.returncode}\n{r.stdout}{r.stderr}')
        if r.returncode != want_code or r.stdout != want_out or want_err not in r.stderr:
            failed += 1
            print(f'FAIL replay mode: {name}\n--- want exit {want_code}\n{want_out}{want_err}\n'
                  f'--- got exit {r.returncode}\n{r.stdout}{r.stderr}')

    refused = (CHARGE, 1, 0, 'payments: connection refused')
    recorded = [CART, ('wire.http@1',) + refused]
    case('recorded 500', seal(capsule_body(recorded)), 0,
         'replay: status 500 (recorded 500)\ncharge failed: payments: connection refused (live calls 0)\n')
    case('recorded deadline', seal(capsule_body([CART, ('wire.http@1', CHARGE, 1, 2, 'payments: deadline exceeded')], 504)), 0,
         'replay: status 504 (recorded 504)\ncharge failed: payments: deadline exceeded (live calls 0)\n')
    divergence = ('replay: divergence at effect 0: got wire.http@1 "POST http://payments/charge\\n\\ncart=", '
                  'recorded redis@1 "GET cart:7"')
    case('changed call order', seal(capsule_body(recorded)), 3,
         'replay: status 500 (recorded 500)\n' + divergence + '\nreplay: 2 recorded effects not served\n'
         'charge failed: ' + divergence + ' (live calls 0)\n', extra={'CHECKOUT_SWAP': '1'})
    case('effects left', seal(capsule_body(recorded + [CART])), 3,
         'replay: status 500 (recorded 500)\nreplay: 1 recorded effects not served\n'
         'charge failed: payments: connection refused (live calls 0)\n')
    case('live kind', seal(capsule_body(recorded)), 0,
         'replay: status 200 (recorded 500)\npaid: live for 2 books (live calls 1)\n',
         extra={'TIN_REPLAY_LIVE': 'Wire.HTTP'})
    waited = REQUEST.replace(b'/checkout/7 ', b'/checkout/7?wait=1 ')
    case('handler waits', seal(capsule_body(recorded, request=waited)), 0,
         'replay: status 500 (recorded 500)\ncharge failed: payments: connection refused (live calls 0)\n')
    panicked = REQUEST.replace(b'/checkout/7 ', b'/checkout/7?panic=1 ')
    case('handler panics', seal(capsule_body([CART, ('wire.http@1', CHARGE, 0, 0, 'ok')], request=panicked)), 0,
         'replay: status 500 (recorded 500)\nInternal Server Error', 'checkout: paid ok')
    case('wrong key', seal(capsule_body(recorded), bytes(32)), 4, '', 'replay: capsule: wrong key or damaged\n')
    damaged = bytearray(seal(capsule_body(recorded)))
    damaged[40] ^= 1
    case('damaged', bytes(damaged), 4, '', 'replay: capsule: wrong key or damaged\n')
    case('no key', seal(capsule_body(recorded)), 4, '', 'replay: capsule: TIN_REPLAY_KEY must be 64 hex digits\n', key=None)
    case('not a capsule', b'GET / HTTP/1.1\r\n\r\n', 4, '', 'replay: capsule: not a capsule (no TINCAP header)\n')
    case('unsupported kind', seal(capsule_body([('redis@9', 'GET cart:7', 0, 0, '2 books')])), 4, '',
         'replay: capsule: effect 0 has kind redis@9, which this build cannot replay\n')
    case('unsupported schema', seal(capsule_body(recorded, schema=2)), 4, '',
         'replay: capsule: unsupported schema 2 (this build reads schema 1)\n')
    case('truncated body', seal(capsule_body(recorded)[:-3]), 4, '', 'replay: capsule: damaged (truncated)\n')
    (ROOT / 'bin/ci/replay/replay_mode.log').write_text('\n'.join(log))
    if failed:
        raise SystemExit(f'FAIL replay mode: {failed} case(s)')
    print('PASS replay mode: recorded 500 and fault identity without live calls, call order divergence, '
          'effects left, --live, unreadable capsules')


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
        replay_mode(work, env)
    print('PASS replay tapes: record, replay without live calls, fault identity, divergence, live kinds, children share the tape, panics on it')


if __name__ == '__main__':
    main()
