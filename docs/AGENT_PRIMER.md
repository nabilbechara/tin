# Tin primer for agents (strict Tin, edition 1)

Tin is a self-hosted language that compiles to native code for Linux arm64 and
Linux x86-64 (production and benchmarks) and macOS arm64 (development only; see
docs/PORTING.md, "Platform roles"). AI writes all Tin code: optimize for speed and
robustness, not human ergonomics. Root: the repository checkout. Full reference:
docs/LANGUAGE.md (language), docs/STDLIB.md (packages), docs/TOOLING.md (commands),
docs/RUNTIME.md (memory, layouts, trusted code), docs/ERRORS.md (every diagnostic and its fix).

## Build and run
    tin FILE.tin                                   compile and run
    tin build FILE.tin -o bin/agent_NAME/prog      executable
    tin build --target linux-arm64 FILE.tin -o bin/linux/prog
    tin fix -edition 1 FILE.tin                    rewrite edition-0 (Go-like) code to edition 1
    docker run --rm -v "$PWD/bin/linux":/w tin-debian-arm64 /w/prog
When several agents work at once, each uses a frozen compiler (for example bin/tinc_agents, with
TIN_ROOT set to the root) and its own output dir bin/agent_NAME/. Never run tools/dev/v2test.sh,
never write bin/t, and never touch selfhost/, lib/runtime/, lib/anvil/, lib/argo/,
lib/hearth/, Makefile or seed/ unless your task says so. If you hit a compiler bug, do NOT fix
the compiler: write a minimal repro as a test, open an issue and work around it.

## Language (strict, edition 1)
- Files start `package main` (programs) or `package NAME` (lib/NAME/, imported with
  `import "NAME"`, called as `NAME.Func`). One `import "path"` per line, before any declaration;
  `import "./geom"` imports a local file or directory package; no aliases. Capitalized names,
  methods and fields are exported; lower-case ones are private to their package. Names are camelCase.
- Statements end at a newline (no semicolons); `//` comments only. Declarations: `fn`, `const`
  (package level, one name each), `let` (a name never reassigned), `mut` (one that is), `type`,
  `shape`, `use`, `on`. `let x = 1`, `mut n i64 = 0`, `let (a, b) = pair()`. Every local has an
  initializer. Go's func, var, short declarations, switch, increments, while, go and iota do not
  exist (`tin fix -edition 1` rewrites them).
- Types: i8 i16 i32 i64 u8 u16 u32 u64, f64, f32 (exact float32 semantics, 4 bytes in slices), bool,
  str (immutable bytes), [N]T arrays, []T (reference header; append mutates it in place and returns
  it, so `mut ys = xs` is one slice under two names: copy for a snapshot, sift.Clone; reading ys after append grew xs is E641), map[K]V (K = str, ints, bool, f64, or structs/enums of those, by value; insertion-ordered),
  struct (reference, never nil; == compares fields by value, same(a, b) is identity; a struct with a slice/map/func field cannot be compared, E237), ?T optional (may be nil; T a number, bool or reference: ?i64 is a boxed value, narrow it with != nil, store it in a global as keep(5)), fault (error;
  nil = ok), fn(A) R function values (top-level functions or literals, which may capture).
- No implicit conversions: i64(x), u8(x) (truncates: the low byte), f64(x), str(c) for a rune/byte,
  str(bytes []u8). Untyped constants adapt and must fit; constant arithmetic is exact (E223).
  Conditions must be bool. Integer + - * and negation panic on overflow (`integer overflow: +`; in a
  handler: 500, the core goes on), signed / panics on MIN / -1, division by zero panics, a shift
  count must be below the width, i64(f) panics out of range or on NaN. Where wrapping is the intent
  (hashes, checksums, PRNGs) write `h *%= prime`, `a +% b`, `a -% b`, or a whole `@wrap fn` kernel;
  never rely on wrap otherwise. Literals: 0x, 0b, 0o, 1_000; units `200ms` `5s` `1h`
  (nanoseconds, for tide and `within`) and `64kb` `4mb` (bytes).
- Structs: `type User struct {` one `name Type` per line `}`; literals always name fields:
  `User{id: 1, name: "a"}`. `@json("id") id i64` sets a JSON key. Methods:
  `fn (p Point) dist() f64`, `fn (p mut Point) move(dx i64)`.
- Errors: a function that can fail returns `!T` (`!(A, B)`, or `!` for no value). Inside it,
  `return v` succeeds and `fail "msg {x}"` / `fail err` leaves with a fault (zero values for the
  rest); `return v, nil` and `(T, fault)` result lists are compile errors. `let v = try f()` passes a
  fault upward; `let v = try f() wrap "loading {id}"` adds context; `let v = f() catch err { 0 }`
  handles it in place (the block's last expression is the value, or the block leaves);
  `let (v, err) = f()` also works. Ignoring a fault is a compile error, and `_` cannot discard one.
  Sentinels: package-level `let ErrNotFound = fault("not found")`; `fault.Is(err, ErrNotFound)`,
  `fault.Wrap(err, "ctx")`; runtime sentinels `fault.DeadlineExceeded`, `fault.Canceled`,
  `fault.LimitExceeded`, `fault.Overloaded`, `fault.Panic`.
- Loops: `for x in xs {}`, `for i, x in xs {}`, `for k, v in m {}`, `for i, c in text {}`,
  `for i in 0..n {}` (half-open; no bounds checks on `xs[i]` for `0..len(xs)`),
  `for i in (0..n).step(2) {}`, `for cond {}`, `for {}`; `outer: for ...` with `break outer` /
  `continue outer`. `x += 1` (there is no increment operator).
- `match` replaces switch and is an expression: `let s = match code { 200 => "ok" 404, 410 => "gone"
  500..600 => "server" n if n < 0 => "bad" _ => "other" }` (one arm per line). Arms are
  `pattern => expr` or `=> { block }`, or `return`/`break`/`continue`/`fail`/an assignment. On a
  fault, arms compare with fault.Is: `match err { nil => ... ErrNotFound => ... _ => ... }`.
- Optionals: `if p != nil { p.x }` narrows (also through && and ||, and `if p == nil { return }`);
  `if let u = find(id) { u.name }` binds. Narrow fields via a local. Using a ?T without narrowing is
  a compile error. Map reads of missing keys return the zero value; use `let (v, ok) = m[k]` to tell.
- Params are read-only unless declared `mut` (`fn (b mut Buf) add(...)`, `fn f(xs mut []i64)`).
  Modifying a non-mut param's contents (fields, elements, append, map store) is a compile error. A call
  writes `mut` before every argument for a mut parameter: `f(mut xs)`, `sift.Ints(mut xs)`,
  `argo.Put(mut buf, v)`; receivers and append/copy/delete take none.
- Enums: `type Shape enum {` one variant per line: `Circle(f64)`, `Rect(f64, f64)`, `Empty` `}`,
  built as `Shape.Circle(2.0)`, read with `match s { Circle(r) => ... Rect(w, h) => ... Empty =>
  ... }` (every variant or `_`; no field access). `==` by value; print as `Rect(3 4)`; JSON
  `{"Rect":{"$0":3,"$1":4}}` / `"Empty"`.
- Generics: `fn maxOf[T i64 | f64 | str](a T, b T) T`,
  `fn mapAll[T constraints.Any, U constraints.Any](xs []T, f fn(T) U) []U`,
  `type Stack[T constraints.Any] struct { items []T }` with `fn (s mut Stack[T]) push(x T)`;
  `maxOf(1, 2)` (inferred) or `maxOf[i64](1, 2)`. Fully specialized. Constraints are imported shapes
  such as `constraints.Any`, `constraints.Comparable` and `sift.Ordered`, or a union of concrete types.
- Shapes: `shape Reader {` one `Read(buf mut []u8) !i64` per line `}`, structural; composed shapes
  and named unions (`shape Num = i64 | f64`); generic shape calls are direct. `dyn S` opts into a
  two-word object/table value and one indirect method call; conversion allocates nothing.
- No threads and no shared mutable globals: every global is per core (each core thread has its own
  copy, initialized on every core). Concurrency is thread-per-core via hearth; messages via relay.
  Data every core only reads (a big lookup table) goes in `shared let t = build()`: one copy, built on
  core 0 before the cores start, immutable (E603 on any write through its name, E604 for a func/dyn/
  fault type); counters and flags every core changes are `shared let n = atomic.NewInt(0)` with
  `n.Add(1)`, `Load`, `Store`, `CompareSwap`.
  `main` runs on core 0 only, so assigning a global in `main` (or in a function it calls) in a program
  that starts cores (`anvil.Serve`, `hearth.Run`) is a compile error (E131): assign it in its
  initializer, in `on core.start` or in `once` (examples/percore.tin).
  Clients a handler uses are package-level `use` resources (per core, opened at core start, closed at
  stop): `use cache = redis.Open(redis.Options{Addr: quarry.Getenv("REDIS_ADDR")})`.
- Tasks: `scope s { ... s.spawn(fn() ! { ... }) ... }` waits for every child (spawned in a loop,
  each spawn captures its own loop variables); the first child fault cancels the rest and is the
  scope's fault. `let t = s.spawn(fn() !T {...})`,
  `try t.wait()`, `t.cancel()`. `let (a, b) = try parallel {` one call per line `}`. `select { let x =
  l.Recv() => ... after(1s) => ... canceled() => ... }`. `lane.New[T](n)` is a queue between tasks.
  `detach { flush(keep(event)) }` outlives the request.
- Boundary blocks give their last expression: `let p = try within 200ms { try api.Get(id) }`
  (deadline; waits fail with fault.DeadlineExceeded), `try limit memory 4mb, tasks 8 { ... }`,
  `guard { ... } catch err { ... }` (a panic becomes fault.Panic), `with policy.Retry(3) { ... }`
  (also policy.Cached, policy.Trace, policy.Bind). `return`/`break` cannot leave them.
- Lifecycle: `on app.start { try migrate() }`, `on app.stop`, `on core.start`, `on core.stop`;
  `once { ... }` runs the first time each core gets there; a function-level `use tx = db.Begin()`
  closes tx when the function returns.
- In anvil each request runs in its own task: a call that waits (tide.Wait, wire, quarry files, redis,
  mysql, postgres, websocket Read) lets the core serve others. Requests have a deadline
  (TIN_DEADLINE_MS, default 30 s); waits past it fail with "deadline exceeded".
- Streaming a response (SSE, a download, a long job): set the status and headers, then
  `try w.Stream()`, and `try w.WriteString(s)` / `try w.Write(bytes)` / `try w.Flush()` as data is ready;
  `w.Length(n)` first for a body of known size (else chunked), `try w.SendFile(path, 0, -1)` for a file
  (sendfile, never read into memory), `w.Closed()` to see a client that left, `w.Abort()` when the data
  source fails half way. A write fails when the client stops reading (TIN_WRITE_TIMEOUT_MS) or the request
  is cancelled: return then. The deadline restarts after each write. See examples/sse.tin.
- HTTP/2: anvil also serves h2c (prior knowledge, or `Upgrade: h2c`) on the same port; handlers,
  the Router and streaming are unchanged, each stream in its own task. `w.Trailer(k, v)` adds a
  trailer (HTTP/2, or after the last chunk of an HTTP/1.1 chunked stream); `q.Proto()` is
  "HTTP/2.0", "HTTP/1.1" or "HTTP/1.0". A unary gRPC service: examples/grpc.tin.
- Services route with `let r = anvil.NewRouter()` in main: ``r.Get(`/users/{id}`, user)`` (Post, Put,
  Patch, Delete, Head, Options, Handle(method, ...), Any), `q.PathParam("id")` (%-decoded), a last
  `{path...}` or `*` for the rest; patterns with {...} are raw strings. Static beats {name} beats the
  rest whatever the order; a wrong method gets 405 + Allow, HEAD falls back to GET, a trailing slash
  is significant. `r.Use(mw)`, mw a top-level
  `fn(q anvil.Req, w mut anvil.Out, next fn(anvil.Req, mut anvil.Out))` that calls `next(q, mut w)`;
  it hands data on with `w.SetValue(k, v)` / `w.Value(k)`. Groups:
  `r.Route("/api", fn(g mut anvil.Router) { g.Use(auth) ... })`, `r.Mount("/v2", sub)`;
  `r.NotFound(h)`, `r.MethodNotAllowed(h)`. `try r.Serve(":8080")` fails first on a bad or
  conflicting pattern (`r.Check()`). Test without a server: `let w = r.Run("GET", "/users/7", "")`
  then `w.Code()`, `w.Header("Allow")`, `str(w.Body)`; `r.Match(method, path)` is the pattern that
  would serve. HTTPS: `try r.ServeTLS(":8443", certPEM, keyPEM)` (or `anvil.ServeTLS(addr, certPEM,
  keyPEM, h)`): PEM text, chain leaf first, RSA or ECDSA key; `q.TLSConn()` is the request's TLS
  connection; `websocket.Accept` works on it (wss://). examples/https_server.tin.
- Memory: no GC. Allocations during a request go to the core's request pool (wiped per request);
  globals live in the long-lived ingot heap. Storing request memory into a global (or anything a global
  holds) without `keep(x)` is a compile error. keep() deep-copies into the ingot heap.
- `make([]T, n)` starts elements at zero values ("" for str, an empty slice for []T). With a non-zero
  length it is a compile error for struct, map and func elements: use make([]T, 0, n) and append.
- Builtins: len cap append make copy delete min max panic fail keep bound reveal; say.Line(a, b...)
  prints space-separated + newline; say.Text(...) no spaces/newline; say.Out(fmt, ...) printf;
  say.Fmt(fmt, ...) -> str; say.Str(x) -> str; verbs %d %s %q %v %x %f %5.2f %-4s etc. Floats print
  like Go's %v.
- Strings interpolate: "user {u.name} has {n} items", "{price:.2} {id:x} [{name:-8}]"; {{ and }} are
  braces; no quotes inside {...}; `raw` backquote strings do not interpolate (use them for text with
  braces of its own, like the route pattern `/users/{id}`).
- Queries: where a parameter has type `query`, a literal keeps its values apart from its text:
  `db.Query("SELECT name FROM users WHERE id = {id}")` binds id, `cache.Do("SET user:{id} {body}")`
  sends three arguments. Passing a `str` there is a compile error; values must be integers, floats,
  str, bool or []u8, with no format spec.
- Bounded and secret values: `name str max 100` (a `bound(x)` call checks an unbounded value and fails
  with fault.LimitExceeded; argo.Get enforces bounds while reading); `token secret str` is kept out of
  say, faults, panics and argo at compile time; `reveal(x)` is the plain value; compare secrets with
  `seal.Equal`.
- Bounds checks are always on (removed when provably safe: `for x in xs`, `for i in 0..len(xs)`).
  Panics print the message, index and length, and a backtrace.
- JSON: argo.Put(mut buf, v) encodes any value (encoder generated per type);
  `argo.Get(text, mut v) catch err { ... }` decodes into a struct, slice or map (a fault leaves v
  unchanged; invalid UTF-8 and lone surrogates are faults); `argo.GetStrict` also rejects unknown and
  duplicate members. Field names are the struct field names, or their `@json("...")`.

## Trusted code (lib/*.tin only)
Standard-library files may use cast(T, x) between i64 and refs, raw word indexing on an i64 pointer p[i]
(8-byte words), load8(p)/store8(p, v), __ld(p, sizelog2), __st(p, v, sizelog2), `shared let` (one
process-wide value, not per core: the runtime's own state, set before cores start or synchronized by
the code) and declarations of libc functions. A str is a pointer to [len word][bytes][NUL]: bytes at
cast(i64, s)+8. A slice is a pointer to a header [len, cap, data, region]. C int returns: only low 32
bits are defined -> i64(i32(x)). Variadic C functions need `...` in the declaration. OS constants and
differences go in NAME_darwin.tin / NAME_linux.tin (see docs/PORTING.md); never hard-code an errno or
flag value in shared code. Runtime helpers you may call: rt_str_from_raw(p, n) str, rt_str_new(n) i64
(len set, bytes at +8), rt_append_str(cast(i64, b), s), rt_slice_grow(h, need, esz), rt_alloc(n),
rt_ingot_alloc(n), rt_core_id(), rt_errno(). Prefer plain Tin over raw tricks unless speed demands it.
Library packages are overflow-checked like user code: mark intended wraps (`+%`, `-%`, `*%`, or `@wrap fn`
for a hash, PRNG or constant-time crypto kernel), and write the magnitude of a negative i64 as
`u64(0 -% v)` (0 - v panics for the most negative value). Only lib/runtime/ keeps machine arithmetic.
Keep comments one line, ending with a period.

## Standard library (import instead of re-implementing)
say(fmt) fault(error chains) twine(strings) glyph(utf8) mint(strconv) argo(JSON) anvil(HTTP/1.1 and HTTP/2 server,
router, HTTPS) wire(TCP, HTTP(S) client) tls(TLS 1.3 client and server) hearth(cores) relay(cross-core messages)
task(deadline, cancellation) lane(queues between tasks) policy(with policies) tide(time)
quarry(os/files/env) trail(paths) lever(flags/args) sift(sort/search) atlas(maps) cairn(containers)
gauge(math) dice(random) stamp(non-crypto hashes) squash(gzip, zlib, snappy, lz4, zstd) seal(SHA-2, HMAC, HKDF, AES-GCM,
ChaCha20-Poly1305, X25519, P-256, base64, hex, RSA-OAEP, constant-time compare) ore(bytes)
flume(buffered I/O) herald(logging) crucible(testing) redis(Redis client) kafka(Kafka client) mysql(MySQL client)
postgres(PostgreSQL client) websocket(WebSocket server via anvil, and client). Signatures:
docs/STDLIB.md.

## Tests in your own packages
Go style: `NAME_test.tin` next to the code (same package), `fn TestX(t mut crucible.T)` with
`crucible.Equal(mut t, "label", got, want)`, `t.True`, `t.NoFault`, `t.HasFault`, `t.Error(msg)`;
`fn BenchmarkX(b mut crucible.B)` loops `b.N` times. Run with `tin test ./dir` (`-bench` too).

## Verification standard
For every function, write an equivalent Go program (stdlib only) under bench/ref/NAME/ (its own
`package main` file; run with `go run`) that prints the same lines for the same inputs, and diff the
Tin output against it. Mismatches are bugs in your package (or compiler bugs: then repro + note).
Include edge cases: empty inputs, max/min integers, invalid input producing faults, unicode.
Anything that touches the OS must also run on Linux (cross-compile and run in tin-debian-arm64).

## Deliverables per package
- lib/NAME/NAME.tin (package NAME) with a one-line comment on every exported function.
- tests/v2/NAME.tin: a `package main` program exercising every function, printing results with
  say.Line (deterministic output; temporary files under /tmp/tin-test-*). Then save the expected
  output: run it, sort the output, and write it to tests/v2/NAME.out
  (`bin/agent_X/prog | sort > tests/v2/NAME.out`) only after verifying every line by hand is correct.
- The package's README: API list, design notes, known gaps.
