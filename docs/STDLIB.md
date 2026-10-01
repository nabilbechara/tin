# Tin standard library

Generated from the comments in `lib/*.tin` by `tools/gendoc.py`.

| package | role (Go equivalent) |
|---|---|
| [say](#say) | formatting and printing (fmt) |
| [argo](#argo) | JSON (encoding/json) |
| [anvil](#anvil) | HTTP/1.1 server (net/http) |
| [hearth](#hearth) | cores and threads (runtime) |
| [relay](#relay) | messages between cores (channels) |
| [wire](#wire) | TCP and HTTP client (net) |
| [twine](#twine) | strings (strings) |
| [glyph](#glyph) | UTF-8 (unicode/utf8) |
| [mint](#mint) | number and string conversion (strconv) |
| [gauge](#gauge) | math (math, math/bits) |
| [ore](#ore) | byte slices (bytes) |
| [flume](#flume) | buffered I/O (bufio) |
| [quarry](#quarry) | files, environment, process (os) |
| [trail](#trail) | paths (path/filepath) |
| [lever](#lever) | command-line flags (flag) |
| [tide](#tide) | time (time) |
| [dice](#dice) | random numbers (math/rand) |
| [sift](#sift) | sorting and searching (sort, slices) |
| [cairn](#cairn) | containers (container/heap, sets, LRU) |
| [stamp](#stamp) | hashes and checksums (hash/*) |
| [seal](#seal) | crypto and encodings (crypto/sha256, hmac, encoding/hex, base64) |
| [herald](#herald) | logging (log/slog) |
| [crucible](#crucible) | testing helpers (testing) |

## say

Built into the compiler (formatting by static type, no reflection): `say.Line(a, b...)`, `say.Text(...)`, `say.Out(format, ...)`, `say.Fmt(format, ...) str`, `say.Str(x) str`, `say.Fault(format, ...) fault`, `say.To(fd, ...)`, `say.LineTo(fd, ...)`. See docs/LANGUAGE.md.

## argo

Package argo writes JSON. argo.Put(b, v) appends v to the []u8 buffer b; the compiler generates a dedicated encoder for v's type (fields in declaration order, no reflection, no allocation). The w* writers below are what those encoders call.

- `Put(b mut []u8, v i64)`: Put appends v as JSON to b. The compiler replaces every call with a typed encoder.
- `Str(b mut []u8, s str)`: Str appends s as a JSON string.
- `Raw(b mut []u8, s str)`: Raw appends already-encoded JSON text.
- `type Parser struct`

## anvil

Package anvil is an HTTP/1.1 server: one event loop per core (kqueue), share-nothing.

Core 0 accepts connections and deals them round-robin to every core through a pipe; from then on a connection belongs to one core for its whole life. Each core reads into one scratch buffer, parses requests in place, runs the handler, writes every response of the batch with one write, and wipes its request pool. Idle connections hold no buffers, only a 96-byte record.

```go
func handle(q anvil.Req, w mut anvil.Out) {
	w.Type("application/json")
	argo.Put(w.Body, Msg{message: "hi"})
}
func main() {
	err := anvil.Serve(":8080", handle)
	say.Line("server:", err)
}
```

- `type Req struct`: Req is the request being served. Its strings live in the request pool: keep() them to store them anywhere long-lived.
- `type Out struct`: Out is the response being built. Body is the response body; the status defaults to 200 and the content type to text/plain.
- `Serve(addr str, h func(Req, mut Out)) !`: Serve listens on addr (":8080", "127.0.0.1:8080") and serves h on every core. It returns only if the server cannot start. TIN_CORES overrides the number of cores.
- `ServeN(addr str, n i64, h func(Req, mut Out)) !`: ServeN is Serve on exactly n cores.
- `Deadline(ms i64)`: Deadline makes every request's waits (tide.Wait, client calls) fail with "deadline exceeded" once ms have passed since the request started (0: no deadline; call before Serve). TIN_DEADLINE_MS sets it too; the default is 30000.
- `(q Req) Header(name str) str`: Header returns the value of the request header name (any case), or "".
- `(q Req) Body() str`: Body returns the request body.
- `(q Req) Param(name str) str`: Param returns query parameter name, %-decoded, or "".
- `(w mut Out) Status(code i64)`: Status sets the response status code.
- `(w mut Out) Type(t str)`: Type sets the Content-Type header.
- `(w mut Out) Head(k str, v str)`: Head adds a response header.
- `(w mut Out) Text(s str)`: Text appends s to the body.
- `(w mut Out) Json()`: Json sets the JSON content type; the body is then written with argo.Put(w.Body, v).
- `OnRelay(h func(i64, str))`: OnRelay makes every core run h(from, msg) for each relay message it receives (call before Serve). Handlers run between requests, with their own request pool.
- `OnTick(ms i64, h func(i64))`: OnTick makes every core run h(core) every ms milliseconds (call before Serve).

## hearth

Package hearth runs a program on every core: one thread per core, each with its own globals, request pool and ingot heap. Cores share nothing; relay carries messages.

- `Cores() i64`: Cores is the number of CPUs this program may use: the CPUs online, capped on Linux by the affinity mask (cpuset) and the cgroup CPU quota (ceil of cpu.max quota/period); never 0.
- `MemLimit() i64`: MemLimit is the memory limit in bytes the container (cgroup) imposes: 0 when there is none.
- `ID() i64`: ID is the current core's number: 0 for the main core.
- `Run(n i64, entry func(i64))`: Run starts entry(i) on cores 1..n-1, runs entry(0) here, then waits for every core. Before starting it sizes the request pools to the memory limit and decides whether cores pin themselves to CPUs (only when they map one-to-one onto the allowed CPUs, or TIN_PIN=1).
- `PoolChunk() i64`: PoolChunk is the request pool chunk size in bytes each core uses (after pool_tune).
- `PoolCapacity() i64`: PoolCapacity is the usable size in bytes of this core's current base pool chunk (0 before its first request allocation).
- `Reset()`: Reset ends the current request: the core's pool is emptied for the next one.

## relay

Package relay carries messages between cores, which share no memory. A message is a str copied into the receiving core's inbox (a lock-free multi-producer queue); the receiver gets its own copy in its request pool. Encode structs with argo.Put/argo.Get.

```go
relay.Send(2, "hello")              // from any core
from, msg := relay.Recv()           // on core 2: blocks until a message arrives
```

- `Send(to i64, msg str)`: Send copies msg into core to's inbox; it never blocks.
- `Broadcast(msg str)`: Broadcast sends msg to every other running core.
- `Cores() i64`: Cores is the number of cores the program started.
- `TryRecv() (i64, str, bool)`: TryRecv returns the next message for this core, if there is one.
- `Recv() (i64, str)`: Recv blocks until a message for this core arrives and returns its sender and text.
- `WakeFD() i64`: WakeFD is this core's wake-up descriptor, for event loops: after it turns readable, call Drain. Arm must be called before the loop blocks.
- `Arm()`: Arm asks senders to wake this core through WakeFD (call just before blocking).
- `Drain(h func(i64, str))`: Drain runs h on every waiting message (event loops call it after WakeFD fires).
- `Received() i64`: Received is how many messages this core has taken from its inbox.
- `Me() i64`: Me is this core's number.

## wire

Package wire is TCP networking and a small HTTP/1.1 client. Calls block the calling core (servers should use anvil); every connection can carry a read/write timeout.

```go
c := try wire.Dial("127.0.0.1:6379")
try c.Write("PING\r\n")
r := try wire.Get("http://127.0.0.1:8080/json")
```

- `type Conn struct`: Conn is a TCP connection.
- `type Listener struct`: Listener accepts TCP connections.
- `type Resp struct`: Resp is an HTTP response.
- `IsEOF(err fault) bool`: EOF is the fault Read returns at the end of the stream.
- `Dial(addr str) !Conn`: Dial connects to "host:port".
- `DialTimeout(addr str, timeout i64) !Conn`: DialTimeout connects to "host:port", giving up after timeout nanoseconds (0: no limit).
- `(c Conn) SetTimeout(ns i64)`: SetTimeout limits every later read and write to ns nanoseconds (0: no limit).
- `(c Conn) SetNoDelay(on bool)`: SetNoDelay turns Nagle's algorithm off (true) or on.
- `(c Conn) Write(s str) !`: Write sends all of s.
- `(c Conn) WriteBytes(b []u8) !`: WriteBytes sends all of b.
- `(c Conn) Read(buf mut []u8, max i64) !i64`: Read appends up to max bytes to buf and returns how many; at the end it returns 0 and EOF.
- `(c Conn) ReadFull(n i64) !str`: ReadFull reads exactly n bytes.
- `(c mut Conn) Close()`: Close closes the connection.
- `Listen(addr str) !Listener`: Listen opens a TCP listener on "host:port" (":0" picks a free port: see Port).
- `(l Listener) Port() i64`: Port is the port the listener is bound to.
- `(l Listener) Accept() !Conn`: Accept waits for the next connection.
- `(l mut Listener) Close()`: Close stops listening.
- `Get(url str) !Resp`: Get fetches url.
- `Post(url str, ctype str, body str) !Resp`: Post sends body with content type ctype to url.
- `Do(method str, url str, headers []str, body str) !Resp`: Do sends one request: headers is a list of name, value pairs.
- `(r Resp) Header(name str) str`: Header returns the response header name (any case), or "".

## twine

Package twine manipulates UTF-8 strings (like Go's strings); case helpers are ASCII/Latin-1 only.

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
- `Fields(s str) []str`: Fields splits s around runs of ASCII white space and returns the non-empty pieces.
- `Join(elems []str, sep str) str`: Join concatenates elems with sep between them.
- `Repeat(s str, count i64) str`: Repeat returns s concatenated count times (empty when count <= 0).
- `Count(s str, sub str) i64`: Count returns the number of non-overlapping sub in s (RuneCount+1 when sub is empty).
- `Replace(s str, old str, repl str, n i64) str`: Replace returns s with the first n non-overlapping old replaced by repl (all when n < 0; empty old matches at every rune boundary).
- `ReplaceAll(s str, old str, repl str) str`: ReplaceAll returns s with every non-overlapping old replaced by repl.
- `ToLower(s str) str`: ToLower returns s with ASCII upper-case letters lowered (other bytes unchanged).
- `ToUpper(s str) str`: ToUpper returns s with ASCII lower-case letters raised (other bytes unchanged).
- `TrimLeft(s str, cutset str) str`: TrimLeft returns s without its leading runes that are in cutset.
- `TrimRight(s str, cutset str) str`: TrimRight returns s without its trailing runes that are in cutset.
- `Trim(s str, cutset str) str`: Trim returns s without leading and trailing runes that are in cutset.
- `TrimSpace(s str) str`: TrimSpace returns s without leading and trailing white space (ASCII, U+0085, U+00A0).
- `TrimPrefix(s str, prefix str) str`: TrimPrefix returns s without the leading prefix, or s unchanged.
- `TrimSuffix(s str, suffix str) str`: TrimSuffix returns s without the trailing suffix, or s unchanged.
- `EqualFold(s str, t str) bool`: EqualFold reports whether s and t are equal under ASCII/Latin-1 simple case folding.
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
- `(b mut Builder) Reset()`: Reset empties the Builder but keeps its capacity.

## glyph

Package glyph is UTF-8 and simple character classification (like Go's unicode/utf8).

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
- `IsLetter(r i32) bool`: IsLetter reports whether r is an ASCII or Latin-1 letter.
- `IsDigit(r i32) bool`: IsDigit reports whether r is an ASCII decimal digit.
- `IsSpace(r i32) bool`: IsSpace reports whether r is ASCII or Latin-1 white space.
- `IsUpper(r i32) bool`: IsUpper reports whether r is an ASCII or Latin-1 upper-case letter.
- `IsLower(r i32) bool`: IsLower reports whether r is an ASCII or Latin-1 lower-case letter.
- `ToUpper(r i32) i32`: ToUpper maps ASCII and simple Latin-1 lower-case letters to upper case (ß, ÿ and µ are unchanged).
- `ToLower(r i32) i32`: ToLower maps ASCII and Latin-1 upper-case letters to lower case.

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
- `ParseFloat(s str) !f64`: ParseFloat parses a Go float literal (decimal or 0x hex with p exponent, underscores, inf/infinity/nan) via strtod.
- `F64frombits(b u64) f64`: F64frombits returns the f64 with bit pattern b.
- `FormatFloat(f f64, fmt u8, prec i64) str`: FormatFloat formats f as 'f' (ddd.ddd), 'e' (d.ddde±dd) or 'g' (shortest of the two); prec -1 is the shortest text that reads back exactly.
- `Quote(s str) str`: Quote returns s as a Go double-quoted literal with \n-style, \x, \u and \U escapes.
- `AppendQuote(b mut []u8, s str) []u8`: AppendQuote appends Quote(s) to b and returns b.
- `QuoteRune(r i32) str`: QuoteRune returns r as a Go single-quoted rune literal (invalid runes become U+FFFD).
- `Unquote(s str) !str`: Unquote interprets s as a Go string literal ("..." with escapes, '...' one rune, `...` raw) and returns its value.

## gauge

Package gauge is floating-point and integer math (like Go's math and math/bits); transcendentals come from libm.

- `const Pi = 3.141592653589793`: Pi is the ratio of a circle's circumference to its diameter.
- `const E = 2.718281828459045`: E is the base of natural logarithms.
- `const Sqrt2 = 1.4142135623730951`: Sqrt2 is the square root of 2.
- `const Ln2 = 0.6931471805599453`: Ln2 is the natural logarithm of 2.
- `const MaxI64 = 9223372036854775807`: MaxI64 is the largest i64.
- `const MinI64 = -9223372036854775807 - 1`: MinI64 is the smallest i64.
- `const MaxU64 u64 = 18446744073709551615`: MaxU64 is the largest u64 (typed, because an untyped constant this large folds to -1 in the frozen compiler).
- `const MaxF64 = 1.7976931348623157e308`: MaxF64 is the largest finite f64.
- `const SmallestNonzeroF64 = 4.9406564584124654e-324`: SmallestNonzeroF64 is the smallest positive denormal f64.
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
- `MinI(a i64, b i64) i64`: MinI returns the smaller of a and b.
- `MaxI(a i64, b i64) i64`: MaxI returns the larger of a and b.
- `AbsI(x i64) i64`: AbsI returns |x| (MinI64 wraps to itself).
- `Clamp(x f64, lo f64, hi f64) f64`: Clamp returns x limited to [lo, hi] (NaN passes through).
- `ClampI(x i64, lo i64, hi i64) i64`: ClampI returns x limited to [lo, hi].
- `Sqrt(x f64) f64`: Sqrt returns the square root of x.
- `Cbrt(x f64) f64`: Cbrt returns the cube root of x.
- `Pow(x f64, y f64) f64`: Pow returns x**y.
- `Exp(x f64) f64`: Exp returns e**x.
- `Exp2(x f64) f64`: Exp2 returns 2**x.
- `Log(x f64) f64`: Log returns the natural logarithm of x.
- `Log2(x f64) f64`: Log2 returns the base-2 logarithm of x.
- `Log10(x f64) f64`: Log10 returns the base-10 logarithm of x.
- `Log1p(x f64) f64`: Log1p returns log(1 + x), accurate for small x.
- `Sin(x f64) f64`: Sin returns the sine of x (radians).
- `Cos(x f64) f64`: Cos returns the cosine of x (radians).
- `Tan(x f64) f64`: Tan returns the tangent of x (radians).
- `Asin(x f64) f64`: Asin returns the arcsine of x.
- `Acos(x f64) f64`: Acos returns the arccosine of x.
- `Atan(x f64) f64`: Atan returns the arctangent of x.
- `Atan2(y f64, x f64) f64`: Atan2 returns the arctangent of y/x using the signs of both to pick the quadrant.
- `Sinh(x f64) f64`: Sinh returns the hyperbolic sine of x.
- `Cosh(x f64) f64`: Cosh returns the hyperbolic cosine of x.
- `Tanh(x f64) f64`: Tanh returns the hyperbolic tangent of x.
- `Floor(x f64) f64`: Floor returns the largest integer value <= x.
- `Ceil(x f64) f64`: Ceil returns the smallest integer value >= x.
- `Trunc(x f64) f64`: Trunc returns the integer part of x (rounding toward zero).
- `Round(x f64) f64`: Round returns x rounded to the nearest integer, halves away from zero.
- `RoundToEven(x f64) f64`: RoundToEven returns x rounded to the nearest integer, halves to the even neighbour.
- `Mod(x f64, y f64) f64`: Mod returns the remainder of x/y with the sign of x (NaN for y == 0 or infinite x).
- `Hypot(x f64, y f64) f64`: Hypot returns sqrt(x*x + y*y) without undue overflow.
- `Pow10(n i64) f64`: Pow10 returns 10**n: +Inf above 308, 0 below -323, exactly as Go's math.Pow10.
- `Gcd(a i64, b i64) i64`: Gcd returns the greatest common divisor of |a| and |b| (0 when both are 0).
- `Lcm(a i64, b i64) i64`: Lcm returns the least common multiple of |a| and |b| (0 when either is 0; wraps on overflow).
- `PopCount(x u64) i64`: PopCount returns the number of one bits in x.
- `LeadingZeros(x u64) i64`: LeadingZeros returns the number of leading zero bits in x (64 for 0).
- `TrailingZeros(x u64) i64`: TrailingZeros returns the number of trailing zero bits in x (64 for 0).

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
- `Repeat(b []u8, n i64) []u8`: Repeat returns n copies of b.

## flume

Package flume reads and writes file descriptors through 64 KiB buffers: lines, whole files and buffered output with one write per flush.

- `type Reader struct`: Reader buffers reads from a file descriptor.
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
- `ReadStdin() !str`: ReadStdin reads standard input to its end.
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

Package sift sorts and searches slices (like Go's sort and slices); without generics every element type has its own function.

- `Ints(xs mut []i64)`: Ints sorts xs in increasing order with pattern-defeating quicksort (not stable, O(n log n) worst case).
- `IntsDesc(xs mut []i64)`: IntsDesc sorts xs in decreasing order.
- `U64s(xs mut []u64)`: U64s sorts xs in increasing unsigned order.
- `F64s(xs mut []f64)`: F64s sorts xs in increasing order with NaNs first, like Go's slices.Sort (-0 sorts before 0).
- `Strs(xs mut []str)`: Strs sorts xs in increasing bytewise order.
- `SortBy(xs mut []i64, less func(i64, i64) bool)`: SortBy sorts xs so that less(xs[i+1], xs[i]) is never true (less must be a strict weak order).
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
- `Keys[K any, V any](m map[K]V) []K`: Keys returns m's keys in insertion order.
- `Values[K any, V any](m map[K]V) []V`: Values returns m's values in insertion order.
- `SortedKeys[K i64 | i32 | i16 | i8 | u64 | u32 | u16 | u8 | f64 | str, V any](m map[K]V) []K`: SortedKeys returns m's keys sorted ascending.
- `Map[T any, U any](xs []T, f func(T) U) []U`: Map returns f applied to each element of xs.
- `Filter[T any](xs []T, keep func(T) bool) []T`: Filter returns the elements of xs for which keep returns true, in order.
- `Reduce[T any, A any](xs []T, start A, f func(A, T) A) A`: Reduce folds xs into one value: f(f(f(start, x0), x1), ...).

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

## seal

Package seal has cryptographic hashes (SHA-256, SHA-1), HMAC-SHA256, constant-time comparison, secure random bytes, and the hex and base64 encodings.

- `Sha256(s str) []u8`: Sha256 is the SHA-256 digest of s (32 bytes).
- `Sha256Soft(s str) []u8`: Sha256Soft is SHA-256 in portable code (the reference the hardware path is tested against).
- `Sha256Hex(s str) str`: Sha256Hex is the SHA-256 digest of s in lower-case hex.
- `Sha1(s str) []u8`: Sha1 is the SHA-1 digest of s (20 bytes); use it only where a protocol requires it.
- `HmacSha256(key str, msg str) []u8`: HmacSha256 is the HMAC-SHA256 of msg under key (32 bytes).
- `ConstantTimeEq(a []u8, b []u8) bool`: ConstantTimeEq compares a and b in time that depends only on their lengths.
- `RandomBytes(n i64) []u8`: RandomBytes returns n cryptographically secure random bytes.
- `Hex(b []u8) str`: Hex encodes b in lower-case hexadecimal.
- `HexDecode(s str) ![]u8`: HexDecode decodes hexadecimal text.
- `B64(b []u8) str`: B64 encodes b as standard padded base64.
- `B64Decode(s str) ![]u8`: B64Decode decodes standard padded base64.
- `B64URL(b []u8) str`: B64URL encodes b as unpadded URL-safe base64 (as in JWTs).
- `B64URLDecode(s str) ![]u8`: B64URLDecode decodes unpadded URL-safe base64.

## herald

Package herald writes leveled log lines, one write(2) per line so cores never interleave:

```go
2026-10-01T11:22:05.123Z INFO core=2 listening addr=:8080
```

- `const LDebug = 0`
- `const LInfo = 1`
- `const LWarn = 2`
- `const LError = 3`
- `SetLevel(l i64)`: SetLevel drops lines below l (LDebug, LInfo, LWarn, LError) on this core.
- `SetOutput(fd i64)`: SetOutput sends this core's lines to file descriptor fd.
- `SetClock(f func() i64)`: SetClock replaces the clock (unix milliseconds), for tests.
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

```go
crucible.EqI("sum", Sum(2, 3), 5)
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
- `Bench(label str, n i64, f func(i64))`: Bench runs f(i) for i in [0, n) and prints the time per call.
- `type T struct`: T is one running test: checks record failures in it, and the test continues.
- `type B struct`: B is one running benchmark: run the measured code b.N times.
- `(t mut T) Error(msg str)`: Error marks the test failed with msg (it keeps running).
- `(t mut T) Log(msg str)`: Log records msg; it is printed only if the test fails.
- `(t T) Failed() bool`: Failed reports whether the test has failed so far.
- `(t mut T) True(label str, cond bool)`: True fails the test with label unless cond holds.
- `(t mut T) False(label str, cond bool)`: False fails the test with label if cond holds.
- `(t mut T) NoFault(label str, err fault)`: NoFault fails the test if err is not nil.
- `(t mut T) HasFault(label str, err fault)`: HasFault fails the test if err is nil.
- `Equal[V comparable](t mut T, label str, got V, want V)`: Equal fails the test unless got == want; both are printed on failure.
- `Run(name str, f func(mut T))`: Run runs one test and prints its result like go test -v.
- `RunBench(name str, f func(mut B))`: RunBench runs one benchmark with b.N doubling until it takes at least 1 s, then prints the time per operation.
- `Finish()`: Finish prints PASS or FAIL and exits with status 1 when a test failed.
