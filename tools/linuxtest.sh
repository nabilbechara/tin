#!/bin/sh
# Usage: tools/linuxtest.sh [COMPILER] — cross-compile every tests/v2 program for linux-arm64,
# run them in an arm64 Linux container and compare with the same expected outputs as macOS.
cd "$(dirname "$0")/.." || exit 1
c=${1:-bin/tinc}
image=${TIN_LINUX_IMAGE:-tin-debian-arm64}
out=bin/linux
mkdir -p $out
: > $out/build.log
for f in tests/v2/*.tin; do
  base=$(basename "$f" .tin)
  case $f in
    *_bad.tin) TIN_ROOT=$PWD "$c" -target linux-arm64 -o $out/$base "$f" 2> $out/$base.err && echo "$base: compiled (should fail)" >> $out/build.log ;;
    *) TIN_ROOT=$PWD "$c" -target linux-arm64 -o $out/$base "$f" 2>> $out/build.log || echo "$base: COMPILE FAILED" >> $out/build.log ;;
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
  timeout 60 ./$base 2>/dev/null | sort > $base.got
  if cmp -s $base.got /src/tests/v2/$base.out; then echo "ok   $base"; else echo "FAIL $base"; diff /src/tests/v2/$base.out $base.got | head -8; fail=1; fi
done
exit $fail
RUN
chmod +x $out/run.sh
cat $out/build.log
docker run --rm -v "$PWD/$out":/w -v "$PWD":/src:ro "$image" /w/run.sh
