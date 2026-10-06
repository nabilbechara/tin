# Design: the syntax of Tin 1 (written 2026-10-04)

Status: **decided**, pending the maintainer's review. This replaces the edition 0 syntax
("Go syntax kept"). It gives one spelling to every construct of `design/design_semantics.md`
and of the existing language, and says how the code base moves to it.

The semantics do not change here: every form below lowers to the syntax tree the compiler
already checks, plus the new nodes the semantics document adds. That is what makes the switch
a parser and a translator, not a new compiler (section 12).

---

## 1. Why leave Go's syntax

v0.5 kept Go's syntax "so models write it fluently". Two things changed:

1. **Tin's meaning is no longer Go's**, and Go-looking code invites Go habits that fail:
   `x := nil`, ignoring an error, `go f()`, `interface{}`, positional struct literals, a
   C-style `for` that the bounds prover cannot read. A model that writes Go gets told no, one
   error at a time. A syntax that looks like what it means removes those errors at the source.
2. **The server constructs** (`within`, `guard`, `parallel`, `select`, `with`, `use`, `on`,
   `secret`, bounded types, unit literals) have no Go spelling. Bolting them onto Go syntax gives
   a hybrid that is neither Go nor clear.

The cost is that models have seen no Tin. It is paid with: one spelling for each thing, a
grammar with no ambiguity (no form needs lookahead past a token to be read), the primer, and
diagnostics that name the fix (design_semantics section 13). Everything that already reads
well stays: `?T`, `!T`, `try`, `catch`, `fail`, `keep`, `defer`, `shape`, `dyn`, `enum`,
interpolation, capitalized exports, call-site `mut`.

**Rules for every choice below:**

1. One way to write each thing. Where two forms exist today, one is removed.
2. Keywords say what the compiler checks. Library behaviour is a call, not a keyword.
3. No form is ambiguous to the parser: generic brackets, block values and literals are all
   decided by the next token.
4. Familiar where it costs nothing: Rust-like declarations, Go-like packages and blocks.

---

## 2. Lexical

- **Source:** UTF-8, `.tin` files.
- **Comments:** `// line` only. A comment directly above a declaration is its documentation.
- **Statements end at a newline**, as in Go (a line ending in an operator, `,`, `(`, `[` or `{`
  continues). There are no semicolons in source.
- **Names:** letters, digits, `_`. **Capitalized = exported**, as today. Multi-word names are
  camelCase (`getUser`, `GetUser`); `snake_case` is not used, so the capitalization rule always
  reads at the first letter.
- **Numbers:** `42`, `1_000_000`, `0xff`, `0b1010`, `0o17`, `3.14`, `1e9`.
- **Unit literals** (new): a number followed directly by a unit is a typed constant.

| unit | type | value |
|---|---|---|
| `ns` `us` `ms` `s` `m` `h` | `Duration` (an `i64` of nanoseconds) | `200ms` = 200 000 000 |
| `b` `kb` `mb` `gb` | `Size` (an `i64` of bytes) | `kb` = 1024, `mb` = 1024², `gb` = 1024³ |

  `1500ms`, `2.5s` (exact in nanoseconds or a compile error), `64kb`, `1mb`. `Duration` and
  `Size` are distinct named types: `within 5mb` is a type error. There is no decimal `kB`: one
  meaning per spelling, and the binary one is what limits and buffers want.

- **Strings:** `"..."` with `{expr}` interpolation and escapes (`\n`, `\t`, `\\`, `\"`, `\{`,
  `\u{263a}`); `` `raw` `` without either. A string never spans lines except a raw one.
- **Characters:** `'a'` is a `u8` when it is ASCII and a `rune` (`i32`) otherwise.

---

## 3. Keywords

```
package import
fn let mut const type shape enum dyn
if else for in match return break continue defer
try catch fail keep
within limit guard scope arena parallel select detach
with use on once
secret max shared
nil true false
```

That is the full reserved list. There is no `pub`: exports are the capitalization rule. Words
that read as names elsewhere stay contextual, recognized only where the grammar wants them, as
`shape` and `dyn` are today: `in`, `max`, `on`, `use`, `with`, `once`, `select`, `scope`, `arena`
may still be used as names where no construct starts.

**Removed:** `func` (`fn`), `var` (`let`/`mut`), `:=`, `switch`/`case`/`default` (`match`),
`++`/`--` (`+= 1`), the C-style `for init; cond; post`, positional struct literals, `go`, `chan`.

---

## 4. Declarations

```
package users

import "anvil"
import "./geom"

const MaxUsers = 1000                     // a compile-time constant
let defaultName = "anonymous"             // a per-core global, set once at core start
mut requests = 0                          // a per-core global that changes
shared let limits = loadLimits()          // built before the cores start, read by all
shared let hits atomic.I64                // atomics are the only shared state that changes

type User struct {
	id    i64
	name  str max 100                     // a bounded field (design_semantics section 8)
	email ?str
	token secret str
}

fn add(a i64, b i64) i64 {
	return a + b
}
```

- **`let`** binds a name that cannot be reassigned. **`mut`** binds one that can. Both infer the
  type from the value or take one: `let n i64 = 0`. There is no third form.
- What a binding refers to can still change through it (a struct field, a slice element), as
  today: `let` fixes the name, not the object. Mutation through parameters stays governed by
  `mut` parameters and call-site `mut`.
- **Globals** are `let`, `mut` or `shared let`, all per core except `shared` (design_semantics
  section 13). A global's initializer may fail only through `try`, which aborts startup.
- **Multiple results** are tuples: `fn split(s str) (str, str)`, read with
  `let (a, b) = split(s)`. `_` discards a value (never a fault).

---

## 5. Functions, methods, closures

```
fn parsePort(text str) !i64 { ... }                 // may fail
fn flush(w mut Writer) ! { ... }                    // may fail, no value
fn (p mut Point) move(dx i64, dy i64) { ... }       // a method; the receiver comes first
fn first[T constraints.Any](xs []T) ?T { ... }      // generic: [T], never <T>

let double = fn(x i64) i64 { return x * 2 }         // a closure: the same fn, with no name
sift.each(xs, fn(x i64) { total += x })
```

- **Generics** keep square brackets: `<` and `>` are comparisons, and `a < b > c` must never
  depend on what `a` is. Explicit instantiation: `parse[i64](s)`.
- **Parameters** are read-only unless declared `mut`; callers write `mut x` for a `mut` argument
  (unchanged). A `mut` struct, optional or map parameter cannot be reassigned (#180, unchanged).
- **Variadics:** `fn sum(xs ...i64) i64`, called `sum(1, 2, 3)` or `sum(xs...)`.
- A function with results ends every path in `return` (functions do not have tail values; only
  boundary blocks and `match` arms do, section 7).

---

## 6. Control flow

```
if n > 0 {
	...
} else if n == 0 {
	...
} else {
	...
}

for x in xs { ... }                // elements
for i, x in xs { ... }             // index and element
for k, v in m { ... }              // map, in insertion order
for i in 0..n { ... }              // half-open range; the bounds prover reads it directly
for i in (0..n).step(2) { ... }    // a step
for running { ... }                // while
for { ... }                        // forever
```

- One `for` with four shapes; the C-style three-clause loop is gone (the range form covers it
  and is what bounds-check elimination proves best). `0..n` is half-open; there is no `..=`.
- `break` and `continue` take an optional label (`outer: for ...`, `break outer`).

**`match`** replaces `switch`, and is an expression when its arms have values:

```
let label = match status {
	200 => "ok"
	404 => "missing"
	500..600 => "server error"
	_ => "other"
}

match shape {                      // an enum: every variant, or `_`
	Circle(r) => area = pi * r * r
	Rect(w, h) => area = w * h
}

let user = loadUser(id) catch err {
	match err {                    // a fault: arms compare with fault.Is
		ErrNotFound => return out.status(404)
		fault.DeadlineExceeded, fault.Overloaded => return out.status(503)
		_ => return out.status(500)
	}
}
```

- Arms are `pattern => expression` or `pattern => { block }`. Patterns: literals, ranges, enum
  variants with bindings, `_`, several patterns separated by `,`, and a guard
  (`n if n > 100 =>`). An enum `match` must cover every variant or have `_`.
- There is no fallthrough.
- Lowering (#225): an arm may also be a `return`, `break`, `continue`, `fail` or an assignment.
  `break` and `continue` in an arm apply to the enclosing loop. A name pattern compares with a
  package-level constant or variable (a sentinel), names a variant of an enum subject, or binds
  the value; naming a local variable is an error (compare with a guard). Inside a variant's
  values a name binds, as in a switch case. A `match` that gives a value handles every value
  (`_`, every variant, or `true` and `false`); as a statement, `let` or assignment value,
  `return` value or a catch or boundary block's last expression its arms may be blocks that
  leave, while inside a larger expression its arms are expressions. A statement `match` a
  `switch` can express compiles to the same instructions as that switch.

---

## 7. Faults, optionals and boundary blocks

Unchanged in spelling: `?T`, `!T`, `try e`, `e catch err { }`, `fail e`, `keep(e)`, `defer`.
New: `try e wrap "msg"` (design_foundations section 3).

```
let user = try db.user(id) wrap "loading user {id}"
let name = maybe ?? "anonymous"            // the default of an optional (new: one operator)
if let u = maybe { use(u) }                // narrowing by binding (new)
if maybe != nil { use(maybe) }             // narrowing by test (as today)
```

- `??` gives a default for a nil optional. `if let x = opt { }` binds the value when it is not
  nil. Both lower to the narrowing the checker already does.

**Boundary blocks** (design_semantics) all have the same form: a keyword, its arguments, a
block. Their value is the block's **last expression**; `fail` and `try` leave it with a fault;
`return`, `break` and `continue` cannot leave it (a compile error that says so).

```
let profile = try within 200ms {
	try api.profile(id)
}

let page = guard {                         // a panic inside becomes fault.Panic
	render(model)
} catch err {
	errorPage(err)
}

let summary = try limit memory 4mb, tasks 8 {
	summarize(try loadAll(ids))
}

let total = arena {                        // temporaries dropped; the result is copied out
	sumLines(try quarry.readAll(path))
}
```

---

## 8. Concurrency

```
let (user, orders) = try parallel {
	db.user(id)
	db.orders(id)
}

scope s {
	for u in urls {
		s.spawn(fn() ! { pages.push(try fetch(u)) })
	}
}

let t = s.spawn(fn() !Report { return try build() })
let report = try t.wait()
t.cancel()

select {
	let job = jobs.recv() => handle(job)
	let r = t.wait() => use(r)
	after(5s) => fail Timeout
	canceled() => return
}

detach {
	analytics.flush(keep(event))
}
```

- `parallel { e1 \n e2 }` evaluates each line as a child task; the value is the tuple.
- `select` arms are waits; `let x = wait =>` binds the result. Ties go to the first arm.
- `detach` requires kept captures (design_semantics section 6); the compiler names any that
  are not.

---

## 9. `with`, `use`, `on`, `once`

```
let payment = try with retry(3) {
	try stripe.charge(card, amount)
}

with bind(requestID, id) {
	handle(req)
}

use db = postgres.open(cfg.db)             // package level: per core, closed at core stop

fn migrate() ! {
	use tx = try db.begin()                // function level: closed when the function ends
	try tx.exec(schema)
}

on app.start {
	try migrate()
}

on app.stop {
	within 5s {
		telemetry.flush()
	}
}

once {
	warmCache()                            // first time this core reaches it
}
```

---

## 10. Types

```
i8 i16 i32 i64  u8 u16 u32 u64  f32 f64  bool  str  rune(=i32)  Duration  Size  fault
[]T          slice            [N]T     value array (copy semantics; roadmap)
map[K]V      map (insertion-ordered)
?T           optional         !T       fallible result (results only)
(A, B)       tuple            fn(A) B  function value
dyn S        dynamic shape    secret T  sensitive value
T max n      bounded (str, slices, []u8)
```

- `type Name struct { ... }`, `type Name enum { A, B(i64), C(str, i64) }`,
  `type Name = Other` (an alias), `type Celsius f64` (a distinct named type).
- **Struct literals are keyed only:** `User{id: 1, name: "a"}`. Positional literals are gone
  (they were how private fields got set from outside, #96).
- `shape` declarations are unchanged (design_foundations section 2.1), written with `fn`-less
  method signatures as today: `shape Reader { read(buf mut []u8) !i64 }`.
- **Attributes** precede what they annotate: `@json("id") id i64`, `@nopoll fn kernel(...)`.
- **Conversions** are calls of the type: `i64(x)`, `f64(n)`, `str(bytes)`.

---

## 11. A service, end to end

```
package api

import "anvil"
import "argo"
import "postgres"
import "redis"

use db = postgres.open(env("DB_URL"))
use cache = redis.open(env("REDIS_URL"))

type User struct {
	@json("id")    id    i64
	@json("name")  name  str max 100
	@json("email") email ?str
}

on app.start {
	try db.ping()
}

fn getUser(q anvil.Req, w mut anvil.Out) ! {
	let id = try q.pathParam[i64]("id")
	let user = try within 200ms {
		try with cached(cache, "user:{id}", 30s) {
			try db.queryOne[User]("select id, name, email from users where id = $1", id)
		}
	}
	match user {
		nil => w.status(404)
		_ => argo.put(mut w.body, user)
	}
}

fn main() {
	let r = anvil.router()
	r.get("/users/{id}", getUser)
	try r.serve(":8080")
}
```

---

## 12. Migration

**One edition, one switch, no dual syntax.** The new parser produces the existing syntax tree,
so the change is mechanical everywhere except the parser:

1. **New parser** behind `-edition 1` (the old one stays as edition 0 during the switch), with the
   grammar of this document and its own test suite of accepted and rejected forms.
2. **The translator** `tin fix -edition 1 FILES`: parse with the old parser, print with the new
   printer. It rewrites `func`→`fn`, `:=`/`var`→`let`/`mut` (by whether the variable is assigned
   again), `switch`→`match`, C-style `for`→ range forms where the shape allows (others become
   `for cond { } ` loops with the step written out), `++`→`+= 1`, positional→keyed literals,
   `tide.Millisecond*n`→`nms` where constant, and exported names unchanged.
3. **One commit converts the repository:** `lib/` (~29k lines), `tests/` (~9.5k), `examples/`,
   `bench/`, `tools/` fixtures; the strict suite, regressions, bootstrap and Linux benchmarks
   must be unchanged by it (the same syntax tree, so the same binaries — checked by comparing
   `tinc -S` output before and after for every file).
4. **The old parser is deleted** in the next PR. There is no third-party Tin code yet (packages
   are #146), so there is no long transition to support.
5. **The compiler's own source** (`selfhost/`, written in the internal legacy dialect) moves last,
   with the same translator extended to the dialect; until then the dialect is accepted only for
   files the build marks as the compiler's.
   **The standard library in edition 1** (#226): its files may also use three forms other code
   cannot. `extern fn` declares the OS functions the macOS runtime calls and the instructions
   that lower inline. `shared mut` is the runtime's mutable cross-core state; elsewhere it is
   E601, as is any `shared` global outside the standard library. The runtime package's files
   have no `package` clause. Each file is read in the edition it is written in: without
   `-edition`, a file with no `func`, `var`, `:=` or `;` is edition 1.
6. **Docs:** LANGUAGE.md is rewritten from this document; AGENT_PRIMER.md, README, STDLIB.md
   (regenerated) and every example follow in the same milestone.

**Coordination:** the libc-removal work (Codex, #198/#209/#215) rewrites runtime files. The
repository-wide conversion commit is scheduled at a quiet point, after those PRs merge or with
them rebased onto it by running the translator on their branches.

---

## 13. Grammar (summary)

```
File        = "package" Name { Import } { TopDecl } .
Import      = "import" String .
TopDecl     = ConstDecl | GlobalDecl | TypeDecl | ShapeDecl | FnDecl
            | UseDecl | OnDecl .
ConstDecl   = "const" Name [ Type ] "=" Expr .
GlobalDecl  = [ "shared" ] ( "let" | "mut" ) Name [ Type ] [ "=" Expr ] .
TypeDecl    = "type" Name [ TypeParams ] ( StructType | EnumType | "=" Type | Type ) .
ShapeDecl   = "shape" Name [ TypeParams ] ( "{" { ShapeMember } "}" | "=" Type { "|" Type } ) .
FnDecl      = { Attr } "fn" [ Receiver ] Name [ TypeParams ] Params [ Result ] Block .
UseDecl     = "use" Name "=" Expr .
OnDecl      = "on" Expr Block .

Stmt        = LetStmt | Assign | ExprStmt | If | For | Match | Return | Break | Continue
            | Defer | Fail | Block | Boundary | Select | Scope | Detach | Once | UseDecl .
LetStmt     = ( "let" | "mut" ) ( Name [ Type ] | "(" Names ")" ) "=" Expr .
If          = "if" ( Expr | "let" Name "=" Expr ) Block [ "else" ( If | Block ) ] .
For         = [ Label ":" ] "for" [ ( Name [ "," Name ] "in" Expr ) | Expr ] Block .
Match       = "match" Expr "{" { Arm } "}" .
Arm         = Pattern { "," Pattern } [ "if" Expr ] "=>" ( Expr | Block ) .
Boundary    = ( "within" Expr | "limit" LimitList | "guard" | "arena" | "parallel"
            | "with" Expr ) Block .
Select      = "select" "{" { [ "let" Name "=" ] Expr "=>" ( Expr | Block ) } "}" .
Scope       = "scope" Name Block .
Detach      = "detach" Block .
Once        = "once" Block .

Expr        = Unary { BinOp Unary } [ "catch" Name Block ] [ "wrap" String ] .
Unary       = [ "try" | "keep" | "-" | "!" | "mut" ] Primary { Postfix } .
Postfix     = "." Name | "[" Expr [ ":" Expr ] "]" | "[" Types "]" | Args | "?" "?" Unary .
Type        = Name [ "[" Types "]" ] | "[" "]" Type | "[" Int "]" Type | "map" "[" Type "]" Type
            | "?" Type | "!" Type | "dyn" Name | "secret" Type | Type "max" Expr
            | "(" Types ")" | "fn" "(" Types ")" [ Type ] .
```

The full grammar, with every production and its precedence table, goes into LANGUAGE.md with
the parser.

---

## 14. Milestone: "Tin 1"

The next milestone is the two documents of this PR, implemented:

| # | work | from |
|---|---|---|
| 1 | Edition-1 parser and its tests | this document §12.1 |
| 2 | `tin fix -edition 1` translator; repository conversion commit; old parser removed | §12.2–4 |
| 3 | LANGUAGE.md, AGENT_PRIMER.md, README, examples rewritten | §12.6 |
| 4 | The semantic steps 1–15 of design_semantics section 16, written in the new syntax | design_semantics |
| 5 | `selfhost/` moved to the new syntax | §12.5 |

Steps 1–3 come first (about 4 PRs) so that every semantic feature is written once, in the new
syntax. Step 4 is the bulk (about 30 PRs). Step 5 can come at the end.
