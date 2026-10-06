#!/usr/bin/env python3
"""Compare two Tin revisions using their own compiler AND runtime/library trees."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from measure import benchmark_names, interleaved, run_checked, tin_command

ROOT = Path(__file__).resolve().parents[1]


def cpu(base, head, suite, names, runs, work):
    records = []
    print('| benchmark | base ms | head ms | head/base time | review |')
    print('|---|---:|---:|---:|---|')
    for name in benchmark_names(suite, names):
        commands = {}
        for label, root in (('base', base), ('head', head)):
            exe = work / (name + '_' + label)
            try:
                run_checked(**tin_command(root, suite / (name + '.tin'), exe))
            except subprocess.CalledProcessError:
                if label != 'base':
                    raise
                break  # a benchmark of something base does not have yet
            commands[label] = {'command': [str(exe)], 'env': dict(os.environ, LC_ALL='C')}
        if 'base' not in commands:
            print(f'| {name} | - | - | - | new: base cannot build it |', flush=True)
            records.append({'benchmark': name, 'new_in_head': True})
            continue
        timing, samples = interleaved(commands, runs)
        ratio = timing['head'] / timing['base']
        review = ratio > 1.05
        print(f"| {name} | {timing['base'] * 1000:.2f} | {timing['head'] * 1000:.2f} | "
              f"{ratio:.3f} | {'REVIEW (>5%)' if review else 'within 5%'} |", flush=True)
        records.append({'benchmark': name, 'seconds': samples, 'head_over_base': ratio,
                        'needs_review': review})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-root', required=True, type=Path)
    parser.add_argument('--head-root', type=Path, default=ROOT)
    parser.add_argument('--suite', choices=('cpu', 'http'), default='cpu')
    parser.add_argument('--bench-dir', type=Path, default=ROOT / 'bench/v2')
    parser.add_argument('--runs', type=int, default=7)
    parser.add_argument('--rounds', type=int, default=5)
    parser.add_argument('--seconds', type=int, default=10)
    parser.add_argument('--json', type=Path)
    parser.add_argument('names', nargs='*')
    args = parser.parse_args()
    if args.runs < 7 or args.rounds < 5 or args.seconds < 1:
        parser.error('require at least 7 CPU runs, 5 HTTP rounds and positive duration')
    base, head = args.base_root.resolve(), args.head_root.resolve()
    for root in (base, head):
        if not (root / 'bin/tinc').is_file() or not ((root / 'toolchain/runtime').is_dir() or (root / 'lib').is_dir()):
            parser.error(f'build {root} with make bootstrap first (compiler and library required)')
    output = ROOT / 'bin/bench'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='compare-', dir=output) as tmp:
        work = Path(tmp)
        if args.suite == 'cpu':
            records = cpu(base, head, args.bench_dir.resolve(), args.names, args.runs, work)
            if args.json:
                args.json.parent.mkdir(parents=True, exist_ok=True)
                args.json.write_text(json.dumps({'base_root': str(base), 'head_root': str(head),
                    'runs': args.runs, 'results': records}, indent=2) + '\n')
        else:
            if args.names:
                parser.error('benchmark names apply only to the CPU suite')
            for label, root in (('base', base), ('head', head)):
                run_checked(**tin_command(root, head / 'examples/api.tin', work / label))
            command = ['python3', str(ROOT / 'bench/http/run_wrk.py'), '1', '2', '100',
                       str(args.seconds), str(args.rounds), '--base-api', str(work / 'base'),
                       '--head-api', str(work / 'head')]
            if args.json:
                command += ['--json', str(args.json.resolve())]
            subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
