#!/bin/sh
set -eu
cd "$(dirname "$0")/.." || exit 1
compiler=${1:-bin/tinc}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$compiler" -edition 1 -parse-only tests/edition1/accepted.tin

for name in legacy_func explicit_semicolon positional_literal short_declaration legacy_var block_comment unknown_unit unknown_integer_unit legacy_switch legacy_go legacy_increment legacy_channel legacy_pointer legacy_while legacy_c_loop legacy_extern grouped_import import_alias no_package grouped_const grouped_type import_after_decl grouped_global multiple_global_names multiple_const_names local_const missing_newline reserved_keyword invalid_match_expression invalid_match_range
do
	if "$compiler" -edition 1 -parse-only "tests/edition1/$name.tin" >"$tmp/$name.out" 2>"$tmp/$name.err"; then
		echo "FAIL edition1/$name: unexpectedly accepted"
		exit 1
	fi
	if ! cmp -s "tests/edition1/$name.err" "$tmp/$name.err"; then
		echo "FAIL edition1/$name: diagnostic mismatch"
		diff -u "tests/edition1/$name.err" "$tmp/$name.err" || true
		exit 1
	fi
done

"$compiler" -S -o "$tmp/edition0.out" tests/edition1/paired_edition0.tin >"$tmp/edition0.s"
"$compiler" -edition 1 -S -o "$tmp/edition1.out" tests/edition1/paired_edition1.tin >"$tmp/edition1.s"
if ! cmp -s "$tmp/edition0.s" "$tmp/edition1.s"; then
	echo "FAIL edition 1 parser: edition 0 and edition 1 range-loop assembly differs"
	diff -u "$tmp/edition0.s" "$tmp/edition1.s" || true
	exit 1
fi

# Boundary blocks run: guard turns a panic into a fault after the defers run; within
# deadlines stop waits, nest, and leave the enclosing block alone (#230, #233); try E wrap
# "msg" passes fault.Wrap(err, msg) upward (#229).
for name in boundaries fault_wrap once
do
	"$compiler" -edition 1 -o "$tmp/$name" "tests/edition1/run/$name.tin"
	"$tmp/$name" >"$tmp/$name.out" 2>/dev/null
	if ! cmp -s "tests/edition1/run/$name.out" "$tmp/$name.out"; then
		echo "FAIL edition1/run/$name: output differs"
		diff -u "tests/edition1/run/$name.out" "$tmp/$name.out" || true
		exit 1
	fi
done

# wrap without try is rejected (#229).
if "$compiler" -edition 1 -o "$tmp/fault_wrap_bad" tests/edition1/fault_wrap_bad.tin >"$tmp/fault_wrap_bad.out" 2>"$tmp/fault_wrap_bad.err"; then
	echo "FAIL edition1/fault_wrap_bad: unexpectedly accepted"
	exit 1
fi
if ! cmp -s tests/edition1/fault_wrap_bad.err "$tmp/fault_wrap_bad.err"; then
	echo "FAIL edition1/fault_wrap_bad: diagnostic mismatch"
	diff -u tests/edition1/fault_wrap_bad.err "$tmp/fault_wrap_bad.err" || true
	exit 1
fi

echo "PASS edition 1 parser"
