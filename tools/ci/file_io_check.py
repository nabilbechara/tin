#!/usr/bin/env python3
"""File I/O in request tasks (#357). On Linux, quarry's reads and writes go through each core's
io_uring when the kernel has it, and through helper threads otherwise or with TIN_IO_URING=0; on
macOS through helper threads. Each path runs here (both on Linux): thousands of concurrent reads
on one core all succeed (a core may have 4096 operations out and the next tasks wait for one
instead of failing); reads and writes give the same content and the same faults; reads that never
finish (a FIFO nobody writes) and writes that never start (a FIFO nobody reads) end at the
deadline while the core goes on serving, and release their descriptors once the FIFO's other side
comes; a within deadline and a scope cancel end a parked write. With io_uring, one ring is made
on the core and no helper thread starts for a regular file; with helper threads, as many start
as the cores, at least 4, or TIN_HELPERS. Files under FUSE, virtiofs, 9p and CIFS mounts keep the
helper threads (the mountinfo parsing and path matching are checked through a probe)."""
import ctypes
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from suite import ROOT
import websocket_check as ws


def get(port, path, timeout=60):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())
    data = b''
    while True:
        part = s.recv(65536)
        if not part:
            break
        data += part
    s.close()
    head, _, body = data.partition(b'\r\n\r\n')
    return int(head.split()[1]), body


def threads(pid):
    status = '/proc/%d/status' % pid
    if os.path.exists(status):
        return int([l for l in open(status) if l.startswith('Threads:')][0].split()[1])
    out = subprocess.run(['ps', '-M', '-p', str(pid)], capture_output=True, text=True).stdout.strip().splitlines()
    return len(out) - 1


def own_threads(pid):
    """Threads of the process that are not the kernel's io_uring workers (iou-wrk-*), or None."""
    tasks = '/proc/%d/task' % pid
    if not os.path.isdir(tasks):
        return None
    names = []
    for t in os.listdir(tasks):
        try:
            names.append(open('%s/%s/comm' % (tasks, t)).read().strip())
        except OSError:
            pass
    return len([n for n in names if not n.startswith('iou-')])


def descriptors(pid):
    """The process's open descriptors and how many are io_uring instances (Linux), or None."""
    fds = '/proc/%d/fd' % pid
    if not os.path.isdir(fds):
        return None, None
    links = []
    for fd in os.listdir(fds):
        try:
            links.append(os.readlink('%s/%s' % (fds, fd)))
        except OSError:
            pass
    return len(links), len([l for l in links if 'io_uring' in l])


def uring_available():
    """Whether this kernel lets a process make an io_uring with the operations Tin uses (5.6+)."""
    if not sys.platform.startswith('linux'):
        return False
    try:
        major, minor = (int(x) for x in platform.release().split('.')[:2])
    except ValueError:
        return False
    if (major, minor) < (5, 6):
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    params = (ctypes.c_uint8 * 120)()
    fd = libc.syscall(425, 4, params)  # io_uring_setup, the same number on arm64 and x86-64
    if fd < 0:
        return False
    os.close(fd)
    return True


def start(exe, cores, **env):
    port = ws.free_port()
    p = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, PORT=str(port), TIN_CORES=str(cores), **env))
    for _ in range(100):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=.1).close()
            return p, port
        except OSError:
            assert p.poll() is None, 'server exited at startup'
            time.sleep(.05)
    raise AssertionError('server did not start')


def eventually(check, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(.02)
    return check()


def expected_check(linux):
    lines = ['size %d: write ok, read ok, same true' % n
             for n in (0, 1, 511, 512, 513, 4095, 4096, 4097, 65536, 3145731)]
    lines += [
        'append: ok ok ok ok ok true',
        'truncate: ok ok ok short',
        'missing: open D/missing: no such file or directory',
        'directory: read D: is a directory',
        'write into a missing directory: open D/nodir/x: no such file or directory',
        'write a directory: open D: is a directory',
        'append to a directory: open D: is a directory',
        'proc: ok true' if linux else 'proc: none',
        '500 tasks: bad 0 ',
    ]
    return '\n'.join(lines) + '\n'


def concurrent_reads(exe, name, env, q, uring):
    """More concurrent reads than the 4096 operations one core may have out: every one succeeds."""
    p, port = start(exe, 1, TIN_DEADLINE_MS='120000', **env)
    try:
        before = own_threads(p.pid)
        for n in (100, 5000, 9000):
            t0 = time.monotonic()
            status, body = get(port, '/files?n=%d%s' % (n, q), 120)
            assert (status, body) == (200, b'ok=%d bad=0 first=' % n), (name, n, status, body)
            print('%s: %d concurrent file reads on one core: all ok in %.2f s' % (name, n, time.monotonic() - t0))
        _, rings = descriptors(p.pid)
        if rings is not None:
            assert rings == (1 if uring else 0), (name, 'io_uring instances', rings)
        if uring:
            after = own_threads(p.pid)
            assert after == before, (name, 'helper threads started for a regular file', before, after)
            print('%s: the reads went through one ring on the core; no helper thread started' % name)
        elif rings is not None:
            print('%s: no io_uring instance was made' % name)
    finally:
        p.kill()
        p.wait()


def contents(exe, name, env, out, linux):
    """Reads and writes of many sizes, appends, truncation and faults: the same on every path."""
    p, port = start(exe, 1, **env)
    try:
        with tempfile.TemporaryDirectory(prefix='check-', dir=out) as d:
            status, body = get(port, '/check?dir=' + d, 120)
            assert status == 200 and body.decode() == expected_check(linux), (name, status, body.decode())
        print('%s: contents of 0 B to 3 MiB, appends, truncation, faults, /proc and 500 tasks at once agree' % name)
    finally:
        p.kill()
        p.wait()


def fifo_reads(exe, name, env, out):
    """Reads that never finish (a FIFO nobody writes to): the tasks past 4096 operations wait,
    all end at the request's deadline, and the core goes on serving."""
    fifo = out / 'fifo'
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(fifo)
    p, port = start(exe, 1, TIN_HELPERS='2', TIN_DEADLINE_MS='1500', **env)
    try:
        t0 = time.monotonic()
        status, body = get(port, '/files?n=5000&file=' + str(fifo), 30)
        took = time.monotonic() - t0
        assert (status, body) == (200, b'ok=0 bad=5000 first=deadline exceeded') and 1.2 < took < 6, (name, status, body[:80], took)
        t0 = time.monotonic()
        assert get(port, '/ok') == (200, b'ok')
        assert time.monotonic() - t0 < 1, 'the core did not serve after the waiting tasks ended'
        print('%s: 5000 reads of a FIFO nobody writes: every one ends with "deadline exceeded" after %.1f s, and /ok answers at once' % (name, took))
    finally:
        p.kill()
        p.wait()


def fifo_writes(exe, name, env, out, data):
    """Writes that never start (a FIFO nobody reads): 5000 tasks end at the deadline (those past
    4096 operations waited for room); once a reader comes the late opens finish, their descriptors
    are closed, and the core reads files again."""
    fifo = out / 'wfifo'
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(fifo)
    p, port = start(exe, 1, TIN_HELPERS='2', TIN_DEADLINE_MS='1500', **env)
    reader = None
    try:
        # Make the ring or the helper threads first, so the descriptor count below is the base.
        assert get(port, '/files?n=1&file=' + str(data)) == (200, b'ok=1 bad=0 first=')
        assert get(port, '/writes?n=1&file=' + str(out / 'written')) == (200, b'ok=1 bad=0 first=')
        base, _ = descriptors(p.pid)
        t0 = time.monotonic()
        status, body = get(port, '/writes?n=5000&file=' + str(fifo), 30)
        took = time.monotonic() - t0
        assert (status, body) == (200, b'ok=0 bad=5000 first=deadline exceeded') and 1.2 < took < 6, (name, status, body[:80], took)
        t0 = time.monotonic()
        assert get(port, '/ok') == (200, b'ok')
        assert time.monotonic() - t0 < 1, 'the core did not serve after the waiting tasks ended'
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)

        def settled():
            try:
                while os.read(reader, 65536):
                    pass
            except BlockingIOError:
                pass
            n, _ = descriptors(p.pid)
            return n is None or n == base
        assert eventually(settled), (name, 'descriptors of the late opens were not closed', base, descriptors(p.pid))
        status, body = get(port, '/files?n=100&file=' + str(data), 30)
        assert (status, body) == (200, b'ok=100 bad=0 first='), (name, status, body)
        print('%s: 5000 writes to a FIFO nobody reads end with "deadline exceeded" after %.1f s; /ok answers '
              'at once; when a reader comes the late opens are closed and reads work again' % (name, took))
    finally:
        if reader is not None:
            os.close(reader)
        p.kill()
        p.wait()


def parked(exe, name, env, out):
    """A write parked on a FIFO ends at a within deadline and at a scope cancel."""
    fifo = out / 'pfifo'
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(fifo)
    p, port = start(exe, 1, **env)
    reader = None
    try:
        status, body = get(port, '/park?file=' + str(fifo), 30)
        assert (status, body) == (200, b'within: deadline exceeded true; cancel: canceled: stop (scope: canceled: stop)'), (name, status, body)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        assert get(port, '/ok') == (200, b'ok')
        print('%s: a parked write ends with "deadline exceeded" at a 300 ms within and "canceled: stop" at a scope cancel' % name)
    finally:
        if reader is not None:
            os.close(reader)
        p.kill()
        p.wait()


def helper_threads(exe, q):
    """Helper threads: the larger of 4 and the cores, or TIN_HELPERS."""
    counts = {}
    for cores, helpers in ((2, '3'), (2, '9'), (8, ''), (1, '')):
        env = {'TIN_HELPERS': helpers} if helpers else {}
        p, port = start(exe, cores, TIN_IO_URING='0', **env)
        try:
            # The listener takes connections before the other cores and the monitor thread
            # start; a served request means every core has started (hearth's start barrier).
            assert get(port, '/ok') == (200, b'ok')
            before = threads(p.pid)
            assert get(port, '/files?n=20' + q)[0] == 200
            time.sleep(.3)
            counts[(cores, helpers)] = threads(p.pid) - before
        finally:
            p.kill()
            p.wait()
    assert counts == {(2, '3'): 3, (2, '9'): 9, (8, ''): 8, (1, ''): 4}, counts
    print('helper threads started: TIN_HELPERS=3 -> 3, 9 -> 9; 8 cores -> 8; 1 core -> 4')


MOUNTS = """slow: [/mnt/s3]
slow: [/mnt/my files]
slow: [/srv/share]
slow: [/src]
slow: [/9]
slow: [/blk]
/mnt/s3: true
/mnt/s3/a.txt: true
/mnt/s3x/a.txt: false
/mnt/my files/b: true
/srv/share/c: true
/src/lib/x.tin: true
/data/d: false
/tmp/e: false
/9/f: true
/blk/g: true
/fusex/h: false
/: false
a slow root holds every path: true
empty mountinfo: 0
"""


def mounts(compiler, out):
    """Which mounts keep the helper threads: FUSE (fuse, fuse.*, fuseblk), virtiofs, 9p and CIFS
    mount points from mountinfo, octal escapes undone, matched by whole path components."""
    with tempfile.TemporaryDirectory(prefix='mounts-', dir=out) as tmp:
        lib = Path(tmp) / 'lib'
        shutil.copytree(ROOT / 'lib', lib)
        with (lib / 'quarry/quarry.tin').open('a') as f:
            f.write('\n' + (ROOT / 'tools/ci/fixtures/mounts_probe.tin').read_text())
        exe = Path(tmp) / 'mounts'
        subprocess.run([compiler, '-o', str(exe), str(ROOT / 'tools/ci/fixtures/mounts.tin')],
                       cwd=ROOT, env=dict(os.environ, TIN_ROOT=tmp), check=True)
        got = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60).stdout
        assert got == MOUNTS, got
    print('slow mounts: FUSE, virtiofs, 9p and CIFS mount points are found and matched by path')


def main():
    out = ROOT / 'bin/ci/files'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'files'
    compiler = os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc'))
    subprocess.run([compiler, '-o', str(exe), 'tools/ci/fixtures/files.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    mounts(compiler, out)
    # The files live in the system's temporary directory: a checkout can be on a FUSE share
    # (Docker Desktop), whose files keep the helper threads.
    work = Path(tempfile.mkdtemp(prefix='tin-files-'))
    try:
        run(exe, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run(exe, out):
    data = out / 'data.txt'
    data.write_text('hello from a helper thread\n')
    q = '&file=' + str(data)
    linux = sys.platform.startswith('linux')

    uring = uring_available()
    if linux and not uring:
        assert os.environ.get('TIN_REQUIRE_IO_URING') != '1', 'TIN_REQUIRE_IO_URING=1 but this kernel refuses io_uring'
        print('io_uring: not available on this kernel; only the helper threads are checked')
    modes = [('io_uring', {}, True)] if uring else []
    modes.append(('helper threads', {'TIN_IO_URING': '0'}, False))
    for name, env, ring in modes:
        concurrent_reads(exe, name, env, q, ring)
        contents(exe, name, env, out, linux)
        fifo_reads(exe, name, env, out)
        fifo_writes(exe, name, env, out, data)
        parked(exe, name, env, out)
    helper_threads(exe, q)


if __name__ == '__main__':
    main()
