#!/usr/bin/env python3
"""Convert Wycheproof signature vectors to the compact files under tests/data/wycheproof/.

Usage: tools/gen_wycheproof.py PATH/TO/wycheproof   (a checkout of github.com/C2SP/wycheproof)

Each output file starts with a comment naming its source, then one line per key group and one
per test:
    group rsa-pkcs1 SHA-256 - KEYHEX          (KEYHEX: DER PKCS #1 RSAPublicKey)
    group rsa-pss SHA-256 32 KEYHEX           (salt length; MGF1 uses the same hash)
    TCID valid|invalid|acceptable MSGHEX SIGHEX   ("-" for an empty field)
Only groups whose hashes seal implements are kept (HASHES below). Standard library only;
the output is deterministic. The vectors are Apache-2.0 (notes/licenses/wycheproof.txt).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests/data/wycheproof'
HASHES = {'SHA-256'}
FILES = [
    'rsa_signature_2048_sha256_test.json',
    'rsa_signature_3072_sha256_test.json',
    'rsa_signature_4096_sha256_test.json',
    'rsa_pss_2048_sha256_mgf1_0_test.json',
    'rsa_pss_2048_sha256_mgf1_32_test.json',
    'rsa_pss_3072_sha256_mgf1_32_test.json',
    'rsa_pss_4096_sha256_mgf1_32_test.json',
    'rsa_pss_misc_test.json',
]


def convert(src, name):
    data = json.loads((src / name).read_text())
    lines = [f'# {name} from github.com/C2SP/wycheproof testvectors_v1 (Apache-2.0)']
    kept = 0
    for group in data['testGroups']:
        kind = group['type']
        if group.get('sha') not in HASHES:
            continue
        if kind == 'RsassaPkcs1Verify':
            lines.append(f"group rsa-pkcs1 {group['sha']} - {group['publicKeyAsn']}")
        elif kind == 'RsassaPssVerify':
            if group.get('mgf') != 'MGF1' or group.get('mgfSha') != group['sha']:
                continue
            lines.append(f"group rsa-pss {group['sha']} {group['sLen']} {group['publicKeyAsn']}")
        else:
            continue
        for test in group['tests']:
            lines.append(f"{test['tcId']} {test['result']} {test['msg'] or '-'} {test['sig'] or '-'}")
            kept += 1
    if kept == 0:
        raise SystemExit(f'{name}: no usable groups')
    out = OUT / name.replace('_test.json', '.txt')
    out.write_text('\n'.join(lines) + '\n')
    print(f'{out.relative_to(ROOT)}: {kept} tests')


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]) / 'testvectors_v1'
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        convert(src, name)


if __name__ == '__main__':
    main()
