# Interface: the FAULT representation (#229)

Owner: #229. Members: #230 (guard, `fault.Panic`), #238 (drain, admission: `fault.Draining`,
`fault.Overloaded`), #241 (replay: recorded faults), #244 (coded diagnostics). Spec:
design_semantics.md section 2, design_foundations.md section 3. Do not change what this
note fixes without the members' approval in the PR that changes it.

## 1. The record

A fault is **one machine word**: 0 for nil, otherwise a pointer `p` into one allocation:

```
p-32  trace    fault word of the backtrace text (0: none); set only for fault.Panic
p-24  joined   pointer to [n][fault 1]...[fault n] for fault.Join (0: none)
p-16  ident    sentinel identity (0: none)
p-8   cause    the wrapped fault (0: none)
p     len      \
p+8   bytes     > a plain str: the FULL message, "outer: inner" for a wrapped fault
      NUL      /
```

- Because `p` is a valid `str`, everything that reads a fault as text keeps working:
  `say.Line(err)`, `{err}`, `say.Str(err)`, `err.Error()`, `panic(err)`, argo, and library
  code such as `say.Str(err) == "deadline exceeded"`. Messages of existing faults are
  unchanged.
- Every fault comes from `rt_fault_raw(data, n, cause, ident)` (lib/runtime/runtime.tin):
  `fail "msg"`, `fail("msg")`, `say.Fault(...)`, `fault("...")` and the `fault` package all
  go through it. **Never make a fault by casting a str** (`cast(fault, s)`): it has no
  record, and `fault.Is`/`Cause` would read the words before it.
- The record is immutable once made. It lives in the region of the code that made it
  (the request pool, or the ingot heap for globals); `keep(err)` copies the whole chain
  (`rt_keep_fault`, identities kept), and `rt_fault_copy(err, true)` / `rt_fault_free`
  carry a chain across a pool scope (websocket `Each` does this).
- `==` on faults compares the words (references). Matching is `fault.Is`.

## 2. Identity

- `ident` 0 means "no identity": such a fault matches (`fault.Is`) only itself, by reference.
- **Runtime sentinels** have fixed identities, used by every library:

  | sentinel | ident | message | runtime constructor (returns the i64 word) |
  |---|---|---|---|
  | `fault.Canceled` | 1 | `canceled` | `rt_fault_canceled()` |
  | `fault.DeadlineExceeded` | 2 | `deadline exceeded` | `rt_fault_deadline()` |
  | `fault.LimitExceeded` | 3 | `limit exceeded` | `rt_fault_limit()` |
  | `fault.Overloaded` | 4 | `overloaded` | `rt_fault_overloaded()` |
  | `fault.Draining` | 5 | `draining` | `rt_fault_draining()` |
  | `fault.Panic` | 6 | the panic message | `rt_fault_panic(msg, trace)` |

  Constants `faultCanceled` .. `faultPanic` name them in the runtime. Runtime and library
  code produce one with `fail cast(fault, rt_fault_deadline())` (a boundary reason:
  `rt_bnd_cancel(b, cast(fault, rt_fault_draining()))`). Each core makes each of these
  records once, in the ingot heap (`rt_fault_std`), so a call allocates nothing and the
  word outlives every request and boundary that holds it; the `fault` package's variables
  are these same words. Identity, not the address, is what matches across cores.
- **Boundaries (#231).** A wait that ends early fails with `rt_wait_fault()`: the cancel
  reason itself when its identity is `DeadlineExceeded` or `LimitExceeded`; otherwise a
  `fault.Canceled` record (message `canceled: <reason>`) whose cause is the reason, so
  `fault.Is` matches both `Canceled` and the reason; `DeadlineExceeded` when nothing
  cancelled the boundary. `rt_bnd_check` cancels a passed deadline with
  `rt_fault_deadline()`, and a boundary out of task budget fails with `rt_fault_limit()`.
  Reasons are compared by identity, never by message. So every deadline wait in lib/
  (tide, wire, DNS, seal, redis, mysql, postgres, websocket, the runtime's helper jobs)
  fails with `fault.DeadlineExceeded`. A drain should cancel with `rt_fault_draining()`.
- **Package-level sentinels**: `var ErrNotFound = fault("not found")`. The checker numbers
  each such declaration from 64 up (`faultUserIdent`) and lowers it to
  `rt_fault_sentinel(msg, ident)`. A global is per core, so every core has its own copy
  of the value, but all copies share the identity, as do copies made by `keep` or sent
  through a record copy. Two declarations with the same message are different sentinels.
  `fault("...")` anywhere other than directly as a package-level var initializer is a
  compile error (use `fail("msg")` for a one-off fault).
- Identities are numbered in check order within one compilation (Tin compiles a whole
  program at once). They are not stable across builds: do not persist them; persist
  messages (replay, #241, records the message and, for runtime sentinels, the ident 1-6).

## 3. The `fault` package (lib/fault/fault.tin)

| function | meaning | Go |
|---|---|---|
| `Wrap(err fault, msg str) !` | `msg: cause`, `err` as cause; nil for nil `err` | `fmt.Errorf("%s: %w", msg, err)` |
| `Is(err fault, target fault) bool` | walks causes and joined faults; equal reference or equal nonzero identity; a nil target matches only nil | `errors.Is` |
| `Cause(err fault) !` | the wrapped fault; nil for none, nil, and a Join | `errors.Unwrap` |
| `Join(errs []fault) !` | every non-nil fault, messages joined with `\n`; nil if none | `errors.Join` |
| `Message(err fault) str` | the full message, `""` for nil | `err.Error()` |
| `Backtrace(err fault) str` | the trace of the first `fault.Panic` in the chain, `""` for none | none |

**Why `!` results.** The language rejects `fault` as a declared result type ("write a
result that can fail as !T"). A `!` function's call already has type `fault`, so the
functions that make a fault are declared `!` and *fail with* the fault they make; `return`
(no fault) is nil. Callers use the value directly: `fail fault.Wrap(err, "loading")`,
`e := fault.Join(errs)`, `if fault.Cause(err) == nil`. The usual rules hold: the value must
be read (an unread fault variable is a compile error). No compiler change was needed, and
no other package gains a way to return a bare `fault`. `Join` takes a `[]fault` because
Tin's `...` parameters are not slices.

The runtime functions behind them (`rt_fault_wrap`, `rt_fault_is`, `rt_fault_cause`,
`rt_fault_join`, `rt_fault_trace`) take and return i64 fault words, so the compiler can
lower syntax to them without importing `fault`.

## 4. `switch` over a fault

`switch err { case A, B: ... case nil: ... default: ... }`, where the tag has type `fault`,
compares each case with `rt_fault_is($sw, case)` instead of `==` (selfhost/check.tin
`lower_switch` marks the comparison `$is`; `chk_binary` lowers it). Cases must be faults
(or `nil`). Cases are tried in order, so a fault that matches several cases (a Join) takes
the first.

## 5. `fault.Panic` payload (#230)

A panic that a `guard` converts is `rt_fault_panic(msg, trace)` (`rt_guard_land`): identity
6, message `panic: <message>` (the text #230's guard already produced, for example
`panic: index out of range [5] with length 3`), and `trace` the backtrace text stored as its
own fault record in the trace word, so `keep` copies it. The guard (and a spawned child's root)
passes `rt_backtrace_text`, the functions `rt_backtrace` prints, one per line (#142), and
`fault.Backtrace(err)` returns it. `fault.Is(err, fault.Panic)` is true for
it through any wrapping.

## 6. `try E wrap "msg"` (edition 1)

The edition-1 parser (#252) reads `try E wrap "msg"` as `EX_WRAP` (`WRAP_X` the `try`,
`WRAP_MESSAGE` the string). `lower_try_stmt` lowers it like `try E`, except that the fault
path returns `rt_fault_wrap(err, msg)`: it is `E catch err { fail fault.Wrap(err, msg) }`,
the message reads `msg: cause`, and `msg` is checked as a `str` and evaluated only on
failure. It works wherever `try` does (statement, `let`, assignment, multiple assignment,
`return`). `wrap` on anything but a `try` is a compile error. Tests:
tests/edition1/run/fault_wrap.tin and tests/edition1/fault_wrap_bad.tin, run by
tests/edition1.sh.

## 7. Follow-ups

- `match` over faults (#252's `EX_MATCH`) lowers like `switch` (section 4): each arm compares
  with `rt_fault_is` (#225, tests/edition1/run/match.tin).
- Producing `fault.Overloaded` and `fault.Draining` belongs to admission and drain (#238);
  they call the constructors in section 2.
