# Go coverage: what Tin has, and what it still needs

Generated from `notes/coverage.md` by `tools/gencoverage.tin`; edit the source and
regenerate `docs/COVERAGE.md` to publish inventory changes.

The goal is a language in which everything Go's built-ins and standard library let a program do can be done, written in Tin. That is a goal about capabilities, not about copying Go: where Go's shape needs something Tin has chosen not to have (interfaces, reflection, shared mutable state), the entry says what takes its place. This page is the checklist. Update it in the same change that adds or removes a capability.

The inventory is the 176 packages `go list std` reports for Go 1.26 (without `internal`, `vendor` and `cmd`), plus the language itself. The `koussa` column is how many of the files in Anghami's service (about 5,600 Go files, 1.15 million lines) import the package, as production files plus test files. It is a yardstick for what real services need, not a port target.

| status | meaning |
|---|---|
| done | covers what the Go package is used for |
| partial | a Tin package covers part of it; the gaps are listed |
| missing | nothing yet |
| design | Go's shape needs something Tin deliberately lacks; the replacement is named or still to be designed |
| n/a | specific to Go's toolchain or runtime, with no counterpart to build |

**Standard library, 176 packages:** 2 done, 45 partial, 7 design, 98 missing, 24 n/a.
**Of the 87 packages koussa imports:** 2 done, 41 partial, 6 design, 38 missing, 0 n/a.

## The language

| Go | Tin | status |
|---|---|---|
| `append`, `cap`, `copy`, `delete`, `len`, `make`, `new`, `panic`, `print`, `println` | the same (docs/LANGUAGE.md section 13); `make` covers slices and maps | done |
| `min`, `max` | two arguments of one type; Go takes any number | partial |
| `clear` |  | missing |
| `complex`, `real`, `imag`, complex types | no complex type | missing |
| `close`, channels | no channels: routines and messages, to be designed (relay between cores exists) | design |
| `recover` | none: a panic ends the program. Per-request fault isolation is to be designed | design |
| integer and float types, `bool`, `string` | `i8` to `i64`, `u8` to `u64`, `f32`, `f64`, `bool`, `str`; no implicit conversions | done |
| arrays `[N]T` | `[N]T` is a slice that starts with N zeros; no value semantics | partial |
| slices, three-index slices | slices are references; the full slice expression `s[a:b:c]` is not documented | partial |
| maps | insertion-ordered; keys `str`, integers, `bool`, `f64`, structs and enums of those | partial |
| structs, methods | yes; fields and methods follow the capitalized-export rule | done |
| struct embedding | not documented | missing |
| struct tags | none: attributes checked by the compiler are the plan | design |
| interfaces, type assertions, type switches | shapes: `shape` declarations (method sets, composition, named unions, generic parameters and instances like `Seq[i64]`), structural satisfaction, static dispatch by monomorphization, and explicit `dyn S` two-word values with method tables, optionals, slices, `keep` and region checks. Map values and `!dyn` results remain deferred. No type assertions or type switches by design (an `enum` is a closed set); #141 | partial |
| generics | type parameters with imported library shapes `constraints.Any`, `constraints.Comparable` and `sift.Ordered`, plus unions; inference; methods on generic types | partial |
| function values, closures | capturing closures as region objects with shared cells (Go 1.22 per-iteration loop variables), frame-resident descriptors for closures only the library calls (no pool allocation), deep-copied by keep(), escape into globals rejected, defer with captures; a local closure cannot recurse and cannot capture a mut parameter; cells for every captured variable (by-value copies of never-reassigned variables are a later optimization) | done |
| method values and expressions | not documented | missing |
| variadic functions | documented for the standard library's formatting; user-declared variadics not documented | partial |
| named results, bare `return` | not documented | missing |
| multiple results, `err` as a value | `!T` results with `fail`, `try` and `catch`; ignoring a fault is a compile error | done |
| `defer` | yes, outside loops | partial |
| `goroutines`, `go`, `select`, `sync` | none: routines to be designed on top of the per-request tasks | design |
| labels, `goto`, `fallthrough` | none | design |
| `switch`, `for`, `range` over slices, strings, maps, integers | yes; `switch` has no fallthrough | done |
| range over functions and iterators |  | missing |
| `iota`, typed and untyped constants | yes | done |
| `init` functions, package variables | package variables initialize in declaration order; `init` is not documented | partial |
| packages and imports, `internal` | directories under `lib/`, imports by name, `./` for local packages; an `internal` rule is not documented | partial |
| modules, `go.mod`, versioned dependencies | path imports from `vendor/`, `tin.mod`, `tin vendor` and `tin.lock` content hashes (PACKAGES.md); no version resolution or fetching by design | partial |
| build tags, `GOOS`/`GOARCH` files | files ending `_darwin`, `_linux`, `_linux_arm64`, `_linux_amd64` | partial |
| `unsafe`, `cgo` | no `unsafe`; `extern` only inside the standard library | design |
| `reflect` | none: compile-time derivation | design |
| `//go:embed`, `//go:generate` | none | missing |
| `testing`, benchmarks, fuzzing | `tin test` with `crucible`; no fuzzing | partial |
| garbage collector | none: request pools and `keep`, checked at compile time | design |
| race detector | not needed: no shared mutable state between threads | n/a |

## The standard library

Ordered by import path, as `go list std` prints them.

| Go package | koussa | status | Tin | what is there, what is missing |
|---|---|---|---|---|
| `archive/tar` | 1+0 | missing |  | tar archives; needs the io shape first |
| `archive/zip` |  | missing |  | zip archives; needs compress/flate |
| `bufio` | 18+3 | partial | flume | buffered Reader (Line, Byte, ReadAll) and Writer (Str, Int, Flush); no Scanner with split functions, no ReadWriter |
| `bytes` | 76+28 | partial | ore, twine.Builder | about 20 functions on []u8; no Buffer or Reader type, no Map, Title, FieldsFunc or TrimFunc |
| `cmp` | 14+5 | partial | sift (Less, Cmp, `Ordered`), builtin min/max | Less and Cmp (NaN first, as Go), and `sift.Ordered` for generic ordering; no cmp.Or |
| `compress/bzip2` |  | missing |  |  |
| `compress/flate` |  | missing |  | needed by gzip, zlib and zip |
| `compress/gzip` | 7+1 | missing |  |  |
| `compress/lzw` |  | missing |  |  |
| `compress/zlib` |  | missing |  |  |
| `container/heap` | 2+0 | partial | cairn | IntHeap and IntMaxHeap; no heap over any element type (generics now allow one) |
| `container/list` | 1+1 | missing | cairn (deque, queue) | no doubly linked list with stable element handles |
| `container/ring` |  | missing |  |  |
| `context` | 3044+681 | missing | design: ambient task deadline and cancellation | every request task already has a deadline; the cancel signal, values and the scoped form are unbuilt |
| `crypto` |  | n/a |  | the Hash registry and interfaces; there are no interfaces |
| `crypto/aes` | 4+0 | missing |  |  |
| `crypto/cipher` | 2+0 | missing |  | GCM, CTR, CBC |
| `crypto/des` |  | missing |  |  |
| `crypto/dsa` |  | missing |  | deprecated in Go |
| `crypto/ecdh` |  | missing |  |  |
| `crypto/ecdsa` | 1+1 | missing |  |  |
| `crypto/ed25519` |  | missing |  |  |
| `crypto/elliptic` |  | missing |  |  |
| `crypto/fips140` |  | n/a |  | Go's FIPS module switch |
| `crypto/hkdf` |  | missing |  |  |
| `crypto/hmac` | 16+7 | partial | seal | HmacSha256 only |
| `crypto/hpke` |  | missing |  |  |
| `crypto/md5` | 12+3 | partial | (postgres/md5, internal) | exists only inside the PostgreSQL client; not public |
| `crypto/mlkem` |  | missing |  |  |
| `crypto/mlkem/mlkemtest` |  | n/a |  |  |
| `crypto/pbkdf2` |  | partial | seal | Pbkdf2Sha256 and a timeout form; no other hashes |
| `crypto/rand` | 18+1 | partial | seal | RandomBytes; no Reader, Int or Prime |
| `crypto/rc4` |  | missing |  | deprecated in Go |
| `crypto/rsa` | 4+0 | partial | seal | ParseRSAPublicKeyPEM and EncryptOAEPSha1 (the MySQL login); no key generation, signing or verification |
| `crypto/sha1` | 8+1 | partial | seal | Sha1 one shot; no streaming hash |
| `crypto/sha256` | 23+8 | partial | seal | Sha256, Sha256Hex (hardware instructions where present); no streaming hash, no SHA-224 |
| `crypto/sha3` |  | missing |  |  |
| `crypto/sha512` | 1+0 | missing |  |  |
| `crypto/subtle` | 9+0 | partial | seal | ConstantTimeEq only |
| `crypto/tls` | 3+2 | missing |  | issue #124: client first, then server; blocks https, wss and TLS to databases |
| `crypto/x509` | 2+3 | missing |  |  |
| `crypto/x509/pkix` |  | missing |  |  |
| `database/sql` | 702+19 | partial | mysql, postgres (and the `query` type) | each client has Open, Query, Exec, Begin, Commit, Rollback and typed values, pooled per core; no shared driver abstraction, no Scan into structs, no prepared-statement handle API |
| `database/sql/driver` | 18+0 | design |  | no interfaces: a driver would be a package with a fixed shape or a table of functions |
| `debug/buildinfo` |  | missing |  | low priority |
| `debug/dwarf` |  | missing |  | low priority |
| `debug/elf` |  | missing |  | low priority (the compiler writes ELF but does not read it) |
| `debug/gosym` |  | n/a |  | Go symbol tables |
| `debug/macho` |  | missing |  | low priority |
| `debug/pe` |  | missing |  | low priority |
| `debug/plan9obj` |  | n/a |  |  |
| `embed` | 2+0 | missing |  | compile-time file embedding |
| `encoding` | 1+0 | design | compile-time derivation | Marshaler interfaces become derived code, as argo already does for JSON |
| `encoding/ascii85` |  | missing |  |  |
| `encoding/asn1` |  | missing |  | needed by x509 |
| `encoding/base32` | 1+0 | missing |  |  |
| `encoding/base64` | 50+15 | partial | seal | standard (padded) and URL-safe (unpadded) with decoders; no padded URL-safe form, no unpadded standard form, no streaming encoder |
| `encoding/binary` | 5+1 | missing |  | byte orders, varints, Read and Write of fixed-size values |
| `encoding/csv` | 4+0 | missing |  |  |
| `encoding/gob` | 2+0 | missing |  | low priority: Go's own format |
| `encoding/hex` | 37+9 | partial | seal | Hex and HexDecode; no Dump, no streaming |
| `encoding/json` | 297+76 | partial | argo | Put and Get are generated per type, fast; no decoding into a dynamic value, no field tags, no Indent, no streaming Encoder or Decoder, no RawMessage beyond Raw |
| `encoding/pem` | 1+1 | missing |  |  |
| `encoding/xml` | 52+8 | missing |  |  |
| `errors` | 393+152 | partial | fault, try, catch, say.Fault | no Is, As, Unwrap or Join: a fault is a message, with no wrapping chain |
| `expvar` |  | missing |  |  |
| `flag` | 1+0 | partial | lever | Str, Int, Bool, F64, Parse, Usage; no FlagSet, no Duration, no custom Value |
| `fmt` | 944+127 | partial | say | Line, Fmt, Str, Fault and string interpolation with format specs, by static type; no Sscanf, Fscan or Scan, and no Stringer or Formatter (formatting is derived) |
| `go/ast` |  | n/a |  | Go's own compiler front end; Tin's compiler is selfhost/ |
| `go/build` |  | n/a |  |  |
| `go/build/constraint` |  | n/a |  |  |
| `go/constant` |  | n/a |  |  |
| `go/doc` |  | n/a |  |  |
| `go/doc/comment` |  | n/a |  |  |
| `go/format` |  | n/a |  | a Tin formatter is a separate tool, not this package |
| `go/importer` |  | n/a |  |  |
| `go/parser` |  | n/a |  |  |
| `go/printer` |  | n/a |  |  |
| `go/scanner` |  | n/a |  |  |
| `go/token` |  | n/a |  |  |
| `go/types` |  | n/a |  |  |
| `go/version` |  | n/a |  |  |
| `hash` | 1+0 | design |  | the Hash interface; streaming hashes need a generic or a table of functions |
| `hash/adler32` |  | partial | stamp | Adler32 one shot |
| `hash/crc32` | 0+1 | partial | stamp | Crc32, Crc32C, Crc32Update; no table type, no streaming hash |
| `hash/crc64` |  | missing |  |  |
| `hash/fnv` | 3+0 | partial | stamp | Fnv32a and Fnv64a; not the FNV-1 variants |
| `hash/maphash` |  | missing |  | maps are hashed internally with a per-process key |
| `html` |  | missing |  | EscapeString and UnescapeString |
| `html/template` | 3+1 | missing |  | contextual escaping; koussa uses templ, a code generator |
| `image` | 24+1 | missing |  |  |
| `image/color` | 9+2 | missing |  |  |
| `image/color/palette` |  | missing |  |  |
| `image/draw` | 1+0 | missing |  |  |
| `image/gif` | 1+0 | missing |  |  |
| `image/jpeg` | 7+1 | missing |  |  |
| `image/png` | 6+0 | missing |  | needs compress/zlib |
| `index/suffixarray` |  | missing |  |  |
| `io` | 91+20 | partial | `io` declares Reader, Writer, Closer, Seeker, ReaderAt, WriterAt and the compositions; structural satisfaction, generic `Copy[R io.Reader, W io.Writer]`, and explicit `dyn io.Writer` calls are verified. The `io.Copy` package function, ReadAll, Pipe, MultiWriter, LimitReader, TeeReader and EOF as a sentinel fault remain future work (#141) |
| `io/fs` | 2+0 | missing |  |  |
| `io/ioutil` |  | n/a | quarry | deprecated in Go; quarry has ReadFile, WriteFile, ReadDir |
| `iter` |  | missing |  | range over functions; `for range` covers slices, strings, maps and integers |
| `log` | 7+2 | partial | herald | levels, output, clock; no Logger values |
| `log/slog` |  | partial | herald | leveled lines with key and value pairs; no Handler, Group or LogValuer |
| `log/syslog` |  | missing |  |  |
| `maps` | 2+4 | partial | atlas | Keys, Values (slices, in insertion order), SortedKeys, Clone, Copy, Equal, EqualFunc, DeleteFunc; no iterator forms (All, Insert, Collect) |
| `math` | 59+23 | partial | gauge | Sin to Atan2, Sinh to Tanh, Exp, Exp2, Log family, Pow, Cbrt, Hypot, Mod, Frexp, Ldexp, Modf (ported from Go, no libm); missing Gamma, Lgamma, Erf, Erfc, Expm1, Asinh, Acosh, Atanh, Sincos, FMA, Nextafter, Remainder, Logb, Dim, Bessel functions |
| `math/big` | 8+0 | missing |  | Int, Float, Rat |
| `math/bits` | 3+0 | done | bits | LeadingZeros, TrailingZeros, PopCount (OnesCount), Len, RotateLeft, Reverse, ReverseBytes, and Add, Sub, Mul, Div, Rem with carries, at 8, 16, 32 and 64 bits as Go has them, each name carrying its width; no uint-wide forms because Tin has no uint |
| `math/cmplx` |  | missing |  | there is no complex type |
| `math/rand` | 17+8 | partial | dice | xoshiro256** generators, Intn, F64, NormF64, Perm, Shuffle; no Zipf, no ExpFloat64, no Source interface |
| `math/rand/v2` | 1+1 | partial | dice | same generators; no PCG or ChaCha8 types, different method names |
| `mime` | 1+0 | missing |  |  |
| `mime/multipart` | 8+0 | missing |  |  |
| `mime/quotedprintable` |  | missing |  |  |
| `net` | 20+2 | partial | wire | TCP Dial, DialTimeout, Listen, Accept, deadlines; no UDP, Unix sockets, IP or CIDR types, resolver control |
| `net/http` | 553+126 | partial | anvil, wire, websocket | server with Router, middleware, groups, HEAD and 405 handling; client Get, Post, Do; WebSocket; no TLS, HTTP/2, cookies, multipart, Client or Transport configuration, streaming bodies |
| `net/http/cgi` |  | missing |  | low priority |
| `net/http/cookiejar` |  | missing |  |  |
| `net/http/fcgi` |  | missing |  | low priority |
| `net/http/httptest` | 1+57 | partial | anvil.Router.Run | runs a request through a router without a socket; no ResponseRecorder or test Server |
| `net/http/httptrace` |  | missing |  |  |
| `net/http/httputil` | 5+0 | missing |  | ReverseProxy, DumpRequest |
| `net/http/pprof` | 1+0 | missing |  | profiling endpoints; part of the performance goal |
| `net/mail` | 6+0 | missing |  |  |
| `net/netip` |  | partial | link | only the check that a bracketed URL host is an IPv6 address, with Go's fault messages (private to link); no Addr, Prefix or AddrPort types |
| `net/rpc` |  | missing |  | low priority |
| `net/rpc/jsonrpc` |  | missing |  | low priority |
| `net/smtp` |  | missing |  |  |
| `net/textproto` |  | missing |  |  |
| `net/url` | 103+20 | partial | link | Parse, ParseRequestURI, URL (String, EscapedPath, EscapedFragment, Hostname, Port, RequestURI, Redacted, ResolveReference, Parse, JoinPath), Userinfo, Values (Get, Set, Add, Del, Has, Encode), ParseQuery, Query/Path Escape and Unescape, JoinPath, with Go's fault messages; User is an optional, Values is a struct over a map (methods need a struct), URL.Clone replaces copying by assignment; no *url.Error type (a fault carries its message only, until fault chains, #142), no MarshalBinary, AppendBinary or UnmarshalBinary |
| `os` | 24+60 | partial | quarry | Args, environment, ReadFile, WriteFile, AppendFile, Mkdir, Remove, Rename, ReadDir, Getwd, Exit, Hostname, Pid; files are opened through flume (buffered) and there is no os.File type with Seek; no Stat and FileInfo, no Chmod, symlinks or pipes |
| `os/exec` | 1+3 | missing |  |  |
| `os/signal` | 1+0 | missing |  | anvil handles SIGTERM and SIGINT for graceful shutdown internally |
| `os/user` |  | missing |  |  |
| `path` | 8+1 | partial | trail | Clean, Base, Dir, Ext, Join, Split, Match, IsAbs |
| `path/filepath` | 27+6 | partial | trail | the same, plus Rel; no Walk, WalkDir, Glob, Abs or EvalSymlinks |
| `plugin` |  | design |  | no dynamic loading |
| `reflect` | 369+132 | design | compile-time derivation (argo, say) | runtime reflection is not planned; what code uses it for (serialization, validation, mapping rows to structs) becomes derived code |
| `regexp` | 59+1 | missing |  | needs an RE2-style engine; linear time |
| `regexp/syntax` |  | missing |  |  |
| `runtime` | 2+2 | partial | hearth | Cores, ID, MemLimit, PoolChunk, Reset; no GC controls (there is no GC), no Gosched or NumGoroutine, no Caller or Stack |
| `runtime/cgo` |  | n/a |  |  |
| `runtime/coverage` |  | missing |  |  |
| `runtime/debug` | 3+0 | missing |  | backtraces exist on panic; no SetGCPercent (no GC), no Stack or ReadBuildInfo |
| `runtime/metrics` |  | missing |  |  |
| `runtime/pprof` |  | missing |  | CPU and allocation profiling; part of the performance goal |
| `runtime/race` |  | n/a |  | the language rules out shared mutable state between threads |
| `runtime/trace` |  | missing |  |  |
| `slices` | 79+37 | partial | sift | Sort, SortFunc, SortStableFunc (Go's algorithm, same order of equal elements), IsSorted, BinarySearch, Min, Max, Index, Contains, Equal, Compare, Reverse, Insert, Delete, DeleteFunc, Replace, Compact, Clone, Grow, Concat, Repeat, with the Func forms; Insert, Delete and the others take a `mut` slice and return the result; no Clip, Chunk, or iterator forms, and no variadic forms (InsertAll and ConcatAll take slices) |
| `sort` | 105+8 | partial | sift | Ints, Strs, SortBy, Search* and the generic `Sort[E sift.Ordered]` and SortFunc; no sort.Interface (by design), no sort.Slice (use SortFunc) |
| `strconv` | 875+97 | partial | mint | Itoa, Atoi, ParseInt, ParseUint, ParseBool, ParseFloat, FormatInt, FormatUint, FormatFloat, Quote, Unquote and friends; no AppendFloat, AppendBool, QuoteToASCII, IsPrint, ParseComplex |
| `strings` | 657+147 | partial | twine | every function except the iterator forms and Reader: Index family, Split family with SplitAfter, Fields and FieldsFunc, Map, Title, Unicode ToUpper, ToLower, ToTitle, EqualFold by SimpleFold, Trim family with Func forms, Cut, CutPrefix, CutSuffix, Replacer, Lines, ToValidUTF8, Clone, Builder (Cap, Grow, Write); Lines is a slice, not an iterator; no NewReader (with the io port), no ToUpperSpecial |
| `structs` |  | n/a |  |  |
| `sync` | 69+32 | design | share-nothing cores, relay | no Mutex or RWMutex by design; WaitGroup, Once, Pool and Map need routine-level equivalents |
| `sync/atomic` | 7+12 | missing |  | the runtime has atomic operations as compiler intrinsics; there is no public package |
| `syscall` | 2+1 | missing |  | low priority |
| `testing` | 4+1071 | partial | crucible, `tin test` | checks, Run, benchmarks; no t.Parallel, subtests with cleanup, TempDir, fuzzing, example tests |
| `testing/cryptotest` |  | missing |  |  |
| `testing/fstest` |  | missing |  |  |
| `testing/iotest` |  | missing |  |  |
| `testing/quick` | 0+1 | missing |  |  |
| `testing/slogtest` |  | missing |  |  |
| `testing/synctest` |  | missing |  |  |
| `text/scanner` |  | missing |  |  |
| `text/tabwriter` |  | missing |  |  |
| `text/template` |  | missing |  |  |
| `text/template/parse` |  | missing |  |  |
| `time` | 1012+272 | partial | tide | Now, Since, Sleep, Wait, durations with parse and format, RFC 3339 and HTTP date, calendar arithmetic; no time zones or Location, no layout-based Format and Parse, no Timer, Ticker or After, no Month and Weekday types |
| `time/tzdata` |  | missing |  |  |
| `unicode` | 14+0 | partial | glyph | Unicode 15.0.0 as Go has it: Is over every category, script and property (the Table enum), IsOneOf, IsLetter, IsDigit, IsNumber, IsSpace, IsUpper, IsLower, IsTitle, IsMark, IsPunct, IsSymbol, IsControl, IsGraphic, IsPrint, To, ToUpper, ToLower, ToTitle, SimpleFold, generated from Go's tables by tools/gen_unicode.py; no RangeTable values, no SpecialCase, no FoldCategory or FoldScript |
| `unicode/utf16` |  | missing |  |  |
| `unicode/utf8` | 10+0 | done | glyph | every function |
| `unique` |  | missing |  |  |
| `unsafe` | 342+0 | design |  | raw operations exist only for the standard library, behind the region checker |
| `weak` |  | n/a |  | there is no garbage collector |

## What to build, in order

The order comes from two things: what other work depends on, and what services import most. Foundations come first because the rest of the library is written in their terms. Each is decided in [notes/design_foundations.md](../notes/design_foundations.md) (the need, the decision, what it replaces, what was rejected, what it unlocks), which also has the order of the steps and what each depends on.

**Foundations (decided; build in the order of that document):**

1. Closures that capture, as region objects.
2. Shapes (structural interfaces, static by default, `dyn` when asked) for `io`, `sort`, `hash` and `database/sql/driver`.
3. Fault chains (`fault.Is`, `Wrap`, `Join`, `try ... wrap`) and `guard` in place of `recover`.
4. Tasks and scopes (structured concurrency on the core) and `context` as ambient deadline, cancellation and slots. `context` is imported by 3,725 koussa files, more than anything else.
5. Atomics for cross-core counters; no mutexes.
6. Compile-time type information and attributes in place of `reflect` and struct tags, extending what `argo` does for JSON.

**High demand:** `time` (zones, layouts, timers), `regexp`, the rest of `encoding/json`, `strconv`, `strings`, `slices`, `maps`, `sort`, `bytes`, `os` file handles, `net/http` client and server completeness, `net/http/httptest`, `encoding/xml`, `crypto/tls` (#124), `database/sql`'s common shape, `image`, `math/big`, `compress/gzip`, `mime/multipart`.

**Performance tooling:** `runtime/pprof`, `net/http/pprof`, `runtime/metrics`: the end goal is performance, and it cannot be improved without a profiler.

**The rest** as services need them: the remaining `crypto`, `encoding`, `text`, `net` and `archive` packages.
