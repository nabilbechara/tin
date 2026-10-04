#!/usr/bin/env python3
"""v0.4 benchmark: GET /users/{id} (Redis cache over MySQL) in Tin vs Go + chi, under wrk2.

Needs a Redis and a MySQL with the users table (bench/v04/seed.py) and a wrk2 binary:
  REDIS_ADDR MYSQL_ADDR MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE WRK2 [CORES=4 ROUNDS=3 SECS=15]
  [SERVER_CPUS=0,1 WRK_CPUS=2,3]  pin the servers and wrk2 to separate CPUs (taskset)

Scenarios (random ids in 1..10000):
  cached   all reads hit Redis (warmed first)
  db       /db/users/{id}: every read is a MySQL prepared statement
  mixed    cached reads with 0.5% /slow (50 ms) requests mixed in
Before every run Redis is emptied and the run warms its own cache, so all its keys are fresh:
their 60 s TTL cannot expire during a run and send a burst of reads to MySQL. Redis snapshots
(a fork every minute under the default config) are turned off for the same reason.
Each runs once at an open-ended rate (the maximum throughput) and once at a fixed rate,
70% of the slower server's maximum, for the latency percentiles (wrk2 corrects for
coordinated omission). Rounds alternate servers; the median of the rounds is reported,
with every round's value and the Tin/Go ratios after the table."""
import os
import re
import socket
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, 'bench', 'v04')
OUT = os.path.join(ROOT, 'bin', 'bench04')
CORES = os.environ.get('CORES', '4')
ROUNDS = int(os.environ.get('ROUNDS', '3'))
SECS = int(os.environ.get('SECS', '15'))
WRK = os.environ['WRK2']
CONNS = int(os.environ.get('CONNS', '256'))
THREADS = os.environ.get('THREADS', '4')
SCENARIOS = [('cached', '/users/', 0), ('db', '/db/users/', 0), ('mixed', '/users/', 0.5)]
SERVERS = {'tin': ('users_tin', 9190), 'go': ('users_go', 9191)}
SERVER_CPUS = os.environ.get('SERVER_CPUS', '')
WRK_CPUS = os.environ.get('WRK_CPUS', '')


def pinned(cpus, argv):
    return ['taskset', '-c', cpus] + argv if cpus else argv


def build():
    os.makedirs(OUT, exist_ok=True)
    subprocess.run([os.path.join(ROOT, 'bin', 'tinc'), '-o', os.path.join(OUT, 'users_tin'), os.path.join(HERE, 'users.tin')],
                   check=True, env=dict(os.environ, TIN_ROOT=ROOT))
    subprocess.run(['go', 'build', '-o', os.path.join(OUT, 'users_go'), '.'], cwd=os.path.join(HERE, 'go'), check=True)


def redis(*args):
    host, port = os.environ['REDIS_ADDR'].rsplit(':', 1)
    with socket.create_connection((host, int(port)), timeout=10) as c:
        c.sendall(('*%d\r\n' % len(args) + ''.join('$%d\r\n%s\r\n' % (len(a), a) for a in args)).encode())
        reply = c.recv(256)
    if not reply.startswith(b'+OK'):
        sys.exit('redis %s: %r' % (' '.join(args), reply))


def start(name):
    redis('FLUSHALL')
    exe, port = SERVERS[name]
    env = dict(os.environ, TIN_CORES=CORES, GOMAXPROCS=CORES, PORT=str(port))
    p = subprocess.Popen(pinned(SERVER_CPUS, [os.path.join(OUT, exe)]), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    return p, port


def us(v):
    m = re.match(r'([\d.]+)(us|ms|s|m)$', v)
    n = float(m.group(1))
    return n * {'us': 1, 'ms': 1000, 's': 1e6, 'm': 6e7}[m.group(2)]


def wrk(port, prefix, slow, rate, secs):
    r = subprocess.run(pinned(WRK_CPUS, [WRK, '-t' + THREADS, '-c%d' % CONNS, '-d%ds' % secs, '-R%d' % rate, '--latency',
                                         '-s', os.path.join(HERE, 'mix.lua'), 'http://127.0.0.1:%d' % port, '--', prefix, str(slow)]),
                       capture_output=True, text=True)
    out = r.stdout
    m = re.search(r'Requests/sec:\s+([\d.]+)', out)
    if not m:
        sys.exit('wrk2 (exit %d) gave no rate:\n%s\n%s' % (r.returncode, out[-2000:], r.stderr[-2000:]))
    rps = float(m.group(1))
    pct = {}
    for p, v in re.findall(r'^\s+(\d+\.\d+)%\s+(\S+)', out, re.M):
        pct[p] = us(v)
    errs = re.findall(r'(Non-2xx or 3xx responses: \d+|Socket errors: .*)', out)
    return rps, pct, errs


def cpu_rss(pid):
    o = subprocess.run(['ps', '-o', 'time=,rss=', '-p', str(pid)], capture_output=True, text=True).stdout.split()
    t = o[0].split(':')
    secs = float(t[-1]) + 60 * float(t[-2]) + (3600 * float(t[-3]) if len(t) == 3 else 0)
    return secs, int(o[1])


def main():
    build()
    redis('CONFIG', 'SET', 'save', '')
    results = {}
    for scen, prefix, slow in SCENARIOS:
        for r in range(ROUNDS):
            for name in (['tin', 'go'] if r % 2 == 0 else ['go', 'tin']):
                p, port = start(name)
                try:
                    wrk(port, prefix, slow, 1000000, 3)  # warm: caches, pools, prepared statements
                    c0, _ = cpu_rss(p.pid)
                    rps, _, errs = wrk(port, prefix, slow, 1000000, SECS)
                    c1, rss = cpu_rss(p.pid)
                    results.setdefault((scen, name, 'max'), []).append((rps, errs, rss, rps * SECS / max(c1 - c0, 0.001)))
                finally:
                    p.terminate()
                    p.wait()
        target = int(0.7 * min(statistics.median(x[0] for x in results[(scen, n, 'max')]) for n in SERVERS))
        for r in range(ROUNDS):
            for name in (['tin', 'go'] if r % 2 == 0 else ['go', 'tin']):
                p, port = start(name)
                try:
                    wrk(port, prefix, slow, target, 3)
                    rps, pct, errs = wrk(port, prefix, slow, target, SECS)
                    results.setdefault((scen, name, 'fixed'), []).append((rps, pct, errs, target))
                finally:
                    p.terminate()
                    p.wait()
    print('cores per server: %s, wrk2 -t%s -c%d, %d s per run, median of %d rounds' % (CORES, THREADS, CONNS, SECS, ROUNDS))
    if SERVER_CPUS or WRK_CPUS:
        print('server CPUs: %s, wrk2 CPUs: %s' % (SERVER_CPUS or 'any', WRK_CPUS or 'any'))
    print('%-8s %-4s %12s %10s %12s %10s %10s %10s %8s' % ('scenario', '', 'max req/s', 'req/cpu-s', 'fixed req/s', 'p50 ms', 'p99 ms', 'p99.9 ms', 'RSS MB'))
    for scen, _, _ in SCENARIOS:
        for name in SERVERS:
            mx = results[(scen, name, 'max')]
            fx = results[(scen, name, 'fixed')]
            med = lambda xs: statistics.median(xs)
            errs = [e for x in mx for e in x[1]] + [e for x in fx for e in x[2]]
            print('%-8s %-4s %12.0f %10.0f %12d %10.2f %10.2f %10.2f %8.0f %s' % (
                scen, name, med(x[0] for x in mx), med(x[3] for x in mx), fx[0][3],
                med(x[1]['50.000'] for x in fx) / 1000, med(x[1]['99.000'] for x in fx) / 1000,
                med(x[1]['99.900'] for x in fx) / 1000, med(x[2] for x in mx) / 1024, ' '.join(sorted(set(errs)))))
    print()
    print('every round (in run order): max req/s | fixed-rate p99 ms')
    for scen, _, _ in SCENARIOS:
        for name in SERVERS:
            print('%-8s %-4s %s | %s' % (scen, name, ' '.join('%.0f' % x[0] for x in results[(scen, name, 'max')]),
                                         ' '.join('%.2f' % (x[1]['99.000'] / 1000) for x in results[(scen, name, 'fixed')])))
    print()
    print('Tin/Go ratios of the medians (above 1: Tin higher)')
    print('%-8s %10s %10s %10s %10s %10s' % ('scenario', 'max req/s', 'req/cpu-s', 'p50', 'p99', 'p99.9'))
    for scen, _, _ in SCENARIOS:
        def m(name, kind, f):
            return statistics.median(f(x) for x in results[(scen, name, kind)])
        cols = [m('tin', 'max', lambda x: x[0]) / m('go', 'max', lambda x: x[0]),
                m('tin', 'max', lambda x: x[3]) / m('go', 'max', lambda x: x[3])]
        cols += [m('tin', 'fixed', lambda x, k=k: x[1][k]) / m('go', 'fixed', lambda x, k=k: x[1][k]) for k in ('50.000', '99.000', '99.900')]
        print('%-8s %10.2f %10.2f %10.2f %10.2f %10.2f' % tuple([scen] + cols))


if __name__ == '__main__':
    main()
