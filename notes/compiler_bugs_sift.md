# Compiler bugs found while building sift/cairn (bin/tinc_agents, frozen 2026-10-01)

## 1. Elements of `make([]str, n)` are nil pointers and crash when read

Symptom: `ss := make([]str, 3)` then `len(ss[0])`, `ss[0] == ""` or `say.Line(ss)` all die with
SIGSEGV (exit 139) before any buffered output is flushed. `var s str` is fine (it is a real empty
string), and after `ss[i] = ""` the elements behave normally, so the bug is that zeroed slice
storage holds 0 where a str must hold a pointer to a `[len][bytes][NUL]` block; `len(s)` and
`rt_str_eq` load through that 0.

Repro: `notes/repro_sift_make_str_nil.tin` (build with the usual `tinc_agents -o ... FILE`, run, exit 139).
`var s str; say.Line(len(s), s == "")` prints `0 true`, so the runtime's "nil strings behave as
empty" promise holds only for variables, not for zeroed slice elements.

Workaround used in sift/cairn: never read an element of `make([]str, n)` before assigning it;
cairn's LRU fills its key/value arrays with `""` on construction, and the tests build `[]str`
values with `make` only when every slot is written first.
