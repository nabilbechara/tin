#!/usr/bin/env python3
"""Maps grow without stalling the core (#346): inserting 4 million integer keys, or a million str
keys, into a long-lived map never makes one insert take a millisecond (before, the rehash at 2^21
entries took 50 to 100 ms). The slowest insert of a run is noise-prone on a shared runner (a
descheduled thread), so the best of five runs is checked (a real stall repeats in every run, at the same insert). Fixture mapgrow.tin; the semantics
(order, deletes, rebuilds) are toolchain/tests/edition1/run/map_growth.tin."""
import os
import subprocess

from suite import ROOT


def run(exe, n, kind):
    out = subprocess.run([str(exe), str(n), kind], capture_output=True, text=True, check=True).stdout
    words = out.split()
    return dict(zip(words[0::2], words[1::2]))


def main():
    work = ROOT / 'bin/ci/mapgrow'
    work.mkdir(parents=True, exist_ok=True)
    exe = work / 'mapgrow'
    compiler = os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc'))
    subprocess.run([compiler, '-o', str(exe), 'tools/ci/fixtures/mapgrow.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    for n, kind in ((4000000, 'int'), (1000000, 'str')):
        runs = [run(exe, n, kind) for _ in range(5)]
        for r in runs:
            assert r['found'] == str(n), r
        worst = min(int(r['worst_us']) for r in runs)
        print('%d %s keys: slowest insert %d us (best of 5 runs; all runs: %s), total %s ms, lookups %s ms' %
              (n, kind, worst, ', '.join(r['worst_us'] for r in runs), runs[0]['total_ms'], runs[0]['lookup_ms']))
        # A shared macOS runner stalls any thread for milliseconds now and then; the old rehash
        # took 50 ms there.
        limit = 1000 if os.path.exists('/proc/self/maps') else 15000
        assert worst < limit, runs


if __name__ == '__main__':
    main()
