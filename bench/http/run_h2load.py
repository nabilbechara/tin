#!/usr/bin/env python3
"""HTTP/2 (h2c) measurements with h2load (#360): anvil (examples/api.tin) against Go's net/http
serving h2c (bench/http/goh2c), interleaved rounds, medians and the ratio.

Usage: run_h2load.py CORES THREADS CONNECTIONS STREAMS SECONDS [ROUNDS] [--json PATH]
Each server gets CORES cores (TIN_CORES, GOMAXPROCS); h2load runs THREADS threads with CONNECTIONS
connections of STREAMS concurrent streams each, for SECONDS after a 2-second warm-up. A round with
a failed, errored or non-2xx request fails the run."""
import argparse
import json
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


def parse_h2load(text):
    finished = re.search(r'^finished in ([\d.]+)(ms|s), ([\d.]+) req/s', text, re.M)
    counts = re.search(r'^requests: (\d+) total, (\d+) started, (\d+) done, (\d+) succeeded, (\d+) failed, '
                       r'(\d+) errored, (\d+) timeout', text, re.M)
    codes = re.search(r'^status codes: (\d+) 2xx, (\d+) 3xx, (\d+) 4xx, (\d+) 5xx', text, re.M)
    # nghttp2 1.59 (Ubuntu 24.04) prints min, max, mean; newer versions min, max, median, p95, p99, mean.
    mean = (re.search(r'^time for request:\s+\S+\s+\S+\s+([\d.]+)(us|ms|s)', text, re.M) or
            re.search(r'^request\s+:\s+(?:\S+\s+){5}([\d.]+)(us|ms|s)', text, re.M))
    if not finished or not counts or not codes or not mean:
        raise ValueError('incomplete h2load output: ' + text)
    done, succeeded, failed, errored, timeout = (int(counts[i]) for i in (3, 4, 5, 6, 7))
    # In a timed run a stream in flight at the end may count its 2xx without being done: no other
    # status may appear at all.
    if failed or errored or timeout or succeeded != done or int(codes[1]) < succeeded or done == 0 or \
            int(codes[2]) + int(codes[3]) + int(codes[4]):
        raise ValueError('h2load reported failed requests: ' + text)
    scale = {'us': 1, 'ms': 1000, 's': 1000000}
    return {'rps': float(finished[3]), 'requests': succeeded,
            'mean_us': float(mean[1]) * scale[mean[2]]}


def process_stats(pid):
    out = subprocess.run(['ps', '-o', 'rss=', '-o', 'time=', '-p', str(pid)],
                         capture_output=True, text=True, check=True, timeout=5).stdout.split()
    rss, cpu = out
    days = 0
    if '-' in cpu:
        days, cpu = cpu.split('-', 1)
    seconds = 0.0
    for piece in cpu.split(':'):
        seconds = seconds * 60 + float(piece)
    return int(rss), seconds + int(days) * 86400


def body_of(url):
    # The same handlers answer HTTP/1.1: check the bodies the measurement asks for.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=1) as reply:
        return reply.read()


def verify(path, body):
    if path == '/json':
        if json.loads(body) != {'message': 'Hello, World!'}:
            raise ValueError('incorrect /json response: ' + repr(body))
    elif body != b'Hello, World!':
        raise ValueError('incorrect /plaintext response: ' + repr(body))


def measure(command, port, path, args, env, log_dir, label):
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
                    verify(path, body_of(url))
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('server did not become ready: ' + label)
                    time.sleep(.05)
            h2load = ['h2load', '-t', str(args.threads), '-c', str(args.connections), '-m', str(args.streams)]
            warm = subprocess.run(h2load + ['-D', '2', url], capture_output=True, text=True, check=True, timeout=30)
            (log_dir / (label + '.warmup.log')).write_text(warm.stdout + warm.stderr)
            parse_h2load(warm.stdout)
            _, before = process_stats(proc.pid)
            run = subprocess.run(h2load + ['-D', str(args.seconds), url], capture_output=True, text=True,
                                 check=True, timeout=args.seconds + 30)
            (log_dir / (label + '.h2load.log')).write_text(run.stdout + run.stderr)
            metrics = parse_h2load(run.stdout)
            rss, after = process_stats(proc.pid)
            if proc.poll() is not None:
                raise RuntimeError('server exited during measurement: ' + label)
            verify(path, body_of(url))
            metrics.update(rss_kb=rss, requests_per_cpu_second=(metrics['requests'] / (after - before)
                           if after > before else None))
            return metrics
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
    parser.add_argument('streams', type=int)
    parser.add_argument('seconds', type=int)
    parser.add_argument('rounds', type=int, nargs='?', default=5)
    parser.add_argument('--json', type=Path, default=ROOT / 'bin/bench-h2.json')
    args = parser.parse_args()
    if min(args.cores, args.threads, args.connections, args.streams, args.seconds, args.rounds) < 1:
        parser.error('all measurement settings must be positive')
    servers = {'anvil': ([str(ROOT / 'bin/api')], 9180),
               'net/http': ([str(ROOT / 'bin/goh2c'), ':9183'], 9183)}
    env = dict(os.environ, TIN_CORES=str(args.cores), TIN_PIN='0', TIN_GRACE='1',
               PORT='9180', GOMAXPROCS=str(args.cores), LC_ALL='C')
    args.json.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path(tempfile.mkdtemp(prefix='h2load-', dir=args.json.parent))
    records = []
    names = list(servers)
    try:
        for round_number in range(args.rounds):
            order = names if round_number % 2 == 0 else names[::-1]
            for path in ('/json', '/plaintext'):
                for name in order:
                    command, port = servers[name]
                    metrics = measure(command, port, path, args, env, log_dir,
                                      f'{round_number}-{name.replace("/", "-")}-{path[1:]}')
                    records.append(dict(server=name, path=path, round=round_number + 1, **metrics))
    finally:
        args.json.write_text(json.dumps({'rounds': args.rounds, 'cores': args.cores, 'threads': args.threads,
            'connections': args.connections, 'streams': args.streams, 'seconds': args.seconds,
            'logs': str(log_dir), 'samples': records}, indent=2) + '\n')
    print('| server | path | median req/s | median mean latency us | median RSS KiB | median req per CPU s | ratio |')
    print('|---|---|---:|---:|---:|---:|---:|')
    for path in ('/json', '/plaintext'):
        medians = {}
        for name in names:
            samples = [r for r in records if r['server'] == name and r['path'] == path]
            medians[name] = {key: statistics.median(r[key] for r in samples if r[key] is not None)
                             for key in ('rps', 'mean_us', 'rss_kb', 'requests_per_cpu_second')}
        for name, v in medians.items():
            print(f"| {name} | {path} | {v['rps']:.0f} | {v['mean_us']:.1f} | {v['rss_kb']:.0f} | "
                  f"{v['requests_per_cpu_second']:.0f} | {v['rps'] / medians[names[0]]['rps']:.3f} |")
    print('Ratio is req/s relative to ' + names[0] + '; higher is faster.')


if __name__ == '__main__':
    main()
