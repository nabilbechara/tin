#!/usr/bin/env python3
"""Run strict tests without losing compiler/process status or trusting stale binaries."""
import argparse
import difflib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]

# Assembly checks (NAME_asm.tin + NAME_asm.check): ordered CHECK/CHECK-NOT lines matched
# against the -S listing, the way lit does it. A [arch] line selects a section, so one
# file can hold the arm64 and amd64 expectations; lines before any section apply to all.
ASM_ARCH = re.compile(r'^\[([a-z0-9_-]+)\]$')
ASM_DIRECTIVE = re.compile(r'^(CHECK|CHECK-NOT):\s*(.*)$')


def asm_arch(target=None):
    """The architecture whose section of a .check file applies: the target if given, else the host."""
    if target:
        return target.split('-')[-1]
    machine = platform.machine().lower()
    if machine in ('arm64', 'aarch64'):
        return 'arm64'
    if machine in ('x86_64', 'amd64'):
        return 'amd64'
    return machine


def parse_checks(path, arch):
    """Read a .check file into ordered (kind, pattern) directives for arch."""
    directives = []
    section = None
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        match = ASM_ARCH.match(line)
        if match:
            section = match.group(1)
            continue
        match = ASM_DIRECTIVE.match(line)
        if not match:
            raise ValueError(f'{path}:{number}: not a CHECK, CHECK-NOT or [arch] line: {line}')
        if not match.group(2):
            raise ValueError(f'{path}:{number}: {match.group(1)} with an empty pattern')
        if section in (None, arch):
            directives.append((match.group(1), match.group(2)))
    return directives


def check_asm(text, directives):
    """Match lit-style directives in order; return (ok, the directive that failed).

    A CHECK-NOT must not match between the previous CHECK's match and the next CHECK's
    match (or the end of the listing), which is lit's scope, so a later part of the file
    that legitimately contains the pattern does not fail an earlier assertion.
    """
    position = 0
    for index, (kind, pattern) in enumerate(directives):
        if kind == 'CHECK-NOT':
            limit = len(text)
            for next_kind, next_pattern in directives[index + 1:]:
                if next_kind == 'CHECK':
                    match = re.search(next_pattern, text[position:])
                    if match:
                        limit = position + match.start()
                    break
            if re.search(pattern, text[position:limit]):
                return False, f'CHECK-NOT: {pattern}'
        else:
            match = re.search(pattern, text[position:])
            if not match:
                return False, f'CHECK: {pattern}'
            position += match.end()
    return True, ''


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
    discovered = sorted((root / 'tests/v2').glob('*.tin'))
    # An _asm.tin file is a program for the assembly checker, not a program to run.
    cases = [c for c in discovered if not c.stem.endswith('_asm')]
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
                results.append({'name': name, 'passed': False, 'exit': None})
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
        arch = asm_arch(target)
        asm_cases = sorted((root / 'tests/v2').glob('*_asm.tin'))
        for source in asm_cases:
            name = source.stem
            check = source.with_suffix('.check')
            if not check.exists():
                print('FAIL', name, 'missing check file:', check)
                results.append({'name': name, 'passed': False, 'exit': None})
                continue
            command = [str(compiler)] + (['-target', target] if target else [])
            command += ['-S', '-o', str(work / name), str(source.relative_to(root))]
            code, stdout, stderr = execute(command, cwd=root, env=env)
            (output / (name + '.asm.log')).write_bytes(stdout + stderr)
            if code != 0:
                passed, why = False, f'compiler exit {code}'
            else:
                try:
                    directives = parse_checks(check, arch)
                    if not directives:
                        passed, why = False, f'no directives for {arch}'
                    else:
                        passed, why = check_asm(stdout.decode(errors='replace'), directives)
                except (ValueError, re.error) as error:
                    passed, why = False, str(error)
            if not passed:
                print(f'FAIL {name} [{arch}]: {why}\n{stderr.decode(errors="replace")[:4000]}')
            else:
                print('PASS', name)
            results.append({'name': name, 'passed': passed, 'exit': code})
        # A check file whose test is missing (a typo in the name) would check nothing.
        asm_stems = {source.stem for source in asm_cases}
        for check in sorted((root / 'tests/v2').glob('*_asm.check')):
            if check.stem not in asm_stems:
                print('FAIL', check.stem, 'check file without a test:', check)
                results.append({'name': check.stem, 'passed': False, 'exit': None})
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
