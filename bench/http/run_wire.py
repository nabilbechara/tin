#!/usr/bin/env python3
"""HTTP client: wire (bench/http/wire_load.tin, one core) against Go's net/http client
(bench/http/goload, GOMAXPROCS=1), both calling Go's net/http server (bench/http/goh2c, two cores):
N GETs of /plaintext from 100 callers at once, over HTTP/2 by prior knowledge (one connection, 100
streams) and over HTTP/1.1 (100 kept connections). Interleaved rounds, medians of requests per
second, with the ratios (#480).

Usage: run_wire.py N ROUNDS [--json PATH]   (needs bin/wire_load, bin/goload, bin/goh2c)"""
import argparse
import json
import os
import socket
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UP, TIN = 9182, 9190
CALLERS = 100


def wait(port):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            socket.create_connection(('127.0.0.1', port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.05)
    raise SystemExit(f'nothing listens on {port}')


def rate(text, n):
    got, errors, ns = (int(x) for x in text.split())
    if errors or got != n:
        raise SystemExit(f'{errors} errors in {got} calls: {text}')
    return got / (ns / 1e9)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('n', type=int)
    parser.add_argument('rounds', type=int)
    parser.add_argument('--json')
    args = parser.parse_args()
    n = args.n // CALLERS * CALLERS
    url = f'http://127.0.0.1:{UP}/plaintext'
    up = subprocess.Popen([str(ROOT / 'bin/goh2c'), f':{UP}'], env=dict(os.environ, GOMAXPROCS='2'))
    tin = subprocess.Popen([str(ROOT / 'bin/wire_load')], env=dict(os.environ, TIN_CORES='1'))
    samples = {k: [] for k in ('tin h2c', 'go h2c', 'tin h1', 'go h1')}
    try:
        wait(UP)
        wait(TIN)
        for r in range(args.rounds + 1):
            for mode in ('h2c', 'h1'):
                q = f'/load?url={url}&n={n}&c={CALLERS}&mode={mode}'
                with urllib.request.urlopen(f'http://127.0.0.1:{TIN}{q}', timeout=300) as resp:
                    t = rate(resp.read().decode(), n)
                g = subprocess.run([str(ROOT / 'bin/goload'), '-url', url, '-n', str(n), '-c', str(CALLERS), '-mode', mode],
                                   capture_output=True, text=True, timeout=300, env=dict(os.environ, GOMAXPROCS='1'))
                gr = rate(g.stdout, n)
                if r > 0:  # the first round warms up
                    samples[f'tin {mode}'].append(t)
                    samples[f'go {mode}'].append(gr)
    finally:
        tin.terminate()
        up.terminate()
    med = {k: statistics.median(v) for k, v in samples.items()}
    print(f'| protocol, {CALLERS} callers | wire (Tin) | net/http (Go) | Tin/Go |')
    print('|---|---:|---:|---:|')
    for mode, label in (('h2c', 'HTTP/2 (one connection)'), ('h1', f'HTTP/1.1 ({CALLERS} connections)')):
        t, g = med[f'tin {mode}'], med[f'go {mode}']
        print(f'| {label} | {t:.0f} req/s | {g:.0f} req/s | {t / g:.2f} |')
    print(f'| HTTP/2 / HTTP/1.1 | {med["tin h2c"] / med["tin h1"]:.2f} | {med["go h2c"] / med["go h1"]:.2f} | |')
    if args.json:
        Path(args.json).write_text(json.dumps({'samples': samples, 'medians': med}, indent=1))


if __name__ == '__main__':
    main()
