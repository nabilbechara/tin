#!/usr/bin/env python3
"""Linux clone threads: repeated returning cores, reaped stacks, inherited masks, child faults."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT
from treeutil import copy_lib


def main():
    out = ROOT / 'bin/ci/thread'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='thread-', dir=out) as tmp:
        work = Path(tmp)
        copy_lib(ROOT, work/'lib')
        (work/'lib/threadprobe').mkdir()
        shutil.copy(ROOT/'tools/ci/fixtures/thread_probe.tin', work/'lib/threadprobe/probe.tin')
        exe = work/'threads'
        subprocess.run([str(ROOT/'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/threads.tin'],
                       check=True, cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(work)), timeout=60)
        result = subprocess.run([str(exe)], capture_output=True, timeout=60)
        (out/'threads.log').write_bytes(result.stdout+result.stderr)
        want = b'cores returned: 208\nrecords live: 0\nthreads: 1\nmappings grew: false\n'
        assert result.returncode == 0 and result.stdout == want, result
        fault = subprocess.run([str(exe), 'overflow'], capture_output=True, timeout=60)
        (out/'overflow.log').write_bytes(fault.stdout+fault.stderr)
        # Reported as what it is since #531 (it was "segmentation fault").
        assert fault.returncode == 2 and b'panic: stack overflow' in fault.stderr, fault
    print('PASS 208 returning clone cores: own signal stacks, inherited mask, own errors, '
          'stacks reaped after the kernel clears the tid; a core stack overflow is reported')


if __name__ == '__main__':
    main()
