# Tin vs Go 1.26 benchmarks (bench/v2, strict Tin)

Date: 2026-10-01. Machine: Apple Silicon macOS (Darwin 23.6), single thread.
Compiler: frozen `bin/tinc_agents` (default flags). Go: `go1.26.1 darwin/arm64`, `go build -o`.
Timing: `/usr/bin/time -l`, 3 runs each, best wall time; RSS = max resident set size.
Sources: `bench/v2/NAME.tin` + `bench/v2/NAME.go` (same algorithm, same sizes, same printed checksum).
Binaries, outputs, timings and `-S` dumps: `bin/agent_bench/` (`run.sh`, `out_*`, `time_*`, `*.s`).
Every pair's stdout is byte-identical (`diff` of `out_NAME_tin.txt` vs `out_NAME_go.txt`).

## Results

| Benchmark | Size | Tin s | Go s | Tin/Go | Tin RSS | Go RSS | Checksum (both) |
|---|---|---|---|---|---|---|---|
| sieve | primes < 100M, `[]u8` | 0.47 | 0.46 | 1.02 | 105 MB | 104 MB | 5761455 |
| nbody | 5 bodies, 50M steps | 2.15 | 1.83 | **1.17** | 5.2 MB | 3.8 MB | -0.169075164 / -0.169059907 |
| fannkuch-redux | n=11 | 1.99–2.25 (1) | 1.90 | **1.05–1.18** | 5.3 MB | 4.1 MB | 556355, max flips 51 |
| spectral-norm | n=5500 | 1.33 | 1.34 | 0.99 | 5.3 MB | 4.0 MB | 1.274224153 |
| binary-trees | depth 18 | 0.30 | 1.18 | 0.25 | **1096 MB** | 41 MB | total 8912880 (2) |
| mandelbrot | n=4000, 50 iters, checksum only | 0.66 | 0.64 | 1.03 | 1.1 MB | 3.7 MB | 490592614184 |
| lcg (fasta-like) | 300M LCG steps + table lookup | 1.22 | 1.19 | 1.03 | 5.2 MB | 3.7 MB | 21023915064753 |
| hashmap | 5M insert + 5M hit + 5M miss, `map[i64]i64` | 0.58 | 0.61 | 0.95 | 287 MB | 202 MB | 5000000 12499997500000 5000000 |
| strbuild | 10M × (small str + 1 byte) into `[]u8` | 0.10 | 0.06 | **1.67** | 115 MB | 100 MB | 45000000 3937500000 |
| json | `argo.Put([]Item×10)` 1M× into reset `[]u8` vs `json.Marshal` | 1.74 | 2.41 | 0.72 | 34.7 MB | 16.4 MB | 1077000000 + identical JSON |

(1) fannkuch Tin measured 1.99 in the first 3-run set and 2.25 in a clean re-run; Go 1.90–1.92 in both. Treat Tin as 5–18% slower.
(2) Tin has no GC: 2^23 nodes per depth × 8 depths + stretch/long-lived trees all stay in the bump pool, hence 1.1 GB. That is the expected cost model, not a leak; speed is 4× Go because allocation is a bump pointer with no GC work.

Floating-point fairness: Go fuses `x*y+z` into `FMADD` on arm64; Tin emits `fmadd`/`fmsub` too (see nbody/mandelbrot/spectral asm), and the three FP benchmarks printed identical digits at `%.9f`.

Harness notes:
- `import "argo"` does not compile with the frozen compiler (`lib/argo.tin:372: invalid number 18446744073709551615`, then `:386: 9223372036854775808`). The json benchmark was built with `TIN_ROOT=bin/agent_bench/root` (a private copy of lib/ with those two literals rewritten as `lim := u64(0); lim--` and `half := u64(1); half <<= 63`). `lib/` itself was not modified. Details in `notes/compiler_bugs_bench.md`.
- Tin has no `gauge` package yet; nbody/spectral use `extern func sqrt(x f64) f64` (libm). Go uses `math.Sqrt` (intrinsic). This is itself one of the findings below.

## Why Tin loses, loop by loop

### strbuild (1.67×) — append is three function calls per byte
Tin's loop body (`bin/agent_bench/strbuild.s`, `_main.main` L1):

```
L1:
	mov x0, x20
	and x9, x19, #3
	ldr x17, [x24]            ; reload len(strs) every iteration
	cmp x9, x17
	b.hs L5                   ; bounds check on strs[i&3] (len is the constant 4)
	ldr x16, [x24, #16]
	ldr x1, [x16, x9, lsl #3]
	bl _rt_append_str         ; call: rt_own call + cap check + libc memcpy call
	mov x20, x0
	mov x0, x20
	movz x17, #10
	sdiv x16, x19, x17        ; i % 10 via sdiv+msub (Go: umulh + shifts)
	msub x9, x16, x17, x19
	add x9, x9, #48
	mov x1, x9
	and x1, x1, #255
	movz x2, #1
	bl _rt_append             ; call: rt_own call + cap check + rt_store_elem call
	mov x20, x0
```

and the runtime's single-element append:

```
_rt_append:
	... bl _rt_own            ; region-ownership check, a call on every append
	ldr x20, [x19]
	ldr x9, [x19, #8]
	cmp x20, x9
	b.lt L68
	... bl _rt_slice_grow
L68:
	ldr x9, [x19, #16]
	madd x0, x20, x21, x9
	mov x1, x22
	mov x2, x21
	bl _rt_store_elem         ; generic store dispatched on element size at run time
	add x9, x20, #1
	str x9, [x19]
```

So `append(b, byte)` costs `bl rt_append` → `bl rt_own` → `bl rt_store_elem` (three calls, two of them to decide an element size that is a compile-time constant), and `append(b, s...)` costs `bl rt_append_str` → `bl rt_own` → `bl memcpy` (libc call for 1–6 bytes). Go inlines the capacity test and the store/`memmove` and only calls `growslice` on growth (its main has `CALL runtime.growslice` on the slow path only). Also visible: the slice pointer is spilled and immediately reloaded right after `rt_slice_make` (`str x9,[x29,#16]; ldr x9,[x29,#16]`).

The same per-byte call chain is the hot path of every encoder: the json benchmark spends most of its 1.74 s in `rt_append`/`rt_append_str` through argo's writers; inlining the fast path would widen that win.

### nbody (1.17×) — sqrt is a libc call, index checks + len reloads inside the pair loop
`_advance` inner loop (`bin/agent_bench/nbody.s` L6):

```
L6:
	ldr x17, [x24]            ; reload len(bodies) each j
	cmp x21, x17
	b.hs L5                   ; bounds check bodies[j] although j < n == len(bodies)
	ldr x16, [x24, #16]
	ldr x19, [x16, x21, lsl #3]
	ldr d16, [x20]            ; dx, dy, dz
	ldr d17, [x19]
	fsub d9, d16, d17
	...
	fmul d16, d9, d9
	fmadd d16, d10, d10, d16
	fmadd d12, d11, d11, d16  ; dsq (fused, same as Go)
	fmov d0, d12
	bl _sqrt                  ; libc call; Go emits FSQRTD inline (0 calls in Go's advance)
	fmov d13, d0
	fmul d16, d12, d13
	fdiv d8, d14, d16         ; mag
	ldr d16, [x20, #24]
	ldr d17, [x19, #48]       ; bj.mass loaded 3 times (once per component)
	fmul d17, d9, d17
	fmsub d16, d17, d8, d16
	str d16, [x20, #24]
	ldr d16, [x20, #32]
	ldr d17, [x19, #48]       ; ...reloaded after the store, no alias info
	...
```

Costs per pair step (500M of them): a real call to `_sqrt` (branch, return, `fmov` in/out, and every live FP value forced into callee-saved d8–d14 across the call), a bounds check with a dependent `ldr` of the header, and `bj.mass`/`bi.mass` re-loaded six times because every `str` to a `Body` field invalidates the loads. Go's `advance` has zero calls and zero bounds checks (`panicBounds` count 0). The remaining gap (≈2 cycles per pair) matches exactly these extra instructions since the `fsqrt`/`fdiv` latency is the same on both.

### fannkuch (1.05–1.18×) — everything outside the innermost loop lives on the stack, double bounds checks
`_fannkuch` is one big function and the allocator spilled almost every variable (`bin/agent_bench/fannkuch.s`):

```
L1:                                   ; perm1[i] = i
	ldr x9, [x29, #136]
	ldr x10, [x29, #112]              ; i reloaded
	ldr x17, [x29, #144]
	cmp x10, x17
	b.hs L5
	ldr x11, [x29, #112]              ; i reloaded again
	str x11, [x9, x10, lsl #3]
L3:
	ldr x9, [x29, #112]               ; i++ as load/add/store
	add x9, x9, #1
	str x9, [x29, #112]
L2:
	ldr x9, [x29, #112]
	ldr x10, [x29, #88]               ; n reloaded
	cmp x9, x10
	b.lt L1
```

The flip loop (the hottest code) does get registers but checks each index twice, once for the load and once for the store:

```
L18:
	cmp x19, x23
	b.hs L5                           ; perm[i] load check
	ldr x27, [x22, x19, lsl #3]
	cmp x19, x23
	b.hs L5                           ; perm[i] store check (same index, same len)
	cmp x20, x23
	b.hs L5                           ; perm[j] load check
	ldr x9, [x22, x20, lsl #3]
	str x9, [x22, x19, lsl #3]
	cmp x20, x23
	b.hs L5                           ; perm[j] store check
	str x27, [x22, x20, lsl #3]
	add x19, x19, #1
	sub x20, x20, #1
L19:
	cmp x19, x20
	b.lt L18
```

Around it, `flips`, `k = perm[0]`, `checksum`, `maxFlips`, `permCount` and the slice headers are all stack slots (`ldr x9,[x29,#40]; add; str` for `flips++`, `[x29,#72]` for checksum, `[x29,#128]` for permCount), and `count[r]--` reloads the `count` header and re-checks `r` three times in a row (`L33`). The rotation loop `perm1[i] = perm1[i+1]` checks both `i` and `i+1` against the same len. Go keeps all of these in registers. The variance between runs (1.99 vs 2.25) is consistent with a memory-op-bound loop.

### Near-parity benchmarks: what the asm still shows
- **sieve** (1.02×): inner `L7` has `cmp x19, x23; b.hs` on `s[j]` although `j < n` and `s := make([]u8, n)`; `movz x9, #1` is re-materialised every iteration. Go keeps two bounds checks here as well (2 `panicBounds`), so parity.
- **lcg** (1.03×): `% 139968` and `% 20` are `sdiv`+`msub` (Go: magic multiply); `alu[seed%20]` and `buf[i&1023]` each keep a bounds check even though `x%20 < 20 = len(alu)` and `x&1023 < 1024 = len(buf)`; the constants 139968 and 300000000 are rebuilt with `movz/movk` inside the loop. Hidden by the serial LCG dependency chain.
- **spectral** (0.99×): `a(i, j)` is **not inlined** — `bl _a` per inner iteration plus `fmov d16, d0`, `ldr x17, [x22]` (len reload) and a bounds check on `v[j]` although `j < n == len(v)` and `v` is a non-`mut` parameter. Go inlines `a` and has no check in the inner loop. Parity only because the loop is bound by `fdiv` latency.
- **mandelbrot** (1.03×): inner loop is as tight as Go's (7 instrs, `fmadd` used). The FP constants 2.0/1.0/1.5 are kept in stack slots and reloaded per row/pixel (`ldr d16, [x29, #32]`) instead of callee-saved d-registers.
- **hashmap** (0.95×, win): lookup is `bl rt_map_get` → `bl rt_map_find` → `bl _lsr`, where `_lsr` is a 9-instruction *function* emulating logical shift right (ARM64 has `lsr xd, xn, xm`):

```
_lsr:
	mov x10, x0
	mov x9, x1
	asr x0, x10, x9
	movz x1, #1
	movz x2, #64
	sub x2, x2, x9
	lsl x1, x1, x2
	sub x1, x1, #1
	and x0, x0, x1
	ret
```

  `rt_map_find` spills `m` to `[x29,#24]` and reloads it for every field. `_, ok := m[k]` compiles to `rt_map_get` + a second call `rt_map_found` with both results spilled and reloaded. Tin still wins because the table is open-addressing with no write barriers and no GC. RSS is 287 vs 202 MB: keys/vals/ctrl are separate arrays sized for ≤50% load (16M slots × 17 B ≈ 272 MB) and the previous tables stay in the pool after `rt_map_grow`.
- **json** (0.72×, win): the typed encoder is inlined into `main` (no reflection), but each field goes through `wstr`/`wint` → `rt_append`/`rt_append_str` with the call chain described under strbuild, which is why it is only 1.4× faster than Go's reflection-based `Marshal` rather than 5–10×.
- **binary-trees** (0.25×, win): `bottomUp` is `bl _rt_alloc` (bump pointer) + two recursive calls; `check` is 2 loads + `cbz` + 2 calls. 4× Go at 27× the memory, as expected without a GC.

## Top 5 codegen improvements (ordered by expected impact)

1. **Inline the append fast path and specialise by element size.** Emit `len < cap` test + `strb/strh/str` (or an inline small-copy for `s...`) in the caller, call `rt_slice_grow` only when full, and drop the per-append `rt_own` and `rt_store_elem` calls (the element size is a compile-time constant). Removes 3 calls per `append(b, x)` and 3 per `append(b, s...)`. Expected: strbuild 1.67× → ~1.0×; json 1.4× → several × faster than Go; every argo/anvil/say builder path benefits.
2. **Intrinsics + small-function inlining.** Treat `sqrt` (future `gauge.Sqrt`) as `fsqrt d0, d0`; inline leaf functions under ~20 instructions (`a` in spectral, `lsr` in the runtime, small methods). nbody's whole 17% is the `bl _sqrt` call plus what it forces into callee-saved registers; `lsr` as a call sits on every map probe. Expected: nbody → parity; spectral/hashmap inner loops shorten by 30–40% of their instructions.
3. **Register allocation with loop-depth spill weights (and no spill-then-reload of fresh values).** fannkuch keeps `i`, `flips`, `checksum`, `permCount`, `maxFlips`, `k` and three slice headers in stack slots; strbuild/hashmap spill values right after producing them; mandelbrot reloads FP constants from the stack; `_, ok := m[k]` spills both results. Prefer spilling the coldest value, keep FP constants in d8–d15 when free, and let 2-result builtins return in registers. Expected: fannkuch → parity (~15%), small gains everywhere.
4. **Bounds-check elimination with length tracking.** Treat `len(s)` as loop-invariant when `s` is not reassigned/appended in the loop (always true for non-`mut` params), record `n == len(s)` from `n := len(s)` and from `s := make([]T, n)`, derive ranges for `x & c` and `x % c`, and dedupe checks of the same index within a block (fannkuch does 4 checks for 2 indexes per swap; `count[r]` is checked 3× in a row). Today every check also costs a dependent `ldr` of the header. Affects sieve, lcg, nbody, spectral, fannkuch, strbuild; cheap individually, but it is one load + cmp + branch in every hot loop body.
5. **Constant handling: division by constant via multiply-high, and hoist constant materialisation.** `% 139968`, `% 20`, `% 10` compile to `sdiv`+`msub` (7–12 cycle latency) where Go uses `smulh/umulh` + shift (`/2` already uses add/asr). Constants wider than 16 bits (`movz`+`movk`×3) are rebuilt inside loops on every iteration (hashmap rebuilds two 64-bit LCG constants = 8 instructions per iteration; lcg rebuilds 139968 and 300000000). Hoist them to callee-saved registers or use literal-pool loads. Expected: lcg and the LCG-driven benchmarks 10–20%; strbuild/json digit formatting a few %.

Also worth noting for the runtime (not codegen): `rt_map_grow` could release the previous tables to the pool (RSS 287 → ~200 MB), and `rt_map_find` should keep `m` in a register.
