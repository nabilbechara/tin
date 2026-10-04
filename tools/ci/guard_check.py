#!/usr/bin/env python3
"""A guard runs resource-cleanup callbacks on a panic (#142, design_semantics section 3).

A probe appended to a temporary copy of lib/tide registers rt_task_cleanup callbacks. Inside a
spawned task, the guard's callee registers one and panics: the guard runs the callee's defer and
that callback before its value is the fault.Panic fault; a callback the task registered before
the guard stays until the task ends.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from suite import ROOT

WANT = 'defer;fault true;cleaned 2;after 0; task end cleaned 21\n'


def main():
    out = ROOT / 'bin/ci/guard'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='guard-', dir=out) as tmp:
        directory = Path(tmp)
        shutil.copytree(ROOT / 'lib', directory / 'lib')
        fixtures = ROOT / 'tools/ci/fixtures'
        with (directory / 'lib/tide/tide.tin').open('a') as f:
            f.write('\n' + (fixtures / 'guard_probe.tin').read_text())
        exe = directory / 'guard'
        subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), str(fixtures / 'guard_cleanup.tin')],
                       cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(directory)), check=True)
        run = subprocess.run([str(exe)], capture_output=True, timeout=20)
        got = run.stdout.decode(errors='replace')
        assert run.returncode == 0, (run.returncode, got, run.stderr)
        assert got == WANT, got
        err = run.stderr.decode(errors='replace')
        assert err.count('panic: index out of range [5] with length 3') == 1, err
    print('PASS guard: defers and cleanup callbacks run before the fault; outer callbacks wait for the task end')


if __name__ == '__main__':
    main()
