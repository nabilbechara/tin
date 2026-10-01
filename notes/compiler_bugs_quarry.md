# Compiler bugs found while building quarry/trail/lever (bin/tinc_agents, 2026-10-01)

## 1. An imported constant is typed i64, so comparing it with an i32 fails to compile

Symptom: `error: mismatched types i32 and i64` for `r == glyph.RuneError` where `r` is `i32`
and `glyph.RuneError` is `const RuneError = 0xfffd` (untyped in lib/glyph.tin). Inside glyph.tin
itself `r = RuneError` with an i32 `r` compiles, so untyped constants adapt within their own
package but become i64 when reached through `pkg.Name`.

Repro: `bin/agent_quarry/repro_const.tin` (complete `package main`):

    var r i32 = 0xfffd
    say.Line(r == glyph.RuneError)   // mismatched types i32 and i64

Workaround used in lib/trail.tin: `i64(r) == glyph.RuneError`.
