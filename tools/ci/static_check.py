#!/usr/bin/env python3
"""Linux static executables: no PT_INTERP or PT_DYNAMIC, a Tin _start, and an empty root."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from suite import ROOT

PT_DYNAMIC, PT_INTERP = 2, 3
PROBE = 'fn main(argc, argv) { let envp = argv + 8 * (argc + 1); return argc * 10 + load8(envp[0]) - 64; }\n'
ENV_PROGRAM = """package main

import "quarry"
import "say"

func main() {
	say.Line("a", quarry.Getenv("STATIC_A"))
	err := quarry.Setenv("STATIC_B", "two")
	v, ok := quarry.LookupEnv("STATIC_B")
	say.Line("b", v, ok, err)
	err = quarry.Unsetenv("STATIC_A")
	v, ok = quarry.LookupEnv("STATIC_A")
	say.Line("unset", v == "", ok, err)
}
"""
ENV_WANT = 'a one\nb two true <nil>\nunset true false <nil>\n'


def segments(path):
    data = Path(path).read_bytes()
    assert data[:4] == b'\x7fELF', path
    phoff = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    return [struct.unpack_from('<I', data, phoff + i * size)[0] for i in range(count)]


def assert_static(path):
    kinds = segments(path)
    assert PT_INTERP not in kinds and PT_DYNAMIC not in kinds, (path, kinds)


def run_in(root, exe, args, env):
    """Runs exe inside an otherwise empty root directory when chroot is available."""
    shutil.copy(exe, root / 'prog')
    chroot = shutil.which('chroot') or '/usr/sbin/chroot'
    cmd = [chroot, str(root), '/prog'] + args
    if os.geteuid() != 0:
        if shutil.which('sudo') is None or subprocess.run(['sudo', '-n', 'true'],
                                                           capture_output=True).returncode != 0:
            return None
        cmd = ['sudo', '-n', 'env', '-i'] + [f'{k}={v}' for k, v in env.items()] + cmd
        env = None
    return subprocess.run(cmd, capture_output=True, timeout=30, env=env)


def main(programs=()):
    out = ROOT / 'bin/ci/static'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='static-', dir=out) as tmp:
        work = Path(tmp)
        source = work / 'probe.tin'
        source.write_text(PROBE)
        for target in ('linux-arm64', 'linux-amd64'):
            exe = work / f'probe-{target}'
            subprocess.run([str(ROOT / 'bin/tinc'), '-target', target, '-o', str(exe), str(source)],
                           check=True, timeout=60)
            assert_static(exe)
        for name in programs:
            exe = work / Path(name).stem
            subprocess.run([str(ROOT / 'tin'), 'build', str(ROOT / name), '-o', str(exe)],
                           check=True, timeout=120)
            assert_static(exe)
        exe = work / ('probe-linux-' + ('arm64' if os.uname().machine in ('aarch64', 'arm64') else 'amd64'))
        env = {'X': '1'}
        result = subprocess.run([str(exe), 'a', 'b'], env=env, timeout=30)
        assert result.returncode == 30 + ord('X') - 64, result
        root = work / 'root'
        root.mkdir()
        jailed = run_in(root, exe, ['a'], env)
        if jailed is None:
            print('NOTE no chroot permission here: the empty-root run is skipped')
        else:
            assert jailed.returncode == 20 + ord('X') - 64, jailed
        # A strict program that reads and changes its environment, and the compiler itself,
        # link without libc too (#125): getenv, setenv and getauxval are the runtime's.
        envprog = work / 'env.tin'
        envprog.write_text(ENV_PROGRAM)
        for target in ('linux-arm64', 'linux-amd64'):
            exe = work / f'env-{target}'
            subprocess.run([str(ROOT / 'bin/tinc'), '-target', target, '-o', str(exe), str(envprog)],
                           check=True, timeout=60, env=dict(os.environ, TIN_ROOT=str(ROOT)))
            assert_static(exe)
        exe = work / ('env-linux-' + ('arm64' if os.uname().machine in ('aarch64', 'arm64') else 'amd64'))
        got = subprocess.run([str(exe)], env={'STATIC_A': 'one'}, capture_output=True, text=True, timeout=30)
        assert got.returncode == 0 and got.stdout == ENV_WANT, got
        if os.uname().sysname == 'Linux':
            # bin/tinc comes from the checked-in seed, which still links libc until the seed
            # refresh (#125); the compiler that compiled itself (make bootstrap) is static.
            built = ROOT / 'bin/s3/tinc'
            assert built.exists(), 'run make bootstrap first: bin/s3/tinc is the compiler it builds'
            assert_static(built)
    print('PASS static linux-arm64/amd64 images (no PT_INTERP, no PT_DYNAMIC); _start passes argc, argv and envp'
          + ('' if jailed is None else '; runs in an empty root')
          + '; a program using getenv/setenv and the compiler itself are static')


if __name__ == '__main__':
    main()
