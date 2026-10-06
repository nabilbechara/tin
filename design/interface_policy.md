# Interface: policies, `with` and `bind` (#237)

Status: **proposed**, for approval by the members of the interface: #232 (structured
concurrency) and #238 (`use`, `on`, lifecycle). Nothing builds on it before each has approved
the PR that adds this file (AGENTS.md, Tin 1 rule 5). After that, a change to a name or a rule
below needs the same approvals.

Spec: `design/design_semantics.md` §7.1 (policies), §0 (slots are owned by a boundary), §6
(children), §14.2 (`with bind(slot, v)` replaces `with slot = v`). The runtime storage of
slots is `design/interface_boundaries.md` §7; section 4 below refines it (key and value word).
This file fixes only names, layout and who calls what. It changes no rule of the spec.

---

## 1. The shape

Package `policy` (`toolchain/std/policy/`) declares

```
shape Policy[T constraints.Any] { Run(body func() !T) !T }
```

A policy is any struct whose methods include `Run(body func() !T) !T` (structural, as every
shape). `with` needs no import: it calls the method directly. The shape is there for generic
code (`func f[T constraints.Any, P policy.Policy[T]](p P, ...)`).

- **Static dispatch.** `with p { }` is a direct call of `P.Run` on the concrete type of `p`
  (monomorphized like a shaped type parameter). A `dyn` policy is a compile error: its `Run`
  cannot be checked (section 3).
- **A receiver may be `mut`** (a cache policy writes its store); the call passes the policy
  value the `with` evaluated.

## 2. What `with p { body }` means

```
let v = try with policy.Retry(3) {
	try stripe.Charge(card, amount)
}
```

1. `p` is evaluated once, before anything else.
2. The block becomes the closure `body` of type `func() !T`. Its value is its last
   expression (untyped constants take their default type); `fail` and `try` leave it with a
   fault. `return`, and `break`/`continue` to a loop outside it, are compile errors.
3. The block's value type must be `T` of `P.Run`; the `with` expression has type `!T`.
   **Inference:** every type parameter of a generic policy constructor that its arguments leave
   open is the block's type: `with policy.Retry(3) { e }` is `with policy.Retry[E](3) { e }`
   where `E` is the type of `e`. Explicit type arguments are taken as written.
4. **A block without a value** has type `!`. Its policy's `Run` is either
   `Run(body func() !) !`, or one with a scalar `T`; then the body gives `T`'s zero, and open
   type parameters are `u8`. The value `Run` returns is dropped.
5. A `with` boundary is entered (section 4), `p.Run(body)` is called, the boundary is left,
   and `Run`'s result is the expression's result. `Run` may call `body` zero or more times and
   may return a value `body` never produced (a cache hit).

## 3. The body closure never outlives `Run` (region rule)

`body` is a frame-local closure: the variables of the block live in the enclosing frame (the
rule of `sift.Each`), so the block may write request memory into them. `Run` may therefore
only **call** `body`, or **pass it as an argument** to a function whose parameter obeys the same
rule (checked recursively; another policy's `Run` qualifies). Any other use in `Run` is a
compile error at that use, naming the method: storing it (a variable, field, element, map,
global, a closure's capture, a `defer`), returning it, converting it, or passing it where the
rule cannot be checked (an indirect call, an extern). The check runs on the `Run` instance each
`with` uses, after the region pass.

## 4. The `with` boundary and slots

**Boundary.** `with` enters a boundary of kind `bkWith` (10, interface_boundaries §1.2) with
`rt_bnd_enter(bkWith)` **around the call to `Run`**, so the policy's own code and every run of
the body are inside it, and leaves it with `rt_bnd_leave(b)` when `Run` returns, with a value
or a fault. It has no flags: a panic and a poll unwind pass through it (their unwind leaves
it), and nothing cancels it directly; it inherits its parent's deadline, budget, cancel state
and slots (`rt_bnd_new`). Its sub-region merges on exit (#176). Cost: one enter and one leave
(a free-list pop and about fifteen stores each), plus a 5-word descriptor on the wrapper's
frame; no pool memory.

**Slots** (refines interface_boundaries §7; the record word `bSlots` and the chain are as there):

| item | decision |
|---|---|
| slot | a value of `policy.Slot[T]` (a struct, so a reference), made by `policy.NewSlot[T](name str)`, normally in a package-level `let` (one per core, like every global) |
| key | the slot object's address. Unique on its core; chains never cross cores, so the key needs no process-wide identity. (The compiler-emitted static word of §7 is dropped: no new declaration syntax.) |
| node | `[next, key, value]`, 3 words from `rt_alloc` (the current pool: the request's, or the core's on the core stack), prepended to `bSlots` of the **current** boundary |
| value word | a reference to a `policy` one-field struct holding the `T` value, so any `T` (including `dyn` and two-word values) is stored the same way; the runtime never reads it |
| `rt_slot_bind(key i64, value i64)` | prepends a node to `rt_bnd_current()[bSlots]` |
| `rt_slot_find(key i64) i64` | the newest node for `key` on `rt_bnd_current()[bSlots]`, or 0 |

**Binding is a policy.** `policy.Bind(s Slot[V], v V)` is a `Policy[T]` (its `T` open, so the
block's type) whose `Run` calls `rt_slot_bind` and then `body`. Because `with` entered a
`bkWith` boundary around `Run`, the binding lives exactly as long as the `with`:

```
let requestID = policy.NewSlot[str]("request id")

try with policy.Bind(requestID, "r-81") {
	handle(req)                       // requestID.Get() is "r-81" here
}
```

- `s.Get() !T` reads the newest binding; with none it fails with `slot <name> is not bound`
  (design_foundations §4: a fault, not a nil).
- A value bound in a request is request memory; the binding cannot outlive its boundary, and
  `Get` results are treated by the region pass like any value of unknown origin.

## 5. Partners

**#232 (structured concurrency).** A child's root copies `bSlots` from its parent at
`rt_bnd_task` (already so in `rt_bnd_new`), so `s.spawn` children and `parallel` lines see every
binding of the `with` blocks around their scope, and bindings made later in the parent are not
seen by children already started. `detach` starts under the core's background boundary: it does
**not** see the request's bindings (their values are request memory); a detached task binds
what it needs itself. A `scope` or `parallel` inside a `with` body is an ordinary child of the
`bkWith` boundary. `select` is unaffected.

**#238 (`use`, `on`, lifecycle).** `on` handlers run as tasks under the background boundary of
their core: no bindings, like `detach`. `use` is not a policy and enters no boundary (it is a
`defer`). anvil may bind runtime slots on a request's root (for example a request id) with
`rt_slot_bind` right after `rt_bnd_task`, before the handler runs; the node lives in the request
pool. The admission policy `anvil.Admit(func(anvil.Load) bool)` is a function, not a
`Policy[T]`; this interface does not cover it.

## 6. Who implements what

| piece | where | issue |
|---|---|---|
| `with` checking (section 2), inference fill, `dyn` and control-flow errors | `toolchain/compiler/lower.tin` (next to `chk_boundary`), `toolchain/compiler/generics.tin` (fill) | #237 |
| wrapper `with$N(c, p)` and adapter: `rt_bnd_enter(bkWith)`, `p.Run(adapter)`, `rt_bnd_leave` | `toolchain/compiler/lower.tin` | #237 |
| body rule (section 3) | `toolchain/compiler/region.tin` | #237 |
| `rt_slot_bind`, `rt_slot_find` | `toolchain/runtime/runtime.tin` (next to `rt_bnd_new`) | #237 (the slot storage #231 left) |
| `policy`: `Policy[T]`, `Slot[T]`, `NewSlot`, `Get`, `Bind`, `Retry`, `Trace`, `Cached` | `toolchain/std/policy/` | #237 |
| slot inheritance by children; `detach` without bindings | runtime (already) | #232 |
| `on` handlers without bindings; request-root bindings in anvil | anvil, runtime | #238 |

**Library policies** (behaviour, not interface): `Retry(n)` runs the body up to `n` times while
it fails, and stops early on a cancellation (`fault.Canceled`, `DeadlineExceeded`,
`LimitExceeded`) or a cancelled boundary; `Backoff(d)` waits between attempts. `Trace(name)`
reports the name, duration and fault of each run to the core's tracer (herald by default).
`Cached(cache, key, ttl)` returns a fresh entry of a per-core `Cache[T]` without running the
body, and stores a successful value with `keep`; faults are not cached.
