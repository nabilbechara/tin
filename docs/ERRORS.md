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

Codes are being added one compiler file at a time (#244); until that is finished, some
errors still print as `error: message` without a code.

Each entry below gives the rule, a program that breaks it with the exact output the compiler
prints for it, and the fixes. `tools/ci/diagnostics_check.py` compiles every example and
requires that output, and checks that the compiler, this page and the tests' expected
diagnostics agree on every code and name. Examples use the syntax of LANGUAGE.md (edition 0)
and are compiled with `-edition 0`; an example opened with ```` ```tin edition=1 ```` is
edition 1 syntax and is compiled with `-edition 1`.

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

```tin
package main

func main() {
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

```tin
package main

func main() {
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

```tin
package main

import "say"

func main() {
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

```tin
package main

func main() {
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

```tin
package main

import "say"

func main() {
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

```tin
package main

import "say"

func main() {
	say.Line("total" 3)
}
```

```text
example.tin:6:19: error E020 UNEXPECTED: expected ')', found a number
```

Fix: add or remove what the message names. The cause is often just before the position: a
missing comma, operator, parenthesis or brace.

### E021 CONST_VALUES

A constant declaration gives every name a value: one value per name.

```tin
package main

const width, height = 640

func main() {
}
```

```text
example.tin:3:7: error E021 CONST_VALUES: constant declaration count mismatch
```

Fix: give one value per name (`const width, height = 640, 480`), or declare each constant on its
own.

### E030 INTERPOLATION

In a string, `{` starts a value that ends at the matching `}`, and one `{...}` holds one
value (with an optional format spec, `{price:.2}`). A literal brace is written `{{` or `}}`.

```tin
package main

import "say"

func main() {
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

```tin
package main

type User struct {
	ID i64 @jsonn("id")
}

func main() {
}
```

```text
example.tin:3:11: error E041 UNKNOWN_ATTRIBUTE: unknown struct attribute; supported attributes are @json("name")
```

Fix: correct the spelling (`@json("id")`), or remove the attribute.

### E042 ATTRIBUTE_ARGS

`@json` takes one string literal: the field's name in JSON.

```tin
package main

type User struct {
	ID i64 @json(1)
}

func main() {
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

```tin
package main

type Shape enum { Rect(w, h,), Empty }

func main() {
}
```

```text
example.tin:3:12: error E044 ENUM_FIELD_TYPES: an enum variant's fields need types: Variant(name Type, ...)
```

Fix: give the last field names their type: `Rect(w, h f64)`.

### E045 EMPTY_ENUM

An enum declares at least one variant.

```tin
package main

type Shape enum { }

func main() {
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
name and takes one step (`for i in (0..n).step(2)`).

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

```tin
package main

func main() {
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

```tin edition=1
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

```tin
package main

shape Reader { Read(buf mut []u8) !i64 }

shape Reader { Write(data []u8) !i64 }

func main() {
}
```

```text
example.tin:5:1: error E101 REDECLARED: 'Reader' is declared as a shape twice
```

Fix: rename one of the declarations, or merge them into one.

### E110 UNKNOWN_PACKAGE

An import path names a package in `vendor/`, in the standard library, or next to the
program's first file; a path starting with `./` names a package next to the importing file
(docs/PACKAGES.md).

```tin
package main

import "geom"

func main() {
}
```

```text
error E110 UNKNOWN_PACKAGE: unknown package "geom" (looked in the standard library, next to the importing file and in the program's directory)
```

Fix: correct the path; for a package in the program's own tree, write it relative to the
importing file (`import "./geom"`).

### E111 LOCK_MISMATCH

When the project directory has a `tin.lock`, every source file outside the standard library
must be listed in it with its SHA-256 hash (docs/PACKAGES.md), so changed or unexpected code
does not build.

```text file=tin.lock
0000000000000000000000000000000000000000000000000000000000000000 example.tin
```

```tin
package main

func main() {
}
```

```text
error E111 LOCK_MISMATCH: tin.lock hash mismatch or missing entry for example.tin
```

Fix: review the change, then regenerate the file's entry (`shasum -a 256 example.tin`).

## E2xx Types, expressions and calls

### E210 ARG_COUNT

A call passes exactly as many arguments as the function has parameters (a variadic
parameter takes the rest).

```tin
package main

func Max[T i64 | f64](a T, b T) T {
	if a > b {
		return a
	}
	return b
}

func main() {
	_ = Max(1, 2, 3)
}
```

```text
example.tin:11:6: error E210 ARG_COUNT: Max expects 2 arguments, got 3
```

Fix: pass one argument per parameter; to take any number of values, declare the last
parameter variadic (`xs ...T`) or pass a slice.

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

## E3xx Memory and regions

### E310 REQUEST_ESCAPE

Memory allocated during a request lives in the core's request pool, which is wiped when the
request ends. Storing it into a global, or into anything a global can reach, would leave a
dangling reference, so `keep(x)` must copy it into the long-lived heap first.

```tin
package main

import "say"

var last str

func remember(name str) {
	last = name
}

func main() {
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

```tin
package main

import "say"

func recorder() func(str) str {
	last := "nobody"
	return func(s str) str {
		prev := last
		last = s
		return prev
	}
}

var rec func(str) str = keep(recorder())

func main() {
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

```tin
package main

import "say"

type Box struct {
	Items []str
}

var box Box = Box{}

func put(b mut Box, s str) {
	b.Items = append(b.Items, s)
}

func main() {
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

```tin
package main

import "hearth"
import "say"

func main() {
	s := say.Fmt("fresh-%d", 1)
	hearth.Reset()
	say.Line(s)
}
```

```text
example.tin:9:11: error E313 USE_AFTER_RESET: 's' may hold request memory from before hearth.Reset(), which freed it, and is read after the reset: keep() the value before the reset, or create it after
```

Fix: `keep()` the value before the reset, or create it again after.

## E4xx Faults and optionals

### E401 CATCH_PLACEMENT

`catch` handles the fault of a whole statement, initializer, assignment or return value,
not of a call in the middle of an expression.

```tin
package main

import "mint"
import "say"

func main() {
	say.Line(1 + (mint.Atoi("2") catch _ { 0 }))
}
```

```text
example.tin:7:31: error E401 CATCH_PLACEMENT: catch goes on a whole statement, initializer, assignment or return value, not inside an expression
```

Fix: give the call its own statement (`let n = mint.Atoi("2") catch _ { 0 }`) and use the result.

## E5xx Generics, shapes and dyn

### E501 NOT_GENERIC

Type arguments go only to a type, function or shape that declares type parameters.

```tin
package main

type Point struct { x i64 }

func main() {
	var p Point[i64]
	_ = p
}
```

```text
example.tin:6:8: error E501 NOT_GENERIC: 'Point' is not a generic type
```

Fix: remove the type arguments (`var p Point`), or give the declaration type parameters
(`type Point[T constraints.Any] struct { x T }`).

### E502 TYPE_ARG_COUNT

A generic type, function or shape gets one type argument per type parameter. A generic
shape named without its type arguments is the same error (`shape Getter needs type
arguments, like Getter[...]`).

```tin
package main

import "constraints"

type Pair[K constraints.Any, V constraints.Any] struct {
	key K
	value V
}

func main() {
	var p Pair[str]
	_ = p
}
```

```text
example.tin:11:8: error E502 TYPE_ARG_COUNT: wrong number of type arguments for 'Pair'
```

Fix: give one type argument per parameter (`Pair[str, i64]`).

### E503 ENDLESS_INSTANTIATION

Generics are fully specialized, so a generic function that calls itself with a type built
from its own type parameter (`F[[]T]` inside `F[T]`) would need an endless series of
instances. Calling itself with the same type arguments is fine.

```tin
package main

import "constraints"

func Wrap[T constraints.Any](x T) i64 {
	return Wrap([]T{x})
}

func main() {
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

```tin
package main

import "constraints"

func Zero[T constraints.Any]() T {
	var z T
	return z
}

func main() {
	_ = Zero()
}
```

```text
example.tin:11:6: error E504 CANNOT_INFER: cannot infer type parameter 'T' (give it explicitly: F[T](...))
```

Fix: write the type arguments (`Zero[i64]()`), or pass an argument whose type names them.

### E505 NOT_A_TYPE_ARG

The brackets after a generic function's name hold types.

```tin
package main

import "constraints"

func Zero[T constraints.Any]() T {
	var z T
	return z
}

func main() {
	_ = Zero[1 + 2]()
}
```

```text
example.tin:11:13: error E505 NOT_A_TYPE_ARG: expected a type argument
```

Fix: put a type in the brackets (`Zero[i64]()`), and pass values in the parentheses.

### E506 RECEIVER_TYPE_PARAMS

A method of a generic type names the type's parameters in its receiver, one plain name each:
`func (s mut Stack[T]) Push(x T)`. A method cannot be specialized for one type argument.

```tin
package main

import "constraints"

type Stack[T constraints.Any] struct {
	items []T
}

func (s mut Stack[[]T]) Push(x T) {
}

func main() {
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

```tin
package main

func Clamp[T i64 | f64](x T, hi T) T {
	if x > hi {
		return hi
	}
	return x
}

func main() {
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

```tin
package main

import "constraints"

func Equal[T constraints.Comparable](a T, b T) bool {
	return a == b
}

func main() {
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

```tin
package main

shape Reader { Read(buf mut []u8) !i64 }

type Empty struct { n i64 }

func Use[R Reader](r R) i64 {
	return 0
}

func main() {
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

```tin
package main

shape Reader { Read(buf mut []u8) !i64 }

type Odd struct { n i64 }

func (o Odd) Read(buf []u8) i64 {
	return 0
}

func Use[R Reader](r R) i64 {
	return 0
}

func main() {
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

```tin
package main

import "io"

type Buf struct { n i64 }

func (b Buf) Write(data []u8) !i64 {
	return len(data)
}

func Drain[R io.Reader](r R) i64 {
	return 0
}

func main() {
	var w dyn io.Writer = Buf{n: 1}
	_ = Drain(w)
}
```

```text
example.tin:17:6: error E514 DYN_WIDENING: a dyn value satisfies its own shape only; dyn-to-dyn widening is the next step (#141)
```

Fix: pass the concrete value, or convert the concrete value to the `dyn` shape you need.

### E515 DYN_PARAM_NAME

A parameter has a name and a type, also when the type is `dyn S`.

```tin
package main

import "io"

func Send(dyn io.Writer) i64 {
	return 0
}

func main() {
}
```

```text
example.tin:5:11: error E515 DYN_PARAM_NAME: a parameter of type dyn S needs a name: write w dyn S
```

Fix: name the parameter: `func Send(w dyn io.Writer)`.

### E520 DYN_CONSTRAINT

A constraint names a shape; `dyn S` is a value type, not a constraint.

```tin
package main

import "io"

type Buf struct { n i64 }

func (b Buf) Write(data []u8) !i64 {
	return len(data)
}

func Send[W dyn io.Writer](w W) i64 {
	return 0
}

func main() {
	_ = Send(Buf{n: 1})
}
```

```text
example.tin:11:13: error E520 DYN_CONSTRAINT: a dyn type is not a constraint: name the shape
```

Fix: write the shape as the constraint (`[W io.Writer]`), or drop the type parameter and
take a `dyn io.Writer` value.

### E521 SHAPE_IN_UNION

A union, named or written in a constraint, lists concrete types. A shape stands alone as a
constraint, or is listed in a shape body.

```tin
package main

shape Reader { Read(buf mut []u8) !i64 }

shape Input = str | Reader

func main() {
}
```

```text
example.tin:5:21: error E521 SHAPE_IN_UNION: a named union lists concrete types, but 'Reader' is a shape: list shapes in a shape body instead
```

Fix: list only concrete types in the union; to combine shapes, list them in a shape body
(`shape ReadCloser { Reader; Closer }`).

### E522 NOT_A_SHAPE

A shape body lists methods and other shapes by name; anything else is an error.

```tin
package main

type Sink struct { n i64 }

shape Writer { Sink }

func main() {
}
```

```text
example.tin:5:16: error E522 NOT_A_SHAPE: shape Writer lists Sink, which is not a shape
```

Fix: list the methods you need (`Write(data []u8) !i64`), or a shape that declares them.

### E523 SHAPE_CYCLE

A shape cannot be composed of itself, directly or through the shapes it lists.

```tin
package main

shape A { B }

shape B { A }

func main() {
}
```

```text
example.tin:3:1: error E523 SHAPE_CYCLE: shape 'A' is composed of itself (directly or through other shapes)
```

Fix: remove one of the listings, and declare the methods directly where they belong.

### E524 SHAPE_METHOD_TWICE

A shape declares each method name once, even with the same signature.

```tin
package main

shape Sizer { Size() i64; Size() i64 }

func main() {
}
```

```text
example.tin:3:27: error E524 SHAPE_METHOD_TWICE: shape Sizer declares Size twice
```

Fix: remove the second declaration.

### E525 SHAPE_METHOD_CONFLICT

When a shape lists other shapes, each method name must keep one signature across all of
them and the shape's own methods.

```tin
package main

shape Counter { Len() i64 }
shape Named { Len() str }
shape Both { Counter; Named }

func main() {
}
```

```text
example.tin:4:15: error E525 SHAPE_METHOD_CONFLICT: shape Both has two methods named Len with different signatures (one from a listed shape)
```

Fix: rename one of the methods, or make the signatures the same.

## E7xx mut parameters

### E701 NOT_MUT

Parameters are read-only unless declared `mut`: changing a parameter's fields, elements or
map entries, or appending to it, needs `mut` on the parameter (and at the call).

```tin
package main

type Box struct {
	Items []str
}

func add(b Box, s str) {
	b.Items = append(b.Items, s)
}

func main() {
	add(Box{}, "x")
}
```

```text
example.tin:8:12: error E701 NOT_MUT: cannot modify parameter 'b': declare it mut
```

Fix: declare the parameter `mut` (`func add(b mut Box, s str)`) and call it with `add(mut box, s)`, or
return the new value instead.

## E9xx Building

### E901 UNKNOWN_TARGET

`-target` takes one of the supported targets: `darwin-arm64`, `linux-arm64`, `linux-amd64`.

```sh
tinc -target windows-amd64 example.tin
```

```tin
package main

func main() {
}
```

```text
error E901 UNKNOWN_TARGET: unknown target windows-amd64 (darwin-arm64, linux-arm64, linux-amd64)
```

Fix: use one of the listed targets (docs/PORTING.md).

### E902 UNKNOWN_EDITION

`-edition` takes `0` (the syntax of docs/LANGUAGE.md) or `1` (Tin 1's syntax).

```sh
tinc -edition 2 example.tin
```

```tin
package main

func main() {
}
```

```text
error E902 UNKNOWN_EDITION: unknown edition 2 (expected 0 or 1)
```

Fix: pass `-edition 0` or `-edition 1`, or leave the flag out for edition 0.

### E903 NO_RUNTIME

Every program is built with the runtime package, `lib/runtime` under the Tin root: `$TIN_ROOT`,
or the directory above the compiler's `bin/`.

```sh
TIN_ROOT=/nonexistent tinc example.tin
```

```tin
package main

func main() {
}
```

```text
error E903 NO_RUNTIME: the runtime package is missing: no lib/runtime in /nonexistent
```

Fix: set `TIN_ROOT` to the Tin checkout or installation, or run the compiler from its
installed `bin/` (the `tin` command sets `TIN_ROOT` itself).

### E904 CANNOT_CREATE

The compiler writes the executable to the `-o` path (`a.out` by default), so its directory
must exist and be writable.

```sh
tinc -o missing/example example.tin
```

```tin
package main

func main() {
}
```

```text
error E904 CANNOT_CREATE: cannot create missing/example
```

Fix: create the directory first, or choose a writable path.

### E990 INTERNAL

The assembler or linker met a case it cannot handle: an instruction it cannot encode, a
branch out of range, code that changed size between layout and encoding, or a missing entry
point. The message starts with `x64:` or `link:`.

No example: only a compiler bug reaches this error.

Fix: report it as a compiler bug with the smallest program that shows it; splitting a very
large function usually avoids a branch out of range in the meantime.
