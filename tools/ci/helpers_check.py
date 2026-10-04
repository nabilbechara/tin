#!/usr/bin/env python3
"""Exact UTC/calendar/error helpers, Linux symbols and inherited OS handles."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import pty
import random
import shutil
import socket
import subprocess
import tempfile
from suite import ROOT


class TM(ctypes.Structure):
    _fields_=[(n,ctypes.c_int) for n in ('sec','min','hour','day','month','year','weekday','yday','isdst')]+[('offset',ctypes.c_long),('zone',ctypes.c_void_p)]


def quoted(s):
    return json.dumps(s,ensure_ascii=False,separators=(',',':'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',default='bin/tinc')
    args=parser.parse_args()
    compiler=(ROOT/args.compiler).resolve()
    out=ROOT/'bin/ci/helpers';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='helpers-',dir=out) as tmp:
        work=Path(tmp);shutil.copytree(ROOT/'lib',work/'lib')
        probe=work/'lib/helperprobe';probe.mkdir()
        shutil.copy(ROOT/'tools/ci/fixtures/helpers_probe.tin',probe/'probe.tin')
        linux=platform.system()=='Linux'
        if linux:shutil.copy(ROOT/'tools/ci/fixtures/helpers_symbols_linux.tin',probe/'symbols_linux.tin')
        exe=work/'helpers'
        subprocess.run([str(compiler),'-o',str(exe),'tools/ci/fixtures/helpers.tin'],check=True,cwd=ROOT,env=dict(os.environ,TIN_ROOT=str(work)),timeout=60)
        libc=ctypes.CDLL(None)
        libc.strerror.restype=ctypes.c_char_p
        expected=''.join(f'{n} {quoted(libc.strerror(n).decode())}\n' for n in range(-2,140)).encode()
        got=subprocess.run([str(exe),'errors'],capture_output=True,timeout=10)
        assert got.returncode==0 and got.stdout==expected,(got,expected)
        times=[0,-1,1,-62167219200,-62135596800,253402300799,951782399,951782400,4107542400,-2208988800]
        rng=random.Random(12504)
        times += [rng.randrange(-1000000000000,1000000000000) for _ in range(2000)]
        data=('\n'.join(map(str,times))+'\n').encode()
        got=subprocess.run([str(exe),'calendar'],input=data,capture_output=True,timeout=20)
        width='1' if linux else '4'
        reference=subprocess.run(['go','run','./bench/ref/calendar',width],input=data,capture_output=True,check=True,cwd=ROOT,timeout=60)
        assert got.returncode==0 and got.stdout==reference.stdout,(got.stderr,got.stdout[:1000],reference.stdout[:1000])
        # Also preserve the former C output exactly, including years before 0001.
        libc.gmtime_r.argtypes=[ctypes.POINTER(ctypes.c_long),ctypes.POINTER(TM)]
        libc.gmtime_r.restype=ctypes.POINTER(TM)
        libc.strftime.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.POINTER(TM)]
        expected=[]
        for seconds in times:
            tm=TM();stamp=ctypes.c_long(seconds)
            assert libc.gmtime_r(ctypes.byref(stamp),ctypes.byref(tm))
            buf=ctypes.create_string_buffer(128)
            n=libc.strftime(buf,128,b'Date: %a, %d %b %Y %H:%M:%S GMT\r\n',ctypes.byref(tm))
            assert n
            expected.append(f'{tm.year+1900} {tm.month+1} {tm.day} {tm.hour} {tm.min} {tm.sec} {tm.weekday} {quoted(buf.value.decode())}\n')
        assert got.stdout==''.join(expected).encode(),'calendar differs from former C formatting'
        got=subprocess.run([str(exe),'hostname'],capture_output=True,timeout=10)
        assert got.returncode==0 and got.stdout==(quoted(socket.gethostname())+'\n').encode(),got
        master,slave=pty.openpty();read,write=os.pipe()
        try:
            with tempfile.TemporaryFile() as f:
                fds=[slave,master,read,write,f.fileno()]
                got=subprocess.run([str(exe),'tty']+list(map(str,fds))+['-1'],pass_fds=fds,capture_output=True,timeout=10)
                expected=''.join(str(os.isatty(fd)).lower()+'\n' for fd in fds+[-1]).encode()
                assert got.returncode==0 and got.stdout==expected,got
        finally:
            for fd in (master,slave,read,write):os.close(fd)
        if linux:
            cpus=sorted(os.sched_getaffinity(0))
            for count in (1,min(2,len(cpus))):
                chosen=set(cpus[:count])
                got=subprocess.run([str(exe),'cpus'],capture_output=True,timeout=10,preexec_fn=lambda:os.sched_setaffinity(0,chosen))
                assert got.returncode==0,got
                n,page=map(int,got.stdout.split())
                assert 1<=n<=count and page==os.sysconf('SC_PAGESIZE'),got
            symbols=work/'symbols.tin'
            symbols.write_text('package main\nimport "helperprobe"\nfunc main() { helperprobe.Symbols() }\n')
            exe2=work/'symbols'
            subprocess.run([str(compiler),'-o',str(exe2),str(symbols)],check=True,env=dict(os.environ,TIN_ROOT=str(work)),timeout=60)
            got=subprocess.run([str(exe2)],capture_output=True,timeout=10)
            assert got.returncode==0 and got.stdout==b'symbols bounded\n',got
        (out/'helpers.log').write_text('2010 calendar values matched Go and former C; errno table exact; hostname/PTY/pipe/file/CPU/symbol checks passed\n')
        print('PASS UTC fields and exact Date headers (2010 Go/C values), all errno messages, hostname, PTY/pipe/file handles, Linux affinity/page size and symbol boundaries')


if __name__=='__main__':main()
