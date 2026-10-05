#!/usr/bin/env python3
"""Compiler root discovery through spaced/unicode trees and symlink launchers."""
import argparse
import ctypes
import platform
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from suite import ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',default='bin/tinc')
    args=parser.parse_args()
    compiler=(ROOT/args.compiler).resolve()
    out=ROOT/'bin/ci/paths';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='paths-',dir=out) as tmp:
        work=Path(tmp)
        tree=work/'Tin tree with spaces λ'
        (tree/'bin').mkdir(parents=True)
        shutil.copytree(ROOT/'lib',tree/'lib')
        shutil.copy(compiler,tree/'bin/tinc')
        (work/'tree link').symlink_to(tree.name,target_is_directory=True)
        (work/'launcher').symlink_to('tree link/bin/tinc')
        (work/'launcher chain').symlink_to('launcher')
        source=work/'hello.tin'
        source.write_text('package main\nimport "say"\nfn main() { say.Line("path discovery λ") }\n')
        env=dict(os.environ)
        env.pop('TIN_ROOT',None)
        unrelated=work/'unrelated';unrelated.mkdir()
        for i,path in enumerate([tree/'bin/tinc',work/'launcher',work/'launcher chain',work/'tree link/bin/../bin/tinc']):
            exe=work/f'hello{i}'
            subprocess.run([str(path),'-o',str(exe),str(source)],env=env,cwd=unrelated,check=True,timeout=60)
            got=subprocess.run([str(exe)],capture_output=True,timeout=10)
            assert got.returncode==0 and got.stdout=='path discovery λ\n'.encode(),got
        # Check canonicalization itself, including .. after a symlink and a loop.
        (work/'loop').symlink_to('loop')
        (work/'broken').symlink_to('missing')
        (work/'file').write_text('x')
        probe=work/'path-probe'
        osname='linux' if platform.system()=='Linux' else 'darwin'
        # The probe is a strict program whose files sit in the tree's selfhost/, which is read trusted.
        shutil.copytree(ROOT/'selfhost',tree/'selfhost')
        shutil.copy(ROOT/'tools/ci/fixtures/path_probe.tin',tree/'selfhost/path_probe.tin')
        sources=[str(tree/'selfhost'/('host_'+osname+'.tin')),str(tree/'selfhost/path_probe.tin')]
        subprocess.run([str(compiler),'-o',str(probe)]+sources,cwd=ROOT,env=dict(env,TIN_ROOT=str(tree)),check=True,timeout=60)
        paths=[str(tree/'bin/tinc'),str(work/'tree link/../file'),str(work/'tree link/bin/../../file'),
               '.',str(work/'launcher chain'),str(work/'loop'),str(work/'broken'),str(work/'file')+'/',
               str(work/'missing'),'',str(work/'file/../file')]
        got=subprocess.run([str(probe)]+paths,cwd=work,capture_output=True,timeout=10)
        oracle=subprocess.run(['go','run',str(ROOT/'bench/ref/realpath/main.go')]+paths,cwd=work,capture_output=True,check=True,timeout=60)
        libc=ctypes.CDLL(None)
        libc.realpath.argtypes=[ctypes.c_char_p,ctypes.c_void_p]
        libc.realpath.restype=ctypes.c_void_p
        expected=[]
        for path in paths:
            buf=ctypes.create_string_buffer(4096)
            absolute=os.path.join(str(work),path) if path else ''
            if libc.realpath(os.fsencode(absolute),buf):expected.append(buf.value+b'\n')
            else:expected.append(b'<nil>\n')
        expected=b''.join(expected)
        assert got.returncode==0 and got.stdout==expected,(got,expected)
        # Darwin retains libSystem's realpath semantics for file/../file. Linux is
        # production and agrees with Go's component-by-component symlink traversal.
        if osname=='linux':assert oracle.stdout==expected,(oracle.stdout,expected)
        # Missing compiler inputs keep the exact diagnostic instead of a crash.
        got=subprocess.run([str(tree/'bin/tinc'),str(work/'missing.tin')],env=env,cwd=unrelated,capture_output=True,timeout=10)
        assert got.returncode!=0 and b'cannot open' in got.stderr and b'missing.tin' in got.stderr,got
    print('PASS compiler root discovery: copied installation, spaces/Unicode, relative symlink chain, directory symlink and missing source diagnostic')


if __name__=='__main__':main()
