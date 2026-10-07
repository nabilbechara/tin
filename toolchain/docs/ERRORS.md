# Compiler diagnostics

Every compiler error has a stable code and a name, printed after its location:

```text
example.tin:11:6: error E510 NOT_IN_UNION: type str does not satisfy the constraint of T
```

- The location is `file:line:col` (1-based). The message says what is wrong and, where the
  compiler knows it, how to fix it. Each error is one line; the compiler reports every error
  it finds in one run and exits with status 1.
- A code names a rule, not a sentence: several messages can share one code (a type and a
  shape given the wrong number of type arguments are both `E502 TYPE_ARG_COUNT`).
- Codes are stable. A code is never renumbered and never reused: when a diagnostic goes
  away, its entry stays on this page with a line `Retired: <why>`.
- The hundreds tell the area:

| codes | area |
|---|---|
| E0xx | reading files, tokens and syntax |
| E1xx | names, declarations, packages and imports |
| E2xx | types, expressions, calls and conversions |
| E3xx | memory: request pools, regions and `keep` |
| E4xx | faults and optionals |
| E5xx | generics, shapes and `dyn` |
| E6xx | concurrency, boundaries and lifecycle |
| E7xx | `mut` parameters and assignment |
| E8xx | trusted code and standard-library-only features |
| E9xx | building: targets, linking and limits |

Each entry below gives the rule, a program that breaks it with the exact output the compiler
prints for it, and the fixes. `tools/ci/diagnostics_check.py` compiles every example and
requires that output, and checks that the compiler, this page and the tests' expected
diagnostics agree on every code and name. Examples are edition 1, the syntax of LANGUAGE.md,
opened with ```` ```tin edition=1 ```` and compiled with `-edition 1`. Edition 0, the syntax
before it, is retired (#226): only `tin fix -edition 1` reads it.

An example for an error about the command line or the installation shows its command in a
```` ```sh ```` block (one line, `[VAR=value ...] tinc ARGS`), and a block opened with
```` ```text file=NAME ```` (any language) is a file written next to the example, such as a
`tin.lock`. An internal error, which only a compiler bug reaches, has a `No example:` line
instead of an example.

## E0xx Files, tokens and syntax

### E001 PACKAGE_CLAUSE

An edition 1 file starts with exactly one package declaration: `package main` for a
program, `package NAME` for a library.

```tin edition=1
fn main() {
}
```

```text
example.tin:1:1: error E001 PACKAGE_CLAUSE: edition 1 files start with a package declaration
```

Fix: start the file with `package main` (or the package's name), and keep only one.

### E002 IMPORT_ORDER

Imports come right after the package declaration, before any other declaration.

```tin edition=1
package main

fn helper() {
}

import "say"

fn main() {
	say.Line("hi")
}
```

```text
example.tin:6:1: error E002 IMPORT_ORDER: imports must precede declarations
```

Fix: move the import up, under the package declaration.

### E003 CANNOT_OPEN

The compiler reads every file named on its command line and every file of the packages they
import. Errors about the command line and the installation have no position.

```sh
tinc missing.tin
```

```text
error E003 CANNOT_OPEN: cannot open missing.tin
```

Fix: check the path (it is relative to the current directory) and that the file is readable.

### E010 UNEXPECTED_CHARACTER

Outside strings and comments, a program uses only the characters of Tin's tokens: letters,
digits, `_`, operators and punctuation.

```tin edition=1
package main

fn main() {
	let price = 5 $ 2
	_ = price
}
```

```text
example.tin:4:16: error E010 UNEXPECTED_CHARACTER: unexpected character '$'
```

Fix: remove the character, or put the text in a string.

### E011 INVALID_NUMBER

A number literal uses only the digits of its base (`0x` hexadecimal, `0b` binary, `0o`
octal), with `_` only between two digits, and an integer literal fits in 64 bits.

```tin edition=1
package main

fn main() {
	let mask = 0x1g
	_ = mask
}
```

```text
example.tin:4:13: error E011 INVALID_NUMBER: invalid number 0x1g
```

Fix: correct the digits, or write the number in a base whose digits it uses.

### E012 NUMERIC_UNIT

A unit directly after a number makes a typed constant. The units are `ns`, `us`, `ms`, `s`,
`m` and `h` for durations and `b`, `kb`, `mb` and `gb` for sizes.

```tin edition=1
package main

fn main() {
	let timeout = 30sec
	_ = timeout
}
```

```text
example.tin:4:16: error E012 NUMERIC_UNIT: unknown numeric unit suffix
```

Fix: use one of the units (`30s`), or put a space or an operator between the number and the name.

### E013 UNTERMINATED

A string literal is closed by `"` on the line where it starts, a raw string by a backquote
before the end of the file, and an escape sequence is complete.

```tin edition=1
package main

import "say"

fn main() {
	say.Line("hello)
}
```

```text
example.tin:6:11: error E013 UNTERMINATED: unterminated string literal
```

Fix: close the string; for text over several lines, use a raw backquote string or `\n`.

### E014 CHAR_LITERAL

A character literal holds exactly one character or escape between single quotes: `'a'`,
`'\n'`, `'é'`.

```tin edition=1
package main

fn main() {
	let c = 'ab'
	_ = c
}
```

```text
example.tin:4:10: error E014 CHAR_LITERAL: unterminated character literal
```

Fix: write one character, or use a string (`"ab"`) for more.

### E015 ESCAPE

A backslash in a string or character starts one of Go's escapes: `\n`, `\t`, `\r`, `\a`,
`\b`, `\f`, `\v`, `\\`, `\'`, `\"`, up to three octal digits, `\xHH`, `\uHHHH` or `\UHHHHHHHH`.

```tin edition=1
package main

import "say"

fn main() {
	say.Line("C:\path")
}
```

```text
example.tin:6:11: error E015 ESCAPE: unknown escape sequence \p
```

Fix: double the backslash (`"C:\\path"`), or use a raw backquote string, which has no escapes.

### E020 UNEXPECTED

The parser found a token where the grammar needs something else. The message names what
was expected and what was found (`found newline` when a line ended early).

```tin edition=1
package main

import "say"

fn main() {
	say.Line("total" 3)
}
```

```text
example.tin:6:19: error E020 UNEXPECTED: expected ')', found a number
```

Fix: add or remove what the message names. The cause is often just before the position: a
missing comma, operator, parenthesis or brace.

### E021 CONST_VALUES

A constant declaration gives its name a value.

```tin edition=1
package main

const width = 640
const height

fn main() {
}
```

```text
example.tin:4:7: error E021 CONST_VALUES: missing constant value
```

Fix: give the constant a value (`const height = 480`). (In edition 0, `const width, height = 640`
also gives this code: one value per name.)

### E030 INTERPOLATION

In a string, `{` starts a value that ends at the matching `}`, and one `{...}` holds one
value (with an optional format spec, `{price:.2}`). A literal brace is written `{{` or `}}`.

```tin edition=1
package main

import "say"

fn main() {
	let n = 3
	say.Line("total: {n")
}
```

```text
example.tin:7:11: error E030 INTERPOLATION: a { in a string starts a value: close it with }, or write {{ for a brace
```

Fix: close the value with `}`, double a literal brace (`{{`, `}}`), or use a raw backquote string,
which does not interpolate.

### E040 ATTRIBUTE_PLACEMENT

An attribute before a declaration (`@nopoll`) applies to a function, so it is followed by
`fn`.

```tin edition=1
package main

@nopoll
let limit = 10

fn main() {
}
```

```text
example.tin:4:1: error E040 ATTRIBUTE_PLACEMENT: attributes here must precede a function, found newline
```

Fix: put the attribute on the function it is meant for, or remove it.

### E041 UNKNOWN_ATTRIBUTE

A struct field takes only the attributes the language defines: `@json("name")`.

```tin edition=1
package main

type User struct {
	@jsonn("id") ID i64
}

fn main() {
}
```

```text
example.tin:4:2: error E041 UNKNOWN_ATTRIBUTE: unknown struct attribute; supported attributes are @json("name")
```

Fix: correct the spelling (`@json("id")`), or remove the attribute.

### E042 ATTRIBUTE_ARGS

`@json` takes one string literal: the field's name in JSON.

```tin edition=1
package main

type User struct {
	@json(1) id i64
}

fn main() {
}
```

```text
example.tin:3:11: error E042 ATTRIBUTE_ARGS: @json expects one string field name
```

Fix: write the name as a string: `@json("id")`.

### E043 EMPTY_TUPLE

A tuple type lists at least one element type.

```tin edition=1
package main

type Empty = ()

fn main() {
}
```

```text
example.tin:3:14: error E043 EMPTY_TUPLE: a tuple type needs at least one element type
```

Fix: list the element types (`(i64, str)`), or leave the result out when there is none.

### E044 ENUM_FIELD_TYPES

Every field of an enum variant has a type. Names that share a type are listed before it:
`Rect(w, h f64)`.

```tin edition=1
package main

type Shape enum { Rect(x f64, w, h,), Empty }

fn main() {
}
```

```text
example.tin:3:12: error E044 ENUM_FIELD_TYPES: an enum variant's fields need types: Variant(name Type, ...)
```

Fix: give the last field names their type (`Rect(x f64, w, h f64)`), or list only types
(`Rect(f64, f64, f64)`).

### E045 EMPTY_ENUM

An enum declares at least one variant.

```tin edition=1
package main

type Shape enum { }

fn main() {
}
```

```text
example.tin:3:12: error E045 EMPTY_ENUM: an enum needs at least one variant
```

Fix: list the variants (`type Shape enum { Circle(r f64), Empty }`), or use a struct.

### E050 LABEL_PLACEMENT

A label names a loop for `break` and `continue`, so it goes right before `for`.

```tin edition=1
package main

fn main() {
	let n = 1
	outer: if n > 0 {
	}
}
```

```text
example.tin:5:9: error E050 LABEL_PLACEMENT: a label must precede a loop, found 'if'
```

Fix: put the label on the loop it names, or remove it.

### E051 EMPTY_SELECT

A `select` waits for the first of its arms, so it needs at least one.

```tin edition=1
package main

fn main() {
	select {
	}
}
```

```text
example.tin:4:2: error E051 EMPTY_SELECT: select needs at least one arm
```

Fix: add the arms to wait on, or remove the `select`.

### E052 RANGE_LOOP

A loop over an integer range binds one name (`for i in 0..n`); a stepped range binds one
name and takes one step (`for i in (0..n).step(2)`), which must be positive: a constant step
of 0 or less is this error, and a step computed at run time that is 0 or less panics with
`range step must be positive` when the loop starts.

```tin edition=1
package main

import "say"

fn main() {
	for i, j in 0..3 {
		say.Line(i, j)
	}
}
```

```text
example.tin:6:2: error E052 RANGE_LOOP: an integer range loop has one binding
```

Fix: bind one name. To number the elements of a slice, range over the slice: `for i, x in xs`.
To count down, count up and compute the value: `for i in 0..n { let j = n - 1 - i }`.

### E053 EMPTY_MATCH

A `match` needs at least one arm.

```tin edition=1
package main

fn name(n i64) str {
	return match n {
	}
}

fn main() {
}
```

```text
example.tin:4:9: error E053 EMPTY_MATCH: match needs at least one arm
```

Fix: add the arms, ending with `_ => ...` when the arms do not cover every value.

### E054 PATTERN

A `match` arm's pattern is a literal, a range with literal endpoints (`1..10`), an enum
variant with its bindings (`Circle(r)`), a name that binds the value, or `_`.

```tin edition=1
package main

fn size(n i64) str {
	let low = 0
	return match n {
		low..10 => "small"
		_ => "large"
	}
}

fn main() {
}
```

```text
example.tin:6:3: error E054 PATTERN: range patterns need literal endpoints
```

Fix: use literal endpoints, or bind the value and test it in a guard.

### E055 DEFER_CALL

`defer` takes a function call, which runs when the function returns.

```tin edition=1
package main

fn main() {
	let n = 1
	defer n
}
```

```text
example.tin:5:2: error E055 DEFER_CALL: expected a function call
```

Fix: defer a call (`defer f.Close()`); wrap anything else in a function and defer a call to it.

### E090 OLD_SYNTAX

Edition 1 replaces some edition 0 syntax; the message names the replacement:

<!-- docs-check: old-syntax begin -->

| edition 0 | edition 1 |
|---|---|
| `func` | `fn` (also for function types) |
| `var`, `:=`, local `const` | `let` (or `mut` when it is assigned again) |
| `x++`, `x--` | `x += 1`, `x -= 1` |
| `while`, C-style `for` | `for cond { }`, `for i in 0..n { }` |
| `switch` | `match` |
| `go` | `scope` or `detach` |
| `extern`, pointer types, channel types | none in user code |
| positional struct literals `P{1, 2}` | `P{x: 1, y: 2}` |
| `/* */` comments, `;` between statements | `//` comments, one statement per line |

<!-- docs-check: old-syntax end -->

```tin edition=1 old-syntax
package main

func main() {
}
```

```text
example.tin:3:1: error E090 OLD_SYNTAX: edition 1 uses 'fn', not 'func'
```

Fix: write the edition 1 form the message names.

### E091 ONE_PER_DECLARATION

Edition 1 declares one name per declaration: one constant, global, type or import path
each, and no grouped `( ... )` declarations.

```tin edition=1
package main

let width, height = 640, 480

fn main() {
}
```

```text
example.tin:3:5: error E091 ONE_PER_DECLARATION: edition 1 declares one name per declaration
```

Fix: split the declaration: `let width = 640` and `let height = 480` on their own lines.

## E1xx Names and declarations

### E101 REDECLARED

A name is declared once in its scope. Two package-level declarations of one name, such as
two shapes, are an error at the second one.

```tin edition=1
package main

shape Reader { Read(buf mut []u8) !i64 }

shape Reader { Write(data []u8) !i64 }

fn main() {
}
```

```text
example.tin:5:1: error E101 REDECLARED: 'Reader' is declared as a shape twice
```

Fix: rename one of the declarations, or merge them into one.

### E102 BUILTIN_NAME

The compiler's intrinsics (`load8`, `store8` and the names that start with `__`, which the
standard library uses) are names of their own; a declaration cannot take one of them.

```tin edition=1
package main

fn load8(p i64) i64 {
	return p
}

fn main() {
}
```

```text
example.tin:3:1: error E102 BUILTIN_NAME: 'load8' is a builtin and cannot be redeclared
```

Fix: give the declaration another name.

### E103 UNDEFINED

Every name refers to a declaration in scope: a local, a parameter, a package-level
declaration of this package, or an imported package.

```tin edition=1
package main

fn main() {
	let n Count = 0
	_ = n
}
```

```text
example.tin:4:8: error E103 UNDEFINED: undefined type 'Count'
```

Fix: declare the name before using it, correct its spelling, or import its package.

### E104 PRIVATE

A lower-case name is private to its package: only capitalized names, methods and fields
are exported.

```tin edition=1
package main

import "twine"

fn main() {
	_ = twine.isASCII("abc")
}
```

```text
example.tin:6:11: error E104 PRIVATE: function isASCII is private to twine: only capitalized names are exported
```

Fix: use the package's exported API (toolchain/docs/STDLIB.md); in your own package, capitalize the
name to export it.

### E110 UNKNOWN_PACKAGE

An import path names a package in `vendor/`, in the standard library, or next to the
program's first file; a path starting with `./` names a package next to the importing file
(toolchain/docs/PACKAGES.md).

```tin edition=1
package main

import "geom"

fn main() {
}
```

```text
error E110 UNKNOWN_PACKAGE: unknown package "geom" (looked in the standard library, next to the importing file and in the program's directory)
```

Fix: correct the path; for a package in the program's own tree, write it relative to the
importing file (`import "./geom"`).

### E111 LOCK_MISMATCH

When the project directory has a `tin.lock`, every vendored source file (under `vendor/`) must
be listed in it with its SHA-256 hash, and every other file the lock lists must still have the
hash it records (toolchain/docs/PACKAGES.md). A changed or unexpected dependency does not build; the
message names the file, the hash the lock records and the hash the file has.

```text file=tin.lock
0000000000000000000000000000000000000000000000000000000000000000 example.tin
```

```tin edition=1
package main

fn main() {
}
```

```text
error E111 LOCK_MISMATCH: tin.lock hash mismatch for example.tin: the lock records sha256 0000000000000000000000000000000000000000000000000000000000000000, the file has 4eb9194b972df4b054a21723df19a9782709caaac26e7ba26e47ce961ac898a1
```

Fix: review the change; if it is intended, run `tin vendor` to copy the dependency again and
record the new hashes (or regenerate the entry with `shasum -a 256 example.tin`).

### E112 NOT_VENDORED

An import path whose first element contains a dot (`github.com/ana/geo`) names a package by
where it comes from. It is read only from `vendor/<path>` in the program's directory: never
from the standard library, and never from the network (toolchain/docs/PACKAGES.md).

```tin edition=1
package main

import "example.com/geo"

fn main() {
}
```

```text
error E112 NOT_VENDORED: package "example.com/geo" is not vendored: there is no vendor/example.com/geo in the program's directory (tin vendor copies it there; the build never fetches)
```

Fix: add the package to `tin.mod` with `require` and run `tin vendor`.

### E113 PACKAGE_CONFLICT

A package's name is the last element of its import path, and two import paths that load
different packages under the same name would merge into one package.

```text file=vendor/example.com/say/say.tin
package say

fn Hi() {
}
```

```tin edition=1
package main

import "say"
import "example.com/say"

fn main() {
}
```

```text
error E113 PACKAGE_CONFLICT: import paths "say" and "example.com/say" are different packages with the same name say
```

Fix: import only one of them; a vendored package should not reuse the name of a standard
package or of another dependency.

### E114 MANIFEST

A vendored package's `tin.mod` is made of `module PATH`, `require PATH SOURCE` and
`caps ...` lines (and `//` comments). Its capabilities are `net`, `files`, `spawn`, `exec`
and `unsafe` (toolchain/docs/PACKAGES.md).

```text file=vendor/example.com/peek/tin.mod
module example.com/peek
caps network
```

```text file=vendor/example.com/peek/peek.tin
package peek

fn Up() bool {
	return false
}
```

```tin edition=1
package main

import "example.com/peek"

fn main() {
	peek.Up()
}
```

```text
vendor/example.com/peek/tin.mod:2: error E114 MANIFEST: unknown capability 'network' (a tin.mod line is module PATH, require PATH SOURCE or caps net files spawn exec unsafe)
```

Fix: correct the line in the package's source and run `tin vendor` again.

### E115 LOCK_CAPS

`tin.lock` has a `caps PATH ...` line for every vendored package, and it must name exactly
the capabilities the vendored `tin.mod` declares, so a reviewer reading the lock sees what
each dependency may do. `tin vendor` writes these lines.

```text file=vendor/example.com/peek/tin.mod
module example.com/peek
caps net
```

```text file=vendor/example.com/peek/peek.tin
package peek

fn Up() bool {
	return false
}
```

```text file=tin.lock
243aa58c8a51ef9c086f7b67a8ec491bb556d1f9a8d0c5e70d0948967a79fbca vendor/example.com/peek/tin.mod
caps example.com/peek
```

```tin edition=1
package main

import "example.com/peek"

fn main() {
	peek.Up()
}
```

```text
error E115 LOCK_CAPS: tin.lock says "caps example.com/peek" for example.com/peek, its manifest declares "caps example.com/peek net" (run tin vendor)
```

Fix: run `tin vendor`, and review the capability the dependency now asks for.

### E120 NO_MAIN

A program has a `main` function, where it starts.

```tin edition=1
package main

fn Main() {
}
```

```text
error E120 NO_MAIN: no main function
```

Fix: add `fn main()` to the program's `package main`.

### E121 MAIN_SIGNATURE

`main` takes no parameters (the program reads its arguments with `lever`), and it is not `extern`.

```tin edition=1
package main

fn main(name str) {
}
```

```text
example.tin:3:1: error E121 MAIN_SIGNATURE: main takes no parameters
```

Fix: declare `fn main()` and read the command line with the `lever` package.

### E130 INIT_ORDER

Constants and globals are initialized in declaration order, so an initializer uses only
those declared before it.

```tin edition=1
package main

import "say"

let total i64 = base * 2
let base i64 = 21

fn main() {
	say.Line(total)
}
```

```text
example.tin:5:17: error E130 INIT_ORDER: the initializer of 'total' uses 'base' before it is initialized (globals are initialized in declaration order)
```

Fix: move the declaration that is used above the one that uses it.

### E131 CORE_GLOBAL

Globals are per core, and `main` runs on core 0 only. In a program that starts cores
(`anvil` `Serve`, `hearth.Run`), a global that `main` or a function it calls assigns holds the
new value on core 0 alone: the other cores read their own copy, still the initializer's. It
works with one core and answers wrongly with more, so it is refused. A global that only
`main`'s own code reads is fine, and so is one a handler assigns (its own core's copy).

```tin edition=1
package main

import "hearth"
import "say"

mut table []str

fn work(id i64) {
	say.Line(id, len(table))
}

fn main() {
	table = keep(make([]str, 3))
	hearth.Run(2, work)
}
```

```text
example.tin:13:2: error E131 CORE_GLOBAL: global 'table' is assigned here, in code that runs on core 0 only (main and what it calls): the other cores keep the initializer's value. Assign it in its initializer, in `on core.start` or in `once`
```

Fix: assign the global where every core runs: in its initializer, in an `on core.start`
handler, or in a `once` block of code the cores run (`examples/percore.tin`).

### E140 RECEIVER

A method belongs to a struct (or enum) type declared in the same package.

```tin edition=1
package main

fn (n i64) Double() i64 {
	return n * 2
}

fn main() {
}
```

```text
example.tin:3:1: error E140 RECEIVER: methods need a struct receiver, not i64
```

Fix: write a function that takes the value (`fn double(n i64) i64`), or declare a struct
that holds it and give the struct the method.

## E2xx Types, expressions and calls

### E201 MAP_KEY

A map compares its keys by value, so a key is a `str`, a number, a `bool`, or a struct or
enum made of those. Slices, maps and other references have no value to compare.

```tin edition=1
package main

fn main() {
	let seen = map[[]i64]bool{}
	_ = len(seen)
}
```

```text
example.tin:4:13: error E201 MAP_KEY: a map key must compare by value (str, numbers, bool, or structs and enums of those), not []i64
```

Fix: key the map by a value that stands for the slice, such as a `str` built from it, or a
struct of its fields.

### E202 ARRAY_TYPE

An array `[N]T` has a constant length of zero or more, a literal `[N]T{...}` lists at most N
values, and its rows of arrays hold numbers, `bool`s and `str`s.

```tin edition=1
package main

const size = -2

mut grid [size]i64

fn main() {
}
```

```text
example.tin:5:10: error E202 ARRAY_TYPE: array length must not be negative
```

Fix: give the array a length of zero or more; for other elements, use a slice and `append`.

### E203 NO_ZERO_VALUE

Structs, maps, functions and `dyn` values are never nil, so they have no zero value: a
variable of such a type needs an initializer, and an array or a slice made with a length
cannot start with such elements.

```tin edition=1
package main

type Point struct {
	x i64
}

mut p Point

fn main() {
}
```

```text
example.tin:7:5: error E203 NO_ZERO_VALUE: a variable of type Point needs an initializer (it cannot be nil; use ?T for an optional)
```

Fix: initialize the variable (`mut p = Point{}`), use `?T` for a value that may be missing, or
make the slice empty with a capacity (`make([]T, 0, n)`) and `append`.

### E210 ARG_COUNT

A call passes exactly as many arguments as the function has parameters (a variadic
parameter takes the rest).

```tin edition=1
package main

fn Max[T i64 | f64](a T, b T) T {
	if a > b {
		return a
	}
	return b
}

fn main() {
	_ = Max(1, 2, 3)
}
```

```text
example.tin:11:6: error E210 ARG_COUNT: Max expects 2 arguments, got 3
```

Fix: pass one argument per parameter; to take any number of values, declare the last
parameter variadic (`xs ...T`) or pass a slice.

### E211 VARIADIC_ARG

`xs...` passes a slice as the variadic parameter, so it is the last argument of a call.

```tin edition=1
package main

fn sum(base i64, xs ...i64) i64 {
	return base
}

fn main() {
	let xs = []i64{1, 2}
	_ = sum(xs..., 3)
}
```

```text
example.tin:9:12: error E211 VARIADIC_ARG: ... is only allowed on the last argument of a call
```

Fix: put the spread slice last, and pass the other values before it.

### E213 FIELD

A selector reads a field the struct declares; an enum's values are read with `switch` or
`match`, and other types have no fields.

```tin edition=1
package main

type User struct {
	Name str
}

fn main() {
	let u = User{Name: "ada"}
	_ = u.Email
}
```

```text
example.tin:9:7: error E213 FIELD: User has no field Email
```

Fix: correct the field name, or add the field to the struct.

### E214 METHOD

A method call names a method of the value's type (or of its shape, for a `dyn` value).

```tin edition=1
package main

type User struct {
	Name str
}

fn main() {
	let u = User{Name: "ada"}
	u.Save()
}
```

```text
example.tin:9:3: error E214 METHOD: User has no method Save
```

Fix: correct the method name, or declare the method (`fn (u User) Save()`).

### E215 NOT_CALLABLE

Only functions and function values can be called.

```tin edition=1
package main

fn main() {
	let n = 3
	n()
}
```

```text
example.tin:5:2: error E215 NOT_CALLABLE: 'n' is not a function
```

Fix: call a function; to convert, write the type (`i64(x)`).

### E216 COMPOSITE

A composite literal names its type (`T{...}`), sets fields of a struct by name, gives keys
in a map literal, and builds only structs, slices, arrays and maps; an enum value is built
with a variant (`Shape.Circle(2)`).

```tin edition=1
package main

type Point struct {
	X i64
	Y i64
}

fn main() {
	let p = Point{X: 1, Z: 2}
	_ = p
}
```

```text
example.tin:9:22: error E216 COMPOSITE: unknown field 'Z'
```

Fix: set the fields the struct declares, by name.

### E217 BUILTIN_ARGS

The builtins take fixed kinds of arguments: `len(x)`, `append(s, v...)` on a slice,
`make([]T, n)` or `make(map[K]V)`, `copy(dst, src)`, `delete(m, k)`, `panic(v)` and
`keep(v)`.

```tin edition=1
package main

fn main() {
	let m = map[str]i64{}
	delete(m)
}
```

```text
example.tin:5:2: error E217 BUILTIN_ARGS: delete needs a map and a key
```

Fix: give the builtin the arguments it takes (`delete(m, "k")`).

### E220 NOT_CONSTANT

A constant's value, an array length and a constant expression are computed by the compiler,
so they use only literals, other constants and operators.

```tin edition=1
package main

fn size() i64 {
	return 4
}

const maxSize = size()

fn main() {
}
```

```text
example.tin:7:17: error E220 NOT_CONSTANT: expression is not a constant
```

Fix: write the value with literals and constants, or make it a variable.

### E221 CONST_TYPE

An integer constant can be used where its value fits a number type; it cannot become a
`str`, a `bool` or another non-number.

```tin edition=1
package main

const name str = 7

fn main() {
}
```

```text
example.tin:3:7: error E221 CONST_TYPE: cannot use an integer constant as str
```

Fix: write a constant of the right kind (`const name = "7"`), or convert where it is used.

### E222 DIVISION_BY_ZERO

A constant expression that divides by zero (`/` or `%`) has no value.

```tin edition=1
package main

const parts = 0
const share = 100 / parts

fn main() {
}
```

```text
example.tin:4:19: error E222 DIVISION_BY_ZERO: division by zero in constant expression
```

Fix: divide by a constant that is not zero.

### E223 CONST_OVERFLOW

A constant fits the type it becomes: `300` is not a `u8`.

```tin edition=1
package main

fn main() {
	let b u8 = 300
	_ = b
}
```

```text
example.tin:4:13: error E223 CONST_OVERFLOW: constant 300 overflows u8
```

Fix: use a wider type, or a value in range.

Constant arithmetic is exact (#362): `9223372036854775807 + 1` is 2^63, which no signed type
holds, and an expression whose exact value is outside -2^63 .. 2^64-1 has no type at all.
Write `+%`, `-%` or `*%` where wrapping is meant.

### E224 SHIFT_COUNT

A constant shift count is between 0 and the width of the shifted value less one (#362): a
`u8` shifts by 0 to 7, an `i64` by 0 to 63. A count outside that range is a compile error; at
run time it panics (`shift count out of range`).

```tin edition=1
package main

fn main() {
	let x u8 = 1
	let y = x << 8
	_ = y
}
```

```text
example.tin:5:12: error E224 SHIFT_COUNT: shift count 8 is out of range for u8: counts are 0 to 7
```

Fix: shift a wider type (`u16(x) << 8`), or a count below the width.

### E230 TYPE_MISMATCH

A value is used where its type is expected: there are no implicit conversions, so an `i64`
is not a `str`, an `i32` is not an `i64`, and `str max 3` is not `str max 2`.

```tin edition=1
package main

fn main() {
	let n i64 = "seven"
	_ = n
}
```

```text
example.tin:4:14: error E230 TYPE_MISMATCH: cannot use str as i64
```

Fix: convert explicitly (`i64(x)`, `str(b)`, `mint.Atoi(s)`), or give the variable the
value's type.

### E231 CONVERSION

A conversion `T(x)` changes a value between number types, between a number and a rune or
byte, or between `str` and `[]u8`; other conversions do not exist.

```tin edition=1
package main

fn main() {
	let s = "12"
	let n = i64(s)
	_ = n
}
```

```text
example.tin:5:10: error E231 CONVERSION: cannot convert str to i64
```

Fix: parse text with `mint.Atoi(s)` (or `mint.ParseFloat`), and format a number with
`say.Str(n)`.

### E232 CONDITION

`if`, `for` and the other conditions take a `bool`; numbers, strings and optionals are not
true or false by themselves.

```tin edition=1
package main

fn main() {
	mut n = 3
	if n {
		n = 0
	}
}
```

```text
example.tin:5:5: error E232 CONDITION: condition must be a bool, not i64
```

Fix: compare explicitly (`if n != 0`, `if s != ""`, `if p != nil`).

### E233 UNTYPED_NIL

`nil` has no type of its own; it is a value of an optional (`?T`) or a fault, so it needs a
type from where it goes.

```tin edition=1
package main

fn main() {
	let x = nil
	_ = x
}
```

```text
example.tin:4:10: error E233 UNTYPED_NIL: nil needs an optional (?T) or fault type
example.tin:4:10: error E233 UNTYPED_NIL: use of untyped nil
```

Fix: write the type (`let x ?Point = nil`).

### E234 VALUE_COUNT

An assignment has one target per value, and places that take one value (a `try` that
initializes a variable, a line of `parallel`, the last expression of a boundary block) get
exactly one.

```tin edition=1
package main

import "say"

fn pair() (i64, i64) {
	return 1, 2
}

fn main() {
	let a = 0
	let b = 0
	let c = 0
	a, b, c = pair()
	say.Line(a, b, c)
}
```

```text
example.tin:13:2: error E234 VALUE_COUNT: assignment count mismatch
```

Fix: give as many names as there are values (use `_` for the ones you do not need).

### E235 NOT_A_VALUE

A type, or a package name on its own, is not a value.

```tin edition=1
package main

import "say"

fn main() {
	let x = say
	_ = x
}
```

```text
example.tin:6:10: error E235 NOT_A_VALUE: use of package 'say' without a selector
```

Fix: select from the package (`say.Line`), or build a value of the type (`T{}`).

### E236 OPERATOR

Each operator works on its own kinds of operands: arithmetic on numbers (and `+` on
`str`), `%`, bit operators and shifts on integers, `!`, `&&` and `||` on `bool`, and `<`,
`<=`, `>`, `>=` on numbers and `str`.

```tin edition=1
package main

fn main() {
	let ok = true
	mut n = 3
	if ok && n {
		n = 0
	}
}
```

```text
example.tin:6:8: error E236 OPERATOR: operands of && and || must be bool
```

Fix: compare to get a `bool` (`n != 0`), or convert the operand.

### E237 COMPARE

`==` and `!=` compare values of one type that have equality: numbers, `bool`, `str`, and
structs and enums whose fields hold such values (compared field by field). Slices, maps,
functions, `dyn` values and optionals have none, alone or inside a struct or enum;
`same(a, b)` asks whether two structs, slices or maps are one object.

```tin edition=1
package main

type Job enum {
	Run(fn())
	Idle
}

fn main() {
	let a = Job.Idle
	let b = Job.Idle
	_ = a == b
}
```

```text
example.tin:11:8: error E237 COMPARE: cannot compare Job values: a variant holds func(), which has no value equality
```

Fix: compare the parts that have equality, or give the type a method that compares.

### E238 INDEX

`x[i]` indexes a slice, an array, a `str` or a map, with an integer index (a map takes its
key type); slicing `x[a:b]` works on slices, arrays and `str`.

```tin edition=1
package main

fn main() {
	let xs = []i64{1, 2, 3}
	_ = xs["1"]
}
```

```text
example.tin:5:8: error E238 INDEX: index must be an integer, not str
```

Fix: index with an integer (convert with `mint.Atoi` or `i64(x)`).

### E239 VARIANT

An enum value is built with one of its variants, passing exactly the values it declares.

```tin edition=1
package main

type Shape enum {
	Circle(f64)
	Rect(f64, f64)
}

fn main() {
	let s = Shape.Rect(2.0)
	_ = s
}
```

```text
example.tin:9:15: error E239 VARIANT: Shape.Rect takes 2 values, got 1
```

Fix: pass every value of the variant (`Shape.Rect(2, 3)`), or use a variant the enum
declares.

### E240 SECRET_TYPE

`secret` qualifies a value: a number, `bool`, `str`, a slice or a map. A struct is not secret
as a whole; its fields are.

```tin edition=1
package main

type Login struct {
	user str
	pass str
}

fn main() {
	let l secret Login = Login{user: "ann", pass: "pw"}
	_ = l
}
```

```text
example.tin:9:8: error E240 SECRET_TYPE: secret qualifies numbers, bool, str, slices and maps, not Login: mark the struct's fields secret instead
```

Fix: declare the fields that hold secrets `secret` (`pass secret str`) and keep the struct plain.

### E241 SECRET_SINK

A secret never reaches a place that prints, formats, encodes or carries it: `say`, string
formatting, `panic`, fault messages (`fail`, `wrap`, `fault`, `say.Fault`), `argo.Put`, and
`copy` or `append` into a slice that is not secret. A value that holds a secret field counts.

```tin edition=1
package main

import "say"

fn main() {
	let token secret str = "s3cr3t"
	say.Line("token: {token}")
}
```

```text
example.tin:7:11: error E241 SECRET_SINK: say.Line would print secret value "token: {token}": leave it out, or reveal the secret on purpose
```

Fix: leave the secret out of the message, or write `reveal(x)` where showing it is intended
(`tin audit secrets` lists every `reveal`).

### E242 SECRET_TO_PLAIN

A secret goes only where a secret is declared: a variable, parameter, field or result that is
not `secret` does not take one. This is how logging and library calls that have not opted in
are kept from secrets.

```tin edition=1
package main

fn send(header str) i64 {
	return len(header)
}

fn main() {
	let token secret str = "s3cr3t"
	_ = send(token)
}
```

```text
example.tin:9:11: error E242 SECRET_TO_PLAIN: cannot pass secret value token to send: its parameter header is not declared secret (declare it secret, or write reveal(token) to pass it on purpose)
```

Fix: declare the parameter or variable `secret`, or pass `reveal(x)` on purpose.

### E243 SECRET_COMPARE

`==`, `!=`, the orderings and `min`/`max` take time that depends on where two values first
differ, which leaks a secret byte by byte, so they are errors on secrets.

```tin edition=1
package main

import "say"

fn main() {
	let token secret str = "s3cr3t"
	if token == "s3cr3t" {
		say.Line("ok")
	}
}
```

```text
example.tin:7:11: error E243 SECRET_COMPARE: cannot compare secret values with ==: use seal.Equal, which takes the same time whatever they hold
```

Fix: compare with `seal.Equal(a, b)`, which takes the same time whatever the values hold;
to order secrets, reveal them on purpose first.

### E244 SECRET_MAP_KEY

A map lookup compares its key in time that depends on the key, so a map key cannot be
secret.

```tin edition=1
package main

fn main() {
	let sessions = map[secret str]i64{}
	_ = sessions
}
```

```text
example.tin:4:17: error E244 SECRET_MAP_KEY: a map key cannot be secret: a lookup compares it in time that depends on its value (key the map by a hash of it, such as seal.Sha256Hex)
```

Fix: key the map by a hash of the secret, such as `seal.Sha256Hex(token)`.

### E245 REVEAL

`reveal(x)` takes exactly one secret value and gives it back with its plain type. A value
that is not secret, or a struct that only holds secret fields, has nothing to reveal.

```tin edition=1
package main

fn main() {
	let name = "ann"
	_ = reveal(name)
}
```

```text
example.tin:5:6: error E245 REVEAL: reveal needs a secret value, not str
```

Fix: drop the `reveal` from a plain value; for a struct, reveal the secret field itself
(`reveal(u.token)`).

### E250 BOUND_TYPE

`max N` bounds the length of a `str`, a slice or a map; the bound is a constant of zero or
more.

```tin edition=1
package main

fn main() {
	let count i64 max 5 = 3
	_ = count
}
```

```text
example.tin:4:12: error E250 BOUND_TYPE: max bounds the length of a str, a slice or a map, not i64
```

Fix: bound only a `str`, a slice or a map; check a number's range with an `if`.

### E251 UNCHECKED_BOUND

A value goes into a bounded type (`str max 8`) only when its length is known to fit: a
literal that is short enough, or a value checked with `bound(x)`.

```tin edition=1
package main

type User struct {
	name str max 8
}

fn rename(u mut User, raw str) {
	u.name = raw
}

fn main() {
}
```

```text
example.tin:8:11: error E251 UNCHECKED_BOUND: cannot use str as str max 8: its length is unchecked (check it with bound(x), which fails with fault.LimitExceeded)
```

Fix: check the length with `bound`, which fails with `fault.LimitExceeded` when it does not
fit: `u.name = try bound(raw)`.

### E252 BOUND_CALL

`bound(x)` checks one value against the bounded type it is stored into, so it needs a
destination whose type is bounded (`str max N`), and a value of that kind.

```tin edition=1
package main

fn check(raw str) ! {
	try bound(raw)
}

fn main() {
}
```

```text
example.tin:4:6: error E252 BOUND_CALL: bound needs a bounded destination to check against: write its type (let v str max 100 = try bound(x))
```

Fix: write the bounded type: `let b str max 100 = try bound(raw)`.

### E260 MISSING_RETURN

A function with results ends with a `return` (or `fail`, `panic`, or an `if`/`switch`/loop
that does on every path), so it never runs off its end.

```tin edition=1
package main

fn sign(n i64) i64 {
	if n < 0 {
		return -1
	}
}

fn main() {
}
```

```text
example.tin:3:1: error E260 MISSING_RETURN: function 'sign' is missing a return at the end
```

Fix: add the `return` for the remaining paths.

### E261 OUTSIDE_LOOP

`break` and `continue` (without a label) belong to the innermost `for` loop around them.

```tin edition=1
package main

fn main() {
	let n = 1
	if n > 0 {
		break
	}
}
```

```text
example.tin:6:3: error E261 OUTSIDE_LOOP: break outside a loop
```

Fix: use `return` to leave the function, or move the statement into the loop.

A labeled `break outer` or `continue outer` needs an enclosing loop of the same function
labeled `outer`; otherwise the message is `break names no enclosing loop: outer`.

### E262 RETURN_COUNT

`return` gives one value per result of the function, and a function without results
returns none.

```tin edition=1
package main

fn both() (i64, str) {
	return 1
}

fn main() {
}
```

```text
example.tin:4:2: error E262 RETURN_COUNT: wrong number of return values
```

Fix: return every result, in order (`return 1, "one"`).

### E263 RANGE

`for x in` walks a slice, an array, a `str` (by rune), a map or a count of integers.

```tin edition=1
package main

type Point struct {
	x i64
	y i64
}

fn main() {
	let p = Point{x: 1, y: 2}
	for i in p {
		_ = i
	}
}
```

```text
example.tin:10:2: error E263 RANGE: cannot range over Point
```

Fix: range over a slice, map or `str` field of the value, or give the type a method that
returns one.

### E264 UNREACHABLE

A statement after a `return`, `fail`, `break`, `continue` or `panic(...)` in the same block
never runs.

```tin edition=1
package main

import "say"

fn answer() i64 {
	return 42
	say.Line("computed")
}

fn main() {
	say.Line(answer())
}
```

```text
example.tin:7:2: error E264 UNREACHABLE: this statement never runs: the return before it always leaves the block
```

Fix: move the statement before the one that leaves, or delete it; to leave only sometimes,
put the leaving statement in an `if`.

### E270 DEFER

A deferred call runs once, when the function returns: so `defer` is not used in a loop,
and a deferred call does not return a fault it would drop.

```tin edition=1
package main

import "say"

fn main() {
	for i in 0..3 {
		defer say.Line(i)
	}
}
```

```text
example.tin:7:3: error E270 DEFER: defer inside a loop would run once per function, not per iteration: move the loop body into a function
```

Fix: move the loop body into a function and `defer` there; defer a function that handles
the fault rather than one that returns it.

### E280 QUERY

A parameter of type `query` (a database or Redis command) takes a string literal: the
values in its `{...}` are sent apart from the text, so a value can never change the command.

```tin edition=1
package main

fn run(q query) {
}

fn main() {
	let text = "SELECT name FROM users WHERE id = 7"
	run(text)
}
```

```text
example.tin:8:6: error E280 QUERY: a query takes a string literal: put values in {...} so they are sent apart from the text, never pasted into it
```

Fix: write the value in the literal: `run("SELECT name FROM users WHERE id = {id}")`.

### E281 ARGO

`argo.Put(mut buf, v)` appends JSON for a value to a `[]u8`, and `argo.Get(text, mut v)`
fills a struct, slice or map from JSON; both need `import "argo"` and a type argo can
encode (no functions, `dyn` values or maps with other keys than `str` and integers).

```tin edition=1
package main

import "argo"

type Job struct {
	Run fn()
}

fn main() {
	let buf = []u8{}
	argo.Put(mut buf, Job{Run: main})
}
```

```text
example.tin:11:6: error E281 ARGO: argo cannot encode values of type func()
```

Fix: encode a struct of plain data (numbers, `str`, `bool`, slices, maps, structs and
enums of those).

### E282 FORMAT

`say.Out`, `say.Fmt` and the other printf-style calls take a format string first. A format
written as a literal is checked against the values after it, as `go vet` does: each verb is
one of `vdbcoOqxXUeEfFgGstp` (`%%` is a percent sign), formats its value's type (`%d` an
integer, `%s` a `str` or fault, `%f` a float, `%t` a bool, `%v` anything), and every verb has a
value and every value a verb. The spec of an interpolated value (`"{x:5.2f}"`) is checked the
same way: `[flags][width][.precision][verb]`. A format that is not a literal is checked when it
runs, which prints Go's `%!d(MISSING)` and `%!(EXTRA ...)` markers.

```tin edition=1
package main

import "say"

fn main() {
	let n = 3
	say.Out(n)
}
```

```text
example.tin:7:10: error E282 FORMAT: format must be a str
```

Fix: pass the format first (`say.Out("%d\n", n)`), or use `say.Line(n)`; give each verb a
value of its type, or use `%v`.

### E290 MATCH_PATTERN

A case of a `switch` or an arm of a `match` fits the value: a variant of the enum it
matches, with as many names as the variant has values, or a literal or range of a number or
`str`.

```tin edition=1
package main

type Shape enum {
	Circle(f64)
	Rect(f64, f64)
}

fn area(s Shape) f64 {
	return match s {
		Circle(r) => 3.0 * r * r
		Rect(w) => w
	}
}

fn main() {
}
```

```text
example.tin:11:3: error E290 MATCH_PATTERN: Rect has 2 values, the pattern has 1
example.tin:9:9: error E291 MATCH_EXHAUSTIVE: match on Shape does not handle Rect (add the arms, or _)
example.tin:11:14: error E103 UNDEFINED: undefined: w
example.tin:11:14: error E230 TYPE_MISMATCH: cannot use i64 as f64
```

Fix: name every value of the variant (`case Rect(w, h)`), and match only variants of the
enum.

### E291 MATCH_EXHAUSTIVE

A `switch` on an enum, and a `match` that gives a value, handle every variant (or have a
`default` / `_` arm), so adding a variant shows every place to update.

```tin edition=1
package main

type Light enum {
	Red
	Amber
	Green
}

fn next(l Light) Light {
	return match l {
		Red => Light.Green
		Green => Light.Amber
	}
}

fn main() {
}
```

```text
example.tin:10:9: error E291 MATCH_EXHAUSTIVE: match on Light does not handle Amber (add the arms, or _)
```

Fix: add the missing cases, or a `default` arm when the rest share one answer.

### E292 MATCH_UNREACHABLE

Every arm can be reached: an arm after one that matches every value, or a variant that an
earlier arm already handles, never runs.

```tin edition=1
package main

fn describe(n i64) str {
	return match n {
		_ => "any",
		0 => "zero",
	}
}

fn main() {
}
```

```text
example.tin:6:3: error E292 MATCH_UNREACHABLE: this arm is never reached: an earlier arm matches every value
```

Fix: remove the arm, or move the catch-all `_` arm last.

### E293 MATCH_VALUE

A `match` that gives a value has an arm that gives one, and then every arm gives one (or
leaves with `return`, `break`, `continue` or `fail`).

```tin edition=1
package main

import "say"

fn main() {
	let n = 2
	let s = match n {
		1 => "one",
		_ => {
			say.Line("other")
		},
	}
	say.Line(s)
}
```

```text
example.tin:10:7: error E293 MATCH_VALUE: this arm gives no value
```

Fix: end each block arm with its value, or leave from it.

## E3xx Memory and regions

### E310 REQUEST_ESCAPE

Memory allocated during a request lives in the core's request pool, which is wiped when the
request ends. Storing it into a global, or into anything a global can reach, would leave a
dangling reference, so `keep(x)` must copy it into the long-lived heap first.

```tin edition=1
package main

import "say"

mut last str

fn remember(name str) {
	last = name
}

fn main() {
	remember(say.Fmt("user-%d", 7))
}
```

```text
example.tin:8:2: error E310 REQUEST_ESCAPE: request memory stored into global 'last', which outlives the request: wrap the value in keep()
```

Fix: store `keep(x)` instead of `x`, or keep the value in a local that ends with the request.

### E311 CAPTURE_ESCAPE

A closure that may outlive the request (one passed to `keep`, stored in a global, or
returned) holds its captured variables in long-lived memory, so storing request memory into
one of them would dangle.

```tin edition=1
package main

import "say"

fn recorder() (fn(str) str) {
	mut last = "nobody"
	return fn(s str) str {
		let prev = last
		last = s
		return prev
	}
}

let rec fn(str) str = keep(recorder())

fn main() {
	say.Line(rec(say.Fmt("session-%d", 42)))
}
```

```text
example.tin:9:3: error E311 CAPTURE_ESCAPE: request memory stored into 'last', a captured variable of a closure that may outlive the request (keep() copies its variables into long-lived memory): wrap the value in keep(), or pass the closure only to functions that call it
```

Fix: store `keep(x)`, or pass the closure only to functions that call it during the request.

### E312 ARG_ESCAPE

A function that stores request memory into a `mut` parameter must be given an argument
that lives no longer than the request. Passing a global, or anything long-lived, through
that parameter would let request memory escape (the same rule as E310, through a call).

```tin edition=1
package main

import "say"

type Box struct {
	Items []str
}

let box Box = Box{}

fn put(b mut Box, s str) {
	b.Items = append(b.Items, s)
}

fn main() {
	put(mut box, say.Fmt("item-%d", 1))
}
```

```text
example.tin:16:2: error E312 ARG_ESCAPE: put stores request memory into its mut parameter 'b', but this argument may be long-lived: keep() the stored values inside put
```

Fix: pass a local instead of the long-lived value, or make the function store `keep(x)`.

### E313 USE_AFTER_RESET

`hearth.Reset()` frees the request pool, so a value allocated before the reset cannot be
read after it.

```tin edition=1
package main

import "hearth"
import "say"

fn main() {
	let s = say.Fmt("fresh-%d", 1)
	hearth.Reset()
	say.Line(s)
}
```

```text
example.tin:9:11: error E313 USE_AFTER_RESET: 's' may hold request memory from before hearth.Reset(), which freed it, and is read after the reset: keep() the value before the reset, or create it after
```

Fix: `keep()` the value before the reset, or create it again after.

### E314 DETACH_ESCAPE

A `detach` block runs as a task that outlives the request that started it, so what it
captures must already be long-lived: request memory is an error unless it was kept first,
or the block reads it only inside `keep()`.

```tin edition=1
package main

mut flushed str = ""

fn flush(s str) {
	flushed = keep(flushed + s)
}

fn later(n i64) {
	let msg = "job {n}"
	detach {
		flush(msg)
	}
}

fn main() {
	later(1)
}
```

```text
example.tin:11:2: error E314 DETACH_ESCAPE: detach captures 'msg', which may hold request memory, but the detached task outlives the request: keep() it before the block (let v = keep(...)), or read it in the block only inside keep()
```

Fix: `let kept = keep(msg)` before the block and use `kept` in it, or write `keep(msg)`
inside the block.

### E315 ARENA_ESCAPE

An `arena { }` block's memory is freed when the block ends, so nothing made in it may be
stored into anything made outside it: a variable from outside the block, a field, element or
map entry of an object from outside, or (through a call) a `mut` argument from outside.
Appending to, or inserting into, a slice or map from outside the block is rejected too,
whatever the value: the slice's new array or the map's new table would be allocated in the
arena. Only the block's value leaves it, copied into the enclosing region.

```tin edition=1
package main

import "say"

fn main() {
	mut last = ""
	let n = arena {
		let line = "line {len(last)}"
		last = line
		len(line)
	}
	say.Line(n, last)
}
```

```text
example.tin:9:3: error E315 ARENA_ESCAPE: memory made in an arena stored into 'last', a variable from outside it, which outlives the arena: make the value the arena block's result (it is copied out), or keep() it
```

Fix: make what must outlive the block its value (`last = arena { ... line }`), grow outside
slices and maps after the block from its value, or `keep()` the value (long-lived memory).

### E316 ARENA_VALUE

An `arena { }` block's value is deep-copied out of the arena, so its type must be one the
copy can follow: not recursive, and holding no `func` or `dyn` value.

```tin edition=1
package main

import "say"

type Node struct {
	name str
	next ?Node
}

fn main() {
	let n = arena {
		Node{name: "a", next: nil}
	}
	say.Line(n.name)
}
```

```text
example.tin:11:10: error E316 ARENA_VALUE: an arena block's value is copied out of the arena, but type Node is recursive, so it cannot be copied: return a value of a non-recursive type
```

Fix: return the data the caller needs (a slice of names instead of a linked list, a name
instead of a handler), and build the rest after the block.

### E320 KEEP_TYPE

`keep(x)` copies a value into the long-lived heap, following every reference in it; a type
that contains itself through references would need a copy without end.

```tin edition=1
package main

type Node struct {
	next ?Node
}

mut head ?Node = nil

fn main() {
	let n = Node{next: nil}
	head = keep(n)
}
```

```text
example.tin:0:0: error E320 KEEP_TYPE: keep cannot copy the recursive type Node
example.tin:0:0: error E320 KEEP_TYPE: keep cannot copy the recursive type ?Node
```

Fix: keep a flat value instead (an index into a kept slice, or the fields you need), or
build the structure in long-lived memory from kept parts.

## E4xx Faults and optionals

### E401 CATCH_PLACEMENT

`catch` handles the fault of a whole statement, initializer, assignment or return value,
not of a call in the middle of an expression.

```tin edition=1
package main

import "mint"
import "say"

fn main() {
	say.Line(1 + (mint.Atoi("2") catch _ { 0 }))
}
```

```text
example.tin:7:31: error E401 CATCH_PLACEMENT: catch goes on a whole statement, initializer, assignment or return value, not inside an expression
```

Fix: give the call its own statement (`let n = mint.Atoi("2") catch _ { 0 }`) and use the result.

### E402 FAULT_RESULT

A function that can fail says so in its result: `!T` (or `!(A, B)`, or `!` for no value),
not a `fault` in the result list.

```tin edition=1
package main

fn parse() (i64, fault) {
	return 1, nil
}

fn main() {
}
```

```text
example.tin:3:1: error E402 FAULT_RESULT: write a result that can fail as !T (or ! when there is no value), not with a fault result
```

Fix: write `fn parse() !i64`, `return v` on success and `fail "msg"` on failure.

### E403 TRY_PLACEMENT

`try` passes a fault upward from a whole statement, initializer, assignment or return
value, not from the middle of an expression.

```tin edition=1
package main

import "mint"

fn double(s str) !i64 {
	return 2 * try mint.Atoi(s)
}

fn main() {
}
```

```text
example.tin:6:13: error E403 TRY_PLACEMENT: try is only allowed as a statement, an initializer, an assignment or a return
```

Fix: give the call its own line (`let n = try mint.Atoi(s)`), then use `n`.

### E410 UNCHECKED_FAULT

A fault is never dropped: each call that can fail is checked (`try`, `catch` or `let (v, err) =`
and a test of `err`), a fault variable is read, and `_` cannot discard one.

```tin edition=1
package main

import "mint"

fn main() {
	mint.Atoi("12")
}
```

```text
example.tin:6:6: error E410 UNCHECKED_FAULT: the fault this call returns is ignored (check it, or use try)
```

Fix: pass it upward with `try`, handle it with `catch`, or test the `err` you assign.

### E411 NO_FAULT_RESULT

`try`, `fail` and `use` can leave the function with a fault, so the function's result says
it can fail (`!T`).

```tin edition=1
package main

import "mint"

fn count(s str) i64 {
	return try mint.Atoi(s)
}

fn main() {
}
```

```text
example.tin:6:2: error E411 NO_FAULT_RESULT: try needs the enclosing function to return a fault (write its result as !T)
```

Fix: declare the result as `!i64` (and its callers check it), or handle the fault in place
with `catch`.

### E412 RETURN_FAULT

In a function returning `!T`, `return` gives only the values; a fault leaves through `fail`.

```tin edition=1
package main

fn load() !i64 {
	return 1, nil
}

fn main() {
}
```

```text
example.tin:4:2: error E412 RETURN_FAULT: a !T function returns only its values: use fail to return a fault
```

Fix: write `return 1`, and `fail err` where the function fails.

### E413 WRAP

`try E wrap "msg"` adds context to the fault `try` passes upward, so `wrap` goes with a
`try`, and its message is a `str`.

```tin edition=1
package main

import "mint"

fn readCount(s str) !i64 {
	return mint.Atoi(s) wrap "reading the count"
}

fn main() {
}
```

```text
example.tin:6:22: error E413 WRAP: wrap adds context to the fault try passes upward: write try E wrap "msg"
```

Fix: pass the fault upward with `try`: `try mint.Atoi(s) wrap "reading the count"`.

### E414 NOT_FALLIBLE

`try` and `catch` handle the fault of a call that can fail (one returning `!T`); a call
that cannot fail needs neither.

```tin edition=1
package main

fn two() i64 {
	return 2
}

fn twice() i64 {
	return two() catch _ { 0 }
}

fn main() {
}
```

```text
example.tin:8:2: error E414 NOT_FALLIBLE: catch needs a call whose result can be a fault (!T)
```

Fix: remove the `try` or `catch`.

### E415 CATCH_VALUE

A `catch` block that gives the value of a call ends with that value, or leaves (`return`,
`break`, `continue` or `fail`); when the call gives several values, the block leaves.

```tin edition=1
package main

import "mint"
import "say"

fn main() {
	let n = mint.Atoi("x") catch _ {
		say.Line("not a number")
	}
	say.Line(n)
}
```

```text
example.tin:8:6: error E415 CATCH_VALUE: a catch block must end with the value to use, or leave (return, break, continue or fail)
```

Fix: end the block with the value to use (`0`), or leave from it.

### E416 FAIL_VALUE

`fail` takes a `str` message or a fault.

```tin edition=1
package main

fn check(n i64) ! {
	if n < 0 {
		fail n
	}
}

fn main() {
}
```

```text
example.tin:5:3: error E416 FAIL_VALUE: fail needs a str message or a fault, not i64
```

Fix: `fail "negative count"`, or `fail say.Fault("bad count %d", n)`.

### E417 SENTINEL

`fault("msg")` declares a sentinel fault that callers compare against: it is written at
package level, as `let ErrX = fault("msg")`, with a `str` message.

```tin edition=1
package main

fn find() ! {
	fail fault("not found")
}

fn main() {
}
```

```text
example.tin:4:7: error E417 SENTINEL: fault("...") declares a sentinel: write it at package level as var ErrX = fault("msg"), or use fail("msg") for a one-off fault
```

Fix: declare `let ErrNotFound = fault("not found")` and `fail ErrNotFound`, or use
`fail "not found"` for a one-off fault.

### E420 OPTIONAL_TYPE

Only numbers, `bool` and references can be optional (`?T`): `?i64`, `?f64`, `?bool`, `?str`,
slices, maps, structs, enums and `dyn` values. A function or a fault already has `nil` of its
own and cannot be wrapped.

```tin edition=1
package main

fn show(f ?fn()) {
}

fn main() {
}
```

```text
example.tin:3:11: error E420 OPTIONAL_TYPE: only numbers, bool and references (str, slices, maps, structs, dyn) can be optional, not func()
```

Fix: use the function or fault itself (`nil` is its missing value), or keep it in a struct and
make the struct optional.

### E421 UNCHECKED_OPTIONAL

An optional (`?T`) may be nil, so its fields and methods are used only after a check
against nil narrows it.

```tin edition=1
package main

type User struct {
	Name str
}

fn show(u ?User) {
	_ = u.Name
}

fn main() {
}
```

```text
example.tin:8:7: error E421 UNCHECKED_OPTIONAL: cannot use a field of optional ?User before checking it against nil
```

Fix: check it first: `if u != nil { return u.Name }`.

## E5xx Generics, shapes and dyn

### E501 NOT_GENERIC

Type arguments go only to a type, function or shape that declares type parameters.

```tin edition=1
package main

type Point struct {
	x i64
}

fn show(p Point[i64]) {
}

fn main() {
}
```

```text
example.tin:7:11: error E501 NOT_GENERIC: 'Point' is not a generic type
```

Fix: remove the type arguments (`p Point`), or give the declaration type parameters
(`type Point[T constraints.Any] struct { x T }`).

### E502 TYPE_ARG_COUNT

A generic type, function or shape gets one type argument per type parameter. A generic
shape named without its type arguments is the same error (`shape Getter needs type
arguments, like Getter[...]`).

```tin edition=1
package main

import "constraints"

type Pair[K constraints.Any, V constraints.Any] struct {
	key K
	value V
}

fn show(p Pair[str]) {
}

fn main() {
}
```

```text
example.tin:10:11: error E502 TYPE_ARG_COUNT: wrong number of type arguments for 'Pair'
```

Fix: give one type argument per parameter (`Pair[str, i64]`).

### E503 ENDLESS_INSTANTIATION

Generics are fully specialized, so a generic function that calls itself with a type built
from its own type parameter (`F[[]T]` inside `F[T]`) would need an endless series of
instances. Calling itself with the same type arguments is fine.

```tin edition=1
package main

import "constraints"

fn Wrap[T constraints.Any](x T) i64 {
	return Wrap([]T{x})
}

fn main() {
	_ = Wrap(1)
}
```

```text
example.tin:6:9: error E503 ENDLESS_INSTANTIATION: instantiating 'Wrap' does not end: it is instantiated with ever deeper type arguments (a generic function calling itself with a type built from its type parameter, such as F[[]T] inside F[T])
```

Fix: recurse with the same type arguments, or move the varying part into a value (a depth
counter, a slice) instead of a type.

### E504 CANNOT_INFER

Every type parameter must be inferable from the arguments, or given explicitly.

```tin edition=1
package main

import "constraints"

fn empty[T constraints.Any]() []T {
	return make([]T, 0)
}

fn main() {
	_ = empty()
}
```

```text
example.tin:10:6: error E504 CANNOT_INFER: cannot infer type parameter 'T' (give it explicitly: F[T](...))
```

Fix: write the type arguments (`Zero[i64]()`), or pass an argument whose type names them.

### E505 NOT_A_TYPE_ARG

The brackets after a generic function's name hold types.

```tin edition=1
package main

import "constraints"

fn Zero[T constraints.Any]() T {
	mut z T
	return z
}

fn main() {
	_ = Zero[1 + 2]()
}
```

```text
example.tin:11:13: error E505 NOT_A_TYPE_ARG: expected a type argument
```

Fix: put a type in the brackets (`Zero[i64]()`), and pass values in the parentheses.

### E506 RECEIVER_TYPE_PARAMS

A method of a generic type names the type's parameters in its receiver, one plain name each:
`fn (s mut Stack[T]) Push(x T)`. A method cannot be specialized for one type argument.

```tin edition=1
package main

import "constraints"

type Stack[T constraints.Any] struct {
	items []T
}

fn (s mut Stack[[]T]) Push(x T) {
}

fn main() {
}
```

```text
example.tin:9:1: error E506 RECEIVER_TYPE_PARAMS: a method's receiver lists its type's parameters by name, like (s Stack[T])
```

Fix: write the parameters by name (`Stack[T]`), or make the method a generic function.

### E510 NOT_IN_UNION

A type argument must be one of the types its union constraint lists, whether the union is
written in place (`[T i64 | f64]`) or named (`shape Number = i64 | f64`, printed as `type str
is not in shape Number: want one of i64 | f64`).

```tin edition=1
package main

fn Clamp[T i64 | f64](x T, hi T) T {
	if x > hi {
		return hi
	}
	return x
}

fn main() {
	_ = Clamp("b", "a")
}
```

```text
example.tin:11:6: error E510 NOT_IN_UNION: type str does not satisfy the constraint of T
```

Fix: pass values of a listed type (convert them: `f64(n)`), or add the type to the union.

### E511 NOT_COMPARABLE

A type argument for `constraints.Comparable` must compare by value with `==`: numbers,
`str`, `bool`, and structs and enums of those. Slices, maps and functions do not.

```tin edition=1
package main

import "constraints"

fn Equal[T constraints.Comparable](a T, b T) bool {
	return a == b
}

fn main() {
	let xs = []i64{1}
	_ = Equal(xs, xs)
}
```

```text
example.tin:11:6: error E511 NOT_COMPARABLE: type []i64 does not satisfy shape Comparable: it is not comparable
```

Fix: compare a comparable key instead (an id, a `str`), or write a function that compares
the elements.

### E512 MISSING_METHOD

A type satisfies a shape only when it has every method the shape lists.

```tin edition=1
package main

shape Reader { Read(buf mut []u8) !i64 }

type Empty struct { n i64 }

fn Use[R Reader](r R) i64 {
	return 0
}

fn main() {
	_ = Use(Empty{n: 1})
}
```

```text
example.tin:12:6: error E512 MISSING_METHOD: type Empty does not satisfy shape Reader: it has no method Read(buf mut []u8) !i64; fix-it: add method Read(buf mut []u8) !i64
```

Fix: add the method with the signature the message gives, or pass a type that has it.

### E513 METHOD_SIGNATURE

A method satisfies a shape only with exactly the shape's signature: the same parameter
types, the same `mut` parameters and the same results, including `!`.

```tin edition=1
package main

shape Reader { Read(buf mut []u8) !i64 }

type Odd struct { n i64 }

fn (o Odd) Read(buf []u8) i64 {
	return 0
}

fn Use[R Reader](r R) i64 {
	return 0
}

fn main() {
	_ = Use(Odd{n: 1})
}
```

```text
example.tin:16:6: error E513 METHOD_SIGNATURE: type Odd does not satisfy shape Reader: method Read(buf []u8) i64 has the wrong signature, want Read(buf mut []u8) !i64; fix-it: change the method signature to Read(buf mut []u8) !i64
```

Fix: change the method to the signature the message gives.

### E514 DYN_WIDENING

A `dyn S` value satisfies its own shape `S` (and `constraints.Any`) only: there is no
conversion from one `dyn` shape to another, and no downcast to the concrete type.

```tin edition=1
package main

import "io"

type Buf struct { n i64 }

fn (b Buf) Write(data []u8) !i64 {
	return len(data)
}

fn Drain[R io.Reader](r R) i64 {
	return 0
}

fn main() {
	let w dyn io.Writer = Buf{n: 1}
	_ = Drain(w)
}
```

```text
example.tin:17:6: error E514 DYN_WIDENING: a dyn value satisfies its own shape only; dyn-to-dyn widening is the next step (#141)
```

Fix: pass the concrete value, or convert the concrete value to the `dyn` shape you need.

### E515 DYN_PARAM_NAME

A parameter has a name and a type, also when the type is `dyn S`.

```tin edition=1
package main

import "io"

fn Send(dyn io.Writer) i64 {
	return 0
}

fn main() {
}
```

```text
example.tin:5:9: error E515 DYN_PARAM_NAME: a parameter of type dyn S needs a name: write w dyn S
```

Fix: name the parameter: `fn Send(w dyn io.Writer)`.

### E516 DYN_OBJECT

A `dyn S` value holds a struct or enum value together with its method table; numbers,
strings and other types are not objects.

```tin edition=1
package main

shape Sized { Size() i64 }

fn main() {
	let s dyn Sized = 3
	_ = s
}
```

```text
example.tin:6:20: error E516 DYN_OBJECT: only a struct or enum can be a dyn object, not untyped int
```

Fix: wrap the value in a struct that has the shape's methods.

### E520 DYN_CONSTRAINT

A constraint names a shape; `dyn S` is a value type, not a constraint.

```tin edition=1
package main

import "io"

type Buf struct { n i64 }

fn (b Buf) Write(data []u8) !i64 {
	return len(data)
}

fn Send[W dyn io.Writer](w W) i64 {
	return 0
}

fn main() {
	_ = Send(Buf{n: 1})
}
```

```text
example.tin:11:11: error E520 DYN_CONSTRAINT: a dyn type is not a constraint: name the shape
```

Fix: write the shape as the constraint (`[W io.Writer]`), or drop the type parameter and
take a `dyn io.Writer` value.

### E521 SHAPE_IN_UNION

A union, named or written in a constraint, lists concrete types. A shape stands alone as a
constraint, or is listed in a shape body.

```tin edition=1
package main

shape Reader { Read(buf mut []u8) !i64 }

shape Input = str | Reader

fn main() {
}
```

```text
example.tin:5:21: error E521 SHAPE_IN_UNION: a named union lists concrete types, but 'Reader' is a shape: list shapes in a shape body instead
```

Fix: list only concrete types in the union; to combine shapes, list them in a shape body
(`shape ReadCloser { Reader; Closer }`).

### E522 NOT_A_SHAPE

A shape body lists methods and other shapes by name; anything else is an error.

```tin edition=1
package main

type Sink struct { n i64 }

shape Writer { Sink }

fn main() {
}
```

```text
example.tin:5:16: error E522 NOT_A_SHAPE: shape Writer lists Sink, which is not a shape
```

Fix: list the methods you need (`Write(data []u8) !i64`), or a shape that declares them.

### E523 SHAPE_CYCLE

A shape cannot be composed of itself, directly or through the shapes it lists.

```tin edition=1
package main

shape A { B }

shape B { A }

fn main() {
}
```

```text
example.tin:3:1: error E523 SHAPE_CYCLE: shape 'A' is composed of itself (directly or through other shapes)
```

Fix: remove one of the listings, and declare the methods directly where they belong.

### E524 SHAPE_METHOD_TWICE

A shape declares each method name once, even with the same signature.

```tin edition=1
package main

shape Sizer {
	Size() i64
	Size() i64
}

fn main() {
}
```

```text
example.tin:5:2: error E524 SHAPE_METHOD_TWICE: shape Sizer declares Size twice
```

Fix: remove the second declaration.

### E525 SHAPE_METHOD_CONFLICT

When a shape lists other shapes, each method name must keep one signature across all of
them and the shape's own methods.

```tin edition=1
package main

shape Counter {
	Len() i64
}

shape Named {
	Len() str
}

shape Both {
	Counter
	Named
}

fn main() {
}
```

```text
example.tin:8:2: error E525 SHAPE_METHOD_CONFLICT: shape Both has two methods named Len with different signatures (one from a listed shape)
```

Fix: rename one of the methods, or make the signatures the same.

### E530 DYN_NOT_YET

Some uses of `dyn` are planned but not built yet (#141): a `dyn` value in a map, a `!dyn`
result, and formatting a `dyn` value.

```tin edition=1
package main

shape Sized { Size() i64 }

fn main() {
	let m = map[str]dyn Sized{}
	_ = len(m)
}
```

```text
example.tin:6:10: error E530 DYN_NOT_YET: a map value of type dyn is the next step: the map stores 16-byte slots with the table (#141)
```

Fix: keep the values in a `[]dyn S` and map the keys to indexes, or use the concrete type
until the feature lands.

## E6xx Concurrency, boundaries and lifecycle

### E601 SHARED_GLOBAL

Globals are per core: each core thread has its own copy. A `shared mut` variable, which every
core would see and change, is limited to the runtime's own state in the standard library. A
value that every core only reads is a `shared let` (below).

```tin edition=1
package main

shared mut hits i64 = 0

fn main() {
}
```

```text
example.tin:3:12: error E601 SHARED_GLOBAL: shared mutable state across cores is not allowed: globals are per core (use const, `shared let` for a value built once and only read, or relay messages)
```

Fix: use a per-core global (`mut hits i64`), a `const`, a `shared let` holding an
`atomic.Int` for a counter every core bumps, or send the data to the core that owns it with
`relay`.

### E602 GO

There is no `go` statement: work runs per core (`hearth`), cores talk through `relay`, and
a request's own concurrent work runs in a `scope` (edition 1).

No example: `go` is edition 0 syntax, which is retired (#226); edition 1 reports E090
OLD_SYNTAX for it and runs concurrent work in a `scope` or with `detach`.

Fix: spawn the work as a child of a scope, or run it per core with `hearth`.

### E603 SHARED_LET_WRITE

A `shared let` is built once, before the cores start, and read by every core, so nothing may
change it afterwards: not assigning it, not storing into its elements, fields or entries,
not `append`, `delete` or `copy` into it, not passing it as a `mut` argument.

```tin edition=1
package main

shared let table = []i64{1, 2, 3}

fn main() {
	table[0] = 9
}
```

```text
example.tin:6:7: error E603 SHARED_LET_WRITE: cannot modify shared let 'table': every core reads it; build a changed copy in a local value instead
```

Fix: copy what you need into a local value and change that, keep a per-core copy in a
`mut` global, or use an `atomic.Int` or `atomic.Bool` for a counter or flag every core
changes.

### E604 SHARED_LET_TYPE

A `shared let` holds plain data that any core can read: numbers, `bool`, `str`, slices, maps,
structs, enums and optionals of them. Functions, `dyn` values, faults and task handles belong
to one core or one scope.

```tin edition=1
package main

shared let handler = fn(x i64) i64 {
	return x + 1
}

fn main() {
	_ = handler(1)
}
```

```text
example.tin:3:12: error E604 SHARED_LET_TYPE: a shared let cannot hold func(i64) i64: every core reads it, so it holds plain data (numbers, str, slices, maps, structs, enums)
```

Fix: declare the function with `fn` (functions are code, not values to share) or keep the
value in a per-core global.

### E610 UNKNOWN_EVENT

`on` runs a block at a lifecycle event: `app.start`, `app.stop`, `core.start`, `core.stop`,
`server.overload` or `server.recovered`.

```tin edition=1
package main

on app.begin {
}

fn main() {
}
```

```text
example.tin:3:7: error E610 UNKNOWN_EVENT: unknown event: on takes app.start, app.stop, core.start, core.stop, server.overload or server.recovered
```

Fix: use one of the listed events.

### E620 USE_RESOURCE

`use x = f()` opens a resource and closes it when the scope ends: `f` can fail (returns
`!T`), and `T` has a method `Close() !`.

```tin edition=1
package main

type Conn struct {
	n i64
}

fn connect() !Conn {
	return Conn{n: 1}
}

fn work() ! {
	use c = connect()
	_ = c
}

fn main() {
}
```

```text
example.tin:12:2: error E620 USE_RESOURCE: use needs a resource: Conn has no method Close() !
```

Fix: give the type a `Close() !` method, or open it with a plain `let` when there is
nothing to close.

### E621 USE_PLACEMENT

A `use` closes its resource when the function returns, so it is not written in a loop,
where it would close only once.

```tin edition=1
package main

type Conn struct {
	n i64
}

fn (c Conn) Close() ! {
}

fn connect() !Conn {
	return Conn{n: 1}
}

fn work() ! {
	for i in 0..3 {
		use c = connect()
	}
}

fn main() {
}
```

```text
example.tin:16:3: error E621 USE_PLACEMENT: use inside a loop would close once per function, not per iteration: move the loop body into a function
```

Fix: move the loop body into a function that has the `use`.

### E630 SELECT_ARM

An arm of `select` waits on `l.Recv()` (a lane), `t.wait()` (a task), `after(d)` or
`canceled()`; `after` and `canceled` give no value to bind.

```tin edition=1
package main

fn first() !str {
	select {
		let x = after(30ms) => return "late"
	}
	return "none"
}

fn main() {
}
```

```text
example.tin:5:3: error E630 SELECT_ARM: after(d) and canceled() give no value to bind
```

Fix: write `after(30ms) => ...` without a name.

### E640 SCOPE_ESCAPE

A scope and the task handles it gives (`spawned`) live only as long as the scope block, so
they stay in local variables and parameters: no globals, fields, results, kept closures or
detached tasks.

```tin edition=1
package main

import "tide"

fn work() ! {
	try tide.Wait(tide.Millisecond)
}

fn give(s scope) spawned {
	return s.spawn(work)
}

fn main() {
}
```

```text
example.tin:9:1: error E640 SCOPE_ESCAPE: a function cannot return a task handle (spawned): it must not outlive its scope block, so it lives only in local variables and parameters
```

Fix: wait for the task inside the scope block, and return its value rather than its handle.

### E641 SLICE_ALIAS

A slice is a reference: after `mut ys = xs` the two names are one slice, and `append` to
either grows both. Reading the other name after the append is almost always a mistake
(a "snapshot" that changed), so user code may not.

```tin edition=1
package main

import "say"

fn main() {
	mut xs = []i64{1, 2, 3}
	mut ys = xs
	xs = append(xs, 4)
	say.Line(len(ys))
}
```

```text
example.tin:9:15: error E641 SLICE_ALIAS: 'ys' is the same slice as 'xs', which append has grown since: 'ys' changed too; copy the slice (sift.Clone) when two independent slices are meant
```

Fix: take a copy for the snapshot (`mut ys = sift.Clone(xs)`), or stop using the old name.
The check follows plain names inside one function: a slice reached through a field, a
parameter's other callers or a closure is not tracked.

### E650 BOUNDARY

A boundary block (`within`, `limit`, `guard`) gives its value with its last expression and
leaves early only with `fail`; `limit` bounds `memory` and `tasks`.

```tin edition=1
package main

fn work() ! {
	try limit cpu 2 {
	}
}

fn main() {
}
```

```text
example.tin:4:6: error E650 BOUNDARY: limit bounds are memory and tasks, not 'cpu'
```

Fix: bound `memory` and `tasks` only (`limit memory 4mb, tasks 8 { ... }`); end a block
with its value, and leave it early only with `fail`.

### E651 PARALLEL

`parallel { ... }` runs two or more lines as child tasks, and each line is an expression
that gives one value.

```tin edition=1
package main

fn one() !i64 {
	return 1
}

fn work() ! {
	parallel {
		one()
		let n = 2
	}
}

fn main() {
}
```

```text
example.tin:10:3: error E651 PARALLEL: each line of parallel is an expression that runs as a child task
```

Fix: make each line an expression (a call, or a value), with at least two lines; compute
other values before the block.

### E652 POLICY

`with p { ... }` runs the block through a policy: a value of a concrete type with a method
`Run(body fn() !T) !T`, whose body gives what the block gives.

```tin edition=1
package main

import "say"

type Plain struct {
	n i64
}

fn work() ! {
	let p = Plain{n: 1}
	try with p {
		say.Line("work")
	}
}

fn main() {
}
```

```text
example.tin:11:11: error E652 POLICY: Plain is not a policy: with needs a value with a method Run(body func() !T) !T
```

Fix: use a policy from the `policy` package (`policy.Retry(3)`), or give the type the `Run`
method.

### E653 POLICY_BODY

A policy's `Run` may only call its `body`, or pass it to a function that only calls it:
the block's variables live on the caller's frame, so a body kept for later would outlive
them.

```tin edition=1
package main

import "say"

type Saver struct {
	saved []fn() !i64
}

fn (s mut Saver) Run(body fn() !i64) !i64 {
	s.saved = append(s.saved, body)
	return try body()
}

fn main() {
	mut s = Saver{saved: []fn() !i64{}}
	let a = with s {
		1
	} catch _ {
		0
	}
	say.Line(a)
}
```

```text
example.tin:10:28: error E653 POLICY_BODY: Saver.Run keeps the body of a with block: a policy may only call body, or pass it to a function that only calls it (the block's variables live on the caller's frame)
```

Fix: call `body()` inside `Run` (as often as the policy needs) and keep only its results.

## E7xx mut parameters

### E701 NOT_MUT

Parameters are read-only unless declared `mut`: changing a parameter's fields, elements or
map entries, or appending to it, needs `mut` on the parameter (and at the call).

```tin edition=1
package main

type Box struct {
	Items []str
}

fn add(b Box, s str) {
	b.Items = append(b.Items, s)
}

fn main() {
	add(Box{}, "x")
}
```

```text
example.tin:8:12: error E701 NOT_MUT: cannot modify parameter 'b': declare it mut
```

Fix: declare the parameter `mut` (`fn add(b mut Box, s str)`) and call it with `add(mut box, s)`, or
return the new value instead.

### E702 MUT_VALUE_PARAM

A `mut` parameter lets a function change what the caller passed, which works for structs,
slices and maps (references). A number, `bool` or `str` is passed by value, so `mut` on it
could not reach the caller.

```tin edition=1
package main

fn bump(n mut i64) {
	n = n + 1
}

fn main() {
}
```

```text
example.tin:3:1: error E702 MUT_VALUE_PARAM: parameter 'n' is mut, but a value of type i64 is passed by value: only structs, slices and maps can be modified through a parameter, so remove mut
```

Fix: return the new value (`fn bump(n i64) i64`), or keep the number in a struct and pass
the struct `mut`.

### E703 CAPTURE_MUT

A function literal cannot capture a `mut` parameter: it could outlive the call and modify
the caller's value later.

```tin edition=1
package main

fn fill(xs mut []i64) {
	let add = fn(v i64) {
		xs = append(xs, v)
	}
	add(1)
}

fn main() {
}
```

```text
example.tin:4:12: error E703 CAPTURE_MUT: a function literal cannot capture the mut parameter 'xs': copy it into a local first, or pass it as an argument
```

Fix: copy it into a local first, or pass it to the literal as an argument.

### E704 MUT_PARAM_REBIND

Assigning a whole new value to a `mut` parameter rebinds only this function's copy, and the
caller would not see it; a `mut` parameter is changed through its fields and elements.

```tin edition=1
package main

type Box struct {
	n i64
}

fn reset(b mut Box) {
	b = Box{n: 0}
}

fn main() {
}
```

```text
example.tin:8:2: error E704 MUT_PARAM_REBIND: cannot assign to mut parameter 'b': it would rebind only this function's copy, and the caller would not see it; modify its fields or elements, or return the new value
```

Fix: change the fields (`b.n = 0`), or return the new value.

A `mut` slice parameter is the same: only `p = append(p, ...)` reaches the caller, because
append grows the shared header in place. A reslice (`p = p[2:]`), another slice, or an append
to anything but `p` itself makes a new header that only this function would see, so
`fn drop2(p mut []u8) { p = p[2:] }` reports E704 too. Fix: return the new slice
(`fn drop2(p []u8) []u8 { return p[2:] }`, called as `a = drop2(a)`), or keep an offset beside it.

### E705 MUT_ARG

A call writes `mut` before an argument exactly when the parameter is `mut`, so every
change a function can make to its arguments shows at the call.

```tin edition=1
package main

fn add(xs mut []i64, v i64) {
	xs = append(xs, v)
}

fn main() {
	mut xs = []i64{}
	add(xs, 1)
}
```

```text
example.tin:9:6: error E705 MUT_ARG: argument 1 of add is a mut parameter: write mut before the argument
```

Fix: write `add(mut xs, 1)`; remove `mut` before an argument whose parameter is not `mut`.

### E710 NOT_ASSIGNABLE

An assignment's target is a variable, a field, or an element of a slice, array or map;
constants, functions and the bytes of a `str` cannot be assigned.

```tin edition=1
package main

const maxSize = 10

fn main() {
	maxSize = 20
}
```

```text
example.tin:6:2: error E710 NOT_ASSIGNABLE: cannot assign to constant 'maxSize'
```

Fix: use a variable for a value that changes; build a new `str` instead of changing one.

### E711 LET_ASSIGN

A name declared with `let` is not reassigned: a local, a tuple binding `let (a, b) = f()`, a
variable a closure captured, or a package-level `let`; nor is a loop's variable (`for i in
0..n`, `for x in xs`), which the loop sets. Fields, elements and map entries reached through it
can still change.

```tin edition=1
package main

import "say"

fn main() {
	let total = 0
	for i in 0..3 {
		total += i
	}
	say.Line(total)
}
```

```text
example.tin:8:3: error E711 LET_ASSIGN: cannot assign to total: it is declared with let, which is not reassigned (declare it with mut to change it; declared at example.tin:6:2)
```

Fix: declare it with `mut` (`mut total = 0`); `tin fix -edition 1 FILE.tin` makes that change
for every `let` the program reassigns. For a loop's variable, change a `mut` copy, or count
with `for cond { }` and a `mut` counter.

## E8xx Trusted code

### E801 TRUSTED_ONLY

`extern` declarations, raw memory access and the runtime's internals are only allowed in
the standard library (the library (`toolchain/std/`, `packages/`, `toolchain/runtime/`)), which is trusted code.

```tin edition=1 old-syntax
package main

extern fn getpid() i64

fn main() {
}
```

```text
example.tin:3:8: error E801 TRUSTED_ONLY: extern is only allowed in the standard library
```

Fix: use the standard library package that wraps the call (`quarry` for the process and
files).

### E802 RUNTIME_INTERNAL

The runtime's own functions (`rt_...`, `memset`, `cast`) are internal: programs and
packages use the standard library instead.

```tin edition=1
package main

fn main() {
	_ = rt_core_id()
}
```

```text
example.tin:4:6: error E802 RUNTIME_INTERNAL: 'rt_core_id' is internal to the runtime
```

Fix: use the standard library function that wraps it (`hearth.Core()` for the core). A
vendored package whose `tin.mod` declares `caps unsafe` may use them, like the library (`toolchain/std/`, `packages/`, `toolchain/runtime/`).

### E803 ADDRESS_OF

`&x` takes the address of a variable, in the standard library only: it needs a variable
name, not a constant or an expression.

```tin edition=1
package main

const size = 4

fn main() {
	_ = &size
}
```

```text
example.tin:6:6: error E803 ADDRESS_OF: cannot take the address of constant 'size'
```

Fix: programs pass structs, slices and maps by reference already; there is no `&` outside
the library (`toolchain/std/`, `packages/`, `toolchain/runtime/`).

### E804 CAPABILITY

A vendored package may only call code that stays within the capabilities its `tin.mod`
declares (`net`, `files`, `spawn`, `exec`, `unsafe`; toolchain/docs/PACKAGES.md). The standard
library's entry points to the operating system are tagged with the capability they need,
and the check follows calls and function values through every package, so calling
another package's function that dials needs `net` too. Every function of a vendored
package is checked, called or not. The error is at the call that leaves the package and
shows the path to the tagged entry point.

```text file=vendor/example.com/peek/tin.mod
module example.com/peek
```

```text file=vendor/example.com/peek/peek.tin
package peek

import "wire"

fn Up(addr str) bool {
	let c = wire.Dial(addr) catch _ {
		return false
	}
	c.Close()
	return true
}
```

```tin edition=1
package main

import "example.com/peek"
import "say"

fn main() {
	say.Line(peek.Up("127.0.0.1:1"))
}
```

```text
vendor/example.com/peek/peek.tin:6:14: error E804 CAPABILITY: wire.Dial needs capability net (wire.Dial -> wire.DialTimeout -> wire.resolve), which package example.com/peek does not declare in its tin.mod (caps: none)
```

Fix: if the dependency should dial, add `caps net` to its `tin.mod` (upstream) and run
`tin vendor`; the lock then shows the new capability for review. Otherwise do not use the
package. `tin caps main.tin` prints what each package can reach.

## E9xx Building

### E901 UNKNOWN_TARGET

`-target` takes one of the supported targets: `darwin-arm64`, `linux-arm64`, `linux-amd64`.

```sh
tinc -edition 1 -target windows-amd64 example.tin
```

```tin edition=1
package main

fn main() {
}
```

```text
error E901 UNKNOWN_TARGET: unknown target windows-amd64 (darwin-arm64, linux-arm64, linux-amd64)
```

Fix: use one of the listed targets (toolchain/docs/PORTING.md).

### E902 UNKNOWN_EDITION

`-edition` takes `0` (the syntax of toolchain/docs/LANGUAGE.md) or `1` (Tin 1's syntax).

```sh
tinc -edition 2 example.tin
```

```tin edition=1
package main

fn main() {
}
```

```text
error E902 UNKNOWN_EDITION: unknown edition 2 (expected 0 or 1)
```

Fix: pass `-edition 1`, or leave the flag out: each file is read in the edition it is written in.
Edition 0 is retired (#226); `tin fix -edition 1` translates it.

### E903 NO_RUNTIME

Every program is built with the runtime package, `toolchain/runtime` under the Tin root: `$TIN_ROOT`,
or the directory above the compiler's `bin/`.

```sh
TIN_ROOT=/nonexistent tinc -edition 1 example.tin
```

```tin edition=1
package main

fn main() {
}
```

```text
error E903 NO_RUNTIME: the runtime package is missing: no runtime in /nonexistent
```

Fix: set `TIN_ROOT` to the Tin checkout or installation, or run the compiler from its
installed `bin/` (the `tin` command sets `TIN_ROOT` itself).

### E904 CANNOT_CREATE

The compiler writes the executable to the `-o` path (`a.out` by default), so its directory
must exist and be writable.

```sh
tinc -edition 1 -o missing/example example.tin
```

```tin edition=1
package main

fn main() {
}
```

```text
error E904 CANNOT_CREATE: cannot create missing/example
```

Fix: create the directory first, or choose a writable path.

### E905 TOO_MANY_LOCALS

On arm64 a function's stack frame (its local variables, temporaries and saved registers) is
at most 4095 bytes, about 500 eight-byte locals.

No example: it takes a function with hundreds of local variables.

Fix: split the function, or keep the values in a slice or a struct instead of separate
locals.

### E906 FIX_USAGE

`tinc -fix` prints one file translated to edition 1 (`tin fix -edition 1 FILES...` runs it per
file), so it takes `-edition 1` and exactly one file.

```sh
tinc -fix example.tin
```

```tin
package main

fn main() {
}
```

```text
error E906 FIX_USAGE: -fix translates one file to edition 1: pass -edition 1 and exactly one file
```

Fix: use `tin fix -edition 1 FILES...`, or pass `-edition 1` and one file to `tinc -fix`.

### E907 TOO_MANY_PARAMS

A function takes at most 8 parameters of each register kind (integers and references, and
floats) and returns at most 8 results.

```tin edition=1
package main

fn sum(a i64, b i64, c i64, d i64, e i64, f i64, g i64, h i64, i i64) i64 {
	return a + b + c + d + e + f + g + h + i
}

fn main() {
}
```

```text
example.tin:3:1: error E907 TOO_MANY_PARAMS: function 'sum' has 9 parameters, the limit is 8
```

Fix: pass a struct (or a slice) that holds the values.

### E990 INTERNAL

The code generator, assembler or linker met a case it cannot handle: a `dyn` value or
argument in a place it cannot put it, an instruction it cannot encode, a branch out of range,
code that changed size between layout and encoding, a missing entry point, or a function
import in a Linux executable (which is static). Assembler and linker messages start with
`x64:` or `link:`.

No example: only a compiler bug reaches this error.

Fix: report it as a compiler bug with the smallest program that shows it; splitting a very
large function usually avoids a branch out of range in the meantime.
