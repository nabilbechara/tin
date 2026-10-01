# Compiler bugs found while building twine/glyph (bin/tinc_agents, 2026-10-01)

## 1. `len(call())` of a `[]u8`-returning call inside `say.Line` args jumps to 0x100000000

Symptom: the program compiles, then traps with `EXC_BAD_INSTRUCTION` at PC 0x100000000 (the
Mach-O header), exit code 132. Output printed before the bad line is lost unless run under lldb.

Repros (each is a complete `package main`; build with the usual `tinc_agents -o ... FILE`):
- `notes/repro_twine_len_u8slice_func.tin` — `say.Line("plain func", len(bytesOf(b)))` where
  `func bytesOf(b Box) []u8` — CRASHES.
- `notes/repro_twine_len_u8slice_method.tin` — `say.Line("x", len(b.Bytes()))` where
  `func (b Box) Bytes() []u8` — CRASHES.
- `notes/repro_twine_len_u8slice_workaround.tin` — `bs := b.Bytes(); say.Line("var", len(bs))`
  and `n := len(b.Bytes()); say.Line("assigned", n)` — both WORK.

What does not crash (bisected):
- `say.Line("m", b.Len()+1)` with an i64-returning method.
- `say.Line("d", b.Bytes())` — passing the []u8 call result directly (prints `[120]`).
- `say.Line("s", len(twine.Split("", ",")))` — `len()` of a call returning `[]str` (works in
  tests/v2/twine.tin).

So the trigger is specifically `len(<call returning []u8>)` used as an argument of say.Line
(both free functions and methods). Likely the say.Line lowering types the inner call's result
as []u8 and takes a wrong path for the `len` of a call temporary (bad call target / clobbered
register). Workaround: bind the slice to a local before `len`.
