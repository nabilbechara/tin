# Interface: arena sub-regions (#236)

Status: **proposed**, for approval by the members of the memory interface (owner #176, PR
#260; #235 and #209 are closed). Nothing builds on this file before #176 has approved the PR
that adds it (AGENTS.md, Tin 1 rule 5). After that, a change to a name or a word below needs
the same approval.

Spec: `design/design_semantics.md` §5 (sub-regions: `arena` is discarded, its result is copied
into the parent region). `design/interface_boundaries.md` §1.1 reserves `bRegion` (words 18-20
of a boundary record) for the region mark and gives merge and discard to #176. This file fills
that in for `arena` only. It changes nothing in #176's reclamation (counts, `drop`, the epoch
limbo, `design/interface_mem.md` in #260).

## 1. What an arena's memory is

An arena is a **fresh request pool**: the same bump chunks, extra chunks and big blocks as
the pool of a request (toolchain/docs/RUNTIME.md §3), made when the block is entered and freed when it
is left. It is pool memory, never ingot memory, so:

- pool memory is never counted (#176), so nothing in #176's interface changes.
- `keep(x)` inside an arena copies into the ingot heap as everywhere else.
- Leaving an arena is **not** a quiescent point for the epoch limbo (#260): it frees only
  the arena's own chunks and never calls `rt_pool_reset`.
- A `limit` around an arena counts the arena's chunks as they are taken (`rt_alloc_slow`,
  #235), and the discard gives them back (`rt_bnd_charge(-n)` with the bytes it frees).

## 2. Record words

`bRegion` (word 18) of a `bkArena` record points to an arena record of `arenaWords` words
(made with `calloc`, freed with the boundary). Words 19 and 20 stay 0.

| word | name | meaning |
|---|---|---|
| 0-4 | `aBump` .. `aExtra` (`aBase` = 2, `aExtra` = 4) | the arena pool's words while they are not in the core context: while the code that entered it is switched out, and after `rt_arena_out` |
| 5 | `aFmt` | the formatting state while the core stack is switched out in it (`rt_task_run`) |
| 6 | `aFmt0` | the formatting state (`ctxFmt`) at entry, given back at exit |
| 7 | `aCleanup` | the running task's cleanup chain (`tCleanup`) at entry |
| 8 | `aOut` | 1 after `rt_arena_out`: the context holds the parent's pool again |
| 9 | `aCharged` | pool bytes the arena charged to limit budgets (`rt_bnd_charge` notes them) |

`arenaWords = 10`. A per-core count `arenaLive` of open arenas keeps every check below off the
paths of programs without arenas.

## 3. Where a pool's words live (pool sharing)

A scope's children share their owner's pool (`rt_pool_words`, #232). An arena entered by
a task must not take that shared pool with it, so the words of every pool have exactly one
home while the code using them is not running:

- **the parent pool** (the one in use at entry): its usual home, `rt_pool_words(t)` (a task's
  own `tPool` words, its owner's for a scope child, `schedPool` on the core stack).
  `rt_arena_open` writes the context back there before it switches, and `rt_arena_out`
  loads it from there, so children that ran while the arena body waited are seen;
- **the arena pool**: the record's words 0-4.

`rt_task_run` loads the running task's pool words from `rt_pool_home(t)` (the innermost
arena entered by `t` itself and not yet switched out, on its boundary chain from `tBnd` up
to its root; else `rt_pool_words(t)`) and, after the task switches back, saves them at
`rt_pool_home(t)` again, computed then (the task may have entered or left arenas). The core
stack's own words go to `rt_pool_home(0)` (the same walk from `bndCur`, else `schedPool`).
With no arena open before or after the run this is `rt_pool_words(t)` and `schedPool`.

## 4. Functions (toolchain/runtime/runtime.tin)

| function | does |
|---|---|
| `rt_arena_open() i64` | enters a `bkArena` boundary, writes the context's pool words back to their home, gives the context a fresh empty pool (`ctxFmt` 0) and returns the boundary record |
| `rt_arena_run(body func(i64) !, r i64) i64` | `body(r)`, its fault as a word (0: none) |
| `rt_arena_out(b i64)` | runs the cleanups registered inside the arena, saves the arena pool in the record and loads the parent pool into the context; arena memory stays readable |
| `rt_arena_fault(f i64) i64` | `f` copied into the current (parent) pool, chain and identity kept (`rt_fault_copy(f, false)`); 0 stays 0 |
| `rt_arena_close(b i64)` | frees the arena pool, gives its charges back to limit budgets, leaves the boundary |
| `rt_arena_discard(b i64, f i64) i64` | leaving `b` on an unwind: switches to the parent pool if `rt_arena_out` has not run (without running cleanups: the unwind ran them), copies fault word `f` there, frees as `rt_arena_close` does without leaving (the caller unlinks the record) and returns the copy |
| `rt_arena_task_end(t i64, b i64)` | `rt_arena_discard` for task `t` ending by panic; a scope child's `spFault` is the fault copied |
| `rt_pool_home(t i64) i64` | where the pool words of task `t` (0: the core stack) live while it is not running (section 3) |

Copy helpers the compiler's generated `arenacopy$N` uses, the pool twins of `rt_keep_str`,
`rt_keep_raw`, `rt_keep_slice` and `rt_keep_map_new`: `rt_arena_str(s str) str`,
`rt_arena_raw(p, n) i64`, `rt_arena_slice(s, esz) i64` and `rt_arena_map_new(m) i64`
(a region-0 map with `m`'s key kind, filled by the copy).

## 5. What the compiler emits

`arena { body }` (edition 1) is a boundary block like `guard` and `limit`: the body becomes
a closure `func($r i64) !` whose last expression is stored through `$r`, and a generated
`arena$N(c)` runs it. A body that cannot fail (no `try` or `fail` leaves the closure) makes
the block's type its value's; one that can makes it `!T`, used with `try` or `catch`.

```
r := rt_alloc(16)                // the result cell, in the parent pool
b := rt_arena_open()
f := rt_arena_run(c, r)
rt_arena_out(b)
f = rt_arena_fault(f)
if f == 0 { r[0] = arenacopy$N(r[0]) }   // only for a value type that holds references
rt_arena_close(b)
```

`arenacopy$N(x T) T` deep-copies `x` into the current pool, as `keep$N` does into the ingot
heap. A value type that holds a func or dyn value, or a recursive type, is a compile error
(`E316 ARENA_VALUE`).

## 6. Unwinding

An arena has no landing of its own: `fail` and `try` leave its closure by returning. A panic
or a cancellation that passes through it is handled where boundaries are left on an unwind:

- `rt_land` (a guard, `limit` or `within` landing): for each `bkArena` it leaves, after
  the deferred calls and cleanups have run, `rt_arena_discard`. A fault that lands is copied
  into the parent pool first (`rt_arena_fault`), since it may have been made in the arena.
- `rt_bnd_task_end` (a task that ends by panic): `rt_arena_discard` for each arena of the
  task, innermost first, so `rt_task_abort` resets the task's own pool, not an arena's. A
  scope child's `spFault`, made in the pool it was using, is copied the same way.

## 7. The region rule (toolchain/compiler/region.tin)

Inside an arena's closure, and closures inside it:

- a captured variable reads as `RG_OUT` (bit 16) instead of `RG_FRESH`: it was made outside
  the arena. `RG_OUT` survives loads and holds, like the other non-fresh bits;
- slicing a slice that may be `RG_OUT` gives `RG_OUT` too: `ys := xs[a:b]` shares `xs`'s
  array, so `ys = append(ys, v)` with spare capacity would write into the outer array;
- storing a value that may be fresh (made in the arena) into a container that may be
  `RG_OUT`, or into a captured variable, is `E315 ARENA_ESCAPE`;
- appending to, or inserting into, a slice or map that may be `RG_OUT` (and is not only
  long-lived) is `E315 ARENA_ESCAPE` whatever the value: growth would allocate in the arena.
- calls are checked from three per-function tables, iterated with the other summaries:
  the parameters a function may grow (`rg_grows`), store its own fresh memory into
  (`rg_fstores`), and store another parameter into (`rg_pstores`), so `setLabel(mut box, s)`
  is an escape only when `s` is arena memory.
