# Interface: long-lived reclamation and sub-regions (#176)

Status: **fixed** (PR #260). Partners: #235, #236, #209 (Codex). Change anything here only
with their approval (AGENTS.md rule 5). Spec: notes/design_semantics.md §5,
notes/design_reclamation.md (PR #214, adopted).

## Ingot block header

Every block of the per-core mmap heap (lib/runtime/memory.tin) keeps its 16-byte header,
so payloads stay 16-byte aligned (docs/RUNTIME.md):

| word | at    | meaning                                                              |
|------|-------|----------------------------------------------------------------------|
| 0    | p-16  | the owning heap (never 0 on a heap block)                            |
| 1    | p-8   | the size word: bits 0-46 the requested size, 47-61 the count, 62 rcQ |

- The count is the number of long-lived references to the block (per core, not atomic).
  `rcPin` (all 15 count bits set) is sticky: a pinned block is never freed. `rcQ` is set
  only while the block waits in the limbo.
- Every reader of the size masks it with `rcSize` (2^47-1; `mem_alloc` caps sizes at
  2^46): `mem_drain`, `mem_free`, `mem_realloc` (an in-place growth keeps the count bits),
  `rt_memory_discard`. `mem_alloc` starts every block, fresh or reused, with a count of 0.

**What is counted.** `rt_rc_*` act only on blocks whose heap word is this core's heap
(`rt_rc_mine`: `(p-16)[0] == memoryHeap`). Static data, code pointers, request-pool memory
and other cores' blocks are never counted, so no static data needs a header.

## rc operations (lib/runtime/runtime.tin)

```
rt_rc_inc(p)                    // p gains one long-lived reference (dequeues a queued p)
rt_rc_dec(p, drop func(i64))    // p loses one; count 0 queues p for the epoch limbo
rt_rc_pin(p)                    // p is kept for good (a reference that cannot be counted)
rt_rc_pinned(p) i64             // rt_rc_pin(p), then p: a store's value, pinned in place
rt_rc_arr_n(p, esz) i64         // element count of a slice backing array block
rt_rc_stats() (blocks, bytes, limbo)  // per-core diagnostics (roadmap 14.1), hearth.RcStats
```

- `rt_rc_dec` never frees or drops at once: a count of 0 appends `[next, block, drop,
  epoch]` to the core's limbo FIFO. The block is memory-intact and its children are
  untouched until release, so a later `rt_rc_inc` (storing a borrowed value) revives it.
  A dec of a block with no count (never counted, or already queued) or a pinned block
  does nothing.
- Drop functions are compiler-generated next to `keep$N`: `drop$N(x T)` decs every
  counted reference inside x (struct and enum-variant fields, slice elements via
  `arrdrop$N(p i64)`, map entries via `rt_map_slots`, then `rt_map_release` frees the
  map's tables), and an opt drop narrows nil first.
- Counted kinds are str, slice, map, struct (enums are structs) and opt of those. Func
  values (code pointers and kept closures), faults and dyn objects are not counted: a
  block they hold is never freed by this machinery (leak, never corruption).

**Pinning.** A block is pinned when a reference to it cannot be counted:
- blocks made while a core initializes its globals (`rt_ingot_alloc` while `ctxIngot` is
  set): globals' initial values are stored without counts;
- values the compiler stores where it cannot count (see Compiler side).

## The epoch limbo

- Participants: the live tasks and the core's own stack. Each core has `epochNext` (the
  current epoch, the tag of anything queued now) and `coreQ` (where the core's own stack
  began at its last quiescent point). A full pool reset on the core's own stack
  (`rt_pool_reset` with no current task: the end of a request or tick in the event loop,
  `hearth.Reset()`, a helper's job) is a quiescent point: `epochNext++`, `coreQ = epochNext`.
  `rt_pool_scope_reset` is not one: the code around a scope may still hold borrows.
- A task joins the live list when it is made (`rt_task_new`, task words tEp/tEpNext/
  tEpPrev) with the epoch of its maker: the running task's, or `coreQ` on the core's own
  stack. So a child keeps whatever its maker could have handed it. It leaves the list
  when it ends (`rt_task_entry`, `rt_task_abort`) or is freed without running
  (`rt_task_free`). The list stays ordered by epoch.
- A block queued at epoch e is released (drop called, then freed) when `e < coreQ` and
  `e <` the oldest live task's epoch. Releases run at task end, at every pool reset and
  when `rt_poll_wait` returns. So a borrowed `u := cache[k]` stays valid until the request
  (or task) that read it ends, however the entry is replaced meanwhile.
- Known limit: a task that lives for a long time (a hijacked WebSocket, a `detach` loop,
  a request with no deadline) holds back every release on its core until it ends. A core
  whose own stack never reaches a quiescent point (a CLI program that never calls
  `hearth.Reset`) never releases: what it drops leaks, as before this interface.

## Maps and slices carry their own region

- Map header word 9 (`m[9]`) is 1 for an ingot map; word 13 holds the value drop and word
  14 the counted-side bits (bit 0 keys, bit 1 values). The map block is 120 bytes.
  `rt_map_make(isstr)` is unchanged; `rt_map_make_rc(isstr, drop, counted)` and
  `rt_keep_map_new(m, drop, counted)` carry the metadata. `rt_map_set`, `rt_map_setk` and
  `rt_map_del` count when `m[9] != 0`: an overwrite incs the new value, then decs the old
  one; a new entry incs a counted key and value; delete decs both. `rt_map_set`'s `dup`
  argument releases an incoming duplicate key only on the counted key side (str and
  encoded keys), never an int key's bits.
- Slice header word 3 (`s[3]`, the region): 0 pool, 1 long-lived, 2 a request-local view
  into a long-lived array. A long-lived header owns one count on its backing array
  (`rt_slice_make`, `rt_keep_slice`); `rt_slice_grow` decs the old array and incs the new
  one. A view (`rt_slice_sub` of a non-pool slice) never owns the array and never counts
  it; it grows into the pool (and becomes region 0). A value stored into a long-lived
  array or a view of one gains its slot's count: `rt_append_rc(s, v, esz)`,
  `rt_slice_appendn_rc(s, t, esz)`, and `rt_slice_copy_rc(dst, src, esz, drop)`, which also
  decs the values it replaces. The compiler lowers counted element types to these, and
  inlines `rt_append_rc`'s fast path like `rt_append`'s.

## Compiler side

- `keep$N` incs every reference it stores (a kept composite owns its fields, elements
  and entries), so a whole kept graph is consistently counted.
- After `region_check()`, `rc_mark` (selfhost/region.tin) visits every analyzable,
  reachable function except lifted ones and `__core_init`:
  - a store whose destination is provably long-lived (a global; a field or element whose
    base ident is a global or a local at exactly `RG_INGOT`) binds its value, reads the
    old one, incs the new value and decs the old (`drop$N`) before the store;
  - a store whose destination may be long-lived but is not provably so (through a
    parameter, a closure's cells, an element of an element) pins its value in place
    (`rt_rc_pinned`): the old slot may never have had a count;
  - a store into a container the region pass proved request-local (bits only
    `RG_FRESH | RG_EMB`) needs nothing;
  - `a, g = f()` incs the new and decs the old value of each counted global it assigns.
- `rc_inc_call`, `rc_dec_call` and `fn_ref_node` mark what they add reachable only once
  `rc_mark` runs: during checking the runtime's bodies are not resolved yet, and marking
  them early hid their callees from the reachability walk.

## Sub-regions (for #235/#236)

Boundary record word 18 (`bRegion`, 3 words, reserved by #231's interface) is the region
mark at entry: `limit { }` counts its sub-region's pool bytes there, `arena { }` marks a
discarded sub-region. Pool accounting stays on the pool (request memory is never
counted here); only the ingot free path, the limbo and the count bits above are this
interface.
