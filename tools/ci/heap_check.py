#!/usr/bin/env python3
"""Long-lived blocks above 4 KiB (#345): size classes reach 256 KiB (about 25% apart) and are served
from slabs, blocks up to 4 MiB above that keep their mappings for reuse, so churn neither
fragments the address space (/proc/self/maps, the default vm.max_map_count is 65530) nor wastes
a page-rounded mapping per value. Fixture blocks.tin prints what hearth.HeapStats and the process
report; the /proc figures are Linux only."""
import os
import subprocess

from suite import ROOT

MiB = 1 << 20


def run(exe, mode, size, count):
    out = subprocess.run([str(exe), mode, str(size), str(count)], capture_output=True, text=True,
                         check=True).stdout.strip().splitlines()
    rows = []
    for line in out:
        words = line.split()
        rows.append(dict(zip(words[0::2], words[1::2])))
    return rows


def main():
    work = ROOT / 'bin/ci/heap'
    work.mkdir(parents=True, exist_ok=True)
    exe = work / 'blocks'
    compiler = os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc'))
    subprocess.run([compiler, '-o', str(exe), 'tools/ci/fixtures/blocks.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    linux = os.path.exists('/proc/self/maps')

    # 5 KB values kept and overwritten: served from a slab, no mapping per value.
    (churn,) = run(exe, 'churn', 5000, 100000)
    print('100000 x 5000 B kept and overwritten: %s ms, %s slab bytes, %s mappings in all, %s in /proc' %
          (churn['ms'], churn['slabs'], churn['heapmaps'], churn['maps']))
    assert int(churn['heapmaps']) < 20, churn
    assert int(churn['slabs']) <= 2 * MiB, churn

    # 60000 distinct 5 KB values: a class of 5120 bytes each (not 8192), the address space
    # stays unfragmented when half of them are deleted.
    fill, deleted, refill = run(exe, 'fill', 5000, 60000)
    print('60000 x 5000 B kept: rss %d MiB, %s mappings; half deleted: %s mappings; kept again: rss %d MiB' %
          (int(fill['rss']) >> 20, fill['maps'], deleted['maps'], int(refill['rss']) >> 20))
    assert int(fill['slabs']) >= 60000 * 5120, fill
    assert int(fill['slabs']) <= 60000 * 5120 * 1.1, fill
    assert int(refill['slabs']) <= int(fill['slabs']) * 1.05, ('memory freed by the deletes is reused', fill, refill)
    if linux:
        assert int(fill['rss']) < 60000 * 5120 * 1.3, fill
        assert int(deleted['maps']) < 1000 and int(refill['maps']) < 1000, (deleted, refill)

    # Blocks above 256 KiB reuse their mappings.
    (big,) = run(exe, 'large', 300000, 20000)
    print('20000 x 300000 B made and dropped: %s ms, %s mappings in all (%s in /proc)' %
          (big['ms'], big['heapmaps'], big['maps']))
    assert int(big['heapmaps']) < 20, big
    (huge,) = run(exe, 'large', 8000000, 50)
    print('50 x 8000000 B made and dropped: %s mappings in all (above 4 MiB each is unmapped when dropped)' %
          huge['heapmaps'])
    assert int(huge['heapmaps']) < 20, huge
    if linux:
        assert int(big['maps']) < 1000 and int(huge['maps']) < 1000, (big, huge)


if __name__ == '__main__':
    main()
