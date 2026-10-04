#!/usr/bin/env python3
"""Native Linux syscall ABI, returning signals, independent errors and getdents64."""
import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from suite import ROOT
from libc_inventory import read_inventory


def undefined_symbols(path):
    data=path.read_bytes()
    assert data[:5]==b'\x7fELF\x02'
    offset=struct.unpack_from('<Q',data,40)[0]
    size,count=struct.unpack_from('<HH',data,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(count)]
    result=set()
    for section in sections:
        if section[1]!=11:
            continue
        strings=sections[section[6]]
        strings=data[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4],section[4]+section[5],section[9]):
            name,_,_,index,_,_=struct.unpack_from('<IBBHQQ',data,pos)
            if name and index==0:
                result.add(strings[name:].split(b'\0',1)[0].decode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target')
    parser.add_argument('--docker')
    args = parser.parse_args()
    out = ROOT / 'bin/ci/syscall'
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='syscall-',dir=out) as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT/'lib',work/'lib')
        probe = work/'lib/syscallprobe'
        probe.mkdir()
        shutil.copy(ROOT/'tools/ci/fixtures/syscall_probe.tin',probe/'probe.tin')
        directory = work/'entries'
        directory.mkdir()
        (directory/'file').write_bytes(b'abc')
        (directory/'directory').mkdir()
        (directory/'symlink').symlink_to('directory')
        (directory/'broken').symlink_to('missing')
        for i in range(5000):
            (directory/(str(i).zfill(5)+'x'*240)).touch()
        exe=work/'syscall'
        cmd=[str(ROOT/'bin/tinc'),'-o',str(exe)]
        if args.target: cmd+=['-target',args.target]
        subprocess.run(cmd+['tools/ci/fixtures/syscall.tin'],check=True,cwd=ROOT,
                       env=dict(os.environ,TIN_ROOT=str(work)),timeout=60)
        forbidden={name for name,row in read_inventory(ROOT/'notes/libc_inventory.md').items()
                   if row['phase']=='3'} | {'syscall'}
        assert not (undefined_symbols(exe)&forbidden),undefined_symbols(exe)&forbidden
        cmd=[str(exe),str(directory)]
        if args.docker:
            cmd=['docker','run','--rm','-v',f'{ROOT}:{ROOT}','-w',str(ROOT),args.docker]+cmd
        result=subprocess.run(cmd,capture_output=True,timeout=30,cwd=ROOT)
        reference=subprocess.run(['go','run','./bench/ref/syscall',str(directory)],
            check=True,capture_output=True,timeout=60,cwd=ROOT)
        (out/'syscall.log').write_bytes(result.stdout+result.stderr)
        assert result.returncode==0 and result.stdout==reference.stdout,(result,reference.stdout)
        print('PASS raw syscall ABI, returning signal on alternate stack, per-thread errors, 5004 long/linked directory entries and forced DT_UNKNOWN')


if __name__=='__main__':
    main()
