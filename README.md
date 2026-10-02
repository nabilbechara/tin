# Tin

Tin is a compiled, Go-like language for servers and tools on macOS arm64 and Linux
arm64/amd64. It is meant to
be written by AI, so it trades human convenience for speed and robustness: the compiler
rejects ignored errors, nil dereferences, request memory leaking into long-lived state, and
shared mutable state between threads.

- **Self-hosted**: the compiler (`tinc`, about 19k lines of Tin) compiles itself to a
  byte-identical binary, on macOS and on Linux, and writes signed Mach-O or ELF executables
  with its own assembler and linkers. No clang, ld, Go or libc headers are needed, and
  cross-compiling is one flag (`tin build --target linux-arm64`).
- **No GC, no pauses**: request-scoped bump pools plus a long-lived per-core heap, with a
  compile-time check that request memory never escapes without `keep()`.
- **Thread per core, share nothing**: per-core globals, `hearth` cores, `relay` messages,
  and an HTTP server (`anvil`) with one kqueue/epoll event loop per core.
- **Strict**: sized integers with no implicit conversions, non-nil references, `?T`
  optionals, faults that must be handled (`try`), mandatory bounds checks (removed when
  proven safe), `defer`, generics by monomorphization.

```go
package main

import "say"
import "argo"
import "anvil"

type Message struct {
	message str
}

func handle(q anvil.Req, w mut anvil.Out) {
	if q.Path == "/json" {
		w.Json()
		argo.Put(mut w.Body, Message{message: "Hello, World!"})
		return
	}
	w.Status(404)
	w.Text("not found")
}

func main() {
	err := anvil.Serve(":8080", handle)
	say.Line("server:", err)
}
```

## Quick start

Install a release without a local toolchain:

```sh
curl -fL https://github.com/yasserreslan/tin/releases/download/v0.4.0/install.sh -o install-tin.sh
sh install-tin.sh 0.4.0
export PATH="$HOME/.tin/bin:$PATH"
```

Or compile in Docker:

```sh
docker run --rm -v "$PWD:/src" ghcr.io/yasserreslan/tin:0.4.0 build app.tin -o app
```

See [distribution and containers](docs/DISTRIBUTION.md) for checksums, upgrades and
multi-stage Dockerfiles. To build and test from a source checkout:

```sh
make install                  # build bin/tinc from the seed and put `tin` on the PATH
tin examples/api.tin          # compile and run
tin build app.tin -o app      # native executable
tin test ./mypkg               # run mypkg's *_test.tin tests (Go style)
tin suite                     # the compiler's strict test suite (tests/v2)
make test                     # everything: strict suite + legacy suites in 3 modes
make bootstrap                # tinc rebuilds itself twice; the binaries must be identical
```

Documentation: [docs/README.md](docs/README.md), the index. The language reference is
[docs/LANGUAGE.md](docs/LANGUAGE.md), the standard library [docs/STDLIB.md](docs/STDLIB.md)
(generated from the sources by `tools/gendoc.py`), commands and builds
[docs/TOOLING.md](docs/TOOLING.md), targets and containers [docs/PORTING.md](docs/PORTING.md),
the runtime [docs/RUNTIME.md](docs/RUNTIME.md), the compiler
[docs/COMPILER.md](docs/COMPILER.md), and full benchmark results
[docs/PERFORMANCE.md](docs/PERFORMANCE.md).

CI and the issue-to-regression workflow: [docs/CI.md](docs/CI.md).

## Standard library

| package | role | | package | role |
|---|---|---|---|---|
| say | formatting, printing | | quarry | files, env, process |
| argo | JSON (generated per type) | | trail | paths |
| anvil | HTTP/1.1 server | | lever | flags |
| hearth | cores | | tide | time |
| relay | messages between cores | | dice | random numbers |
| wire | TCP, HTTP client | | sift | sorting, searching |
| twine | strings | | cairn | heaps, deques, sets, LRU |
| glyph | UTF-8 | | stamp | CRC-32, FNV, xxHash64 |
| mint | number/string conversion | | seal | SHA-256, HMAC, PBKDF2, base64, hex |
| gauge | math | | herald | logging |
| ore | byte slices | | crucible | test checks, benchmarks |
| flume | buffered I/O | | redis | Redis client (pipelined) |
| websocket | WebSocket server and client | | mysql | MySQL client (pooled) |
| postgres | PostgreSQL client (pooled, SCRAM) | | | |

Language and library checks live in `tests/v2/`, and protocol client checks in
`tools/ci/`. Core library behavior is also checked against Go equivalents in
`bench/ref/`; see [notes/stdlib_verified.md](notes/stdlib_verified.md).

## Performance

Apple M3 Pro (5 performance + 6 efficiency cores), Go 1.26, fasthttp 1.74, wrk 4.2, the
load generator on the same machine. Run with `bench/http/run_wrk.sh` and
`bench/http/run_pipelined.sh`.

**HTTP, 1 server core, wrk -t4 -c100, median of 3** (the server is the bottleneck):

| server | /json req/s | p99 | /plaintext req/s | p99 | memory |
|---|---|---|---|---|---|
| **anvil** | **316k** | **0.63 ms** | **324k** | **0.60 ms** | 3–6 MB |
| fasthttp | 231k | 0.77 ms | 236k | 1.17 ms | 9–13 MB |
| net/http | 138k | 1.33 ms | 141k | 1.51 ms | 13–14 MB |

**HTTP, 16 pipelined requests per write** (TechEmpower plaintext style):

| server cores | anvil | fasthttp | net/http |
|---|---|---|---|
| 1 | **2.98M** | 1.40M | 0.19M |
| 2 | **4.46M** | 2.83M | 0.33M |
| 4 | **3.69M** | 3.45M | 0.65M |

**HTTP on Linux** (arm64 Debian container on the same Mac, wrk -t4 -c100, median of 3):

| server cores | anvil | fasthttp | net/http |
|---|---|---|---|
| 1 /json | **414k**, p99 **0.44 ms** | 243k, 0.89 ms | 107k, 2.03 ms |
| 2 /json | **859k**, p99 **0.32 ms** | 378k, 0.71 ms | 181k, 1.71 ms |
| 4 /json | **855k**, p99 **0.79 ms** | 719k, 1.84 ms | 406k, 1.42 ms |

At 4 cores on `/plaintext`, with accept-time balancing: anvil 883k req/s, p99 0.42 ms
against fasthttp 866k, 0.99 ms.

On macOS without pipelining, at 2 or more server cores wrk itself saturates this machine (all three
servers land at 220–260k req/s, and net/http comes out about 10% ahead at 4 cores because
its bursty replies let wrk batch). Per CPU-second of server time, anvil serves 328k
requests at one core against 237k for fasthttp and 143k for net/http.

**CPU benchmarks** (bench/v2, best of 3, identical output to Go). The mixed demo
(`examples/demo.tin` vs `examples/demo_go`: primes, sort, SHA-256, JSON, maps) runs in
0.80 s against Go's 1.01 s.

| benchmark | Tin | Go | Tin/Go |
|---|---|---|---|
| binary-trees (depth 18) | 0.31 s | 0.95 s | **0.33** |
| sort 10M i64, stable | 0.68 s | 2.65 s | **0.26** |
| sort 10M i64 | 0.60 s | 0.68 s | **0.89** |
| JSON encode (argo vs encoding/json) | 1.08 s | 1.83 s | **0.59** |
| SHA-256, 100 MB (CPU SHA instructions) | 0.037 s | 0.035 s | 1.05 |
| hash map 5M i64 | 0.54 s | 0.60 s | **0.90** |
| spectral-norm 5500 | 1.30 s | 1.30 s | 1.00 |
| mandelbrot 4000 | 0.69 s | 0.67 s | 1.03 |
| sieve 100M | 0.48 s | 0.46 s | 1.04 |
| LCG loop | 1.26 s | 1.21 s | 1.04 |
| n-body 50M | 1.89 s | 1.76 s | 1.07 |
| fannkuch 11 | 1.97 s | 1.72 s | 1.15 |
| string building 10M | 0.07 s | 0.06 s | 1.17 |

binary-trees uses 917 MB against Go's 37 MB: a plain program never resets its pool
(servers reset it per request). Binaries are tens of KB (Go: megabytes).

## Layout

```
selfhost/    the compiler: lex, parse, check, lower, generics, region, inline, opt,
             gen + asm (arm64), gen_x64 + asm_x64, macho, elf, elf_x64
lib/         runtime and standard library
tests/v2/    strict tests with expected outputs (*_bad.tin: expected compile errors)
bench/       CPU benchmarks vs Go (v2/), HTTP benchmarks (http/), Go reference programs (ref/)
bootstrap/   the original Go compiler (stage 0) and the legacy test harness
seed/        tinc-darwin-arm64, tinc-linux-arm64: the compilers that start a build
tools/       test runners (v2test.sh, linuxtest.sh), debugging helpers, gendoc.py
docs/        the documentation (index: docs/README.md)
notes/       verification notes, benchmark analyses, roadmap
```

## Status and next steps

Targets: darwin-arm64, linux-arm64 and linux-amd64, each tested natively in CI, and the
compiler self-hosts on all three; see [docs/PORTING.md](docs/PORTING.md).

v0.4: each anvil request runs in its own task with its own stack and pool, so a handler
that waits (`tide.Wait`, `wire`, `quarry` files, `redis`, `mysql`, `postgres`, `websocket`) lets its
core serve other requests meanwhile. Sockets are non-blocking; DNS and file I/O go to
helper threads; every request has a deadline. Statements and commands are `query`
values, so a value is always sent apart from the text. See
[docs/RUNTIME.md](docs/RUNTIME.md) and [notes/roadmap.md](notes/roadmap.md).
