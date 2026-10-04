# Interface: long-lived reclamation and sub-regions (#176)

Status: **fixed** (this PR). Partners: #235, #236, #209 (Codex). Change anything here only
with their approval in this PR (AGENTS.md rule 5). Spec: notes/design_semantics.md §5,
notes/design_reclamation.md (PR #214, adopted).

## Ingot block header

Every block of the per-core mmap heap (lib/runtime/memory.tin) has a 24-byte header; the
payload pointer p is the block start plus 24:

| word | at    | meaning                                                     |
|------|-------|-------------------------------------------------------------|
| 0    | p-24  | the owning heap (never 0 on a heap block)                   |
| 1    | p-16  | the requested payload size in bytes                          |
| 2    | p-8   | rc: long-lived references to this block (not atomic, per core) |

`mem_alloc`/`mem_free`/`mem_realloc`/`mem_drain` class sizes on `size + 24`. `mem_alloc`
zeroes the rc word on every path (a freelist reuse must not inherit a stale count).

**Immortal objects.** Static data (Tin string literals, the shared empty slice header) and
code pointers are never counted. The writers (elf.tin, elf_x64.tin, macho.tin, gen.tin
`-S`) reserve 24 zero bytes immediately before each static Tin string and before the
shared empty slice, so a counted operation can test `(p-24)[0] == 0` and skip: one load,
one compare. `rt_rc_inc`/`rt_rc_dec` apply this test themselves.

## rc operations (lib/runtime/runtime.tin)

```
rt_rc_inc(p)                    // p gains one long-lived reference; skips immortals
rt_rc_dec(p, drop func(i64))    // p loses one; count 0 queues p for the epoch limbo
rt_rc_arr_n(p, esz) i64         // element count of a slice backing array block
rt_rc_stats() (blocks, bytes, limbo)  // per-core diagnostics (roadmap 14.1)
```

- `rt_rc_dec` never frees or drops at once: a count of 0 appends `[next, block, drop,
  epoch]` to the core's limbo FIFO. The block is memory-intact and its children are
  untouched until release, so a later `rt_rc_inc` (storing a borrowed value) revives it
  (the limbo entry is skipped on release).
- Drop functions are compiler-generated next to `keep$N`: `drop$N(x T)` dec (`rt_rc_dec`)
  every counted reference inside x (struct and enum-variant fields, slice element drop
  via `arrdrop$N(p i64)`, map entries via `rt_map_slots`), and `opt$N` narrows nil.
- Counted kinds are str, slice, map, struct (enums with payloads) and opt of those.
  **Not counted in this PR** (known gaps, leak not corruption): func values (top-level
  code pointers and kept closures), faults, dyn objects, bulk `append(s, t...)`.

## The epoch limbo

- Each core has `epochNext` (incremented at every task start) and a live-task list keyed
  by start epoch (task words tEp/tEpNext/tEpPrev).
- A block queued at epoch e is released (drop called, then freed) only when every task
  that started at or before e has finished; releases run at task end (`rt_task_entry`,
  `rt_task_abort`), at `rt_pool_reset` (request end, `hearth.Reset`) and when
  `rt_poll_wait` returns. This is what keeps a borrowed `u := cache[k]` valid while
  another request replaces the entry.
- Bounded by the request deadline: a parked task's wait fails at its deadline, so limbo
  cannot be pinned longer (a task that never waits again needs #234's safepoints).

## Maps and slices carry their own region

- Map header word 9 (`m[9]`) is 1 for an ingot map; word 13 holds the value drop and
  word 14 has counted-side bits (bit 0 keys, bit 1 values). The map block is 120 bytes.
  `rt_map_make` remains unchanged; `rt_map_make_rc(isstr, drop, counted)` and
  `rt_keep_map_new(m, drop, counted)` carry the metadata. `rt_map_set`,
  `rt_map_setk` and `rt_map_del` do the counting themselves when `m[9] != 0`: overwrite
  decs the old value, a new entry incs key (str keys) and value, delete decs both. No
  compiler marking is needed for maps: mixed-origin locals count correctly, because the
  map's own region word decides at runtime.
- A slice header word 3 (`s[3]`, the region) gates slices: an ingot slice's backing array
  holds one rc from its header (`rt_slice_make`, `rt_keep_slice` set it), and
  `rt_slice_grow` decs the old array. A sub-slice is a request-local view and does not
  count or own the shared backing array. `rt_append_rc(s, v, esz)` is `rt_append`
  plus the element inc, for counted element types.

## Compiler side

- `keep$N` now also incs every reference it stores (a kept composite owns its fields,
  elements and entries), so a whole kept graph is consistently counted.
- After `region_check()`, an rc pass (selfhost/region.tin, `rc_mark`) wraps stores whose
  destination is provably long-lived: an assignment to a global, and field, element and
  append stores whose base ident is exactly `RG_INGOT` (`S_REGION == RG_INGOT`, the
  region pass's bits) or a global. It reads the old value first, emits
  `rt_rc_dec(old, drop$N)`, `rt_rc_inc(v)` around the store. In `__core_init` every
  allocation is ingot or immortal, so stores there are inc-only (the target starts
  zero). Mixed-origin bases are skipped (leak, not corruption) and are the main known
  gap; `s[i] = v` with a non-simple index expression is inc-only for the same reason.

## Sub-regions (for #235/#236)

Boundary record word 18 (`bRegion`, 3 words, reserved by #231's interface) is the region
mark at entry: `limit { }` counts its sub-region's pool bytes there, `arena { }` marks a
discarded sub-region. Pool accounting stays on the pool (request memory is never
counted here); only the ingot free path, the limbo and the rc words above are this
interface.
