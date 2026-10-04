#!/usr/bin/env python3
"""Compare exact number bits and text with Go and a pinned hard parsing corpus."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile

from suite import ROOT


def compare(exe, inputs, expected, directory, label):
    assert len(inputs) == len(expected) and inputs, 'empty or incomplete number corpus'
    # Bounded batches keep the request pool small without exposing private reset helpers.
    for start in range(0, len(inputs), 10000):
        batch = inputs[start:start + 10000]
        result = subprocess.run([str(exe)], input=b''.join(batch), capture_output=True,
                                timeout=60, cwd=ROOT)
        (directory / (label + '.stderr.log')).write_bytes(result.stderr)
        assert result.returncode == 0, f'{label}: exit {result.returncode}: {result.stderr!r}'
        actual = result.stdout.splitlines(keepends=True)
        want = expected[start:start + len(batch)]
        if actual != want:
            (directory / (label + '.actual.log')).write_bytes(result.stdout)
            for i, (got, value) in enumerate(zip(actual, want)):
                if got != value:
                    raise AssertionError(f'{label} case {start+i}: {batch[i]!r}: '
                                         f'got {got!r}, want {value!r}')
            raise AssertionError(f'{label}: {len(actual)} output lines, want {len(want)}')
    print(f'PASS {label}: {len(inputs)} exact results')


def main():
    directory = ROOT / 'bin/ci/number'
    directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TIN_ROOT=str(ROOT))
    subprocess.run(['python3', str(ROOT / 'tools/gen_number_powers.py'), '--check'],
                   check=True, cwd=ROOT, timeout=10)
    with tempfile.TemporaryDirectory(prefix='number-', dir=directory) as tmp:
        work = Path(tmp)
        exe = work / 'number'
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe),
                        'tools/ci/fixtures/number.tin'], check=True, cwd=ROOT, env=env,
                       timeout=60)
        subprocess.run(['go', 'run', './bench/ref/number', str(work)], check=True,
                       cwd=ROOT, timeout=60)
        compare(exe, (work / 'input.txt').read_bytes().splitlines(keepends=True),
                (work / 'expected.txt').read_bytes().splitlines(keepends=True),
                directory, 'Go-strconv-fmt')
        rows = gzip.decompress((ROOT / 'tools/ci/data/parse-number-f64.txt.gz').read_bytes())
        inputs, expected = [], []
        for row in rows.splitlines():
            bits, number = row.split(b' ', 1)
            inputs.append(b'P\t' + number + b'\n')
            expected.append(str(int(bits, 16)).encode() + b'\n')
        compare(exe, inputs, expected, directory, 'parse-number-fxx')
        (directory / 'results.json').write_text(json.dumps(
            {'passed': True, 'go_cases': len((work / 'input.txt').read_bytes().splitlines()),
             'hard_cases': len(inputs)}, indent=2) + '\n')


if __name__ == '__main__':
    main()
