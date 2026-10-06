# Design: the server semantics of Tin (written 2026-10-04)

Status: **decided**, pending the maintainer's review. This document gives one model for what
the design brief (`Tin_Language_Design_Brief.md`) asks the language and runtime to know:
failure, panics, cancellation, deadlines, limits, tasks, memory ownership, sensitive data,
server lifecycle and production replay. It decides each feature the brief approved, in terms
of that model.

**It is about meaning, not spelling.** Examples use today's Tin syntax so they can be read
now, but the surface syntax is a separate decision (a later `design/design_syntax.md`); a
redesign of the syntax changes no rule below. Where a name is new, it is a working name.

**Relation to `design/design_foundations.md`.** That document stays the base: closures, shapes,
fault chains, `guard`, ambient deadlines and slots, scopes and `spawn`, `lane[T]`, atomics,
derivation and packages are kept as decided there. Section 14 lists the four places this
document changes it.

---

## 0. The model in one page

Every piece of running work is a **task**, and every task belongs to exactly one **boundary**.
Boundaries nest, from the process down to a block inside a handler:

```
process
 └─ server                         lifecycle: STARTING → RUNNING ⇄ OVERLOADED → DRAINING → STOPPED
     └─ core (one per CPU)          per-core globals; the core's background boundary
         ├─ background boundary     long-lived work: detach, ticks, relay handlers, on-handlers
         └─ request boundary        one per HTTP request (a task with its own pool)
             └─ block boundaries    within, limit, guard, scope, arena, with-policies
                 └─ child tasks     spawned in a scope
```

A boundary owns five things, all inherited by what it contains unless it narrows them:

| owns | meaning | narrows by |
|---|---|---|
| **region** | the memory made inside it | `arena` (a sub-region that is dropped), `scope`/`guard` (a sub-region that merges) |
| **deadline** | the instant its work is cancelled | `within d` (the earlier of the two wins) |
| **cancellation** | whether its work has been told to stop, and why | `s.cancel(reason)`, a child's fault, a deadline, a limit, the drain |
| **budget** | memory, task count, queued work it may use | `limit` |
| **slots** | typed ambient values (request id, user) | `with bind(slot, v)` |

Four rules make the features compose instead of being islands:

1. **Cancellation flows down, never up or sideways.** Cancelling a boundary cancels everything
   inside it; nothing inside can cancel its parent except by returning a fault.
2. **A deadline is a cancellation scheduled in advance; an exceeded budget is a cancellation
   triggered by use.** There is one mechanism (section 4), with three causes.
3. **Leaving a boundary early is an unwind:** `defer`s run innermost first, then resource
   cleanups, then the boundary's sub-region is discarded. A fault, a cancellation and a panic
   all leave the same way; they differ only in where they stop (section 3).
4. **Memory never outlives its boundary** unless it is `keep`-copied to the long-lived heap (or
   copied out of an `arena` as the block's result). The region checker proves it at compile time
   (section 5).

The rest of this document is these rules applied to each feature.

---

## 1. Three kinds of failure

| kind | examples | how it travels | who handles it |
|---|---|---|---|
| **Fault** (expected) | not found, connection refused, timeout, bad input | a value: `!T` results, `try`, `catch`, `fail` | the caller, explicitly |
| **Panic** (a bug) | index out of range, divide by zero, `panic(...)`, broken invariant | an unwind | the nearest `guard`, the request boundary, or a task root |
| **Process failure** | SIGKILL, kernel OOM, machine loss, a stack overflow outside a task or a guard | none | infrastructure (restart, replay of the last capsules) |

- A fault is never discardable (as today). A panic is never a fault until a `guard` converts it,
  and ordinary code cannot catch one: the control flow of non-boundary code stays visible.
- **Stack overflow** in a task or a guard block is a panic (#342): the fault handler redirects
  the interrupted context to a function on the signal stack that panics, which unwinds as any
  panic does. Outside them (`main`, the core's own stack) it is a process failure that prints a
  panic line and exits 2 (#175).
- **Out of memory.** Exceeding a `limit`'s memory budget or the request's budget is a
  cancellation (`fault.LimitExceeded`), contained like any other. The operating system refusing
  memory is a process failure.

---

## 2. Faults

Kept from design_foundations section 3 (chains, sentinels, `wrap`, `fault.Is`, `Join`, no
`As`, structured results are enums). Added here:

**Standard sentinels**, defined by the runtime, used by every library, testable with `fault.Is`:

| sentinel | raised by |
|---|---|
| `fault.Canceled` | a wait in a boundary that was cancelled (its cause is the reason, below) |
| `fault.DeadlineExceeded` | a deadline (request deadline or `within`) |
| `fault.LimitExceeded` | a `limit` budget, a request budget, a bounded value too large (section 8) |
| `fault.Overloaded` | admission refused by load shedding (section 11) |
| `fault.Draining` | the cause of cancellations during a drain |
| `fault.Panic` | a panic converted by `guard`; carries the message and backtrace |

**Matching.** `switch` over a fault compares cases with `fault.Is`, so the brief's `match` is the
existing `switch`:

```
user := LoadUser(id) catch err {
	switch err {
	case ErrNotFound:            // fault.Is(err, ErrNotFound): walks the chain
		return out.Status(404)
	case fault.DeadlineExceeded, fault.Overloaded:
		return out.Status(503)
	default:
		return out.Status(500)
	}
}
```

HTTP status codes never live in faults (brief section 33): the mapping is at the HTTP layer.

---

## 3. Panics and `guard`

**Decision.** `guard` is a boundary that converts a panic inside it into the fault
`fault.Panic`. It is a block (and keeps design_foundations' expression form `guard CALL`
as the same thing on one call):

```
res := guard {                    // type !T
	render(page)
}
```

- On a panic inside: unwind (rule 3: defers, cleanups, the guard's sub-region discarded), then
  the guard's value is a `fault.Panic` fault carrying the message and backtrace. Handle it with
  the usual `catch`. There is no separate `recover` clause: one fault mechanism (this replaces the
  brief's `guard { } recover err { }`).
- On success the sub-region merges into the enclosing one with no copy.
- **Implicit guards:** every request boundary, every task root (a spawned child, a detached task,
  an `on` handler) and every tick/relay handler is guarded by the runtime. A panicking handler
  is a logged 500 and the server keeps running (built, #200, without unwinding yet).
- **Where a panic stops:** at the nearest `guard` or implicit guard. `within`, `limit`,
  `scope`, `arena` and `with` boundaries let it pass, running their defers on the way.
- **What is not rolled back:** writes to long-lived memory (globals, kept data) made before the
  panic. A guard restores memory ownership, not data invariants. Code that must keep an
  invariant across a panic updates long-lived state last, after the work that can fail.

---

## 4. Cancellation, deadlines and budgets: one mechanism

**The cancellation record.** Every boundary has a cancel state: `nil`, or a fault (the reason).
Cancelling a boundary sets its state and that of every boundary and task inside it.

**How cancellation is observed.**

1. **At a wait.** Every wait in the runtime goes through one function (`rt_task_wait`). A task
   whose boundary is cancelled wakes, and the wait returns its reason as a fault
   (`fault.Canceled` wrapping the cause, or `fault.DeadlineExceeded` / `fault.LimitExceeded`
   directly). Clients (`wire`, `redis`, `mysql`, `postgres`, `websocket`, `tide`, files) need no
   change: they already return the wait's fault.
2. **In CPU-bound code: safepoints.** The compiler inserts a poll on every loop back-edge and
   function entry of code that can run in a task: one load of a per-core word and a predicted
   branch. A **watchdog** (one thread per process, waking every millisecond) sets that word
   when a core's running task has passed its deadline or been cancelled. The poll then **unwinds**
   to the boundary that owns the cause, which turns it into the fault. So `within 200ms { tight
   loop }` really stops after about 200 ms, and a stuck handler cannot hold its core forever.
   - The poll is the price of the guarantee. It is measured on the Linux benchmarks before it
     is turned on by default (the AGENTS.md rule), and a function can opt out
     (`@nopoll`, for proven-short kernels) — the only opt-out.
   - An unwind from a poll is the same as a panic's (rule 3) but stops at the boundary that owns
     the deadline or budget, not at a `guard`.

**Where a cancellation stops.** At the boundary whose deadline, budget or `cancel` caused it.
There it becomes that boundary's fault. Above it, the work continues normally with the fault as
a value.

**Deadlines.** `within d { }` is a boundary whose deadline is `min(now + d, enclosing deadline)`.
Every request has the server's deadline (`TIN_DEADLINE_MS`, default 30 s). A task started by
`main` has none. There is no other way to set a deadline: the brief's `limit { time }` is `within`.

```
profile := try within 200 * tide.Millisecond {
	try api.Profile(id)
}
```

**Explicit cancellation.** `s.cancel(reason)` on a scope, `t.Cancel()` on a spawned task's
handle. There is no `cancel` keyword: a cancellation always names what it cancels.

**Reading it.** `task.Canceled() ?fault` reads the current state without waiting (for code that
wants to stop at a better point than the next poll), and `task.Deadline()` gives the instant.

---

## 5. Memory and lifetimes

Kept: regions, `keep`, the region checker (design_foundations principle 4, LANGUAGE.md §10).
Decided here:

**Sub-regions.** A boundary may have its own region:

| boundary | sub-region | on normal exit | on unwind |
|---|---|---|---|
| request | the request pool | reset after the response | reset |
| `guard`, `scope`, `within`, `limit`, `with` | yes | **merges** into the parent (no copy) | discarded |
| `arena` | yes | **discarded**; the block's result is copied into the parent region | discarded |

- `arena { }` is the brief's `scope temp { }` (renamed: `scope` is the concurrency boundary,
  section 6). It is for large temporaries outside a request: parsing a big file, a batch step.
  The region checker forbids a value made in the arena from being stored anywhere outside it,
  except as the block's result, which the compiler copies out (like `keep`, but into the parent's
  region).
- `limit { memory n }` counts the bytes its sub-region (and the sub-regions inside it) take
  from the pool; passing `n` cancels the boundary with `fault.LimitExceeded` (section 4).

**Long-lived memory is reclaimed** (#176). Decision: **per-core reference counts on long-lived
objects, with an epoch deferral** (the recommendation of PR #214,
adopted):

- A store into a long-lived slot (a global, a field or element of a kept object, a map entry)
  increments the new value's count and decrements the old one's; a count reaching zero runs the
  type's generated `drop`, which decrements its children.
- Counts are per core and not atomic: long-lived objects never cross cores (share-nothing).
- Kept data has no cycles (`keep` rejects recursive types), so counting reclaims everything.
- A block whose count reaches zero waits in the core's limbo until every task that started before
  it has finished (an epoch), so a request that read `u := cache[k]` keeps a valid `u` even if
  another request replaced `cache[k]` meanwhile. The wait is bounded by the request deadline.
- Request-pool memory pays nothing; reads pay nothing.

**`once`.** Runs its block the first time it is reached **on each core** (globals are per core,
so this is the natural unit). Process-wide one-time work is `on app.start` (section 10), which
runs once before the cores start. There is no third form.

---

## 6. Structured concurrency

Kept from design_foundations section 5: `scope s { s.spawn(f) }` is the primitive. Children run
on the parent's core, cooperatively, share the parent's region, and cannot outlive the scope.
The first child fault cancels its siblings and becomes the scope's fault. `lane[T]` is the
bounded queue between tasks on a core; `relay` connects cores.

Decided here, for the brief's constructs:

| brief | decision |
|---|---|
| `task` | `s.spawn(f)` inside a `scope`. The task handle has `Wait() !T` and `Cancel()`. |
| `parallel { a; b }` | **kept, as the one convenience form:** each expression runs as a child of an implicit scope; the value is the tuple of results; the first fault cancels the rest. `user, orders := try parallel { db.User(id); db.Orders(id) }` |
| `await all` | **dropped.** Tin has no futures: a task parks anywhere and no function is `async`, so there is nothing to await. `parallel` is the wait-for-all. |
| `cancel x` | a method on what is cancelled: `s.cancel(reason)`, `t.Cancel()`. |
| `select` | **kept as the syntax over `wait.First`:** the first ready case wins, the other registrations are withdrawn, ties go to the first case in source order (deterministic, which replay needs). Cases are waits: `lane.Recv()`, `t.Wait()`, `after(d)`, `canceled()`. |
| `detach` | **allowed, with an owner** (this changes design_foundations, which rejected it): `detach { }` spawns into the **core's background boundary**, never "nowhere". Everything it captures must be long-lived: the compiler requires `keep` for request memory, as for a global. It has its own pool, is guarded like a task root, and is cancelled with `fault.Draining` when the server drains. This is design_foundations' `hearth.Background(f)` with a keyword, because the brief is right that a lifetime change should be visible at the site. |
| `race` | not added: `select` over two `t.Wait()` is the race. |

**Ordering on a core is deterministic given the events:** tasks switch only at waits, safepoint
unwinds, `yield` and task end, in queue order. With the events recorded, a request's concurrency
replays exactly (section 12).

---

## 7. `with`, `use`, `on`: the three composition forms

### 7.1 `with`: a policy around a block

A policy is any value whose type satisfies

```
shape Policy[T] { Run(body func() !T) !T }
```

and `with p { body }` calls `p.Run(body)` with the block as a closure that never outlives the
call (the frame-local closure rule, so the body may use request memory freely). Its type is
`!T`. Static dispatch: a policy is a type parameter, not a `dyn`, unless written `dyn`.

```
payment := try with retry(3) {
	try stripe.Charge(card, amount)
}
```

- Inside the block, `return`, `break` and `continue` that would leave the block are compile
  errors. The block's value is its last expression; `fail` and `try` leave it with a fault.
  (Non-local return through a closure is the one thing that would make policies surprising.)
- A policy may run the body several times (retry); side effects run again. The library documents it.
- **Runtime-backed policies** use the same protocol: `with bind(requestID, "r-81") { }` sets a
  slot for the block and its children (this replaces design_foundations' `with requestID = v`
  syntax; same semantics). `retry`, `cache`, `memo`, `transaction`, `circuitBreaker`,
  `rateLimit`, `idempotent`, `bulkhead`, `trace` are library policies, never keywords.
- `within`, `limit`, `guard`, `scope` and `arena` stay keywords, because they are boundaries
  the compiler and runtime must understand (unwinding, regions, the watchdog), not policies a
  library could write.

### 7.2 `use`: a resource bound to a scope

```
use db = postgres.Open(cfg.DB)          // package level: one per core
func migrate() ! {
	use tx = db.Begin()                 // function level
	...
}
```

A resource is a value whose type satisfies `shape Resource { Close() ! }`, made by a call of type
`!T`.

- **Function level:** `use x = e` is `x := try e` plus a `defer` that closes it; a fault from
  `Close` is joined into the function's fault.
- **Package level:** opened on each core when the core starts (per-core, like every global),
  closed when the core stops after the drain. A fault while opening aborts startup with the
  message, before the server accepts anything.
- `use` is never "global forever": every resource has a scope, visible where it is declared.

### 7.3 `on`: typed events

```
on app.start { try migrate() }          // once per process, before the cores start
on core.start { warm() }                // on each core
on server.overload { metrics.Inc(overloads) }
on app.stop { within 5 * tide.Second { telemetry.Flush() } }
```

- An event is a typed value declared by the runtime or a library (`app.start`, `app.stop`,
  `core.start`, `core.stop`, `server.overload`, `server.recovered`, `signal(SIGHUP)`); no
  strings.
- A handler runs as a task in the background boundary of its core (process events on core 0),
  guarded, with no deadline unless it sets one. Handlers of one event run in declaration order.
- A fault from an `on app.start` handler aborts startup; elsewhere it is logged.

---

## 8. Bounded values

**Decision.** A bounded type is a **refinement** checked where data enters, not a dependent type
carried through arithmetic: `str max 100`, `[]Item max 1000`, `[]u8 max 1 * mib`.

- A bounded value is produced at a boundary that enforces it while reading: JSON decoding into a
  bounded field, `q.Body()` into a bounded type, `bound(x) !T` for any value. Too large is
  `fault.LimitExceeded`, and readers stop reading at the bound instead of after it.
- A bounded type is assignable to its unbounded type. The reverse needs `bound`. Operations that
  could grow a value (`append`, concatenation) produce the unbounded type.
- The compiler uses bounds to preallocate exactly and to prove request memory budgets; tooling
  uses them to generate fuzz inputs.
- Field bounds are written with the type (`name str max 100`), so `argo`, validation and
  database row mapping read them through derivation (design_foundations section 7).

---

## 9. `secret`

**Decision.** `secret T` is a type qualifier. The compiler tracks it; the runtime never sees it.

- **Sinks reject it at compile time:** formatting (`say`, logging), JSON encoding, fault
  messages (`fail`, `wrap`, interpolation into a fault), panics, metrics labels, replay capture,
  and any library parameter not declared `secret`. The diagnostic names the value and the sink.
- **Propagation:** an expression with a secret operand is secret (concatenation, interpolation,
  slicing, a struct literal with a secret field makes that field secret). `len(s)` is not secret.
  Comparison of two secrets must use `seal.Equal` (constant time), not `==`.
- **Declassification is explicit:** `reveal(x)` gives `T`. The compiler can list every `reveal`
  in a program (`tin audit secrets`), so review knows where secrets leave.
- **Libraries opt in:** a function that must use the value (an HTTP auth header setter, a hash,
  a database password) declares `secret` parameters; it is then responsible for not leaking it,
  and is reviewed as such.
- **Replay** stores a keyed hash of each secret (section 12), never its text.

---

## 10. Server lifecycle

```
STARTING ──▶ RUNNING ◀──▶ OVERLOADED
                │              │
                └──────┬───────┘
                       ▼
                   DRAINING ──▶ STOPPED
```

- **STARTING:** `on app.start` handlers, then package-level `use` and `on core.start` on every
  core. Any fault aborts with its message and status 1.
- **RUNNING / OVERLOADED:** admission (section 11) decides each new request; `server.overload`
  and `server.recovered` fire on transitions, with hysteresis.
- **DRAINING:** started by SIGTERM/SIGINT or `server.Drain(d)`. The listeners close; idle
  keep-alive connections close; in-flight requests continue; at `d` (default `TIN_GRACE`, 25 s)
  every remaining request and background task is cancelled with `fault.Draining`. A second
  signal stops at once. (The first half is what anvil does today; cancellation at the deadline
  replaces today's `exit`.)
- **STOPPED:** `on core.stop`, package-level `use` closes, then `on app.stop` handlers, each with
  the deadline it sets itself (`within`). Then exit 0.

The brief's `drain server within 10s` is `server.Drain(10 * tide.Second)`, and `grace 5s { }` is
`within 5s { }` inside `on app.stop`. Neither is a keyword.

---

## 11. Overload: admission, shedding, backpressure

**Decision.** The runtime measures, a policy decides, the runtime enforces. No `shed` keyword.

- **Signals** (per core, cheap to read): waiting requests, live connections, bytes buffered for
  partial requests, request-pool bytes in use, event-loop lag (how late the loop wakes), and the
  long-lived heap size.
- **Admission policy:** `anvil.Admit(func(l anvil.Load) bool)`, called before a new request's
  handler runs; refusal is 503 with `Retry-After`, counted, and does not allocate. The default
  policy is today's built-in limits (4096 waiting, the connection cap, the buffering budget).
- **Backpressure is the default:** every queue is bounded (`lane[T]` needs a capacity; the
  server's limits bound connections and buffers). Full queues say what happens at the call:
  `Send` waits, `TrySend` returns `false`; dropping is a library policy.
- `fault.Overloaded` is what clients inside Tin see when a downstream Tin service sheds.

---

## 12. Production replay

**Promise.** A request recorded in production can be run again, locally or in CI, against any
build, with every external effect served from the recording and none performed.

### 12.1 Effects: what is recorded

An **effect** is anything whose result does not follow from the program and its input:

| effect | recorded at |
|---|---|
| network calls (HTTP client, Redis, MySQL, PostgreSQL, WebSocket) | the library client's call: the request and the reply or fault |
| files, DNS | the `quarry` and `wire` calls |
| clock | `tide.Now`, `tide.Since` |
| randomness, ids | `dice`, `seal.RandomBytes`, uuid |
| scheduling | the winner of each `select`, the order tasks resumed in, cancellations and their causes |
| the request | method, path, headers, body (secrets and policy-excluded headers replaced) |

**Why this is complete without an `external` keyword:** user code cannot reach the operating
system except through the standard library (C calls are limited to `lib/`, and package
capabilities (#146) make that a checked rule). Every effect therefore passes through a library
function that records it. A package with the `unsafe` capability is marked *not replay-safe*.

The runtime provides one hook, `rt_effect(kind, key, body)`: recording, it runs `body` and
appends `(seq, kind, key, result)`; replaying, it returns the recorded result for the next
`(kind, key)` and never runs `body`.

### 12.2 Capsules

- A capsule is the request plus its ordered effect log, versioned (the Tin version and a schema
  per effect kind), written by the runtime to a local spool directory with a size bound
  (ring buffer).
- **What is captured:** every request that ends in a 5xx or a panic, plus a sampled fraction of
  the rest (`TIN_REPLAY_SAMPLE`, default 0). Off unless a spool directory is set.
- **Secrets** are stored as keyed hashes (HMAC with a key from the environment). On replay a
  secret is a deterministic stand-in with the same hash. Fields and headers can be excluded by
  policy (PII).
- Capsules are encrypted at rest with a key from the environment. Shipping them anywhere is
  operations, not runtime.

### 12.3 Replaying

`tin replay CAPSULE [--against BUILD]` runs the handler with every effect served from the
capsule.

- **Divergence:** if the new code asks for an effect the recording does not have (a different
  call, or a different order), replay stops and reports the first divergence. It never falls
  through to a live call. `--live KIND` opts one effect kind into real calls, explicitly.
- **Concurrency:** scheduling decisions are replayed, so a request with `parallel` and `select`
  takes the same path (section 6).
- `tin replay CAPSULE --save-test NAME` turns a capsule into a regression test that CI runs.
- **Compatibility:** a capsule replays on later Tin versions while its effect schemas are
  supported; an unsupported schema is a clear error, not a wrong replay.

---

## 13. Smaller decisions

- **Effects and purity.** No function-level `uses db, network` declarations and no `pure`
  keyword in this version. The compiler *infers* each function's effects (which effect kinds it
  can reach) and reports them in tooling; replay and reviewers use the inferred set. Package
  capabilities (#146) are the enforced rule. Declared effects can be added later if inference
  proves insufficient.
- **Core-local and shared state.** Globals are per core by default (as today); there is no
  `core` keyword. `shared` is limited to atomics and to data built before the cores start and
  only read after (`shared let`); cross-core messages are typed `relay.Port[T]`. No `send`
  keyword.
- **Observability.** The runtime exposes the request id (a slot), the task id, the core, the
  deadline, the cancel cause, pool bytes and the replay id to libraries. Logging, metrics and
  tracing are libraries; `trace` is a `with` policy.
- **Diagnostics.** Every compiler error gets a stable code and a name (`E310 REQUEST_ESCAPE`),
  the rule, the location and one or two fixes, as the brief's section 49 shows. Codes are
  documented and never reused.

---

## 14. What this changes in design_foundations.md

1. **`detach` exists** (section 6), owned by the core's background boundary, with kept
   captures. design_foundations rejected detached tasks because they could not be made
   region-safe. Owning them by a long-lived boundary and requiring `keep` makes them safe, and the
   brief asked for the lifetime change to be visible.
2. **`with` is the policy form** (section 7.1). Slot binding is the policy `with bind(slot, v)`,
   not `with slot = v`.
3. **`guard` is a block boundary** (section 3) that yields a `fault.Panic` fault. The expression
   form `guard CALL` remains as shorthand.
4. **CPU-bound code is cancelled by safepoints** (section 4). design_foundations had only
   `task.Canceled()` polling by hand, which left `within` unenforced on code that never waits.

Everything else there is kept.

---

## 15. What is out (and why)

| brief item | decision | why |
|---|---|---|
| `await all` | out | no futures in Tin; `parallel` is wait-for-all |
| `limit { time }` | out | `within` is the deadline |
| `grace` | out | `within` inside `on app.stop` |
| `drain` (keyword) | out | `server.Drain(d)` and SIGTERM |
| `shed` (keyword) | out | admission policy + runtime signals |
| `cancel` (keyword) | out | a method on what is cancelled |
| `guard { } recover err { }` | replaced | `guard` yields a fault; handle it with `catch` |
| `scope temp { }` as an arena | renamed `arena` | `scope` is the concurrency boundary |
| `uses ...`, `pure fn` | deferred | inferred effects first; package capabilities enforce |
| `core`, `send` | out | per-core is the default; `relay.Port[T]` |
| `external` | stays rejected | effects are found at library boundaries |
| `race` | out | `select` over task waits |

---

## 16. Order of work

Each step is one or more PRs with tests on all three targets (and Linux numbers for anything
on a hot path, AGENTS.md). A step starts when what it needs has merged.

| # | step | needs | PRs (est.) |
|---|---|---|---|
| 1 | Fault chains and sentinels (design_foundations 3); `switch` over faults | — | 2 |
| 2 | Unwinding: defers and cleanups on panic; `guard` blocks; implicit guards with defers | 1 | 2 |
| 3 | Boundary records: cancel state, deadline, budget, slots per boundary; `rt_task_wait` wakes on cancel | 2 | 2 |
| 4 | `scope`, `spawn`, `Wait`, `Cancel`, `parallel`, `lane[T]`, `select`, `detach` | 3 | 3 |
| 5 | `within`; request deadline as a boundary deadline | 3 | 1 |
| 6 | Safepoints and the watchdog (measured on Linux before default-on) | 2, 3 | 2 |
| 7 | `limit` (memory, tasks), request budgets | 3, 6 | 1 |
| 8 | Long-lived reclamation: counts, `drop`, epochs (#176); Codex's mmap heaps (#209) first | #209 | 3 |
| 9 | `arena`, `once` per core | 2 | 1 |
| 10 | `with` and the policy shape; `bind`; library policies `retry`, `cache`, `trace` | 4 | 2 |
| 11 | `use`, `on`, the lifecycle state machine, `server.Drain`, admission policy | 4, 5 | 2 |
| 12 | `secret` and `reveal`; library opt-ins | — | 2 |
| 13 | Bounded values; reading at boundaries; `argo` and `q.Body()` support | derivation | 2 |
| 14 | Replay: `rt_effect`, recording in every client, capsules, `tin replay`, `--save-test` | 4, 12 | 4 |
| 15 | Diagnostic codes across the compiler | — | 1 |

About 30 PRs. Steps 1, 12 and 15 can start now and in parallel. Replay (14) comes after the
concurrency and `secret` work it depends on, but is not blocked on its most ambitious version:
its first PR records the request input, the clock, randomness and client results, with no
scheduling.

The syntax redesign (a separate document) can proceed alongside: none of these steps depends on
the spelling, and the translator that moves the code base to a new syntax works on the same
syntax tree.
