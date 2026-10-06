#!/usr/bin/env python3
"""Compare Tin and Go with alternating runs, output equality and medians.

BENCH_DIR selects the suite (default bench/); RUNS defaults to seven.
Reference performance numbers come from native Linux (toolchain/docs/PERFORMANCE.md).
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from measure import benchmark_names, interleaved, tin_command

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('names', nargs='*')
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    directory = (ROOT / os.environ.get('BENCH_DIR', 'bench')).resolve()
    runs = int(os.environ.get('RUNS', '7'))
    if runs < 7:
        parser.error('RUNS must be at least 7')
    names = benchmark_names(directory, args.names)
    subprocess.run(['make', '-s', 'bin/tinc'], cwd=ROOT, check=True)
    output = ROOT / 'bin/bench'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    print('| benchmark | Tin build ms | Go build ms | Tin run ms | Go run ms | Go/Tin time |')
    print('|---|---:|---:|---:|---:|---:|')
    with tempfile.TemporaryDirectory(prefix='reference-', dir=output) as tmp:
        for name in names:
            tin_exe, go_exe = Path(tmp) / (name + '_tin'), Path(tmp) / (name + '_go')
            builds = {'tin': tin_command(ROOT, directory / (name + '.tin'), tin_exe),
                      'go': {'command': ['go', '-C', str(directory), 'build', '-o',
                                         str(go_exe), name + '.go']}}
            build, _ = interleaved(builds, 3, check_output=False)
            timing, samples = interleaved({'tin': {'command': [str(tin_exe)]},
                                           'go': {'command': [str(go_exe)]}}, runs)
            ratio = timing['go'] / timing['tin']
            print(f"| {name} | {build['tin'] * 1000:.1f} | {build['go'] * 1000:.1f} | "
                  f"{timing['tin'] * 1000:.1f} | {timing['go'] * 1000:.1f} | {ratio:.3f} |", flush=True)
            records.append({'benchmark': name, 'seconds': samples, 'go_over_tin': ratio})
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({'runs': runs, 'results': records}, indent=2) + '\n')


if __name__ == '__main__':
    main()
