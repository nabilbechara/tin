#!/usr/bin/env python3
"""Packages (#146): tin vendor, offline builds from vendor/, tin.lock hashes and capabilities."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def run(argv, cwd, env, offline=False):
    if offline:
        argv = ['unshare', '-rn'] + argv
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


def can_unshare():
    """Whether this host lets an unprivileged process run without any network (Linux)."""
    if not shutil.which('unshare'):
        return False
    try:
        return subprocess.run(['unshare', '-rn', 'true'], capture_output=True, timeout=10).returncode == 0
    except OSError:
        return False


def expect(cond, what, result=None):
    if not cond:
        detail = '' if result is None else f'\nexit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}'
        raise SystemExit(f'FAIL packages: {what}{detail}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='bin/tinc')
    args = parser.parse_args()
    tin = str(ROOT / 'tin')
    out = ROOT / 'bin/ci/packages'
    out.mkdir(parents=True, exist_ok=True)
    # A dead proxy: a build that tried to fetch would fail even where namespaces are not allowed.
    env = dict(os.environ, TIN_ROOT=str(ROOT), LC_ALL='C', HTTP_PROXY='http://127.0.0.1:9',
               HTTPS_PROXY='http://127.0.0.1:9', TMPDIR=str(out))
    offline = can_unshare()
    with tempfile.TemporaryDirectory(prefix='pkg-', dir=out) as tmp:
        work = Path(tmp)
        # Two dependencies, given as local source directories; geo requires units itself.
        write(work / 'src/units/units.tin', 'package units\n\n// Cm converts metres to centimetres.\n'
              'fn Cm(m i64) i64 {\n\treturn m * 100\n}\n')
        write(work / 'src/units/tin.mod', 'module example.com/units\n')
        write(work / 'src/geo/geo.tin', 'package geo\n\nimport "example.com/units"\n\n'
              '// Area is in square centimetres.\nfn Area(w i64, h i64) i64 {\n'
              '\treturn units.Cm(w) * units.Cm(h)\n}\n')
        write(work / 'src/geo/geo_test.tin', 'package geo\n')
        write(work / 'src/geo/tin.mod', 'module example.com/geo\nrequire example.com/units ../units\n')
        app = work / 'app'
        write(app / 'tin.mod', 'module example.com/app\nrequire example.com/geo ../src/geo\n')
        write(app / 'main.tin', 'package main\n\nimport "example.com/geo"\nimport "say"\n\n'
              'fn main() {\n\tsay.Line("area", geo.Area(2, 3))\n}\n')

        result = run(['sh', tin, 'vendor', str(app)], work, env)
        expect(result.returncode == 0, 'tin vendor failed', result)
        vendored = sorted(p.relative_to(app).as_posix() for p in (app / 'vendor').rglob('*') if p.is_file())
        expect(vendored == ['vendor/example.com/geo/geo.tin', 'vendor/example.com/geo/tin.mod',
                            'vendor/example.com/units/tin.mod', 'vendor/example.com/units/units.tin'],
               f'tin vendor copied {vendored} (tests must stay out, requires are transitive)')
        lock = (app / 'tin.lock').read_text()
        want = ''.join(f'{hashlib.sha256((app / f).read_bytes()).hexdigest()} {f}\n' for f in vendored)
        want += 'caps example.com/geo\ncaps example.com/units\n'
        expect(lock == want, f'tin.lock is\n{lock}instead of\n{want}')

        source_tree = work / 'src-copy'
        shutil.copytree(work / 'src', source_tree)
        # The sources are gone and there is no network: the build reads only vendor/.
        shutil.rmtree(work / 'src')
        exe = work / 'app-bin'
        result = run([args.compiler if os.path.isabs(args.compiler) else str(ROOT / args.compiler),
                      '-o', str(exe), 'main.tin'], app, env, offline)
        expect(result.returncode == 0, 'the vendored program did not build offline', result)
        ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        expect(ran.stdout == 'area 60000\n', f'the vendored program printed {ran.stdout!r}')
        result = run(['sh', tin, 'main.tin'], app, env, offline)
        expect(result.returncode == 0 and result.stdout == 'area 60000\n', 'tin main.tin offline', result)

        # One changed byte in a vendored file fails the build, naming the file and both hashes.
        units = app / 'vendor/example.com/units/units.tin'
        before = hashlib.sha256(units.read_bytes()).hexdigest()
        data = bytearray(units.read_bytes())
        data[data.index(b'100')] = ord('9')
        units.write_bytes(bytes(data))
        after = hashlib.sha256(bytes(data)).hexdigest()
        result = run(['sh', tin, 'build', 'main.tin', '-o', str(exe)], app, env, offline)
        want = (f'error E111 LOCK_MISMATCH: tin.lock hash mismatch for vendor/example.com/units/units.tin: '
                f'the lock records sha256 {before}, the file has {after}\n')
        expect(result.returncode == 1 and result.stderr == want, 'a changed vendored byte was not refused', result)

        # A vendored file the lock does not list is refused too.
        units.write_text(units.read_text().replace('* 900', '* 100'))
        write(app / 'vendor/example.com/units/extra.tin', 'package units\n')
        extra = hashlib.sha256(b'package units\n').hexdigest()
        result = run(['sh', tin, 'build', 'main.tin', '-o', str(exe)], app, env, offline)
        want = (f'error E111 LOCK_MISMATCH: tin.lock has no entry for vendor/example.com/units/extra.tin '
                f'(sha256 {extra}); every vendored file must be locked\n')
        expect(result.returncode == 1 and result.stderr == want, 'an unlocked vendored file was accepted', result)
        units.unlink()
        shutil.copytree(source_tree, work / 'src')

        # A dependency that dials without net is refused at its call, naming the path to the entry point.
        write(work / 'src/peek/peek.tin', 'package peek\n\nimport "wire"\n\n'
              '// Up reports whether addr accepts a connection.\nfn Up(addr str) bool {\n'
              '\tlet (c, err) = wire.Dial(addr)\n\tif err != nil {\n\t\treturn false\n\t}\n\tc.Close()\n\treturn true\n}\n')
        write(work / 'src/peek/tin.mod', 'module example.com/peek\n')
        write(app / 'tin.mod', 'module example.com/app\nrequire example.com/geo ../src/geo\n'
              'require example.com/peek ../src/peek\n')
        write(app / 'main.tin', 'package main\n\nimport "example.com/geo"\nimport "example.com/peek"\nimport "say"\n\n'
              'fn main() {\n\tsay.Line("area", geo.Area(2, 3), peek.Up("127.0.0.1:1"))\n}\n')
        result = run(['sh', tin, 'vendor'], app, env)
        expect(result.returncode == 0, 'tin vendor with peek', result)
        expect('caps example.com/peek\n' in (app / 'tin.lock').read_text(), 'the lock lists peek with no capabilities')
        result = run(['sh', tin, 'build', 'main.tin', '-o', str(exe)], app, env, offline)
        want = ('vendor/example.com/peek/peek.tin:7:21: error E804 CAPABILITY: wire.Dial needs capability net '
                '(wire.Dial -> wire.DialTimeout -> wire.resolve), which package example.com/peek does not declare '
                'in its tin.mod (caps: none)\n')
        expect(result.returncode == 1 and result.stderr == want, 'wire.Dial without net was not refused', result)

        # Granting net upstream and vendoring again shows the new capability in the lock, and builds.
        write(work / 'src/peek/tin.mod', 'module example.com/peek\ncaps net\n')
        before = (app / 'tin.lock').read_text()
        result = run(['sh', tin, 'vendor'], app, env)
        expect(result.returncode == 0, 'tin vendor after granting net', result)
        after = (app / 'tin.lock').read_text()
        expect('caps example.com/peek\n' in before and 'caps example.com/peek net\n' in after,
               f'the lock does not show the new capability:\n{after}')
        result = run(['sh', tin, 'build', 'main.tin', '-o', str(exe)], app, env, offline)
        expect(result.returncode == 0, 'peek with net did not build', result)
        ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        expect(ran.stdout == 'area 60000 false\n', f'the program printed {ran.stdout!r}')
        result = run(['sh', tin, 'caps', 'main.tin'], app, env)
        expect(result.returncode == 0 and 'example.com/geo\nexample.com/peek net\nexample.com/units\n' in result.stdout
               and 'main net\n' in result.stdout and 'wire net\n' in result.stdout, 'tin caps', result)

        # A lock whose caps line disagrees with the vendored manifest is refused.
        (app / 'tin.lock').write_text(after.replace('caps example.com/peek net\n', 'caps example.com/peek\n'))
        result = run(['sh', tin, 'build', 'main.tin', '-o', str(exe)], app, env, offline)
        want = ('error E115 LOCK_CAPS: tin.lock says "caps example.com/peek" for example.com/peek, '
                'its manifest declares "caps example.com/peek net" (run tin vendor)\n')
        expect(result.returncode == 1 and result.stderr == want, 'a stale caps line was accepted', result)
    how = 'in a network namespace with no interfaces' if offline else 'with a dead proxy (no unprivileged network namespaces here)'
    print(f'PASS packages: tin vendor, an offline build {how}, tin.lock refusals and capabilities')


if __name__ == '__main__':
    main()
