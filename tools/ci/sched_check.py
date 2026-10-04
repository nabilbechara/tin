#!/usr/bin/env python3
"""Scheduling replay (#243, notes/interface_replay.md section 7): a recording select appends
its winning arm as sched.select@1 keyed by its site; a replaying select checks, watches and
waits for the recorded arm only, so a select that raced a timer takes the recorded branch
under any live timing. A request's tasks resume in the recorded order (sched.resume@1), and
a task whose effect is not the next record waits for its turn; when no task can go on, the
replay diverges instead of hanging. The fixture counts branches, it never times them."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT

EXPECTED = '''\
no tape: lane
lane recorded: lane [sched.resume@1  1 sched.resume@1  1 sched.resume@1  0 sched.select@1 sched.tin:17 0]
lane live now: timer replayed: 20 of 20 took lane clean: 20
timer recorded: timer [sched.resume@1  1 sched.resume@1  0 sched.select@1 sched.tin:17 1 sched.resume@1  1 sched.resume@1  0]
timer live now: lane replayed: 20 of 20 took timer clean: 20
race: 30 of 30 recordings replayed their branch under both timings
deadline recorded: fault deadline exceeded [sched.resume@1  1 sched.resume@1  0 sched.select@1 sched.tin:17 2 sched.resume@1  1 sched.resume@1  0]
deadline replayed: fault deadline exceeded diverged: false
order recorded: ab ba live swapped: ba
order replayed: 20 of 20 gave ab and 20 of 20 gave ba
effects recorded: v:b v:a  [sched.resume@1  1 sched.resume@1  2 test@1 b test@1 a sched.resume@1  0]
effects replayed: 20 of 20 gave v:b v:a 
effects diverged: fault replay: divergence at effect 2: got test@1 "a", recorded test@1 "b" | replay: divergence at effect 2: got test@1 "a", recorded test@1 "b"
old tape: v:a lane diverged: false left: 0
other site: other replay: divergence at effect 0: select at sched.tin:30 has no record
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
    print('PASS scheduling replay: select winners and resume order replayed under the opposite timing, effects in their recorded order, deadline exits, divergence')


if __name__ == '__main__':
    main()
