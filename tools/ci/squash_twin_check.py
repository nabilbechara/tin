#!/usr/bin/env python3
"""DEFLATE against Go's compress/flate (#448): Go inflates Tin's raw DEFLATE and Tin inflates
Go's, of an input that uses every length and distance code at levels 1, 6 and 9. Tin's encoder
and decoder share their length and distance tables, so a round trip through Tin alone cannot
catch a wrong entry; Go can."""
import os
import subprocess
import tempfile
from pathlib import Path

from suite import ROOT


def main():
    directory = ROOT / 'bin/ci/squash_twin'
    directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TIN_ROOT=str(ROOT))
    with tempfile.TemporaryDirectory(prefix='squash-', dir=directory) as tmp:
        work = Path(tmp)
        exe = work / 'squash_twin'
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/squash_twin.tin'],
                       check=True, cwd=ROOT, env=env, timeout=120)
        lines = []
        for command in ([str(exe), 'enc', str(work)],
                        ['go', 'run', './bench/ref/squash_twin', str(work)],
                        [str(exe), 'dec', str(work)]):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
            assert result.returncode == 0, f'{command[0]}: exit {result.returncode}: {result.stdout}{result.stderr}'
            lines += result.stdout.splitlines()
        print('\n'.join(lines))
        size = lines[0].split()[1]
        checked = [l for l in lines[1:] if 'inflates' in l]
        assert len(checked) == 6, f'want 6 checks, got {len(checked)}'
        bad = [l for l in checked if ' ok ' + size + ' ' not in l]
        assert not bad, 'DEFLATE disagrees with Go:\n' + '\n'.join(bad)
    print('PASS squash: Go inflates Tin\'s DEFLATE and Tin inflates Go\'s, every length and distance code')


if __name__ == '__main__':
    main()
