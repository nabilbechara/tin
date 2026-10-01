# Compiler bugs found while building tide/dice (bin/tinc_agents, frozen 2026-10-01)

## 1. Constant folding of u64 values >= 2^63 is signed

An untyped constant at or above 2^63 is held as a negative i64, so operators folded at compile
time act on the negative value. Repro: `notes/repro_tide_const_u64_shift.tin`.

- `a := u64(0xffffffffffffffff) >> 11` compiles and yields 18446744073709551615 (-1 >> 11 == -1,
  an arithmetic shift); `v >> 11` on a `var v u64` holding the same value yields the correct
  9007199254740991 (logical shift).
- `var c u64 = 0xffffffffffffffff >> 11` fails to compile: `constant -1 overflows u64`.
- `const k = 0xffffffffffffffff` then `u64(k)` fails to compile: `constant -1 overflows u64`
  (the direct form `var v u64 = 0xffffffffffffffff` is accepted, as the primer says).

Workaround used in lib/dice.tin and lib/tide.tin: never shift, divide or convert a u64 constant
>= 2^63 at compile time; build it at run time (`^u64(0)`, `u64(1) << 63`, or a `var`).
