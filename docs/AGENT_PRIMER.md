# Tin primer for agents (strict Tin)

Tin is a self-hosted, Go-like language that compiles to native code for macOS arm64 and
Linux arm64 (x86-64 in progress). AI writes all Tin code: optimize for speed and
robustness, not human ergonomics. Root: /Users/yasserreslan/Desktop/tin. Full reference:
docs/LANGUAGE.md (language), docs/STDLIB.md (packages), docs/TOOLING.md (commands),
docs/RUNTIME.md (memory, layouts, trusted code).

## Build and run
    tin FILE.tin                                   compile and run
    tin build FILE.tin -o bin/agent_NAME/prog      executable
    tin build --target linux-arm64 FILE.tin -o bin/linux/prog
    docker run --rm -v "$PWD/bin/linux":/w tin-debian-arm64 /w/prog
When several agents work at once, each uses a frozen compiler (for example bin/tinc_agents, with
TIN_ROOT set to the root) and its own output dir bin/agent_NAME/. Never run tools/v2test.sh,
never write bin/t, and never touch selfhost/, lib/runtime*.tin, lib/anvil*.tin, lib/argo.tin,
lib/hearth.tin, Makefile or seed/ unless your task says so. If you hit a compiler bug, do NOT fix
the compiler: write a minimal repro to notes/compiler_bugs_NAME.md and work around it.

## Language (strict)
- Files start `package main` (programs) or `package NAME` (lib/NAME.tin, imported with
  `import "NAME"`, called as `NAME.Func`). `import "./geom"` imports a local file or directory
  package. Capitalized names, methods and fields are exported; lower-case ones are private to their package.
- Types: i8 i16 i32 i64 u8 u16 u32 u64, f64, bool, str (immutable bytes), [N]T arrays, []T (reference
  header; append mutates it in place and returns it), map[K]V (K = str or integer), struct (reference,
  never nil; == compares identity), ?T optional (may be nil), fault (error; nil = ok), func(...) values
  (top-level functions or literals without captures).
- No implicit conversions: i64(x), u8(x), f64(x), str(c) for a rune/byte, str(bytes []u8). Untyped
  constants adapt and must fit. Conditions must be bool. Integer overflow wraps; division by zero
  panics; shift counts are taken mod 64. Literals: 0x, 0b, 0o, 1_000.
- Errors: a function that can fail returns `!T` (`!(A, B)`, or `!` for no value). Inside it, `return v`
  succeeds and `fail "msg"` / `fail err` leaves with a fault (zero values for the rest); `return v, nil` and
  `(T, fault)` result lists are compile errors. `v := try f()` passes a fault upward; `v := f() catch err { 0 }`
  handles it in place (the block's last expression is the value, or the block leaves); `v, err := f()` also
  works. Ignoring a fault is a compile error, and `_` cannot discard one. `fail("msg")` and
  `say.Fault("fmt %d", x)` make fault values.
- Optionals: `if p != nil { p.x }` narrows (also through && and ||, and `if p == nil { return }`). Narrow fields via a local. Using a ?T
  without narrowing is a compile error. Map reads of missing keys return the zero value; use
  `v, ok := m[k]` to tell.
- Params are read-only unless declared `mut` (`func (b mut Buf) Add(...)`, `func f(xs mut []i64)`).
  Modifying a non-mut param's contents (fields, elements, append, map store) is a compile error. A call
  writes `mut` before every argument for a mut parameter: `f(mut xs)`, `sift.Ints(mut xs)`,
  `argo.Put(mut buf, v)`; receivers and append/copy/delete take none.
- No `go` statements, no shared mutable globals: every global is per core (each core thread has its own
  copy, initialized on every core). Concurrency is thread-per-core via hearth; messages via relay.
- Memory: no GC. Allocations during a request go to the core's request pool (wiped per request);
  globals live in the long-lived ingot heap. Storing request memory into a global (or anything a global
  holds) without `keep(x)` is a compile error. keep() deep-copies into the ingot heap.
- `make([]T, n)` starts elements at zero values ("" for str, an empty slice for []T). With a non-zero
  length it is a compile error for struct, map and func elements: use make([]T, 0, n) and append.
- Builtins: len cap append make copy delete panic fail keep; say.Line(a, b...) prints space-separated
  + newline; say.Text(...) no spaces/newline; say.Out(fmt, ...) printf; say.Fmt(fmt, ...) -> str;
  say.Str(x) -> str; verbs %d %s %q %v %x %f %5.2f %-4s etc. Floats print like Go's %v.
- for i := 0; i < n; i++ {}, for cond {}, for {}, for i, x := range slice/str/map {}, switch x { case a, b: }.
  Methods: `func (p Point) Name() str`. Multiple returns. Composite literals T{F: v}, []T{...}, map[K]V{...}.
- Generics: `func Max[T i64 | f64 | str](a T, b T) T`, `func Map[T any, U any](xs []T, f func(T) U) []U`,
  `type Stack[T any] struct { items []T }` with `func (s mut Stack[T]) Push(x T)`; `Max(1, 2)` (inferred)
  or `Max[i64](1, 2)`. Fully specialized; `var zero T` is the zero value. Constraints: any, comparable,
  or a union of concrete types.
- Bounds checks are always on (removed when provably safe: range loops, i < len(s) loops). Panics print
  the message, index and length, and a backtrace.
- JSON: argo.Put(mut buf, v) encodes any value (encoder generated per type); `err := argo.Get(text, mut v)`
  decodes into a struct, slice or map. Field names are the struct field names.

## Trusted code (lib/*.tin only)
Standard-library files may use cast(T, x) between i64 and refs, raw word indexing on an i64 pointer p[i]
(8-byte words), load8(p)/store8(p, v), __ld(p, sizelog2), __st(p, v, sizelog2), `shared var` (one process-wide variable, not per core: the runtime's own state, set before cores
start or synchronized by the code) and
`extern func name(a i64, ...) i64` for libc. A str is a pointer to [len word][bytes][NUL]: bytes at
cast(i64, s)+8. A slice is a pointer to a header [len, cap, data, region]. C int returns: only low 32
bits are defined -> i64(i32(x)). Variadic C functions need `...` in the extern. OS constants and
differences go in NAME_darwin.tin / NAME_linux.tin (see docs/PORTING.md); never hard-code an errno or
flag value in shared code. Runtime helpers you may call: rt_str_from_raw(p, n) str, rt_str_new(n) i64
(len set, bytes at +8), rt_append_str(cast(i64, b), s), rt_slice_grow(h, need, esz), rt_alloc(n),
rt_ingot_alloc(n), rt_core_id(), rt_errno(). Prefer plain Tin over raw tricks unless speed demands it.
Keep comments one line, ending with a period.

## Standard library (import instead of re-implementing)
say(fmt) twine(strings) glyph(utf8) mint(strconv) argo(JSON) anvil(HTTP server) wire(TCP, HTTP client)
hearth(cores) relay(cross-core messages) tide(time) quarry(os/files/env) trail(paths) lever(flags/args)
sift(sort/search) cairn(containers) gauge(math) dice(random) stamp(non-crypto hashes) seal(SHA-256,
HMAC, base64, hex) ore(bytes) flume(buffered I/O) herald(logging) crucible(testing). Signatures:
docs/STDLIB.md.

## Verification standard
For every function, write an equivalent Go program (stdlib only) under bench/ref/NAME/ (its own
`package main` file; run with `go run`) that prints the same lines for the same inputs, and diff the
Tin output against it. Mismatches are bugs in your package (or compiler bugs: then repro + note).
Include edge cases: empty inputs, max/min integers, invalid input producing faults, unicode.
Anything that touches the OS must also run on Linux (cross-compile and run in tin-debian-arm64).

## Deliverables per package
- lib/NAME.tin (package NAME) with a one-line comment on every exported function.
- tests/v2/NAME.tin: a `package main` program exercising every function, printing results with
  say.Line (deterministic output; temporary files under /tmp/tin-test-*). Then save the expected
  output: run it, sort the output, and write it to tests/v2/NAME.out
  (`bin/agent_X/prog | sort > tests/v2/NAME.out`) only after verifying every line by hand is correct.
- A short section appended to notes/stdlib_NAME.md: API list, design notes, known gaps.
