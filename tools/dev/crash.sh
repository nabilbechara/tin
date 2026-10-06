#!/bin/sh
# Usage: tools/dev/crash.sh PROGRAM ARGS... — run under lldb and print a Tin backtrace on a crash.
dir=$(cd "$(dirname "$0")" && pwd)
lldb --batch -o "command script import $dir/tinbt.py" -o run -k tinbt -k quit -- "$@" < /dev/null 2>&1 | sed -n '/^pc /,/^(lldb) quit/p'
