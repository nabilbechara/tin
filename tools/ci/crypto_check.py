#!/usr/bin/env python3
"""seal primitives against Wycheproof vectors and Python's hashlib/hmac on random inputs."""
import argparse
import hashlib
import hmac
import json
import os
import random
import subprocess
import tempfile
from pathlib import Path
from suite import ROOT

VECTORS = ROOT / 'tests/wycheproof'


def hx(b):
    return b.hex() if b else '-'


def hkdf(name, ikm, salt, info, size):
    n = hashlib.new(name).digest_size
    prk = hmac.new(salt or bytes(n), ikm, name).digest()
    out, t, i = b'', b'', 1
    while len(out) < size:
        t = hmac.new(prk, t + info + bytes([i]), name).digest()
        out += t
        i += 1
    return out[:size]


def wycheproof(cases):
    """Appends (input line, check) pairs for each Wycheproof file; check(output) is True when right."""
    for name in ('sha256', 'sha384', 'sha512'):
        data = json.loads((VECTORS / f'hmac_{name}_test.json').read_text())
        for group in data['testGroups']:
            bits = group['tagSize']
            for t in group['tests']:
                tag = t['tag']
                valid = t['result'] == 'valid'
                line = f"hmac {name} {hx(bytes.fromhex(t['key']))} {hx(bytes.fromhex(t['msg']))}"
                cases.append((line, lambda out, tag=tag, valid=valid, bits=bits:
                              (out[:bits // 4] == tag) == valid, f"hmac_{name} {t['tcId']}"))
        data = json.loads((VECTORS / f'hkdf_{name}_test.json').read_text())
        for group in data['testGroups']:
            for t in group['tests']:
                line = f"hkdf {name} {hx(bytes.fromhex(t['ikm']))} {hx(bytes.fromhex(t['salt']))} {hx(bytes.fromhex(t['info']))} {t['size']}"
                want = t['okm'] if t['result'] == 'valid' else 'fault'
                cases.append((line, lambda out, want=want: out == want,
                              f"hkdf_{name} {t['tcId']}"))


def ecdh(cases, file, op, size):
    """Wycheproof ECDH vectors: valid ones give the shared secret, invalid ones a fault, and
    acceptable ones (such as compressed points) either."""
    data = json.loads((VECTORS / file).read_text())
    for group in data['testGroups']:
        for t in group['tests']:
            priv = int(t['private'], 16).to_bytes(size, 'big') if t['private'] else b''
            line = f"{op} {hx(priv)} {hx(bytes.fromhex(t['public']))}"
            want, result = t['shared'], t['result']
            cases.append((line, lambda out, want=want, result=result:
                          out == want if result == 'valid' else out == 'fault' if result == 'invalid' else out in (want, 'fault'),
                          f"{file} {t['tcId']}"))


def random_cases(cases):
    rng = random.Random(124)
    for name in ('sha256', 'sha384', 'sha512'):
        # Every length across the padding boundaries of one and two blocks, then longer inputs.
        for n in list(range(0, 300)) + [rng.randrange(300, 5000) for _ in range(20)]:
            msg = rng.randbytes(n)
            want = hashlib.new(name, msg).hexdigest()
            cases.append((f'sha {name} {hx(msg)}', lambda out, want=want: out == want, f'sha_{name} len {n}'))
        for _ in range(100):
            key = rng.randbytes(rng.randrange(0, 300))
            msg = rng.randbytes(rng.randrange(0, 600))
            want = hmac.new(key, msg, name).hexdigest()
            cases.append((f'hmac {name} {hx(key)} {hx(msg)}', lambda out, want=want: out == want, f'hmac_{name} random'))
        for _ in range(50):
            ikm, salt, info = rng.randbytes(rng.randrange(0, 100)), rng.randbytes(rng.randrange(0, 100)), rng.randbytes(rng.randrange(0, 100))
            size = rng.randrange(0, 255 * hashlib.new(name).digest_size + 1)
            want = hkdf(name, ikm, salt, info, size).hex()
            cases.append((f'hkdf {name} {hx(ikm)} {hx(salt)} {hx(info)} {size}', lambda out, want=want: out == want, f'hkdf_{name} random'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='bin/tinc')
    args = parser.parse_args()
    compiler = (ROOT / args.compiler).resolve()
    out = ROOT / 'bin/ci/crypto'
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    wycheproof(cases)
    ecdh(cases, 'ecdh_secp256r1_ecpoint_test.json', 'p256ecdh', 32)
    random_cases(cases)
    with tempfile.TemporaryDirectory(prefix='crypto-', dir=out) as tmp:
        exe = Path(tmp) / 'crypto_vectors'
        subprocess.run([str(compiler), '-o', str(exe), 'tools/ci/fixtures/crypto_vectors.tin'], check=True, cwd=ROOT,
                       env=dict(os.environ, TIN_ROOT=str(ROOT)), timeout=120)
        data = ''.join(line + '\n' for line, _, _ in cases).encode()
        got = subprocess.run([str(exe)], input=data, capture_output=True, timeout=600)
        assert got.returncode == 0, got.stderr.decode(errors='replace')[:4000]
        lines = got.stdout.decode().split('\n')[:-1]
        assert len(lines) == len(cases), (len(lines), len(cases), got.stderr[:2000])
        failed = [(name, line, o) for (line, check, name), o in zip(cases, lines) if not check(o if o != '-' else '')]
        for name, line, o in failed[:20]:
            print('FAIL', name, line[:200], '->', o[:200])
        if failed:
            raise SystemExit(f'crypto: {len(failed)} of {len(cases)} vectors failed')
    print(f'crypto: {len(cases)} vectors passed')


if __name__ == '__main__':
    main()
