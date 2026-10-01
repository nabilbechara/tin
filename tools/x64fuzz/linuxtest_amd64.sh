#!/bin/sh
# Usage: tools/x64fuzz/linuxtest_amd64.sh [COMPILER] — cross-compile every tests/v2 program for
# linux-amd64, run them in the (emulated) amd64 Linux container and compare with the same
# expected outputs as macOS. A copy of tools/linuxtest.sh with the target and image changed;
# TIN_ROOT may point at a tree whose lib/ carries the per-arch runtime files.
cd "$(dirname "$0")/../.." || exit 1
c=${1:-bin/tinc}
image=${TIN_LINUX_IMAGE:-tin-debian-amd64}
root=${TIN_ROOT:-$PWD}
out=${X64_TEST_DIR:-bin/linux-amd64}
mkdir -p $out
: > $out/build.log
for f in tests/v2/*.tin; do
  base=$(basename "$f" .tin)
  case $f in
    *_bad.tin) TIN_ROOT=$root "$c" -target linux-amd64 -o $out/$base "$f" 2> $out/$base.err && echo "$base: compiled (should fail)" >> $out/build.log ;;
    *) TIN_ROOT=$root "$c" -target linux-amd64 -o $out/$base "$f" 2>> $out/build.log || echo "$base: COMPILE FAILED" >> $out/build.log ;;
  esac
done
cat > $out/run.sh <<'RUN'
#!/bin/sh
cd /w
fail=0
for t in /src/tests/v2/*.tin; do
  base=$(basename "$t" .tin)
  case $base in *_bad) continue ;; esac
  [ -x ./$base ] || { echo "FAIL $base: not built"; fail=1; continue; }
  [ -f /src/tests/v2/$base.out ] || { echo "skip $base: no .out"; continue; }
  timeout 300 ./$base 2>$base.err | sort > $base.got
  if cmp -s $base.got /src/tests/v2/$base.out; then echo "ok   $base"; else echo "FAIL $base"; diff /src/tests/v2/$base.out $base.got | head -8; head -3 $base.err; fail=1; fi
done
exit $fail
RUN
chmod +x $out/run.sh
cat $out/build.log
docker run --rm --platform linux/amd64 -v "$(cd $out && pwd)":/w -v "$PWD":/src:ro "$image" /w/run.sh
