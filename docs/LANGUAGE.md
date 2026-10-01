# The Tin language reference

Tin is a compiled, statically typed, Go-like language for servers and tools. It targets
macOS on Apple Silicon (darwin-arm64) and Linux on arm64 (linux-arm64), with Linux on
x86-64 (linux-amd64) in progress. It is designed to be written by AI: it trades human
convenience for speed and robustness, and the compiler rejects whole classes of bugs
instead of leaving them to tests:

- ignored errors (a fault must be handled);
- nil dereferences (references are never nil; optionals must be checked);
- request memory leaking into long-lived state (compile-time region check);
- shared mutable state between threads (globals are per core; no `go`);
- implicit numeric conversions (none exist);
- out-of-range indexing (always checked, the check removed only where proven safe).

This document is the reference. [STDLIB.md](STDLIB.md) lists the standard library,
[TOOLING.md](TOOLING.md) the commands, [RUNTIME.md](RUNTIME.md) and
[COMPILER.md](COMPILER.md) how it works inside.

Contents: 1 Programs and packages · 2 Lexical elements · 3 Types · 4 Constants ·
5 Declarations · 6 Expressions · 7 Statements · 8 Errors · 9 Optionals ·
10 Memory and regions · 11 Concurrency · 12 Generics · 13 Builtins · 14 say ·
15 argo · 16 Safety checks · 17 Standard-library-only features · 18 Grammar ·
19 Legacy syntax · 20 Differences from Go

---

## 1. Programs and packages

A program is one or more `.tin` files, each starting with a package clause; the program's
files say `package main` and one of them declares `func main()`.

```go
package main

import "say"

func main() {
	say.Line("hello, tin")
}
```

Run it with `tin hello.tin` (see [TOOLING.md](TOOLING.md)).

### Imports

```go
import "say"          // the standard library: lib/say ... lib/wire
import "./geom"       // relative to this file: ./geom.tin, or every .tin file in ./geom/
import "util"         // not in the standard library: <directory of the program>/util(.tin)
import u "util"       // with an alias
```

- A package is a file `name.tin` or a directory of `.tin` files. Directory files are read
  in sorted order; `*_test.tin` files are skipped.
- Every file of a package starts with the same `package name` clause.
- Platform-specific files: next to `name.tin`, the compiler also loads `name_darwin.tin`
  or `name_linux.tin` for the target OS, and `name_linux_arm64.tin` /
  `name_linux_amd64.tin` for the target CPU. In a directory package, files for other
  targets are skipped.
- The package name is the last element of the import path (`"net/http"` is `http`).
  Members are used as `pkg.Name`.
- **Exports** follow Go: a capitalized top-level name, method or struct field
  (`Serve`, `Out.Status`, `Resp.Body`) is visible to importers; a lower-case one
  (`parseInt`, `Conn.fd`) is private to its package, and using it from another package is
  a compile error. Code the compiler generates (JSON encoding, printing, `keep`) may read
  private fields.
- Imports must not form a cycle.

### Program start

Before `main` runs, every package's global initializers run (on every core: see
section 11), in declaration order within a file and file order within the program.
`main` returns nothing; the program exits with status 0 when it returns, 2 on a panic,
or with the code passed to `quarry.Exit`.

---

## 2. Lexical elements

- **Encoding**: source is UTF-8.
- **Comments**: `// to end of line` and `/* block */` (not nested).
- **Semicolons** are inserted at the end of a line whose last token is an identifier, a
  literal, `break`, `continue`, `return`, `)`, `]` or `}` (Go's rule). Write the opening
  brace of a block on the same line.
- **Identifiers**: letters, digits and `_`, not starting with a digit. `_` alone is the
  blank identifier.
- **Keywords**: `break case const continue default defer else extern fn for func go if
  import let map mut nil package range return struct switch true false try type var`
  (`fn`, `let`, `extern`, `while` belong to the legacy syntax, section 20; `go` is
  reserved and rejected).
- **Integer literals**: `42`, `0x2a`, `0o52`, `0b101010`, with `_` between digits
  (`1_000_000`). Values up to 2^64-1 are allowed; a literal above 2^63-1 only fits
  64-bit unsigned types (or keeps its bit pattern as an `i64`).
- **Float literals**: `3.14`, `1e-9`, `.5`, `6.02e23`.
- **Character literals**: `'a'`, `'\n'`, `'\x41'`, `'é'`, `'é'`: an untyped
  integer constant holding the code point.
- **String literals**: `"text"` with escapes `\n \t \r \\ \" \' \0 \a \b \f \v \xHH \ooo
  \uHHHH \UHHHHHHHH`, and raw strings in backquotes (no escapes, may span lines).

### Operators and punctuation

```
+  -  *  /  %  &  |  ^  <<  >>  &&  ||  !  ~
== != <  <= >  >=
=  := += -= *= /= %= &= |= ^= <<= >>=  ++  --
(  )  [  ]  {  }  ,  ;  .  :  ...  ?
```

---

## 3. Types

| type | size | notes |
|---|---|---|
| `i8 i16 i32 i64` | 1 2 4 8 | signed integers; arithmetic wraps |
| `u8 u16 u32 u64` | 1 2 4 8 | unsigned integers; arithmetic wraps |
| `f64` | 8 | IEEE-754 double |
| `bool` | 1 | `true`, `false` |
| `str` | ref | immutable bytes (UTF-8 by convention); never nil; zero value `""` |
| `[]T` | ref | slice: a reference to a header (length, capacity, data) |
| `[N]T` | ref | a `[]T` that starts with N zero elements (`[N][M]T` too) |
| `map[K]V` | ref | hash map; K is `str` or an integer type; never nil |
| `struct { ... }` | ref | a reference to an object; never nil |
| `?T` | ref | optional T: a T or `nil` (T a reference type) |
| `fault` | ref | an error; `nil` means no error |
| `func(A, B) (R, S)` | 8 | a function value: a top-level function or a function literal without captures |

There are no pointers in user code, no interfaces, no channels and no `byte`/`int`
aliases: use `u8` and `i64`.

### Reference semantics

Strings, slices, maps and structs are references. Assigning or passing one copies the
reference, not the contents:

```go
a := Point{X: 1}
b := a
b.X = 2            // a.X is 2 as well
xs := []i64{1}
ys := xs
ys = append(ys, 2) // xs sees the new element too: append grows the header in place
```

Use `keep(x)` (a deep copy into long-lived memory) or explicit copies (`copy`,
`ore.Clone`, a new literal) when independent values are needed.

### Slices

- `len(s)`, `cap(s)`; indexing `s[i]` (bounds checked); slicing `s[lo:hi]`,
  `s[lo:]`, `s[:hi]` shares the elements; `hi` may not exceed `len(s)`.
- `append(s, v1, v2...)` and `append(s, t...)` add elements, growing in place (the
  header is updated); always assign the result back: `s = append(s, v)`.
- `make([]T, n)` and `make([]T, n, capacity)`. Elements start as zero values: `""` for
  `str`, an empty slice for `[]T`. `make` with a non-zero length is rejected for struct,
  map and func elements (they have no zero value): use `make([]T, 0, n)` and append, or
  `[]?T`.
- Slice literals: `[]i64{1, 2, 3}`, `[]Point{{X: 1}, {X: 2}}`.
- `[N]T` declares a slice that starts with N zero elements: `var grid [3][3]u8`,
  struct fields `cells [16]i64`. It is not a value type: assigning it shares it.

### Maps

- `make(map[K]V)` or a literal `map[str]i64{"a": 1}`.
- `m[k]` reads (a missing key reads as V's zero value: 0, `""`, an empty slice, a new
  empty struct or map); `v, ok := m[k]` also reports presence; `m[k] = v` writes;
  `m[k] += 1` updates; `delete(m, k)` removes; `len(m)` counts.
- `for k, v := range m` iterates in table order (not sorted, not random).
- Keys are `str` or integer types.

### Structs

```go
type Point struct {
	X, Y i64
	Name str
	Tags []str
	Next ?Point
}
p := Point{X: 1, Y: 2, Name: "a", Tags: []str{}}
p := Point{1, 2, "a", []str{}, nil}   // positional, every field in order
```

- Fields of type `str`, `[]T` and `[N]T` that a literal leaves out start as `""` and
  empty slices. Fields of struct, map and func type must be set (they cannot be nil);
  make them `?T` to allow nil.
- `p.X` reads a field, `p.X = 3` writes it (see `mut` in section 5).
- `new(T)` is `T{}`.

### Enums

An enum is a value that is one of several variants, each with its own data:

```go
type Shape enum {
	Circle(r f64)
	Rect(w, h f64)
	Named(name str, inner Shape)  // enums may hold themselves (trees)
	Empty
}
type Color enum { Red, Green, Blue }
type Option[T any] enum { Some(v T), None }

s := Shape.Rect(3, 4)
c := Color.Red
o := Option[i64].Some(7)

switch s {                        // must handle every variant, or have default
case Circle(r):
	area = 3.14159 * r * r
case Rect(w, h):
	area = w * h
case Named(_, inner):             // _ skips a value
	area = 0
case Empty:
	area = 0
}
```

- A variant's data is read only through `switch`: there is no `s.r`, and no composite
  literal `Shape{...}`. A case either binds every value of one variant, or lists several
  variants that bind nothing (`case Green, Blue:`). A `switch` that misses a variant
  without a `default` is a compile error naming the missing ones; one whose every branch
  returns ends the function.
- `==` compares by value (same variant, equal data) when all the data compares by value
  (numbers, bools, strs, such enums); an enum holding a slice, map, struct or func cannot
  be compared.
- Printing gives `Rect(3 4)` / `Red`; JSON (argo) is `{"Rect":{"w":3,"h":4}}` for a variant
  with data and `"Red"` for one without, both ways.
- The zero value (for example next to a fault) is the first variant without data.
- Enums are references underneath, like structs: `keep` copies them, and the region check
  treats their data like struct fields. Variants follow the export rule.

### Strings

- `len(s)` is the byte length; `s[i]` is a `u8` (bounds checked); `s[lo:hi]` is a
  substring; `+` concatenates; `==`, `!=`, `<`, `<=`, `>`, `>=` compare byte-wise.
- `for i, c := range s` iterates UTF-8 code points: `i` the byte offset, `c` the code
  point as an `i32` (invalid bytes give U+FFFD).
- Conversions: `str(b)` from a `[]u8`, `str(c)` from an integer code point, `[]u8(s)` to
  bytes; `mint` converts numbers (section 13 lists `say.Str` too).

### Optionals and faults

`?T` and `fault` are the only types with a `nil` value; see sections 8 and 9.

### Function values

```go
type Handler func(anvil.Req, mut anvil.Out)
func double(x i64) i64 { return 2 * x }
f := double
g := func(x i64) i64 { return x + 1 }  // a literal; it cannot capture local variables
say.Line(f(3), g(3))
```

Function literals are lifted to top-level functions: they may use their parameters and
globals, not the enclosing function's locals.

A `mut` parameter is part of a function's type: `func put(b mut Box)` has type
`func(mut Box)`, which is not `func(Box)`. A call through a function value is checked like a
direct one: an argument for a `mut` parameter must be modifiable, and because the callee is
unknown, the compiler assumes it may store request memory there, so passing long-lived
memory (a global, or anything reachable from one) to a `mut` parameter of a function value is
a compile error. Call the function directly, or pass request-owned memory.

### Conversions

There are no implicit conversions between types. Convert explicitly:

| conversion | meaning |
|---|---|
| `i64(x)`, `u8(x)`, `i32(x)` ... | integer to integer: truncates to the width, then sign- or zero-extends |
| `f64(n)` | integer to float |
| `i64(f)` | float to integer, truncating toward zero |
| `str(b)` | `[]u8` to `str` (copies) |
| `[]u8(s)` | `str` to `[]u8` (copies) |
| `str(c)` | integer code point to a one-character `str` (UTF-8) |
| `T(x)` | between a named type and its underlying type |

### Named types

`type Celsius f64`, `type IDs []i64`, `type Handler func(Req, mut Out)` declare new names;
a named type converts to and from its underlying type explicitly.

---

## 4. Constants

```go
const Limit = 100            // untyped integer constant
const Pi = 3.141592653589793 // untyped float constant
const Name = "tin"           // string constant
const Mask u8 = 0x0f         // typed constant
const (
	Red Color = iota         // iota: 0, 1, 2 ... within a const group
	Green                    // repeats the previous expression with the next iota
	Blue
)
```

- Untyped constants take the type the context needs and must fit it: `var b u8 = 300`
  and `i8(200)` are compile errors.
- Constant expressions are folded exactly in 64 bits; values above 2^63-1 are treated as
  unsigned for `>>`, `/`, `%` and comparisons.
- A constant used where no type is known becomes an `i64` (integers) or `f64` (floats).

---

## 5. Declarations

### Variables

```go
x := 1                       // declare and initialize (type inferred)
var y i64 = 2                // with a type
var z u8                     // zero value: 0, false, "", empty slice
var s []str                  // an empty slice (a real header, never nil)
a, b := 1, 2                 // several at once
q, err := parse("12")        // results of a multi-value call
```

- Every variable is initialized. Struct, map and func variables need an initializer
  (they have no zero value).
- `:=` declares new variables in the current scope; a name cannot be redeclared in the
  same scope.

### Globals

```go
var hits i64                       // per core: every core has its own copy
var cache map[str]User = make(map[str]User)
```

Globals are per core (section 11): each core thread has its own copy, and initializers
run once on every core. Values stored into globals live in the long-lived heap
(section 10).

### Functions

```go
func add(a i64, b i64) i64 {
	return a + b
}
func divmod(a i64, b i64) (i64, i64) {
	return a / b, a % b
}
func parse(s str) !i64 { ... }
func fill(xs mut []i64, v i64) {      // may modify its argument
	for i := 0; i < len(xs); i++ {
		xs[i] = v
	}
}
```

- Parameters each have a type (`a i64, b i64`; a shared type list `a, b i64` is also
  accepted). Up to 8 integer and 8 float parameters.
- Results: none, one (`i64`), a list (`(i64, str)`), or any of these marked as able to fail (`!i64`, `!(i64, str)`, `!`); up to 8. There are no named
  results.
- Every path of a function with results must end in a `return`.
- Parameters are read-only: modifying a parameter's contents (assigning its fields or
  elements, appending to it, storing into its map) is a compile error unless the
  parameter is declared `mut`. Passing a read-only parameter on to a `mut` parameter is
  also rejected. Reassigning the parameter variable itself is allowed.
- **Call-site `mut`.** An argument for a `mut` parameter is written `mut x`, so every
  call shows what it may modify: `fill(mut xs, 0)`, `sift.Ints(mut xs)`,
  `argo.Put(mut buf, v)`, `argo.Get(text, mut v)`, and through function values too
  (`f(mut box)`). Leaving it out, or writing it for a parameter that is not `mut`, is a
  compile error. Method receivers (`p.Move(1, 2)`) and the builtins `append`, `copy` and
  `delete` take no `mut`.

### Methods

```go
func (p Point) Dist() f64 { ... }
func (p mut Point) Move(dx i64, dy i64) { p.X += dx; p.Y += dy }
p.Move(1, 2)
```

The receiver is a parameter like any other: `mut` lets the method modify it. Methods are
declared on named struct types in the same package.

### Types

```go
type Point struct { X, Y i64 }
type Stack[T any] struct { items []T }    // generic: section 12
type ID i64
```

### Externs (standard library only)

```go
extern func write(fd i64, p i64, n i64) i64
extern func snprintf(buf i64, n i64, f i64, ...) i64
```

Declares a C function from the system library; see section 18.

---

## 6. Expressions

### Precedence (high to low)

| level | operators | associativity |
|---|---|---|
| unary | `-x`, `!x`, `^x` (bitwise not), `~x` (bitwise not), `try f()` | right |
| 5 | `*`, `/`, `%`, `<<`, `>>`, `&` | left |
| 4 | `+`, `-`, `\|`, `^` | left |
| 3 | `==`, `!=`, `<`, `<=`, `>`, `>=` | left |
| 2 | `&&` | left |
| 1 | `\|\|` | left |

Postfix forms bind tighter than unary operators: calls `f(x)`, indexing `s[i]`, slicing
`s[lo:hi]`, selectors `x.f`, composite literals `T{...}`, explicit type arguments
`F[T](x)`.

### Arithmetic

- Both operands of a binary operator have the same type (after untyped constants adapt):
  `i32 + i64` is an error; convert one side.
- Integer arithmetic wraps on overflow. Division by zero panics. `/` truncates toward
  zero; `%` has the sign of the dividend.
- `>>` is arithmetic for signed types and logical for unsigned types. A shift count is
  taken modulo 64, the hardware rule (`1 << 64` is 1); narrower types shift in 64 bits
  and then truncate to their width (`u8(1) << 9` is 0). Keep counts below the width.
- `&&` and `||` short-circuit and take `bool` operands.
- Strings support `+` and comparisons; `bool` supports `==`, `!=`, `!`, `&&`, `||`.
- Comparing references: optionals and faults compare with `nil`; `==` on structs, slices
  and maps compares identity (the same object), not contents: compare fields or
  elements for equality of contents.

### Conditions

Conditions of `if`, `for` and `switch` cases must be `bool`; there is no truthiness.

### Calls

- Arguments are evaluated left to right.
- A call that returns several values is used in a multi-assignment, a `return` of the
  same result list, or with `try`.
- Calling through a function value: `f(x)`.
- Method call: `x.M(args)`; `pkg.F(args)` for a package function.

### Composite literals

`T{F: v, G: w}`, `T{v, w}` (all fields, in order), `[]T{a, b}`, `map[K]V{k: v}`,
`Stack[i64]{items: []i64{}}`. Inside a slice or map literal, the element type may be
omitted for struct elements: `[]Point{{X: 1}, {X: 2}}`.

---

## 7. Statements

```go
x := expr                    // declaration
x = expr                     // assignment
a, b = b, a                  // parallel assignment
x += 1; x -= 1; x *= 2       // compound assignment (all binary operators)
x++; x--
f(x)                         // expression statement (a call)

if v := f(); v > 0 {         // optional init statement
} else if v < 0 {
} else {
}

for i := 0; i < n; i++ { }   // three-clause loop
for cond { }                 // while loop
for { }                      // infinite loop
for i, x := range xs { }     // slice: index and element (x is a copy of the element)
for i := range xs { }        // index only
for _, x := range xs { }     // element only
for i, c := range text { }   // str: byte offset and code point
for k, v := range m { }      // map
for i := range 10 { }        // integers 0..9

switch x {                   // tag switch: no fallthrough
case 1, 2:
	...
case 3:
	...
default:
	...
}
switch v := f(); {           // tagless switch with an init statement
case v > 10:
case v > 0:
}

break; continue              // innermost loop (break also leaves a switch)
return; return x; return a, b
defer f(a, b)                // section 8
```

There are no labels, no `goto`, no `fallthrough` and no `select`. `go` is rejected
(section 11).

---

## 8. Errors

A function that can fail says so in its result: `!T` is "a T, or a fault", `!(A, B)`
"an A and a B, or a fault", and `!` alone "nothing, or a fault".

```go
func parse(s str) !i64 {
	if s == "" {
		fail "empty input"           // leave with a fault (zero values for the rest)
	}
	n := i64(0)
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c < '0' || c > '9' {
			fail say.Fault("bad digit %q at %d", str(c), i)
		}
		n = n*10 + i64(c-'0')
	}
	return n                         // success: just the value
}

func double(s str) !i64 {
	v := try parse(s)                // on a fault: pass it upward
	return v * 2
}

func save(path str, text str) ! {   // can fail, gives nothing
	w := try flume.Create(path)
	w.Str(text)
	try w.Close()
}                                    // running off the end succeeds

func main() {
	v := double("21") catch err {    // handle it where it happens
		say.Line("error:", err)
		0
	}
	n, err := double("x")            // or look at the fault yourself
	if err != nil {
		say.Line("error:", err)      // a fault prints as its message
	}
	say.Line(v, n)
}
```

- **One way to write it.** A result list ending in `fault` is rejected: write `!T`. In a
  `!T` function `return` gives only the values (`return v`; a bare `return` in a `!`
  function), and `fail X` leaves with a fault: X is a `str` message or a `fault` value.
  `return v, nil` and `return 0, fail(...)` are compile errors that point at these forms.
  A fault always comes with zero values: `str`, slice, map and struct zeros are real
  values, never nil, so a struct that owns a resource must treat its zero value as
  closed (as `flume.Writer` and `wire.Conn` do).
- **A fault must be handled.** Ignoring a call's fault is a compile error; so is a fault
  variable that is never read, and `_` in a fault position.
- `fail("text")` as an expression makes a fault value (to store or pass along);
  `say.Fault(format, args...)` formats one. A fault prints as its message, and
  `say.Str(err)` gives the message as a `str`.
- `try` passes a fault upward (inside a `!T` function): `v := try f()`, `v = try f()`,
  `a, b := try f()`, `try f()` (statement), `return try f()`.
- `catch` handles a fault in place: `E catch err { ... }` on a whole statement,
  initializer, assignment or return value (not inside a larger expression). `err` is the
  fault (`_` to ignore it). When a value is needed, the block's last expression is that
  value; otherwise, or when the call has several results, the block must leave (`return`,
  `break`, `continue`, `fail`, `panic`). On success the block does not run.
  ```go
  port := mint.Atoi(text) catch _ { 8080 }
  n, ok := parsePair(s) catch err {
      say.Line("skipping:", err)
      continue
  }
  w.Close() catch err { herald.Warn(say.Str(err)) }
  ```
- `try` and `catch` cannot be nested inside another expression: bind the inner result
  first.
- `defer f(args)` evaluates `f` and its arguments when the defer statement runs and calls
  `f` when the function returns, last deferred first, on every return path including the
  returns `try` makes. A defer inside a loop is rejected (it would run once per function,
  not per iteration: move the loop body into a function). Deferring a call that returns a
  fault is rejected (the fault would be lost: defer a function that handles it).
  Deferred calls must be plain function or method calls.
- `panic("message")` stops the program with status 2 after printing `panic: message`
  and a backtrace of the calling functions (inlined functions do not appear). A failed
  bounds check prints `index out of range [5] with length 3`. Panics cannot be recovered.

---

## 9. Optionals

`?T` holds a `T` or `nil` (T is a reference type: str, slice, map, struct). Inside a
branch where the compiler can see the check, the variable has type `T`:

```go
func find(id i64) ?User { ... }

u := find(7)
if u == nil {
	return
}
say.Line(u.Name)                 // u is a User from here on

if a != nil && b != nil {        // both narrowed inside
	use(a, b)
}
if l == nil || r == nil {        // both narrowed after the if when it returns
	return 1
}
return check(l) + check(r)
```

Narrowing works on local variables in `if x != nil {...}`, `if x == nil {...} else
{...}`, `if x == nil { return }` (narrowed after), and `&&` / `||` combinations of these.
Assigning `nil` to a narrowed variable is a type error. Store a field in a local first to
narrow it (`l := n.left`).

---

## 10. Memory and regions

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

```go
var cache map[str]User = make(map[str]User)
var recent []str

func remember(q anvil.Req, u User) {
	cache[keep(q.Path)] = keep(u)     // key and value copied into long-lived memory
	recent = append(recent, keep(q.Path))
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
- function summaries: which `mut` parameters a function stores request memory into, and
  where its results come from (iterated to a fixed point over the whole program). A
  helper that stores its argument into a global makes its callers `keep`; passing a
  global to a function that stores request memory into that parameter is an error at the
  call (`put stores request memory into its mut parameter 'b', but this argument may be
  long-lived: keep() the stored values inside put`);
- `keep` results, globals and constants are long-lived; literals are static.

Plain programs (no server) never reset their pool: memory is released when the program
exits.

---

## 11. Concurrency: one thread per core, share nothing

There are no goroutines and no shared mutable state.

- **Globals are per core.** Each core thread has its own copy of every global,
  initialized on that core. Two cores never see each other's globals.
- `go f()` is a compile error.
- `hearth.Run(n, f)` runs `f(core)` on n core threads (the calling thread is core 0) and
  returns when all have returned. `hearth.Cores()` is the number of CPUs the process may
  use (on Linux it respects the container's CPU limit and affinity), `hearth.ID()` the
  current core.
- `relay.Send(core, msg)` copies a `str` message into another core's inbox (a lock-free
  queue); `relay.Recv()` blocks for the next one, `relay.TryRecv()` polls,
  `relay.Broadcast(msg)` sends to every other core. Encode structs with `argo.Put` /
  `argo.Get`.
- `anvil.Serve` runs one HTTP event loop per core; a connection stays on one core.
  `anvil.OnRelay(h)` and `anvil.OnTick(ms, h)` run handlers on server cores between
  requests.

---

## 12. Generics

```go
func Max[T i64 | f64 | str](a T, b T) T {
	if a > b {
		return a
	}
	return b
}

func Map[T any, U any](xs []T, f func(T) U) []U {
	out := make([]U, 0, len(xs))
	for _, x := range xs {
		out = append(out, f(x))
	}
	return out
}

type Stack[T any] struct {
	items []T
}

func (s mut Stack[T]) Push(x T) {
	s.items = append(s.items, x)
}

func (s mut Stack[T]) Pop() (T, bool) {
	n := len(s.items)
	if n == 0 {
		var zero T
		return zero, false
	}
	x := s.items[n-1]
	s.items = s.items[:n-1]
	return x, true
}

type Pair[A any, B any] struct {
	first  A
	second B
}

Max(3, 9)                          // T inferred from the arguments
Max[f64](1, 2.5)                   // explicit
s := Stack[i64]{items: []i64{}}
p := Pair[str, i64]{first: "k", second: 7}
```

- Type parameters: `[T any]`, `[T comparable]`, or a union `[T i64 | f64 | str]` (the
  type argument must be one of them). Several: `[K comparable, V any]`.
- Type arguments are inferred from the call's arguments (untyped constants default to
  `i64`/`f64`), or given explicitly: `F[T](...)`, `pkg.F[T](...)`.
- Every instantiation is compiled separately and fully specialized: there is no boxing
  and no runtime dispatch. Methods of a generic type are instantiated with it.
- `var zero T` is T's zero value (an error at instantiation if T has none, e.g. a
  struct).
- Inside a generic function, operations are checked per instantiation: `a > b` with
  `T = bool` is reported where `Max[bool]` is instantiated.

---

## 13. Builtins

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
| `panic(msg)` | stop the program |
| `fail(msg)` | make a fault |
| `keep(x)` | deep copy into long-lived memory (section 10) |
| `print(...)`, `println(...)` | same as `say.Text` / `say.Line` |

Compiler-generated package functions: `say.*` (section 15), `argo.Put`, `argo.Get`
(section 16).

---

## 14. String interpolation

A `"..."` literal can hold values in braces; it becomes a `str` built by the same
formatting code as `say.Fmt`, decided at compile time from each value's static type:

```go
msg := "user {u.Name} has {len(items)} items"
row := "{price:.2} {id:x} [{name:-12}] [{n:05}]"
fail "port {n} out of range"
say.Line("hits={m["hits"]}")            // not allowed: no quotes inside {...}
say.Line(`raw strings keep {braces}`)   // backquotes: no interpolation
say.Line("literal {{braces}} and 100%") // {{ and }} are braces; % needs no escaping
```

- Anything inside `{...}` is an expression (no `"` inside; bind the value first).
- A spec after the last top-level `:` uses printf flags, width, precision and verb:
  `{x:5}`, `{x:-8}`, `{x:05}`, `{x:x}`, `{x:q}`, `{x:.3e}`. Without a verb the value is
  printed as `%v`, and a precision on a float means decimal places (`{pi:.2}` is `3.14`).
- A lone `}` is an error (write `}}`), and so is an unclosed `{`.

## 15. Printing and formatting: say

`say` is built into the compiler: each argument is formatted by its static type, without
interfaces or reflection.

```go
say.Line("x =", x, ok)              // space-separated, newline
say.Text("no", "spaces")            // concatenated, no newline
say.Out("%5.2f|%-4s|%x\n", f, s, n) // printf to stdout
s := say.Fmt("%d items", n)         // printf to a str
s2 := say.Str(x)                    // one value as a str
err := say.Fault("bad %q", s)       // printf to a fault
say.To(w, "%d\n", n)                // printf to w (any value with a Write(str) method)
say.LineTo(w, a, b)                 // Line to w
```

Verbs: `%v` (default format), `%d` (integer), `%s` (string), `%q` (quoted string or
character), `%x %X` (hex, also of strings), `%o` (octal), `%b` (binary), `%c`
(character), `%U` (U+0041), `%e %E` (exponent), `%f` (fixed), `%g %G` (shortest), `%t`
(bool), `%p` (address), `%%`. Flags: width (`%5d`), precision (`%.3f`), `-` (left
align), `+` (sign), `0` (zero pad), `#` (alternate), space.

Default formats: integers in decimal; floats in the shortest form that reads back
exactly, with an exponent below 1e-4 or from 1e21 (Go's `%v`); `true`/`false`; strings as
is; slices as `[a b c]`; maps as `map[k:v ...]` with sorted keys; structs as `{a b}`;
nil optionals and faults as `<nil>`.

Output to stdout is buffered (64 KiB, or per line on a terminal) and flushed at exit.

---

## 16. JSON: argo

```go
type User struct {
	id    i64
	name  str
	email str
	tags  []str
	boss  ?User
}

b := make([]u8, 0, 1024)
argo.Put(mut b, User{id: 7, name: "ana", email: "a@x", tags: []str{"admin"}})
// {"id":7,"name":"ana","email":"a@x","tags":["admin"],"boss":null}

u := User{tags: []str{}}
err := argo.Get(text, mut u)        // fills u; returns a fault for bad JSON or types
xs := []User{}
err2 := argo.Get(text, mut xs)      // appends decoded elements
```

- The compiler generates an encoder and a decoder for each type. JSON member names are
  the struct's field names, in declaration order.
- `argo.Put(mut b, v)` appends to a `[]u8`; any type: integers, floats (shortest exact form,
  exponent below 1e-6 or from 1e21, NaN/Inf as `null`), bools, strs (escaped), slices,
  maps with str or integer keys, structs, optionals (`null` when nil), faults (their
  message or `null`).
- `argo.Get(text, mut v)` fills a struct, slice (appending) or map (adding entries); nested
  struct fields are filled in place, `?T` fields accept `null`, unknown members are
  skipped, sized integers are range checked (`700` into a `u8` is a fault), and trailing
  garbage is a fault. Error messages name the offset: `argo: expected an integer in
  [0, 65535] at offset 8, found "7"`.
- `argo.Str(b, s)` and `argo.Raw(b, json)` write pieces by hand.

---

## 17. Safety checks

- **Bounds**: every slice and string index is checked; slicing beyond the length panics.
  The compiler removes a check where it can prove the index is in range: `range` loops,
  `for i := 0; i < len(s); i++` (and loops whose bound is `len(s)` held in an unchanged
  variable), `if i < len(s)` with a non-negative i, and constant indexes.
- **Nil**: str, slice, map and struct values are never nil. Optionals must be checked
  before use (section 9). Missing map keys read as zero values; `try` returns real zero
  values.
- **Integer overflow** wraps (it does not trap). Division by zero panics.
- **Uninitialized memory** cannot be read: every variable, field and element starts as a
  zero value or is required to be set.
- **Memory lifetime**: the region check (section 10).
- **Data races**: impossible by construction (section 11).
- **Stack overflow**: deep recursion crashes the process (the default thread stack is
  8 MiB).

---

## 18. Standard-library-only features

Files under `lib/` are trusted and may use operations user code cannot:

- `cast(T, x)` between `i64` and reference types (a str is a pointer to
  `[length word][bytes][NUL]`; a slice to a header `[len, cap, data, region]`);
- word indexing on raw pointers (`p[i]` reads the 8-byte word at `p + 8*i` when `p` is an
  `i64`), `load8(p)`, `store8(p, v)`, `__ld(p, log2size)`, `__st(p, v, log2size)`;
- atomics: `__atomic_add`, `__atomic_swap`, `__atomic_cas`, `__atomic_load`,
  `__atomic_store`; `__yield` (a spin-wait hint);
- `__ctx()` / `__set_ctx(p)` (the core context register), `__fp()` (the frame pointer),
  `__empty()` (the static empty slice header), `&x` (address of a local or global);
- `extern func name(params) R` declarations of system library functions (variadic C
  functions need `...` in the declaration); C int results are valid in the low 32 bits:
  convert with `i64(i32(x))`;
- `shared var` (one process-wide variable, not per core) for the runtime's own state;
- the runtime's `rt_` functions (see RUNTIME.md).

User code that needs these goes through a library package.

---

## 19. Grammar

EBNF; `{x}` repeats, `[x]` is optional, `|` separates alternatives. Semicolons are
inserted automatically (section 2).

```
File          = PackageClause ";" { Import ";" } { TopDecl ";" } .
PackageClause = "package" ident .
Import        = "import" ( ImportSpec | "(" { ImportSpec ";" } ")" ) .
ImportSpec    = [ ident ] string .
TopDecl       = ConstDecl | VarDecl | TypeDecl | FuncDecl | ExternDecl .

ConstDecl     = "const" ( ConstSpec | "(" { ConstSpec ";" } ")" ) .
ConstSpec     = identList [ Type ] [ "=" exprList ] .
VarDecl       = [ "shared" ] "var" ( VarSpec | "(" { VarSpec ";" } ")" ) .
VarSpec       = identList ( Type [ "=" exprList ] | "=" exprList ) .
TypeDecl      = "type" ( TypeSpec | "(" { TypeSpec ";" } ")" ) .
TypeSpec      = ident [ TypeParams ] [ "=" ] Type .
TypeParams    = "[" TypeParam { "," TypeParam } "]" .
TypeParam     = ident [ Constraint ] .
Constraint    = "any" | "comparable" | Type { "|" Type } .

FuncDecl      = "func" [ Receiver ] ident [ TypeParams ] Params [ Results ] Block .
Receiver      = "(" ident [ "mut" ] Type ")" .
Params        = "(" [ Param { "," Param } ] ")" .
Param         = identList [ "mut" ] Type .
Results       = [ "!" ] [ Type | "(" Type { "," Type } ")" ] .   (a bare "!" only)
ExternDecl    = "extern" "func" ident "(" [ Param { "," Param } ] [ "," "..." ] ")" [ Results ] .

Type          = TypeName [ TypeArgs ] | "[" "]" Type | "[" expr "]" Type
              | "map" "[" Type "]" Type | "?" Type | "func" ParamTypes [ Results ]
              | "struct" "{" { identList Type ";" } "}"
              | "enum" "{" Variant { ( "," | ";" ) Variant } "}" .
Variant       = ident [ "(" [ identList Type { "," identList Type } ] ")" ] .
ParamTypes    = "(" [ [ ident ] [ "mut" ] Type { "," [ ident ] [ "mut" ] Type } ] ")" .
TypeName      = ident | ident "." ident .
TypeArgs      = "[" Type { "," Type } "]" .

Block         = "{" { Statement ";" } "}" .
Statement     = SimpleStmt | VarDecl | ConstDecl | IfStmt | ForStmt | SwitchStmt
              | "return" [ exprList ] | "break" | "continue" | "defer" Call | Block .
SimpleStmt    = expr | exprList ( "=" | ":=" ) exprList | expr assignOp expr
              | expr "++" | expr "--" .
IfStmt        = "if" [ SimpleStmt ";" ] expr Block [ "else" ( IfStmt | Block ) ] .
ForStmt       = "for" [ expr | ForClause | RangeClause ] Block .
ForClause     = [ SimpleStmt ] ";" [ expr ] ";" [ SimpleStmt ] .
RangeClause   = [ identList ":=" ] "range" expr .
SwitchStmt    = "switch" [ SimpleStmt ";" ] [ expr ] "{" { CaseClause } "}" .
CaseClause    = ( "case" exprList | "default" ) ":" { Statement ";" } .

expr          = unary | expr binaryOp expr .
unary         = primary | ( "-" | "!" | "^" | "~" ) unary | "try" Call .
primary       = operand | primary "." ident | primary "[" expr "]"
              | primary "[" [ expr ] ":" [ expr ] "]" | primary TypeArgs
              | Call | Composite .
Call          = primary "(" [ Arg { "," Arg } [ "..." ] ] ")" .
Arg           = [ "mut" ] expr .
Composite     = ( TypeName [ TypeArgs ] | "[" "]" Type | "map" "[" Type "]" Type )
                "{" [ Element { "," Element } [ "," ] ] "}" .
Element       = [ ( ident | expr ) ":" ] ( expr | "{" ... "}" ) .
operand       = literal | ident | "(" expr ")" | FuncLit .
FuncLit       = "func" Params [ Results ] Block .
```

---

## 20. Legacy syntax

The compiler's own sources (`selfhost/`, `lib/std.tin`) and old programs use Tin's first
syntax, still fully supported: a file with no `package` clause is legacy.

```
// Every value is a 64-bit word; there are no types.
var counter;                      // a global
const SIZE = 16;
extern fn malloc(n);              // a libSystem function
fn add(a, b) {                    // parameters are words; falling off the end returns 0
    let x = a + b;                // let declares; statements end with ;
    while x > 10 {
        x = x - 1;
    }
    if x == 3 { return 1; } else if x > 3 { return 2; }
    return x;
}
fn main(argc, argv) {             // argv is a pointer to C strings
    let p = malloc(16);
    p[0] = 1;                     // word indexing on pointers
    store8(p + 8, 'a');           // byte store; load8 reads
    puts("hello");                // string literals are C strings
    return 0;
}
```

Legacy programs are compiled with `lib/std.tin` (`tin` adds it automatically when a file
has no package clause). See [COMPILER.md](COMPILER.md) for how the compiler is written.

---

## 21. Differences from Go

| Go | Tin |
|---|---|
| `int`, `byte`, `rune`, `float64`, `string` | `i64`, `u8`, `i32`, `f64`, `str` |
| implicit untyped-to-typed only, but `int` everywhere | sized types everywhere, explicit conversions |
| `error` interface | `fault` (a message); `fail`, `say.Fault`, `try` |
| unchecked errors allowed | ignoring a fault is a compile error |
| nil maps, slices, pointers | never nil; `?T` for optional values |
| pointers, `&x`, `*p` | reference types (structs, slices, maps are references) |
| slices are values (header copied) | slices are references (header shared, `append` in place) |
| goroutines, channels, mutexes | one thread per core, per-core globals, `relay` messages |
| garbage collector | request pools + `keep` into a long-lived heap, checked at compile time |
| interfaces, reflection | generics (monomorphized), compiler-generated `say` and `argo` |
| closures capture variables | function literals cannot capture locals |
| `defer` in loops, `recover` | defer outside loops only; no recover |
| `fmt.Println` | `say.Line` (formatting by static type) |
| interfaces for sum types | `enum` with exhaustive `switch` |
| exported = capitalized | the same rule, enforced for names, methods and fields |
| `f(&x)` to let a callee modify x | `f(mut x)` for a `mut` parameter |
| `for range ch`, `select`, labels, `goto`, `fallthrough` | not available |
