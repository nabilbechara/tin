#!/bin/sh
# Compare two compilers on a corpus: for every strict test and example, and for each target, the
# assembly listing (-S) of the two must be byte-identical. Proves that a change to the compiler's own
# source (not to its behavior) did not change what it generates (design/design_typed_compiler.md).
#
#   tools/dev/compare_compilers.sh OLD_TINC NEW_TINC [FILE.tin...]
cd "$(dirname "$0")/../.." || exit 1
old=$1
new=$2
[ -x "$old" ] && [ -x "$new" ] || { echo "usage: $0 OLD_TINC NEW_TINC [FILE.tin...]" >&2; exit 2; }
shift 2
if [ $# -eq 0 ]; then
	set -- $(ls tests/v2/*.tin examples/*.tin 2>/dev/null | grep -v '_bad\.tin$')
fi
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
checked=0
failed=0
for target in darwin-arm64 linux-arm64 linux-amd64; do
	for f in "$@"; do
		"$old" -target "$target" -S "$f" > "$tmp/old" 2> "$tmp/old.err"
		"$new" -target "$target" -S "$f" > "$tmp/new" 2> "$tmp/new.err"
		checked=$((checked + 1))
		if ! cmp -s "$tmp/old" "$tmp/new" || ! cmp -s "$tmp/old.err" "$tmp/new.err"; then
			echo "DIFFERENT: $target $f"
			failed=$((failed + 1))
		fi
	done
done
echo "compared $checked listings, $failed different"
[ "$failed" -eq 0 ]
