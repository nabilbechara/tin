#!/usr/bin/env python3
"""tin replay --save-test (#242): turn a capsule into a regression case.

Usage: replay_save.py ROOT NAME ISSUE CAPSULE BUILD.tin STDOUT_FILE

Writes toolchain/tests/regressions/NAME.tin (a copy of BUILD.tin), toolchain/tests/regressions/NAME.tcap (the capsule,
opened with TIN_REPLAY_KEY and sealed again under a public test key kept in the case) and the
case in cases.json: the program run with the replay switches must exit 0 and print STDOUT_FILE.
The saved capsule is readable by anyone: review its request and results before committing it.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import struct
import sys

MAGIC = b'TINCAP\x01\x00'
# Saved tests are public: their capsules are sealed under this key, written in the case itself.
TEST_KEY = hashlib.sha256(b'tin replay saved tests: not a secret').hexdigest()


def keys(key):
    return (hmac.new(key, b'tin replay enc', hashlib.sha256).digest(),
            hmac.new(key, b'tin replay mac', hashlib.sha256).digest())


def stream(ke, nonce, n):
    return b''.join(hmac.new(ke, nonce + struct.pack('<q', i), hashlib.sha256).digest() for i in range((n + 31) // 32))


def unseal(data, key):
    """The body of a capsule envelope (design/interface_replay.md, section 6)."""
    if data[:8] != MAGIC:
        raise ValueError('not a capsule (no TINCAP header)')
    ke, km = keys(key)
    if len(data) < 56 or not hmac.compare_digest(hmac.new(km, data[:-32], hashlib.sha256).digest(), data[-32:]):
        raise ValueError('wrong key or damaged')
    nonce, ct = data[8:24], data[24:-32]
    return bytes(a ^ b for a, b in zip(ct, stream(ke, nonce, len(ct))))


def seal(body, key):
    ke, km = keys(key)
    nonce = os.urandom(16)
    head = MAGIC + nonce + bytes(a ^ b for a, b in zip(body, stream(ke, nonce, len(body))))
    return head + hmac.new(km, head, hashlib.sha256).digest()


def main(argv):
    if len(argv) != 7:
        raise SystemExit(__doc__)
    root, name, issue, capsule, build, out = Path(argv[1]), argv[2], argv[3], Path(argv[4]), Path(argv[5]), Path(argv[6])
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        raise SystemExit('tin replay: --save-test NAME must be lower-case letters, digits and dashes')
    if not issue.isdigit():
        raise SystemExit('tin replay: --issue N must be an issue number')
    key = bytes.fromhex(os.environ.get('TIN_REPLAY_KEY', ''))
    dest = root / 'toolchain/tests/regressions'
    manifest = dest / 'cases.json'
    cases = json.loads(manifest.read_text())
    if (dest / (name + '.tin')).exists() or any(c['source'] == name + '.tin' for c in cases):
        raise SystemExit(f'tin replay: toolchain/tests/regressions/{name}.tin exists already')
    try:
        body = unseal(capsule.read_bytes(), key)
    except ValueError as exc:
        raise SystemExit(f'tin replay: capsule: {exc}')
    (dest / (name + '.tin')).write_text(build.read_text())
    (dest / (name + '.tcap')).write_bytes(seal(body, bytes.fromhex(TEST_KEY)))
    cases.append({'source': name + '.tin', 'issue': int(issue),
                  'replay': {'capsule': name + '.tcap', 'key': TEST_KEY},
                  'expected': {'phase': 'run', 'exit': 0, 'stdout': out.read_text()}})
    manifest.write_text(json.dumps(cases, indent=2) + '\n')
    print(f'tin replay: saved toolchain/tests/regressions/{name}.tin and {name}.tcap (#{issue}); '
          f'the capsule is public now: review its request and results before committing')


if __name__ == '__main__':
    main(sys.argv)
