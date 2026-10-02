#!/usr/bin/env python3
"""Test an extracted release from another directory, then its Linux builder/runtime image."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=180, **kwargs)


def check(archive, docker=False, image=None, skip_native=False):
    with tempfile.TemporaryDirectory(prefix='tin-release-') as directory:
        work = Path(directory)
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            tar.extractall(work)
        tree, = [p for p in work.iterdir() if p.is_dir()]
        version = (tree / 'VERSION').read_text().strip()
        env = dict(os.environ)
        env.pop('TIN_ROOT', None)
        source = work / 'hello.tin'
        source.write_text('package main\nimport "say"\nfunc main() { say.Line("release works") }\n')
        if not skip_native:
            result = run([str(tree / 'tin'), str(source)], cwd=work, env=env, capture_output=True, text=True)
            assert result.stdout == 'release works\n', result.stdout
            # The standalone tinc symlink must also find lib/ without TIN_ROOT.
            link = work / 'tinc'
            link.symlink_to(tree / 'bin/tinc')
            run([str(link), '-o', str(work / 'hello'), str(source)], cwd=work, env=env)
            result = run([str(work / 'hello')], capture_output=True, text=True)
            assert result.stdout == 'release works\n'
            run(['make', 'bootstrap'], cwd=tree, env=env, stdout=subprocess.DEVNULL)
            mirror = work / 'releases' / ('v' + version)
            mirror.mkdir(parents=True)
            shutil.copy2(archive, mirror / archive.name)
            shutil.copy2(archive.with_suffix('.gz.sha256'), mirror / 'SHA256SUMS')
            installed = work / 'installed tin'
            run(['sh', str(ROOT / 'install.sh'), version], cwd=work,
                env=dict(env, TIN_RELEASE_BASE_URL=mirror.parent.as_uri(), TIN_INSTALL_DIR=str(installed)))
            result = run([str(installed / 'bin/tin'), str(source)], cwd=work, capture_output=True, text=True)
            assert result.stdout == 'release works\n'
            print('PASS relocated archive, standalone compiler, self-hosting, verified installer', flush=True)
        if not docker:
            return
        context = work / 'context'
        context.mkdir()
        shutil.move(str(tree), context / 'tin')
        shutil.copy2(ROOT / 'docker/builder.Dockerfile', context / 'Dockerfile')
        builder = image or 'tin-builder:distribution-check'
        runtime = 'tin-api:distribution-check'
        run(['docker', 'build', '--build-arg', 'TIN_VERSION=' + version, '-t', builder, str(context)])
        run(['docker', 'run', '--rm', '-v', str(work) + ':/src', builder, 'hello.tin'])
        run(['docker', 'build', '--build-arg', 'TIN_BUILDER=' + builder, '-f',
             'examples/k8s/Dockerfile', '-t', runtime, '.'], cwd=ROOT)
        # Docker chooses a free host port; the user's port 8080 remains untouched.
        cid = run(['docker', 'run', '-d', '--rm', '--cpus=2', '--memory=256m', '-p', '127.0.0.1::8080',
                   '-e', 'TIN_GRACE=1', runtime], capture_output=True, text=True).stdout.strip()
        try:
            port = run(['docker', 'port', cid, '8080/tcp'], capture_output=True, text=True).stdout.strip().rsplit(':', 1)[1]
            url = 'http://127.0.0.1:' + port
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + '/healthz', timeout=1) as response:
                        assert response.read() == b'ok'
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(.05)
            else:
                raise AssertionError('Container never became healthy')
            with urllib.request.urlopen(url + '/json', timeout=2) as response:
                assert b'Hello, World!' in response.read()
            run(['docker', 'exec', cid, 'sh', '-c', 'test ! -e /opt/tin && test "$(id -u)" = 10001'])
        finally:
            run(['docker', 'stop', '-t', '5', cid], stdout=subprocess.DEVNULL)
        print('PASS builder, source-to-runtime image, HTTP, non-root user, shutdown', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--docker', action='store_true')
    parser.add_argument('--image')
    parser.add_argument('--skip-native', action='store_true', help='Cross-built local container test only; CI tests native archives')
    args = parser.parse_args()
    if args.skip_native and not args.docker:
        parser.error('--skip-native requires --docker')
    check(args.archive, args.docker, args.image, args.skip_native)
