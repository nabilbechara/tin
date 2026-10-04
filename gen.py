#!/usr/bin/env python3
# Generates index.html and syntax.html for the Tin documentation site.
import html, os, re

HERE = os.path.dirname(os.path.abspath(__file__))

def code(src, lang="tin"):
    body = html.escape(src.strip("\n"))
    return f'<pre><code class="{lang}">{body}</code></pre>'

def inline(text):
    # `x` -> <code>x</code>, **x** -> <strong>x</strong>
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text

def rules(items):
    return '<ul class="rule">' + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>"

def table(head, rows):
    h = "".join(f"<th>{inline(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"

ARROW = '<span class="arrow"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 1.5 L6.5 5 L3 8.5"/></svg></span>'

def body(items):
    out = []
    for kind, val in items:
        if kind == "p": out.append(f"<p>{inline(val)}</p>")
        elif kind == "code": out.append(code(val))
        elif kind == "rules": out.append(rules(val))
        elif kind == "table": out.append(table(*val))
    return "".join(out)

def card(c):
    sig = f'<span class="sig">{html.escape(c["sig"])}</span>' if c.get("sig") else ""
    deeper = ""
    if c.get("deeper"):
        deeper = (f'<details class="deeper"><summary>{ARROW}Deeper</summary><div class="body">'
                  f'{body(c["deeper"])}</div></details>')
    return (f'<article class="card" id="{c["id"]}"><h3>{inline(c["title"])}{sig}</h3>'
            f'<p>{inline(c["text"])}</p>{code(c["code"]) if c.get("code") else ""}'
            f'{rules(c["rules"]) if c.get("rules") else ""}{body(c.get("extra", []))}{deeper}</article>')

# ---------------------------------------------------------------- content
S = []  # sections

S.append(dict(id="program", n="01", title="Programs and packages",
intro="A file belongs to a package. Programs start in `main`; libraries export by capitalization.",
cards=[
dict(id="package", title="package and import", sig="package NAME · import \"path\"",
text="Every file starts with `package`. Imports name a standard package, a local directory or a vendored path.",
code='''
package main

import "say"
import "anvil"
import "./geom"                 // a directory next to this file
import "github.com/ana/geo"     // vendored under vendor/

fn main() {
	say.Line("area", geom.Area(2, 3), geo.Version)
}
''',
rules=["`package main` is a program; any other name is a library used as `name.Func`.",
       "One import per line. A package is `lib/NAME.tin` or a directory of `.tin` files."],
deeper=[("p","Resolution order: `./` paths next to the file, dotted paths only under `vendor/`, then the standard library, then a package beside the program."),
        ("code",'''
// tin.mod next to your sources
module example.com/app
require github.com/ana/geo ../geo

// tin vendor copies it into vendor/ and writes tin.lock (content hashes)
'''),
        ("rules",["`tin vendor` rebuilds `vendor/` from scratch; commit `vendor/` and `tin.lock`.",
                  "Two paths loading different packages under one name is `E113 PACKAGE_CONFLICT`."])]),
dict(id="exports", title="Exports by capitalization", sig="Name vs name",
text="A capitalized name is exported from its package; a lower-case one is private. No `pub` keyword.",
code='''
package geom

type Point struct {      // exported type
	X i64                // exported field
	tag str              // private field
}

fn Area(w i64, h i64) i64 { return w * h }   // exported
fn clamp(v i64) i64 { return v }             // private
''',
rules=["The rule covers functions, types, methods and fields.", "Multi-word names are camelCase: `getUser`, `GetUser`."]),
dict(id="lines", title="Lines and comments", sig="// comment",
text="A statement ends at the newline. No semicolons, no block comments.",
code='''
// A comment above a declaration documents it.
fn total(xs []i64) i64 {
	mut sum = 0
	for x in xs {
		sum += x          // one statement per line
	}
	return sum +
		0                 // a line ending in an operator continues
}
''',
rules=["A line continues after an operator, `,`, `(`, `[` or `{`.", "Semicolons are an error (`E090 OLD_SYNTAX`)."]),
dict(id="main", title="Program start", sig="fn main()",
text="`main` takes no arguments and may be `!`: a fault from it ends the process with its message.",
code='''
fn main() ! {
	let r = anvil.NewRouter()
	r.Get(`/users/{id}`, user)
	try r.Serve(":8080")
}
''',
deeper=[("p","Order at startup: shared globals, core 0's globals and `use` resources, `on app.start`, `core.start`, then `main`. Other cores open their globals before any core serves."),
        ("rules",["Globals are per core and initialized on every core; a global **assigned in `main` is set on core 0 only**. Build per-core data in initializers, `once` or `on core.start`.",
                  "`quarry.Args()` and `quarry.Getenv(name)` read arguments and the environment."])]),
]))

S.append(dict(id="values", n="02", title="Literals and bindings",
intro="Numbers, units, strings and characters; `let` for names that stay, `mut` for names that change.",
cards=[
dict(id="numbers", title="Numbers", sig="42 · 0xff · 1_000 · 3.14 · 1e9",
text="Integer and float literals adapt to the type they meet and must fit it.",
code='''
let a = 42            // i64 when nothing else decides
let b u8 = 0xff
let c = 0b1010 + 0o17 + 1_000_000
let d = 3.14 * 2.5e3  // f64
let e u8 = 300        // compile error: does not fit
''',
rules=["Integer arithmetic wraps; division by zero panics; shifts count modulo 64.",
       "`i64(x)`, `u8(x)`, `f64(n)` convert explicitly. Nothing converts implicitly."]),
dict(id="units", title="Unit literals", sig="200ms · 5s · 64kb · 1mb",
text="A number followed by a unit is a typed constant: durations in nanoseconds, sizes in bytes.",
code='''
let timeout = 200ms        // Duration: 200 000 000 ns
let grace = 2.5s           // exact in ns, or a compile error
let buffer = 64kb          // Size: 65 536 bytes
within 5s { try fetch() }
limit memory 4mb { build() }
''',
extra=[("table",(["unit","type","value"],
    [["`ns` `us` `ms` `s` `m` `h`","`Duration` (i64 ns)","`1h` = 3 600 000 000 000"],
     ["`b` `kb` `mb` `gb`","`Size` (i64 bytes)","`kb` = 1024, `mb` = 1024²"]]))],
rules=["`Duration` and `Size` are distinct named types: `within 5mb` is a type error."]),
dict(id="strings-lit", title="Strings and characters", sig="\"text {value}\" · `raw` · 'a'",
text="Double quotes interpolate `{expr}` and take escapes. Backquotes are raw. A character is a `u8` when ASCII, a `rune` otherwise.",
code='''
let name = "ana"
let s = "hello {name}, {len(name)} bytes\\n"
let r = `raw text keeps {braces} and \\n`
let braces = "literal {{braces}} and 100%"
let a = 'a'          // u8
let e = 'é'          // rune (i32)
''',
rules=["Escapes: `\\n \\t \\r \\\\ \\\" \\0 \\xHH \\uHHHH`.", "`{{` and `}}` write braces; no `\"` inside `{...}`.", "A string never spans lines unless raw."],
deeper=[("p","A format spec after the last `:` uses printf flags, width, precision and verb."),
        ("code",'''
let row = "{price:.2} {id:x} [{name:-12}] [{n:05}]"
// 3.50 2a [ana         ] [00042]
fail "port {n} out of range"            // interpolation in faults too
say.Line(`route /users/{id}`)           // raw: braces are text
'''),
        ("rules",["Without a verb a value prints as `%v`; a precision on a float means decimal places.",
                  "Text with braces of its own (routes) is a raw string."])]),
dict(id="let", title="let and mut", sig="let x = e · mut y T = e",
text="`let` binds a name that cannot be reassigned. `mut` binds one that can. The type is inferred or written after the name.",
code='''
let n = 10
let zero i64 = 0
mut total = zero
total += n              // ok: mut
n = 3                   // compile error: let
let (a, b) = pair()     // a tuple result
mut (lo, hi) = bounds()
''',
rules=["Every variable is initialized; struct, map and `fn` values have no zero value and need one.",
       "`let` fixes the name, not the object: fields and elements may still change through it.",
       "`_` discards a value, never a fault."]),
dict(id="const", title="const", sig="const Name [T] = expr",
text="A compile-time constant. Untyped constants adapt where they are used.",
code='''
const MaxUsers = 1000
const Pi = 3.141592653589793
const Mask u8 = 0x0f
const Greeting = "tin"
''',
rules=["One constant per declaration (no `const (...)` groups, no `iota`).",
       "Constant expressions fold exactly in 64 bits."]),
dict(id="globals", title="Globals", sig="let · mut · shared let",
text="Package-level bindings are per core: every core thread has its own copy, initialized when the core starts.",
code='''
let defaultName = "anonymous"           // per core, set once
mut requests = 0                        // per core, changes
shared let limits = loadLimits()        // built before cores start, read by all
mut cache = map[str]User{}              // per-core cache
''',
rules=["An initializer may use earlier globals, never later ones.", "Values stored into globals live in long-lived memory: see keep."],
deeper=[("p","Per-core globals are why there are no mutexes: two cores never see the same variable. Cross-core communication is `relay` messages."),
        ("code",'''
mut hits = 0

fn count(q anvil.Req, w mut anvil.Out, next fn(anvil.Req, mut anvil.Out)) {
	hits += 1                 // this core's counter
	next(q, mut w)
}
'''),
        ("rules",["Reading a core's counter from another core is impossible; sum them with `relay` or expose per-core metrics.",
                  "A global's initializer may fail only through `try`, which aborts startup."])]),
]))

S.append(dict(id="types", n="03", title="Types",
intro="Sized numbers, immutable strings, reference containers, structs, enums. Nothing is nil except `?T` and `fault`.",
cards=[
dict(id="primitives", title="Numbers and bool", sig="i8…i64 · u8…u64 · f32 f64 · bool",
text="Integers are sized and signed or unsigned. Floats are IEEE-754. Conditions must be `bool`: there is no truthiness.",
code='''
let a i32 = 7
let b = i64(a) * 2       // convert to mix widths
let f = f64(b) / 3.0
let t = i64(f)           // truncates toward zero
if b > 0 && !false { }   // bool only
''',
extra=[("table",(["type","size","notes"],
   [["`i8 i16 i32 i64`","1 2 4 8","signed, wrapping"],["`u8 u16 u32 u64`","1 2 4 8","unsigned, wrapping"],
    ["`f64` / `f32`","8 / 4","`f32` rounds every operation like Go's float32"],["`bool`","1","`true`, `false`"],["`rune`","4","`i32` code point"]]))]),
dict(id="str", title="str", sig="immutable bytes · never nil",
text="A `str` is immutable UTF-8 bytes. Indexing gives a `u8`; ranging gives code points.",
code='''
let s = "héllo"
let n = len(s)           // 6 bytes
let c = s[0]             // u8 'h'
let sub = s[1:3]         // substring, shares bytes
let joined = s + "!"
for i, r in s { say.Line(i, r) }   // byte offset, rune
let bytes = []u8(s)      // copies
let back = str(bytes)    // copies
''',
rules=["`==` `<` compare bytewise. `twine` has Split, Join, HasPrefix, Repeat and the rest.", "`str(c)` makes a one-character string from a code point."]),
dict(id="slices", title="Slices and arrays", sig="[]T · [N]T",
text="A slice is a reference to a header (len, cap, data). `append` grows it in place and returns it; two names for one slice are one slice.",
code='''
mut xs = []i64{3, 1, 2}
xs = append(xs, 4)              // always assign back
let head = xs[0:2]              // a view: writes show through
let grid = [3][3]u8{}           // starts as 3 x 3 zeros
let buf = make([]u8, 0, 1024)   // length 0, capacity 1024
say.Line(len(xs), cap(xs), head)
''',
rules=["Every index is bounds-checked; the check is removed when provable (`for x in xs`, `i < len(xs)`).",
       "`make([]T, n)` of structs, maps or fns is an error: they have no zero value. Use `make([]T, 0, n)` and append."],
deeper=[("p","Reference semantics matter: assigning a slice copies the header pointer, not the elements."),
        ("code",'''
let a = []i64{1}
mut b = a
b = append(b, 2)        // a sees 2 elements too
let c = ore.Clone(a)    // an independent copy
let n = copy(b, c)      // copies min(len) elements, returns the count
'''),
        ("rules",["`[N]T` is a slice that starts with N zero elements, not a value type.",
                  "`xs...` spreads a slice into a variadic call or an `append`.", "`sift` sorts, searches, maps and filters any slice."])]),
dict(id="maps", title="Maps", sig="map[K]V · insertion ordered",
text="Keys hash by value: `str`, integers, `bool`, `f64`, or structs and enums of those. Iteration follows insertion order.",
code='''
mut m = map[str]i64{"a": 1}
m["b"] = 2
m["a"] += 10
let v = m["zzz"]            // missing key: zero value
let (n, ok) = m["b"]        // presence
delete(m, "a")
for k, v in m { say.Line(k, v) }
say.Line(len(m))
''',
rules=["Never nil; `make(map[K]V)` or a literal.", "A struct key is copied in. Slices, maps, fns and optionals cannot be keys.",
       "Hashing is keyed per process (SipHash): no hash flooding."]),
dict(id="structs", title="Structs", sig="type T struct { ... }",
text="A struct is a reference, never nil. Literals name every field they set; one field per line in the declaration.",
code='''
type User struct {
	id    i64
	name  str
	tags  []str
	boss  ?User          // optional: may be nil
}

let u = User{id: 7, name: "ana", tags: []str{}, boss: nil}
u.name = "ann"          // the object changes, the binding does not
say.Line(u.id, u.name)
''',
rules=["`str` and slice fields left out start as `\"\"` and empty. Struct, map and `fn` fields must be set, or be `?T`.",
       "`==` on structs compares identity, not contents.", "Positional literals are an error (`E090`)."]),
dict(id="enums", title="Enums", sig="type T enum { A, B(i64) }",
text="A value that is one of several variants, each with data. Read with `match`, which must cover every variant.",
code='''
type Shape enum {
	Circle(f64)
	Rect(f64, f64)
	Empty
}

let s = Shape.Rect(3, 4)
let area = match s {
	Circle(r) => 3.14159 * r * r
	Rect(w, h) => w * h
	Empty => 0.0
}
''',
rules=["Variant data is read only through `match`: no `s.r`.", "`==` compares by value when the data does; printing gives `Rect(3 4)`.",
       "JSON: `{\"Rect\":{\"$0\":3,\"$1\":4}}` with data, `\"Empty\"` without."],
deeper=[("p","Enums may hold themselves (trees) and take type parameters."),
        ("code",'''
type Option[T constraints.Any] enum {
	Some(T)
	None
}

type Tree enum {
	Leaf(i64)
	Node(Tree, Tree)
}

fn sum(t Tree) i64 {
	return match t {
		Leaf(v) => v
		Node(l, r) => sum(l) + sum(r)
	}
}

let o = Option[i64].Some(7)
match o {
	Some(v) => say.Line(v)
	None => say.Line("none")
}
'''),
        ("rules",["Several variants in one arm bind nothing: `Red, Green => ...`.", "`_` inside a variant skips a value: `Node(_, r)`.",
                  "The zero value is the first variant without data."])]),
dict(id="named", title="Named types and aliases", sig="type A B · type A = B",
text="`type Name Underlying` is a distinct type that converts explicitly; `type Name = Other` is the same type under another name.",
code='''
type Celsius f64              // distinct: Celsius(21.5), f64(c)
type IDs []i64
type Coord = (i64, i64)       // alias of a tuple type
type Mapper = fn(i64) i64     // alias of a function type
type Bytes [8]u8
type Name str max 100         // a bounded str
type Token secret str         // a secret str
''',
rules=["Methods are declared on named struct types of the same package."]),
dict(id="bounded", title="Bounded values", sig="str max 100 · []T max n",
text="A bound is checked where data enters: JSON decoding, request bodies, `bound(x)`. Too large is `fault.LimitExceeded`.",
code='''
type User struct {
	name str max 100
	tags []str max 20
}

fn create(raw str) !User {
	let name str max 100 = try bound(raw)   // checks the length
	mut u = User{name: name, tags: []str{}}
	try argo.Get(body, mut u)               // stops reading at the bound
	return u
}
''',
rules=["Bounded assigns to unbounded and to a looser bound, never the reverse.", "`append` and `+` give the unbounded type."]),
dict(id="secret", title="Secrets", sig="secret T · reveal(x)",
text="`secret` marks a value the compiler must keep out of logs, faults, JSON and plain parameters. It computes like its plain type.",
code='''
type Account struct {
	token secret str
}

fn check(given secret str, stored secret str) bool {
	return seal.Equal(given, stored)      // constant time; == is an error
}

say.Line(a.token)          // compile error: a sink
let shown = reveal(a.token) // explicit declassification
''',
rules=["Interpolation, slicing, conversions and map reads of a secret give secrets; `len` does not.",
       "`tin audit secrets FILE.tin` lists every `reveal` and every secret handed to a library."]),
dict(id="fntype", title="Function values", sig="fn(A) B",
text="A function value is a top-level function or a closure. `mut` parameters are part of the type.",
code='''
type Handler = fn(anvil.Req, mut anvil.Out)

fn double(x i64) i64 { return 2 * x }
fn apply(f fn(i64) i64, x i64) i64 { return f(x) }

let f = double
let g = fn(x i64) i64 { return x + 1 }
say.Line(apply(f, 3), apply(g, 3))      // 6 4
''',
rules=["A call through a value is checked like a direct one: `f(mut box)` needs a modifiable argument."]),
]))

S.append(dict(id="functions", n="04", title="Functions",
intro="`fn` for functions, methods and closures. Parameters are read-only unless `mut`. Results are values, tuples or `!T`.",
cards=[
dict(id="fn", title="fn and results", sig="fn name(params) Result { }",
text="A function returns nothing, one value, a tuple, or any of these marked `!` (can fail).",
code='''
fn add(a i64, b i64) i64 { return a + b }
fn divmod(a i64, b i64) (i64, i64) { return a / b, a % b }
fn parse(s str) !i64 { ... }           // a value, or a fault
fn flush(w mut Writer) ! { ... }       // nothing, or a fault
fn greet() { say.Line("hi") }

let (q, r) = divmod(7, 2)
''',
rules=["Every path of a function with results ends in `return`.", "Up to 8 integer and 8 float parameters; up to 8 results."]),
dict(id="mut", title="mut parameters and call-site mut", sig="fn f(xs mut []T) · f(mut xs)",
text="A parameter is read-only: changing its fields, elements or entries is a compile error. `mut` allows it, and every call shows it.",
code='''
fn fill(xs mut []i64, v i64) {
	for i in 0..len(xs) { xs[i] = v }
}

fn rename(u User, n str) { u.name = n }     // compile error: u is not mut

mut xs = make([]i64, 3)
fill(mut xs, 7)                 // the caller writes mut too
argo.Put(mut buf, value)
sift.Ints(mut xs)
''',
rules=["`mut` is for structs, slices, maps and optionals of them; numbers, `str` and faults are values, so `mut` on them is an error.",
       "A `mut` struct, optional or map parameter cannot be reassigned inside the function; a `mut` slice can (`xs = append(xs, v)`).",
       "Receivers and the builtins `append`, `copy`, `delete` take no `mut`."]),
dict(id="variadic", title="Variadics", sig="fn f(xs ...T)",
text="The last parameter may take any number of arguments, or a spread slice.",
code='''
fn sum(xs ...i64) i64 {
	mut t = 0
	for x in xs { t += x }
	return t
}

let xs = []i64{1, 2}
say.Line(sum(1, 2, 3), sum(xs...))
'''),
dict(id="methods", title="Methods", sig="fn (r T) name() · fn (r mut T) name()",
text="The receiver comes first and is a parameter like any other; `mut` lets the method change it.",
code='''
type Point struct {
	x i64
	y i64
}

fn (p Point) dist() f64 { return gauge.Sqrt(f64(p.x*p.x + p.y*p.y)) }
fn (p mut Point) move(dx i64, dy i64) {
	p.x += dx
	p.y += dy
}

mut p = Point{x: 3, y: 4}
p.move(1, 1)                 // no mut at the call for receivers
say.Line(p.dist())
'''),
dict(id="closures", title="Closures", sig="fn(params) R { body }",
text="A function literal may read and write the variables around it; both share one variable.",
code='''
fn makeCounter() fn() i64 {
	mut n = 0
	return fn() i64 {
		n += 1
		return n
	}
}

let c = makeCounter()
say.Line(c(), c(), c())      // 1 2 3
sift.Each(xs, fn(x i64) { total += x })
''',
rules=["Each loop iteration has its own variable, so closures made in different iterations differ.",
       "A closure cannot capture a `mut` parameter; copy it to a local first.", "A local closure cannot call itself: use a top-level function."],
deeper=[("p","Where a closure lives decides what it may store. One called at once, or passed to library functions that only call it (`sift.Each`, `Map`, `Filter`), stays on the caller's frame. Any other closure is allocated in the request pool."),
        ("code",'''
mut handlers = []fn() i64{}

fn register(q anvil.Req) {
	let path = q.Path
	handlers = append(handlers, keep(fn() i64 { return len(path) }))
	// keep copies the descriptor and every captured variable
}

defer fn() { say.Line("done", n) }()      // sees n's value when it runs
'''),
        ("rules",["Storing a closure that captures request memory in a global needs `keep(f)`.",
                  "A kept closure's captured variables are long-lived: its body storing request memory into them is a compile error."])]),
dict(id="generics", title="Generics", sig="fn f[T C](x T) · type S[T C] struct",
text="Type parameters in square brackets, constrained by a shape or a union. Every instantiation is compiled separately: no boxing, no dispatch.",
code='''
import "constraints"

fn max[T i64 | f64 | str](a T, b T) T {
	if a > b { return a }
	return b
}

type Stack[T constraints.Any] struct {
	items []T
}

fn (s mut Stack[T]) push(x T) { s.items = append(s.items, x) }

say.Line(max(3, 9), max[f64](1, 2.5))     // inferred, or explicit
mut s = Stack[i64]{items: []i64{}}
s.push(1)
''',
rules=["Constraints: `constraints.Any`, `constraints.Comparable`, `sift.Ordered`, a union `i64 | f64 | str`, or any shape.",
       "Operations are checked per instantiation: `max[bool]` fails where it is instantiated."],
deeper=[("code",'''
fn mapSlice[T constraints.Any, U constraints.Any](xs []T, f fn(T) U) []U {
	mut out = make([]U, 0, len(xs))
	for x in xs { out = append(out, f(x)) }
	return out
}

type Pair[A constraints.Any, B constraints.Any] struct {
	first  A
	second B
}

let names = mapSlice(users, fn(u User) str { return u.name })
let p = Pair[str, i64]{first: "k", second: 7}
'''),
        ("rules",["Generic shape calls are direct calls on the concrete type (see Shapes).",
                  "Untyped constants infer `i64` or `f64`: `max(1, 2)` is `max[i64]`."])]),
dict(id="attributes", title="Attributes", sig="@name(args)",
text="An attribute precedes what it annotates. They are checked at compile time and add no runtime metadata.",
code='''
type User struct {
	@json("id")   id   i64
	@json("name") name str
}

@nopoll fn kernel(xs []f64) f64 { ... }    // no cancellation polls in this function
''',
rules=["`@json(\"key\")` renames a JSON member.", "`@nopoll` omits safepoints in a proven-short kernel."]),
]))

S.append(dict(id="control", n="05", title="Control flow",
intro="`if`, one `for` with four shapes, and `match` as statement or expression. No `switch`, no `goto`, no fallthrough.",
cards=[
dict(id="if", title="if / else", sig="if cond { } else if { } else { }",
text="Conditions are `bool`. Braces are mandatory.",
code='''
if n > 0 {
	say.Line("positive")
} else if n == 0 {
	say.Line("zero")
} else {
	say.Line("negative")
}
if let u = maybeUser { say.Line(u.name) }     // binds when not nil
''',
rules=["No init statement: bind the value on the line before.", "`if x != nil { }` narrows an optional; see Optionals."]),
dict(id="for", title="for", sig="for x in xs · for i in 0..n · for cond · for",
text="One loop keyword. Ranges are half-open and read directly by the bounds prover.",
code='''
for x in xs { }                 // elements
for i, x in xs { }              // index and element
for k, v in m { }               // map, insertion order
for i, r in "héllo" { }         // byte offset and rune
for i in 0..n { }               // 0 .. n-1
for i in (0..n).step(2) { }     // a step
for running { }                 // while
for { break }                   // forever
''',
rules=["`break` and `continue` take an optional label.", "No C-style `for i := 0; ...`; no `..=`."],
deeper=[("code",'''
outer: for i in 0..n {
	for j in 0..n {
		if grid[i][j] == 0 { continue outer }
		if grid[i][j] > limit { break outer }
	}
}
'''),
        ("rules",["Element variables are copies of the element; write through the index to change the slice.",
                  "Each iteration gets a fresh loop variable, so closures capture distinct values."])]),
dict(id="match", title="match", sig="match x { pattern => value }",
text="Arms are `pattern => expression` or `pattern => { block }`. As an expression it must handle every value; as a statement arms may leave.",
code='''
let label = match status {
	200 => "ok"
	404 => "missing"
	500..600 => "server error"
	401, 403 => "auth"
	n if n > 600 => "unknown {n}"
	_ => "other"
}

match shape {                       // an enum: every variant or _
	Circle(r) => area = pi * r * r
	Rect(w, h) => area = w * h
	Empty => return
}
''',
rules=["Patterns: literals, ranges, several patterns with `,`, a guard `n if cond`, enum variants with bindings, `_`.",
       "A name pattern compares with a package-level constant or sentinel, names a variant, or binds the value.", "There is no fallthrough."],
deeper=[("p","Over a fault, arms compare with `fault.Is`, so wrapped causes match their sentinel. Over a `bool`, `true` and `false` cover it."),
        ("code",'''
let user = loadUser(id) catch err {
	match err {
		ErrNotFound => return w.Status(404)
		fault.DeadlineExceeded, fault.Overloaded => return w.Status(503)
		_ => return w.Status(500)
	}
}

match result {
	Some(Other(v)) => use(v)        // nested variant patterns
	_ => { return }
}
'''),
        ("rules",["An arm may be a `return`, `break`, `continue`, `fail` or an assignment; `break` applies to the enclosing loop.",
                  "A statement `match` compiles to the same instructions a `switch` would."])]),
]))

S.append(dict(id="errors", n="06", title="Errors",
intro="A function that can fail says so with `!`. A fault is a value that must be handled: `try` passes it up, `catch` handles it here.",
cards=[
dict(id="fail", title="!T and fail", sig="fn f() !T · fail \"msg\" · fail err",
text="`!T` is a `T` or a fault; `!` alone is nothing or a fault. `return` gives the value; `fail` leaves with a fault.",
code='''
fn parse(s str) !i64 {
	if s == "" {
		fail "empty input"                    // a message
	}
	mut n = 0
	for i, c in s {
		if c < '0' || c > '9' {
			fail say.Fault("bad digit %q at %d", str(c), i)
		}
		n = n*10 + i64(c-'0')
	}
	return n
}
''',
rules=["`return v, nil` and result lists ending in `fault` are compile errors: write `!T`.",
       "A fault always comes with zero values for the rest: real `\"\"`, empty slices, never nil."]),
dict(id="try", title="try", sig="let v = try f() · try f()",
text="Inside a `!` function, `try` passes a fault to the caller and continues with the value otherwise.",
code='''
fn double(s str) !i64 {
	let v = try parse(s)
	return v * 2
}

fn save(path str, text str) ! {
	let w = try flume.Create(path)
	w.Str(text)
	try w.Close()                 // as a statement
}
''',
rules=["`try` cannot sit inside a larger expression: bind the inner result first.", "Ignoring a fault is a compile error; so is `_` in a fault position."]),
dict(id="catch", title="catch", sig="e catch err { ... }",
text="Handles a fault in place. The block's last expression is the value, or the block leaves with `return`, `break`, `continue` or `fail`.",
code='''
let port = mint.Atoi(text) catch _ { 8080 }

let (n, ok) = parsePair(s) catch err {
	say.Line("skipping:", err)
	continue
}

w.Close() catch err { herald.Warn(say.Str(err)) }

let (v, err) = double("x")      // or look at the fault yourself
if err != nil { say.Line("error:", err) }
''',
rules=["`err` is the fault; `_` ignores it. The block does not run on success.", "A fault prints as its message; `say.Str(err)` gives it as a `str`."]),
dict(id="wrap", title="wrap, sentinels and chains", sig="try e wrap \"msg\" · fault.Is",
text="`wrap` adds context and keeps the cause. A package-level `fault(\"...\")` is a sentinel with its own identity, matched through the chain.",
code='''
let ErrNotFound = fault("not found")       // a sentinel, package level only

fn load(id i64) !User {
	let row = try db.QueryOne("...", id) wrap "loading user {id}"
	if row == nil { fail ErrNotFound }
	return try decode(row)
}

let u = load(7) catch err {
	if fault.Is(err, ErrNotFound) { return w.Status(404) }
	fail err
}
''',
rules=["`fault.Wrap(err, msg)`, `fault.Cause`, `fault.Join([]fault{a, b})`, `fault.Message`.",
       "Runtime sentinels: `fault.Canceled`, `DeadlineExceeded`, `LimitExceeded`, `Overloaded`, `Draining`, `Panic`."],
deeper=[("p","`try e wrap \"m\"` is `e catch err { fail fault.Wrap(err, \"m\") }`. A wrapped fault reads `loading user 7: not found` and `fault.Is` still finds `ErrNotFound`."),
        ("code",'''
fn fetchAll(ids []i64) ![]User {
	mut out = []User{}
	mut errs = []fault{}
	for id in ids {
		let u = load(id) catch err {
			errs = append(errs, err)
			continue
		}
		out = append(out, u)
	}
	if len(errs) > 0 { fail fault.Join(errs) }     // messages on separate lines
	return out
}
'''),
        ("rules",["`fault(\"...\")` anywhere but a package-level `let` is a compile error; use `say.Fault` for formatted faults.",
                  "`==` on faults compares references; use `fault.Is`."])]),
dict(id="defer", title="defer", sig="defer f(args)",
text="Runs when the function returns, last deferred first, on every path including the ones `try` and panics take.",
code='''
fn copyFile(src str, dst str) ! {
	let r = try quarry.Open(src)
	defer r.Close()
	let w = try flume.Create(dst)
	defer w.Flush()
	try io.Copy(mut w, mut r)
}
''',
rules=["Not inside loops (move the body to a function).", "A deferred call cannot return a fault: defer one that handles it.",
       "A function-level `use x = e` is `let x = try e` plus a deferred `Close` whose fault is joined to the function's."]),
dict(id="panic", title="panic and guard", sig="panic(msg) · guard { } · guard f()",
text="A panic is a bug: index out of range, division by zero, `panic(...)`. It unwinds to the nearest `guard`, which turns it into a `fault.Panic`.",
code='''
let page = guard {
	render(model)                 // a panic here becomes a fault
} catch err {
	say.Line(fault.Backtrace(err))
	errorPage(err)
}

let v = guard risky(x) catch _ { 0 }     // the same around one call
''',
rules=["Every request, spawned task, tick and relay handler is guarded implicitly: a panic logs, runs defers, answers 500, and the core goes on.",
       "A panic in `main` outside a guard, or a stack overflow, ends the process with a backtrace."]),
]))

S.append(dict(id="optionals", n="07", title="Optionals",
intro="`?T` holds a `T` or `nil`. The compiler narrows it where it can see the check, so a nil is never dereferenced.",
cards=[
dict(id="opt", title="?T and narrowing", sig="?T · if x != nil · if x == nil { return }",
text="After a check the variable has type `T` inside the branch, or after an early return.",
code='''
fn find(id i64) ?User { ... }

let u = find(7)
if u == nil {
	return
}
say.Line(u.name)                 // u is a User from here on

if a != nil && b != nil { use(a, b) }
if l == nil || r == nil { return 1 }
return check(l) + check(r)
''',
rules=["Only references can be optional: `str`, slices, maps, structs, `dyn`, enums.", "Narrow a field through a local: `let next = node.next`.",
       "Assigning `nil` to a narrowed variable is a type error."]),
dict(id="iflet", title="if let and ??", sig="if let x = opt { } · opt ?? default",
text="`if let` binds the value when present; `??` gives a default for nil.",
code='''
if let user = find(id) {
	say.Line(user.name)
} else {
	say.Line("no user")
}

let name = maybeName ?? "anonymous"
let port = config.port ?? 8080
''',
deeper=[("p","Optional fields print as an address (like a Go pointer) so a self-referencing structure prints and ends. JSON encodes a nil optional as `null` and accepts `null` into one."),
        ("code",'''
type Node struct {
	value i64
	next  ?Node
}

fn length(head ?Node) i64 {
	mut n = 0
	mut cur = head
	for cur != nil {
		n += 1
		cur = cur.next
	}
	return n
}
''')]),
]))

S.append(dict(id="memory", n="08", title="Memory",
intro="No garbage collector. Requests allocate in a pool wiped after the response; long-lived data lives in a per-core heap, and the compiler proves request memory never leaks into it.",
cards=[
dict(id="keep", title="Pools and keep", sig="keep(x)",
text="Storing request memory into a global, or anything a global reaches, is a compile error unless the value goes through `keep`, which deep-copies it into the long-lived heap.",
code='''
mut cache = map[str]User{}
mut recent = []str{}

fn remember(q anvil.Req, u User) {
	cache[keep(q.Path)] = keep(u)         // key and value copied
	recent = append(recent, keep(q.Path))
}

fn forget(q anvil.Req) {
	cache[q.Path] = u                     // E310 REQUEST_ESCAPE: wrap the value in keep()
}
''',
rules=["Globals and constants are long-lived; literals are static; fresh allocations are request memory.",
       "The checker follows stores through fields, elements, map entries, `append`, `copy` and function summaries.",
       "Long-lived memory is reference counted and reclaimed when overwritten or deleted."],
deeper=[("p","A helper that stores into a `mut` parameter makes its callers responsible: passing a global to it is an error at the call unless the helper keeps what it stores."),
        ("code",'''
type Cache struct {
	m map[str]str
}

fn (c mut Cache) put(k str, v str) {
	c.m[keep(k)] = keep(v)          // keep inside: callers may pass a global
}

mut gc = Cache{m: map[str]str{}}

fn h(q anvil.Req, w mut anvil.Out) {
	gc.put(q.Path, q.Body())        // ok because put keeps
	let u = cache["k"]              // stays valid for the whole request
	w.Text(u.name)                  // even if another request replaces the entry
}
'''),
        ("rules",["A plain program never resets its pool; everything is released at exit. `hearth.Reset()` resets it by hand, and reading a value from before the reset is `E313 USE_AFTER_RESET`.",
                  "`hearth.RcStats()` reports counted blocks, bytes and the release queue."])]),
dict(id="arena", title="arena", sig="arena { body }",
text="Runs its body in a fresh pool dropped when the block ends. Only the block's value leaves, copied out.",
code='''
mut total = 0
for path in paths {
	total += arena {                  // each step's temporaries are freed
		countWords(load(path))
	}
}

let names = try arena {
	let text = try quarry.ReadFile(path)
	let doc = try parse(text)
	doc.names                         // copied out; doc is freed
}
''',
rules=["Storing an arena value anywhere outside is `E315 ARENA_ESCAPE`; appending to an outside slice inside is rejected too.",
       "A recursive type, a `fn` or a `dyn` value cannot be the result (`E316`).", "`keep(x)` inside an arena still copies to the long-lived heap."]),
dict(id="limit-memory", title="limit memory", sig="limit memory n, tasks k { }",
text="Counts the pool chunks and tasks taken inside the block; passing a budget cancels it with `fault.LimitExceeded`.",
code='''
let summary = try limit memory 4mb, tasks 8 {
	summarize(try loadAll(ids))
}
''',
rules=["`TIN_REQUEST_MEMORY` bounds every request the same way; past it the request ends with 500 and the server goes on."]),
]))

S.append(dict(id="concurrency", n="09", title="Boundaries and concurrency",
intro="One thread per core, no shared mutable state. Work is tasks inside boundaries; cancellation, deadlines and budgets flow down, never up.",
cards=[
dict(id="within", title="within", sig="within d { body }",
text="A deadline for the block: the earlier of `now + d` and the enclosing one. Waits past it fail with `fault.DeadlineExceeded`.",
code='''
let profile = try within 200ms {
	try api.Profile(id)
}

within 50ms {
	within 1h { }               // still 50 ms: the earlier deadline wins
}
''',
rules=["Every request has the server's deadline (`TIN_DEADLINE_MS`, default 30 s); `main` has none.",
       "`task.Deadline()` reads the effective deadline; `task.Canceled()` the fault the next wait would give."],
deeper=[("p","Waits observe cancellation at once. CPU-bound code observes it at safepoints, which `tin build --polls` inserts on loop back-edges; without them, poll by hand."),
        ("code",'''
fn crunch(xs []f64) !f64 {
	mut acc = 0.0
	for i, x in xs {
		if i % 4096 == 0 { try task.Canceled() }    // stop at a point of your own
		acc += x * x
	}
	return acc
}
''')]),
dict(id="scope", title="scope and spawn", sig="scope s { s.spawn(fn() ! { }) }",
text="Structured concurrency on one core. Children share the parent's pool and cannot outlive the scope; the first fault cancels the rest.",
code='''
scope s {
	for u in urls {
		let url = u
		s.spawn(fn() ! {
			pages = append(pages, try fetch(url))
		})
	}
}                                   // waits for every child

scope s {
	let t = s.spawn(fn() !Report { return try build() })
	let report = try t.wait()
	t.cancel()
	s.cancel("done")                // cancels the scope by hand
}
''',
rules=["Children run when the parent waits; `s.yield()` lets ready tasks run.", "A handle cannot leave its scope: no globals, fields, results or captures by `detach`.",
       "`try` inside the body passes the scope's fault on; leaving early cancels and joins the children."]),
dict(id="parallel", title="parallel", sig="let (a, b) = try parallel { e1 \\n e2 }",
text="Each line runs as a child task; the value is the tuple of results. The first fault cancels the others.",
code='''
let (user, orders) = try parallel {
	db.User(id)
	db.Orders(id)
}
'''),
dict(id="select", title="select", sig="select { let x = wait => arm }",
text="Waits on several sources; the first ready arm wins, ties go to source order. Arms are waits: lanes, task handles, `after(d)`, `canceled()`.",
code='''
select {
	let job = jobs.Recv() => handle(job)
	let r = t.wait() => use(r)
	after(5s) => fail "timed out"
	canceled() => return
}
''',
rules=["With no arm ready it parks until one is, or the earliest `after`.", "A cancelled boundary with no `canceled()` arm ends the select with its fault."]),
dict(id="lane", title="lane", sig="lane.New[T](capacity)",
text="A bounded queue between tasks on one core. `Send` waits when full; `TrySend` returns false.",
code='''
let jobs = lane.New[Job](64)

scope s {
	s.spawn(fn() ! {
		for j in work { try jobs.Send(j) }
		jobs.Close()
	})
	for {
		let j = jobs.Recv() catch _ { break }
		try process(j)
	}
}
''',
rules=["Across cores use `relay.Send(core, msg)` and `relay.Next()`; messages are copied."]),
dict(id="detach", title="detach", sig="detach { body }",
text="Starts a task in the core's background boundary that outlives the request. Everything it captures must be long-lived.",
code='''
fn h(q anvil.Req, w mut anvil.Out) {
	let e = keep(event(q))
	detach {
		analytics.Flush(e)          // runs after the response
	}
	detach {
		audit(keep(q.Path))         // or keep inside the block
	}
	w.Text("accepted")
}
''',
rules=["Its fault is logged, not passed on; the drain cancels it with `fault.Draining`.", "A capture that may hold request memory is a compile error naming it."]),
dict(id="cores", title="Cores and relay", sig="hearth.Run(n, f) · relay.Send(core, msg)",
text="`hearth.Run` runs `f(core)` on n threads. `relay` copies `str` messages into another core's inbox.",
code='''
fn work(core i64) {
	relay.Send(0, "hello from {core}")
}

fn main() {
	hearth.Run(hearth.Cores(), work)
}

anvil.OnRelay(fn(from i64, msg str) { ... })    // in a server
anvil.OnTick(1000, fn(core i64) { ... })
''',
rules=["`hearth.Cores()` respects cgroup quotas and affinity; `TIN_CORES` lowers it.", "Encode structs with `argo` to send them."]),
]))

S.append(dict(id="policies", n="10", title="Policies and lifecycle",
intro="`with` runs a block under a library policy, `use` binds a resource to a scope, `on` handles lifecycle events, `once` runs per core.",
cards=[
dict(id="with", title="with", sig="with policy { body }",
text="Any value with `Run(body fn() !T) !T` is a policy. Retry, trace, cache and slot binding are library code, not keywords.",
code='''
let payment = try with policy.Retry(3) {
	try stripe.Charge(card, amount)
}

let page = try with policy.Trace("render") {
	try render(model)
}
''',
rules=["`return`, `break` and `continue` cannot leave the block; its value is the last expression.",
       "A policy may run the body several times; side effects run again."],
deeper=[("p","Slots are typed ambient values (request id, user) bound for a block and everything it spawns."),
        ("code",'''
let requestID = task.NewSlot[str]("request-id")

fn logged(q anvil.Req, w mut anvil.Out, next fn(anvil.Req, mut anvil.Out)) {
	with policy.Bind(requestID, q.Header("x-request-id")) {
		next(q, mut w)
	}
}

fn deep() ! {
	let id = try requestID.Get()           // anywhere below the bind
	herald.Info2("working", "request", id)
}
''')]),
dict(id="use", title="use", sig="use x = e",
text="At package level: a per-core resource opened at core start and closed at core stop. In a function: `let x = try e` plus a deferred `Close`.",
code='''
use db = postgres.Open(cfg)          // one per core; a fault aborts startup

fn migrate() ! {
	use tx = db.Begin()              // closed when migrate ends, even on a fault
	try tx.Exec(schema)
	try tx.Commit()
}
''',
rules=["A resource is any value with `Close() !`.", "A fault from `Close` is joined after the function's own fault."]),
dict(id="on", title="on", sig="on event { body }",
text="Typed lifecycle events, run in declaration order, each guarded.",
code='''
on app.start { try migrate() }            // once, before the cores start
on core.start { warm() }                  // on each core
on server.overload { metrics.Inc(shed) }
on server.recovered { metrics.Inc(ok) }
on core.stop { flushLocal() }
on app.stop {
	within 5s { telemetry.Flush() }
}
''',
rules=["A fault or panic in a start handler ends startup with status 1; elsewhere it is logged.",
       "SIGTERM starts a drain: listeners close, in-flight requests finish, then remaining work is cancelled with `fault.Draining` at `TIN_GRACE`."]),
dict(id="once", title="once", sig="once { body }",
text="Runs its block the first time each core reaches it. Process-wide one-time work belongs in `on app.start`.",
code='''
fn handler(q anvil.Req, w mut anvil.Out) {
	once {
		warmCache()              // this core, first request only
	}
	w.Text("ok")
}
'''),
dict(id="admission", title="Admission and drain", sig="anvil.Admit(p) · anvil.Drain(d)",
text="A policy decides each new request from the core's load; refusal is a 503 with `Retry-After` and no allocation.",
code='''
fn admit(l anvil.Load) bool {
	return l.Waiting < 2000 && l.Buffered < 128mb
}

fn main() ! {
	anvil.Admit(admit)
	anvil.Deadline(5000)
	try anvil.Serve(":8080", handler)
}
''',
rules=["Built-in limits: 4096 waiting requests per core, 16384 connections per core, 64 MiB bodies, 256 MiB buffered.",
       "`anvil.Drain(d)` starts the same graceful shutdown as SIGTERM."]),
]))

S.append(dict(id="output", n="11", title="Strings, output and queries",
intro="Formatting is generated per type at compile time: no reflection. Queries keep values apart from text.",
cards=[
dict(id="say", title="say", sig="say.Line · Text · Out · Fmt · Str · Fault",
text="Each argument is formatted by its static type.",
code='''
say.Line("x =", x, ok)              // space-separated, newline
say.Text("no", "spaces")            // concatenated
say.Out("%5.2f|%-4s|%x\\n", f, s, n)  // printf
let s = say.Fmt("%d items", n)
let t = say.Str(x)                  // any value as a str
let e = say.Fault("bad %q", s)      // a formatted fault
say.To(w, "%d\\n", n)                // to anything with Write(str)
''',
extra=[("table",(["verb","meaning"],[["`%v`","default format"],["`%d %x %o %b`","integers"],["`%s %q`","string, quoted"],["`%f %e %g`","floats"],["`%t`","bool"],["`%+v`","structs with field names"]]))],
rules=["Default formats: slices `[a b c]`, maps `map[k:v]` with sorted keys, structs `{a b}`, nil `<nil>`.", "Floats print in the shortest form that reads back exactly."]),
dict(id="queries", title="Queries", sig="c.Do(\"SET user:{id} {body}\")",
text="Where a parameter has type `query`, a literal keeps its text pieces and values apart, so a value can never change the shape of a command.",
code='''
try cache.Do("SET user:{id} {body}")        // SET, user:42, body: three arguments
let rows = try db.Query("SELECT name FROM users WHERE id = {id}")   // bound
try db.Exec(cmd)                             // compile error: cmd is a str
''',
rules=["Values must be integers, floats, `str`, `bool` or `[]u8`, with no format spec.", "A secret in a query is sent as itself and never recorded in a replay capsule."]),
dict(id="logging", title="herald", sig="herald.Info(msg) · Info2(msg, k, v)",
text="Structured key-value logging with levels; secrets are rejected at compile time.",
code='''
herald.Info("started")
herald.Info2("request", "path", q.Path)
herald.Error2("upstream", "err", say.Str(err))
herald.SetLevel(herald.Warn)
'''),
]))

S.append(dict(id="json", n="12", title="JSON",
intro="`argo` generates an encoder and a decoder per type. Member names are the field names unless `@json` renames them.",
cards=[
dict(id="argo", title="argo.Put and argo.Get", sig="argo.Put(mut b, v) · argo.Get(text, mut v)",
text="`Put` appends to a `[]u8`; `Get` fills a struct, appends to a slice or adds to a map, and fails on bad JSON or types.",
code='''
type User struct {
	@json("id") id i64
	name  str
	email ?str
	tags  []str
}

mut b = make([]u8, 0, 256)
argo.Put(mut b, User{id: 7, name: "ana", email: nil, tags: []str{"admin"}})
// {"id":7,"name":"ana","email":null,"tags":["admin"]}

mut u = User{id: 0, name: "", email: nil, tags: []str{}}
try argo.Get(text, mut u)
mut xs = []User{}
try argo.Get(list, mut xs)
''',
rules=["Numbers must fit their type (`300` into a `u8` fails); `1e400`, `007` and trailing garbage fail.",
       "Nesting deeper than 512 fails. Unknown members are skipped; a duplicate key takes the last value.",
       "Enums: `{\"Rect\":{\"$0\":3,\"$1\":4}}` with data, `\"Empty\"` without. Floats: shortest form; NaN and Inf as `null`."],
deeper=[("code",'''
fn create(q anvil.Req, w mut anvil.Out) {
	mut u = User{id: 0, name: "", email: nil, tags: []str{}}
	argo.Get(q.Body(), mut u) catch err {
		w.Status(400)
		w.Text("bad json: {err}")
		return
	}
	w.Json()
	argo.Put(mut w.Body, u)
}
'''),
        ("rules",["`argo.Str(b, s)` and `argo.Raw(b, json)` write pieces by hand.", "Bounded fields stop reading at the bound with `fault.LimitExceeded`."])]),
]))

S.append(dict(id="shapes", n="13", title="Shapes and dyn",
intro="A shape is a set of method signatures satisfied structurally. Static by default through generics; `dyn S` opts into one indirect call.",
cards=[
dict(id="shape", title="shape", sig="shape S { method(params) R }",
text="Members are method signatures without receiver or body, or the names of other shapes. A named union lists concrete types.",
code='''
shape Reader { read(buf mut []u8) !i64 }
shape Writer { write(data []u8) !i64 }
shape ReadWriter {
	Reader
	Writer
	flush() !
}
shape Ordered = i64 | i32 | f64 | str
shape Seq[T constraints.Any] { next() ?T }

fn copyAll[R Reader, W Writer](dst mut W, src mut R) !i64 { ... }
''',
rules=["Satisfaction is structural: same names, parameter types, `mut` marks and results. No declaration needed.",
       "Generic shape calls are direct calls on the concrete type: no dispatch, no allocation."]),
dict(id="dyn", title="dyn", sig="dyn S · ?dyn S · []dyn S",
text="A two-word value: the object and a static method table. Converting allocates nothing; a call is one indirect jump.",
code='''
shape Writer { write(s str) }

type File struct { fd i64 }
fn (f File) write(s str) { ... }

fn out(w dyn Writer) { w.write("x") }

let f = File{fd: 1}
out(f)                                // converts at the call
let ws = []dyn Writer{f}
let w dyn Writer = f
''',
rules=["Never nil; `?dyn S` is the optional.", "No downcast and no type switch: a closed set is an `enum`, an open set is a method on the shape."]),
]))

S.append(dict(id="server", n="14", title="A service, end to end",
intro="The constructs together: a router, a per-core database, a cache policy, deadlines and JSON.",
cards=[
dict(id="service", title="HTTP service", sig="anvil · argo · postgres · redis",
text="Each request runs in its own task; a wait lets the core serve others. Allocations go to the request pool and vanish after the response.",
code='''
package main

import "anvil"
import "argo"
import "policy"
import "postgres"
import "redis"
import "quarry"

use db = postgres.Open(postgres.Options{Addr: quarry.Getenv("DB_ADDR")})
use cache = redis.Open(redis.Options{Addr: quarry.Getenv("REDIS_ADDR")})

type User struct {
	@json("id")    id    i64
	@json("name")  name  str max 100
	@json("email") email ?str
}

on app.start { try db.Ping() }

fn getUser(q anvil.Req, w mut anvil.Out) ! {
	let id = try mint.Atoi(q.PathParam("id"))
	let user = try within 200ms {
		try with policy.Retry(2) {
			try db.QueryOne[User]("SELECT id, name, email FROM users WHERE id = {id}")
		}
	}
	match user {
		nil => w.Status(404)
		_ => {
			w.Json()
			argo.Put(mut w.Body, user)
		}
	}
}

fn main() ! {
	let r = anvil.NewRouter()
	r.Get(`/users/{id}`, getUser)
	try r.Serve(":8080")
}
''',
rules=["Routes: static beats `{name}` beats `{rest...}`; wrong method gets 405 with `Allow`; `$PORT` overrides the port.",
       "Middleware: `fn(q anvil.Req, w mut anvil.Out, next fn(anvil.Req, mut anvil.Out))` added with `r.Use`.",
       "Test without a server: `r.Run(\"GET\", \"/users/7\", \"\")` gives an `Out` with `Code()` and `Body`."]),
]))

S.append(dict(id="reference", n="15", title="Reference",
intro="Builtins, keywords and the grammar in one place.",
cards=[
dict(id="builtins", title="Builtins", sig="",
text="Functions the compiler knows.",
extra=[("table",(["builtin","meaning"],[
 ["`len(x)` `cap(s)`","length of a str (bytes), slice or map; capacity of a slice"],
 ["`append(s, v...)`","add elements, a spread slice, or a str to a `[]u8`; returns s"],
 ["`make([]T, n, c)` `make(map[K]V)`","a new slice or map"],
 ["`copy(dst, src)`","copies min(len) elements; returns the count"],
 ["`delete(m, k)`","removes an entry"],
 ["`min(a, b)` `max(a, b)`","of two numbers of one type"],
 ["`keep(x)`","deep copy into long-lived memory"],
 ["`bound(x)`","checks a bound; `!T`"],
 ["`reveal(x)`","declassifies a secret"],
 ["`fault(\"msg\")`","declares a sentinel (package level only)"],
 ["`panic(msg)`","stops the task or program"],
 ["`new(T)`","`T{}`"]]))]),
dict(id="keywords", title="Keywords", sig="",
text="The full reserved list. Words such as `in`, `max`, `on`, `use`, `with`, `once`, `select`, `scope`, `arena`, `shape` and `dyn` stay usable as names where no construct starts.",
code='''
package import
fn let mut const type shape enum dyn
if else for in match return break continue defer
try catch fail keep
within limit guard scope arena parallel select detach
with use on once
secret max shared
nil true false
'''),
dict(id="precedence", title="Operators and precedence", sig="high to low",
text="Postfix forms bind tightest: calls, indexing, slicing, selectors, literals, type arguments.",
extra=[("table",(["level","operators"],[
 ["unary","`-x` `!x` `^x` `try e` `keep e` `mut x`"],
 ["5","`*` `/` `%` `<<` `>>` `&`"],["4","`+` `-` `|` `^`"],["3","`==` `!=` `<` `<=` `>` `>=`"],["2","`&&`"],["1","`||`"],["postfix","`e catch err { }` `try e wrap \"m\"` `opt ?? d`"]]))],
rules=["Both operands of a binary operator have one type after untyped constants adapt.", "Assignment: `=` `+=` `-=` `*=` `/=` `%=` `&=` `|=` `^=` `<<=` `>>=`; parallel `a, b = b, a`."]),
dict(id="grammar", title="Grammar summary", sig="EBNF",
text="`{x}` repeats, `[x]` is optional, `|` separates alternatives.",
code='''
File        = "package" Name { Import } { TopDecl } .
TopDecl     = ConstDecl | GlobalDecl | TypeDecl | ShapeDecl | FnDecl | UseDecl | OnDecl .
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
Boundary    = ( "within" Expr | "limit" LimitList | "guard" | "arena" | "parallel" | "with" Expr ) Block .
Select      = "select" "{" { [ "let" Name "=" ] Expr "=>" ( Expr | Block ) } "}" .

Expr        = Unary { BinOp Unary } [ "catch" Name Block ] [ "wrap" String ] .
Unary       = [ "try" | "keep" | "-" | "!" | "mut" ] Primary { Postfix } .
Postfix     = "." Name | "[" Expr [ ":" Expr ] "]" | "[" Types "]" | Args | "??" Unary .
Type        = Name [ "[" Types "]" ] | "[" "]" Type | "[" Int "]" Type | "map" "[" Type "]" Type
            | "?" Type | "!" Type | "dyn" Name | "secret" Type | Type "max" Expr
            | "(" Types ")" | "fn" "(" Types ")" [ Type ] .
''', ),
]))

# ---------------------------------------------------------------- pages
def head(title, desc, active):
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,500;0,600;0,700;1,500&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="tin.css">
<script>try{{var t=localStorage.getItem('tin-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}</script>
</head>
<body>
<header class="top"><div class="top-inner">
  <a class="brand" href="index.html"><img src="logo.svg" alt="">Tin</a>
  <nav>
    <a href="syntax.html"{' class="active"' if active=="syntax" else ""}>Syntax</a>
    <a href="https://github.com/yasserreslan/tin/blob/main/docs/STDLIB.md">Standard library</a>
    <a href="https://github.com/yasserreslan/tin/blob/main/docs/RUNTIME.md">Runtime</a>
  </nav>
  <span class="spacer"></span>
  <a class="btn" href="https://github.com/yasserreslan/tin">GitHub</a>
  <button class="btn theme" onclick="tinToggleTheme()" title="Toggle theme" aria-label="Toggle theme">◐</button>
</div></header>
'''

FOOT = '''
<footer>Tin · a compiled language for servers, written in Tin · <a href="https://github.com/yasserreslan/tin">source</a> · <a href="https://github.com/yasserreslan/tin/milestone/2">milestone: Completeness</a></footer>
<script src="tin.js"></script>
</body>
</html>
'''

def syntax_page():
    side = ['<aside class="side"><details class="toc" open><summary>Contents</summary><nav>']
    for s in S:
        side.append(f'<h4>{s["n"]}</h4><a href="#{s["id"]}">{inline(s["title"])}</a><div class="sub">')
        for c in s["cards"]:
            side.append(f'<a href="#{c["id"]}">{inline(c["title"])}</a>')
        side.append("</div>")
    side.append("</nav></details></aside>")
    main = ['<main class="main"><header><h1>The syntax of Tin</h1>',
            '<p>Every construct on one page: a short explanation, an example, and a <b>Deeper</b> arrow when there is more to say. Tin 1 (edition 1) spelling.</p>',
            '<div class="notice"><span>⚙</span><div><b>Status.</b> This is the Tin 1 syntax. Today the compiler takes it with <code>tin build --edition 1</code>; the repository converts in <a href="https://github.com/yasserreslan/tin/issues/226">#226</a>, after which it is the default.</div></div>',
            '</header>']
    for s in S:
        main.append(f'<section class="part" id="{s["id"]}"><h2><span class="n">{s["n"]}</span>{inline(s["title"])}</h2><p class="intro">{inline(s["intro"])}</p>')
        for c in s["cards"]:
            main.append(card(c))
        main.append("</section>")
    main.append("</main>")
    return head("Tin · Syntax", "The syntax of Tin, construct by construct, with examples.", "syntax") + '<div class="docs">' + "".join(side) + "".join(main) + "</div>" + FOOT

HERO_CODE = '''
package main

import "anvil"
import "argo"

type Message struct {
	text str max 200
}

fn hello(q anvil.Req, w mut anvil.Out) ! {
	let reply = try within 200ms {
		try greet(q.PathParam("name"))
	}
	w.Json()
	argo.Put(mut w.Body, Message{text: reply})
}

fn main() ! {
	let r = anvil.NewRouter()
	r.Get(`/hello/{name}`, hello)
	try r.Serve(":8080")
}
'''

TILES = [
 ("values", "let · mut · units", "Literals and bindings", "Numbers, 200ms and 64kb, interpolated strings, names that stay and names that change."),
 ("types", "struct · enum · ?T", "Types", "Sized numbers, immutable strings, reference containers, enums read by match, nothing nil by accident."),
 ("functions", "fn · mut · [T]", "Functions", "Read-only parameters, call-site mut, methods, closures, monomorphized generics."),
 ("control", "for · match", "Control flow", "One loop with four shapes; match over values, ranges, enums and faults."),
 ("errors", "!T · try · catch", "Errors", "Faults are values that must be handled. wrap keeps the cause, guard turns a panic into one."),
 ("memory", "keep · arena", "Memory", "Request pools wiped per response; keep copies what must live on; the compiler checks it."),
 ("concurrency", "within · scope · select", "Concurrency", "Tasks inside boundaries; deadlines, budgets and cancellation flow down, never up."),
 ("policies", "with · use · on", "Policies and lifecycle", "Retry and trace as library policies; resources bound to scopes; typed lifecycle events."),
 ("server", "anvil · argo", "A service end to end", "Router, per-core database, deadline, JSON: the constructs together in forty lines."),
]

def index_page():
    tiles = "".join(f'<a class="tile" href="syntax.html#{i}"><span class="k">{html.escape(k)}</span><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></a>' for i, k, t, d in TILES)
    return head("Tin", "Tin is a compiled language for servers: no GC, one thread per core, faults you must handle, memory the compiler checks.", "index") + f'''
<section class="hero">
  <div>
    <img class="mark" src="logo.svg" alt="Tin">
    <h1>Tin.<br>A language <em>forged</em> for servers.</h1>
    <p class="lede">Compiled, self-hosted, no garbage collector. One thread per core, faults you cannot ignore, request memory the compiler proves never leaks. Written to be written by machines, read by people.</p>
    <div class="actions">
      <a class="btn primary" href="syntax.html">Read the syntax →</a>
      <a class="btn" href="https://github.com/yasserreslan/tin#readme">Install</a>
    </div>
    <div class="pills">
      <span class="pill"><b>Sn</b> element 50</span><span class="pill">Linux arm64 · amd64</span><span class="pill">no GC, no pauses</span><span class="pill">thread per core</span><span class="pill">self-hosted compiler</span><span class="pill">kqueue / epoll server</span>
    </div>
  </div>
  <div>{code(HERO_CODE)}</div>
</section>
<section class="grid">{tiles}</section>
''' + FOOT

with open(os.path.join(HERE, "syntax.html"), "w") as f: f.write(syntax_page())
with open(os.path.join(HERE, "index.html"), "w") as f: f.write(index_page())
print("sections", len(S), "cards", sum(len(s["cards"]) for s in S))
