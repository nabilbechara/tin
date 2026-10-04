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

fn main() {
	say.Line("a", quarry.Getenv("STATIC_A"))
	mut err = quarry.Setenv("STATIC_B", "two")
	mut (v, ok) = quarry.LookupEnv("STATIC_B")
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


def run_in_containers(work, exe):
    """Runs exe in Alpine (musl, no glibc) and in an image built FROM scratch (no files at all)."""
    docker = shutil.which('docker')
    if docker is None or subprocess.run([docker, 'info'], capture_output=True).returncode != 0:
        assert os.environ.get('CI') != 'true', 'CI needs docker for the Alpine and FROM scratch runs'
        return False
    image = work / 'image'
    image.mkdir()
    shutil.copy(exe, image / 'prog')
    (image / 'Dockerfile').write_text('FROM scratch\nCOPY prog /prog\nENTRYPOINT ["/prog"]\n')
    tag = 'tin-static-check:' + exe.name
    subprocess.run([docker, 'build', '-q', '-t', tag, str(image)], check=True, capture_output=True, timeout=300)
    runs = {
        'scratch': [docker, 'run', '--rm', '-e', 'STATIC_A=one', tag],
        'alpine': [docker, 'run', '--rm', '-e', 'STATIC_A=one', '-v', f'{image}:/w:ro', 'alpine:3.20', '/w/prog'],
    }
    for name, cmd in runs.items():
        got = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        assert got.returncode == 0 and got.stdout == ENV_WANT, (name, got)
    subprocess.run([docker, 'rmi', '-f', tag], capture_output=True)
    return True


def symbols(work, envprog, machine):
    """#351: a Linux executable carries a symbol table that nm and addr2line read (so perf and
    gdb name its functions); -strip leaves it and the section headers out."""
    nm, addr2line = shutil.which('nm'), shutil.which('addr2line')
    if nm is None or addr2line is None:
        assert os.environ.get('CI') != 'true', 'CI needs binutils for the symbol check'
        return False
    env = dict(os.environ, TIN_ROOT=str(ROOT))
    exe, bare = work / 'symbols', work / 'symbols-stripped'
    subprocess.run([str(ROOT / 'bin/tinc'), '-target', 'linux-' + machine, '-o', str(exe), str(envprog)],
                   check=True, timeout=60, env=env)
    subprocess.run([str(ROOT / 'bin/tinc'), '-strip', '-target', 'linux-' + machine, '-o', str(bare), str(envprog)],
                   check=True, timeout=60, env=env)
    listed = subprocess.run([nm, str(exe)], capture_output=True, text=True, timeout=30).stdout
    names = {line.split()[-1]: line.split()[0] for line in listed.splitlines() if ' T ' in line}
    assert 'main.main' in names and 'quarry.Getenv' in names, sorted(names)[:20]
    found = subprocess.run([addr2line, '-f', '-e', str(exe), '0x' + names['main.main']],
                           capture_output=True, text=True, timeout=30).stdout
    assert found.splitlines()[0] == 'main.main', found
    gone = subprocess.run([nm, str(bare)], capture_output=True, text=True, timeout=30)
    assert gone.stdout == '' and 'no symbols' in gone.stderr, gone
    assert bare.stat().st_size < exe.stat().st_size
    return True


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
        contained = False
        named = False
        if os.uname().sysname == 'Linux':
            # The compiler is static at every stage: the checked-in seed, the bin/tinc it builds
            # and the compiler that compiled itself (make bootstrap).
            machine = 'arm64' if os.uname().machine in ('aarch64', 'arm64') else 'amd64'
            for compiler in (ROOT / f'seed/tinc-linux-{machine}', ROOT / 'bin/tinc', ROOT / 'bin/s3/tinc'):
                assert compiler.exists(), f'{compiler} is missing: run make bootstrap first'
                assert_static(compiler)
            contained = run_in_containers(work, exe)
            named = symbols(work, envprog, machine)
    print('PASS static linux-arm64/amd64 images (no PT_INTERP, no PT_DYNAMIC); _start passes argc, argv and envp'
          + ('' if jailed is None else '; runs in an empty root')
          + '; a program using getenv/setenv and the compiler (seed, bin/tinc, stage 3) are static'
          + ('; the program runs on Alpine and FROM scratch' if contained else '')
          + ('; nm and addr2line name its functions, and -strip removes the symbols' if named else ''))


if __name__ == '__main__':
    main()
