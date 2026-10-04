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
diagnostics agree on every code and name.

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
