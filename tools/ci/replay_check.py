#!/usr/bin/env python3
"""Replay tapes (#241): rt_effect records results and faults, and a replay serves them without
running the live call, keeps fault identity, and stops at the first divergence."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT

EXPECTED = '''\
record first: one true ran 1
record fault: redis GET: deadline exceeded true ran 2
record word: 42
record bytes: abc
replay first: one true
replay fault: redis GET: deadline exceeded true
replay word: 42
replay bytes: abc
bodies run while replaying: 0 left: 0 diverged: false
past the end: replay: divergence at effect 4: got test@1 "third", recorded nothing more
sticky: true ran 0
mismatch: replay: divergence at effect 0: got test@1 "other", recorded test@1 "first"
live kind: fresh ran 1
secret handle unkeyed: tin-secret:unkeyed
'''


def main():
    out = ROOT / 'bin/ci/replay'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='replay-', dir=out) as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / 'lib', work / 'lib')
        probe = work / 'lib/replayprobe'
        probe.mkdir()
        shutil.copy(ROOT / 'tools/ci/fixtures/replay_probe.tin', probe / 'probe.tin')
        exe = work / 'replay'
        env = dict(os.environ, TIN_ROOT=str(work))
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/replay.tin'],
                       check=True, env=env, cwd=ROOT, timeout=60)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30, cwd=ROOT)
        (out / 'replay.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result
        if result.stdout != EXPECTED:
            raise SystemExit('FAIL replay tapes: output differs\n--- want\n' + EXPECTED +
                             '--- got\n' + result.stdout)
    print('PASS replay tapes: record, replay without live calls, fault identity, divergence, live kinds')


if __name__ == '__main__':
    main()
