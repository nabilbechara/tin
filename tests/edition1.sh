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
# deadlines stop waits, nest, and leave the enclosing block alone (#230, #233); try E wrap
# "msg" passes fault.Wrap(err, msg) upward (#229).
# task.Deadline and task.Canceled read the innermost boundary; nested within takes the
# earlier deadline (#233).
for name in boundaries fault_wrap once polls deadlines
do
	polls=
	[ "$name" != polls ] || polls=-polls
	"$compiler" $polls -edition 1 -o "$tmp/$name" "tests/edition1/run/$name.tin"
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

# A call that can fail as a boundary block's last expression needs try or catch (#233).
if "$compiler" -edition 1 -o "$tmp/boundary_fault_bad" tests/edition1/boundary_fault_bad.tin >"$tmp/boundary_fault_bad.out" 2>"$tmp/boundary_fault_bad.err"; then
	echo "FAIL edition1/boundary_fault_bad: unexpectedly accepted"
	exit 1
fi
if ! cmp -s tests/edition1/boundary_fault_bad.err "$tmp/boundary_fault_bad.err"; then
	echo "FAIL edition1/boundary_fault_bad: diagnostic mismatch"
	diff -u tests/edition1/boundary_fault_bad.err "$tmp/boundary_fault_bad.err" || true
	exit 1
fi

# match (#225): literal, range, constant, sentinel, variant, nested, binding and guarded arms;
# values in let, assignment, return, catch blocks and expressions; break and continue in arms.
"$compiler" -edition 1 -o "$tmp/match" tests/edition1/run/match.tin
"$tmp/match" >"$tmp/match.out" 2>/dev/null
if ! cmp -s tests/edition1/run/match.out "$tmp/match.out"; then
	echo "FAIL edition1/run/match: output differs"
	diff -u tests/edition1/run/match.out "$tmp/match.out" || true
	exit 1
fi
if "$compiler" -edition 1 -o "$tmp/match_bad" tests/edition1/match_bad.tin >"$tmp/match_bad.out" 2>"$tmp/match_bad.err"; then
	echo "FAIL edition1/match_bad: unexpectedly accepted"
	exit 1
fi
if ! cmp -s tests/edition1/match_bad.err "$tmp/match_bad.err"; then
	echo "FAIL edition1/match_bad: diagnostic mismatch"
	diff -u tests/edition1/match_bad.err "$tmp/match_bad.err" || true
	exit 1
fi
# Bounded values (#240): argo stops at a bound with fault.LimitExceeded, bound(x) checks a
# length, and an unbounded value never becomes bounded without it.
"$compiler" -edition 1 -o "$tmp/bounded" tests/edition1/run/bounded.tin
"$tmp/bounded" >"$tmp/bounded.out" 2>/dev/null
if ! cmp -s tests/edition1/run/bounded.out "$tmp/bounded.out"; then
	echo "FAIL edition1/run/bounded: output differs"
	diff -u tests/edition1/run/bounded.out "$tmp/bounded.out" || true
	exit 1
fi
if "$compiler" -edition 1 -o "$tmp/bounded_bad" tests/edition1/bounded_bad.tin >"$tmp/bounded_bad.out" 2>"$tmp/bounded_bad.err"; then
	echo "FAIL edition1/bounded_bad: unexpectedly accepted"
	exit 1
fi
if ! cmp -s tests/edition1/bounded_bad.err "$tmp/bounded_bad.err"; then
	echo "FAIL edition1/bounded_bad: diagnostic mismatch"
	diff -u tests/edition1/bounded_bad.err "$tmp/bounded_bad.err" || true
	exit 1
fi

# Structured concurrency (#232): scopes, spawn, wait, cancel, first-fault cancellation.
for name in scopes lanes selects guards handles
do
	"$compiler" -edition 1 -o "$tmp/$name" "tests/edition1/run/$name.tin"
	"$tmp/$name" >"$tmp/$name.out" 2>/dev/null
	if ! cmp -s "tests/edition1/run/$name.out" "$tmp/$name.out"; then
		echo "FAIL edition1/run/$name: output differs"
		diff -u "tests/edition1/run/$name.out" "$tmp/$name.out" || true
		exit 1
	fi
done

# secret T (#239): a secret computes like its plain type and reveal gives it back; every sink
# rejects it at compile time; tinc -audit-secrets lists every reveal and every secret passed to
# a library parameter declared secret.
"$compiler" -edition 1 -o "$tmp/secrets" tests/edition1/run/secrets.tin
"$tmp/secrets" >"$tmp/secrets.out" 2>/dev/null
if ! cmp -s tests/edition1/run/secrets.out "$tmp/secrets.out"; then
	echo "FAIL edition1/run/secrets: output differs"
	diff -u tests/edition1/run/secrets.out "$tmp/secrets.out" || true
	exit 1
fi
"$compiler" -edition 1 -audit-secrets tests/edition1/run/secrets.tin >"$tmp/secrets.audit"
if ! cmp -s tests/edition1/run/secrets.audit "$tmp/secrets.audit"; then
	echo "FAIL edition1/run/secrets: audit differs"
	diff -u tests/edition1/run/secrets.audit "$tmp/secrets.audit" || true
	exit 1
fi
for name in secret_sinks secret_rules
do
	if "$compiler" -edition 1 -o "$tmp/$name" "tests/edition1/$name.tin" >"$tmp/$name.out" 2>"$tmp/$name.err"; then
		echo "FAIL edition1/$name: unexpectedly accepted"
		exit 1
	fi
	if ! cmp -s "tests/edition1/$name.err" "$tmp/$name.err"; then
		echo "FAIL edition1/$name: diagnostic mismatch"
		diff -u "tests/edition1/$name.err" "$tmp/$name.err" || true
		exit 1
	fi
	if "$compiler" -edition 1 -audit-secrets "tests/edition1/$name.tin" >/dev/null 2>&1; then
		echo "FAIL edition1/$name: audit accepted a rejected program"
		exit 1
	fi
done
# with policies and bind (#237): retry, trace, cached, slots seen by spawned children and
# parallel lines; a policy that keeps its body is a compile error.
"$compiler" -edition 1 -o "$tmp/policies" tests/edition1/run/policies.tin
"$tmp/policies" >"$tmp/policies.out" 2>/dev/null
if ! cmp -s tests/edition1/run/policies.out "$tmp/policies.out"; then
	echo "FAIL edition1/run/policies: output differs"
	diff -u tests/edition1/run/policies.out "$tmp/policies.out" || true
	exit 1
fi
if "$compiler" -edition 1 -o "$tmp/policy_keeps_body" tests/edition1/policy_keeps_body.tin >"$tmp/policy_keeps_body.out" 2>"$tmp/policy_keeps_body.err"; then
	echo "FAIL edition1/policy_keeps_body: unexpectedly accepted"
	exit 1
fi
if ! cmp -s tests/edition1/policy_keeps_body.err "$tmp/policy_keeps_body.err"; then
	echo "FAIL edition1/policy_keeps_body: diagnostic mismatch"
	diff -u tests/edition1/policy_keeps_body.err "$tmp/policy_keeps_body.err" || true
	exit 1
fi

# A task handle cannot outlive its scope, and detach captures only long-lived memory (#232):
# each is a compile error.
for name in scope_escape_bad detach_capture_bad
do
	if "$compiler" -edition 1 -o "$tmp/$name" "tests/edition1/$name.tin" >"$tmp/$name.out" 2>"$tmp/$name.err"; then
		echo "FAIL edition1/$name: unexpectedly accepted"
		exit 1
	fi
	if ! cmp -s "tests/edition1/$name.err" "$tmp/$name.err"; then
		echo "FAIL edition1/$name: diagnostic mismatch"
		diff -u "tests/edition1/$name.err" "$tmp/$name.err" || true
		exit 1
	fi
done

echo "PASS edition 1 parser"
