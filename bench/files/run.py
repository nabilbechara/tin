#!/usr/bin/env python3
"""quarry.ReadFile of 10k files in request handlers (#357): io_uring versus helper threads.

A server (bench/files/files.tin) answers GET /read?n=N by reading the core's next N of FILES
files (SIZE bytes each, in the page cache after a warm-up pass) one after another. For each
core count, the io_uring path (the default on Linux) and the helper threads (TIN_IO_URING=0)
run in alternating rounds; each run keeps 4 connections per core busy for a fixed time and
counts the files read in verified responses. Reported: median files/s, the server's CPU time
per 1000 files, and the ratios. Numbers count only on Linux (toolchain/docs/PERFORMANCE.md).
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def cpu_seconds(pid):
    """User plus system CPU time of every thread of pid (Linux /proc), or None."""
    try:
        fields = open('/proc/%d/stat' % pid).read().rsplit(')', 1)[1].split()
    except OSError:
        return None
    return (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')


def rings(pid):
    try:
        return sum('io_uring' in os.readlink('/proc/%d/fd/%s' % (pid, fd)) for fd in os.listdir('/proc/%d/fd' % pid))
    except OSError:
        return None


def start(exe, port, cores, ring, files, count):
    env = dict(os.environ, PORT=str(port), TIN_CORES=str(cores), FILES_DIR=str(files), FILES_COUNT=str(count),
               TIN_DEADLINE_MS='600000')
    env.pop('TIN_IO_URING', None)
    if not ring:
        env['TIN_IO_URING'] = '0'
    p = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(200):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=.1).close()
            return p
        except OSError:
            if p.poll() is not None:
                raise RuntimeError('server exited at startup')
            time.sleep(.05)
    raise RuntimeError('server did not start')


def load(port, conns, n, size, seconds):
    """Keeps conns keep-alive connections busy for seconds; returns the files read."""
    want = str(n * size).encode()
    done = [0] * conns
    errors = []
    end = time.monotonic() + seconds

    def client(i):
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=120)
        try:
            while time.monotonic() < end:
                c.request('GET', '/read?n=%d' % n)
                r = c.getresponse()
                body = r.read()
                if r.status != 200 or body != want:
                    errors.append((r.status, body[:200]))
                    return
                if time.monotonic() <= end:
                    done[i] += n
        except Exception as e:  # a failed request is never a sample
            errors.append(repr(e))
        finally:
            c.close()
    threads = [threading.Thread(target=client, args=(i,)) for i in range(conns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise RuntimeError('requests failed: %r' % errors[:3])
    return sum(done)


def run_one(exe, cores, ring, args, files):
    port = free_port()
    p = start(exe, port, cores, ring, files, args.files)
    try:
        conns = 4 * cores
        # Warm-up: every file once through each core's path (and its ring or the helpers).
        load(port, conns, args.n, args.size, 1.0)
        c0 = cpu_seconds(p.pid)
        t0 = time.monotonic()
        got = load(port, conns, args.n, args.size, args.seconds)
        took = time.monotonic() - t0
        c1 = cpu_seconds(p.pid)
        r = rings(p.pid)
        if r is not None and sys.platform.startswith('linux'):
            if ring and r == 0:
                raise RuntimeError('io_uring run made no ring (the kernel refuses io_uring?)')
            if not ring and r != 0:
                raise RuntimeError('TIN_IO_URING=0 run made a ring')
        if p.poll() is not None:
            raise RuntimeError('server exited during the run')
        cpu = None if c0 is None else (c1 - c0) * 1e6 / got  # ms of CPU per 1000 files
        return got / took, cpu
    finally:
        p.kill()
        p.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--files', type=int, default=10000)
    ap.add_argument('--size', type=int, default=4096)
    ap.add_argument('--n', type=int, default=1000, help='files read per request')
    ap.add_argument('--cores', default='1,2,4,8')
    ap.add_argument('--rounds', type=int, default=5)
    ap.add_argument('--seconds', type=float, default=3.0)
    ap.add_argument('--dir', help='where to make the files (default: a temporary directory)')
    ap.add_argument('--json')
    args = ap.parse_args()
    cores = [int(c) for c in args.cores.split(',')]

    out = ROOT / 'bin/bench-files'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'files'
    subprocess.run([os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc')), '-o', str(exe), str(ROOT / 'bench/files/files.tin')],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    files = Path(tempfile.mkdtemp(prefix='tin-bench-files-', dir=args.dir))
    try:
        for i in range(args.files):
            (files / ('f%d' % i)).write_bytes(os.urandom(args.size))
        samples = {(c, m): [] for c in cores for m in ('helper', 'io_uring')}
        cpus = {(c, m): [] for c in cores for m in ('helper', 'io_uring')}
        for rnd in range(args.rounds):
            for c in cores:
                order = ('helper', 'io_uring') if rnd % 2 == 0 else ('io_uring', 'helper')
                for m in order:
                    rate, cpu = run_one(exe, c, m == 'io_uring', args, files)
                    samples[(c, m)].append(rate)
                    if cpu is not None:
                        cpus[(c, m)].append(cpu)
                    print('round %d, %d cores, %-8s %10.0f files/s' % (rnd + 1, c, m, rate), file=sys.stderr, flush=True)
    finally:
        shutil.rmtree(files, ignore_errors=True)

    med = {k: statistics.median(v) for k, v in samples.items()}
    cpu = {k: statistics.median(v) if v else None for k, v in cpus.items()}
    print('quarry.ReadFile of %d files of %d bytes, %d per request, 4 connections per core, %d rounds of %.0f s, medians'
          % (args.files, args.size, args.n, args.rounds, args.seconds))
    print('%5s  %14s  %14s  %9s  %16s  %16s' % ('cores', 'helper files/s', 'io_uring files/s', 'uring/helper',
                                                  'helper CPU ms/1k', 'io_uring CPU ms/1k'))
    for c in cores:
        h, u = med[(c, 'helper')], med[(c, 'io_uring')]
        ch, cu = cpu[(c, 'helper')], cpu[(c, 'io_uring')]
        print('%5d  %14.0f  %16.0f  %11.2fx  %16s  %18s' % (c, h, u, u / h, '-' if ch is None else '%.2f' % ch,
                                                           '-' if cu is None else '%.2f' % cu))
    base = cores[0]
    for c in cores[1:]:
        print('%d cores / %d: helper %.2fx, io_uring %.2fx' % (c, base, med[(c, 'helper')] / med[(base, 'helper')],
                                                              med[(c, 'io_uring')] / med[(base, 'io_uring')]))
    if args.json:
        Path(args.json).write_text(json.dumps({
            'files': args.files, 'size': args.size, 'per_request': args.n, 'rounds': args.rounds, 'seconds': args.seconds,
            'samples': {'%d %s' % k: v for k, v in samples.items()},
            'cpu_ms_per_1k': {'%d %s' % k: v for k, v in cpus.items()},
        }, indent=1))


if __name__ == '__main__':
    main()
