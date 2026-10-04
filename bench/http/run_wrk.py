#!/usr/bin/env python3
"""Checked HTTP measurements; reference servers or two Tin revisions, interleaved medians."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def parse_wrk(text):
    rps = re.search(r'^Requests/sec:\s*([\d.]+)\s*$', text, re.M)
    p99 = re.search(r'^\s*99%\s+([\d.]+)(us|ms|s)\s*$', text, re.M)
    total = re.search(r'^\s*(\d+) requests in ', text, re.M)
    if not rps or not p99 or not total:
        raise ValueError('incomplete wrk output: ' + text)
    if re.search(r'Socket errors:|Non-2xx or 3xx responses:', text):
        raise ValueError('wrk reported request errors: ' + text)
    result = {'rps': float(rps[1]), 'p99_us': float(p99[1]) * {'us': 1, 'ms': 1000, 's': 1000000}[p99[2]],
              'requests': int(total[1])}
    if not all(math.isfinite(v) for v in result.values()) or result['rps'] <= 0 or result['requests'] <= 0:
        raise ValueError('wrk returned invalid or zero throughput')
    return result


def process_stats(pid):
    result = subprocess.run(['ps', '-o', 'rss=', '-o', 'time=', '-p', str(pid)],
                            capture_output=True, text=True, check=True, timeout=5)
    rss, cpu = result.stdout.split()
    days = 0
    if '-' in cpu:
        days, cpu = cpu.split('-', 1)
    seconds = 0.0
    for piece in cpu.split(':'):
        seconds = seconds * 60 + float(piece)
    return int(rss), seconds + int(days) * 86400


def response(url):
    # Local probes must not pass through an inherited HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=1) as reply:
        if reply.status != 200:
            raise ValueError('unexpected HTTP status: ' + str(reply.status))
        return reply.read()


def verify_body(path, body):
    if path == '/json':
        if json.loads(body) != {'message': 'Hello, World!'}:
            raise ValueError('incorrect /json response: ' + repr(body))
    elif body != b'Hello, World!':
        raise ValueError('incorrect /plaintext response: ' + repr(body))


def measure(command, port, path, args, env, log_dir, label):
    # Fail on an occupied port instead of timing a stale server.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', port))
    url = f'http://127.0.0.1:{port}{path}'
    with (log_dir / (label + '.server.log')).open('wb') as log:
        proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 10
            while True:
                if proc.poll() is not None:
                    raise RuntimeError('server exited during startup: ' + label)
                try:
                    body = response(url)
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('server did not become ready: ' + label)
                    time.sleep(.05)
            verify_body(path, body)
            wrk = ['wrk', f'-t{args.threads}', f'-c{args.connections}', '--latency']
            warmup = subprocess.run(wrk + ['-d2s', url], capture_output=True, text=True,
                                    check=True, timeout=15)
            (log_dir / (label + '.warmup.log')).write_text(warmup.stdout + warmup.stderr)
            parse_wrk(warmup.stdout)
            _, before = process_stats(proc.pid)
            result = subprocess.run(wrk + [f'-d{args.seconds}s', url], capture_output=True,
                                    text=True, check=True, timeout=args.seconds + 15)
            (log_dir / (label + '.wrk.log')).write_text(result.stdout + result.stderr)
            metrics = parse_wrk(result.stdout)
            rss, after = process_stats(proc.pid)
            if proc.poll() is not None:
                raise RuntimeError('server exited during measurement: ' + label)
            verify_body(path, response(url))
            metrics.update(rss_kb=rss, requests_per_cpu_second=(metrics['requests'] / (after - before)
                           if after > before else None))
            return metrics, body
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cores', type=int)
    parser.add_argument('threads', type=int)
    parser.add_argument('connections', type=int)
    parser.add_argument('seconds', type=int)
    parser.add_argument('rounds', type=int, nargs='?', default=3)
    parser.add_argument('--base-api', type=Path)
    parser.add_argument('--head-api', type=Path)
    parser.add_argument('--json', type=Path, default=ROOT / 'bin/bench-http.json')
    args = parser.parse_args()
    comparison = args.base_api is not None
    if comparison != (args.head_api is not None):
        parser.error('provide both --base-api and --head-api')
    if min(args.cores, args.threads, args.connections, args.seconds, args.rounds) < 1:
        parser.error('all measurement settings must be positive')
    if comparison and args.rounds < 5:
        parser.error('revision comparisons require at least 5 rounds')
    servers = ({'base': ([str(args.base_api.resolve())], 9180),
                'head': ([str(args.head_api.resolve())], 9180)} if comparison else
               {'anvil': ([str(ROOT / 'bin/api')], 9180),
                'fasthttp': ([str(ROOT / 'bin/fast'), ':9182'], 9182),
                'net/http': ([str(ROOT / 'bin/gonet'), ':9181'], 9181)})
    env = dict(os.environ, TIN_CORES=str(args.cores), TIN_PIN='0', TIN_GRACE='1',
               PORT='9180', GOMAXPROCS=str(args.cores), LC_ALL='C')
    args.json.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path(tempfile.mkdtemp(prefix='wrk-', dir=args.json.parent))
    records = []
    expected = {}
    names = list(servers)
    try:
        for round_number in range(args.rounds):
            order = names if round_number % 2 == 0 else names[::-1]
            for path in ('/json', '/plaintext'):
                for name in order:
                    command, port = servers[name]
                    metrics, body = measure(command, port, path, args, env, log_dir,
                                            f'{round_number}-{name.replace("/", "-")}-{path[1:]}')
                    if comparison:
                        if path in expected and body != expected[path]:
                            raise ValueError('OUTPUT MISMATCH between HTTP revisions: ' + path)
                        expected[path] = body
                    records.append(dict(server=name, path=path, round=round_number + 1, **metrics))
    finally:
        args.json.write_text(json.dumps({'rounds': args.rounds, 'cores': args.cores,
            'threads': args.threads, 'connections': args.connections, 'seconds': args.seconds,
            'logs': str(log_dir), 'samples': records}, indent=2) + '\n')
    print('| server | path | median req/s | median p99 us | median RSS KiB | ratio | review |')
    print('|---|---|---:|---:|---:|---:|---|')
    for path in ('/json', '/plaintext'):
        medians = {}
        for name in names:
            samples = [r for r in records if r['server'] == name and r['path'] == path]
            medians[name] = {key: statistics.median(r[key] for r in samples)
                             for key in ('rps', 'p99_us', 'rss_kb')}
        for name, values in medians.items():
            ratio = values['rps'] / medians[names[0]]['rps']
            review = 'REVIEW (>5%)' if comparison and name == 'head' and ratio < .95 else ''
            print(f"| {name} | {path} | {values['rps']:.0f} | {values['p99_us']:.1f} | "
                  f"{values['rss_kb']:.0f} | {ratio:.3f} | {review} |")
    print('Ratio is req/s relative to ' + names[0] + '; higher is faster.')


if __name__ == '__main__':
    main()
