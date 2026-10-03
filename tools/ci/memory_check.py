#!/usr/bin/env python3
"""Memory primitives, cross-core returns, and deterministic allocation failure (#178)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT


def main():
    out = ROOT / 'bin/ci/memory'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='memory-', dir=out) as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / 'lib', work / 'lib')
        probe = work / 'lib/memoryprobe'
        probe.mkdir()
        shutil.copy(ROOT / 'tools/ci/fixtures/memory_probe.tin', probe / 'probe.tin')
        exe = work / 'memory'
        env = dict(os.environ, TIN_ROOT=str(work))
        subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe),
                        'tools/ci/fixtures/memory.tin'], check=True, env=env, cwd=ROOT,
                       timeout=60)
        reference = subprocess.run(['go', 'run', './bench/ref/memory'], check=True,
                                   capture_output=True, cwd=ROOT, timeout=60).stdout
        result = subprocess.run([str(exe)], capture_output=True, timeout=30, cwd=ROOT)
        (out / 'memory.log').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0 and result.stdout == reference, result
        # Injection is process-wide and counts allocations/mappings, including startup.
        # It is enabled only by the explicit test flag; ordinary environments ignore it.
        for after in range(41):
            result = subprocess.run([str(exe)], capture_output=True, timeout=10,
                env=dict(env, TIN_ALLOC_TEST='1', TIN_FAIL_ALLOC_AFTER=str(after)), cwd=ROOT)
            assert result.returncode == 2, (after, result.returncode, result.stderr)
            assert b'out of memory (' in result.stderr and b' bytes)\n' in result.stderr, (
                after, result.stderr)
        result = subprocess.run([str(exe)], capture_output=True, timeout=30,
            env=dict(env, TIN_ALLOC_TEST='0', TIN_FAIL_ALLOC_AFTER='0'), cwd=ROOT)
        assert result.returncode == 0 and result.stdout == reference, result
        print('PASS memory: alignments, overlap, guard pages, zeroing, realloc, 1000 cross-core returns')
        print('PASS #178: 41 deterministic allocation/mapping failures; test flag gates injection')


if __name__ == '__main__':
    main()
