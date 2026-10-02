# Design: the foundations (written 2026-10-02)

docs/COVERAGE.md lists what Tin lacks. Most of the long tail (`context`, `io`, `sort`,
`database/sql/driver`, `errors`, `sync`, `reflect`, `encoding/json`) is blocked by six missing
foundations. This document decides each of them. Decisions are final unless a prototype proves
one wrong; each section says what it replaces in Go, why, and what builds on it.

Principles that decide every choice below:

1. **Nothing hidden.** No hidden allocation, dispatch, thread or lock. A cost is visible in the source.
2. **Checked at compile time.** If a rule can be enforced by the compiler, it is, and the error says how to fix it.
3. **Share nothing.** Cores own their data; tasks on one core cooperate and never race; data crosses cores by message.
4. **Regions are the memory model.** A value lives in the request or scope that made it, or is `keep`-copied out. Every feature below is a region rule, not a new kind of memory.
5. **One way to do it.** Where Go has three spellings, Tin has one.

What already exists and is built on, not replaced (docs/RUNTIME.md): request tasks with their own
stack and pool, `rt_task_park`/`wake`/`defer`, a per-core ready queue and timer heap, per-request
deadlines (`anvil.Deadline`), cleanup callbacks that run before a pool resets, `shared var`,
`relay` messages between cores, `?T`, faults with `try`/`catch`/`fail`, `keep()`, monomorphized
generics, `enum` with exhaustive `switch`.

Order of work and why: **closures, shapes, errors, tasks and scopes, guard, typeinfo, atomics.**
Closures come first because scopes, callbacks and most of the library take a function that must
carry state. Shapes come second because `io`, `sort` and `database/sql` are written in terms of
them. Section 9 gives the order with its dependencies.

---

## 1. Closures: a function literal captures what it uses

**Need.** 2,559 function literals in the service used as the yardstick, many capturing locals.
Today a literal cannot capture, so every callback needs a hand-written state struct, and a task
body (section 5) could not see its parent's variables.

**Decision.** A function literal may capture any variable in scope. The closure is an ordinary
**region object**: a code pointer and a table of captured cells, allocated in the current region,
like a struct. Every captured variable lives in a one-word cell in that region, and the closure and
its parent both hold the cell, so a write by either is seen by both (Go's semantics).

```
total := 0
sift.Each(xs, func(x i64) { total += x })       // the closure and this function share total
counter := func() i64 { n++; return n }          // n lives in the region, not in the frame
```

**Lifetime is the region rule, not a new rule.** A closure is a region object, so the region
checker already forbids storing it in long-lived memory. `keep(f)` deep-copies it: the code
pointer, and every cell into the long-lived heap, so **a kept closure owns copies of what it
captured** and no longer shares them with its parent. That is the only place Tin's semantics
differ from Go's, it is visible at the `keep`, and it is what share-nothing requires: the kept
closure may run on another core's behalf later, and shared mutable cells cannot cross cores.
Everything a kept closure captured must itself be keepable (no captured function-local pointers
into another region); the checker says which variable is the problem.

A function value stays one type, `func(A) B`. A top-level function converts to it with a null
environment. The `mut` marks of a function type still apply.

**Cost.** One region allocation per closure that captures, plus one per captured variable. The
compiler removes both for a closure that does not escape its frame (passed down as an argument,
never stored): the cells stay in the frame. This is an optimization that changes no behaviour, and
it is the first thing to measure.

**Replaces:** Go closures. **Rejected:** capture by value only (Go programmers write counters and
accumulators; it would be a trap); a separate escaping-closure type (two function types for one
idea); capture by reference with no region rule (a dangling cell after the request ends).

**Unlocks:** callbacks with state; every `Func` form in `sift` taking a closure; sections 5 and 6.

---

## 2. Shapes: abstraction without interfaces

**Need.** 400 interface types in the yardstick service. `io.Reader` and `Writer`, `sort.Interface`,
`hash.Hash`, `database/sql/driver`, `fmt.Stringer`, `error` all need a way to write code over
"anything with these methods". Today: nothing, which is why `bufio`, `io.Copy` and `sort.Sort`
have no Tin form.

**Decision.** A **shape** is a set of method signatures. A type satisfies a shape **structurally**:
if it has the methods, it satisfies it, with no declaration (Go's convenience, so the existing
library satisfies new shapes without edits). Two ways to use one, chosen at the point of use:

```
shape Reader { Read(buf mut []u8) !i64 }
shape Writer { Write(data []u8) !i64 }
shape ReadWriter { Reader; Writer }                   // composition by listing shapes

// Static: a type parameter. Monomorphized, no dispatch, no allocation. The default.
func Copy[R Reader, W Writer](dst mut W, src mut R) !i64 { ... }

// Dynamic: a value of any type that satisfies the shape. Opt-in, visible in the type.
func Log(w dyn Writer, msg str) { ... }
```

`dyn S` is a **fat reference**: the object pointer plus a table of its methods for that shape. It
allocates nothing (a struct is already a reference; the table is static, built where the
conversion happens) and is two words. It converts from a concrete type implicitly where a `dyn S`
is expected, and the compiler reports the missing method when it does not satisfy. A `dyn S` is
never nil, as nothing else in Tin is; `?dyn S` is the optional.

Named unions become shapes too: `shape Ordered = i64 | i32 | ... | f64 | str`. `any`,
`comparable` and `Ordered` are then ordinary names in the library (`sift.Ordered`), not syntax, and
a signature no longer repeats an eleven-way union.

**There is no downcast.** No type assertion and no type switch on a `dyn`: a closed set of cases is
an `enum` (checked for exhaustiveness), an open set is a method on the shape (`Kind()`). Go code
that switches on a dynamic type is a code smell that Tin does not need to accommodate, and
leaving it out is what keeps `dyn` free of runtime type information.

**Replaces:** `interface`, `any`, type assertions. **Rejected:** Go interfaces everywhere (they
hide dispatch and allocation, and they put runtime type information in every value); nominal
`impl` blocks (every existing type would need edits to satisfy a new shape; the library would
have to be rewritten); Rust-style trait objects with downcasting.

**Unlocks:** `io` (Reader, Writer, Copy, Pipe, MultiWriter, LimitReader, TeeReader), `bufio` over
any reader, `hash.Hash` and streaming `sha256`/`crc32`, `sort.Interface`, the `database/sql`
driver contract, `fmt.Stringer` and `Formatter`, `net.Conn`/`Listener`, `testing` helpers, and
`error` payloads.

---

## 3. Errors: a chain, and a guard at the request boundary

**Need.** `errors` is imported by 545 files (`Is`, `As`, `Unwrap`, `Join`, `%w`), and 14 files use
`recover`. Tin's `fault` is a message with no chain, and a panic ends the process.

**Decision, chain.** A fault is a value of the built-in `fault` type holding a message and an
optional cause. A package-level fault is a **sentinel**: it has an identity.

```
var ErrNotFound = fault("not found")                       // a sentinel

func find(key str) !Item {
	if !present(key) {
		fail ErrNotFound
	}
	...
}

func load(id i64) !User {
	row := try find("user:{id}") wrap "loading user {id}"   // wrap: add context, keep the cause
	...
}

if fault.Is(err, ErrNotFound) { ... }                      // walks the chain, compares identity
```

`try E wrap "msg"` is sugar for `E catch err { fail fault.Wrap(err, "msg") }`: the message becomes
`msg: cause`, and the cause stays reachable. The package `fault` has `Wrap`, `Is`, `Cause`,
`Join` (several faults, all reachable) and `Message`. Typed payloads are **not** a fault feature: a
function that must return structured information returns an `enum` result, as Rust's `Result` with
an error enum does, so the caller's `switch` is checked for exhaustiveness. Go's `errors.As` exists
because an interface can hide a type; Tin has no hidden types.

**Decision, guard.** There is no `recover`. The one real use of it in a server is "a bug in one
request must not kill the process", so that is what Tin provides, at a boundary:

```
res := guard handle(req)       // run in a sub-region; a panic becomes a fault, the sub-region resets
```

`guard CALL` has type `!T` for a call of type `T`. If the call panics, its defers run, its
sub-region is discarded (resource-cleanup callbacks first, then the pool rewinds to the mark), and
the expression is a fault carrying the panic message and backtrace. If it returns, the sub-region
merges into the caller's with no copy. `anvil` wraps every handler in `guard`, so a panicking
handler is a logged 500, not a dead server. Code that is not a request or task boundary has no
reason to catch a panic, and the language does not offer it: the control flow of ordinary code
stays visible.

**Replaces:** `errors`, `%w`, `recover`. **Rejected:** panics as exceptions with `recover` anywhere
(invisible control flow, and a recovered panic can leave data half-updated, which a discarded
sub-region cannot); typed error payloads via downcast.

**Unlocks:** `errors` complete, `os.ErrNotExist`-style sentinels across the library (`io.EOF` is
already `wire.IsEOF`), per-request fault isolation in `anvil`.

---

## 4. Context: the deadline and the cancellation belong to the task

**Need.** `context` is imported by 3,725 files in the yardstick service, and `context.Context` is
the first parameter of most functions. It carries three things: a deadline, a cancellation, and
request values. All three are properties of the **running task**, which Tin already has.

**Decision.** Each task has an **ambient deadline** (already there: the request deadline), an
**ambient cancellation** and **ambient slots**, inherited by the tasks it spawns. Nothing is passed
as a parameter.

```
within 2s {                        // the deadline of this block is min(2s from now, the current one)
	rows := try db.Query(q)        // a wait that passes it fails with fault.DeadlineExceeded
	...
}

slot requestID str                 // declared at package level: a typed key, no string keys, no any

with requestID = "r-81" {          // sets the slot for this block and the tasks it spawns
	log.Info("start")              // reads requestID.Get() inside
}
```

- **Waits obey it.** Every wait in the runtime already goes through `rt_task_wait`, which knows
  the deadline. It is extended to wake with `fault.Canceled` when the task's scope has been
  cancelled (section 5). `tide.Wait`, `wire`, `redis`, `mysql`, `postgres`, `websocket` and the
  helper-thread calls need no change.
- **CPU-bound loops poll:** `task.Canceled() ?fault` is a cheap read of one word.
- **No default `Background()`:** a task started by `main` has no deadline, a request has the
  server's.
- `slot` values are typed, hold anything `keep`able, last for the `with` block, and cannot leak
  past it (region rule). Reading a slot with no value is a fault, not a nil.

**Replaces:** `context.Context`, `WithCancel`, `WithTimeout`, `WithDeadline`, `WithValue`,
`Background`, `TODO`, `Cause`, `AfterFunc`. In the yardstick service this removes a parameter from
most of its function signatures, and a whole class of bug (a missed `ctx` that makes a call
uncancellable).

**Rejected:** a `Context` value passed explicitly (it is the thing that makes Go APIs noisy, and
nothing enforces that it is passed); dynamically-typed values (`any` keys and values: the usual
source of `context` bugs).

**Unlocks:** `context` complete, `database/sql` with cancellation, `http.NewRequestWithContext`,
`os/exec` with cancellation, graceful shutdown for anything.

---

## 5. Tasks and scopes: structured concurrency on the core

**Need.** 99 `go` statements, 73 channels, 49 `select` in the yardstick service. The runtime
already runs a request as a stackful task that parks on I/O; there is no way for a program to
start a second one.

**Decision.** Concurrency is **structured**: a task is always started inside a **scope** and
cannot outlive it.

```
func fetchAll(urls []str) ![]Page {
	pages := make([]Page, len(urls))
	scope s {
		for i, u := range urls {
			s.spawn(func() ! {                    // a child task, on this core
				pages[i] = try fetch(u)
			})
		}
	}                                            // returns when every child has finished
	return pages                                 // a fault from any child is the scope's fault
}
```

- **A scope waits for all its children.** The first child fault cancels the others (their waits wake
  with `fault.Canceled`) and becomes the scope's fault; `s.cancel(reason)` does the same by hand.
- **Children run on the parent's core**, cooperatively: they switch only where they park (a wait,
  `defer()` or `s.yield()`), so **tasks on one core cannot race**: no mutex is needed or offered.
  This is what the runtime already does for requests (docs/RUNTIME.md, "Request tasks").
- **They share the parent's region.** A child may read and write what its parent made, because the
  scope guarantees the parent outlives it. This is what makes the capturing closure in the example
  legal under the region checker, and it is why there is no detached `go`: a task that outlives its
  creator would hold a dangling reference to a pool that has been reset.
- **Values come back through the scope:** `t := s.spawn(f)` with `f` returning `!T`, then `t.Wait()
  !T` inside the scope.
- **Between tasks on one core: `lane[T]`**, a bounded queue in the library (`New`, `Send`, `Recv`,
  `Close`), parking a sender when full and a receiver when empty. It replaces `chan` for
  the work-queue and fan-in/fan-out patterns, and `Recv` takes the ambient deadline like any
  wait. `wait.First(a, b ...)` over lanes and a timeout replaces `select`.
- **Between cores: `relay`**, as today, with typed ports (`relay.Port[T]`) serialising through the
  same derivation as JSON (section 7) instead of strings.
- **Work that must outlive a request** (a flush, a refresh) is `hearth.Background(f)`: a task on a
  core's own long-lived scope, started once, whose captured values are `keep`-copied (section 1).

**Replaces:** `go`, `chan`, `select`, `sync.WaitGroup`, `errgroup`. **Rejected:** detached
goroutines (they cannot be made region-safe, and they are how Go programs leak); OS threads per
task (the point of the design is the core that never blocks); async/await colouring (a task parks
anywhere, so no function needs a different type).

**Unlocks:** parallel fan-out inside a request, every client that wants concurrent calls, `os/exec`,
`net/http` clients with concurrent requests, `testing` with `t.Parallel`.

---

## 6. Synchronization: atomics for shared counters, nothing else

**Need.** `sync` is imported by 101 files and `sync/atomic` by 19 in the yardstick service. In a
share-nothing design nearly all of it is unnecessary; what remains is counters and flags that
several cores read.

**Decision.** There is **no `Mutex`, `RWMutex` or `Cond`**, by design.

- `sync/atomic` becomes the package `atomic`: `I64`, `U64`, `Bool`, with `Load`, `Store`, `Add`,
  `Swap`, `CompareAndSwap`. Only these may be declared `shared var`, so cross-core mutable state is
  limited to what the hardware can update atomically; the compiler rejects any other `shared var`
  that is written.
- `sync.Once` is a package-level initializer, or `once` per core (a `slot`-like declaration that runs
  its function the first time the core needs it).
- `sync.WaitGroup` is a scope (section 5). `sync.Pool` is what a request pool already is.
  `sync.Map` is `atlas` on a core plus `relay`.
- **The pattern for shared state is one owner per core and messages:** a cache that every core
  shares is N per-core caches, or one core that owns it and answers `relay` requests; data that
  is built once and only read afterwards (as `anvil`'s router table is) needs neither. docs/RUNTIME.md will say so with an example.

**Replaces:** `sync`, `sync/atomic`. **Rejected:** mutexes (they invite the shared mutable state the
whole design avoids, and a lock held across a park would be a deadlock the type system cannot see).

---

## 7. Derivation: compile-time type information, not reflection

**Need.** `reflect` is imported by 501 files and struct tags appear 16,455 times in the yardstick
service: serialization, validation, row mapping and flag parsing all work from "the fields of this
type". Today `argo` and `say` are special cases inside the compiler.

**Decision.** Types carry **attributes**, and generic code can **loop over a type's fields at
compile time**. Nothing exists at run time.

```
type User struct {
	id    i64   @json("id")
	email str   @json("email,omitempty") @validate("email")
	roles []str @json("roles")
}

func Encode[T](v T) str {
	var out strings.Builder
	for f in fields[T] {                       // unrolled when Encode[User] is instantiated
		if f.attr("json") == "" { continue }
		out.Str("{f.attr("json")}:")
		out.Str(Encode(v.field(f)))            // typed access: no any, no assertion
	}
	return out.String()
}
```

- `fields[T]` is a compile-time list of `{name, type, attributes}`; `v.field(f)` reads that field
  with its static type. The loop is unrolled per instantiation, so a derived encoder costs exactly
  what the hand-written one would.
- **Attributes are checked.** `@json(...)` is declared by the package that interprets it
  (`attr json(name str, omitempty bool)`), so a misspelled option is a compile error in the type
  declaration, not a silent no-op at run time (Go's struct tags are unchecked strings).
- `argo` is rewritten in this mechanism, then `say`'s struct printing, then new users:
  `database/sql` row scanning, `flag` from a struct, validation, `encoding/xml`, `csv`, `gob`.
  `reflect` itself is **not provided**.

**Replaces:** `reflect`, struct tags, code generators for them. **Rejected:** runtime reflection
(type tables in every binary, dynamic dispatch, the end of "nothing hidden"); keeping the
compiler-special-cased derivation (every new format would be a compiler change).

**Unlocks:** `encoding/json` complete (tags, `omitempty`, dynamic decoding into a shape),
`encoding/xml`, `encoding/csv`, `database/sql` scanning into structs, `flag` from a struct,
`html/template`, validation libraries.

---

## 8. Packages: reproducible, hashed, vendored

**Need.** 157 modules in the yardstick service, and no way to name a dependency.

**Decision.** A package is imported by a path (`import "github.com/ana/geo"`); a `tin.lock` file
records every dependency with a content hash, and `tin vendor` copies them into `vendor/` in the
repository. The build reads only `vendor/`, never the network, and refuses a file whose hash is not
the one recorded. A dependency is source: there is no binary package format. Resolution is the one
rule: the lock file says exactly which versions.

**A package declares what it may do.** Its manifest lists capabilities (`net`, `files`, `spawn`,
`exec`, `unsafe`); the compiler rejects a call outside them, and the lock file shows a reviewer what
an upgrade is asking for. This is the reason to do packages in Tin, not as a copy of `go.mod`: a
language written to be generated by AI will pull in code nobody read, and the compiler should be
able to say what that code is allowed to touch.

**Rejected:** a central registry first (a policy decision for later, not a design one); semantic
version resolution (it is where the complexity and the surprises are, and a lock file makes it
unnecessary).

---

## 9. Order of work

Each step is one or more PRs with tests; a step starts when what it depends on is merged.

| # | work | depends on | what it adds to docs/COVERAGE.md |
|---|---|---|---|
| 1 | Closures: capture, region cells, `keep` copies them, frame-local cells for non-escaping closures | none | `closures`, method values; callback APIs |
| 2 | Shapes: declaration, structural satisfaction, `[T Shape]`, named unions, then `dyn` | none | unblocks `io`, `sort`, `hash`, `database/sql/driver`, `Stringer` |
| 3 | Faults: sentinels, `fault` package, `wrap`, `guard`, `anvil` guards handlers | none | `errors` |
| 4 | The `io` family on shapes: `Reader`/`Writer`, `Copy`, `bufio`, streaming hashes, `os.File` | 2 | `io`, `bufio`, `hash`, `crypto/*` streaming, `os` |
| 5 | Tasks and scopes: `scope`, `spawn`, `Wait`, `lane`, `wait.First`, ambient cancel | 1, 3 | `go`, `chan`, `select`, `sync.WaitGroup` |
| 6 | Context: `within`, `slot`, `with`, cancel in `rt_task_wait`, deadline in clients | 5 | `context` |
| 7 | Atomics and `shared var` rules, `hearth.Background` | 5 | `sync`, `sync/atomic` |
| 8 | Derivation: attributes, `fields[T]`, `argo` and `say` rewritten on it | 2 | `reflect`, struct tags, `encoding/json` complete |
| 9 | Packages: manifest, `tin.lock`, `tin vendor`, capabilities | none | modules |

Steps 1, 2, 3 and 9 are independent and can proceed in parallel; the standard library breadth in
COVERAGE.md's "high demand" list (`time`, `net/url`, `regexp`, `strconv`, `strings`, `bytes`,
`os`, `net/http`) proceeds alongside, because it needs only what exists today for everything that
does not take an `io.Reader` or a callback with state.

## 10. What this does not decide

- The surface syntax of `attr`, `fields[T]` and `slot` is settled here in shape and will be refined
  while it is implemented; the semantics above are the decision.
- Whether `guard` should also bound a sub-region's memory (a quota per request) is left for the
  implementation to measure.
- The standard library's names for the shapes beyond `Reader` and `Writer` follow Tin's naming
  (short words), chosen when each package is written.
