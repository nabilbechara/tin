#!/usr/bin/env python3
"""HTTPS: anvil.ServeTLS (bench/http/https.tin) against Go's crypto/tls (bench/http/gotls), one
server core each, interleaved rounds, medians with the Tin/Go ratio.

Scenarios (TLS 1.3, certificates generated per run with openssl):
  handshakes ECDSA P-256 / RSA-2048   bin/tlsload: every connection a full handshake (no session
                                      cache; wrk would resume sessions now that both servers issue
                                      tickets), one GET each
  resumed handshakes ECDSA P-256      bin/tlsload -resume: every connection resumes the session of
                                      the one before (a ticket, no certificate or signature, #472)
  keep-alive /plaintext               wrk: requests per second on established connections
  1 MiB bodies                        wrk: MiB per second on established connections

Usage: run_https.py SECONDS ROUNDS [--json PATH]   (needs bin/https_bench, bin/gotls, bin/tlsload,
wrk, openssl)"""
import argparse
import json
import os
import re
import socket
import ssl
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCENARIOS = [
    # name, certificate, path, connections, new connection per request
    ('handshakes ECDSA P-256', 'ecdsa', '/plaintext', 50, True),
    ('handshakes RSA-2048', 'rsa', '/plaintext', 50, True),
    ('resumed handshakes ECDSA P-256', 'ecdsa', '/plaintext', 32, True),
    ('keep-alive /plaintext', 'ecdsa', '/plaintext', 100, False),
    ('1 MiB bodies', 'ecdsa', '/big?n=1048576', 10, False),
]


def make_certs(work):
    certs = {}
    for kind, args in (('ecdsa', ['-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256']), ('rsa', ['-newkey', 'rsa:2048'])):
        cert, key = work / f'{kind}.pem', work / f'{kind}.key'
        subprocess.run(['openssl', 'req', '-x509', *args, '-keyout', str(key), '-out', str(cert), '-days', '30', '-nodes',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                       check=True, capture_output=True)
        certs[kind] = (cert, key)
    return certs


def parse_wrk(text, reference=False):
    rps = re.search(r'^Requests/sec:\s*([\d.]+)\s*$', text, re.M)
    xfer = re.search(r'^Transfer/sec:\s*([\d.]+)(B|KB|MB|GB)\s*$', text, re.M)
    if not rps or not xfer:
        raise ValueError('incomplete wrk output: ' + text)
    errors = re.search(r'Socket errors: connect (\d+), read (\d+), write (\d+), timeout (\d+)', text)
    # A request of the reference server (Go, GOMAXPROCS=1) now and then takes longer than wrk's 2 s
    # timeout with 1 MiB bodies: noted, since it is not what is measured. anvil's are errors.
    timeouts = int(errors[4]) if errors else 0
    if reference and timeouts:
        print(f'note: wrk timed out {timeouts} request(s) of the reference server')
        timeouts = 0
    if re.search(r'Non-2xx or 3xx responses:', text) or (errors and (int(errors[1]) or int(errors[3]) or timeouts)):
        raise ValueError('wrk reported request errors: ' + text)
    mib = float(xfer[1]) * {'B': 1 / 1048576, 'KB': 1 / 1024, 'MB': 1, 'GB': 1024}[xfer[2]]
    return float(rps[1]), mib


def ready(port):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    deadline = time.monotonic() + 10
    while True:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1) as raw:
                with ctx.wrap_socket(raw, server_hostname='localhost') as s:
                    s.sendall(b'GET /plaintext HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                    data = b''
                    while True:
                        chunk = s.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    if not data.endswith(b'Hello, World!') or s.version() != 'TLSv1.3':
                        raise ValueError(f'unexpected answer {s.version()}: {data!r}')
                    return
        except (OSError, ssl.SSLError):
            if time.monotonic() > deadline:
                raise RuntimeError(f'server on {port} did not answer over TLS')
            time.sleep(0.05)


def measure(name, server, cert, path, conns, close, args, log_dir, label):
    port = 9190 if name == 'anvil' else 9191
    env = dict(os.environ, TIN_CORES='1', TIN_PIN='0', GOMAXPROCS='1', PORT=str(port), TLS_CERT=str(cert[0]), TLS_KEY=str(cert[1]))
    cmd = [str(ROOT / 'bin/https_bench')] if name == 'anvil' else [str(ROOT / 'bin/gotls'), f':{port}', str(cert[0]), str(cert[1])]
    with (log_dir / f'{label}.server.log').open('wb') as log:
        proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=log)
        try:
            ready(port)
            if '-resumed-' in label or '-handshakes-' in label:
                resume = '-resumed-' in label
                load = [str(ROOT / 'bin/tlsload'), '-addr', f'127.0.0.1:{port}', '-path', path, '-c', str(conns)]
                if resume:
                    load.append('-resume')
                subprocess.run(load + ['-d', '1'], capture_output=True, text=True, check=True, timeout=30)
                r = subprocess.run(load + ['-d', str(args.seconds)], capture_output=True, text=True, check=True,
                                   timeout=args.seconds + 30)
                (log_dir / f'{label}.tlsload.log').write_text(r.stdout + r.stderr)
                if proc.poll() is not None:
                    raise RuntimeError(f'{name} exited during {label}')
                m = json.loads(r.stdout)
                if m['errors'] or m['handshakes'] == 0 or (resume and m['resumed'] < 0.9 * m['handshakes']) or \
                        (not resume and m['resumed'] != 0):
                    raise ValueError(f'{name} {label}: {r.stdout}')
                return m['rate'], 0.0
            wrk = ['wrk', '-t2', f'-c{conns}']
            if close:
                wrk += ['-H', 'Connection: close']
            url = f'https://127.0.0.1:{port}{path}'
            subprocess.run(wrk + ['-d1s', url], capture_output=True, text=True, check=True, timeout=30)
            r = subprocess.run(wrk + [f'-d{args.seconds}s', url], capture_output=True, text=True, check=True, timeout=args.seconds + 30)
            (log_dir / f'{label}.wrk.log').write_text(r.stdout + r.stderr)
            if proc.poll() is not None:
                raise RuntimeError(f'{name} exited during {label}')
            return parse_wrk(r.stdout, reference=name != 'anvil')
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seconds', type=int)
    parser.add_argument('rounds', type=int)
    parser.add_argument('--json', type=Path, default=ROOT / 'bin/bench-https.json')
    args = parser.parse_args()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path(tempfile.mkdtemp(prefix='https-', dir=args.json.parent))
    certs = make_certs(log_dir)
    servers = ['anvil', 'crypto/tls']
    records = []
    try:
        for rnd in range(args.rounds):
            order = servers if rnd % 2 == 0 else servers[::-1]
            for scen, kind, path, conns, close in SCENARIOS:
                for name in order:
                    label = f'{rnd}-{name.replace("/", "-")}-{scen.split()[0]}-{kind}-{path.strip("/").split("?")[0]}'
                    rps, mib = measure(name, None, certs[kind], path, conns, close, args, log_dir, label)
                    records.append(dict(server=name, scenario=scen, round=rnd + 1, rps=rps, mib=mib))
    finally:
        args.json.write_text(json.dumps({'rounds': args.rounds, 'seconds': args.seconds, 'logs': str(log_dir),
                                         'samples': records}, indent=2) + '\n')
    print('| scenario | anvil | crypto/tls | anvil / Go |')
    print('|---|---:|---:|---:|')
    for scen, kind, path, conns, close in SCENARIOS:
        key, unit = ('mib', 'MiB/s') if path.startswith('/big') else ('rps', 'handshakes/s' if close else 'req/s')
        med = {name: statistics.median(r[key] for r in records if r['server'] == name and r['scenario'] == scen) for name in servers}
        print(f"| {scen} | {med['anvil']:.0f} {unit} | {med['crypto/tls']:.0f} {unit} | {med['anvil'] / med['crypto/tls']:.2f} |")
    print(f'One server core each (TIN_CORES=1, GOMAXPROCS=1), wrk -t2 on the same machine, {args.seconds} s runs, '
          f'{args.rounds} alternating rounds, medians; higher is better.')


if __name__ == '__main__':
    main()
