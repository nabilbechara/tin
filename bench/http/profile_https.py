#!/usr/bin/env python3
"""Where a full TLS handshake spends its time in anvil (#488): bin/https_bench on one core under
bin/tlsload (every connection a full handshake), sampled with perf's cpu-clock for SECONDS.
Prints the flat profile (top symbols, percent of the server's samples) for an ECDSA P-256 and an
RSA-2048 certificate. Linux only; needs perf, openssl, and bin/https_bench and bin/tlsload built
(the Profile workflow builds them).
Usage: profile_https.py SECONDS [ecdsa|rsa ...]"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_https as r  # noqa: E402

ROOT = r.ROOT


def profile(kind, cert, seconds, top):
    env = dict(os.environ, TIN_CORES='1', TIN_PIN='0', PORT='9190', TLS_CERT=str(cert[0]), TLS_KEY=str(cert[1]))
    proc = subprocess.Popen([str(ROOT / 'bin/https_bench')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        r.ready(9190)
        load = subprocess.Popen([str(ROOT / 'bin/tlsload'), '-addr', '127.0.0.1:9190', '-path', '/plaintext', '-c', '50',
                                 '-d', str(seconds + 4)], stdout=subprocess.PIPE, text=True)
        time.sleep(2)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'perf.data'
            subprocess.run(['sudo', 'perf', 'record', '-e', 'cpu-clock', '-F', '1999', '-p', str(proc.pid), '-o', str(data),
                            '--', 'sleep', str(seconds)], check=True, capture_output=True)
            rep = subprocess.run(['sudo', 'perf', 'report', '-i', str(data), '--no-children', '--sort', 'symbol', '--stdio',
                                  '--percent-limit', '0.3'], check=True, capture_output=True, text=True).stdout
        rate = load.communicate()[0].strip()
        lines = [l for l in rep.splitlines() if l.strip() and not l.startswith('#')]
        print(f'### {kind}: full handshakes (load generator) {rate}')
        print('```')
        print('\n'.join(lines[:top]))
        print('```')
        assert proc.poll() is None, 'the server died'
    finally:
        proc.terminate()
        proc.wait()


def main():
    seconds = int(sys.argv[1])
    kinds = sys.argv[2:] or ['ecdsa', 'rsa']
    with tempfile.TemporaryDirectory() as tmp:
        certs = r.make_certs(Path(tmp))
        for kind in kinds:
            profile(kind, certs[kind], seconds, 45)


if __name__ == '__main__':
    main()
