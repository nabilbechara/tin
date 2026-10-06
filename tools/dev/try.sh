#!/bin/sh
# Usage: tools/dev/try.sh COMPILER FILE.tin — compile with COMPILER and run, printing a backtrace on compiler crash.
cd "$(dirname "$0")/../.." || exit 1
c=$1; f=$2; shift 2
TIN_ROOT=$PWD "$c" -o bin/t "$f"; rc=$?
if [ $rc -ge 128 ]; then
  python3 - "$c" "$f" <<'PY'
import subprocess,os,sys
env=dict(os.environ,TIN_ROOT=os.getcwd())
try:
    r=subprocess.run(["lldb","--batch","-o","command script import tools/dev/tinbt.py","-o","run","-k","tinbt 30","-k","quit","--",sys.argv[1],"-o","bin/t",sys.argv[2]],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60,env=env)
    o=r.stdout; i=o.find("stop reason"); print(o[i:])
except subprocess.TimeoutExpired: print("lldb timeout")
PY
  exit $rc
fi
[ $rc -eq 0 ] && bin/t "$@"
