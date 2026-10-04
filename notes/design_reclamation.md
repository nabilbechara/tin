# Reclaiming long-lived memory (#176): options and a recommendation

Status: **proposal, decision needed.** Nothing here is implemented. It assumes the mmap heaps
of #209 (Codex, phase 2 of #125), whose ingot heap gets a `free(block)` and a cross-core
return path; this note decides *when* the compiler and runtime call it.

## The problem

Request memory is wiped per request. Long-lived memory — globals and everything `keep()`
copies into the per-core ingot heap — is never freed:

- overwriting or deleting a map entry drops the old kept key and value;
- assigning a new kept value to a global, or a field or element of a kept object, drops the old one;
- `append` on a long-lived slice drops the old backing array when it grows;
- reloading configuration or replacing a cache leaks the old one entirely.

The audit measured one cache key overwritten per request growing RSS by the size of the value,
and a map churn reaching 1 GB. Any server with mutable state is eventually OOM-killed.

## What makes this tractable in Tin

1. **Long-lived data is acyclic.** `keep` rejects recursive types ("keep cannot copy the
   recursive type ..."), so kept graphs are trees or DAGs: reference counting cannot leak
   through cycles.
2. **Long-lived data is per core.** Globals are per core and cross-core mutable state is
   limited to `lib/` (atomics). A kept object is only ever reached by its own core's code, so
   any count needs no atomic instructions, and a deferred free only has to wait for tasks
   on that core.
3. **Every long-lived write is visible to the compiler.** The region pass already knows which
   stores go into long-lived memory (it is how it demands `keep`).
4. **Request code only borrows long-lived data.** A handler that reads `cache[k]` into a local
   holds a pointer into the ingot heap until its task ends; that is the one way a free can
   become a use-after-free.

## Options

### A. Ownership: a long-lived slot owns its value; overwrite frees the old one

`keep()` already produces a unique deep copy. If every long-lived slot owned its value
exclusively, an overwrite or delete could free the old value deeply (a generated `drop$T`,
the mirror of `keep$T`).

- Needs a new rule: storing a value *read from* long-lived memory into another long-lived slot
  (`g2 = g1`, `m2[k] = m1[k]`) is an error unless it goes through `keep()` (a copy), or the
  two slots would share and double-free.
- Locals that borrowed the old value still dangle: needs the epoch deferral below.
- Cost: zero per access; a deep free per overwrite.
- Breaking: code that shares long-lived values between slots must add `keep()`.

### B. Explicit `drop(x)`

A builtin that frees a kept value. Simple to implement, but with aliasing it double-frees, and
without a borrow checker it is a use-after-free in safe code: it contradicts LANGUAGE.md §17
("memory lifetime: the region check"). Rejected unless paired with A's rules, which make it
unnecessary.

### C. Arenas per owner

`a := arena.New(); cfg = a.Keep(load())`; replacing the arena frees everything in it (after the
epoch). Good for whole-structure replacement (config reload, router swap, TLS certificate
rotation), useless for a cache whose entries churn individually. Complements A or D; does
not replace them.

### D. Reference counts on long-lived objects (recommended)

Each ingot block gets a count of the **long-lived** references to it (request-memory locals are
not counted: they are borrows, covered by the epoch). The compiler emits, for each store into
a long-lived slot of a reference type, an increment of the new value and a decrement of the
old; a count reaching zero runs `drop$T`, which decrements the children and frees the block
through the epoch queue. `keep()` returns a block with count 0 that the store raises to 1.

- No language change, no new rules, existing programs keep compiling.
- Sharing is fine (`g2 = g1` counts two).
- No cycles (point 1), so nothing leaks.
- Per-core, non-atomic counts (point 2): an increment is one load-add-store on a line the
  core already owns.
- Cost only on long-lived writes, which are rare next to request work; request-pool code
  and reads are unchanged.

### The epoch deferral (needed by A, C and D)

A freed block is not reused at once. Each core counts request tasks started; a block freed
at count `e` goes to a per-core limbo list tagged `e`, and is released when every task that
started at or before `e` has finished (the oldest live task's start number passes `e`).
Code outside tasks (`main` loops, ticks, relay handlers) releases at `hearth.Reset()` or
at the end of the tick. This is what keeps `u := cache[k]; cache[k] = keep(v); use(u)` safe:
`u` stays valid until the task that read it ends.

- Bounded by the request deadline (30 s default): a stuck task cannot pin limbo for longer.
- A core with no tasks running frees immediately.

## Recommendation

**D + the epoch deferral**, with **C** added later for bulk replacement. D fixes the leak for
every existing program without new rules, and the per-core, acyclic structure of long-lived
data removes the usual costs of reference counting (atomics, cycle collection).

### Implementation sketch (after #209 lands)

1. Runtime: a count word in each ingot block header (or a side table per slab); `rt_rc_inc`,
   `rt_rc_dec` (inlined fast paths); per-core limbo lists and the task-start counter in the
   task runtime; release in the event loop and at `hearth.Reset()`.
2. Compiler: `drop$T` generated next to `keep$T` (`check.tin`); the region pass marks
   long-lived stores, and lowering wraps them (`old := slot; slot = new; inc(new); dec(old)`),
   including map set/delete (`rt_map_set`, `rt_map_del`), slice element stores into long-lived
   slices, and `append` regrowth on a long-lived slice (the old backing array is dropped).
3. Tests: a churn soak that must hold RSS flat (the audit's 8M-iteration map churn and the
   per-request cache overwrite), borrow-after-overwrite inside a waiting task, sharing between
   two globals, deep structures (maps of structs of slices), and `hearth.Reset()` releases.
4. Diagnostics (roadmap 14.1): per-core live ingot bytes and limbo size, exported for logs.

### Open questions for the maintainer

- Accept D's per-write cost, or prefer A's zero-cost model with the new aliasing rule?
- Is 30 s (the request deadline) an acceptable worst case for memory held in limbo?
- Should `cairn.LRU` (unusable in a global today, see the audit) be made long-lived-aware in the same change?
