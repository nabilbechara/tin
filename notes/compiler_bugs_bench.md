# Compiler bugs hit while benchmarking (bin/tinc_agents, frozen 2026-10-01)

## 1. `import "argo"` fails: `lib/argo.tin:372:11: error: invalid number 18446744073709551615`
Repro: `TIN_ROOT=$ROOT bin/tinc_agents -o /tmp/x tests/v2/json.tin` (the reference test itself).
lib/argo.tin was edited after the compiler was frozen; the frozen lexer/const folder rejects a u64-max
decimal literal (it only accepts literals that fit in i64). Workaround used for the JSON benchmark:
a private TIN_ROOT (`bin/agent_bench/root/`) holding a copy of lib/ where the literal is replaced by
`lim := u64(0); lim--` and `(lim-d)/10`. lib/ itself was not modified.

## 2. Optional narrowing does not see compound conditions
`if l == nil || r == nil { return 1 }; return 1 + check(l) + check(r)` -> `cannot use ?Node as Node`.
Only `if x != nil { ... }` / `if x == nil {} else { ... }` on a plain local identifier narrows.
Workaround: nest `if l != nil { if r != nil { ... } }`. (Documented behaviour of narrow_begin, but
`&&` of two nil checks would be a cheap extension.)
