# Tin standard library

Generated from the comments in `lib/*/` by `tools/gendoc.py`.

| package | role (Go equivalent) |
|---|---|
| [say](#say) | formatting and printing (fmt) |
| [fault](#fault) | fault chains and standard sentinels (errors) |
| [argo](#argo) | JSON (encoding/json) |
| [io](#io) | streaming shapes (io) |
| [anvil](#anvil) | HTTP/1.1 server (net/http) |
| [hearth](#hearth) | cores and threads (runtime) |
| [relay](#relay) | messages between cores (channels) |
| [task](#task) | deadline and cancellation of the running code (context) |
| [wire](#wire) | TCP and HTTP client (net) |
| [twine](#twine) | strings (strings) |
| [glyph](#glyph) | UTF-8 and Unicode (unicode/utf8, unicode) |
| [mint](#mint) | number and string conversion (strconv) |
| [gauge](#gauge) | math (math) |
| [bits](#bits) | bit counting and manipulation (math/bits) |
| [link](#link) | URLs and their escaping (net/url) |
| [ore](#ore) | byte slices (bytes) |
| [flume](#flume) | buffered I/O (bufio) |
| [quarry](#quarry) | files, environment, process (os) |
| [trail](#trail) | paths (path/filepath) |
| [lever](#lever) | command-line flags (flag) |
| [tide](#tide) | time (time) |
| [dice](#dice) | random numbers (math/rand) |
| [sift](#sift) | sorting, searching and the generic slice functions (sort, slices, cmp) |
| [atlas](#atlas) | functions on maps (maps) |
| [cairn](#cairn) | containers (container/heap, sets, LRU) |
| [stamp](#stamp) | hashes and checksums (hash/*) |
| [squash](#squash) | compression: DEFLATE, gzip, zlib, Snappy, LZ4, Zstandard (compress/flate, compress/gzip, compress/zlib) |
| [seal](#seal) | crypto and encodings (crypto/sha256, hmac, encoding/hex, base64) |
| [herald](#herald) | logging (log/slog) |
| [crucible](#crucible) | testing helpers (testing) |
| [constraints](#constraints) | named generic constraint shapes |
| [policy](#policy) | with policies and slots (context values, retry/cache/trace middleware) |
| [redis](#redis) | Redis client (go-redis) |
| [mysql](#mysql) | MySQL client (database/sql with go-sql-driver/mysql) |
| [postgres](#postgres) | PostgreSQL client (database/sql with pgx) |
| [kafka](#kafka) | Kafka client (franz-go, sarama) |
| [websocket](#websocket) | WebSocket server and client (gorilla/websocket) |

## say

Built into the compiler (formatting by static type, no reflection): `say.Line(a, b...)`, `say.Text(...)`, `say.Out(format, ...)`, `say.Fmt(format, ...) str`, `say.Str(x) str`, `say.Fault(format, ...) fault`, `say.To(fd, ...)`, `say.LineTo(fd, ...)`. See docs/LANGUAGE.md.

## fault

Package fault is fault chains and the standard sentinels, like Go's errors package: Wrap adds context and keeps the cause, Is walks the chain comparing identity, Join keeps several faults reachable. The runtime's sentinels are the variables Canceled, DeadlineExceeded, LimitExceeded, Overloaded, Draining and Panic; a package declares its own as `let ErrX = fault("msg")`. A function that makes a fault is declared ! here: its fault is the value (fail it, keep it in a variable, or test it). Layout and identities: notes/interface_faults.md.

- `Wrap(err fault, msg str) !`: Wrap is err with msg in front ("msg: cause"), err reachable as its cause; nil when err is nil.
- `Is(err fault, target fault) bool`: Is reports whether err or a fault in its chain (causes and joined faults) is target: the same sentinel, or the same fault.
- `Cause(err fault) !`: Cause is the fault err wraps; nil when it wraps none (and for nil and a Join).
- `Join(errs []fault) !`: Join is one fault holding every non-nil fault of errs, each reachable by Is, the messages on separate lines; nil when all are nil.
- `Message(err fault) str`: Message is the full message of err ("outer: inner" for a wrapped fault), "" for nil.
- `Backtrace(err fault) str`: Backtrace is the backtrace text of the panic in err's chain (a fault.Panic), "" for none.

## argo

Package argo writes JSON. argo.Put(b, v) appends v to the []u8 buffer b; the compiler generates a dedicated encoder for v's type (fields in declaration order, no reflection, no allocation). The w* writers below are what those encoders call. argo.Get(s, v) fills v from the JSON text s with a decoder generated the same way; it returns a fault for arrays and objects nested more than 512 deep, as each level takes stack.

- `Put(b mut []u8, v i64)`: Put appends v as JSON to b. The compiler replaces every call with a typed encoder.
- `Str(b mut []u8, s str)`: Str appends s as a JSON string.
- `Raw(b mut []u8, s str)`: Raw appends already-encoded JSON text.
- `type Parser struct`

## io

Package io declares the streaming shapes: a type satisfies Reader, Writer, Closer or Seeker by having the methods, with no declaration, and compositions like ReadWriteCloser by satisfying every listed shape. The helpers (Copy, ReadAll, Pipe, MultiWriter, ...) and EOF as a sentinel fault land with the io port (roadmap #141); the byte, rune and string shapes (ByteReader, RuneReader, StringWriter, ...) and Go's ReaderFrom and WriterTo (which need dyn) are not declared yet.

- `shape Reader { Read(buf mut []u8) !i64 }`: Reader is anything with Read: it fills buf and returns how many bytes it wrote.
- `shape Writer { Write(data []u8) !i64 }`: Writer is anything with Write: it takes data and returns how many bytes it took.
- `shape Closer { Close() !i64 }`: Closer is anything with Close.
- `shape Seeker { Seek(offset i64, whence i64) !i64 }`: Seeker is anything with Seek: offset is relative to whence (0 start, 1 current, 2 end).
- `shape ReaderAt { ReadAt(buf mut []u8, off i64) !i64 }`: ReaderAt is a reader that does not move a position: it reads at off.
- `shape WriterAt { WriteAt(data []u8, off i64) !i64 }`: WriterAt is a writer that does not move a position: it writes at off.
- `shape ReadWriter`: ReadWriter reads and writes.
- `shape ReadCloser`: ReadCloser reads and closes.
- `shape WriteCloser`: WriteCloser writes and closes.
- `shape WriteSeeker`: WriteSeeker writes and seeks.
- `shape ReadSeekCloser`: ReadSeekCloser reads, seeks and closes.
- `shape ReadWriteCloser`: ReadWriteCloser reads, writes and closes.
- `shape ReadSeeker`: ReadSeeker reads and seeks.
- `shape ReadWriteSeeker`: ReadWriteSeeker reads, writes and seeks.

## anvil

Package anvil is an HTTP/1.1 server: one event loop per core (kqueue), share-nothing.

Core 0 accepts connections and deals them round-robin to every core through a pipe; from then on a connection belongs to one core for its whole life. Each core reads into one scratch buffer, parses requests in place, runs the handler, writes every response of the batch with one write, and wipes its request pool. Idle connections hold no buffers, only a 96-byte record.

```tin
type Msg struct {
	message str
}

fn handle(q anvil.Req, w mut anvil.Out) {
	w.Type("application/json")
	argo.Put(mut w.Body, Msg{message: "hi"})
}

fn main() {
	anvil.Serve(":8080", handle) catch err {
		say.Line("server:", err)
	}
}
```

A Router picks the handler by method and path pattern, and runs middleware around it. Patterns match whole segments: "users" itself, {id} any one non-empty segment, and a last {path...} or * the rest of the path. Static segments win over {name}, and {name} over the rest, segment by segment, whatever the order of registration. A path whose routes take other methods gets 405 with Allow, any other miss 404; HEAD falls back to GET. A trailing slash is part of the path: /users/ and /users are different routes. Write patterns with {...} as raw strings: in "..." the braces would interpolate.

```tin
fn user(q anvil.Req, w mut anvil.Out) {
	let id = q.PathParam("id")
	w.Text("user {id}")
}

fn logged(q anvil.Req, w mut anvil.Out, next fn(anvil.Req, mut anvil.Out)) {
	next(q, mut w)
	herald.Log(herald.LInfo, "request", []str{
		"method", q.Method, "route", q.Pattern(), "status", say.Str(w.Code()), "client", q.ClientIP(),
	})
}

fn main() {
	let r = anvil.NewRouter()
	r.Use(logged)
	r.Get(`/users/{id}`, user)
	r.Route("/admin", fn(g mut anvil.Router) {
		g.Use(logged)
		g.Delete(`/users/{id}`, user)
	})
	r.Serve(":8080") catch err {
		say.Line("server:", err)
	}
}
```

The middleware writes one herald line per request, with the client's address as client:

```text
2026-10-05T09:00:00.000Z INFO core=0 request method=GET route=/users/{id} status=200 client=203.0.113.7
```

q.ClientIP() is the connection's peer unless the peer is one of the TrustedProxies: behind a proxy of yours, call TrustedProxies first, or every line carries the proxy's address.

- `TrustedProxies(cidrs []str) !`: TrustedProxies sets the proxies whose X-Forwarded-For and Forwarded headers ClientIP believes, as networks ("10.0.0.0/8", "fd00::/8") or single addresses. Call it before Serve. With none (the default) ClientIP is the connection's peer: the headers are written by the client and prove nothing unless a proxy you run replaced them.
- `(q Req) RemoteAddr() str`: RemoteAddr is the address the request's connection comes from, "ip:port" ("[ip]:port" for IPv6, and an IPv4 client of an IPv6 listener as IPv4), or "" for a request made in the process. It is read once per connection. A request replayed from a capsule (#242) gets the address it was recorded with, "" when the capsule is older than that (schema 1).
- `(q Req) ClientIP() str`: ClientIP is the client's IP address: the connection's peer, or, when the peer is one of the TrustedProxies, the rightmost address of X-Forwarded-For (else Forwarded's for=) that is not a trusted proxy. A malformed entry ends the walk at the peer. "" for a request made in the process.
- `type Req struct`: Req is the request being served. Its strings live in the request pool: keep() them to store them anywhere long-lived.
- `type Out struct`: Out is the response being built. Body is the response body; the status defaults to 200 and the content type to text/plain.
- `Serve(addr str, h fn(Req, mut Out)) !`: Serve listens on addr (":8080", "127.0.0.1:8080") and serves h on every core. It returns only if the server cannot start. TIN_CORES overrides the number of cores.
- `ServeN(addr str, n i64, h fn(Req, mut Out)) !`: ServeN is Serve on exactly n cores.
- `Drain(grace i64)`: Drain starts the graceful shutdown from code, as SIGTERM does (#238): listeners close, the requests in flight finish, and after grace nanoseconds what is left is cancelled with fault.Draining; then the cores stop, Serve returns and the stop events run. Any core may call it; it does nothing outside a server or once a shutdown started.
- `Timeouts(header i64, read i64, idle i64, write i64)`: Timeouts sets the connection timeouts in milliseconds; 0 turns one off. header: a request's line and headers must arrive within it (slowloris); read: the whole request, body included; idle: a keep-alive connection with no request in progress; write: a response the client stops reading (no progress for this long). A connection is closed when one passes; a request whose handler is running is governed by Deadline instead. Defaults 10000, 60000, 60000 and 30000; TIN_HEADER_TIMEOUT_MS, TIN_READ_TIMEOUT_MS, TIN_IDLE_TIMEOUT_MS and TIN_WRITE_TIMEOUT_MS override them. Call before Serve.
- `type Load struct`: Load is what an admission policy sees of the core a new request arrived on: its waiting request tasks, live connections, bytes buffered for requests still arriving, how many requests were refused so far, the request-pool bytes its requests hold beyond each one's first chunk (what TIN_REQUEST_MEMORY counts), and the bytes its long-lived (ingot) heap holds (design_semantics §11).
- `Admit(p fn(Load) bool)`: Admit sets the admission policy (call before Serve): after the built-in limits, p decides each new request before its handler runs; false answers 503 with Retry-After: 1 without running the handler. Every core calls p with its own Load.
- `Limits(maxBody i64, maxBuffered i64, maxConns i64)`: Limits sets the largest request body in bytes (413 past it), the bytes of requests still arriving that one core may buffer (a new partial request past it gets 503 and close), and the connections per core (more are closed at accept; 0: no limit). Defaults 64 MiB, 256 MiB and 16384; TIN_MAX_BODY, TIN_MAX_BUFFERED and TIN_MAX_CONNS override them. Call before Serve.
- `Deadline(ms i64)`: Deadline makes every request's waits (tide.Wait, client calls) fail with "deadline exceeded" once ms have passed since the request started (0: no deadline; call before Serve). TIN_DEADLINE_MS sets it too; the default is 30000.
- `(q Req) Header(name str) str`: Header returns the value of the request header name (any case), or "". A chunked request's trailer fields are read after the header block's.
- `(q Req) Hijack() !i64`: Hijack takes the request's connection out of HTTP for a protocol of its own (the websocket package uses it): the responses before this request are written, the core stops reading the connection and the request's deadline no longer applies. It returns the non-blocking descriptor, for the caller's I/O until the handler returns; then anvil closes it. The handler's Out is not sent.
- `(w mut Out) Stream() !`: Stream switches the response to streaming. The status, content type and headers set so far are sent with the first Write or Flush (set them before). The body is then written with Write and Flush, in chunks (Transfer-Encoding: chunked), or as a plain body of the size Length gave; an HTTP/1.0 client, which cannot read chunks, gets the body up to the end of the connection. Each write waits for a slow client within the write timeout (TIN_WRITE_TIMEOUT_MS), and the request deadline (TIN_DEADLINE_MS) counts from the last write, so a stream lives as long as it keeps writing. Calling Stream again does nothing.
- `(w mut Out) Length(n i64) !`: Length sets the size of the streamed body in bytes: the response then has a Content-Length header instead of chunks, and the handler must write exactly n bytes. Call it after Stream and before the first Write or Flush.
- `(w mut Out) Write(b []u8) !`: Write sends b as part of the body, after the head if that is not out yet. It waits while the client does not read, and fails when the client has closed the connection, stopped reading for the write timeout, or the request was cancelled: the handler should stop then. Text appended to the body with Text or argo.Put(mut w.Body, v) is sent by the next Write or Flush.
- `(w mut Out) WriteString(s str) !`: WriteString is Write for a str.
- `(w mut Out) Flush() !`: Flush sends the head if it is not out yet and what Text or argo.Put put in the body so far, as one chunk: with it a handler makes a client see an event now.
- `(w mut Out) Abort()`: Abort ends a stream the handler cannot finish (its data source failed halfway): the connection closes without the last chunk, so the client sees an incomplete response instead of a short one that looks complete. Before the head is sent, the response is an ordinary one again.
- `(w Out) Closed() bool`: Closed reports whether the client has closed the connection (a stream's handler asks between events: a write only fails once the client's reset arrives).
- `(w mut Out) SendFile(path str, off i64, n i64) !`: SendFile sends n bytes of the file at path, from byte off, as the body (n < 0: to the end of the file). As the whole body of a response that is not streaming yet it starts the stream with a Content-Length of n, so a download is `w.SendFile(path, 0, -1)`; in a stream already begun, the bytes go out as chunks or as part of the Content-Length body. The file goes to the socket with sendfile(2) in pieces of 1 MiB on a helper thread, so it is never read into the request pool and a slow disk does not stop the core; each piece waits for a slow client within the write timeout.
- `(q Req) Body() str`: Body returns the request body (a chunked one decoded).
- `(q Req) BodyBound(n i64) !str`: BodyBound returns the request body when it is at most n bytes, and otherwise fails with fault.LimitExceeded before copying any of it: the compiler calls it for q.Body() into a bounded type (try bound(q.Body()), #240).
- `(q Req) Param(name str) str`: Param returns query parameter name, %-decoded, or "".
- `(q Req) PathParam(name str) str`: PathParam returns path parameter name of the Router route that matched ({name}, {name...}, or "*" for a last *), %-decoded, or "".
- `(q Req) Pattern() str`: Pattern returns the pattern of the Router route serving the request ("/users/{id}"), or "" (no Router, or a 404 or 405 answer).
- `(w mut Out) Status(code i64)`: Status sets the response status code.
- `(w mut Out) Type(t str)`: Type sets the Content-Type header. CR, LF and NUL in t become spaces, so a value taken from the request cannot add header lines.
- `(w mut Out) Head(k str, v str)`: Head adds a response header. A name that is not an HTTP token is ignored, and so are Content-Length, Transfer-Encoding and Connection: anvil writes the framing itself. CR, LF and NUL in the value become spaces, so a value taken from the request cannot add header lines or a body (response splitting), as Go's net/http does.
- `(w mut Out) Text(s str)`: Text appends s to the body.
- `(w mut Out) Json()`: Json sets the JSON content type; the body is then written with argo.Put(mut w.Body, v).
- `(w Out) Code() i64`: Code returns the response status set so far (200 unless Status changed it).
- `(w Out) Header(k str) str`: Header returns response header k as set so far (Type sets Content-Type, Head the rest), or "".
- `(w mut Out) SetValue(key str, value str)`: SetValue stores value under key for the rest of the request: middleware hand data (a user id, a request id) to the handlers after them this way. Value reads it back.
- `(w Out) Value(key str) str`: Value returns what SetValue stored under key in this request, or "".
- `OnRelay(h fn(i64, str))`: OnRelay makes every core run h(from, msg) for each relay message it receives (call before Serve). Handlers run between requests, with their own request pool.
- `OnTick(ms i64, h fn(i64))`: OnTick makes every core run h(core) every ms milliseconds (call before Serve).
- `type Router struct`: Router sends each request to the handler routed for its method and path pattern, through the middleware added with Use. Build it in main (or in a function a global's initializer calls), then Serve it, or try requests on it with Run.
- `NewRouter() Router`: NewRouter makes an empty router: every request gets 404 until routes are added.
- `(r mut Router) Get(pattern str, h fn(Req, mut Out))`: Get routes GET requests for pattern to h, and HEAD requests unless Head routes them.
- `(r mut Router) Post(pattern str, h fn(Req, mut Out))`: Post routes POST requests for pattern to h.
- `(r mut Router) Put(pattern str, h fn(Req, mut Out))`: Put routes PUT requests for pattern to h.
- `(r mut Router) Patch(pattern str, h fn(Req, mut Out))`: Patch routes PATCH requests for pattern to h.
- `(r mut Router) Delete(pattern str, h fn(Req, mut Out))`: Delete routes DELETE requests for pattern to h.
- `(r mut Router) Head(pattern str, h fn(Req, mut Out))`: Head routes HEAD requests for pattern to h (without it, they go to the GET route).
- `(r mut Router) Options(pattern str, h fn(Req, mut Out))`: Options routes OPTIONS requests for pattern to h.
- `(r mut Router) Handle(method str, pattern str, h fn(Req, mut Out))`: Handle routes requests with method (any HTTP method name, like "PROPFIND") for pattern to h.
- `(r mut Router) Any(pattern str, h fn(Req, mut Out))`: Any routes requests for pattern with every method to h; a route for the request's own method on the same pattern wins over it.
- `(r mut Router) Use(mw fn(Req, mut Out, fn(Req, mut Out)))`: Use adds middleware mw to r. Middleware run in the order added, around every route of r and of the routers mounted in it, and around their 404 and 405 answers. Each gets next, the rest of the chain, and decides whether and when to call it.
- `(r mut Router) Route(prefix str, build fn(mut Router))`: Route groups routes under prefix ("/api"): build adds them to a new router mounted there.
- `(r mut Router) Mount(prefix str, sub Router)`: Mount serves sub's routes under prefix: "/api" and "/users" make "/api/users", and "/api" and "" make "/api". r's middleware run before sub's, and sub's 404 and 405 answers (with its middleware) cover the paths under prefix.
- `(r mut Router) NotFound(h fn(Req, mut Out))`: NotFound sets the handler for the paths no route matches (under r's prefix when r is mounted); the status starts as 404.
- `(r mut Router) MethodNotAllowed(h fn(Req, mut Out))`: MethodNotAllowed sets the handler for the paths whose routes take other methods; the status starts as 405 and the Allow header lists those methods.
- `(r Router) Check() !`: Check fails with r's first bad pattern, conflicting route or misplaced mount, the error Serve would fail with before listening.
- `(r Router) Serve(addr str) !`: Serve listens on addr and serves r on every core, like anvil.Serve. The routes are checked and compiled once, into a table every core reads; Serve fails with r's error, if any (see Check).
- `(r Router) ServeN(addr str, n i64) !`: ServeN is Serve on exactly n cores.
- `(r Router) Run(method str, target str, body str) Out`: Run sends one request through r on this thread, as Serve would (middleware, 404, 405), and returns the response: for tests. target is the path and query ("/users/7?full=1"), the request has no headers, and a HEAD response keeps its body. Run panics if r has an error (see Check).
- `(r Router) Match(method str, path str) str`: Match returns the pattern of the route that would serve method and path ("/users/{id}"), or "" when the request would get 404 or 405. Like Run, it panics if r has an error (see Check).

## hearth

Package hearth runs a program on every core: one thread per core, each with its own globals, request pool and ingot heap. Cores share nothing; relay carries messages.

- `Cores() i64`: Cores is the number of CPUs this program may use: the CPUs online, capped on Linux by the affinity mask (cpuset) and the cgroup CPU quota (ceil of cpu.max quota/period); never 0.
- `MemLimit() i64`: MemLimit is the memory limit in bytes the container (cgroup) imposes: 0 when there is none.
- `ID() i64`: ID is the current core's number: 0 for the main core.
- `Run(n i64, entry fn(i64))`: Run starts entry(i) on cores 1..n-1, runs entry(0) here, then waits for every core. Before starting it sizes the request pools to the memory limit and decides whether cores pin themselves to CPUs (only when they map one-to-one onto the allowed CPUs, or TIN_PIN=1).
- `PoolChunk() i64`: PoolChunk is the request pool chunk size in bytes each core uses (after pool_tune).
- `PoolCapacity() i64`: PoolCapacity is the usable size in bytes of this core's current base pool chunk (0 before its first request allocation).
- `Reset()`: Reset ends the current request: the core's pool is emptied for the next one.
- `RcStats() (i64, i64, i64)`: RcStats reports what long-lived memory this core still counts (#176): the number of counted blocks, their bytes and how many dropped blocks wait in the limbo.

## relay

Package relay carries messages between cores, which share no memory. A message is a str copied into the receiving core's inbox (a lock-free multi-producer queue); the receiver gets its own copy in its request pool. Encode structs with argo.Put/argo.Get.

```tin body
relay.Send(2, "hello")              // from any core
let (from, msg) = relay.Recv()      // on core 2: blocks until a message arrives
let (from, msg) = try relay.Next()  // the same, but fails on a deadline or cancel
```

- `Send(to i64, msg str)`: Send copies msg into core to's inbox; it never blocks.
- `Broadcast(msg str)`: Broadcast sends msg to every other running core.
- `Cores() i64`: Cores is the number of cores the program started.
- `TryRecv() (i64, str, bool)`: TryRecv returns the next message for this core, if there is one.
- `Recv() (i64, str)`: Recv blocks until a message for this core arrives and returns its sender and text. It blocks the whole core and ignores deadlines and cancels; use Next in tasks and within blocks.
- `Next() !(i64, str)`: Next waits until a message for this core arrives and returns its sender and text. Unlike Recv it waits through rt_task_wait: inside a task the core serves other tasks meanwhile, and a deadline (within, the request's) or a cancel ends the wait with that fault. Under anvil.OnRelay the event loop takes every message, so do not call Next there.
- `WakeFD() i64`: WakeFD is this core's wake-up descriptor, for event loops: after it turns readable, call Drain. Arm must be called before the loop blocks.
- `Arm()`: Arm asks senders to wake this core through WakeFD (call just before blocking).
- `Drain(h fn(i64, str))`: Drain runs h on every waiting message (event loops call it after WakeFD fires).
- `Received() i64`: Received is how many messages this core has taken from its inbox.
- `Me() i64`: Me is this core's number.

## task

Package task reads the deadline and cancellation of the running code, which belong to its innermost boundary (the request, a `within` or `limit` block, a scope's child; Go's context.Context Deadline and Err, without passing a context). Waits already fail when either stops the code: these are for code that does not wait, or that wants to stop at a point of its own choosing.

- `Deadline() i64`: Deadline is the effective deadline of the running code in tide.Now() nanoseconds (the earliest of its request's and every enclosing within block's), or 0 when it has none.
- `Canceled() !`: Canceled is nil while the running code may go on, else the fault its next wait would fail with: fault.DeadlineExceeded once the deadline has passed, fault.LimitExceeded past a budget, or fault.Canceled wrapping the reason of a cancel or drain.

## wire

Package wire is TCP networking and a small HTTP/1.1 client. Calls block the calling core (servers should use anvil); every connection can carry a read/write timeout.

```tin body
let c = try wire.Dial("127.0.0.1:6379")
try c.Write("PING\r\n")
let r = try wire.Get("http://127.0.0.1:8080/json")
```

- `type Conn struct`: Conn is a TCP connection.
- `type Listener struct`: Listener accepts TCP connections.
- `type Resp struct`: Resp is an HTTP response.
- `IsEOF(err fault) bool`: EOF is the fault Read returns at the end of the stream.
- `Dial(addr str) !Conn`: Dial connects to "host:port".
- `DialTimeout(addr str, timeout i64) !Conn`: DialTimeout connects to "host:port", giving up after timeout nanoseconds (0: no limit).
- `(c Conn) Fd() i64`: Fd is the connection's descriptor, for clients that do their own I/O on it (it stays non-blocking; Close still closes it).
- `(c mut Conn) SetTimeout(ns i64)`: SetTimeout limits every later read and write to ns nanoseconds (0: no limit).
- `(c Conn) SetNoDelay(on bool)`: SetNoDelay turns Nagle's algorithm off (true) or on.
- `(c Conn) Write(s str) !`: Write sends all of s.
- `(c Conn) WriteBytes(b []u8) !`: WriteBytes sends all of b.
- `(c Conn) Read(buf mut []u8, max i64) !i64`: Read appends up to max bytes to buf and returns how many; at the end it returns 0 and EOF.
- `(c Conn) ReadFull(n i64) !str`: ReadFull reads exactly n bytes.
- `(c mut Conn) Close()`: Close closes the connection.
- `Listen(addr str) !Listener`: Listen opens a TCP listener on "host:port" (":0" picks a free port: see Port).
- `(l Listener) Port() i64`: Port is the port the listener is bound to.
- `(l Listener) Accept() !Conn`: Accept waits for the next connection.
- `(l Listener) AcceptTimeout(timeout i64) !Conn`: AcceptTimeout waits at most timeout ns for the next connection (0: no limit), failing with a fault that says "timed out" when none came.
- `(l mut Listener) Close()`: Close stops listening.
- `type Options struct`: Options configure one client call (DoWith); the zero value is what Do uses.
- `const DefaultMaxBody = 67108864`: DefaultMaxBody is the largest response body Do accepts (64 MiB, anvil's request limit): a larger one is a fault rather than memory a broken or hostile server can fill.
- `Get(url str) !Resp`: Get fetches url.
- `Post(url str, ctype str, body str) !Resp`: Post sends body with content type ctype to url.
- `Do(method str, url str, headers []str, body str) !Resp`: Do sends one request: headers is a list of name, value pairs. The method and header names must be tokens, and the URL and header values must not hold CR, LF, NUL or other control bytes (the URL no spaces either), or Do fails instead of sending a request an input could have split. Response bodies over DefaultMaxBody fail; DoWith sets a timeout and the limit.
- `DoWith(method str, url str, headers []str, body str, opt Options) !Resp`: DoWith is Do with options: an overall timeout and a response size limit.
- `(r Resp) Header(name str) str`: Header returns the response header name (any case), or "".

## twine

Package twine manipulates UTF-8 strings (like Go's strings), with Unicode case mapping, folding and white space from glyph's tables.

- `Clone(s str) str`: Clone returns a copy of s that shares no memory with it.
- `CutPrefix(s str, prefix str) (str, bool)`: CutPrefix returns s without the leading prefix and true, or s and false when it does not start with prefix.
- `CutSuffix(s str, suffix str) (str, bool)`: CutSuffix returns s without the trailing suffix and true, or s and false when it does not end with suffix.
- `SplitAfter(s str, sep str) []str`: SplitAfter slices s after every sep (into runes when sep is empty) and returns the pieces, each ending with sep.
- `SplitAfterN(s str, sep str, n i64) []str`: SplitAfterN is SplitAfter returning at most n pieces (all when n < 0, none when n == 0).
- `LastIndexAny(s str, chars str) i64`: LastIndexAny returns the byte offset of the last rune of s that is in chars, or -1.
- `ToValidUTF8(s str, replacement str) str`: ToValidUTF8 returns s with each run of invalid UTF-8 bytes replaced by replacement.
- `Lines(s str) []str`: Lines returns the lines of s, each ending with its newline ("\n", and a final line may lack one).
- `type Replacer struct`: Replacer replaces a list of strings with replacements, in one pass over the text.
- `NewReplacer(oldnew []str) Replacer`: NewReplacer returns a Replacer from a list of old, new string pairs. Replacements are made in the order they appear in the text, without overlapping matches; at one position the old strings are tried in argument order. An empty old string matches at the start and after every byte. It panics when the list has an odd length.
- `(r Replacer) Replace(s str) str`: Replace returns s with all replacements performed.
- `IndexByte(s str, c u8) i64`: IndexByte returns the byte offset of the first c in s, or -1.
- `LastIndexByte(s str, c u8) i64`: LastIndexByte returns the byte offset of the last c in s, or -1.
- `Index(s str, sub str) i64`: Index returns the byte offset of the first sub in s, or -1 (0 for an empty sub).
- `LastIndex(s str, sub str) i64`: LastIndex returns the byte offset of the last sub in s, or -1 (len(s) for an empty sub).
- `Contains(s str, sub str) bool`: Contains reports whether sub occurs in s.
- `ContainsByte(s str, c u8) bool`: ContainsByte reports whether byte c occurs in s.
- `HasPrefix(s str, prefix str) bool`: HasPrefix reports whether s starts with prefix.
- `HasSuffix(s str, suffix str) bool`: HasSuffix reports whether s ends with suffix.
- `Split(s str, sep str) []str`: Split slices s around every sep (into runes when sep is empty) and returns the pieces.
- `SplitN(s str, sep str, n i64) []str`: SplitN is Split returning at most n pieces (all when n < 0, none when n == 0).
- `Join(elems []str, sep str) str`: Join concatenates elems with sep between them.
- `Repeat(s str, count i64) str`: Repeat returns s concatenated count times (empty when count <= 0; panics when the length overflows).
- `Count(s str, sub str) i64`: Count returns the number of non-overlapping sub in s (RuneCount+1 when sub is empty).
- `Replace(s str, old str, repl str, n i64) str`: Replace returns s with the first n non-overlapping old replaced by repl (all when n < 0; empty old matches at every rune boundary).
- `ReplaceAll(s str, old str, repl str) str`: ReplaceAll returns s with every non-overlapping old replaced by repl.
- `TrimLeft(s str, cutset str) str`: TrimLeft returns s without its leading runes that are in cutset.
- `TrimRight(s str, cutset str) str`: TrimRight returns s without its trailing runes that are in cutset.
- `Trim(s str, cutset str) str`: Trim returns s without leading and trailing runes that are in cutset.
- `TrimSpace(s str) str`: TrimSpace returns s without leading and trailing white space (ASCII, U+0085, U+00A0).
- `TrimPrefix(s str, prefix str) str`: TrimPrefix returns s without the leading prefix, or s unchanged.
- `TrimSuffix(s str, suffix str) str`: TrimSuffix returns s without the trailing suffix, or s unchanged.
- `Compare(a str, b str) i64`: Compare returns -1, 0 or 1 ordering a and b bytewise.
- `IndexRune(s str, r i32) i64`: IndexRune returns the byte offset of the first r in s, or -1.
- `ContainsRune(s str, r i32) bool`: ContainsRune reports whether rune r occurs in s.
- `IndexAny(s str, chars str) i64`: IndexAny returns the byte offset of the first rune of s that is in chars, or -1.
- `ContainsAny(s str, chars str) bool`: ContainsAny reports whether any rune of chars occurs in s.
- `Cut(s str, sep str) (str, str, bool)`: Cut splits s around the first sep, returning (before, after, true), or (s, "", false) when absent.
- `type Builder struct`: Builder accumulates bytes; the zero Builder{} is ready to use, NewBuilder preallocates.
- `NewBuilder(n i64) Builder`: NewBuilder returns an empty Builder with room for n bytes.
- `(b mut Builder) Str(s str)`: Str appends s.
- `(b mut Builder) Byte(c u8)`: Byte appends one byte.
- `(b mut Builder) Rune(r i32)`: Rune appends the UTF-8 encoding of r.
- `(b mut Builder) Int(v i64)`: Int appends v in decimal.
- `(b Builder) Len() i64`: Len returns the number of bytes accumulated.
- `(b Builder) String() str`: String returns a copy of the accumulated bytes as a str.
- `(b Builder) Bytes() []u8`: Bytes returns the accumulated bytes without copying (aliases the Builder).
- `(b Builder) Cap() i64`: Cap returns the number of bytes the Builder can hold without growing.
- `(b mut Builder) Grow(n i64)`: Grow makes room for n more bytes.
- `(b mut Builder) Write(p []u8)`: Write appends p.
- `(b mut Builder) Reset()`: Reset empties the Builder but keeps its capacity.
- `Map(mapping fn(i32) i32, s str) str`: Map returns s with every rune replaced by mapping(rune); a rune mapped to a negative value is dropped. Invalid UTF-8 bytes reach mapping as U+FFFD, and a rune mapped to it is written as U+FFFD.
- `ToUpper(s str) str`: ToUpper returns s with every letter mapped to upper case.
- `ToLower(s str) str`: ToLower returns s with every letter mapped to lower case.
- `ToTitle(s str) str`: ToTitle returns s with every letter mapped to title case.
- `Title(s str) str`: Title returns s with the first letter of each word mapped to title case. It cannot tell where words start in every script (the apostrophe in "they're" starts one): it is Go's deprecated strings.Title.
- `EqualFold(s str, t str) bool`: EqualFold reports whether s and t are equal under Unicode simple case folding.
- `Fields(s str) []str`: Fields splits s around runs of white space (Unicode's) and returns the non-empty pieces.
- `FieldsFunc(s str, f fn(i32) bool) []str`: FieldsFunc splits s around runs of runes for which f is true and returns the non-empty pieces.
- `IndexFunc(s str, f fn(i32) bool) i64`: IndexFunc returns the byte offset of the first rune for which f is true, or -1.
- `LastIndexFunc(s str, f fn(i32) bool) i64`: LastIndexFunc returns the byte offset of the last rune for which f is true, or -1.
- `ContainsFunc(s str, f fn(i32) bool) bool`: ContainsFunc reports whether f is true for any rune of s.
- `TrimLeftFunc(s str, f fn(i32) bool) str`: TrimLeftFunc returns s without the leading runes for which f is true.
- `TrimRightFunc(s str, f fn(i32) bool) str`: TrimRightFunc returns s without the trailing runes for which f is true.
- `TrimFunc(s str, f fn(i32) bool) str`: TrimFunc returns s without the leading and trailing runes for which f is true.

## glyph

Package glyph is UTF-8 (like Go's unicode/utf8) and Unicode: general categories, scripts, properties and case mapping, from the same tables as Go's unicode package (see UnicodeVersion).

- `const RuneError = 0xfffd`: RuneError is the replacement character returned for invalid UTF-8.
- `const MaxRune = 0x10ffff`: MaxRune is the largest valid Unicode code point.
- `const UTFMax = 4`: UTFMax is the maximum number of bytes one encoded rune occupies.
- `ValidRune(r i32) bool`: ValidRune reports whether r can be legally encoded as UTF-8.
- `RuneLen(r i32) i64`: RuneLen returns the number of bytes needed to encode r, or -1 if r is not a valid rune.
- `EncodeRune(b mut []u8, r i32) i64`: EncodeRune appends the UTF-8 encoding of r to b (RuneError if invalid) and returns the byte count.
- `RuneStr(r i32) str`: RuneStr returns r encoded as a one-rune string (RuneError if invalid).
- `DecodeRune(s str, i i64) (i32, i64)`: DecodeRune decodes the rune starting at byte i of s, returning (RuneError, 1) for bad bytes and (RuneError, 0) at the end.
- `DecodeLastRune(s str, end i64) (i32, i64)`: DecodeLastRune decodes the last rune of s[0:end], returning its rune and size ((RuneError, 0) when end <= 0).
- `RuneStart(b u8) bool`: RuneStart reports whether byte b could be the first byte of an encoded rune (not a continuation byte).
- `FullRune(s str, i i64) bool`: FullRune reports whether s[i:] begins with a complete encoded rune (invalid bytes count as complete).
- `RuneCount(s str) i64`: RuneCount returns the number of runes in s, counting each invalid byte as one rune.
- `Valid(s str) bool`: Valid reports whether s is entirely valid UTF-8.
- `const UnicodeVersion = "15.0.0"`: UnicodeVersion is the version of the Unicode Character Database the tables come from.
- `type Table enum`: Table names a set of code points by Unicode's own name: a general category (Lu, Nd, P), a script (Latin, Han, Arabic) or a property (White_Space, Dash). Use it with Is.
- `Is(t Table, r i32) bool`: Is reports whether r is in the set t.
- `IsOneOf(sets []Table, r i32) bool`: IsOneOf reports whether r is in any of the sets.
- `IsLetter(r i32) bool`: IsLetter reports whether r is a letter (category L).
- `IsDigit(r i32) bool`: IsDigit reports whether r is a decimal digit (category Nd).
- `IsNumber(r i32) bool`: IsNumber reports whether r is a number (category N).
- `IsSpace(r i32) bool`: IsSpace reports whether r is white space as Unicode defines it (property White_Space): tab, line feed, vertical tab, form feed, carriage return, space, U+0085, U+00A0 and the Unicode space separators.
- `IsUpper(r i32) bool`: IsUpper reports whether r is an upper-case letter (category Lu).
- `IsLower(r i32) bool`: IsLower reports whether r is a lower-case letter (category Ll).
- `IsTitle(r i32) bool`: IsTitle reports whether r is a title-case letter (category Lt).
- `IsMark(r i32) bool`: IsMark reports whether r is a mark (category M).
- `IsPunct(r i32) bool`: IsPunct reports whether r is punctuation (category P).
- `IsSymbol(r i32) bool`: IsSymbol reports whether r is a symbol (category S).
- `IsControl(r i32) bool`: IsControl reports whether r is a control character: U+0000 to U+001F and U+007F to U+009F.
- `IsGraphic(r i32) bool`: IsGraphic reports whether r is a letter, mark, number, punctuation, symbol or space separator.
- `IsPrint(r i32) bool`: IsPrint reports whether r is printable: a letter, mark, number, punctuation or symbol, or the ASCII space (no other space is).
- `const UpperCase = 0`: The case a rune is mapped to by To.
- `const LowerCase = 1`
- `const TitleCase = 2`
- `To(which i64, r i32) i32`: To maps r to the given case (UpperCase, LowerCase or TitleCase); a rune without a mapping is returned unchanged.
- `ToUpper(r i32) i32`: ToUpper maps r to upper case.
- `ToLower(r i32) i32`: ToLower maps r to lower case.
- `ToTitle(r i32) i32`: ToTitle maps r to title case.
- `SimpleFold(r i32) i32`: SimpleFold iterates over the code points that are equivalent under simple case folding: it returns the smallest rune greater than r in r's orbit, or the smallest one when there is none ('K' gives 'k', 'k' gives U+212A, U+212A gives 'K').

## mint

Package mint converts numbers and quoted strings to and from text (like Go's strconv), with Go's error texts.

- `const MaxI64 = 9223372036854775807`: MaxI64 is the largest i64.
- `const MinI64 = -9223372036854775807 - 1`: MinI64 is the smallest i64.
- `Itoa(v i64) str`: Itoa returns v in decimal.
- `FormatInt(v i64, base i64) str`: FormatInt returns v in base 2..36 with lower-case digits (panics on any other base).
- `FormatUint(v u64, base i64) str`: FormatUint returns v in base 2..36 with lower-case digits (panics on any other base).
- `AppendInt(b mut []u8, v i64) []u8`: AppendInt appends v in decimal to b and returns b (use it as b = AppendInt(b, v)).
- `Atoi(s str) !i64`: Atoi parses a decimal i64 like Go's Atoi; out of range is a fault (with 0, where Go returns the clamped value).
- `ParseInt(s str, base i64) !i64`: ParseInt parses a signed integer in base 2..36, or base 0 for 0x/0o/0b prefixes and underscores.
- `ParseUint(s str, base i64) !u64`: ParseUint parses an unsigned integer in base 2..36, or base 0 for 0x/0o/0b prefixes and underscores.
- `ParseBool(s str) !bool`: ParseBool parses 1 t T TRUE true True and 0 f F FALSE false False.
- `ParseFloat(s str) !f64`: ParseFloat parses a Go float literal (decimal or 0x hex with p exponent, underscores, inf/infinity/nan) with exact nearest-even rounding.
- `F64frombits(b u64) f64`: F64frombits returns the f64 with bit pattern b.
- `FormatFloat(f f64, fmt u8, prec i64) str`: FormatFloat formats f as 'f' (ddd.ddd), 'e' (d.ddde±dd) or 'g' (shortest of the two); prec -1 is the shortest text that reads back exactly.
- `Quote(s str) str`: Quote returns s as a Go double-quoted literal with \n-style, \x, \u and \U escapes.
- `AppendQuote(b mut []u8, s str) []u8`: AppendQuote appends Quote(s) to b and returns b.
- `QuoteRune(r i32) str`: QuoteRune returns r as a Go single-quoted rune literal (invalid runes become U+FFFD).
- `Unquote(s str) !str`: Unquote interprets s as a Go string literal ("..." with escapes, '...' one rune, `...` raw) and returns its value.

## gauge

Package gauge is floating-point math and a few integer helpers (like Go's math); bit operations are in package bits. The transcendental functions are written in Tin (ported from Go's math package); only the functions the CPU has an instruction for (sqrt, floor, ceil, trunc, round, rint) go through the system.

- `Atan(x f64) f64`: Atan returns the arctangent of x, in [-Pi/2, Pi/2]. Atan(±0) = ±0, Atan(±Inf) = ±Pi/2.
- `Atan2(y f64, x f64) f64`: Atan2 returns the arctangent of y/x using the signs of both to pick the quadrant, in [-Pi, Pi].
- `Asin(x f64) f64`: Asin returns the arcsine of x, in [-Pi/2, Pi/2]. NaN for |x| > 1.
- `Acos(x f64) f64`: Acos returns the arccosine of x, in [0, Pi]. NaN for |x| > 1.
- `Cbrt(x f64) f64`: Cbrt returns the cube root of x. Cbrt(±0) = ±0, Cbrt(±Inf) = ±Inf, Cbrt(NaN) = NaN.
- `Exp(x f64) f64`: Exp returns e**x. Exp(+Inf) = +Inf, Exp(-Inf) = 0, Exp(NaN) = NaN; it overflows above 709.78.
- `const Exp2Overflow = 1.0239999999999999e+03`
- `const Exp2Underflow = -1.0740e+03`
- `Exp2(x f64) f64`: Exp2 returns 2**x. Exp2(+Inf) = +Inf, Exp2(-Inf) = 0, Exp2(NaN) = NaN.
- `F64bits(f f64) u64`: F64bits returns the IEEE 754 bit pattern of f.
- `F64frombits(b u64) f64`: F64frombits returns the f64 with bit pattern b.
- `Abs(x f64) f64`: Abs returns |x| (NaN stays NaN, -0 becomes +0).
- `Signbit(x f64) bool`: Signbit reports whether x is negative or negative zero.
- `Copysign(f f64, sign f64) f64`: Copysign returns a value with the magnitude of f and the sign of sign.
- `Inf(sign i64) f64`: Inf returns +Inf when sign >= 0, else -Inf.
- `NaN() f64`: NaN returns a quiet not-a-number.
- `IsNaN(f f64) bool`: IsNaN reports whether f is not-a-number.
- `IsInf(f f64, sign i64) bool`: IsInf reports whether f is +Inf (sign > 0), -Inf (sign < 0) or either (sign == 0).
- `Min(x f64, y f64) f64`: Min returns the smaller of x and y; any NaN gives NaN and -0 is smaller than +0 (like Go).
- `Max(x f64, y f64) f64`: Max returns the larger of x and y; any NaN gives NaN and +0 is larger than -0 (like Go).
- `Clamp(x f64, lo f64, hi f64) f64`: Clamp returns x limited to [lo, hi] (NaN passes through).
- `Pow10(n i64) f64`: Pow10 returns 10**n: +Inf above 308, 0 below -323, exactly as Go's math.Pow10.
- `Frexp(f f64) (f64, i64)`: Frexp breaks f into a fraction in [0.5, 1) and a power of two: f = frac * 2**exp. Frexp(0), Frexp(±Inf) and Frexp(NaN) return f and 0.
- `Ldexp(frac f64, exp i64) f64`: Ldexp returns frac * 2**exp, the inverse of Frexp.
- `Modf(f f64) (f64, f64)`: Modf returns the integer and fractional parts of f, both with the sign of f.
- `const Pi = 3.141592653589793`: Pi is the ratio of a circle's circumference to its diameter.
- `const E = 2.718281828459045`: E is the base of natural logarithms.
- `const Sqrt2 = 1.4142135623730951`: Sqrt2 is the square root of 2.
- `const Ln2 = 0.6931471805599453`: Ln2 is the natural logarithm of 2.
- `const MaxI64 = 9223372036854775807`: MaxI64 is the largest i64.
- `const MinI64 = -9223372036854775807 - 1`: MinI64 is the smallest i64.
- `const MaxU64 u64 = 18446744073709551615`: MaxU64 is the largest u64 (typed, because an untyped constant this large folds to -1 in the frozen compiler).
- `const MaxF64 = 1.7976931348623157e308`: MaxF64 is the largest finite f64.
- `const SmallestNonzeroF64 = 4.9406564584124654e-324`: SmallestNonzeroF64 is the smallest positive denormal f64.
- `Sqrt(x f64) f64`: Sqrt returns the square root of x.
- `Floor(x f64) f64`: Floor returns the largest integer value <= x.
- `Ceil(x f64) f64`: Ceil returns the smallest integer value >= x.
- `Trunc(x f64) f64`: Trunc returns the integer part of x (rounding toward zero).
- `Round(x f64) f64`: Round returns x rounded to the nearest integer, halves away from zero.
- `RoundToEven(x f64) f64`: RoundToEven returns x rounded to the nearest integer, halves to the even neighbour.
- `Sinh(x f64) f64`: Sinh returns the hyperbolic sine of x. It uses Exp above 0.5 and a rational approximation below.
- `Cosh(x f64) f64`: Cosh returns the hyperbolic cosine of x.
- `Tanh(x f64) f64`: Tanh returns the hyperbolic tangent of x, in [-1, 1].
- `Hypot(p f64, q f64) f64`: Hypot returns sqrt(p*p + q*q), overflowing only if the result does.
- `MinI(a i64, b i64) i64`: MinI returns the smaller of a and b.
- `MaxI(a i64, b i64) i64`: MaxI returns the larger of a and b.
- `AbsI(x i64) i64`: AbsI returns |x| (MinI64 wraps to itself).
- `ClampI(x i64, lo i64, hi i64) i64`: ClampI returns x limited to [lo, hi].
- `Gcd(a i64, b i64) i64`: Gcd returns the greatest common divisor of |a| and |b| (0 when both are 0).
- `Lcm(a i64, b i64) i64`: Lcm returns the least common multiple of |a| and |b| (0 when either is 0; wraps on overflow).
- `Log(x f64) f64`: Log returns the natural logarithm of x. Log(+Inf) = +Inf, Log(0) = -Inf, Log(x < 0) = NaN.
- `Log2(x f64) f64`: Log2 returns the binary logarithm of x, exact for powers of two.
- `Log10(x f64) f64`: Log10 returns the decimal logarithm of x.
- `Log1p(x f64) f64`: Log1p returns log(1 + x), accurate even when x is close to zero.
- `Mod(x f64, y f64) f64`: Mod returns the remainder of x/y with the sign of x, exactly. NaN for y == 0, infinite x or either NaN.
- `Pow(x f64, y f64) f64`: Pow returns x**y, with the special cases of C99 and Go: Pow(x, ±0) = 1, Pow(1, y) = 1, Pow(NaN, y) = NaN, Pow(x < 0, non-integer y) = NaN, and the usual infinities and signed zeros. It is exact for small integer powers of exactly representable bases and within an ulp or two otherwise (it is not correctly rounded).
- `Sin(x f64) f64`: Sin returns the sine of x (radians). Sin(±0) = ±0, Sin(±Inf) = Sin(NaN) = NaN.
- `Cos(x f64) f64`: Cos returns the cosine of x (radians). Cos(±Inf) = Cos(NaN) = NaN.
- `Tan(x f64) f64`: Tan returns the tangent of x (radians). Tan(±0) = ±0, Tan(±Inf) = Tan(NaN) = NaN.

## bits

Package bits counts, rotates and reverses the bits of fixed-width unsigned integers, and does 64-bit and 32-bit arithmetic with carries (like Go's math/bits). Every name carries its width; PopCount is Go's OnesCount; there is no uint-wide form because Tin has no uint.

- `Len64(x u64) i64`: Len64 returns the minimum number of bits needed to represent x; Len64(0) is 0.
- `Len32(x u32) i64`: Len32 is Len64 for a u32.
- `Len16(x u16) i64`: Len16 is Len64 for a u16.
- `Len8(x u8) i64`: Len8 is Len64 for a u8.
- `LeadingZeros64(x u64) i64`: LeadingZeros64 returns the number of leading zero bits in x; it is 64 for 0.
- `LeadingZeros32(x u32) i64`: LeadingZeros32 returns the number of leading zero bits in x; it is 32 for 0.
- `LeadingZeros16(x u16) i64`: LeadingZeros16 returns the number of leading zero bits in x; it is 16 for 0.
- `LeadingZeros8(x u8) i64`: LeadingZeros8 returns the number of leading zero bits in x; it is 8 for 0.
- `TrailingZeros64(x u64) i64`: TrailingZeros64 returns the number of trailing zero bits in x; it is 64 for 0.
- `TrailingZeros32(x u32) i64`: TrailingZeros32 returns the number of trailing zero bits in x; it is 32 for 0.
- `TrailingZeros16(x u16) i64`: TrailingZeros16 returns the number of trailing zero bits in x; it is 16 for 0.
- `TrailingZeros8(x u8) i64`: TrailingZeros8 returns the number of trailing zero bits in x; it is 8 for 0.
- `PopCount64(x u64) i64`: PopCount64 returns the number of one bits in x.
- `PopCount32(x u32) i64`: PopCount32 returns the number of one bits in x.
- `PopCount16(x u16) i64`: PopCount16 returns the number of one bits in x.
- `PopCount8(x u8) i64`: PopCount8 returns the number of one bits in x.
- `RotateLeft64(x u64, k i64) u64`: RotateLeft64 returns x rotated left by k bits; a negative k rotates right.
- `RotateLeft32(x u32, k i64) u32`: RotateLeft32 returns x rotated left by k bits; a negative k rotates right.
- `RotateLeft16(x u16, k i64) u16`: RotateLeft16 returns x rotated left by k bits; a negative k rotates right.
- `RotateLeft8(x u8, k i64) u8`: RotateLeft8 returns x rotated left by k bits; a negative k rotates right.
- `ReverseBytes64(x u64) u64`: ReverseBytes64 returns x with its bytes in reversed order.
- `ReverseBytes32(x u32) u32`: ReverseBytes32 returns x with its bytes in reversed order.
- `ReverseBytes16(x u16) u16`: ReverseBytes16 returns x with its bytes in reversed order.
- `Reverse64(x u64) u64`: Reverse64 returns x with its bits in reversed order.
- `Reverse32(x u32) u32`: Reverse32 returns x with its bits in reversed order.
- `Reverse16(x u16) u16`: Reverse16 returns x with its bits in reversed order.
- `Reverse8(x u8) u8`: Reverse8 returns x with its bits in reversed order.
- `Add64(x u64, y u64, carry u64) (u64, u64)`: Add64 returns the sum x + y + carry and the carry out. carry must be 0 or 1, otherwise the behavior is undefined.
- `Add32(x u32, y u32, carry u32) (u32, u32)`: Add32 returns the sum x + y + carry and the carry out (0 or 1).
- `Sub64(x u64, y u64, borrow u64) (u64, u64)`: Sub64 returns the difference x - y - borrow and the borrow out. borrow must be 0 or 1, otherwise the behavior is undefined.
- `Sub32(x u32, y u32, borrow u32) (u32, u32)`: Sub32 returns the difference x - y - borrow and the borrow out (0 or 1).
- `Mul64(x u64, y u64) (u64, u64)`: Mul64 returns the 128-bit product of x and y as (high word, low word).
- `Mul32(x u32, y u32) (u32, u32)`: Mul32 returns the 64-bit product of x and y as (high word, low word).
- `const Div64Mask32 = two32 - 1`
- `Div64(hi u64, lo u64, y u64) (u64, u64)`: Div64 returns the quotient and remainder of (hi, lo) divided by y. It panics for y == 0 (division by zero) and for y <= hi (the quotient does not fit in 64 bits).
- `Div32(hi u32, lo u32, y u32) (u32, u32)`: Div32 returns the quotient and remainder of (hi, lo) divided by y. It panics for y == 0 and for y <= hi (the quotient does not fit in 32 bits).
- `Rem64(hi u64, lo u64, y u64) u64`: Rem64 returns the remainder of (hi, lo) divided by y, for any hi (no overflow panic). It panics for y == 0.
- `Rem32(hi u32, lo u32, y u32) u32`: Rem32 returns the remainder of (hi, lo) divided by y. It panics for y == 0.

## link

Package link parses, builds and resolves URLs, and escapes and unescapes their parts (like Go's net/url). A URL is a struct; its User is an optional (nil when the URL has no userinfo); query parameters are a Values, a small wrapper over map[str][]str whose keys keep insertion order and whose Encode sorts them. Faults carry Go's messages: parse "x": invalid URL escape "%zz".

- `QueryUnescape(s str) !str`: QueryUnescape converts each %AB in s to the byte 0xAB and each + to a space; a % not followed by two hex digits is a fault.
- `PathUnescape(s str) !str`: PathUnescape is QueryUnescape for a path segment: + stays a plus sign.
- `QueryEscape(s str) str`: QueryEscape escapes s for use as a query key or value: a space becomes +.
- `PathEscape(s str) str`: PathEscape escapes s for use as one path segment: / and ? are escaped too.
- `type Userinfo struct`: Userinfo is the username and optional password of a URL.
- `User(username str) Userinfo`: User returns a Userinfo with a username and no password.
- `UserPassword(username str, password str) Userinfo`: UserPassword returns a Userinfo with a username and a password (only for legacy services: RFC 2396 warns against passwords in URLs).
- `(u Userinfo) Username() str`: Username returns the username.
- `(u Userinfo) Password() (str, bool)`: Password returns the password and whether one is set.
- `(u Userinfo) String() str`: String returns the escaped userinfo, username[:password].
- `type URL struct`: URL is a parsed URL, in the general form [scheme:][//[userinfo@]host][/]path[?query][#fragment]. A URL whose rest after the scheme does not start with a slash is opaque: scheme:opaque[?query][#fragment]. Path and Fragment are stored decoded; RawPath and RawFragment hold the original encoding when it differs from the default one (EscapedPath and EscapedFragment use them).
- `(u URL) Clone() URL`: Clone returns a copy of u (a plain assignment of a struct shares it).
- `Parse(rawURL str) !URL`: Parse parses a URL, absolute or relative; a hostname and path without a scheme is invalid but may not be rejected, because of parsing ambiguities.
- `ParseRequestURI(rawURL str) !URL`: ParseRequestURI parses a URL received in an HTTP request: an absolute URI or an absolute path, without a #fragment.
- `(u URL) EscapedPath() str`: EscapedPath returns u.RawPath when it is a valid encoding of u.Path, else the default escaping.
- `(u URL) EscapedFragment() str`: EscapedFragment returns u.RawFragment when it is a valid encoding of u.Fragment, else the default.
- `(u URL) Username() str`: Username returns the username of u's userinfo, or "".
- `(u URL) Password() (str, bool)`: Password returns the password of u's userinfo and whether one is set.
- `(u URL) String() str`: String reassembles u into a URL string: [scheme:][//[userinfo@]host][/]path[?query][#fragment].
- `(u URL) Redacted() str`: Redacted is String with the password, if any, replaced by xxxxx.
- `(u URL) IsAbs() bool`: IsAbs reports whether u has a scheme.
- `(u URL) Hostname() str`: Hostname returns u.Host without its port, and without the brackets of an IPv6 literal.
- `(u URL) Port() str`: Port returns the port of u.Host, or "" when there is none.
- `(u URL) RequestURI() str`: RequestURI returns what goes in an HTTP request line: the escaped path (or / when empty) and query, or the opaque part.
- `(u URL) Query() Values`: Query parses u.RawQuery, keeping every well-formed parameter and skipping malformed ones.
- `(u URL) Parse(ref str) !URL`: Parse parses ref (which may be relative) in the context of u: Parse then ResolveReference.
- `(u URL) ResolveReference(ref URL) URL`: ResolveReference resolves a URI reference against u as an absolute URI (RFC 3986 section 5.2): ref may be relative or absolute, and u is typically an absolute URL.
- `(u URL) JoinPath(elems []str) URL`: JoinPath returns a copy of u with the elements joined onto its path (cleaned, with a trailing slash kept if the last element had one).
- `JoinPath(base str, elems []str) !str`: JoinPath parses base and joins the elements onto its path, returning the URL as a string.
- `type Values struct`: Values maps a query key to its values, in the order they were added; Encode sorts the keys.
- `NewValues() Values`: NewValues returns an empty Values.
- `(v Values) Get(key str) str`: Get returns the first value of key, or "" when there is none.
- `(v Values) All(key str) []str`: All returns every value of key (empty when there is none).
- `(v mut Values) Set(key str, value str)`: Set makes value the only value of key.
- `(v mut Values) Add(key str, value str)`: Add appends value to the values of key.
- `(v mut Values) Del(key str)`: Del removes key and its values.
- `(v Values) Has(key str) bool`: Has reports whether key is present.
- `(v Values) Keys() []str`: Keys returns the keys in the order they were first added.
- `(v Values) Len() i64`: Len returns the number of keys.
- `ParseQuery(query str) !Values`: ParseQuery parses a URL query ("a=1&b=2&a=3") into Values. It faults on the first malformed parameter (a bad escape, or a semicolon separator); URL.Query keeps the good ones instead.
- `(v Values) Encode() str`: Encode returns the values URL-encoded ("a=1&a=3&b=2"), sorted by key.

## ore

Package ore works on byte slices ([]u8), like Go's bytes. Functions that append take the slice as mut and grow it in place.

- `Equal(a []u8, b []u8) bool`: Equal reports whether a and b hold the same bytes.
- `Compare(a []u8, b []u8) i64`: Compare returns -1, 0 or 1 by byte-wise order.
- `IndexByte(b []u8, c u8) i64`: IndexByte returns the index of the first c in b, or -1.
- `LastIndexByte(b []u8, c u8) i64`: LastIndexByte returns the index of the last c in b, or -1.
- `Index(b []u8, sep []u8) i64`: Index returns the index of the first occurrence of sep in b, or -1.
- `Contains(b []u8, sep []u8) bool`: Contains reports whether sep occurs in b.
- `HasPrefix(b []u8, p []u8) bool`: HasPrefix reports whether b starts with p.
- `HasSuffix(b []u8, p []u8) bool`: HasSuffix reports whether b ends with p.
- `Clone(b []u8) []u8`: Clone returns a fresh copy of b.
- `AppendStr(b mut []u8, s str) []u8`: AppendStr appends the bytes of s.
- `AppendByte(b mut []u8, c u8) []u8`: AppendByte appends c.
- `AppendInt(b mut []u8, v i64) []u8`: AppendInt appends v in decimal.
- `AppendUint(b mut []u8, v u64) []u8`: AppendUint appends v in decimal.
- `AppendHex(b mut []u8, v u64) []u8`: AppendHex appends v in lower-case hexadecimal (no prefix).
- `Reset(b mut []u8)`: Reset empties b, keeping its capacity.
- `Truncate(b mut []u8, n i64)`: Truncate keeps the first n bytes of b.
- `ToStr(b []u8) str`: ToStr returns b's bytes as a str.
- `TrimSpace(b []u8) []u8`: TrimSpace returns b without leading and trailing ASCII white space (a sub-slice).
- `Split(b []u8, sep u8) []str`: Split cuts b around every sep byte and returns the pieces as strs.
- `Fields(b []u8) []str`: Fields splits b around runs of ASCII white space.
- `ToLower(b []u8) []u8`: ToLower returns a copy with ASCII letters lowered.
- `ToUpper(b []u8) []u8`: ToUpper returns a copy with ASCII letters raised.
- `Repeat(b []u8, n i64) []u8`: Repeat returns n copies of b (panics when the length overflows).

## flume

Package flume reads and writes file descriptors through 64 KiB buffers: lines, whole files and buffered output with one write per flush.

- `type Reader struct`: Reader buffers reads from a file descriptor. Inside a task it waits on a pipe, socket or terminal through rt_task_wait, so a deadline or cancel fails the read (the next read retries).
- `type Writer struct`: Writer buffers writes to a file descriptor.
- `New(fd i64) Reader`: New reads from fd.
- `Open(path str) !Reader`: Open reads the file at path.
- `(r mut Reader) Close()`: Close closes the reader's descriptor.
- `(r mut Reader) Line() !(str, bool)`: Line returns the next line without its "\n" (or "\r\n"); ok is false at the end.
- `(r mut Reader) Byte() (u8, bool)`: Byte returns the next byte; ok is false at the end.
- `(r mut Reader) ReadAll() !str`: ReadAll returns everything left.
- `ReadFile(path str) !str`: ReadFile returns the contents of the file at path.
- `NewWriter(fd i64) Writer`: NewWriter writes to fd.
- `Stdout() Writer`: Stdout writes to standard output (flush it before mixing with say output).
- `Create(path str) !Writer`: Create truncates or creates the file at path for writing.
- `(w mut Writer) Str(s str)`: Str appends s.
- `(w mut Writer) Byte(c u8)`: Byte appends c.
- `(w mut Writer) Int(v i64)`: Int appends v in decimal.
- `(w mut Writer) Line(s str)`: Line appends s and a newline.
- `(w mut Writer) Flush() !`: Flush writes everything buffered (with as few writes as the descriptor allows).
- `(w mut Writer) Close() !`: Close flushes and closes the writer's descriptor once; closing again (or a writer that never opened) is a fault.

## quarry

Package quarry is the operating system interface (like Go's os): arguments, environment, files and directories.

- `Args() []str`: Args returns the command line, program name first.
- `Getenv(key str) str`: Getenv returns the value of environment variable key, or "" when it is unset.
- `LookupEnv(key str) (str, bool)`: LookupEnv returns the value of key and whether it is set (an empty value is still set).
- `Setenv(key str, value str) !`: Setenv sets environment variable key to value; an empty key or one holding '=' or NUL is a fault.
- `Unsetenv(key str) !`: Unsetenv removes environment variable key.
- `ReadFile(path str) !str`: ReadFile returns the whole content of the file at path.
- `ReadStdin() !str`: ReadStdin reads standard input to its end. Inside a task, from a pipe, socket or terminal, it waits through rt_task_wait: the core serves others, and a deadline or cancel fails it.
- `WriteFile(path str, data str) !`: WriteFile writes data to the file at path, creating it (mode 0644) or truncating it.
- `AppendFile(path str, data str) !`: AppendFile appends data to the file at path, creating it (mode 0644) when needed.
- `Exists(path str) bool`: Exists reports whether path names an existing file or directory (symlinks are followed).
- `IsDir(path str) bool`: IsDir reports whether path names a directory.
- `Size(path str) !i64`: Size returns the size in bytes of the file at path.
- `ModTime(path str) !i64`: ModTime returns the modification time of path in seconds since the Unix epoch.
- `Remove(path str) !`: Remove deletes the file or empty directory at path.
- `RemoveAll(path str) !`: RemoveAll deletes path and everything below it; a missing path is not a fault.
- `Rename(oldpath str, newpath str) !`: Rename moves oldpath to newpath, replacing a file there; like Go it never replaces a directory.
- `Mkdir(path str) !`: Mkdir creates the directory path (mode 0755); its parent must exist.
- `MkdirAll(path str) !`: MkdirAll creates path and any missing parents (mode 0755); an existing directory is fine.
- `SortStrs(a mut []str)`: SortStrs sorts a bytewise in place.
- `ReadDir(path str) ![]str`: ReadDir returns the names in directory path, sorted bytewise, without "." and "..".
- `Getwd() !str`: Getwd returns the current working directory ($PWD when it still names it, like Go).
- `Chdir(path str) !`: Chdir changes the current working directory to path.
- `TempDir() str`: TempDir returns the directory for temporary files: $TMPDIR, or /tmp.
- `Hostname() !str`: Hostname returns the machine's host name.
- `Pid() i64`: Pid returns the process id.
- `Exit(code i64)`: Exit flushes stdout and ends the program with status code.
- `Eprint(s str)`: Eprint writes s to stderr.
- `Eprintln(s str)`: Eprintln writes s and a newline to stderr in one write.

## trail

Package trail manipulates slash-separated file paths (like Go's path/filepath on Unix).

- `const Separator = '/'`: Separator is the path separator byte.
- `Clean(path str) str`: Clean returns the shortest path equivalent to path by Go's rules: no "." or ".." elements where avoidable, no repeated or trailing slashes, "." for an empty path.
- `IsAbs(path str) bool`: IsAbs reports whether path starts with a slash.
- `Base(path str) str`: Base returns the last element of path after dropping trailing slashes: "." for an empty path, "/" for all slashes.
- `Dir(path str) str`: Dir returns Clean of everything but the last element of path: "." when there is no slash.
- `Ext(path str) str`: Ext returns the suffix of path's last element from its final dot, or "".
- `Split(path str) (str, str)`: Split splits path right after its last slash into (dir, file); dir keeps the slash.
- `JoinAll(parts []str) str`: JoinAll joins the non-empty parts with slashes and Cleans the result; "" when every part is empty.
- `Join2(a str, b str) str`: Join2 joins two path elements like Go's filepath.Join(a, b).
- `Join3(a str, b str, c str) str`: Join3 joins three path elements like Go's filepath.Join(a, b, c).
- `Rel(base str, targ str) !str`: Rel returns a relative path that is lexically equivalent to targ when joined to base, or a fault when one is absolute and the other is not or base holds "..".
- `Match(pattern str, name str) !bool`: Match reports whether name matches the shell pattern: '*' (no slash), '?', '[a-z]', '[^x]' and '\' escapes, like Go's filepath.Match.

## lever

Package lever parses command-line flags (like Go's flag): register handles, Parse the arguments, then read .Val().

- `type Flag struct`: Flag is one registered flag; the typed handles below wrap it.
- `type StrFlag struct`: StrFlag is the handle of a string flag.
- `type IntFlag struct`: IntFlag is the handle of an integer flag.
- `type BoolFlag struct`: BoolFlag is the handle of a boolean flag.
- `type F64Flag struct`: F64Flag is the handle of a floating-point flag.
- `Str(name str, def str, help str) StrFlag`: Str registers a string flag with its default and help text.
- `Int(name str, def i64, help str) IntFlag`: Int registers an integer flag with its default and help text.
- `Bool(name str, def bool, help str) BoolFlag`: Bool registers a boolean flag with its default and help text.
- `F64(name str, def f64, help str) F64Flag`: F64 registers a floating-point flag with its default and help text.
- `(h StrFlag) Val() str`: Val returns the flag's value (its default until Parse sets it).
- `(h IntFlag) Val() i64`: Val returns the flag's value (its default until Parse sets it).
- `(h BoolFlag) Val() bool`: Val returns the flag's value (its default until Parse sets it).
- `(h F64Flag) Val() f64`: Val returns the flag's value (its default until Parse sets it).
- `(h StrFlag) Given() bool`: Given reports whether the flag appeared on the command line.
- `(h IntFlag) Given() bool`: Given reports whether the flag appeared on the command line.
- `(h BoolFlag) Given() bool`: Given reports whether the flag appeared on the command line.
- `(h F64Flag) Given() bool`: Given reports whether the flag appeared on the command line.
- `Reset()`: Reset forgets every registered flag and parse result (for programs that parse several times).
- `Rest() []str`: Rest returns the arguments left after the flags (empty before Parse).
- `Parsed() bool`: Parsed reports whether Parse has run.
- `Set(name str, value str) !`: Set assigns value to the flag named name as if it were given on the command line.
- `Parse(args []str) !`: Parse reads flags from args (without the program name) until the first non-flag or "--"; the rest is kept for Rest().
- `Usage() str`: Usage returns the flags sorted by name, each with its value type, help and non-zero default, formatted exactly like Go's PrintDefaults.

## tide

Package tide is clocks, durations and civil (calendar) time in UTC, like Go's time package.

- `const Nanosecond = 1`: Durations are i64 nanoseconds; these constants are the units, like Go's time.Duration.
- `const Microsecond = 1000`
- `const Millisecond = 1000000`
- `const Second = 1000000000`
- `const Minute = 60000000000`
- `const Hour = 3600000000000`
- `const Sunday = 0`: Weekdays as returned in Civil.Weekday, Sunday first like Go.
- `const Monday = 1`
- `const Tuesday = 2`
- `const Wednesday = 3`
- `const Thursday = 4`
- `const Friday = 5`
- `const Saturday = 6`
- `Now() i64`: Now returns monotonic nanoseconds since boot (CLOCK_UPTIME_RAW): use it to measure intervals.
- `Wall() i64`: Wall returns the wall clock as nanoseconds since the Unix epoch, 1970-01-01T00:00:00Z.
- `Since(t i64) i64`: Since returns the nanoseconds elapsed since the Now() reading t.
- `Sleep(ns i64)`: Sleep pauses the current core for ns nanoseconds (nothing happens when ns <= 0).
- `Wait(ns i64) !`: Wait pauses for ns like Sleep, but inside a request with a deadline it fails with "deadline exceeded" once the deadline comes first. On a server core, other requests run while one waits.
- `Seconds(d i64) f64`: Seconds returns d as floating-point seconds, like Go's Duration.Seconds.
- `Minutes(d i64) f64`: Minutes returns d as floating-point minutes.
- `Hours(d i64) f64`: Hours returns d as floating-point hours.
- `Milliseconds(d i64) i64`: Milliseconds returns d as whole milliseconds, truncated toward zero.
- `Microseconds(d i64) i64`: Microseconds returns d as whole microseconds, truncated toward zero.
- `FormatDuration(d i64) str`: FormatDuration renders d exactly like Go's Duration.String: "1.5s", "250ms", "1h2m3s", "0s", "-1.5µs".
- `ParseDuration(s str) !i64`: ParseDuration parses "300ms", "-1.5h" or "2h45m" (units ns us µs ms s m h) exactly like Go's time.ParseDuration.
- `type Civil struct`: Civil is a broken-down UTC instant: Month 1..12, Day 1..31, Weekday 0 (Sunday)..6, YearDay 1..366.
- `IsLeap(year i64) bool`: IsLeap reports whether year is a leap year in the proleptic Gregorian calendar.
- `DaysIn(year i64, month i64) i64`: DaysIn returns the number of days in month (1..12) of year, or 0 for a month out of range.
- `DaysFromCivil(y i64, m i64, d i64) i64`: DaysFromCivil returns the days from 1970-01-01 to the date y-m-d (m 1..12; d may be out of range and carries).
- `CivilFromDays(z i64) (i64, i64, i64)`: CivilFromDays returns the (year, month, day) that is z days after 1970-01-01.
- `UTCSec(sec i64) Civil`: UTCSec breaks Unix seconds into UTC calendar fields (Nano is 0); it covers every i64 second.
- `UTC(ns i64) Civil`: UTC breaks the Unix-nanosecond instant ns into its UTC calendar fields.
- `Date(year i64, month i64, day i64, hour i64, min i64, sec i64, nano i64) i64`: Date returns the Unix nanoseconds of the UTC civil time; out-of-range fields carry like Go's time.Date (month 13 is January of the next year).
- `Unix(c Civil) i64`: Unix returns the Unix nanoseconds of c (the inverse of UTC; Weekday and YearDay are ignored, other fields carry).
- `UnixSec(c Civil) i64`: UnixSec returns the Unix seconds of c, rounded toward negative infinity.
- `WeekdayName(d i64) str`: WeekdayName returns the English name of weekday d (0 = Sunday), or "%!Weekday(d)" with d unsigned like Go.
- `MonthName(m i64) str`: MonthName returns the English name of month m (1 = January), or "%!Month(m)" with m unsigned like Go.
- `FormatRFC3339(ns i64) str`: FormatRFC3339 renders the Unix-nanosecond instant ns as "2026-10-01T11:22:05Z" (whole seconds, UTC).
- `FormatRFC3339Nano(ns i64) str`: FormatRFC3339Nano is FormatRFC3339 with the fractional seconds, trailing zeros removed: "2026-10-01T11:22:05.5Z".
- `ParseRFC3339(s str) !i64`: ParseRFC3339 parses "2026-10-01T11:22:05Z", optional fraction ".123" and offsets "+02:00", accepting what Go's time.Parse(RFC3339) accepts, into Unix nanoseconds.
- `FormatHTTP(unixSec i64) str`: FormatHTTP renders Unix seconds in the HTTP date format "Thu, 01 Oct 2026 11:22:05 GMT".

## dice

Package dice is fast pseudo-random numbers (like Go's math/rand): xoshiro256** generators and a lazily seeded per-core one.

- `type Rand struct`: Rand is a xoshiro256** generator; make one with New or FromState, or call the package functions for this core's generator.
- `(r mut Rand) Seed(s u64)`: Seed resets r to the sequence for seed s (expanded with splitmix64, so every seed gives a good state).
- `New(s u64) Rand`: New returns a generator seeded with s; equal seeds give equal sequences.
- `FromState(s0 u64, s1 u64, s2 u64, s3 u64) Rand`: FromState returns a generator holding the exact xoshiro256** state words, which must not all be zero.
- `(r Rand) State() (u64, u64, u64, u64)`: State returns the four state words, so the sequence can be resumed later with FromState.
- `(r mut Rand) U64() u64`: U64 returns the next uniformly distributed 64-bit value.
- `(r mut Rand) U32() u32`: U32 returns the next uniformly distributed 32-bit value (the high half of U64).
- `(r mut Rand) U64n(n u64) u64`: U64n returns a uniform value in [0, n) without bias (Lemire's method); n == 0 means the full 64-bit range.
- `(r mut Rand) I64n(n i64) i64`: I64n returns a uniform value in [0, n); it panics when n <= 0.
- `(r mut Rand) Intn(n i64) i64`: Intn is I64n under Go's name (Tin's int is i64).
- `(r mut Rand) Range(lo i64, hi i64) i64`: Range returns a uniform value in [lo, hi); it panics when hi <= lo.
- `(r mut Rand) F64() f64`: F64 returns a uniform float in [0, 1) built from 53 random bits.
- `(r mut Rand) NormF64() f64`: NormF64 returns a normally distributed float (mean 0, standard deviation 1) by Marsaglia's polar method.
- `(r mut Rand) Shuffle(xs mut []i64)`: Shuffle permutes xs uniformly in place (Fisher-Yates).
- `(r mut Rand) ShuffleStr(xs mut []str)`: ShuffleStr permutes the strings xs uniformly in place.
- `(r mut Rand) Perm(n i64) []i64`: Perm returns a uniformly random permutation of 0..n-1 (empty when n <= 0).
- `(r mut Rand) Fill(b mut []u8)`: Fill overwrites every byte of b with random bytes, eight at a time.
- `(r mut Rand) Bytes(n i64) []u8`: Bytes returns n random bytes (empty when n <= 0).
- `(r mut Rand) Str(n i64, alphabet str) str`: Str returns n characters drawn uniformly from alphabet (its bytes when ASCII, its runes otherwise); "" when n <= 0 or alphabet is empty.
- `Seed(s u64)`: Seed seeds this core's generator so that the package functions become deterministic on this core.
- `U64() u64`: U64 returns the next 64-bit value from this core's generator.
- `U32() u32`: U32 returns the next 32-bit value from this core's generator.
- `U64n(n u64) u64`: U64n returns a uniform value in [0, n) from this core's generator (n == 0 means the full range).
- `I64n(n i64) i64`: I64n returns a uniform value in [0, n) from this core's generator; it panics when n <= 0.
- `Intn(n i64) i64`: Intn is I64n under Go's name.
- `Range(lo i64, hi i64) i64`: Range returns a uniform value in [lo, hi) from this core's generator; it panics when hi <= lo.
- `F64() f64`: F64 returns a uniform float in [0, 1) from this core's generator.
- `NormF64() f64`: NormF64 returns a standard normal float from this core's generator.
- `Shuffle(xs mut []i64)`: Shuffle permutes xs uniformly in place with this core's generator.
- `ShuffleStr(xs mut []str)`: ShuffleStr permutes the strings xs uniformly in place with this core's generator.
- `Perm(n i64) []i64`: Perm returns a random permutation of 0..n-1 from this core's generator.
- `Fill(b mut []u8)`: Fill overwrites b with random bytes from this core's generator.
- `Bytes(n i64) []u8`: Bytes returns n random bytes from this core's generator.
- `Str(n i64, alphabet str) str`: Str returns n random characters of alphabet from this core's generator.

## sift

Package sift sorts and searches slices and has the generic functions on them (like Go's sort, slices and cmp). Sort, SortFunc, IsSorted and the rest work on any element type; the type-specific functions (Ints, Strs, SortBy ...) are the faster, older forms.

- `Ints(xs mut []i64)`: Ints sorts xs in increasing order with pattern-defeating quicksort (not stable, O(n log n) worst case).
- `IntsDesc(xs mut []i64)`: IntsDesc sorts xs in decreasing order.
- `U64s(xs mut []u64)`: U64s sorts xs in increasing unsigned order.
- `F64s(xs mut []f64)`: F64s sorts xs in increasing order with NaNs first, like Go's slices.Sort (-0 sorts before 0).
- `Strs(xs mut []str)`: Strs sorts xs in increasing bytewise order.
- `SortBy(xs mut []i64, less fn(i64, i64) bool)`: SortBy sorts xs so that less(xs[i+1], xs[i]) is never true (less must be a strict weak order).
- `HeapInts(xs mut []i64)`: HeapInts sorts xs in increasing order with heapsort (slower than Ints, no recursion, no extra memory).
- `StableInts(xs mut []i64)`: StableInts sorts xs in increasing order with a merge sort that keeps equal elements in their original order.
- `IsSortedInts(xs []i64) bool`: IsSortedInts reports whether xs is in increasing order.
- `IsSortedStrs(xs []str) bool`: IsSortedStrs reports whether xs is in increasing bytewise order.
- `SearchInts(xs []i64, x i64) i64`: SearchInts returns the first index of sorted xs holding a value >= x (len(xs) when there is none).
- `SearchStrs(xs []str, x str) i64`: SearchStrs returns the first index of sorted xs holding a str >= x bytewise (len(xs) when there is none).
- `ReverseInts(xs mut []i64)`: ReverseInts reverses xs in place.
- `ReverseStrs(xs mut []str)`: ReverseStrs reverses xs in place.
- `UniqInts(xs mut []i64) i64`: UniqInts compacts runs of equal values in sorted xs to one element and returns the new length (xs[0:k] is the result).
- `MinInts(xs []i64) !i64`: MinInts returns the smallest element of xs, or a fault when xs is empty.
- `MaxInts(xs []i64) !i64`: MaxInts returns the largest element of xs, or a fault when xs is empty.
- `SumInts(xs []i64) i64`: SumInts returns the sum of xs (wrapping on overflow, 0 for an empty slice).
- `IndexInts(xs []i64, x i64) i64`: IndexInts returns the index of the first x in xs, or -1.
- `ContainsStr(xs []str, x str) bool`: ContainsStr reports whether x occurs in xs.
- `EqualInts(a []i64, b []i64) bool`: EqualInts reports whether a and b have the same length and elements.
- `Map[T constraints.Any, U constraints.Any](xs []T, f fn(T) U) []U`: Map returns f applied to each element of xs.
- `Filter[T constraints.Any](xs []T, keep_ fn(T) bool) []T`: Filter returns the elements of xs for which keep returns true, in order.
- `Reduce[T constraints.Any, A constraints.Any](xs []T, start A, f fn(A, T) A) A`: Reduce folds xs into one value: f(f(f(start, x0), x1), ...).
- `shape Ordered = i64 | i32 | i16 | i8 | u64 | u32 | u16 | u8 | f64 | f32 | str`: Ordered is the set of built-in types with a total ordering operator.
- `Sort[E Ordered](xs mut []E)`: Sort sorts xs in ascending order, in place. Floating-point NaNs sort first. It is not stable, and the order of equal elements is the same as Go's slices.Sort.
- `SortFunc[E constraints.Any](xs mut []E, cmp fn(E, E) i64)`: SortFunc sorts xs in place by cmp, which returns a negative number when a sorts before b, zero when they are equal and a positive number after. It is not stable.
- `SortStableFunc[E constraints.Any](xs mut []E, cmp fn(E, E) i64)`: SortStableFunc is SortFunc, keeping the original order of elements that compare equal.
- `IsSorted[E Ordered](xs []E) bool`: IsSorted reports whether xs is in ascending order.
- `IsSortedFunc[E constraints.Any](xs []E, cmp fn(E, E) i64) bool`: IsSortedFunc reports whether xs is sorted by cmp.
- `Less[E Ordered](x E, y E) bool`: Less is cmp.Less: x < y, with NaN smaller than every other value (and so before them in Sort).
- `Cmp[E Ordered](x E, y E) i64`: Cmp is cmp.Compare: -1 if x sorts before y, 0 if they are equal, +1 after. NaNs are equal to each other and sort before every other value.
- `BinarySearch[E Ordered](xs []E, target E) (i64, bool)`: BinarySearch searches the sorted xs for target and returns the position where it is, or would be inserted, and whether it is there.
- `BinarySearchFunc[E constraints.Any, T constraints.Any](xs []E, target T, cmp fn(E, T) i64) (i64, bool)`: BinarySearchFunc is BinarySearch for a target of another type, ordered by cmp(element, target).
- `Min[E Ordered](xs []E) E`: Min returns the smallest element of xs; a NaN anywhere gives NaN. It panics if xs is empty. (-0 and +0 compare equal here, so a mix of them returns whichever comes first.)
- `Max[E Ordered](xs []E) E`: Max returns the largest element of xs; a NaN anywhere gives NaN. It panics if xs is empty.
- `MinFunc[E constraints.Any](xs []E, cmp fn(E, E) i64) E`: MinFunc returns the first smallest element of xs by cmp. It panics if xs is empty.
- `MaxFunc[E constraints.Any](xs []E, cmp fn(E, E) i64) E`: MaxFunc returns the first largest element of xs by cmp. It panics if xs is empty.
- `Index[E constraints.Comparable](xs []E, v E) i64`: Index returns the position of the first element equal to v, or -1.
- `IndexFunc[E constraints.Any](xs []E, f fn(E) bool) i64`: IndexFunc returns the position of the first element for which f is true, or -1.
- `Contains[E constraints.Comparable](xs []E, v E) bool`: Contains reports whether v is in xs.
- `ContainsFunc[E constraints.Any](xs []E, f fn(E) bool) bool`: ContainsFunc reports whether f is true for some element of xs.
- `Equal[E constraints.Comparable](a []E, b []E) bool`: Equal reports whether a and b have the same length and equal elements.
- `EqualFunc[A constraints.Any, B constraints.Any](a []A, b []B, eq fn(A, B) bool) bool`: EqualFunc is Equal for two element types, with eq deciding.
- `Compare[E Ordered](a []E, b []E) i64`: Compare compares a and b element by element with Cmp, then by length: -1, 0 or +1.
- `CompareFunc[A constraints.Any, B constraints.Any](a []A, b []B, cmp fn(A, B) i64) i64`: CompareFunc is Compare for two element types, with cmp comparing elements.
- `Reverse[E constraints.Any](xs mut []E)`: Reverse reverses xs in place.
- `Clone[E constraints.Any](xs []E) []E`: Clone returns a copy of xs that shares nothing with it.
- `Grow[E constraints.Any](xs []E, n i64) []E`: Grow returns a copy of xs with room for n more elements before it has to grow again.
- `Concat[E constraints.Any](a []E, b []E) []E`: Concat returns a new slice holding a followed by b.
- `ConcatAll[E constraints.Any](parts [][]E) []E`: ConcatAll returns a new slice holding every slice of parts, in order.
- `Repeat[E constraints.Any](xs []E, count i64) []E`: Repeat returns a new slice that repeats xs count times.
- `Insert[E constraints.Any](xs mut []E, i i64, v E) []E`: Insert inserts v at position i (0 to len(xs)) and returns the longer slice. Like append, it grows xs in place, so every other reference to the same slice sees the new length.
- `InsertAll[E constraints.Any](xs mut []E, i i64, vs []E) []E`: InsertAll inserts all of vs at position i and returns the longer slice (grown in place, as Insert).
- `Delete[E constraints.Any](xs mut []E, i i64, j i64) []E`: Delete removes xs[i:j] and returns the shorter slice; the elements after j move down in place.
- `DeleteFunc[E constraints.Any](xs mut []E, del fn(E) bool) []E`: DeleteFunc removes the elements for which del is true, in place, and returns the shorter slice.
- `Replace[E constraints.Any](xs mut []E, i i64, j i64, vs []E) []E`: Replace replaces xs[i:j] with vs and returns the resulting slice (grown or shrunk in place).
- `Compact[E constraints.Comparable](xs mut []E) []E`: Compact removes runs of equal consecutive elements, keeping the first of each run, in place, and returns the shorter slice.
- `CompactFunc[E constraints.Any](xs mut []E, eq fn(E, E) bool) []E`: CompactFunc is Compact with eq deciding which neighbours are equal.
- `Each[E constraints.Any](xs []E, f fn(E))`: Each calls f for every element of xs in ascending index order.

## atlas

Package atlas is the functions on maps (like Go's maps): keys, values, copies and comparisons.

- `Keys[K constraints.Comparable, V constraints.Any](m map[K]V) []K`: Keys returns m's keys in insertion order.
- `Values[K constraints.Comparable, V constraints.Any](m map[K]V) []V`: Values returns m's values in insertion order.
- `SortedKeys[K sift.Ordered, V constraints.Any](m map[K]V) []K`: SortedKeys returns m's keys in ascending order (NaN first), whatever order they were added in.
- `Clone[K constraints.Comparable, V constraints.Any](m map[K]V) map[K]V`: Clone returns a new map with the same entries, in the same order.
- `Copy[K constraints.Comparable, V constraints.Any](dst mut map[K]V, src map[K]V)`: Copy adds every entry of src to dst, replacing the values of keys dst already has.
- `Equal[K constraints.Comparable, V constraints.Comparable](a map[K]V, b map[K]V) bool`: Equal reports whether a and b have the same keys with equal values.
- `EqualFunc[K constraints.Comparable, V1 constraints.Any, V2 constraints.Any](a map[K]V1, b map[K]V2, eq fn(V1, V2) bool) bool`: EqualFunc is Equal with eq comparing the values, which may have different types.
- `DeleteFunc[K constraints.Comparable, V constraints.Any](m mut map[K]V, del fn(K, V) bool)`: DeleteFunc removes the entries for which del is true.

## cairn

Package cairn is a set of containers for i64 and str values: heaps, a deque, a queue, hash sets, a bitset and an LRU cache.

- `type IntHeap struct`: IntHeap is a binary min-heap of i64 values; IntHeap{} is ready to use.
- `NewIntHeap(n i64) IntHeap`: NewIntHeap returns an empty min-heap with room for n values.
- `(h mut IntHeap) Push(v i64)`: Push adds v to the heap.
- `(h mut IntHeap) Pop() (i64, bool)`: Pop removes and returns the smallest value, or (0, false) when the heap is empty.
- `(h IntHeap) Peek() (i64, bool)`: Peek returns the smallest value without removing it, or (0, false) when the heap is empty.
- `(h IntHeap) Len() i64`: Len returns the number of values in the heap.
- `type IntMaxHeap struct`: IntMaxHeap is a binary max-heap of i64 values; IntMaxHeap{} is ready to use.
- `NewIntMaxHeap(n i64) IntMaxHeap`: NewIntMaxHeap returns an empty max-heap with room for n values.
- `(h mut IntMaxHeap) Push(v i64)`: Push adds v to the heap.
- `(h mut IntMaxHeap) Pop() (i64, bool)`: Pop removes and returns the largest value, or (0, false) when the heap is empty.
- `(h IntMaxHeap) Peek() (i64, bool)`: Peek returns the largest value without removing it, or (0, false) when the heap is empty.
- `(h IntMaxHeap) Len() i64`: Len returns the number of values in the heap.
- `type IntDeque struct`: IntDeque is a double-ended queue of i64 values in a growing ring buffer; IntDeque{} is ready to use.
- `NewIntDeque(n i64) IntDeque`: NewIntDeque returns an empty deque with room for n values.
- `(d mut IntDeque) PushBack(v i64)`: PushBack appends v at the back.
- `(d mut IntDeque) PushFront(v i64)`: PushFront prepends v at the front.
- `(d mut IntDeque) PopFront() (i64, bool)`: PopFront removes and returns the front value, or (0, false) when the deque is empty.
- `(d mut IntDeque) PopBack() (i64, bool)`: PopBack removes and returns the back value, or (0, false) when the deque is empty.
- `(d IntDeque) Front() (i64, bool)`: Front returns the front value, or (0, false) when the deque is empty.
- `(d IntDeque) Back() (i64, bool)`: Back returns the back value, or (0, false) when the deque is empty.
- `(d IntDeque) At(i i64) i64`: At returns the i-th value from the front, panicking when i is out of range.
- `(d IntDeque) Len() i64`: Len returns the number of values in the deque.
- `type IntQueue struct`: IntQueue is a first-in first-out queue of i64 values in a growing ring buffer; IntQueue{} is ready to use.
- `NewIntQueue(n i64) IntQueue`: NewIntQueue returns an empty queue with room for n values.
- `(q mut IntQueue) Push(v i64)`: Push appends v at the back of the queue.
- `(q mut IntQueue) Pop() (i64, bool)`: Pop removes and returns the front value, or (0, false) when the queue is empty.
- `(q IntQueue) Peek() (i64, bool)`: Peek returns the front value without removing it, or (0, false) when the queue is empty.
- `(q IntQueue) Len() i64`: Len returns the number of values in the queue.
- `type IntSet struct`: IntSet is a hash set of i64 values with open addressing and linear probing; IntSet{} is ready to use.
- `NewIntSet(n i64) IntSet`: NewIntSet returns an empty set sized for about n values.
- `(s mut IntSet) Add(k i64) bool`: Add puts k in the set and reports whether it was absent.
- `(s IntSet) Has(k i64) bool`: Has reports whether k is in the set.
- `(s mut IntSet) Del(k i64) bool`: Del removes k and reports whether it was present.
- `(s IntSet) Len() i64`: Len returns the number of values in the set.
- `(s IntSet) Keys() []i64`: Keys returns the values in table order (unsorted).
- `type StrSet struct`: StrSet is a set of strs backed by a map; make one with NewStrSet.
- `NewStrSet() StrSet`: NewStrSet returns an empty set.
- `(s mut StrSet) Add(k str) bool`: Add puts k in the set and reports whether it was absent.
- `(s StrSet) Has(k str) bool`: Has reports whether k is in the set.
- `(s mut StrSet) Del(k str) bool`: Del removes k and reports whether it was present.
- `(s StrSet) Len() i64`: Len returns the number of strs in the set.
- `(s StrSet) Keys() []str`: Keys returns the strs in map order (unsorted).
- `type Bitset struct`: Bitset is a growing set of bit indexes stored in []u64 words; Bitset{} is ready to use.
- `NewBitset(n i64) Bitset`: NewBitset returns a bitset with room for n bits (Set grows it further as needed).
- `(b mut Bitset) Set(i i64)`: Set turns bit i on, growing the bitset when i is past its end.
- `(b mut Bitset) Clear(i i64)`: Clear turns bit i off (bits past the end are already off).
- `(b Bitset) Has(i i64) bool`: Has reports whether bit i is on (false past the end or for a negative i).
- `(b Bitset) Count() i64`: Count returns the number of bits that are on.
- `(b Bitset) Next(i i64) i64`: Next returns the lowest bit index >= i that is on, or -1.
- `(b Bitset) Len() i64`: Len returns the number of bits the bitset currently holds words for.
- `(b Bitset) Words() []u64`: Words returns the underlying words without copying.
- `type LRU struct`: LRU is a least-recently-used cache from str to str with a fixed capacity; use NewLRU.
- `NewLRU(capacity i64) LRU`: NewLRU returns an empty cache holding at most capacity entries (at least 1).
- `(c mut LRU) Get(k str) (str, bool)`: Get returns the value for k and marks it most recently used, or ("", false).
- `(c LRU) Peek(k str) (str, bool)`: Peek returns the value for k without touching its recency, or ("", false).
- `(c LRU) Has(k str) bool`: Has reports whether k is cached, without touching its recency.
- `(c mut LRU) Put(k str, v str)`: Put stores v under k as most recently used, evicting the least recently used entry when full.
- `(c mut LRU) Del(k str) bool`: Del removes k and reports whether it was cached.
- `(c LRU) Len() i64`: Len returns the number of cached entries.
- `(c LRU) Cap() i64`: Cap returns the capacity.
- `(c LRU) Keys() []str`: Keys returns the cached keys from most to least recently used.

## stamp

Package stamp computes non-cryptographic hashes and checksums: FNV-1a, CRC-32 (IEEE and Castagnoli, slicing-by-8), Adler-32, xxHash64, and Hash, a fast 64-bit hash for tables.

- `Crc32(s str) u32`: Crc32 is the IEEE CRC-32 of s (as in zip, gzip and PNG).
- `Crc32Update(crc u32, s str) u32`: Crc32Update continues an IEEE CRC-32 over more data.
- `Crc32C(s str) u32`: Crc32C is the Castagnoli CRC-32 of s (as in iSCSI, ext4 and many databases).
- `Fnv32a(s str) u32`: Fnv32a is the 32-bit FNV-1a hash of s.
- `Fnv64a(s str) u64`: Fnv64a is the 64-bit FNV-1a hash of s.
- `Adler32(s str) u32`: Adler32 is the Adler-32 checksum of s (as in zlib).
- `Xxh64(s str, seed u64) u64`: Xxh64 is the xxHash64 of s with seed.
- `Hash(s str) u64`: Hash is a fast, well-mixed 64-bit hash for hash tables (not stable across versions).

## squash

Package squash compresses and decompresses: DEFLATE (RFC 1951) and its gzip (RFC 1952) and zlib (RFC 1950) wrappers like Go's compress/flate, compress/gzip and compress/zlib, plus Snappy, LZ4 and Zstandard (RFC 8878). Every decoder takes the most bytes it may produce and fails with fault.LimitExceeded past it, so a small input cannot make a huge output.

```tin body
let z = squash.Gzip("hello, hello, hello", squash.Default)
let back = try squash.Gunzip(z, 64mb)
```

- `Deflate(data str, level i64) str`: Deflate compresses data as raw DEFLATE at level (Store to Best).
- `const Store = 0`: Levels for Deflate, Gzip, Zlib and Zstd: Store writes the data uncompressed (in valid frames), Fastest and Best trade speed against size, Default is between.
- `const Fastest = 1`
- `const Default = 6`
- `const Best = 9`
- `Inflate(data str, max i64) !str`: Inflate decompresses raw DEFLATE data, producing at most max bytes.
- `Gzip(data str, level i64) str`: Gzip compresses data as one gzip member (no name, no time, OS unknown) at level.
- `Gunzip(data str, max i64) !str`: Gunzip decompresses gzip data (one member or several back to back), producing at most max bytes. It checks each member's CRC-32 and length.
- `Zlib(data str, level i64) str`: Zlib compresses data in the zlib format (RFC 1950) at level.
- `Unzlib(data str, max i64) !str`: Unzlib decompresses zlib data, producing at most max bytes, and checks its Adler-32.
- `Lz4(data str) str`: Lz4 compresses data as one LZ4 frame: independent 64 KiB blocks, a stored block where compression does not help, and a content checksum.
- `Lz4NoChecksum(data str) str`: Lz4NoChecksum is Lz4 without the content checksum (the frame Kafka's Java client writes).
- `Unlz4(data str, max i64) !str`: Unlz4 decompresses LZ4 frames (one or several, and skippable frames), producing at most max bytes.
- `Lz4BlockOf(data str) str`: Lz4BlockOf compresses data as one bare LZ4 block (no frame).
- `UnLz4Block(b str, max i64) !str`: UnLz4Block decompresses one bare LZ4 block, producing at most max bytes.
- `Snappy(data str) str`: Snappy compresses data as one Snappy block.
- `Unsnappy(data str, max i64) !str`: Unsnappy decompresses one Snappy block whose length is at most max.
- `Unzstd(data str, max i64) !str`: Unzstd decompresses Zstandard data (any number of frames, and skippable frames), producing at most max bytes.
- `Zstd(data str, level i64) str`: Zstd compresses data as one Zstandard frame at level (Store to Best; Store writes raw blocks).

## seal

Package seal has cryptographic hashes (SHA-256, SHA-384, SHA-512, SHA-1), HMAC over any of the SHA-2 hashes, HKDF, PBKDF2-HMAC-SHA-256, P-256 ECDH, RSA signature verification (PKCS #1 v1.5 and PSS), X.509 certificates with chain and host name verification, constant-time comparison, secure random bytes, the hex, base64 and PEM encodings, and RSA-OAEP encryption with a public key.

- `type AEAD struct`: AEAD is an authenticated cipher with its key (AES-GCM or ChaCha20-Poly1305): Seal encrypts and appends a 16-byte tag, Open checks the tag in constant time and decrypts.
- `NewChaCha20Poly1305(key secret []u8) !AEAD`: NewChaCha20Poly1305 is the RFC 8439 AEAD with a 32-byte key.
- `(a AEAD) NonceSize() i64`: NonceSize is the nonce length in bytes (12).
- `(a AEAD) Overhead() i64`: Overhead is the tag length in bytes (16).
- `(a AEAD) Seal(nonce []u8, plaintext secret []u8, aad []u8) ![]u8`: Seal encrypts plaintext and authenticates it with aad under a 12-byte nonce, returning the ciphertext followed by the tag. A nonce must never be used twice with one key.
- `(a AEAD) Open(nonce []u8, sealed []u8, aad []u8) ![]u8`: Open checks the tag of sealed (ciphertext then tag) against aad and the nonce and returns the plaintext; it fails, revealing nothing else, when anything was changed.
- `(a mut AEAD) Rekey(key secret []u8) !`: Rekey replaces a's key with key, of the same algorithm and length, reusing a's memory: an AEAD kept in long-lived memory (a connection's state) can change keys without allocating there.
- `AESHardware() bool`: AESHardware reports whether AES-GCM runs on the CPU's AES instructions here (AES-NI and PCLMULQDQ, or ARMv8 AES and PMULL); without them it runs a slower constant-time software path and ChaCha20-Poly1305 is the faster choice.
- `NewAESGCM(key secret []u8) !AEAD`: NewAESGCM is AES-GCM (16-byte tags, 12-byte nonces) with a 16-, 24- or 32-byte key (AES-128, AES-192 or AES-256).
- `ChaCha20(key secret []u8, nonce []u8, counter u32, data []u8) ![]u8`: ChaCha20 XORs data with the ChaCha20 keystream (RFC 8439) for a 32-byte key, a 12-byte nonce and the initial block counter.
- `ParseRSAPublicKeyDER(der []u8) !RSAPublicKey`: ParseRSAPublicKeyDER reads a DER RSAPublicKey (PKCS #1) or SubjectPublicKeyInfo holding one.
- `VerifyECDSA(curve str, pub []u8, digest []u8, sig []u8) !`: VerifyECDSA checks a DER-encoded ECDSA signature over digest (a hash of the message) by the public key pub, an uncompressed point on curve ("P-256" or "P-384"). A digest longer than the curve's order is truncated to its leftmost bytes, as FIPS 186-5 says.
- `SignECDSA(k ECPrivateKey, h Hash, digest []u8) ![]u8`: SignECDSA signs digest (a hash of the message, made with h) with k and returns a DER ECDSA-Sig-Value. The nonce is RFC 6979's, derived with HMAC over h, so equal inputs give equal signatures.
- `(k PrivateKey) SignTLS(scheme i64, msg []u8) ![]u8`: SignTLS signs msg (the bytes a TLS 1.3 CertificateVerify covers) with k under scheme: RSA-PSS 0x0804-0x0806 for RSA keys, 0x0403 for P-256 and 0x0503 for P-384.
- `VerifyEd25519(pub []u8, msg []u8, sig []u8) !`: VerifyEd25519 checks an Ed25519 signature (64 bytes) of msg by the public key pub (32 bytes).
- `type Hash enum { SHA256, SHA384, SHA512 }`: Hash names a SHA-2 function for Hmac and HKDF.
- `Sum(h Hash, s secret str) []u8`: Sum is the digest of s under h; s may be secret.
- `Size(h Hash) i64`: Size is the length in bytes of h's digest.
- `BlockSize(h Hash) i64`: BlockSize is the length in bytes of h's input block (the HMAC key block).
- `Hmac(h Hash, key secret str, msg str) []u8`: Hmac is the HMAC of msg under key with hash h (RFC 2104); key may be secret.
- `HkdfExtract(h Hash, salt str, ikm secret str) []u8`: HkdfExtract is HKDF-Extract(salt, ikm) (RFC 5869): a pseudorandom key of Size(h) bytes. An empty salt means Size(h) zero bytes. ikm may be secret.
- `HkdfExpand(h Hash, prk secret str, info str, n i64) ![]u8`: HkdfExpand is HKDF-Expand(prk, info, n) (RFC 5869): n bytes, at most 255*Size(h). prk may be secret.
- `HkdfExpandLabel(h Hash, key secret str, label str, context str, n i64) ![]u8`: HkdfExpandLabel is TLS 1.3's HKDF-Expand-Label(secret, label, context, n) (RFC 8446 section 7.1); label is given without the "tls13 " prefix. key may be secret.
- `type RSAPrivateKey struct`: RSAPrivateKey is an RSA key with its CRT values; the private parts can only be read by seal.
- `type ECPrivateKey struct`: ECPrivateKey is an ECDSA key on P-256 or P-384: the curve, the scalar and the uncompressed public point.
- `type PrivateKey struct`: PrivateKey is an RSA or ECDSA private key, as ParsePrivateKeyPEM reads it.
- `ParsePrivateKeyDER(der []u8) !PrivateKey`: ParsePrivateKeyDER reads a PKCS #8 PrivateKeyInfo, a PKCS #1 RSAPrivateKey or a SEC 1 ECPrivateKey.
- `ParsePrivateKeyPEM(pem str) !PrivateKey`: ParsePrivateKeyPEM reads the first "PRIVATE KEY", "RSA PRIVATE KEY" or "EC PRIVATE KEY" block of pem.
- `(k PrivateKey) MatchesCertificate(c Certificate) bool`: MatchesCertificate reports whether k is the private key of c's public key.
- `P256NewPrivateKey() []u8`: P256NewPrivateKey returns a random P-256 private key: 32 big-endian bytes in [1, n-1].
- `P256PublicKey(priv secret []u8) ![]u8`: P256PublicKey is the uncompressed public key (65 bytes) of a P-256 private key; it fails unless priv is 32 bytes in [1, n-1]. Constant-time in priv.
- `P256ECDH(priv secret []u8, peer []u8) ![]u8`: P256ECDH is the P-256 Diffie-Hellman shared secret (the 32-byte x coordinate of priv*peer). peer is an uncompressed or compressed public key; it fails for an invalid private key, a point not on the curve, or a result at infinity. Constant-time in priv.
- `RSAKeyBits(key RSAPublicKey) i64`: RSAKeyBits is the size of key's modulus in bits.
- `VerifyPKCS1v15(key RSAPublicKey, h Hash, digest []u8, sig []u8) !`: VerifyPKCS1v15 checks an RSASSA-PKCS1-v1_5 signature over digest, a hash made with h.
- `VerifyPSS(key RSAPublicKey, h Hash, digest []u8, sig []u8, saltLen i64) !`: VerifyPSS checks an RSASSA-PSS signature over digest, a hash made with h, with MGF1 over the same hash. saltLen is the exact salt length, or -1 to accept any.
- `SignPKCS1v15(k mut RSAPrivateKey, h Hash, digest []u8) ![]u8`: SignPKCS1v15 signs digest, a hash made with h, with RSASSA-PKCS1-v1_5 (deterministic).
- `SignPSS(k mut RSAPrivateKey, h Hash, digest []u8) ![]u8`: SignPSS signs digest, a hash made with h, with RSASSA-PSS: MGF1 over h and a random salt as long as the digest (what TLS 1.3 requires).
- `Sha256(s secret str) []u8`: Sha256 is the SHA-256 digest of s (32 bytes); s may be secret.
- `Sha256Soft(s str) []u8`: Sha256Soft is SHA-256 in portable code (the reference the hardware path is tested against).
- `Sha256Hex(s secret str) str`: Sha256Hex is the SHA-256 digest of s in lower-case hex; s may be secret.
- `Sha1(s str) []u8`: Sha1 is the SHA-1 digest of s (20 bytes); use it only where a protocol requires it.
- `HmacSha256(key secret str, msg str) []u8`: HmacSha256 is the HMAC-SHA256 of msg under key (32 bytes); key may be secret.
- `Pbkdf2Sha256(password secret str, salt str, iterations i64, length i64) ![]u8`: Pbkdf2Sha256 derives length bytes using PBKDF2-HMAC-SHA-256. Iterations must be positive; length must be between 0 and 1 MiB. Temporary storage is reused between rounds, so memory usage does not grow with iterations. Choose the work factor for your protocol or password policy (this function does not choose one). The password may be secret.
- `Pbkdf2Sha256Timeout(password secret str, salt str, iterations i64, length i64, timeout i64) ![]u8`: Pbkdf2Sha256Timeout derives bytes like Pbkdf2Sha256, with a timeout in nanoseconds (<= 0: no limit). Both forms honor request deadlines and let other tasks run between batches of rounds. Scratch storage is released before any timeout fault returns.
- `ConstantTimeEq(a secret []u8, b secret []u8) bool`: ConstantTimeEq compares a and b in time that depends only on their lengths; they may be secret.
- `Equal(a secret str, b secret str) bool`: Equal reports whether a and b hold the same bytes, in time that depends only on their lengths. It is how secrets are compared: == on a secret is a compile error.
- `RandomBytes(n i64) []u8`: RandomBytes returns n cryptographically secure random bytes.
- `Hex(b []u8) str`: Hex encodes b in lower-case hexadecimal.
- `HexDecode(s str) ![]u8`: HexDecode decodes hexadecimal text.
- `B64(b []u8) str`: B64 encodes b as standard padded base64.
- `B64Decode(s str) ![]u8`: B64Decode decodes standard padded base64.
- `B64URL(b []u8) str`: B64URL encodes b as unpadded URL-safe base64 (as in JWTs).
- `B64URLDecode(s str) ![]u8`: B64URLDecode decodes unpadded URL-safe base64.
- `type RSAPublicKey struct`: RSAPublicKey is an RSA public key: modulus N and exponent E, as big-endian bytes.
- `ParseRSAPublicKeyPEM(pem str) !RSAPublicKey`: ParseRSAPublicKeyPEM reads a PEM "PUBLIC KEY" (SubjectPublicKeyInfo) or "RSA PUBLIC KEY" (PKCS #1) block.
- `EncryptOAEPSha1(key RSAPublicKey, msg []u8) ![]u8`: EncryptOAEPSha1 encrypts msg for key with RSA-OAEP (SHA-1, MGF1-SHA-1, empty label), as MySQL's caching_sha2_password and sha256_password expect.
- `Sha512(s secret str) []u8`: Sha512 is the SHA-512 digest of s (64 bytes); s may be secret.
- `Sha384(s secret str) []u8`: Sha384 is the SHA-384 digest of s (48 bytes); s may be secret.
- `X25519(scalar secret []u8, point []u8) ![]u8`: X25519 is the RFC 7748 function: the shared secret of a 32-byte private scalar and a peer's 32-byte public key. It fails for wrong lengths and when the result is all zeros (a low-order peer key), as TLS 1.3 requires. Constant-time in the scalar and the point.
- `X25519NewPrivateKey() []u8`: X25519NewPrivateKey returns 32 random bytes to use as an X25519 private key.
- `X25519PublicKey(priv secret []u8) ![]u8`: X25519PublicKey is the public key (32 bytes) of a 32-byte X25519 private key.
- `type PEMBlock struct`: PEMBlock is one "-----BEGIN TYPE-----" block: its type and decoded bytes.
- `DecodePEM(text str) ![]PEMBlock`: DecodePEM returns every PEM block in text, in order; text between blocks is ignored.
- `type SignatureAlgorithm enum`: SignatureAlgorithm is how a certificate is signed.
- `type PublicKeyAlgorithm enum`: PublicKeyAlgorithm is the kind of key a certificate holds.
- `const KeyUsageDigitalSignature = 1`: Key usage bits (KeyUsage), numbered as in RFC 5280 with bit 0 = digitalSignature.
- `const KeyUsageContentCommitment = 2`
- `const KeyUsageKeyEncipherment = 4`
- `const KeyUsageDataEncipherment = 8`
- `const KeyUsageKeyAgreement = 16`
- `const KeyUsageCertSign = 32`
- `const KeyUsageCRLSign = 64`
- `const KeyUsageEncipherOnly = 128`
- `const KeyUsageDecipherOnly = 256`
- `const ExtKeyUsageAny = "2.5.29.37.0"`: Extended key usage OIDs.
- `const ExtKeyUsageServerAuth = "1.3.6.1.5.5.7.3.1"`
- `const ExtKeyUsageClientAuth = "1.3.6.1.5.5.7.3.2"`
- `type Name struct`: Name is a distinguished name: the common attributes, and the DER bytes chains are matched on.
- `type Certificate struct`: Certificate is a parsed X.509 v1/v3 certificate. Times are Unix seconds.
- `(n Name) String() str`: String formats n like "CN=example.com,O=Example,C=US".
- `ParseCertificate(der []u8) !Certificate`: ParseCertificate parses one DER certificate. Slices in the result share der's memory.
- `ParseCertificatesPEM(pem str) ![]Certificate`: ParseCertificatesPEM parses every CERTIFICATE block in pem (other blocks are skipped).
- `(c Certificate) CheckSignature(alg SignatureAlgorithm, signed []u8, sig []u8) !`: CheckSignature checks that sig is c's key's signature of signed under alg. SHA-1 is refused.
- `(c Certificate) CheckSignatureFrom(parent Certificate) !`: CheckSignatureFrom checks that parent signed c. It does not check that parent may sign.
- `(c Certificate) CheckTLSSignature(scheme i64, signed []u8, sig []u8) !`: CheckTLSSignature checks a TLS 1.3 CertificateVerify signature by c's key: scheme is the SignatureScheme code and signed the bytes the peer signed (padding, context and transcript hash).
- `type CertPool struct`: CertPool is a set of certificates indexed by subject, used for roots and intermediates.
- `NewCertPool() CertPool`: NewCertPool returns an empty pool.
- `(p mut CertPool) Add(c Certificate)`: Add adds c to the pool unless it is already there.
- `(p mut CertPool) AddPEM(pem str) !i64`: AddPEM adds every certificate in pem that parses and returns how many were added; it fails only when none could be.
- `(p CertPool) Len() i64`: Len is the number of certificates in the pool.
- `(p CertPool) Certificates() []Certificate`: Certificates returns the pool's certificates in the order they were added.
- `SystemRoots() !CertPool`: SystemRoots loads the operating system's trusted roots (SSL_CERT_FILE overrides the location) once per core and returns them.
- `type VerifyOptions struct`: VerifyOptions controls Verify. Roots nil means the system roots; Now 0 means the clock; DNSName "" skips the host name check; KeyUsages empty means server authentication; MaxChain 0 means 8 certificates, leaf and root included.
- `(c Certificate) Verify(opts VerifyOptions) ![]Certificate`: Verify builds a chain from c through opts.Intermediates to a trusted root and checks it: validity periods, CA and key-usage rules, path lengths, name constraints, signatures (no SHA-1), the chain length and the host name. The chain is returned leaf first, root last.
- `ParseIP(s str) ?[]u8`: ParseIP parses dotted IPv4 (4 bytes) or IPv6 text (16 bytes), optionally in brackets; nil if invalid.
- `(c Certificate) VerifyHostname(host str) !`: VerifyHostname checks that c is valid for host: an IP address against the IP SANs, otherwise a DNS name against the DNS SANs (case-insensitive, one leftmost "*" label followed by at least two labels; a host containing "*" never matches). The common name is not used.

## herald

Package herald writes leveled log lines, one write(2) per line so cores never interleave:

```text
2026-10-01T11:22:05.123Z INFO core=2 listening addr=:8080
```

- `const LDebug = 0`
- `const LInfo = 1`
- `const LWarn = 2`
- `const LError = 3`
- `SetLevel(l i64)`: SetLevel drops lines below l (LDebug, LInfo, LWarn, LError) on this core.
- `SetOutput(fd i64)`: SetOutput sends this core's lines to file descriptor fd.
- `SetClock(f fn() i64)`: SetClock replaces the clock (unix milliseconds), for tests.
- `Line(l i64, msg str, kv []str) str`: Line formats a log line (without writing it): timestamp, level, core, message, pairs.
- `Log(l i64, msg str, kv []str)`: Log writes msg at level l with key/value pairs kv (k1, v1, k2, v2, ...).
- `Debug(msg str)`: Debug logs msg at debug level.
- `Info(msg str)`: Info logs msg at info level.
- `Warn(msg str)`: Warn logs msg at warning level.
- `Error(msg str)`: Error logs msg at error level.
- `Info2(msg str, k str, v str)`: Info2 logs msg with one key/value pair.
- `Info4(msg str, k1 str, v1 str, k2 str, v2 str)`: Info4 logs msg with two key/value pairs.
- `Error2(msg str, k str, v str)`: Error2 logs msg with one key/value pair at error level.

## crucible

Package crucible is for tests and micro-benchmarks: labeled checks that collect failures, Done to report them (exit status 1 on failure), and Bench to time a function.

```tin body
crucible.EqI("sum", 2 + 3, 5)
crucible.Done()
```

- `EqI(label str, got i64, want i64)`: EqI checks two integers.
- `EqU(label str, got u64, want u64)`: EqU checks two unsigned integers.
- `EqS(label str, got str, want str)`: EqS checks two strings.
- `EqB(label str, got bool, want bool)`: EqB checks two bools.
- `EqF(label str, got f64, want f64, eps f64)`: EqF checks two floats within eps.
- `True(label str, cond bool)`: True checks that cond holds.
- `False(label str, cond bool)`: False checks that cond does not hold.
- `NoFault(label str, err fault)`: NoFault checks that err is nil.
- `HasFault(label str, err fault)`: HasFault checks that err is not nil.
- `Failed() bool`: Failed reports whether any check failed so far.
- `Checks() i64`: Checks is the number of checks run so far.
- `Done()`: Done prints "ok N checks" or every failure, and exits with status 1 if any failed.
- `Bench(label str, n i64, f fn(i64))`: Bench runs f(i) for i in [0, n) and prints the time per call.
- `type T struct`: T is one running test: checks record failures in it, and the test continues.
- `type B struct`: B is one running benchmark: run the measured code b.N times.
- `(t mut T) Error(msg str)`: Error marks the test failed with msg (it keeps running).
- `(t mut T) Log(msg str)`: Log records msg; it is printed only if the test fails.
- `(t T) Failed() bool`: Failed reports whether the test has failed so far.
- `(t mut T) True(label str, cond bool)`: True fails the test with label unless cond holds.
- `(t mut T) False(label str, cond bool)`: False fails the test with label if cond holds.
- `(t mut T) NoFault(label str, err fault)`: NoFault fails the test if err is not nil.
- `(t mut T) HasFault(label str, err fault)`: HasFault fails the test if err is nil.
- `Equal[V constraints.Comparable](t mut T, label str, got V, want V)`: Equal fails the test unless got == want; both are printed on failure.
- `Run(name str, f fn(mut T))`: Run runs one test and prints its result like go test -v.
- `RunBench(name str, f fn(mut B))`: RunBench runs one benchmark with b.N doubling until it takes at least 1 s, then prints the time per operation.
- `Finish()`: Finish prints PASS or FAIL and exits with status 1 when a test failed.

## constraints

Package constraints contains the named generic constraints used by the standard library.

- `shape Any {}`: Any imposes no operations on a type parameter.
- `shape Comparable {}`: Comparable admits values that can be compared by value, including structs and enums whose fields are all comparable. The compiler checks this property at each instantiation.

## policy

Package policy is the with policies (design_semantics §7.1, notes/interface_policy.md): with p { body } calls p.Run(body) inside a boundary of its own, with the block as body. Slots are typed ambient values that Bind binds for a block and the tasks it spawns; Retry, Trace and Cached are the library policies.

- `shape Policy[T constraints.Any] { Run(body fn() !T) !T }`: Policy is what with p { body } needs of p: Run runs body (any number of times) and gives the block's value. Run may only call body, or pass it to a function that only calls it.
- `type Slot[T constraints.Any] struct`: Slot is a typed ambient value: with policy.Bind(s, v) { } binds it for the block and the tasks the block spawns.
- `NewSlot[T constraints.Any](name str) Slot[T]`: NewSlot makes a slot named name; declare it once, in a package-level let (one per core).
- `(s Slot[T]) Name() str`: Name is the slot's name.
- `(s Slot[T]) Get() !T`: Get is the value of the innermost Bind of s around the running code; it fails when s is not bound.
- `(s Slot[T]) Bound() bool`: Bound reports whether s is bound around the running code.
- `type BindPolicy[V constraints.Any, T constraints.Any] struct`: BindPolicy binds a slot for its block (Bind).
- `Bind[V constraints.Any, T constraints.Any](s Slot[V], v V) BindPolicy[V, T]`: Bind is a policy that binds s to v for its block and the tasks the block spawns: with policy.Bind(requestID, id) { }.
- `(b BindPolicy[V, T]) Run(body fn() !T) !T`: Run binds the slot on the with block's boundary, then runs body once.
- `type RetryPolicy[T constraints.Any] struct`: RetryPolicy runs its block again while it fails (Retry).
- `Retry[T constraints.Any](attempts i64) RetryPolicy[T]`: Retry is a policy that runs its block up to attempts times while it fails and gives the last fault. A cancellation ends it at once: a cancellation fault from the block is given as it is, and a boundary cancelled (or past its deadline) between attempts gives the cancellation's fault. The block's side effects run again on each attempt.
- `(r RetryPolicy[T]) Backoff(d i64) RetryPolicy[T]`: Backoff is r waiting d before the second attempt, and twice as long before each later one.
- `(r RetryPolicy[T]) Run(body fn() !T) !T`: Run runs body until it succeeds, attempts runs have failed, or the boundary is cancelled.
- `SetTracer(f fn(str, i64, fault))`: SetTracer sends this core's trace spans to f(name, duration in ns, fault or nil) instead of the log.
- `type TracePolicy[T constraints.Any] struct`: TracePolicy reports each run of its block (Trace).
- `Trace[T constraints.Any](name str) TracePolicy[T]`: Trace is a policy that reports its block's name, duration and fault to the core's tracer (a herald line by default).
- `(t TracePolicy[T]) Run(body fn() !T) !T`: Run runs body once and reports it.
- `type Cache[T constraints.Any] struct`: Cache is a per-core store for Cached: declare it in a package-level let. Values are kept (copied to the long-lived heap).
- `NewCache[T constraints.Any](max i64) Cache[T]`: NewCache makes a cache of at most max entries (at least one); a full cache drops its oldest entry.
- `(c Cache[T]) Len() i64`: Len is the number of entries, fresh or expired.
- `(c mut Cache[T]) Drop(key str)`: Drop removes key's entry.
- `type CachedPolicy[T constraints.Any] struct`: CachedPolicy answers its block from a cache (Cached).
- `Cached[T constraints.Any](c Cache[T], key str, ttl i64) CachedPolicy[T]`: Cached is a policy that gives the value cached under key while it is younger than ttl (ns), without running its block; otherwise it runs the block and caches a value it gives. Faults are not cached.
- `(p mut CachedPolicy[T]) Run(body fn() !T) !T`: Run gives the cached value, or runs body and caches its value.

## redis

Package redis is a Redis client. Commands are queries: in c.Do("SET user:{id} {body}") the values travel as separate arguments, so a value can never change a command.

Each core keeps one connection per Client. The requests a core serves at the same time share it: their commands are written together and the replies matched in order (pipelining), so a busy server makes few system calls per command. Inside a request task a call waits without blocking the core; outside one it blocks.

```tin body
let cache = redis.Open(redis.Options{Addr: "127.0.0.1:6379"})
try cache.Set("greeting", "hello")
let (v, found) = try cache.Get("greeting")
```

Blocking commands (BLPOP, SUBSCRIBE, ...) would hold up the commands queued behind them and are not supported.

- `type Reply enum`: Reply is one Redis reply.
- `type Options struct`: Options says where and how to connect.
- `ParseURL(url str) !Options`: ParseURL reads "redis://[[user]:password@]host[:port][/db]"; "rediss://" is the same over TLS 1.3 (TLS is set, so the server's certificate is verified for host).
- `type Client struct`: Client sends commands to one Redis server. Open it in a global's initializer (which runs on every core) or once in main, not per request.
- `Open(o Options) Client`: Open makes a client for the server in o. It connects on first use, on each core.
- `(c Client) Do(q query) !Reply`: Do sends one command and returns its reply; an error reply fails.
- `(c Client) Pipe(qs []query) ![]Reply`: Pipe sends commands together and returns their replies in order; error replies come back as Err. The commands go out back to back, so MULTI ... EXEC in one Pipe is atomic.
- `(c Client) Get(key str) !(str, bool)`: Get returns the value at key, and whether there is one.
- `(c Client) Set(key str, value str) !`: Set stores value at key.
- `(c Client) SetEx(key str, value str, ttl i64) !`: SetEx stores value at key for ttl nanoseconds (at least a millisecond).
- `(c Client) Del(key str) !i64`: Del removes key; it returns how many keys it removed (0 or 1).
- `(c Client) Incr(key str) !i64`: Incr adds one to the integer at key and returns the result.
- `(c Client) Expire(key str, ttl i64) !bool`: Expire makes key expire after ttl nanoseconds; false when there is no such key.
- `(c Client) Ping() !`: Ping checks that the server answers.

## mysql

Package mysql is a MySQL client (tested with MySQL 8.0). Statements are queries: in db.Query("SELECT name FROM users WHERE id = {id}") the text becomes "... id = ?" and id a bound parameter of a prepared statement, so a value can never change a statement.

Each core keeps a pool of connections per Client (Options.Pool, default max(2, 64/cores); Options.MaxTotal caps them for the process); a request task waits for a free one without blocking the core. Prepared statements are cached per connection. Authentication: caching_sha2_password (the MySQL 8 default, including the RSA key exchange when the server has no cached entry) and mysql_native_password. Options.TLS connects over TLS 1.3 (SSLRequest), verifying the server's certificate and name.

Sizing: a Client opened in a global's initializer is opened on every core, so a 32-core pod with Pool 16 may open 512 connections to one server, and a fleet of pods multiplies that. Pool, when not set, is max(2, 64/cores) per core: about 64 for the process, at least 2 on each core. Options.MaxTotal caps the connections of the whole process, over all cores (Clients with the same address, user, database and MaxTotal share one cap): a core at the cap waits, within the request's deadline and Options.Timeout, until a connection is released or a core that has one idle gives up its slot. Set MaxTotal to at least the number of cores that serve database requests; below that, cores share connections by closing and dialing again.

```tin body
let pw = quarry.Getenv("MYSQL_PASSWORD")
let id = 7
let db = mysql.Open(mysql.Options{Addr: "127.0.0.1:3306", User: "app", Password: pw, Database: "shop"})
let rows = try db.Query("SELECT id, name FROM users WHERE id = {id}")
for r in rows.Rows {
	say.Line(r[0].Int(), r[1].Text())
}
```

- `type Value enum`: Value is one column of a row.
- `type Rows struct`: Rows is a query's result.
- `type Result struct`: Result is what a statement without rows did.
- `type Options struct`: Options says where and how to connect.
- `type Client struct`: Client runs statements on one MySQL server. Open it in a global's initializer (which runs on every core) or once in main, not per request.
- `type Tx struct`: Tx is a transaction: its statements run on one connection until Commit or Rollback.
- `Open(o Options) Client`: Open makes a client for the server in o. It connects on first use, on each core.
- `(v Value) IsNull() bool`: IsNull reports whether v is NULL.
- `(v Value) Int() i64`: Int is v as an integer (a Text or Float converted, NULL and bad text 0).
- `(v Value) Float() f64`: Float is v as a float.
- `(v Value) Text() str`: Text is v as text ("" for NULL).
- `(r Rows) Col(name str) i64`: Col is the index of the named column, or -1.
- `(c Client) Query(q query) !Rows`: Query runs a statement and returns its rows.
- `(c Client) Exec(q query) !Result`: Exec runs a statement and returns what it changed.
- `(c Client) Ping() !`: Ping checks that the server answers.
- `(c Client) Begin() !Tx`: Begin starts a transaction; finish it with Commit or Rollback, or its connection stays out of the pool.
- `(t mut Tx) Query(q query) !Rows`: Query runs a statement in the transaction and returns its rows.
- `(t mut Tx) Exec(q query) !Result`: Exec runs a statement in the transaction.
- `(t mut Tx) Commit() !`: Commit makes the transaction's changes permanent.
- `(t mut Tx) Rollback() !`: Rollback undoes the transaction's changes.

## postgres

Package postgres is a PostgreSQL protocol 3.0 client over TCP. Query interpolation binds binary parameters as $1, $2, ...; a plain str cannot be used as SQL. Connections are pooled per core (Options.Pool, default max(2, 64/cores); Options.MaxTotal caps them for the process) and waiting request tasks park without blocking it. Authentication supports SCRAM-SHA-256, MD5 and cleartext. Options.SSLMode turns on TLS 1.3 (SSLRequest): "require" encrypts, "verify-full" (the default when Options.TLS is set) also checks the server's certificate and name.

Sizing: a Client opened in a global's initializer is opened on every core, so a 32-core pod with Pool 16 may open 512 connections to one server, and a fleet of pods multiplies that. Pool, when not set, is max(2, 64/cores) per core: about 64 for the process, at least 2 on each core. Options.MaxTotal caps the connections of the whole process, over all cores (Clients with the same address, user, database and MaxTotal share one cap): a core at the cap waits, within the request's deadline and Options.Timeout, until a connection is released or a core that has one idle gives up its slot. Set MaxTotal to at least the number of cores that serve database requests; below that, cores share connections by closing and dialing again.

```tin body
let pw = quarry.Getenv("POSTGRES_PASSWORD")
let name = "ana"
let db = postgres.Open(postgres.Options{Addr: "127.0.0.1:5432", User: "app", Password: pw, Database: "shop"})
let rows = try db.Query("INSERT INTO users(name) VALUES ({name}) RETURNING id")
let id = rows.Rows[0][0].Int()
```

- `type Value enum`: Value is one column of a row.
- `type Rows struct`: Rows is a query's result.
- `type Result struct`: Result is what a statement without rows did.
- `type Options struct`: Options says where and how to connect.
- `type Client struct`: Client runs statements on one PostgreSQL server. Open it in a global's initializer (which runs on every core) or once in main, not per request.
- `type Tx struct`: Tx is a transaction: its statements run on one connection until Commit or Rollback.
- `Open(o Options) Client`: Open makes a client for the server in o. It connects on first use, on each core.
- `(v Value) IsNull() bool`: IsNull reports whether v is NULL.
- `(v Value) Int() i64`: Int is v as an integer (a Text or Float converted, NULL and bad text 0).
- `(v Value) Float() f64`: Float is v as a float.
- `(v Value) Text() str`: Text is v as text ("" for NULL).
- `(r Rows) Col(name str) i64`: Col is the index of the named column, or -1.
- `(c Client) Query(q query) !Rows`: Query returns the first rowset. With no parameters, multiple statements are allowed and all replies are consumed before returning. Integers and booleans use Value.Int; float4/8 use Value.Float; other OIDs (including numeric and bytea) use Value.Text.
- `(c Client) Exec(q query) !Result`: Exec returns the affected count of the last command. Use Query with RETURNING to obtain generated IDs (PostgreSQL has no connection-wide last insert ID).
- `(c Client) Ping() !`: Ping checks that the server answers.
- `(c Client) Begin() !Tx`: Begin pins a connection until Commit or Rollback. SQL errors abort the transaction until Rollback. Copies share its state: finishing one finishes them all. In request tasks an unfinished transaction is dropped when its owning task/scope ends. Outside tasks always finish explicitly. Tx and its rows belong to the caller's pool.
- `(t mut Tx) Query(q query) !Rows`: Query runs a statement in the transaction and returns its first rowset.
- `(t mut Tx) Exec(q query) !Result`: Exec runs a statement in the transaction and returns its affected count.
- `(t mut Tx) Commit() !`: Commit makes the transaction's changes permanent. An aborted transaction must be rolled back explicitly; PostgreSQL's implicit COMMIT-to-ROLLBACK is not success.
- `(t mut Tx) Rollback() !`: Rollback undoes the transaction's changes and releases its connection.

## kafka

Package kafka is an Apache Kafka client: a producer (idempotent by default, with batching and gzip, snappy, lz4 and zstd compression), fetching from partitions (read_committed too), consumer groups with rebalancing, transactions, and administration of topics, partitions, records, groups and configs. It speaks Kafka's binary protocol directly (request versions brokers 2.4 to 4.x accept; run against 3.9 and 4.2), over plain TCP or TLS 1.3, with SASL PLAIN, SCRAM-SHA-256 or SCRAM-SHA-512.

Each core keeps one connection per broker for each Client. The requests a core serves at the same time share a connection, and sends of the same turn to one partition share a record batch, so a busy service makes few requests. Inside a request task a call waits without blocking the core; outside one it blocks.

```tin body
let bus = kafka.Open(kafka.Options{Brokers: []str{"127.0.0.1:9092"}})
let ack = try bus.Send("orders", kafka.Message{Key: "7", Value: "paid"})
let records = try bus.Fetch("orders", ack.Partition, ack.Offset, 1s)
```

A key picks the partition the way the Java client does (murmur2), so a key lands on the same partition from either. Consumer groups: Group and notes/design_kafka.md (section 3) for where a consumer loop runs. Transactions: Transactional.

- `type TopicSpec struct`: TopicSpec describes a topic to create.
- `type Config struct`: Config is one configuration entry.
- `type Resource enum`: Resource is what a config belongs to.
- `type GroupListing struct`: GroupListing is one group a cluster knows.
- `type GroupMember struct`: GroupMember is one member of a described group.
- `type GroupDescription struct`: GroupDescription is the state of a group.
- `(c Client) CreateTopic(name str, partitions i64, replicas i64) !`: CreateTopic makes a topic. It fails with ErrTopicExists when there already is one.
- `(c Client) CreateTopics(specs []TopicSpec) !`: CreateTopics makes topics; the first failure fails the call (ErrTopicExists for one that exists).
- `(c Client) DeleteTopics(names []str) !`: DeleteTopics removes topics.
- `(c Client) ListTopics() ![]str`: ListTopics is the names of the cluster's topics (internal ones too).
- `(c Client) CreatePartitions(topic str, total i64) !`: CreatePartitions grows topic to total partitions.
- `(c Client) DeleteRecords(topic str, partition i64, before i64) !i64`: DeleteRecords deletes the records of the partition before offset; it returns the partition's new first offset.
- `(c Client) ListGroups() ![]GroupListing`: ListGroups lists the groups of the whole cluster (each broker knows those it coordinates).
- `(c Client) DescribeGroup(group str) !GroupDescription`: DescribeGroup is the state, protocol and members of group.
- `(c Client) DeleteGroups(groups []str) !`: DeleteGroups removes empty groups and their committed offsets.
- `(c Client) DescribeConfigs(kind Resource, name str) ![]Config`: DescribeConfigs is the configuration of a topic or a broker (a broker by its node id).
- `(c Client) SetConfig(kind Resource, name str, key str, value str) !`: SetConfig sets one config of a topic or a broker (IncrementalAlterConfigs: the others stay).
- `(c Client) ResetConfig(kind Resource, name str, key str) !`: ResetConfig removes one config of a topic or a broker, back to its default.
- `(c Client) Close()`: Close closes this core's connections of the client; the next request connects again. Requests waiting on them fail.
- `type Want struct`: Want names a partition and the offset to read it from.
- `type Part struct`: Part is what a fetch learned about one partition.
- `type Fetched struct`: Fetched is the records of a FetchAll, in partition order, and what it learned of each partition.
- `(c Client) Fetch(topic str, partition i64, offset i64, maxWait i64) ![]Record`: Fetch reads records of topic's partition from offset on. It returns as soon as there are records, or empty after maxWait nanoseconds with none. At most Options.FetchMax bytes of whole record batches come back; a record before offset is skipped. An offset outside the partition fails with ErrOffsetOutOfRange.
- `(c Client) FetchAll(wants []Want, maxWait i64) !Fetched`: FetchAll reads several partitions at once: one request per leader broker, all sent before any is waited for when called inside a task. A partition whose offset is out of range is reported in Parts, not as a fault.
- `(c Client) Offsets(topic str, partition i64) !(i64, i64)`: Offsets returns the first offset still in partition and the offset the next record will get.
- `(c Client) OffsetAt(topic str, partition i64, ts i64) !i64`: OffsetAt is the first offset whose record's timestamp is at or after ts (ms since the epoch), or -1 when every record is older.
- `type Assignor enum`: Assignor is how a group's leader spreads partitions over its members.
- `type Start enum`: Start is where a member starts reading a partition the group has no offset for.
- `type GroupOptions struct`: GroupOptions describe a member.
- `type Group struct`: Group is this core's member of a consumer group.
- `type TopicPartition struct`: TopicPartition names a partition and an offset (a position or a committed offset).
- `(c Client) Group(o GroupOptions) !Group`: Group makes this core's member of a consumer group. It joins on the first Poll.
- `(g Group) MemberID() str`: MemberID is the id the coordinator gave this member ("" before it joined).
- `(g Group) Generation() i64`: Generation is the group generation this member is in (-1 before it joined).
- `(g Group) Assigned() []TopicPartition`: Assigned is the member's partitions with the offset each will be read from next (-1 until known).
- `(g Group) Seek(topic str, partition i64, offset i64) !`: Seek makes the next Poll read the member's partition from offset.
- `(g Group) Heartbeat() !`: Heartbeat tells the coordinator the member is alive (Poll does it when due). A rebalance makes the next Poll rejoin.
- `(g Group) Poll(maxWait i64) ![]Record`: Poll returns the next records of the member's partitions, waiting up to maxWait (less when a heartbeat falls due). It joins the group first, rejoins after a rebalance, heartbeats, and unless ManualCommit is set commits what the previous Poll returned.
- `(g Group) Commit() !`: Commit stores the member's positions (the offsets after the records Poll returned) as the group's committed offsets. A rebalance in the meantime fails it with ErrRebalance.
- `(g Group) CommitOffsets(parts []TopicPartition) !`: CommitOffsets stores the given offsets (each the next offset to read) for the group.
- `(g Group) Close() !`: Close commits (unless ManualCommit) and leaves the group, so its partitions move to the other members at once. A static member (InstanceID) does not leave: its session keeps its partitions for a restart.
- `(c Client) Commit(group str, topic str, partition i64, offset i64) !`: Commit stores offset as group's position in the partition, without being a member (the "simple consumer" commit: generation -1). The offset is the next one to read.
- `(c Client) Committed(group str, topic str, partition i64) !i64`: Committed is the offset group last committed for the partition, or -1 when it has none.
- `type Mechanism enum`: Mechanism is the SASL mechanism used when Options.Username is set.
- `type Acks enum`: Acks says which replicas must have a record before Send returns.
- `type Options struct`: Options says where and how to connect, and how to produce and fetch.
- `type Client struct`: Client talks to one Kafka cluster. Open it in a global's initializer (which runs on every core) or once in main, not per request.
- `type Ack struct`: Ack says where Send put a record. Offset is -1 with Acks.NoAck, and when an idempotent retry found the batch already written.
- `Open(o Options) Client`: Open makes a client for the cluster in o. It connects on first use, on each core.
- `(c Client) Partitions(topic str) !i64`: Partitions is how many partitions topic has (asking the cluster). A topic created a moment ago may not be in every broker's metadata yet, so an unknown topic is asked about again for a little while (about two seconds) before the call fails with ErrUnknownTopic.
- `(c Client) Ping() !`: Ping checks that a broker answers.
- `(c Client) Send(topic str, m Message) !Ack`: Send appends one record to topic and returns where it went. A record with a key goes to the partition the key hashes to; one without goes to one partition per call, in turn.
- `(c Client) SendTo(topic str, partition i64, m Message) !Ack`: SendTo appends one record to a chosen partition of topic.
- `(c Client) SendBatchTo(topic str, partition i64, ms []Message) ![]Ack`: SendBatchTo appends records to a chosen partition of topic, in one batch with what other tasks of this core send there meanwhile.
- `(c Client) SendBatch(topic str, ms []Message) ![]Ack`: SendBatch appends records to topic and returns where each went, in order. Records of one partition go in one batch (with what other tasks of this core send meanwhile). A failed batch fails the call; records of other partitions may already be written.
- `type Message struct`: Message is one record to send.
- `type Header struct`: Header is a record header.
- `type Record struct`: Record is a record read from a partition.
- `type Compression enum`: Compression codecs, as the record batch attributes number them.
- `Murmur2(data str) i64`: Murmur2 is the hash Kafka's default partitioner uses for keys (Java's Utils.murmur2), so a key lands on the same partition here as from the Java client.
- `PartitionFor(key str, n i64) i64`: PartitionFor is the partition Kafka's default partitioner picks for key among n partitions.
- `EncodeBatch(ms []Message, now i64, c Compression) str`: EncodeBatch is ms as one record batch (format 2) compressed with c, the bytes Kafka stores and sends, with offsets counted from 0. A message whose Timestamp is 0 gets now (ms since the epoch).
- `DecodeBatches(data str) ![]Record`: DecodeBatches reads the record batches in data, as a Fetch response carries them, with any codec. A batch the data ends in the middle of is dropped; a damaged one, a changed byte (CRC-32C) or an old message format fails. Control batches (transaction markers) are skipped.
- `type Txn struct`: Txn is this core's transactional producer for one transactional id.
- `(c Client) Transactional(txid str, timeout i64) !Txn`: Transactional makes this core's producer for transactional id txid (timeout: how long the broker lets a transaction stay open, default 60 s). It fences any older producer with the same id, and aborts what that one left open.
- `(t Txn) Begin() !`: Begin starts a transaction.
- `(t Txn) Send(topic str, m Message) !Ack`: Send writes one record in the open transaction.
- `(t Txn) SendBatch(topic str, ms []Message) ![]Ack`: SendBatch writes records in the open transaction, one batch per partition; readers with ReadCommitted see them only once the transaction commits.
- `(t Txn) SendOffsets(group str, offsets []TopicPartition) !`: SendOffsets commits a consumer group's offsets as part of the open transaction (consume-transform-produce): they become the group's committed offsets only if the transaction commits.
- `(t Txn) Commit() !`: Commit commits the open transaction: its records become visible to ReadCommitted readers and its offsets the group's.
- `(t Txn) Abort() !`: Abort discards the open transaction.

## websocket

Package websocket is the WebSocket protocol (RFC 6455): Accept upgrades an anvil request, Dial connects to a server (ws://, or wss:// over TLS 1.3). Messages are text or binary; pings are answered and fragments joined inside Read. Inside a request task a Read waits without blocking the core, so one core holds many idle connections.

```tin
fn handle(q anvil.Req, w mut anvil.Out) {
	let ws = websocket.Accept(q, mut w) catch _ { return }
	ws.Each(echo) catch _ {}
}

fn echo(ws websocket.Conn, m websocket.Message) ! {
	try ws.WriteText("echo: {m.Data}")
}
```

- `type Message struct`: Message is one complete message.
- `type Conn struct`: Conn is a WebSocket connection.
- `Accept(q anvil.Req, w mut anvil.Out) !Conn`: Accept completes the opening handshake for request q and takes over its connection. A request that is not a WebSocket handshake gets a 400 (426 for another version) in w and fails. The connection and its buffers close when the handler returns.
- `Dial(url str) !Conn`: Dial connects to a ws:// or wss:// URL ("ws://host:port/path"); wss:// verifies the server's certificate against the system's roots. Close it when finished; inside a request task, it is also closed automatically when its scope ends.
- `DialTLS(url str, cfg tls.Config) !Conn`: DialTLS is Dial with the TLS configuration of a wss:// URL (RootCAs, Timeout for the handshake, InsecureSkipVerify for tests); the server name is the URL's host.
- `(c Conn) SetTimeout(ns i64)`: SetTimeout limits every later read and write to ns nanoseconds (0: no limit).
- `(c Conn) SetMaxMessage(n i64)`: SetMaxMessage sets the largest message Read accepts (default 16 MiB); a bigger one closes the connection with 1009.
- `(c Conn) WriteText(s str) !`: WriteText sends s as a text message.
- `(c Conn) WriteBinary(b []u8) !`: WriteBinary sends b as a binary message.
- `(c Conn) Ping() !`: Ping sends a ping; the peer's pong is consumed by Read.
- `(c Conn) CloseWith(code i64, reason str) !`: CloseWith sends a close frame with code and reason; the connection then only drains.
- `(c Conn) Close()`: Close sends a normal close (1000) and, for a client, closes the connection.
- `IsClosed(err fault) bool`: IsClosed reports whether err is the normal end of a connection: the peer closed it.
- `(c Conn) Read() !Message`: Read returns the next message; it answers pings and joins fragments on the way. When the peer closes, it answers the close and fails with "websocket: closed (code)". The returned message lives in the caller's pool. For a long-lived stream, use Each to reset message allocations after every callback without invalidating the Conn.
- `(c Conn) Each(h fn(Conn, Message) !) !`: Each reads messages and calls h until a read or callback fails. Every callback has a reusable message pool: use keep() to retain its data after the callback returns. The Conn and all objects allocated before Each remain valid. Callbacks may wait. A closed peer returns the same IsClosed fault as Read; callback faults propagate.
