#!/bin/sh
# Usage: tools/v2test.sh [COMPILER] — compile and run every tests/v2/*.tin and compare its
# sorted output with the .out file next to it; *_bad.tin must fail with the .err lines.
cd "$(dirname "$0")/.." || exit 1
c=${1:-bin/tinc}
fail=0
for f in tests/v2/*.tin; do
  base=${f%.tin}
  case $f in
    *_bad.tin)
      TIN_ROOT=$PWD "$c" -o bin/t "$f" 2> bin/t.err && { echo "FAIL $f: compiled"; fail=1; continue; }
      diff -u "$base.err" bin/t.err > /dev/null || { echo "FAIL $f"; diff -u "$base.err" bin/t.err | head -20; fail=1; } ;;
    *)
      TIN_ROOT=$PWD "$c" -o bin/t "$f" || { echo "FAIL $f: compile"; fail=1; continue; }
      bin/t | sort > bin/t.out
      [ -f "$base.out" ] || { echo "skip $f: no $base.out yet (review the output, then save it)"; continue; }
      diff -u "$base.out" bin/t.out > /dev/null || { echo "FAIL $f"; diff -u "$base.out" bin/t.out | head -20; fail=1; } ;;
  esac
done
[ $fail = 0 ] && echo "v2 tests pass"
exit $fail
