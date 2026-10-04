# Interface: boundaries and cancellation (runtime) — #231

Status: **proposed**, for approval by the members of the interface: #230 (unwinding), #232
(structured concurrency), #233 (`within`), #234 (safepoints), #235 (`limit`). Nothing builds on
it before each has approved the PR that adds this file (AGENTS.md, Tin 1 rule 5). After that, a
change to a name or a word below needs the same approvals.

Spec: `notes/design_semantics.md` §0 (the model), §3 (where a panic stops), §4 (one
cancellation mechanism), §5 (sub-regions), §6 (scopes). This file decides only the runtime
names and data layout that those sections leave open. It changes no rule there.

Neighbouring interfaces this one uses but does not define:

- **Fault representation (#229):** the reason a boundary is cancelled is a `fault` value, and
  the runtime raises the sentinels `fault.Canceled`, `fault.DeadlineExceeded`,
  `fault.LimitExceeded` and `fault.Draining`. Until #229 lands they are the plain message faults
  `"canceled"`, `"deadline exceeded"`, `"limit exceeded"` and `"draining"`; the message of
  `fault.DeadlineExceeded` must stay `deadline exceeded` (tests and `tools/ci` checks read it).
- **Memory: sub-regions (#176):** what a region mark is, and how a sub-region merges and is
  discarded. This file only reserves the words that hold the mark.
- **Policies (#237):** the language surface of `with bind(slot, v)`; this file gives its runtime
  storage.

---

## 1. What a boundary is at run time

A **boundary record** is a block of `bndWords` words owned by the core that made it. Every
running piece of work has a *current boundary*: a task has it in a new task word `tBnd`; code
on the core's own stack (`main`, initializers, the event loop) has it in the per-core variable
`bndCur`. Records form a tree per core:

```
core root (bkCore, one per core, made when the core starts; its own deadline is none)
 ├─ background (bkBackground): detach, ticks, relay handlers, on-handlers
 │   └─ task roots (bkTask)
 ├─ request roots (bkRequest): one per request task, made by anvil
 │   └─ block boundaries (bkGuard, bkWithin, bkLimit, bkScope, bkArena, bkWith)
 │       └─ task roots of spawned children (bkTask), whose parent is the scope
 └─ block boundaries entered by code on the core stack (main)
```

The tree never crosses cores (share-nothing): records are allocated, linked, cancelled and
freed by their own core only. The watchdog thread (#234) never reads a record; it reads only
the per-core context words of section 6.

### 1.1 Record layout

| word | name | meaning | written by |
|---|---|---|---|
| 0 | `bParent` | the enclosing boundary; 0 for a core root | enter |
| 1 | `bKind` | kind (low 8 bits, section 1.2) and flags (bits 8 and up) | enter |
| 2 | `bTask` | the task running in it; 0 on the core stack | enter |
| 3 | `bCancel` | cancel state: 0 = not cancelled, else the reason (a `fault`) | cancel |
| 4 | `bOrigin` | the boundary whose cancellation reached this one (itself if it was cancelled directly); 0 | cancel |
| 5 | `bDeadline` | effective deadline, mono ns: min(own, parent's); 0 = none | enter, set_deadline |
| 6 | `bDlOwner` | the boundary whose own deadline is the effective one; 0 | enter, set_deadline |
| 7 | `bLimit` | the innermost boundary with a budget, at or above this one; 0 = none | enter, set_limit |
| 8 | `bMemMax` | memory budget, bytes (0 = none); meaningful when `bLimit` is this record | #235 |
| 9 | `bMemUsed` | pool bytes taken inside it (section 5) | #235 |
| 10 | `bTaskMax` | task budget (0 = none) | #235 |
| 11 | `bTaskUsed` | live task roots inside it | #235 |
| 12 | `bSlots` | slot chain head, inherited from the parent at entry (section 7) | enter, bind |
| 13 | `bChild` | first child boundary | enter, leave |
| 14 | `bNext` | next sibling | enter, leave |
| 15 | `bPrev` | previous sibling (0: first child) | enter, leave |
| 16 | `bCleanup` | the task's cleanup chain head (`tCleanup`) at entry | enter |
| 17 | `bLand` | landing data for an unwind to this boundary, owned by #230 | #230 |
| 18–20 | `bRegion` | region mark at entry, owned by #176 | #176 |
| 21 | `bFault` | the fault an unwind landed with; read once by the landing code | #230 |
| 22 | `bOwnDl` | this boundary's own deadline (mono ns); 0 = none | set_deadline |
| 23 | — | reserved (0) | — |

`bndWords = 24` (192 bytes). Records come from a per-core free list (`bndFree`) of ingot
blocks and go back to it at leave, like task records; a boundary costs no pool memory, so its
record survives the discard of its own sub-region.

### 1.2 Kinds and flags

| kind | value | made by | flags |
|---|---|---|---|
| `bkCore` | 1 | the runtime, per core | `bfGuard` |
| `bkBackground` | 2 | the runtime, per core | — |
| `bkRequest` | 3 | anvil, per request task | `bfRoot`, `bfGuard` |
| `bkTask` | 4 | spawn, `parallel`, `detach`, `on`, ticks, relay handlers | `bfRoot`, `bfGuard` |
| `bkGuard` | 5 | `guard` | `bfGuard` |
| `bkWithin` | 6 | `within` | — |
| `bkLimit` | 7 | `limit` | — |
| `bkScope` | 8 | `scope` | — |
| `bkArena` | 9 | `arena` | — |
| `bkWith` | 10 | `with` (policies and `bind`) | — |

- `bfRoot = 256`: the root of a task. Unwinds never cross it (section 4).
- `bfGuard = 512`: a panic stops here (design_semantics §3: `guard` and the implicit guards).

### 1.3 Task word

`tBnd = 52`: the task's current boundary. `taskWords` becomes 53. `rt_task_new` sets it to 0;
`rt_bnd_task` (below) gives the task its root.

`tDeadline` (word 30) keeps its meaning for existing readers (`rt_task_wait`, `rt_helper_run`,
`seal`, `wire/dns_linux`, `postgres`): it is always the effective deadline of the task's current
boundary, `tBnd[bDeadline]`. Enter, leave and `rt_bnd_set_deadline` keep it equal.

---

## 2. Functions

All are per core and must be called on the owning core. `b` is a record address. A Tin
function cannot return `fault`, so the runtime passes faults out as words (a fault is a
pointer today; #229 keeps it one word) and callers `fail cast(fault, w)`. Until #229 lands,
`rt_wait_fault` recognises the deadline and budget reasons by their messages.

### 2.1 Entering and leaving

| function | does |
|---|---|
| `rt_bnd_current() i64` | the current boundary (`tBnd` of the running task, else `bndCur`) |
| `rt_bnd_core() i64` | this core's root |
| `rt_bnd_background() i64` | this core's background boundary |
| `rt_bnd_enter(kind i64) i64` | a new child of the current boundary, which becomes current. Inherits the deadline, `bLimit`, slots and, if the parent is cancelled, its cancel state and origin. Saves `bCleanup` and the region mark. |
| `rt_bnd_leave(b i64)` | normal exit of the current boundary `b`: unlinks it, makes its parent current, restores `tDeadline`, frees the record. The sub-region merges (nothing is copied or freed); for `bkArena` the caller discards it first (#236 through #176's functions). |
| `rt_bnd_task(t i64, parent i64, kind i64) !` | gives task `t` a root boundary (`bkRequest` or `bkTask`) under `parent`, before `rt_task_run(t)` first runs it. Counts toward `parent`'s task budget and fails with `fault.LimitExceeded` when it is full (#235); `t` does not start then. The root is left by the runtime when the task ends (normally or by panic). |

`rt_bnd_enter` and `rt_bnd_leave` must pair on every normal path; the compiler emits the
leave (it is the boundary block's own epilogue). On an unwind, #230's code leaves every
record above the target instead.

### 2.2 Deadlines

| function | does |
|---|---|
| `rt_bnd_set_deadline(b i64, at i64)` | sets `b`'s own deadline (`bOwnDl`, mono ns, 0 = none); `b` and every boundary inside it recompute `bDeadline` = min(own, parent's) and `bDlOwner`, and a task whose current boundary changed gets the new `tDeadline`. Usually called right after enter; anvil's Hijack calls it on a running request (`at = 0`). |
| `rt_bnd_deadline(b i64) i64` | the effective deadline (`task.Deadline()` reads it from the current boundary) |
| `rt_task_set_deadline(t, at)` | **kept**: sets the deadline of `t`'s root (anvil's request deadline; `at = 0` on Hijack) |

A deadline is a cancellation scheduled in advance: when it passes, the runtime calls
`rt_bnd_cancel(owner, fault.DeadlineExceeded)` on `bDlOwner`, from whichever notices it first
(a wait's timer, `rt_bnd_check`, or the poll of section 6).

### 2.3 Cancellation

| function | does |
|---|---|
| `rt_bnd_cancel(b i64, reason fault)` | if `b` is not cancelled: sets `bCancel = reason`, `bOrigin = b` on `b`, and on every descendant not already cancelled sets the same reason with `bOrigin = b`; ends the wait of every task waiting inside `b`'s subtree (`rt_task_interrupt`); sets `ctxWatch = -1` if the running task is inside it (section 6). The first reason wins; cancelling again does nothing. |
| `rt_bnd_canceled(b i64) i64` | the reason as a fault word, or 0. `task.Canceled()` is this on the current boundary, after `rt_bnd_check`. |
| `rt_bnd_check()` | cancels the deadline owner if the current effective deadline has passed (one clock read); used by `task.Canceled()` and after a wait ends by its deadline. |
| `rt_bnd_stopped() bool` | `rt_bnd_check()`, then whether the current boundary is cancelled: for code that reads `tDeadline` itself (DNS, PBKDF2, `postgres` budgets, `rt_helper_run`). |
| `rt_task_interrupt(t i64)` | ends any wait of `t` (fd, timer or park) as `waitDeadline` and queues `t` to run; does nothing if `t` is not waiting. Internal to cancel. |

**Direction.** `rt_bnd_cancel` writes only `b` and its descendants. Nothing in the runtime
cancels a parent or a sibling: "the first child fault cancels its siblings" is the scope
cancelling *itself* (`rt_bnd_cancel(scope, childFault)`, #232), which reaches the siblings as
its descendants. A drain is `rt_bnd_cancel(rt_bnd_core(), fault.Draining)` on each core (#238).

### 2.4 Waits

`rt_task_wait(fd, want, timeout) i64` keeps its signature and return codes. Two changes:

1. **At entry**, after `rt_bnd_check()`, a task whose current boundary is cancelled does not
   wait: it returns `waitDeadline` at once.
2. **While parked**, a cancel of an enclosing boundary ends the wait with `waitDeadline`
   (through `rt_task_interrupt`), the same code a passed deadline returns today. A wait ended by
   its deadline's timer calls `rt_bnd_check()` before returning, so the deadline owner is
   cancelled with `fault.DeadlineExceeded` and the state is set when the caller asks for it.

So `waitDeadline` (value 1) now means "the boundary stopped this wait": deadline, cancellation,
budget or drain. Every client already turns it into a fault and stops, so no client loops on
it. The fault to raise is new:

| function | gives |
|---|---|
| `rt_wait_fault() i64` | the fault (as a word: `fail cast(fault, rt_wait_fault())`) for a wait that returned `waitDeadline`, from the current boundary's reason: `fault.DeadlineExceeded` and `fault.LimitExceeded` directly; any other reason (an explicit cancel, a sibling's fault, `fault.Draining`) as `fault.Canceled` wrapping it (design_semantics §4). |
| `rt_wait_msg() str` | its message, for clients that build their fault later (`mysql`, `postgres`, `websocket`). |

The client change is one line per site, mechanical: `fail "deadline exceeded"` after a
`waitDeadline` becomes `fail cast(fault, rt_wait_fault())`. The sites are `wire/wire.tin`,
`wire/dns_linux.tin`, `redis`, `mysql`, `postgres`, `websocket`, `seal` (PBKDF2), `tide.Wait`
and `rt_helper_run`; the code that reads `tDeadline` directly also tests `rt_bnd_stopped()`. Helper-thread jobs already survive an abandoned
wait (`jGone`), so a cancelled task never resumes into a finished job.

On the core stack (no task), a wait cannot be woken by another task: it observes the deadline
through its timeout and the cancel state at entry only.

---

## 3. Values of a boundary block

A boundary block's value is what its body produced: a value, or the fault it left with
(`fail`, `try`, a client's `rt_wait_fault()`). A body that catches the cancellation's fault and
finishes normally finishes normally; the cancel state stays set, so its next wait fails again.
Only an **unwind** (section 4) gives the block a value the body did not produce: the fault in
`bFault`.

---

## 4. Unwinding to a boundary (agreed with #230)

#230 implements these; this file fixes their names and what they promise to the boundary side.

| function | does |
|---|---|
| `rt_unwind(target i64, f fault)` | never returns. Runs, innermost first, every defer and cleanup the running task registered after `target[bCleanup]`; leaves every boundary above `target` (discarding each sub-region through #176's mark in `bRegion`, then freeing the record); then resumes at `target`'s landing with `target[bFault] = f`. `target` must be in the running task's chain, at or below its root. |
| `rt_bnd_target(origin i64) i64` | where an unwind caused by `origin` stops: `origin` itself if it is in the running task's chain, else the running task's root (`bfRoot`). |
| `rt_bnd_guard() i64` | the nearest boundary with `bfGuard` in the running task's chain: where a panic stops. |
| `rt_bnd_poll()` | the slow path of a poll hit (#234): `rt_unwind(rt_bnd_target(o), rt_wait_fault())` where `o` is the current boundary's `bOrigin` (or its deadline owner, after `rt_bnd_check`). |

- **Where each unwind stops.** A panic: `rt_bnd_guard()`, with `fault.Panic` (#229, #230). A
  poll on a cancelled or expired boundary: `rt_bnd_target(origin)`, with the cancellation's
  fault. A wait never unwinds; it returns `waitDeadline` (section 2.4).
- **Task roots.** An unwind never leaves the task it runs in. When it stops at a root whose
  origin is above it (a child of a cancelled scope), the task ends with that fault as its
  result; the scope (#232) reads it from the root's `bFault`.
- **Panics in cleanups** end the process (design_semantics, #230).
- `rt_task_recover`, `rt_task_panicked` and `rt_task_abort` stay for anvil until #230 replaces
  them with the root's `bfGuard`; the boundary side does not depend on them.
- How a landing is saved (`bLand`) and how defers are registered on the cleanup chain is #230's
  decision. The boundary side needs only: `bCleanup` marks the chain, `bLand` holds whatever
  `rt_unwind` needs, and `bFault` carries the fault to the landing.

---

## 5. Budgets (agreed with #235)

- `rt_bnd_set_limit(b i64, mem i64, tasks i64)` right after `rt_bnd_enter(bkLimit)`: sets
  `bMemMax`, `bTaskMax` (0 = no bound), and `bLimit = b` for `b` and everything entered
  inside it.
- **Memory is charged per pool chunk, not per allocation:** the slow path that takes a new chunk
  or a big block (`rt_alloc_slow`) adds its size to `bMemUsed` of `bLimit` and of every limiting
  boundary above it (each record's parent's `bLimit`); a discard subtracts what it frees. The
  bump fast path of `rt_alloc` is unchanged.
- **Exceeding cancels; it never unwinds from the allocator.** The allocation succeeds,
  `rt_bnd_cancel(limitBoundary, fault.LimitExceeded)` runs, and the work stops at its next
  wait or poll. (Unwinding inside `rt_alloc` would leave runtime structures half-built.) A
  request-wide budget (`TIN_REQUEST_MEMORY`) is the same budget on the request root.
- **Tasks** are counted at `rt_bnd_task` (a fifth spawn in `limit tasks 4` fails with
  `fault.LimitExceeded`) and released when the task's root is left.

---

## 6. Per-core context words for polls and the watchdog (agreed with #234)

The context block has spare words 12–31 (`ctxWords` stays 32; global offsets do not move).

| word | name | meaning | written by | read by |
|---|---|---|---|---|
| 12 | `ctxPoll` | nonzero: the next poll calls `rt_bnd_poll` | the watchdog (set); the core (clear, at every switch) | the compiled poll (one load, one predicted branch) |
| 13 | `ctxWatch` | the running task's effective deadline (mono ns), 0 = none, -1 = its boundary is cancelled | the core, at every task switch, enter, leave and cancel | the watchdog |
| 14 | `ctxRunGen` | counts task switches on this core | the core, at every switch | the watchdog |

- **Polls are the backstop, waits come first.** The watchdog arms `ctxPoll` only for a task
  that is still running, without having switched (`ctxRunGen` unchanged), one watchdog period
  after its `ctxWatch` deadline passed or it was cancelled. Code that handles a cancelled wait's
  fault therefore finishes its work (its next wait fails at once) instead of being unwound in
  the middle of it, and a task that never waits is still stopped within a period or two.
- Only the watchdog sets `ctxPoll`; the core clears it at every task switch. Nothing else
  arms a poll, so a poll never fires in a task that has just been resumed from a wait.
- Context words are written by the watchdog thread and read by the core: plain aligned word
  stores and loads (atomic on both CPUs); the watchdog never writes anything else.

---

## 7. Slots (runtime side of `bind`, #237)

- A slot key is the address of a per-program static word the compiler emits for each `slot`
  declaration. A binding is a node `[next, key, value]` allocated in the binding boundary's
  region; `bSlots` points to the newest. A child boundary starts with its parent's `bSlots`, so
  the chain is persistent and spawned tasks see their scope's bindings.
- `rt_slot_bind(key i64, value i64)` prepends a node to the current boundary (a `bkWith`
  entered by `bind`). `rt_slot_find(key i64) i64` returns the newest node for `key` on the
  current boundary's chain (value at word 2), or 0 when unbound (the language makes that a
  fault). Bindings vanish with their boundary; a value must be valid for the boundary's region,
  which the region checker proves (design_foundations §4).

---

## 8. Costs

- Entering and leaving a block boundary: a free-list pop and about fifteen stores; no pool
  memory, no system call. A request pays one root (`rt_bnd_task`).
- `rt_task_wait`: one extra load and branch at entry (the cancel state); `rt_bnd_check` reads the
  clock only when the task has a deadline.
- Allocation: nothing on the bump path; one branch per new chunk when no limit is set.
- Polls and the watchdog are #234's, measured on Linux before they are on by default.

The implementation PRs of #231 change `rt_task_wait` and the request path, so they carry
bench-linux numbers (AGENTS.md).

---

## 9. Who implements what

| piece | issue |
|---|---|
| Records, enter/leave, `rt_bnd_task`, deadlines, `rt_bnd_cancel`, `rt_task_interrupt`, `rt_wait_fault`, waits, the client one-liners, anvil's request root, slots storage | #231 |
| `rt_unwind`, `rt_bnd_target`, `rt_bnd_guard`, landings, defers on the cleanup chain, `fault.Panic` | #230 |
| `scope`, spawn on `rt_bnd_task`, sibling cancel through `rt_bnd_cancel(scope, f)`, `detach` under the background | #232 |
| `within` on `rt_bnd_enter(bkWithin)` + `rt_bnd_set_deadline`; request deadline on the root; `task.Deadline()`, `task.Canceled()` | #233 |
| `ctxPoll`/`ctxWatch`/`ctxRunGen`, the compiled poll, the watchdog, `rt_bnd_poll` callers | #234 |
| `rt_bnd_set_limit`, chunk charging, task counting, `TIN_REQUEST_MEMORY` | #235 |
| Region mark in `bRegion`, merge and discard | #176 (MEM interface) |
| Drain as `rt_bnd_cancel(core root, fault.Draining)` | #238 |
