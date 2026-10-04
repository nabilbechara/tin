#!/usr/bin/env python3
"""Scheduling replay (#243, notes/interface_replay.md section 7): a recording select appends
its winning arm as sched.select@1 keyed by its site; a replaying select checks, watches and
waits for the recorded arm only, so a select that raced a timer takes the recorded branch
under any live timing. The fixture counts branches, it never times them."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT

EXPECTED = '''\
no tape: lane
lane recorded: lane [sched.select@1 sched.tin:17 0]
lane live now: timer replayed: 20 of 20 took lane clean: 20
timer recorded: timer [sched.select@1 sched.tin:17 1]
timer live now: lane replayed: 20 of 20 took timer clean: 20
race: 30 of 30 recordings replayed their branch under both timings
deadline recorded: fault deadline exceeded [sched.select@1 sched.tin:17 2]
deadline replayed: fault deadline exceeded diverged: false
other site: other replay: divergence at effect 0: got sched.select@1 "sched.tin:30", recorded sched.select@1 "sched.tin:17"
'''


def main():
    out = ROOT / 'bin/ci/sched'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sched-', dir=out) as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / 'lib', work / 'lib')
        probe = work / 'lib/schedprobe'
        probe.mkdir()
        shutil.copy(ROOT / 'tools/ci/fixtures/sched_probe.tin', probe / 'probe.tin')
        exe = work / 'sched'
        env = dict(os.environ, TIN_ROOT=str(work))
        subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/sched.tin'],
                       check=True, env=env, cwd=ROOT, timeout=60)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, cwd=ROOT)
        (out / 'sched.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result
        if result.stdout != EXPECTED:
            raise SystemExit('FAIL scheduling replay: output differs\n--- want\n' + EXPECTED +
                             '--- got\n' + result.stdout)
    print('PASS scheduling replay: select winners recorded by site, replayed under the opposite timing, deadline exits, divergence')


if __name__ == '__main__':
    main()
