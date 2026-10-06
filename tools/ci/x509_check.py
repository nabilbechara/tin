#!/usr/bin/env python3
"""Certificates and signatures in seal (#124 phase 2), against Go's crypto/x509 and crypto/rsa.

1. A fresh test PKI (bench/ref/x509_pki: a root, intermediates, leaves and every bad case) is
   generated for this run; toolchain/tests/v2/seal_x509.tin and its Go twin bench/ref/seal_x509 verify every
   case, and both must give the outcome cases.txt expects.
2. The checked-in PKI (toolchain/tests/data/x509: chains and parsed fields) and the Wycheproof vectors
   (toolchain/tests/wycheproof/rsa, ecdsa and ed25519) give the same results in Go as the strict suite's expected Tin output.
3. Every byte of every certificate in the fresh PKI, in toolchain/tests/data/x509_real (public roots that
   found differences before) and in the system bundle is flipped three ways;
   Tin must reject every mutant Go rejects (Tin may reject more: Go ignores trailing bytes in a
   few places).
4. Private keys and signing (toolchain/tests/data/keys): signatures Tin makes for TLS (RSA-PSS with random
   salts, RFC 6979 ECDSA) verify in Go; deterministic ones equal Go's (toolchain/tests/v2/seal_sign.tin).
5. SystemRoots reads the operating system's bundle and parses the same certificates Go does.
Needs Go (as http_check.py does)."""
import os
from pathlib import Path
import subprocess
import tempfile

from suite import ROOT

LINUX_BUNDLES = [
    '/etc/ssl/certs/ca-certificates.crt',
    '/etc/pki/tls/certs/ca-bundle.crt',
    '/etc/ssl/ca-bundle.pem',
    '/etc/pki/tls/cacert.pem',
    '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
    '/etc/ssl/cert.pem',
]


def run(command, timeout=300):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=timeout,
                            env=dict(os.environ, TIN_ROOT=str(ROOT)))
    if result.returncode != 0:
        raise AssertionError(f'{" ".join(map(str, command))}: exit {result.returncode}\n'
                             f'{result.stdout.decode(errors="replace")[-4000:]}'
                             f'{result.stderr.decode(errors="replace")[-4000:]}')
    return result.stdout.decode()


def build(source, out):
    run(['bin/tinc', '-o', str(out), source])
    return out


def outcomes(text):
    """NAME -> "OK n" or the failure class, from "NAME OK n" / "NAME FAIL class[: fault]" lines."""
    got = {}
    for line in text.splitlines():
        name, rest = line.split(' ', 1)
        if rest.startswith('FAIL '):
            rest = rest[5:].split(':', 1)[0]
        got[name] = rest
    return got


def expected(cases):
    want = {}
    for line in Path(cases).read_text().splitlines():
        f = line.split()
        if f[0] != 'now':
            want[f[0]] = ' '.join(f[6:])
    return want


def check_pki(tin, pki):
    want = expected(pki / 'cases.txt')
    got_tin = outcomes(run([str(tin), str(pki)]))
    got_go = outcomes(run(['go', 'run', './bench/ref/seal_x509', str(pki)]))
    bad = []
    for name, outcome in want.items():
        if got_tin.get(name) != outcome or got_go.get(name) != outcome:
            bad.append(f'{name}: expected {outcome}, Tin {got_tin.get(name)}, Go {got_go.get(name)}')
    assert not bad, 'fresh PKI:\n' + '\n'.join(bad)
    print(f'PASS fresh test PKI: {len(want)} cases agree with Go and the expectations')


def check_checked_in():
    tin = outcomes((ROOT / 'toolchain/tests/v2/seal_x509.out').read_text())
    go = outcomes(run(['go', 'run', './bench/ref/seal_x509']))
    assert tin == go, f'checked-in PKI: Tin {tin} != Go {go}'
    want = sorted((ROOT / 'toolchain/tests/v2/seal_wycheproof.out').read_text().splitlines() +
                  (ROOT / 'toolchain/tests/v2/seal_wycheproof_ecdsa.out').read_text().splitlines() +
                  (ROOT / 'toolchain/tests/v2/seal_wycheproof_ed25519.out').read_text().splitlines())
    got = sorted(run(['go', 'run', './bench/ref/seal_wycheproof']).splitlines())
    assert got == want, 'Wycheproof: Go output differs from toolchain/tests/v2/seal_wycheproof*.out:\n' + \
        '\n'.join(set(got) ^ set(want))
    want_sign = (ROOT / 'toolchain/tests/v2/seal_sign.out').read_text().splitlines()
    got_sign = sorted(run(['go', 'run', './bench/ref/seal_sign']).splitlines())
    assert got_sign == want_sign, 'signing: Go output differs from toolchain/tests/v2/seal_sign.out:\n' + \
        '\n'.join(sorted(set(got_sign) ^ set(want_sign))[:40])
    want_info = (ROOT / 'toolchain/tests/v2/seal_certinfo.out').read_text().splitlines()
    got_info = sorted(run(['go', 'run', './bench/ref/seal_certinfo']).splitlines())
    assert got_info == want_info, 'certificate fields: Go output differs from toolchain/tests/v2/seal_certinfo.out:\n' + \
        '\n'.join(sorted(set(got_info) ^ set(want_info))[:40])
    print(f'PASS checked-in PKI ({len(tin)} cases), certificate fields ({len(want_info)} lines) and '
          f'Wycheproof ({len(want)} files) agree with Go')


def system_bundle():
    paths = [os.environ['SSL_CERT_FILE']] if os.environ.get('SSL_CERT_FILE') else \
        (['/etc/ssl/cert.pem'] if os.uname().sysname == 'Darwin' else LINUX_BUNDLES)
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def check_mutants(mutate, gomutate, files):
    """Tin runs once per certificate (a plain program frees memory only at exit); Go once."""
    tin, go = set(), set()
    for f in files:
        count = Path(f).read_text(errors='replace').count('-----BEGIN CERTIFICATE-----')
        for k in range(count):
            tin |= {(f,) + tuple(l.split()[:3]) for l in run([str(mutate), f, str(k)]).splitlines() if 'rejected' in l}
    lines = run([str(gomutate)] + files).splitlines()
    for l in lines:
        if 'rejected' in l:
            a, k, i, x = l.split()[:4]
            go.add((files[int(a) - 1], k, i, x))
    lax = sorted(go - tin)
    assert not lax, f'Tin accepts {len(lax)} mutants Go rejects (file, cert, byte, xor):\n' + \
        '\n'.join(' '.join(m) for m in lax[:50])
    print(f'PASS mutated certificates: {len(go)} Go rejections all rejected by Tin '
          f'({len(tin - go)} more rejected by Tin only), {len(files)} files')


def check_signatures(signer):
    """Signatures Tin makes with the test keys (random PSS salts included) verify in Go."""
    lines = run([str(signer)])
    assert 'error' not in lines, lines
    proc = subprocess.run(['go', 'run', './bench/ref/seal_sign', 'verify', 'toolchain/tests/data/keys'], cwd=ROOT,
                          input=lines.encode(), capture_output=True, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode(errors='replace')
    out = proc.stdout.decode().splitlines()
    bad = [l for l in out if not l.endswith(' ok')]
    want = len([l for l in lines.splitlines() if l.strip()])
    assert not bad and len(out) == want, f'Go rejected Tin signatures: {bad} ({len(out)} of {want} checked)'
    print(f'PASS signatures: Go verifies all {want} TLS signatures Tin made (RSA-PSS, ECDSA and Ed25519)')


def check_system_roots(roots):
    out = run([str(roots)]).strip()
    path = system_bundle()
    if path is None:
        print('SKIP SystemRoots: no system bundle on this machine')
        return
    want = run(['go', 'run', './bench/ref/x509_roots', path]).strip()
    blocks = Path(path).read_text(errors='replace').count('-----BEGIN CERTIFICATE-----')
    assert out == want, f'SystemRoots: Tin {out}, Go {want} of the {blocks} certificates in {path}'
    print(f'PASS SystemRoots: {out.split()[1]} of the {blocks} certificates in {path}, as Go')


def main():
    directory = ROOT / 'bin/ci/x509'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='x509-', dir=directory) as tmp:
        tmp = Path(tmp)
        tin = build('toolchain/tests/v2/seal_x509.tin', tmp / 'seal_x509')
        mutate = build('tools/ci/fixtures/x509_mutate.tin', tmp / 'x509_mutate')
        gomutate = tmp / 'x509_mutate_go'
        run(['go', 'build', '-o', str(gomutate), './bench/ref/x509_mutate'])
        roots = build('tools/ci/fixtures/x509_roots.tin', tmp / 'x509_roots')
        signer = build('tools/ci/fixtures/sign_tls.tin', tmp / 'sign_tls')
        pki = tmp / 'pki'
        run(['go', 'run', './bench/ref/x509_pki', str(pki)])
        check_pki(tin, pki)
        check_checked_in()
        files = sorted(str(p) for p in (pki / 'certs').glob('*.pem'))
        files += sorted(str(p) for p in (ROOT / 'toolchain/tests/data/x509_real').glob('*.pem'))
        if system_bundle():
            files.append(system_bundle())
        check_mutants(mutate, gomutate, files)
        check_signatures(signer)
        check_system_roots(roots)


if __name__ == '__main__':
    main()
