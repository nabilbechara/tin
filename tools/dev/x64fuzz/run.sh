#!/bin/sh
# Usage: tools/dev/x64fuzz/run.sh [COUNT] [SEED] — encode COUNT random x86-64 instructions with
# selfhost/asm_x64.tin, disassemble the bytes with GNU objdump in Docker and diff the listings.
# X64FUZZ_DIR picks the work directory; X64FUZZ_IMAGE names an image that already has
# binutils-x86-64-linux-gnu installed (the default installs it into debian:bookworm-slim).
cd "$(dirname "$0")/../../.." || exit 1
count=${1:-20000}
seed=${2:-1}
w=${X64FUZZ_DIR:-${TMPDIR:-/tmp}/x64fuzz}
mkdir -p "$w" || exit 1
w=$(cd "$w" && pwd)
case $(uname -s) in Darwin) host=darwin ;; *) host=linux ;; esac
bin/tinc -o "$w/fuzz" selfhost/records.tin selfhost/util.tin "selfhost/host_$host.tin" selfhost/asm_x64.tin tools/dev/x64fuzz/fuzz.tin || exit 1
"$w/fuzz" "$w/out.bin" "$w/ours.txt" "$count" "$seed" || exit 1
image=${X64FUZZ_IMAGE:-debian:bookworm-slim}
install=
if [ "$image" = debian:bookworm-slim ]; then
  install='apt-get update -qq && apt-get install -y -qq binutils-x86-64-linux-gnu >/dev/null && '
fi
docker run --rm --platform linux/arm64 -v "$w:/w" "$image" \
  sh -c "${install}x86_64-linux-gnu-objdump -D -b binary -m i386:x86-64 -M intel /w/out.bin" > "$w/objdump.txt" || exit 1
python3 tools/dev/x64fuzz/compare.py "$w/ours.txt" "$w/objdump.txt"
