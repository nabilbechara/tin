# The Tin language reference

Tin is a compiled, statically typed language for servers and tools. It targets Linux on
arm64 and x86-64 (production) and macOS on Apple Silicon (development). It is designed to
be written by AI: it trades human convenience for speed and robustness, and the compiler
rejects whole classes of bugs instead of leaving them to tests:

- ignored errors (a fault must be handled);
- nil dereferences (references are never nil; optionals must be checked);
- request memory leaking into long-lived state (compile-time region check);
- shared mutable state between threads (globals are per core; tasks live in scopes);
- implicit numeric conversions (none exist);
- out-of-range indexing (always checked, the check removed only where proven safe);
- secrets reaching logs, faults or JSON (`secret T` is tracked at compile time).

This document describes **edition 1**, the syntax every Tin program uses: `fn`, `let` and
`mut`, `match`, `for x in xs`, keyed struct literals, unit literals, and blocks for
deadlines, budgets and tasks (`within`, `limit`, `guard`, `scope`, `select`). It is written
from [design/design_syntax.md](../../design/design_syntax.md); the semantics are in
[design/design_semantics.md](../../design/design_semantics.md). The Go-like syntax before it,
edition 0, is history (`design/design_syntax.md` replaces it); section 22 maps each
old form to its replacement.

[STDLIB.md](STDLIB.md) lists the standard library, [TOOLING.md](TOOLING.md) the commands,
[ERRORS.md](ERRORS.md) every diagnostic, [RUNTIME.md](RUNTIME.md) and
[COMPILER.md](COMPILER.md) how it works inside.

Contents: 1 Programs and packages · 2 Lexical elements · 3 Types · 4 Constants ·
5 Declarations · 6 Expressions · 7 Statements · 8 Faults · 9 Optionals ·
10 Boundary blocks · 11 Concurrency · 12 Memory and regions · 13 Generics · 14 Builtins ·
15 String interpolation · 16 Printing: say · 17 JSON: argo · 18 Safety checks ·
19 Attributes · 20 Standard-library-only features · 21 Grammar · 22 From edition 0 ·
23 Differences from Go

**Status.** A few edition 1 forms are read by the parser but not yet accepted by the
checker, and are marked *not yet implemented* where they appear: `opt ?? fallback`, `arena`
blocks (#236), tuple type aliases (`type Pair = (i64, i64)`) and variadic parameters
(`xs ...i64`). The checker also does not yet reject reassigning a `let` name or an unknown
attribute.

---

## 1. Programs and packages

A program is one or more `.tin` files, each starting with a package declaration; the
program's files say `package main` and one of them declares `fn main()`.

```tin
package main

import "say"

fn main() {
	say.Line("hello, tin")
}
```

Run it with `tin hello.tin` (see [TOOLING.md](TOOLING.md)).

### Imports

```tin
package main

import "say"
import "./geom"

fn main() {
	say.Line(geom.Area(2, 3))
}
```

- One path per `import`, after the package declaration and before every other
  declaration. There are no import aliases and no grouped imports.
- `import "say"` is the standard library (`toolchain/std/say` ... `packages/wire`). `import "./geom"` is
  relative to the importing file: `./geom.tin`, or every `.tin` file in `./geom/`.
  `import "util"`, outside the standard library, is `<directory of the program>/util(.tin)`;
  `import "github.com/ana/geo"` is a dependency (below).
- A package is a file `name.tin` or a directory of `.tin` files. Directory files are read
  in sorted order; `*_test.tin` files are skipped.
- Every file of a package starts with the same `package name` declaration.
- Platform-specific files: next to `name.tin`, the compiler also loads `name_darwin.tin`
  or `name_linux.tin` for the target OS, and `name_linux_arm64.tin` /
  `name_linux_amd64.tin` for the target CPU. In a directory package, files for other
  targets are skipped.
- The package name is the last element of the import path (`"./net/http"` is `http`).
  Members are used as `pkg.Name`.
- **Exports**: a capitalized top-level name, method or struct field (`Serve`,
  `Out.Status`, `Resp.Body`) is visible to importers; a lower-case one (`parseInt`,
  `Conn.fd`) is private to its package, and using it from another package is a compile
  error. Code the compiler generates (JSON encoding, printing, `keep`) may read private
  fields. Multi-word names are camelCase (`getUser`, `GetUser`), so the rule always reads
  at the first letter.
- Imports must not form a cycle.
- **Dependencies** are imported by path: an import whose first element contains a dot
  (`"github.com/ana/geo"`) is read only from `vendor/<path>` in the program's directory,
  never from the standard library or the network. `tin vendor` copies the packages
  `tin.mod` requires there, and `tin.lock` records each vendored file's SHA-256; a file
  whose hash differs is a compile error (toolchain/docs/PACKAGES.md). Two import paths cannot load
  different packages with the same name.
- **Capabilities:** a vendored package's `tin.mod` declares what it may do (`caps net files
  spawn exec unsafe`). A call from it that can reach, through any package, a standard library
  entry point needing another capability is a compile error at the call (`E804`); `unsafe`
  lets it use the trusted operations of section 20.

The `./geom` package of the example is a file `geom.tin`:

```tin file=geom.tin
package geom

// Area is the area of a w by h rectangle.
fn Area(w i64, h i64) i64 {
	return w * h
}
```

### Program start

Before `main` runs, every package's globals and package-level `use` resources are set up
on every core (section 11): a package's after those of the packages it imports, and within
a package in declaration order, file by file. Then the `on app.start` handlers run, then
`main`. `main` returns nothing; the program exits with status 0 when it returns, 2 on a
panic, 1 when startup fails, or with the code passed to `quarry.Exit`.

---

## 2. Lexical elements

- **Encoding**: source is UTF-8.
- **Comments**: `// to end of line` only. A comment directly above a declaration is its
  documentation (`tools/gen/gendoc.py` builds [STDLIB.md](STDLIB.md) from them).
- **Statements end at a newline.** There are no semicolons in source. A line whose last
  token is an operator, `,`, `(`, `[` or `{` continues on the next line; so does a call or
  literal whose brackets are still open. Write the opening brace of a block on the same
  line.
- **Identifiers**: letters, digits and `_`, not starting with a digit. `_` alone is the
  blank identifier.
- **Reserved words** (never names): `break catch const continue defer detach else enum
  extern false fail fn for func go guard if import keep let limit map match mut nil
  package parallel range return secret shared struct switch true try type var while
  within`, plus `case` and `default`. `func`, `var`, `range`, `switch`, `case`, `default`,
  `while`, `go` and `extern` only produce a diagnostic naming their edition 1 form.
- **Contextual words** are keywords only where a construct starts and ordinary names
  elsewhere: `in`, `max`, `on`, `use`, `with`, `once`, `select`, `scope`, `arena`,
  `shape`, `dyn`, `wrap`.
- **Integer literals**: `42`, `0x2a`, `0o52`, `0b101010`, with `_` between digits
  (`1_000_000`). Values up to 2^64-1 are allowed; a literal above 2^63-1 only fits
  64-bit unsigned types (or keeps its bit pattern as an `i64`).
- **Float literals**: `3.14`, `1e-9`, `.5`, `6.02e23`.
- **Unit literals**: a number followed directly by a unit is an integer constant in
  nanoseconds or bytes:

  | unit | value |
  |---|---|
  | `ns` `us` `ms` `s` `m` `h` | nanoseconds: `200ms` is 200 000 000, `2.5s` is 2 500 000 000 |
  | `b` `kb` `mb` `gb` | bytes: `kb` is 1024, `mb` 1024², `gb` 1024³ |

  A fractional value must be a whole number of nanoseconds or bytes. Any other letter
  after a number is a compile error (E012 NUMERIC_UNIT). `tide.Wait(5s)`,
  `within 200ms { }`, `limit memory 4mb { }`.
- **Character literals**: `'a'`, `'\n'`, `'\x41'`, `'é'`: an untyped integer constant
  holding the code point (`rune` is a name for `i32`).
- **String literals**: `"text"` with `{expr}` interpolation (section 15) and the escapes
  `\n \t \r \\ \" \' \0 \a \b \f \v \xHH \ooo \uHHHH \UHHHHHHHH`; `{{` and `}}` are braces.
  A raw string in backquotes has neither escapes nor interpolation and may span lines.

### Operators and punctuation

```text
+  -  *  /  %  &  |  ^  <<  >>  &&  ||  !  ~  +%  -%  *%
==  !=  <  <=  >  >=
=  +=  -=  *=  /=  %=  &=  |=  ^=  <<=  >>=  +%=  -%=  *%=
(  )  [  ]  {  }  ,  .  :  ..  ...  ?  ??  !  =>  @
```

---

## 3. Types

| type | size | notes |
|---|---|---|
| `i8 i16 i32 i64` | 1 2 4 8 | signed integers; arithmetic wraps; `rune` is `i32` |
| `u8 u16 u32 u64` | 1 2 4 8 | unsigned integers; arithmetic wraps |
| `f64` | 8 | IEEE-754 double |
| `f32` | 4 | IEEE-754 single: every operation rounds to f32 exactly as Go's float32 does (it is computed in f64 and rounded, which is exact for + - * / and conversions); `[]f32` uses 4 bytes per element; prints and encodes to JSON in its own shortest form (`f32(0.1)` is `0.1`) |
| `bool` | 1 | `true`, `false` |
| `str` | ref | immutable bytes (UTF-8 by convention); never nil; zero value `""` |
| `[]T` | ref | slice: a reference to a header (length, capacity, data) |
| `[N]T` | ref | a `[]T` that starts with N zero elements (`[N][M]T` too) |
| `map[K]V` | ref | hash map, insertion-ordered; K is `str`, an integer type, `bool`, `f64`, or a struct or enum of those; never nil |
| `struct { ... }` | ref | a reference to an object; never nil |
| `enum { ... }` | ref | one of several variants, each with its own data |
| `?T` | ref | optional T: a T or `nil` (T a number, `bool` or reference type; a number is boxed) |
| `!T` | | a result that is a T or a fault (function results only, section 8) |
| `fault` | ref | an error; `nil` means no error |
| `(A, B)` | | several results of a function |
| `fn(A, B) R` | 8 | a function value: a top-level function, or a function literal, which may capture variables of the enclosing functions |
| `dyn S` | 16 | any value whose type has the methods of shape S, with dynamic dispatch |
| `secret T` | as T | a value the compiler keeps away from logs, faults and output (section 18) |
| `T max n` | as T | a str, slice or map of at most n elements (section 17) |
| `query` | ref | a literal's text pieces and values kept apart, for database and cache clients (section 15) |

There are no pointers in user code, no interfaces, no channels and no `byte`/`int`
aliases: use `u8` and `i64`.

### Reference semantics

Strings, slices, maps, structs and enums are references. Assigning or passing one copies
the reference, not the contents:

<!-- tin-prelude
type Point struct {
	x i64
}
-->
```tin body
let a = Point{x: 1}
let b = a
b.x = 2              // a.x is 2 as well
mut xs = []i64{1}
mut ys = xs
ys = append(ys, 2)   // xs sees the new element too: append grows the header in place
```

Use `keep(x)` (a deep copy into long-lived memory) or explicit copies (`copy`,
`ore.Clone`, `sift.Clone`, a new literal) when independent values are needed.

Slices stay references (#352), so the trap is guarded rather than removed: in user code, once
`append` has grown a slice that another local name shares (`mut ys = xs`), reading that other
name is E641 (`ys` would have changed under you). Take `sift.Clone(xs)` for a snapshot.

### Slices

- `len(s)`, `cap(s)`; indexing `s[i]` (bounds checked); slicing `s[lo:hi]`,
  `s[lo:]`, `s[:hi]` shares the elements; `hi` may not exceed `len(s)`.
- `append(s, v1, v2)` and `append(s, t...)` add elements, growing in place (the header is
  updated); always assign the result back: `s = append(s, v)`.
- `make([]T, n)` and `make([]T, n, capacity)`. Elements start as zero values: `""` for
  `str`, an empty slice for `[]T`. `make` with a non-zero length is rejected for struct,
  map and func elements (they have no zero value): use `make([]T, 0, n)` and append, or
  `[]?T`.
- Slice literals: `[]i64{1, 2, 3}`, `[]Point{{x: 1}, {x: 2}}` (the element type may be
  left out of struct elements).
- `[N]T` is a slice that starts with N zero elements: a struct field `cells [16]i64`. It
  is not a value type: assigning it shares it. A literal lists at most N values and the rest
  are zero values: `[3]i64{1, 2}` is `[1 2 0]`, `[2][3]i64{{1}}` is `[[1 0 0] [0 0 0]]`, and
  `[2]i64{1, 2, 3}` is an error (E202).

### Maps

- `make(map[K]V)` or a literal `map[str]i64{"a": 1}`.
- `m[k]` reads (a missing key reads as V's zero value: 0, `""`, an empty slice, a new
  empty struct or map); `let (v, ok) = m[k]` also reports presence; `m[k] = v` writes;
  `m[k] += 1` updates; `delete(m, k)` removes; `len(m)` counts.
- `for k, v in m` iterates in **insertion order**: a new key goes last, updating a key
  keeps its place, and deleting then re-adding moves it to the end. JSON output and
  `atlas.Keys` / `atlas.Values` follow the same order; printing a map sorts its keys like
  Go (strings bytewise, numbers by value, floats with NaN first, `false` before `true`)
  and prints each key and value with its own type.
- Keys are `str`, integers, `bool`, `f64` (by bits), or structs and enums made only of
  those, which hash and compare **by value**. A struct key is copied in, so changing the
  original afterwards does not change the map. Slices, maps, funcs, optionals and faults
  cannot be keys (compile error).
- `atlas.Keys(m)`, `atlas.Values(m)`, `atlas.SortedKeys(m)` return the keys or values as a
  slice, and `atlas.Clone`, `Copy`, `Equal`, `EqualFunc` and `DeleteFunc` work on whole
  maps; `sift.Map(xs, f)`, `sift.Filter(xs, keep)` and `sift.Reduce(xs, start, f)` work on
  any slice, next to `sift.Sort`, `Index`, `Contains`, `Insert`, `Delete` and the rest of
  the slice functions.

### Structs

```tin
type Point struct {
	x    i64
	y    i64
	name str
	tags []str
	next ?Point
}

fn main() {
	let p = Point{x: 1, y: 2, name: "a", tags: []str{}}
	let q = Point{x: 3}
	_ = p
	_ = q
}
```

- A struct literal names its fields: `Point{x: 1, y: 2}`. Positional literals do not
  exist, so a struct with private fields is built only inside its package.
- One field per line (`x, y i64` declares two of one type). A field may carry attributes
  (`@json("id") id i64`, section 19).
- Fields of type `str`, `[]T` and `[N]T` that a literal leaves out start as `""` and
  empty slices; numbers as 0. Fields of struct, map and func type must be set (they cannot
  be nil); make them `?T` to allow nil.
- `p.x` reads a field, `p.x = 3` writes it (see `mut` parameters in section 5).
- `new(T)` is `T{}`.

### Enums

An enum is a value that is one of several variants, each with its own data:

```tin
import "constraints"

type Shape enum {
	Circle(f64)
	Rect(f64, f64)
	Named(str, Shape)   // enums may hold themselves (trees)
	Empty
}

type Color enum {
	Red
	Green
	Blue
}

type Option[T constraints.Any] enum {
	Some(T)
	None
}

fn area(s Shape) f64 {
	return match s {
		Circle(r) => 3.14159 * r * r
		Rect(w, h) => w * h
		Named(_, inner) => area(inner)   // _ skips a value
		Empty => 0.0
	}
}

fn main() {
	let s = Shape.Rect(3.0, 4.0)
	let c = Color.Red
	let o = Option[i64].Some(7)
	_ = area(s)
	_ = c
	_ = o
}
```

- A variant lists the types of its data. The data is read only through `match`
  (section 7): there is no `s.r`, and no struct literal `Shape{...}`. An arm binds every
  value of one variant, or lists several variants that bind nothing (`Green, Blue =>`).
  A `match` that misses a variant without `_` is a compile error naming the missing ones.
- `==` compares by value (same variant, equal data) when all the data compares by value
  (numbers, bools, strs, such enums); an enum holding a slice, map, struct or func cannot
  be compared.
- Printing gives `Rect(3 4)` / `Red`; JSON (argo) is `{"Rect":{"$0":3,"$1":4}}` for a
  variant with data (`$0`, `$1` ... are the positions) and `"Red"` for one without, both
  ways.
- The zero value (for example next to a fault) is the first variant without data.
- Enums are references underneath, like structs: `keep` copies them, and the region check
  treats their data like struct fields. Variants follow the export rule.

### Strings

- `len(s)` is the byte length; `s[i]` is a `u8` (bounds checked); `s[lo:hi]` is a
  substring; `+` concatenates; `==`, `!=`, `<`, `<=`, `>`, `>=` compare byte-wise.
- `for i, c in s` iterates UTF-8 code points: `i` the byte offset, `c` the code point as
  an `i32` (invalid bytes give U+FFFD); `for c in s` gives the code points alone.
- Conversions: `str(b)` from a `[]u8`, `str(c)` from an integer code point, `[]u8(s)` to
  bytes; `mint` converts numbers (`say.Str` too, section 16).

### Optionals and faults

`?T` and `fault` are the only types with a `nil` value; see sections 8 and 9.

### Function values

```tin
import "say"

type Handler = fn(i64) i64

fn double(x i64) i64 {
	return 2 * x
}

fn main() {
	let f Handler = double
	let g = fn(x i64) i64 { return x + 1 }   // a literal; it may capture local variables
	say.Line(f(3), g(3))
}
```

A function type is `fn(A, B) R`, `fn(A) !R` for one that may fail, and `fn(mut A)` for one
that may modify its argument. As a result type it is written in parentheses:
`fn counter() (fn() i64)`.

### Closures

A function literal may read and write the variables of the functions around it: the
closure and its parent share one variable, so a write by either is seen by both.

```tin
import "say"

fn makeCounter() (fn() i64) {
	mut n = 0
	return fn() i64 {
		n += 1
		return n
	}
}

fn main() {
	let c = makeCounter()
	say.Line(c(), c(), c())   // 1 2 3
}
```

- **Each iteration has its own loop variable**: in `for i in 0..3` and `for v in xs`,
  closures made in different iterations capture different variables.
- **Where the closure lives.** A function literal that is called at once, or passed to one
  of the library functions that only call what they are given (`sift.Each`, `Map`,
  `Filter`, `Reduce` and the `*Func` functions of `sift`, `atlas` and `twine`, a `with`
  policy's `Run`), keeps its captured variables on the caller's stack frame: no pool
  allocation. Every other closure (returned, stored in a slice, a struct or a map, passed
  to your own function, deferred) allocates its descriptor and cells in the current
  request pool and lives as long as that pool.
- **Long-lived closures.** Storing a closure that captures request memory in a global, or
  anywhere long-lived, without `keep` is a compile error naming the global. `keep(f)`
  deep-copies the descriptor and every captured variable into the long-lived heap.
- **What a closure may store in its captured variables.** A closure passed only to
  functions that call it (`sift.Each` and the others above) is part of its parent's frame,
  so its body may store request memory in a captured local, for example
  `out = append(out, s)` to collect results. Any other closure may be kept, after which its
  captured variables are long-lived, so its body storing request memory in a captured
  variable is a compile error naming the variable: store `keep(v)`, or pass the closure
  only to functions that call it.
- **Captured `mut` parameters are rejected**: a function literal cannot capture a `mut`
  parameter (the parameter is the caller's variable, not a cell); copy it into a local, or
  pass it as an argument.
- **Recursion.** A local closure cannot call itself (a variable of function type needs an
  initializer): use a top-level function, or pass the function to itself.
- All captured variables are cells; copying a variable that is never reassigned by value,
  instead of sharing a cell, is a later optimization (it changes no result).

A `mut` parameter is part of a function's type: `fn put(b mut Box)` has type
`fn(mut Box)`, which is not `fn(Box)`. A call through a function value is checked like a
direct one: an argument for a `mut` parameter must be modifiable, and because the callee
is unknown, the compiler assumes it may store request memory there, so passing long-lived
memory (a global, or anything reachable from one) to a `mut` parameter of a function value
is a compile error. Call the function directly, or pass request-owned memory.

### Conversions

There are no implicit conversions between types. A conversion is a call of the type:

| conversion | meaning |
|---|---|
| `i64(x)`, `u8(x)`, `i32(x)` ... | integer to integer: truncates to the width, then sign- or zero-extends (`u8(x)` is how code asks for the low byte) |
| `f64(n)` | integer to float |
| `i64(f)` | float to integer, truncating toward zero; panics when the result does not fit the type or `f` is NaN (section 18) |
| `str(b)` | `[]u8` to `str` (copies) |
| `[]u8(s)` | `str` to `[]u8` (copies) |
| `str(c)` | integer code point to a one-character `str` (UTF-8) |
| `T(x)` | between a named type and its underlying type |

### Named types and aliases

`type Celsius f64`, `type IDs []i64`, `type Handler fn(Req, mut Out)` declare new types;
a named type converts to and from its underlying type explicitly. `type Id = i64` is an
alias: another name for the same type.

### Shapes and `dyn`

A *shape* is a set of method signatures. A type satisfies a shape structurally: if it has
the methods, it satisfies it, with no declaration. Shapes replace interfaces.

```tin
import "constraints"

shape Reader {
	Read(buf mut []u8) !i64
}

shape Writer {
	Write(data []u8) !i64
}

shape ReadWriter {   // composition by listing shapes
	Reader
	Writer
	Flush() !i64
}

shape Ordered = i64 | i32 | f64 | str   // a named union

shape Seq[T constraints.Any] {   // a shape with type parameters
	Next() ?T
	Close() !i64
}
```

A member is a method signature or the name of another shape, one per line. A method
signature is an `fn` signature without `fn`, receiver and body: the same `mut` marks and
`!T` results apply, and a method's receiver is implicit.

A shape is used in two ways:

- **Statically**, as a type-parameter constraint:
  `fn copyAll[R Reader, W Writer](dst mut W, src mut R) !i64`. This is the default; it is
  monomorphized, with no dispatch and no allocation. A type satisfies it by having the
  methods: same names, parameter types and `mut` marks, result types (including `!T`),
  and variadic mark. Receiver mutability is not part of satisfaction — a `mut` receiver is
  a property of the concrete method, so a call to one takes the call-site `mut`, and a
  generic body that makes such a call declares its parameter `mut`.
- **Dynamically**, as `dyn S`: the object pointer plus a static table of its methods for
  `S`, converting from a concrete type where a `dyn S` is expected. Conversion allocates
  nothing, and a method call uses one indirect call. A `dyn S` is never nil; `?dyn S` is
  the optional.

```tin
import "say"

shape Named {
	name() str
}

type Dog struct {
	n str
}

fn (d Dog) name() str {
	return d.n
}

fn greet[T Named](x T) str {   // static: one copy of greet per type
	return "hello {x.name()}"
}

fn main() {
	let d = Dog{n: "rex"}
	let v dyn Named = d          // dynamic: object and method table
	say.Line(greet(d), v.name())
}
```

There is no downcast and no type switch: a closed set of cases is an `enum` with an
exhaustive `match`, an open set is a method on the shape. A named union
(`shape Ordered = i64 | f64 | str`) is a constraint listing concrete types.

**Status.** Shapes support structural constraints, composition, named unions and generic
instances. Calls through shaped type parameters are direct calls on concrete types. `dyn S`
uses a two-word object/table pair; the checker verifies conversions, and method calls
dispatch through the table without allocating. `?dyn S`, `[]dyn S`, `keep` of a dynamic
value or container, and region checks are implemented. Map values and `!dyn` results
remain deferred; see [the representation and staging note](../../design/design_dyn.md). The
`io` shapes live in `toolchain/std/io`. `constraints.Any`, `constraints.Comparable` and
`sift.Ordered` are ordinary library shapes, not language keywords; import their packages
where used.

---

## 4. Constants

```tin
const Limit = 100              // untyped integer constant
const Pi = 3.141592653589793   // untyped float constant
const Name = "tin"             // string constant
const Mask u8 = 0x0f           // typed constant
const Timeout = 200ms          // a unit literal is an integer constant
```

- Constants are declared at package level, one per declaration. There is no `iota`:
  a set of named alternatives is an `enum`.
- Initializers must be constant expressions. Constants cannot be reassigned. They require
  no runtime storage.
- Untyped constants take the type the context needs and must fit it: `let b u8 = 300` and
  `i8(200)` are compile errors.
- Constant arithmetic is exact (#362): `+`, `-`, `*` and negation compute the true value,
  which must lie in -2^63 .. 2^64-1 and fit the type the constant takes (E223).
  `9223372036854775807 + 1` is 2^63: a `u64`, but no `i64`. A literal above 2^63-1, or the
  result of a bit operation (`&`, `|`, `^`, `~`, `<<`, `>>`) on one, keeps its bit pattern
  as an `i64` (`0xffffffffffffffff` is -1 there); a shift may not lose a set bit. Values above
  2^63-1 are treated as unsigned for `>>`, `/`, `%` and comparisons. A constant shift count
  is between 0 and the width less one (E224). `+%`, `-%` and `*%` fold modulo 2^64.
- A constant used where no type is known becomes an `i64` (integers) or `f64` (floats).

---

## 5. Declarations

### Variables: `let` and `mut`

<!-- tin-prelude
fn pair() (i64, i64) {
	return 1, 2
}

let lookup = map[str]i64{"k": 1}
-->
```tin body
let x = 1                    // a name that is not reassigned (type inferred)
mut y i64 = 2                // a name that is, with a type
mut s []str = []str{}
let (a, b) = pair()          // the results of a call with several results
let (v, ok) = lookup["k"]    // a map read with its presence
y += x
s = append(s, "a")
_ = a + b + v
_ = ok
```

- **`let`** binds a name that is not reassigned; **`mut`** binds one that is. Both infer
  the type from the value or take one: `let n i64 = 0`. Every local has an initializer.
  Assigning a `let` name (`=`, `+=`, a tuple assignment, from a closure; a package-level
  `let` too) is a compile error (E711); `tin fix -edition 1` declares such names `mut`. So is
  assigning a loop's variable (`for i in 0..n`, `for x in xs`), which the loop sets.
- `let` fixes the name, not the object: what a binding refers to can still change through
  it (a struct field, a slice element). Changes through parameters are governed by `mut`
  parameters and the call-site `mut` below.
- `let (a, b) = f()` binds several results; `_` discards one (never a fault). A name
  cannot be declared twice in the same block.

### Globals

```tin
import "say"

const Workers = 4
let greeting = "hello"           // per core, set once when the core starts
mut hits i64 = 0                 // per core, changed by this core's code
mut cache map[str]str = map[str]str{}

fn main() {
	hits += 1
	cache[keep("k")] = keep(greeting)
	say.Line(hits, cache)
}
```

Globals are per core (section 11): each core thread has its own copy, and initializers
run once on every core. Values stored into globals live in the long-lived heap
(section 12). A `mut` global of a type with a zero value may leave out its initializer
(`mut hits i64`). A global's initializer may fail only through `try`, which aborts
startup.

Globals are per core, and `main` runs on core 0 only: a global that `main` (or a function it
calls) assigns holds the new value on core 0 alone, while the handlers of the other cores read
their own copy, still the initializer's. With one core that goes unnoticed; with several it
answers wrongly. In a program that starts cores (`anvil.Serve`, `hearth.Run`) it is a compile
error (E131). A global that only `main`'s own code reads may be assigned there.

```tin error=E131
import "anvil"
import "say"

mut table []str

fn h(q anvil.Req, w mut anvil.Out) {
	w.Text("{len(table)}")
}

fn main() {
	table = keep(make([]str, 3))      // E131: only core 0 would have it
	say.Line(anvil.Serve(":8080", h))
}
```

Assign it where every core runs: in the initializer (`let table = load()`), in `on core.start`
(before the core serves; section "`use`, `on`, `once`") or in `once`. Data built from work done
once in `on app.start`, such as a file, is read and parsed by each core in `on core.start`
(`examples/percore.tin`).

An initializer may use imported packages and the globals declared before it. Using a
later global of its package (or itself), directly or through a function it calls or refers
to, is a compile error: that global's initializer has not run yet.

`use name = expr` at package level is a per-core resource opened with the globals and
closed when the core stops (section 11). A `shared let` is one process-wide value (section 11).

### Functions

```tin
fn add(a i64, b i64) i64 {
	return a + b
}

fn divmod(a i64, b i64) (i64, i64) {
	return a / b, a % b
}

fn parse(s str) !i64 {
	if s == "" {
		fail "empty"
	}
	return len(s)
}

fn fill(xs mut []i64, v i64) {      // may modify its argument
	for i in 0..len(xs) {
		xs[i] = v
	}
}

fn main() {
	mut xs = make([]i64, 3)
	fill(mut xs, add(1, 2))
	let (q, r) = divmod(7, 2)
	_ = q + r
	_ = parse("12") catch _ { 0 }
}
```

- Each parameter has a type (`a i64, b i64`; a shared type `a, b i64` is also accepted).
  Up to 8 integer and 8 float parameters. A variadic last parameter `xs ...i64` is a `[]i64` inside, called
  `sum(1, 2, 3)` or `sum(xs...)` (*not yet implemented in edition 1*).
- Results: none, one (`i64`), a list (`(i64, str)`), or any of these marked as able to
  fail (`!i64`, `!(i64, str)`, `!`); up to 8. There are no named results.
- A function with results ends every path in `return` (functions do not have tail values;
  only boundary blocks, `catch` blocks and `match` arms do).
- Parameters are read-only: modifying a parameter's contents (assigning its fields or
  elements, appending to it, storing into its map) is a compile error unless the
  parameter is declared `mut`. Passing a read-only parameter on to a `mut` parameter is
  also rejected. Reassigning the parameter variable itself is allowed, except for a `mut`
  struct, optional or map parameter: `b = Box{}` or `x = nil` there would rebind only the
  callee's copy, which the caller (who wrote `mut`) would never see, so it is a compile
  error. Modify the fields or elements instead, or return the new value. A `mut` slice
  parameter may still be reassigned, for `xs = append(xs, v)`.
- `mut` is for a struct, a slice, a map or an optional of one: a callee modifies what they
  hold. A number, a `bool`, a `str` or a fault is passed by value, so `mut` on such a
  parameter is a compile error (it would silently do nothing), also for a generic function
  at the instantiation that makes the parameter one of those types.
- **Call-site `mut`.** An argument for a `mut` parameter is written `mut x`, so every
  call shows what it may modify: `fill(mut xs, 0)`, `sift.Ints(mut xs)`,
  `argo.Put(mut buf, v)`, `argo.Get(text, mut v)`, and through function values too
  (`f(mut box)`). Leaving it out, or writing it for a parameter that is not `mut`, is a
  compile error. Method receivers (`p.move(1, 2)`) and the builtins `append`, `copy` and
  `delete` take no `mut`.

### Methods

```tin
type Point struct {
	x i64
	y i64
}

fn (p Point) sum() i64 {
	return p.x + p.y
}

fn (p mut Point) move(dx i64, dy i64) {
	p.x += dx
	p.y += dy
}

fn main() {
	let p = Point{x: 1, y: 2}
	p.move(1, 2)
	_ = p.sum()
}
```

The receiver comes first and is a parameter like any other: `mut` lets the method modify
it. Methods are declared on named types in the same package.

### Types

```tin
import "constraints"

type Point struct {
	x i64
	y i64
}

type Stack[T constraints.Any] struct {   // generic: section 13
	items []T
}

type Id i64                               // a distinct named type
type Score = i64                          // an alias
```

---

## 6. Expressions

### Precedence

From the tightest to the loosest; binary operators of one level associate to the left.

| level | operators |
|---|---|
| postfix | calls `f(x)`, indexing `s[i]`, slicing `s[lo:hi]`, selectors `x.f`, type arguments `f[T]`, composite literals `T{...}`, `opt ?? fallback` |
| unary | `-x`, `!x`, `~x` and `^x` (bitwise not), `try e` |
| 5 | `*`, `/`, `%`, `<<`, `>>`, `&`, `*%` |
| 4 | `+`, `-`, `\|`, `^`, `+%`, `-%` |
| 3 | `==`, `!=`, `<`, `<=`, `>`, `>=`; `..` (a range, only after `for ... in`) |
| 2 | `&&` |
| 1 | `\|\|` |
| suffix | `e wrap "msg"` (after `try`, section 8) |
| statement | `e catch err { ... }`, on a whole initializer, assignment, return value or statement |

`a < b > c` is `(a < b) > c`, a type error: generic brackets are square (`f[T](x)`), never
angle brackets, so a comparison never depends on what its operands are.

### Arithmetic

- Both operands of a binary operator have the same type (after untyped constants adapt):
  `i32 + i64` is an error; convert one side.
- Integer arithmetic is checked (#362): `+`, `-`, `*` and negation panic with `integer
  overflow` when the exact result does not fit the operand type (`i8` through `u64`), and
  signed `/` panics on the most negative value divided by -1. `%` cannot overflow
  (`-9223372036854775808 % -1` is 0). Division by zero panics. `/` truncates toward zero;
  `%` has the sign of the dividend. In a request handler the panic is that request's 500
  and the core goes on serving (section 18).
- Wrapping is written out: `a +% b`, `a -% b` and `a *% b` (and `+%=`, `-%=`, `*%=`)
  compute modulo 2^width, for hashes, checksums and random number generators:
  `h = (h ^ b) *% 1099511628211`. A function declared `@wrap` (section 19) keeps the
  machine's arithmetic throughout: `+ - *` and negation wrap, the most negative value / -1
  is itself, and shift counts are taken modulo 64; it is for kernels whose arithmetic is
  modular everywhere (cipher rounds, constant-time field arithmetic). Its closures, generic
  instances and methods are `@wrap` too.
- `>>` is arithmetic for signed types and logical for unsigned types. A shift count must
  be between 0 and the width of the shifted value less one: `u8(1) << 8` panics (a constant
  count out of range is E224), and so does a negative count. Bits shifted out are dropped:
  a shift is a bit operation, so `u8(0x81) << 1` is 2.
- The compiler removes a check that cannot fire: the counter of `for i in 0..n` steps up
  below its bound, and after inlining, ranges known from constants, lengths, narrow types,
  locals assigned once and loop counters prove that `i * 31` or `i + j + 1` on such values
  fits.
- `&&` and `||` short-circuit and take `bool` operands.
- Strings support `+` and comparisons; `bool` supports `==`, `!=`, `!`, `&&`, `||`.
- Comparing references: optionals and faults compare with `nil`. `==` and `!=` on structs
  and enums compare **by value** (#352): field by field, so `P{x: 1} == P{x: 1}` is true
  (a struct holding a slice, map, function, `dyn` value or optional has no value equality:
  E237). `same(a, b)` is identity, whether two names are one object; it takes two structs,
  slices or maps of one type. `==` on slices and maps compares identity (compare elements
  with `sift.Equal` and friends). A slice or map assigned to a second name is one object
  (`mut ys = xs` then `ys = append(ys, 2)` grows `xs` as well, the example in section 3):
  copy with `copy` or `ore.Clone` when two independent values are meant.

### Conditions

Conditions of `if`, `for` and match guards must be `bool`; there is no truthiness.

### Calls

- Arguments are evaluated left to right.
- A call that returns several values is used in `let (a, b) = f()`, an assignment
  `a, b = f()`, a `return` of the same result list, or with `try`.
- Calling through a function value: `f(x)`.
- Method call: `x.m(args)`; `pkg.F(args)` for a package function; `F[T](args)` and
  `pkg.F[T](args)` with explicit type arguments.

### Composite literals

`T{f: v, g: w}`, `[]T{a, b}`, `map[K]V{k: v}`, `Stack[i64]{items: []i64{}}`. Inside a
slice or map literal, the element type may be left out of struct elements:
`[]Point{{x: 1}, {x: 2}}`. A struct literal always names its fields.

### Nil coalescing

`opt ?? fallback` is the value of an optional, or `fallback` when it is nil:
`let name = maybe ?? "anonymous"` (*not yet implemented*: the parser reads it, the
checker does not; write `if let`, section 9).

---

## 7. Statements

<!-- tin-prelude
fn work(x i64) {
}
-->
```tin body
mut x = 1                    // declaration (section 5)
x = 2                        // assignment
mut a = 1
mut b = 2
a, b = b, a                  // parallel assignment
x += 1                       // compound assignment (all binary operators)
x *= 2
work(x)                      // expression statement (a call)
```

<!-- tin-prelude
fn work(x i64) {
}
-->
```tin body
let n = 3
if n > 0 {
	work(n)
} else if n == 0 {
	work(0)
} else {
	work(-n)
}
```

There are no `++`/`--` (write `+= 1`), no `goto`, no fallthrough and no semicolons.

### `for`

One `for` with four shapes:

<!-- tin-prelude
import "say"
-->
```tin body
let xs = []i64{10, 20, 30}
let m = map[str]i64{"a": 1}
mut running = true
for x in xs {                     // elements
	say.Line(x)
}
for i, x in xs {                  // index and element
	say.Line(i, x)
}
for k, v in m {                   // a map, in insertion order
	say.Line(k, v)
}
for i, c in "héllo" {             // a str: byte offset and code point
	say.Line(i, c)
}
for i in 0..len(xs) {             // a half-open integer range
	say.Line(i)
}
for i in (0..10).step(2) {        // a range with a step
	say.Line(i)
}
for running {                     // while a condition holds
	running = false
}
for {                             // forever
	break
}
```

- `lo..hi` counts from `lo` up to `hi - 1`; there is no `..=`. The bounds are evaluated
  once. The bounds prover reads this form directly: `for i in 0..len(xs) { xs[i] }` has no
  bounds check.
- `for x in xs` gives a copy of each element (a reference for reference types); `for i, x`
  gives the index too. To change elements, assign `xs[i]`.
- Each iteration has its own loop variables (section 3, Closures).
- A loop may have a label; `break` and `continue` take an optional label naming an
  enclosing loop:

<!-- tin-prelude
import "say"
-->
```tin body
outer: for i in 0..3 {
	for j in 0..3 {
		if j > i {
			continue outer
		}
		if i == 2 {
			break outer
		}
		say.Line(i, j)
	}
}
```

### `match`

`match` compares a value with patterns, in order, and runs the first arm that matches.
It is a statement, or an expression when its arms give values:

<!-- tin-prelude
type Shape enum {
	Circle(f64)
	Rect(f64, f64)
	Empty
}
-->
```tin
fn label(status i64) str {
	return match status {
		200 => "ok"
		301, 302 => "redirect"
		404 => "missing"
		500..600 => "server error"
		n if n < 0 => "invalid"
		_ => "other"
	}
}

fn area(s Shape) f64 {
	mut area = 0.0
	match s {                          // an enum: every variant, or _
		Circle(r) => area = 3.14159 * r * r
		Rect(w, h) => area = w * h
		Empty => {
			return 0.0
		}
	}
	return area
}
```

- An arm is `patterns => expression` or `patterns => { block }`. An arm may also be a
  `return`, `break`, `continue`, `fail` or an assignment; `break` and `continue` apply to
  the enclosing loop. There is no fallthrough.
- **Patterns**: literals (numbers, strings, characters, `true`, `false`, `nil`); ranges
  with literal ends (`500..600`, half-open); enum variants with bindings (`Rect(w, h)`,
  `Shape.Rect(w, _)`, nested `Pair(Circle(r), 2)`); `_`; a name; several patterns
  separated by `,`; and a guard after the patterns (`n if n > 100 =>`), which, when false,
  goes on to the next arm.
- **Names**: a name that is a package-level constant or variable (a sentinel such as
  `ErrNotFound`) compares with it; a variant name matches that variant of an enum subject;
  any other name binds the value (`n if n > 100`). Naming a local variable is an error:
  compare with a guard. Inside a variant's values a name always binds.
- An enum `match` handles every variant or has `_`. A `match` that gives a value handles
  every value (`_`, every variant, or `true` and `false`).
- A `match` as a statement, `let` or assignment value, `return` value or a `catch` or
  boundary block's last expression may have arms that are blocks that leave; inside a
  larger expression its arms are expressions.
- On a `fault`, arms compare with `fault.Is`, so a wrapped fault matches its sentinel
  (section 8). On an optional, a `nil` arm narrows the value for the arms after it.

### `return`, `defer`

`return`, `return x`, `return a, b`. `defer f(a, b)` (section 8).

---

## 8. Faults

A function that can fail says so in its result: `!T` is "a T, or a fault", `!(A, B)`
"an A and a B, or a fault", and `!` alone "nothing, or a fault".

```tin
import "flume"
import "say"

fn parse(s str) !i64 {
	if s == "" {
		fail "empty input"             // leave with a fault (zero values for the rest)
	}
	mut n i64 = 0
	for i in 0..len(s) {
		let c = s[i]
		if c < '0' || c > '9' {
			fail "bad digit {str(c)} at {i}"
		}
		n = n * 10 + i64(c - '0')
	}
	return n                           // success: just the value
}

fn double(s str) !i64 {
	let v = try parse(s)               // on a fault: pass it upward
	return v * 2
}

fn save(path str, text str) ! {       // can fail, gives nothing
	mut w = try flume.Create(path)
	w.Str(text)
	try w.Close()
}                                      // running off the end succeeds

fn main() {
	let v = double("21") catch err {   // handle it where it happens
		say.Line("error:", err)
		0
	}
	let (n, err) = double("x")         // or look at the fault yourself
	if err != nil {
		say.Line("error:", err)        // a fault prints as its message
	}
	say.Line(v, n)
	save("/tmp/tin-doc.txt", "hi") catch err {
		say.Line(err)
	}
}
```

- **One way to write it.** A result list ending in `fault` is rejected: write `!T`. In a
  `!T` function `return` gives only the values (`return v`; a bare `return` in a `!`
  function), and `fail X` leaves with a fault: X is a `str` message (interpolated like any
  string) or a `fault` value. `return v, nil` and `return 0, fail(...)` are compile errors
  that point at these forms. A fault always comes with zero values: `str`, slice, map and
  struct zeros are real values, never nil, so a struct that owns a resource must treat its
  zero value as closed (as `flume.Writer` and `wire.Conn` do).
- **A fault must be handled.** Ignoring a call's fault is a compile error; so is a fault
  variable that is never read, and `_` in a fault position.
- `fail("text")` as an expression makes a fault value (to store or pass along);
  `say.Fault(format, args...)` formats one. A fault prints as its message, and
  `say.Str(err)` gives the message as a `str`.
- `try` passes a fault upward (inside a `!T` function): `let v = try f()`,
  `v = try f()`, `let (a, b) = try f()`, `try f()` (a statement), `return try f()`.
- `try e wrap "msg"` passes the fault upward with context: it is
  `e catch err { fail fault.Wrap(err, "msg") }`, so
  `let user = try load(id) wrap "loading user {id}"` fails with
  `loading user 7: not found`. `wrap` follows only a `try`.
- `catch` handles a fault in place: `e catch err { ... }` on a whole statement,
  initializer, assignment or return value (not inside a larger expression). `err` is the
  fault (`_` to ignore it). When a value is needed, the block's last expression is that
  value; otherwise, or when the call has several results, the block must leave (`return`,
  `break`, `continue`, `fail`, `panic`). On success the block does not run.

<!-- tin-prelude
import "herald"
import "mint"
import "say"

fn parsePair(s str) !(i64, i64) {
	return 1, 2
}

fn closeIt() ! {
}
-->
```tin body
let text = "80"
let port = mint.Atoi(text) catch _ { 8080 }
for s in []str{"1,2", "x"} {
	let (n, m) = parsePair(s) catch err {
		say.Line("skipping:", err)
		continue
	}
	say.Line(n, m, port)
}
closeIt() catch err { herald.Warn(say.Str(err)) }
```

- `try` and `catch` cannot be nested inside another expression: bind the inner result
  first.
- **Chains and sentinels** (package `fault`, design/interface_faults.md). A package-level
  `let ErrNotFound = fault("not found")` is a sentinel: each such declaration has its own
  identity (`fault("...")` anywhere else is a compile error; use `fail("msg")`).
  `fault.Wrap(err, "loading user {id}")` is a fault reading `loading user 7: not found`
  whose cause is `err` (nil when `err` is nil); `fault.Is(err, ErrNotFound)` walks the
  causes and joined faults and compares identity (a fault without identity matches only
  itself); `fault.Cause`, `fault.Join([]fault{a, b})` (messages on separate lines) and
  `fault.Message` complete it. Functions that make a fault are declared `!`: their fault is
  the value, so `fail fault.Wrap(err, "context")` or `let e = fault.Join(errs)`. The
  runtime's sentinels are `fault.Canceled`, `fault.DeadlineExceeded` (every deadline wait
  fails with it), `fault.LimitExceeded`, `fault.Overloaded`, `fault.Draining` and
  `fault.Panic`. `==` on faults compares the references; a `match` compares with
  `fault.Is` (a `nil` arm matches no fault):

```tin
import "fault"

let ErrNotFound = fault("not found")

fn status(err fault) i64 {
	return match err {
		nil => 200
		ErrNotFound => 404
		fault.DeadlineExceeded, fault.Overloaded => 503
		_ => 500
	}
}
```

- `defer f(args)` evaluates `f` and its arguments when the defer statement runs and calls
  `f` when the function returns, last deferred first, on every return path including the
  returns `try` makes. A defer inside a loop is rejected (it would run once per function,
  not per iteration: move the loop body into a function). Deferring a call that returns a
  fault is rejected (the fault would be lost: defer a function that handles it). Deferred
  calls must be plain function or method calls.
- Deferred calls also run when a panic unwinds through their function inside a request,
  a task or a `guard` block, innermost first, before the request's resource cleanups; a
  panic inside a deferred call during that unwinding ends the process.
- `panic("message")` stops the program with status 2 after printing `panic: message`
  and a backtrace of the calling functions (inlined functions do not appear), unless a
  `guard` block (section 10) or a request's implicit guard catches it. A failed bounds
  check prints `index out of range [5] with length 3`.

---

## 9. Optionals

`?T` holds a `T` or `nil` (T is a number, `bool` or a reference type: str, slice, map, struct,
enum, `dyn S`). `?i64`, `?f64`, `?bool` and the other number types (#353) are a box holding
the value, made where a number meets an optional (`let n ?i64 = 5`, `return i`, a field or a
function argument); nil is no box. A variable checked with `n != nil` (or `if let`, `&&`,
`||`, the arms of a `match`) reads as the number inside the branch; `==` and `!=` between two
optional numbers compare by value (both nil, or both set and equal). A global holding one is
assigned `keep(5)`, as any value stored where it outlives the request. JSON `null` and a
missing member are nil, a wrong type is a fault (`argo`).
Inside a branch where the compiler can see the check, the variable has type `T`:

<!-- tin-prelude
import "say"

type User struct {
	name str
}

type Node struct {
	left  ?Node
	right ?Node
}

fn find(id i64) ?User {
	return nil
}

fn depth(n Node) i64 {
	let l = n.left
	let r = n.right
	if l == nil || r == nil {   // both narrowed after the if, since it returns
		return 1
	}
	return depth(l) + depth(r)
}
-->
```tin body
let u = find(7)
if u == nil {
	return
}
say.Line(u.name)                // u is a User from here on

if let v = find(8) {            // binds the value when it is not nil
	say.Line(v.name)
}

let a = find(1)
let b = find(2)
if a != nil && b != nil {       // both narrowed inside
	say.Line(a.name, b.name)
}
```

- Narrowing works on local variables in `if x != nil {...}`, `if x == nil {...} else
  {...}`, `if x == nil { return }` (narrowed after), `&&` / `||` combinations of these,
  and the arms after a `nil` arm of a `match`. Assigning `nil` to a narrowed variable is a
  type error. Store a field in a local first to narrow it (`let l = n.left`).
- `if let v = opt { ... }` binds `v` (a `T`) when `opt` is not nil.
- Using a `?T` without narrowing is a compile error. Map reads of missing keys return the
  zero value, not an optional; use `let (v, ok) = m[k]` to tell.

---

## 10. Boundary blocks

A boundary block is a keyword, its arguments and a block. It runs the block inside a
boundary of its own (a deadline, a budget, a policy, a guard against panics), and its
value is the block's **last expression**. `fail` and `try` leave the block with a fault,
which is the block's fault: handle it with `try` in front of the block, or `catch` after
it. `return`, `break` and `continue` cannot leave a boundary block (a compile error that
says so).

<!-- tin-prelude
import "fault"
import "say"
import "tide"

fn load(id i64) !str {
	try tide.Wait(1ms)
	return "user{id}"
}

fn render(xs []i64) i64 {
	return xs[3]
}
-->
```tin body
let profile = try within 200ms {          // a deadline
	try load(7)
}
let page = guard {                         // a panic inside becomes fault.Panic
	render([]i64{1, 2})
} catch err {
	say.Line("render failed:", fault.Is(err, fault.Panic))
	0
}
let summary = try limit memory 4mb, tasks 8 {
	let name = try load(9)
	len(name)
}
say.Line(profile, page, summary)
```

- **`within d { }`**: a deadline `d` nanoseconds from now (`200ms`, `5s`), or the
  enclosing one when that is earlier (the request's `TIN_DEADLINE_MS`, an outer `within`).
  Every wait inside (`tide.Wait`, `wire`, database and cache clients, file reads on helper
  threads, `select`) fails with `fault.DeadlineExceeded` past it, and the block gives that
  fault. Code that does not wait is stopped at its next safepoint: a program that starts
  cores polls in its own loops and function entries by default; elsewhere, check
  `task.Canceled()` or build with `--polls` ([TOOLING.md](TOOLING.md)).
- **`limit memory n, tasks k { }`**: a budget of pool memory and of tasks started inside
  (either bound alone is allowed). Passing it leaves the block with `fault.LimitExceeded`
  at once, after its defers and cleanups.
- **`guard { }`**: a panic inside (a failed bounds check, `panic(...)`, a nil map key)
  unwinds the block, runs its defers, and becomes the block's fault, `fault.Panic` with
  the panic message. Every request handler, `on` handler and `anvil.OnTick` /
  `anvil.OnRelay` handler runs inside an implicit guard.
- **`with p { }`**: runs the block through a policy, a value whose type has a method
  `Run(body fn() !T) !T` (the shape `policy.Policy`). `policy.Retry(3)` runs the block
  again while it fails, `policy.Cached(cache, key, ttl)` answers from a cache,
  `policy.Trace(name)` reports its duration and fault, and `policy.Bind(slot, v)` binds a
  typed ambient value (`slot.Get()`) for the block and the tasks it spawns. `Run` may
  only call `body`, or pass it to a function that only calls it.
- **`parallel { }`**: each line of the block is a child task (section 11); the value is
  the tuple of their values, `let (user, orders) = try parallel { ... }`.
- **`arena { }`**: the block's temporary allocations are dropped at its end and its value
  is copied out (*not yet implemented*, #236).

```tin
import "constraints"
import "policy"
import "say"

let requestID = policy.NewSlot[str]("request id")

mut tries i64 = 0

fn flaky() !i64 {
	tries += 1
	if tries < 3 {
		fail "attempt {tries} failed"
	}
	return tries
}

fn current() str {
	return requestID.Get() catch _ { "none" }
}

fn main() {
	let v = with policy.Retry(3) {
		try flaky()
	} catch err {
		say.Line("gave up:", err)
		0
	}
	let id = with policy.Bind(requestID, "r-42") {
		current()
	} catch _ {
		""
	}
	say.Line(v, id, current())
}
```

---

## 11. Concurrency

There are no threads in user code and no shared mutable state.

- **Globals are per core.** Each core thread has its own copy of every global,
  initialized on that core. Two cores never see each other's globals, so a 100 MB table in
  a plain global takes 100 MB on every core.
- **`shared let`** (#344) is the exception for data that every core only reads: it is
  evaluated once, on core 0, before the cores start, and lives in memory every core reads,
  so the table above costs 100 MB for any number of cores. `shared let table = build()`
  holds numbers, `bool`, `str`, slices, maps, structs, enums and optionals of them (E604
  for a function, `dyn` value or fault). It is immutable afterwards: assigning it, storing
  into its elements, fields or entries, `append`, `delete` and `copy` into it, and passing
  it as a `mut` argument are compile errors (E603). The check follows the name it is
  written with: a local alias (`let ys = table`) is not tracked, so never change the
  elements of one (a slice, map or struct taken from a `shared let` is the shared data, not
  a copy; `copy` it into a new slice first). `shared mut` stays library-only (E601).
- **`atomic`** has `atomic.Int` and `atomic.Bool`, counters and flags that every core may
  change: `shared let hits = atomic.NewInt(0)`, then `hits.Add(1)`, `Load`, `Store`,
  `Swap` and `CompareSwap` from any core. The operations are indivisible and sequentially
  consistent across the process. Make them in a `shared let`: one made in a handler or a
  per-core global lives in one core's memory.
- `hearth.Run(n, f)` runs `f(core)` on n core threads (the calling thread is core 0) and
  returns when all have returned. `hearth.Cores()` is the number of CPUs the process may
  use (on Linux it respects the container's CPU limit and affinity), `hearth.ID()` the
  current core.
- `relay.Send(core, msg)` copies a `str` message into another core's inbox (a lock-free
  queue); `relay.Recv()` blocks for the next one, `relay.TryRecv()` polls,
  `relay.Broadcast(msg)` sends to every other core. Encode structs with `argo.Put` /
  `argo.Get`.
- `anvil` runs one HTTP event loop per core; a connection stays on one core. A `Router`
  built in `main` is compiled once by `r.Serve` into a table every core reads. Each
  request runs in its own task: a call that waits lets the core serve others.
  `anvil.OnRelay(h)` and `anvil.OnTick(ms, h)` run handlers on server cores between
  requests.

### Tasks: `scope`, `spawn`, `parallel`

A task is a function running on the current core that waits without blocking it. Tasks
are started inside a `scope` block, which ends only when all of them have:

```tin
import "say"
import "tide"

fn fetch(i i64) !str {
	try tide.Wait((4 - i) * 10ms)
	return "page{i}"
}

fn fetchAll(n i64) ![]str {
	let pages = make([]str, n)
	scope s {
		for i in 0..n {
			let k = i
			s.spawn(fn() ! {
				pages[k] = try fetch(k)
			})
		}
	}
	return pages
}

fn both() !str {
	let (a, b) = try parallel {
		fetch(1)
		fetch(2)
	}
	return a + b
}

fn main() {
	let pages = fetchAll(4) catch _ { []str{} }
	let ab = both() catch _ { "" }
	say.Line(pages, ab)
}
```

- `scope s { }` names its scope. `s.spawn(fn() ! { ... })` starts a child task;
  `s.spawn(fn() !T { ... })` one with a value. The scope's end waits for every child. The
  first child fault cancels the scope (and so its other children) and is the scope's
  fault. Leaving the scope body early, by `return` or a `try`'s fault, cancels and joins
  the children still running.
- `let t = s.spawn(f)` is a handle: `try t.wait()` waits for it (and gives its value),
  `t.cancel()` cancels it; a child cancelled through its handle does not fail the scope.
- `s.cancel(reason)` cancels the whole scope: every wait inside it fails with
  `canceled: reason` (`fault.Canceled`), which is the scope's fault unless a child failed
  first. `s.yield()` lets the core's other ready tasks run before the caller goes on.
- Children share their parent's request memory and may store into what they capture.
  Each spawn captures its own copy of the loop's variables.
- A handle and its scope cannot outlive the scope block: they live only in local
  variables and parameters, never in a global, a field, a result or a `dyn` value.
- `parallel { a \n b }` is a scope with one child per line; its value is the tuple of the
  values.

### `select`, lanes, `detach`

<!-- tin-prelude
import "lane"
import "say"
-->
```tin body
mut jobs = lane.New[str](8)
try jobs.Send("build")
select {
	let job = jobs.Recv() => say.Line("got", job)
	after(5s) => say.Line("timeout")
	canceled() => return
}
```

- `select` waits for the first of its arms: a lane receive or send, a task handle's
  `wait()`, `after(d)`, or `canceled()` (the enclosing boundary was cancelled). `let x =
  wait =>` binds the value. Ties go to the first arm in source order. A cancelled
  boundary with no `canceled()` arm ends the select with its fault.
- `lane.New[T](n)` is a bounded queue between the tasks of one core: `try l.Send(v)` and
  `let v = try l.Recv()` wait while it is full or empty.
- `detach { ... }` starts a task that outlives the request: it has its own pool, runs when
  the event loop turns, logs its fault instead of passing it on, and is cancelled by the
  drain. What it captures must already be long-lived: read request values only inside
  `keep()` (`detach { flush(keep(event)) }`), or keep them first.

### `use`, `on`, `once`

<!-- tin-prelude
import "say"

type Conn struct {
	name str
}

fn (c Conn) Close() ! {
	say.Line("close", c.name)
}

fn connect(name str) !Conn {
	return Conn{name: name}
}
-->
```tin
use db = connect("main")            // per core: opened with the globals, closed at core stop

on app.start {
	say.Line("starting with", db.name)
}

on app.stop {
	say.Line("stopped")
}

fn migrate() ! {
	use tx = connect("tx")          // closed when the function returns
	say.Line("migrating with", tx.name)
}

fn main() {
	once {
		say.Line("first time this core gets here")
	}
	migrate() catch err {
		say.Line(err)
	}
}
```

- A package-level `use name = e` is a per-core global opened with the core's other globals
  (on core 0 and on every core `hearth.Run` starts) and closed with `name.Close()` when the
  core stops, last opened first. A fault there ends startup with status 1.
- A function-level `use name = e` is `let name = try e` plus a deferred `name.Close()`; a
  fault from `Close` is joined after the function's own fault.
- `on EVENT { }` handlers run in declaration order: `app.start` (before `main`, once),
  `core.start` and `core.stop` (on every core), `app.stop` (after `main` returns),
  `server.overload` and `server.recovered` (anvil's admission policy). A fault in a start
  handler ends startup with status 1.
- `once { }` runs its block the first time each core reaches it.

The runtime side of all of this (boundaries, cancellation, the drain) is in
[RUNTIME.md](RUNTIME.md).

---

## 12. Memory and regions

Tin has no garbage collector. Each core has two kinds of memory:

- **the request pool**: every allocation a request (or a plain program's `main`) makes is
  a bump-pointer allocation from it; a server wipes the pool after each response, so
  serving costs no frees and no collection pauses;
- **the ingot heap**: long-lived memory for globals and everything they hold, a
  size-class allocator. Global initializers allocate here.

**Rule: request memory must never be reachable from long-lived memory.** Storing a value
that may point into the request pool into a global, or into anything reachable from a
global, is a compile error unless the value goes through `keep(x)`, which deep-copies
`x` into the ingot heap and returns the copy:

<!-- tin-prelude
type User struct {
	name str
}
-->
```tin
mut cache map[str]User = map[str]User{}
mut recent []str = []str{}

fn remember(path str, u User) {
	cache[keep(path)] = keep(u)          // key and value copied into long-lived memory
	recent = append(recent, keep(path))
}
```

Without `keep`, the compiler reports: `request memory stored into global 'recent',
which outlives the request: wrap the value in keep()` (or `... into long-lived memory
(it may be reachable from a global)`).

What the checker tracks:
- every value's possible origins: a fresh allocation, long-lived memory, an unknown
  source, or one of the function's parameters;
- stores through fields, slice elements, map entries, `append`, `copy`, and assignments
  to globals;
- what request-owned containers hold: a fresh slice, map or struct given a global's
  object (or a parameter's) hands it back as long-lived (or as that parameter), so
  `let xs = []Box{gbox}` followed by `xs[0].items = append(xs[0].items, q)` needs
  `keep(q)` (it changes `gbox`), and `fn f(b Box) { let xs = []Box{b}; ... }` storing
  into `xs[0]` needs `b mut`;
- function summaries: which `mut` parameters a function stores request memory into (and
  where inside them), what its containers hold, and where its results come from
  (iterated to a fixed point over the whole program). A helper that stores its
  argument into a global makes its callers `keep`; passing a global to a function that
  stores request memory into that parameter is an error at the call (`put stores request
  memory into its mut parameter 'b', but this argument may be long-lived: keep() the
  stored values inside put`; for a standard-library function, which the caller cannot
  change, `... pass request memory (a local) instead`, as for an `anvil.Router` held in a
  global and changed in `main`);
- `keep` results, globals and constants are long-lived; literals are static.

Plain programs (no server) never reset their pool: memory is released when the program
exits. Tasks of a scope share their parent's pool; a `detach` task has its own.

**Arenas** (edition 1, #236). `arena { body }` runs its body in a sub-region of its own: a
fresh pool, dropped when the block ends. The block's value (its last expression) is copied
into the enclosing region, so it is all that leaves; a batch loop whose steps run in arenas
keeps a flat footprint however many steps it takes, outside a request as well as inside one.

<!-- tin-prelude
let paths = []str{"a.txt", "b.txt"}
let path = "c.txt"
mut total = 0
type Doc struct {
	names []str
}
fn load(path str) str { return path }
fn countWords(s str) i64 { return len(s) }
fn parse(text str) !Doc { return Doc{names: []str{text}} }
-->
```tin body
for path in paths {
	total += arena {                    // each file's temporaries are freed after its step
		countWords(load(path))
	}
}
let names = try arena {                 // a body that can fail is a !T: try or catch it
	let text = try quarry.ReadFile(path)
	let doc = try parse(text)
	doc.names                           // copied out; doc is freed with the arena
}
```

- A body that cannot fail has the type of its value (none for a statement block); one whose
  `try` or `fail` can leave it is a `!T`, used with `try` or `catch` like the other boundary
  blocks. `return` cannot leave it. A panic passes through it (the arena is freed on the way)
  to the nearest `guard`.
- The value is deep-copied, like `keep`, but into the enclosing region. A recursive type, or
  one holding a `func` or `dyn` value, cannot be the value (E316 ARENA_VALUE).
- **Nothing else made in the arena may leave it** (E315 ARENA_ESCAPE): storing it into a
  variable from outside the block, into a field, element or map entry of an object from
  outside, or through a call's `mut` argument. Appending to or inserting into a slice or
  map from outside is rejected whatever the value, since its new array or table would be
  allocated in the arena: grow it after the block, from the block's value. Values from
  outside may be read, and stored into objects from outside. `keep(x)` inside an arena still
  copies into long-lived memory.
- Scope children inside an arena allocate in it and end with their scope, inside the block.
  The arena's memory counts toward an enclosing `limit memory`, and is given back when the
  arena ends.

---

## 13. Generics

```tin
import "constraints"
import "say"

fn maxOf[T i64 | f64 | str](a T, b T) T {
	if a > b {
		return a
	}
	return b
}

fn mapAll[T constraints.Any, U constraints.Any](xs []T, f fn(T) U) []U {
	mut out = make([]U, 0, len(xs))
	for x in xs {
		out = append(out, f(x))
	}
	return out
}

type Stack[T constraints.Any] struct {
	items []T
}

fn (s mut Stack[T]) push(x T) {
	s.items = append(s.items, x)
}

fn (s mut Stack[T]) pop() !T {
	let n = len(s.items)
	if n == 0 {
		fail "empty stack"               // a fault comes with T's zero value
	}
	let x = s.items[n - 1]
	s.items = s.items[:n - 1]
	return x
}

type Pair[A constraints.Any, B constraints.Any] struct {
	first  A
	second B
}

fn main() {
	let s = Stack[i64]{items: []i64{}}
	s.push(4)
	let top = s.pop() catch _ { -1 }
	let p = Pair[str, i64]{first: "k", second: 7}
	say.Line(maxOf(3, 9), maxOf[f64](1, 2.5), top, p.first)
	say.Line(mapAll([]i64{1, 2}, fn(x i64) str { return "<{x}>" }))
}
```

- Type parameters go in square brackets after the name: an imported shape such as
  `[T constraints.Any]` or `[K constraints.Comparable]`, a union `[T i64 | f64 | str]`
  (the type argument must be one of them), or another shape name (`[R Reader]`,
  section 3). Ordering constraints use `[T sift.Ordered]`.
- Type arguments are inferred from the call's arguments (untyped constants default to
  `i64`/`f64`), or given explicitly: `f[T](...)`, `pkg.F[T](...)`.
- Every instantiation is compiled separately and fully specialized: there is no boxing
  and no runtime dispatch. Methods of a generic type are instantiated with it.
- A generic function gets T's zero value from a fault (`fail` gives zero values for every
  result) or from a `make([]T, 1)` element; edition 1 has no local declaration without an
  initializer yet.
- Inside a generic function, operations are checked per instantiation: `a > b` with
  `T = bool` is reported where `maxOf[bool]` is instantiated.

---

## 14. Builtins

| builtin | meaning |
|---|---|
| `len(x)` | length of a str (bytes), slice or map |
| `cap(s)` | capacity of a slice |
| `append(s, v...)` | add elements (or `append(s, t...)` a slice, or `append(b, text...)` a str to a `[]u8`) |
| `make([]T, n[, c])`, `make(map[K]V)` | new slice or map |
| `new(T)` | `T{}` |
| `copy(dst, src)` | copy min(len) elements (or bytes of a str into a `[]u8`); returns the count |
| `delete(m, k)` | remove a map entry |
| `min(a, b)`, `max(a, b)` | of two numbers of the same type |
| `panic(msg)` | stop the program (or the enclosing `guard`) |
| `fail(msg)` | make a fault |
| `fault(msg)` | declare a sentinel: only as `let ErrX = fault("msg")` at package level |
| `keep(x)` | deep copy into long-lived memory (section 12) |
| `bound(x)` | check a value against a bounded type (section 17) |
| `reveal(x)` | the plain value of a secret (section 18) |
| `print(...)`, `println(...)` | same as `say.Text` / `say.Line` |

Compiler-generated package functions: `say.*` (section 16), `argo.Put`, `argo.Get`, `argo.GetStrict`
(section 17). Inside a `select`: `after(d)` and `canceled()`.

---

## 15. String interpolation

A `"..."` literal can hold values in braces; it becomes a `str` built by the same
formatting code as `say.Fmt`, decided at compile time from each value's static type:

<!-- tin-prelude
type User struct {
	name str
}
-->
```tin
import "say"

fn report(u User, items []str, price f64, id i64, name str, n i64) ! {
	let msg = "user {u.name} has {len(items)} items"
	let row = "{price:.2} {id:x} [{name:-12}] [{n:05}]"
	say.Line(msg, row)
	say.Line(`raw strings keep {braces}`)    // backquotes: no interpolation
	say.Line("literal {{braces}} and 100%")  // {{ and }} are braces; % needs no escaping
	if n < 0 {
		fail "count {n} out of range"
	}
}
```

- Anything inside `{...}` is an expression, with no `"` inside (bind the value first:
  `"hits={m["hits"]}"` is an error).
- A spec after the last top-level `:` uses printf flags, width, precision and verb:
  `{x:5}`, `{x:-8}`, `{x:05}`, `{x:x}`, `{x:q}`, `{x:.3e}`. Without a verb the value is
  printed as `%v`, and a precision on a float means decimal places (`{pi:.2}` is `3.14`).
- A lone `}` is an error (write `}}`), and so is an unclosed `{`.
- Text with braces of its own, like an anvil route pattern, is a raw string:
  ``r.Get(`/users/{id}`, user)``. In `"/users/{id}"` the `{id}` would be a value; when no
  `id` is in scope the compiler says so (`undefined: id (in a string, {id} is a value:
  ...)`).

### Queries

Where a parameter (or variable) has the builtin type `query`, a literal does not become a
`str`: it becomes a `query`, the text pieces around each `{value}` and the values
themselves, kept apart. Clients for databases and caches take a `query`, so a value can
never change the shape of a command:

<!-- tin-prelude
import "redis"
-->
```tin body
let c = redis.Open(redis.Options{Addr: "127.0.0.1:6379"})
let id = 42
let body = "{\"name\":\"ana\"}"
try c.Do("SET user:{id} {body}")     // SET, user:42 and body are three arguments
```

- Passing a `str` where a `query` is expected is a compile error: a query takes a string
  literal.
- `query` is `struct { Parts []str; Args []qarg }`, with `len(Parts) == len(Args) + 1`.
- `qarg` is an enum: `Int(i64)`, `Float(f64)`, `Str(str)`, `Bool(bool)`, `Bytes([]u8)`.
  Integers of any width become `Int`, `f32` becomes `Float`; other types are a compile
  error, and so is a format spec (`{x:5}`): values are sent as they are.
- A plain literal without values is a query with one part and no values.

---

## 16. Printing and formatting: say

`say` is built into the compiler: each argument is formatted by its static type, without
interfaces or reflection.

<!-- tin-prelude
type Log struct {
	lines []str
}

fn (l mut Log) Write(s str) {
	l.lines = append(l.lines, s)
}
-->
```tin body
let x = 3
let ok = true
let f = 2.5
let s = "go"
let n = 255
say.Line("x =", x, ok)                // space-separated, newline
say.Text("no", "spaces")              // concatenated, no newline
say.Out("%5.2f|%-4s|%x\n", f, s, n)   // printf to stdout
let t = say.Fmt("%d items", n)        // printf to a str
let u = say.Str(x)                    // one value as a str
let err = say.Fault("bad %q", s)      // printf to a fault
mut w = Log{}
say.To(w, "%d\n", n)                  // printf to w (any value with a Write(str) method)
say.LineTo(w, t, u, err)              // Line to w
```

Verbs: `%v` (default format), `%d` (integer), `%s` (string), `%q` (quoted string or
character), `%x %X` (hex, also of strings), `%o` (octal), `%b` (binary), `%c`
(character), `%U` (U+0041), `%e %E` (exponent), `%f` (fixed), `%g %G` (shortest), `%t`
(bool), `%p` (address), `%%`. Flags: width (`%5d`), precision (`%.3f`), `-` (left
align), `+` (sign), `0` (zero pad), `#` (alternate), space.

Default formats: integers in decimal; floats in the shortest form that reads back
exactly, with an exponent below 1e-4 or from 1e21 (Go's `%v`); `true`/`false`; strings as
is; slices as `[a b c]` (of slices, maps and faults too: `[[1 2] [3]]`); maps as `map[k:v ...]` with sorted keys; structs as `{a b}`, with
nested structs, enums (by name) and slices of structs printed in full; `NaN`, `+Inf` and
`-Inf` for the non-finite floats under every verb; nil optionals and faults as `<nil>`. An
optional field of a struct prints as an address, as a pointer field does in Go, so that a
structure that points back at itself prints and ends; an optional number prints as the number
or `<nil>`.

`%+v` is not `%v` with a sign: it prints no `+` on numbers and gives structs their field
names (`{a:1 b:2.5}`). `%+d`, `%+g`, `%+f` and `%+e` do print the sign.

Output to stdout is buffered (64 KiB, or per line on a terminal) and flushed at exit.

---

## 17. JSON: argo

```tin
import "argo"
import "say"

type User struct {
	@json("id") id i64
	name  str
	email str
	tags  []str
	boss  ?User
}

fn main() {
	mut b = make([]u8, 0, 1024)
	argo.Put(mut b, User{id: 7, name: "ana", email: "a@x", tags: []str{"admin"}})
	say.Line(str(b))   // {"id":7,"name":"ana","email":"a@x","tags":["admin"],"boss":null}

	mut u = User{id: 0}
	argo.Get(str(b), mut u) catch err {   // fills u; a fault for bad JSON or types
		say.Line(err)
	}
	mut xs = []User{}
	argo.Get(`[{"id":1}]`, mut xs) catch err {   // appends decoded elements
		say.Line(err)
	}
	say.Line(u.name, len(xs))
}
```

- The compiler generates an encoder and a decoder for each type. JSON member names are
  the struct's field names, in declaration order, or the name an `@json("...")` attribute
  gives.
- `argo.Put(mut b, v)` appends to a `[]u8`; any type: integers, floats (shortest exact
  form, exponent below 1e-6 or from 1e21, NaN/Inf as `null`), bools, strs (escaped),
  slices, maps with str or integer keys, structs, enums, optionals (`null` when nil),
  faults (their message or `null`).
- `argo.Get(text, mut v)` fills a struct, slice (appending) or map (adding entries);
  nested struct fields are filled in place, `?T` fields accept `null`, unknown members are
  skipped, numbers follow the JSON grammar and must fit their type (`007`, `1.`, `700`
  into a `u8` and `1e400` into an `f64` are faults), and trailing garbage is a fault, as
  are arrays and objects nested more than 512 deep (each level takes stack, and a request
  handler's stack is 256 KiB). Error messages name the offset: `argo: expected an integer
  in [0, 65535] at offset 8, found "7"`.
- **A fault leaves the target as it was** (#354). `argo.Get` checks the text against the
  type first, with a pass that stores nothing, and fills the target only when that passes,
  so `[1, 2, 3,]` into a slice that held `[9]` fails and leaves `[9]`. A slice is instead
  filled in place and cut back to its old length on a fault (no second pass). Text that
  passes cannot fail while filling, except that a bound on a map that already holds
  entries counts them.
- `argo.GetStrict(text, mut v)` is `argo.Get` for an API boundary: an **unknown member**
  and a **duplicate member** (`{"n":1,"n":2}`, a way to smuggle a parameter past a check
  that reads the first value) are faults naming the key and its offset. `argo.Get` skips
  unknown members and the last duplicate wins, as in Go. Both reject **invalid UTF-8** in
  a string and an **unpaired surrogate** escape (`"\ud800"`), naming the offset, where Go
  silently substitutes U+FFFD. Bounds (`str max 100`) are checked by both.
- `argo.Str(b, s)` and `argo.Raw(b, json)` write pieces by hand.
- **Bounded values** (#240): `name str max 100`, `tags []str max 20`,
  `map[str]i64 max 50` bound a length. A bounded value is assignable to its unbounded type
  (and to a looser bound), never the reverse: an unbounded value becomes bounded only
  through `bound(x)`, whose type is its destination's (`let n str max 100 = try
  bound(raw)`, an assignment or a `return`) and which fails with `fault.LimitExceeded`
  when `x` is longer. A str literal within the bound fits. `append` and `+` give the
  unbounded type. `argo.Get` enforces bounds while reading: a str stops at its bound and a
  slice or map before the element past it, failing with `fault.LimitExceeded` without
  reading the rest, and `try bound(q.Body())` checks an anvil request body's length before
  copying it. `max` after `[]T` or `map[K]V` bounds the slice or map; for a slice of
  bounded strs, name the element type (`type Tag str max 20`, then `[]Tag`).

```tin
import "argo"
import "say"

type Tag str max 20

type Short str max 8

type Signup struct {
	name str max 100
	tags []Tag max 5
}

fn shortName(raw str) !Short {
	let n Short = try bound(raw)
	return n
}

fn main() {
	mut s = Signup{name: "ana"}
	argo.Get(`{"name":"ana","tags":["a","b"]}`, mut s) catch err {
		say.Line(err)
	}
	let n = shortName("a very long name") catch err {
		say.Line(err)    // fault.LimitExceeded
		""
	}
	say.Line(s.name, len(s.tags), n)
}
```

---

## 18. Safety checks

- **Bounds**: every slice and string index is checked; slicing beyond the length panics.
  The compiler removes a check where it can prove the index is in range: `for x in xs`,
  `for i in 0..len(xs)` (and loops whose bound is `len(xs)` held in an unchanged
  variable), and `if i < len(xs)` with a non-negative i.
- **Nil**: str, slice, map and struct values are never nil. Optionals must be checked
  before use (section 9). Missing map keys read as zero values; `try` returns real zero
  values.
- **Integer overflow** panics (#362): `+`, `-`, `*`, negation and signed `/` whose result
  does not fit the type, a shift count outside 0 .. width-1, and a float to integer
  conversion out of range or of NaN (`panic: integer overflow: +`, `shift count out of
  range`, `float to integer conversion out of range`, with a backtrace). Integer conversions
  truncate on purpose (`u8(x)`). Wrapping is explicit: `+%`, `-%`, `*%` and `@wrap`
  functions (section 6). Constant arithmetic that overflows is a compile error (E223, E224).
  The runtime (`toolchain/runtime/`) and the compiler keep the machine's arithmetic. Division by
  zero panics.
- **Uninitialized memory** cannot be read: every variable, field and element starts as a
  zero value or is required to be set.
- **Memory lifetime**: the region check (section 12).
- **Data races**: impossible by construction (section 11).
- **Stack overflow**: deep recursion in a request handler, a spawned child, a detached task,
  a tick, a relay handler or a `guard` block is a panic of that one (#342): `panic: stack
  overflow (...)` and a backtrace go to stderr, its deferred calls and cleanups run, a request
  gets 500, a `guard`'s fault holds the message, and the core goes on. `main` and the `on`
  handlers outside a task still end the process with `panic: segmentation fault ...` on stderr
  and status 2, after flushing the output printed before it. Threads have 8 MiB stacks; a task
  runs on a 256 KiB stack, or `TIN_TASK_STACK` bytes (64 KiB to 256 MiB): a lazily committed
  mapping, so a bigger one costs address space, and memory only for tasks that recurse deeply.
- **Secrets** (design_semantics §9): `secret T` qualifies a number, bool, str, slice or
  map (`token secret str` in a struct, `fn sign(key secret []u8)`). The compiler tracks it
  and the runtime never sees it: a secret computes exactly like its plain type. A plain
  value may become secret; a secret becomes plain only through `reveal(x)`. Operators,
  interpolation, indexing, slicing, conversions, `for ... in` and map reads on a secret
  give secrets; `len` and `cap` do not. These reject a secret (or a value holding one,
  such as a struct with a secret field) at compile time: `say` formatting, `panic`, fault
  messages (`fail`, `wrap`, `fault`, `say.Fault`), `argo.Put`, `copy`/`append` into a
  plain slice, and every parameter, variable or result not declared `secret` (so logging
  and any library function that did not opt in). `==`, `!=`, the orderings and
  `min`/`max` on secrets are errors: compare with `seal.Equal`, which takes constant time.
  A secret map key is an error. A struct is made secret field by field, not as a whole.
  A secret may be written into a query literal (`cache.Do("GET {token}")`): the value is
  sent as itself, and the query's `Hidden` bits mark it, so a replay capsule holds its keyed
  handle, never its text (#241).
  `tin audit secrets FILE.tin` lists every `reveal`, every secret passed to a library
  parameter declared secret and every secret sent in a query, so review knows where secrets
  leave.

```tin
import "seal"
import "say"

type Account struct {
	name  str
	token secret str
}

fn check(a Account, given secret str) bool {
	return seal.Equal(a.token, given)
}

fn main() {
	let a = Account{name: "ana", token: "s3cret"}
	say.Line(a.name, check(a, "guess"), len(reveal(a.token)))
}
```

---

## 19. Attributes

An attribute is `@name(arguments)` before what it annotates. Attributes are checked at
compile time; they add no runtime metadata and do not change layouts. Invalid arguments are
compile errors (E042); unknown attribute names should be too, but edition 1 does not reject
them yet.

| attribute | on | meaning |
|---|---|---|
| `@json("name")` | a struct field | the JSON member name `argo` writes and reads |
| `@nopoll` | a function | no safepoint polls in its loops, for short hot kernels ([TOOLING.md](TOOLING.md)) |
| `@wrap` | a function | the machine's integer arithmetic: `+ - *` and negation wrap, shift counts modulo 64 (section 6); for hashes, ciphers and constant-time field arithmetic |

```tin
type User struct {
	@json("id") id i64
	@json("display_name") name str
}

@nopoll fn sum(xs []i64) i64 {
	mut t i64 = 0
	for x in xs {
		t += x
	}
	return t
}

// splitmix64's output step computes modulo 2^64.
@wrap fn mix(z0 u64) u64 {
	mut z = (z0 ^ (z0 >> 30)) * 0xbf58476d1ce4e5b9
	z = (z ^ (z >> 27)) * 0x94d049bb133111eb
	return z ^ (z >> 31)
}
```

---

## 20. Standard-library-only features

Files under the library (`toolchain/std/`, `packages/`, `toolchain/runtime/`) are trusted and may use operations user code cannot. So may a vendored
package whose `tin.mod` declares `caps unsafe` (toolchain/docs/PACKAGES.md); the packages that call it
then need `unsafe` too.

- `cast(T, x)` between `i64` and reference types (a str is a pointer to
  `[length word][bytes][NUL]`; a slice to a header `[len, cap, data, region]`);
- word indexing on raw pointers (`p[i]` reads the 8-byte word at `p + 8*i` when `p` is an
  `i64`), `load8(p)`, `store8(p, v)`, `__ld(p, log2size)`, `__st(p, v, log2size)`;
- atomics: `__atomic_add`, `__atomic_swap`, `__atomic_cas`, `__atomic_load`,
  `__atomic_store`; `__yield` (a spin-wait hint);
- `__ctx()` / `__set_ctx(p)` (the core context register), `__fp()` (the frame pointer),
  `__empty()` (the static empty slice header), `&x` (address of a local or global);
- declarations of system library functions, and calls to them (variadic C functions need
  `...` in the declaration); C int results are valid in the low 32 bits: convert with
  `i64(i32(x))`;
- `shared let` (one process-wide value, not per core) for the runtime's own state;
- `secret` parameter types (`fn Equal(a secret str, b secret str) bool`): callers may
  pass secrets, and inside the function the parameter is its plain type. The library is
  responsible for not leaking the value (section 18);
- the runtime's `rt_` functions (see RUNTIME.md).

User code that needs these goes through a library package.

---

## 21. Grammar

EBNF: `{x}` repeats, `[x]` is optional, `|` separates alternatives, `"x"` is a token.
`NL` is the end of a line (a statement ends there unless the line ends in an operator,
`,`, `(`, `[` or `{`, or a bracket is still open). Precedence is the table of section 6.

```ebnf
File        = "package" Name NL { Import NL } { TopDecl NL } .
Import      = "import" String .
TopDecl     = ConstDecl | GlobalDecl | TypeDecl | ShapeDecl | FnDecl | UseDecl | OnDecl .

ConstDecl   = "const" Name [ Type ] "=" Expr .
GlobalDecl  = [ "shared" ] ( "let" | "mut" ) Name [ Type ] [ "=" Expr ] .
UseDecl     = "use" Name "=" Expr .
OnDecl      = "on" Name "." Name Block .
TypeDecl    = "type" Name [ TypeParams ] ( "=" Type | Type ) .
TypeParams  = "[" TypeParam { "," TypeParam } "]" .
TypeParam   = Name [ Constraint ] .
Constraint  = Type { "|" Type } .
ShapeDecl   = "shape" Name [ TypeParams ] ( "{" { ShapeMember NL } "}" | "=" Constraint ) .
ShapeMember = Name [ TypeArgs ] | Name Params [ Result ] .
FnDecl      = { Attribute } "fn" [ Receiver ] Name [ TypeParams ] Params [ Result ] Block .
Receiver    = "(" Name [ "mut" ] Type ")" .
Params      = "(" [ Param { "," Param } ] ")" .
Param       = Name { "," Name } [ "mut" ] [ "..." ] Type .
Result      = "!" [ Type | "(" Type { "," Type } ")" ] | Type | "(" Type { "," Type } ")" .
Attribute   = "@" Name [ "(" [ Expr { "," Expr } ] ")" ] .

Type        = TypeName [ TypeArgs ] | "[" "]" Type | "[" Expr "]" Type
            | "map" "[" Type "]" Type | "?" Type | "dyn" TypeName [ TypeArgs ]
            | "secret" Type | Type "max" Expr | "(" Type { "," Type } ")"
            | "fn" "(" [ ParamType { "," ParamType } ] ")" [ Result ]
            | StructType | EnumType .
ParamType   = [ "mut" ] Type .
TypeName    = Name [ "." Name ] .
TypeArgs    = "[" Type { "," Type } "]" .
StructType  = "struct" "{" { { Attribute } Name { "," Name } Type NL } "}" .
EnumType    = "enum" "{" Variant { ( "," | NL ) Variant } "}" .
Variant     = Name [ "(" Type { "," Type } ")" ] .

Block       = "{" { Stmt NL } "}" .
Stmt        = LetStmt | Assign | ExprStmt | If | For | Match | Return | Break | Continue
            | Defer | Fail | Block | Boundary | Select | Scope | Detach | Once | UseDecl .
LetStmt     = ( "let" | "mut" ) ( Name [ Type ] | "(" Name { "," Name } ")" ) "=" Expr .
Assign      = Expr { "," Expr } AssignOp Expr { "," Expr } .
AssignOp    = "=" | "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>="
            | "+%=" | "-%=" | "*%=" .
ExprStmt    = Expr .
If          = "if" ( Expr | "let" Name "=" Expr ) Block [ "else" ( If | Block ) ] .
For         = [ Name ":" ] "for" [ Name [ "," Name ] "in" Iterable | Expr ] Block .
Iterable    = Expr | Expr ".." Expr | "(" Expr ".." Expr ")" "." "step" "(" Expr ")" .
Match       = "match" Expr "{" { Arm NL } "}" .
Arm         = Pattern { "," Pattern } [ "if" Expr ] "=>" ( Expr | Block | Return
            | Break | Continue | Fail | Assign ) .
Pattern     = Literal | Literal ".." Literal | "_" | Name
            | TypeName [ "(" Pattern { "," Pattern } ")" ] .
Return      = "return" [ Expr { "," Expr } ] .
Break       = "break" [ Name ] .
Continue    = "continue" [ Name ] .
Defer       = "defer" Call .
Fail        = "fail" Expr .
Boundary    = ( "within" Expr | "limit" Name Expr { "," Name Expr } | "guard" | "arena"
            | "parallel" | "with" Expr ) Block .
Select      = "select" "{" { [ "let" Name "=" ] Expr "=>" ( Expr | Block | Return ) NL } "}" .
Scope       = "scope" Name Block .
Detach      = "detach" Block .
Once        = "once" Block .

Expr        = Unary { BinaryOp Unary } [ "wrap" Expr ] [ "catch" ( Name | "_" ) Block ] .
BinaryOp    = "||" | "&&" | "==" | "!=" | "<" | "<=" | ">" | ">=" | "+" | "-" | "|" | "^"
            | "*" | "/" | "%" | "<<" | ">>" | "&" | "+%" | "-%" | "*%" .
Unary       = ( "-" | "!" | "~" | "^" | "try" ) Unary | Postfix .
Postfix     = Primary { "." Name | "[" Expr "]" | "[" [ Expr ] ":" [ Expr ] "]" | TypeArgs
            | Args | "??" Unary | Composite } .
Args        = "(" [ Arg { "," Arg } [ "..." ] ] ")" .
Arg         = [ "mut" ] Expr .
Composite   = "{" [ Element { "," Element } [ "," ] ] "}" .
Element     = [ Name ":" | Expr ":" ] ( Expr | Composite ) .
Primary     = Literal | Name | "(" Expr ")" | FnLit | Boundary | Match
            | ( "[" "]" Type | "[" Expr "]" Type | "map" "[" Type "]" Type ) .
FnLit       = "fn" Params [ Result ] Block .
Literal     = Int | Float | Unit | Char | String | RawString | "true" | "false" | "nil" .
```

---

## 22. From edition 0

Edition 0 was Tin's Go-like syntax (see `design/design_syntax.md`). `tin fix -edition 1 FILES`
rewrites it; the compiler names the edition 1 form for each one it meets (E090
OLD_SYNTAX, E091 ONE_PER_DECLARATION in [ERRORS.md](ERRORS.md)).

<!-- docs-check: old-syntax begin -->

| edition 0 | edition 1 |
|---|---|
| `func f(x i64) i64 { }` | `fn f(x i64) i64 { }` |
| `x := 1`, `var x = 1` | `let x = 1` (never reassigned) or `mut x = 1` |
| `var x i64` (a local) | `mut x i64 = 0` |
| `a, b := f()` | `let (a, b) = f()` |
| `var g = 1` (a global) | `let g = 1` or `mut g = 1` |
| `const ( A = iota; B )` | one `const` per name, or an `enum` |
| `import ( "a"; "b" )`, `import u "util"` | one `import "a"` per line; no aliases |
| `switch x { case 1, 2: ... default: ... }` | `match x { 1, 2 => ... _ => ... }` |
| `switch { case x > 0: }` | `match true { true if x > 0 => ... _ => ... }`, or `if` |
| `for i := 0; i < n; i++ { }` | `for i in 0..n { }` |
| `for i, x := range xs { }` | `for i, x in xs { }` |
| `for i := range 10 { }` | `for i in 0..10 { }` |
| `x++`, `x--` | `x += 1`, `x -= 1` |
| `if v := f(); v > 0 { }` | `let v = f()` on its own line, then `if v > 0 { }` |
| `Point{1, 2}` | `Point{x: 1, y: 2}` |
| `type Shape enum { Rect(w, h f64) }` | `type Shape enum { Rect(f64, f64) }` |
| `func(i64) i64` (a type), `func(x i64) { }` (a literal) | `fn(i64) i64`, `fn(x i64) { }` |
| `ID i64 @json("id")` | `@json("id") id i64` |
| `tide.Millisecond * 200` | `200ms` |
| `/* comment */` | `// comment` |
| `a; b` on one line | one statement per line |
| `extern func`, `shared var` (library only) | library declarations, `shared let` |

<!-- docs-check: old-syntax end -->

---

## 23. Differences from Go

<!-- docs-check: old-syntax begin -->

| Go | Tin |
|---|---|
| `int`, `byte`, `rune`, `float64`, `string` | `i64`, `u8`, `i32` (`rune`), `f64`, `str` |
| `func`, `:=`, `var` | `fn`, `let` (not reassigned), `mut` |
| `switch` | `match`, an expression with patterns, exhaustive over enums |
| three-clause `for`, `range` | `for x in xs`, `for i in 0..n` |
| implicit untyped-to-typed only, but `int` everywhere | sized types everywhere, explicit conversions |
| `error` interface | `fault` (a message, with chains and sentinels); `!T`, `fail`, `try`, `catch`, `wrap` |
| unchecked errors allowed | ignoring a fault is a compile error |
| nil maps, slices, pointers | never nil; `?T` for optional values |
| pointers, `&x`, `*p` | reference types (structs, slices, maps are references) |
| slices are values (header copied) | slices are references (header shared, `append` in place) |
| goroutines, channels, mutexes | one thread per core, per-core globals, `scope`/`spawn` tasks, `lane`, `select`, `relay` messages |
| `context.Context` | `within`, `limit`, cancellation through boundaries, `with policy.Bind` |
| package variables initialized in dependency order | declaration order; an initializer using a later global is a compile error |
| garbage collector | request pools + `keep` into a long-lived heap, checked at compile time |
| interfaces, reflection | shapes (`shape`, satisfied structurally; `dyn S` for explicit dynamic dispatch); generics (monomorphized); compiler-generated `say` and `argo` |
| struct tags | attributes (`@json("id")`) |
| closures capture variables | the same, with per-iteration loop variables; no `mut` parameter capture; a local closure cannot recurse |
| `defer` in loops, `recover` | defer outside loops only; `guard` blocks turn a panic into a fault |
| `fmt.Println` | `say.Line` (formatting by static type) |
| interfaces for sum types | `enum` with exhaustive `match` |
| exported = capitalized | the same rule, enforced for names, methods and fields |
| `f(&x)` to let a callee modify x | `f(mut x)` for a `mut` parameter |
| `time.Millisecond * 200` | `200ms` |
| `goto`, `fallthrough` | not available |
| integer arithmetic wraps; shift counts of any size; `int64(1e300)` is implementation-defined | `+ - *` panic on overflow, `+% -% *%` and `@wrap` wrap; shift counts below the width; float to integer panics out of range |

<!-- docs-check: old-syntax end -->
