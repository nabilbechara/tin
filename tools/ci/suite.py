#!/usr/bin/env python3
"""Run strict tests without losing compiler/process status or trusting stale binaries."""
import argparse
import difflib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def execute(command, *, cwd=ROOT, timeout=60, env=None):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or b"", (exc.stderr or b"") + b"\nCI timeout\n"


def compare(name, expected, actual):
    if expected == actual:
        return True
    print(''.join(difflib.unified_diff(expected.decode(errors='replace').splitlines(True),
                                     actual.decode(errors='replace').splitlines(True),
                                     fromfile=name + '.expected', tofile=name + '.actual'))[:6000])
    return False


def run(compiler, target=None, docker=None, root=ROOT):
    cases = sorted((root / 'tests/v2').glob('*.tin'))
    if not cases:
        raise ValueError('No strict tests discovered')
    output = root / 'bin/ci'
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TIN_ROOT=os.environ.get('TIN_ROOT', str(root)), LC_ALL='C')
    results = []
    # Unique directory for each run: failed compilation cannot reuse a stale executable.
    with tempfile.TemporaryDirectory(prefix='strict-', dir=output) as work:
        work = Path(work)
        for source in cases:
            name = source.stem
            negative = name.endswith('_bad')
            golden = source.with_suffix('.err' if negative else '.out')
            if not golden.exists():
                print('FAIL', name, 'missing expected output:', golden)
                results.append({'name': name, 'passed': False})
                continue
            exe = work / name
            command = [str(compiler)] + (['-target', target] if target else [])
            command += ['-o', str(exe), str(source.relative_to(root))]
            code, stdout, stderr = execute(command, cwd=root, env=env)
            (output / (name + '.compile.log')).write_bytes(stdout + stderr)
            if negative:
                passed = code == 1 and compare(name, golden.read_bytes(), stderr)
            elif code != 0:
                passed = False
            else:
                command = [str(exe)]
                if docker:
                    command = ['docker', 'run', '--rm', '--platform', target.replace('-', '/'),
                               '-v', str(work) + ':/work', '-w', '/work', docker,
                               'timeout', '60', '/work/' + name]
                code, stdout, stderr = execute(command, cwd=root, timeout=75 if docker else 60)
                (output / (name + '.run.log')).write_bytes(stdout + stderr)
                passed = code == 0 and compare(name, golden.read_bytes(), b''.join(sorted(stdout.splitlines(True))))
            if not passed:
                print(f'FAIL {name}: exit {code}\n{stderr.decode(errors="replace")[:4000]}')
            else:
                print('PASS', name)
            results.append({'name': name, 'passed': passed, 'exit': code})
    (output / 'strict-results.json').write_text(json.dumps(results, indent=2) + '\n')
    return all(r['passed'] for r in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', nargs='?', default='bin/tinc')
    parser.add_argument('--target')
    parser.add_argument('--docker', help='Execute cross-built tests in this Linux image')
    args = parser.parse_args()
    if args.docker and not args.target:
        parser.error('--docker requires --target')
    return 0 if run(Path(args.compiler).resolve(), args.target, args.docker) else 1


if __name__ == '__main__':
    sys.exit(main())
