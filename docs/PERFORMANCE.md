# Performance

## Benchmark policy

Tin is deployed on Linux, so its performance is judged on Linux. macOS arm64 is a
development platform (docs/PORTING.md, "Platform roles").

- **Reference numbers are Linux.** A number quoted as a result (README, this file, a PR
  claiming a speed-up or "no regression", a release note) comes from Linux on bare metal
  or a dedicated VM, native to the CPU, with the machine, CPU model, kernel, Go version
  and load-generator placement stated next to it. Both CPUs count: linux-arm64 and
  linux-amd64.
- **Not reference:** macOS, Linux containers on a macOS host (Docker Desktop runs a VM),
  emulated CPUs, laptops on battery. These are fine for a quick check during development,
  but are not quoted as results and do not decide "faster or slower".
- **Comparisons run on the same machine in the same job**, interleaved (Tin and Go, before
  and after), and are reported as medians with the ratio. On shared machines (GitHub-hosted
  runners) only the ratios are meaningful; absolute numbers vary between runs.
- **Continuous tracking:** `.github/workflows/bench-linux.yml` runs the CPU suite
  (`bench/v2`, Tin vs Go) and the HTTP suite (`bench/http/run_wrk.sh`, anvil vs fasthttp vs
  net/http) on `ubuntu-24.04` (x86-64) and `ubuntu-24.04-arm` every week, on demand and on
  pull requests that change `bench/`, `lib/` or `selfhost/`, and writes the tables to
  the job summary. The same job compares the PR head with its merge base, each built
  from its own seed, compiler, runtime and libraries. Manual runs accept `base_ref`;
  manual runs without it and scheduled runs compare against the first parent.
- **Existing macOS numbers:** the sections below were measured on the macOS development
  machine before this policy. They are kept for history until Linux reference runs replace
  them, section by section; do not add new macOS numbers.

## Comparing revisions

For libc-removal work ([phase plan](../notes/libc_removal.md)), use both native Linux
jobs in `bench-linux.yml`. Each job retains Tin-versus-Go measurements and adds a
base-versus-head comparison with identical benchmark source. Each compiler loads its
own revision's `lib/` through an explicit `TIN_ROOT`; copying two compiler binaries
into one source tree is not an allocator/runtime comparison.

CPU measurements use at least seven alternating runs per side, check stdout and stderr
on **every** run, and report medians plus head/base elapsed time. HTTP uses at least
five alternating rounds per side on one server core, `/json` and `/plaintext`, with the
same load generator and settings. It checks readiness, response bodies, process status
and wrk errors; failed work is never a performance sample. JSON artifacts retain raw
samples, and HTTP keeps per-run wrk output and server logs. Outputs, crashes, timeouts
and invalid measurements fail the job. Timing alone never fails CI.

A CPU head/base ratio above 1.05 or HTTP head/base req/s below 0.95 is marked **REVIEW**.
Rerun the affected benchmark once; if it persists, fix it or attach a profile for the
maintainer's decision before merging a runtime phase. Paste both architecture tables
and the workflow links in the PR. These thresholds are review triggers, not evidence
that a shared runner measures a 5% change precisely.

With two already bootstrapped checkouts, run on the same native Linux machine:

```sh
python3 bench/compare.py --base-root /path/to/base --head-root /path/to/head --json bin/bench-cpu-compare.json
python3 bench/compare.py --base-root /path/to/base --head-root /path/to/head --suite http --json bin/bench-http-compare.json
# A focused CPU rerun (same seven samples per side):
python3 bench/compare.py --base-root /path/to/base --head-root /path/to/head nbody
# Reference measurements still compare against Go:
BENCH_DIR=bench/v2 python3 bench/run.py --json bin/bench-cpu-reference.json
```

The default CPU input suite is the comparison script's `bench/v2`; `--bench-dir` selects
another shared input suite. HTTP always compiles the head checkout's `examples/api.tin`
with both compilers and their matching library trees. The shell entrypoint
`bench/http/run_wrk.sh` keeps its positional arguments and also accepts
`--base-api /path/to/base-server --head-api /path/to/head-server` (at least five rounds).

## Measurement setup of the existing numbers (macOS development machine)

Measured on an Apple M3 Pro (5 performance + 6 efficiency cores), Go 1.26, fasthttp
1.74, wrk 4.2 (4.1 inside Linux containers), the load generator always on the same
machine as the server. Linux numbers come from an arm64 Debian container under Docker
Desktop, running natively. Scripts: TOOLING.md §7.

The v0.4 service benchmark (`GET /users/{id}` through Redis over MySQL, Tin vs Go + chi
under wrk2, `bench/v04`) is built but not yet measured on a quiet machine; its results
will go here (issue #74).

## 1. HTTP

**macOS, 1 server core, wrk -t4 -c100, median of 3** (the server is the bottleneck):

| server | /json req/s | p99 | /plaintext req/s | p99 | memory |
|---|---|---|---|---|---|
| anvil | 316k | 0.63 ms | 324k | 0.60 ms | 3–6 MB |
| fasthttp | 231k | 0.77 ms | 236k | 1.17 ms | 9–13 MB |
| net/http | 138k | 1.33 ms | 141k | 1.51 ms | 13–14 MB |

**Linux arm64 container, wrk -t4 -c100, median of 3:**

| cores | anvil | fasthttp | net/http |
|---|---|---|---|
| 1 /json | 414k, p99 0.44 ms | 243k, 0.89 ms | 107k, 2.03 ms |
| 2 /json | 859k, p99 0.32 ms | 378k, 0.71 ms | 181k, 1.71 ms |
| 4 /json | 855k, p99 0.79 ms | 719k, 1.84 ms | 406k, 1.42 ms |
| 4 /plaintext | 883k, p99 0.42 ms | 866k, 0.99 ms | 429k, 1.10 ms |

The 4-core /plaintext row is after accept-time balancing (median of 7 interleaved rounds,
server on CPUs 0–3 and wrk on 4–7). With server and wrk sharing all CPUs: anvil 864k, p99
0.40 ms against fasthttp 852k, 0.39 ms. Before balancing, `SO_REUSEPORT` spread 100
connections 26/21/29/20 over the cores and anvil's p99 was about twice fasthttp's; now
27/27/28/26.

**Pipelined (16 requests per write), macOS:** anvil 2.98M req/s on 1 core, 4.46M on 2,
3.69M on 4 (client-bound); fasthttp 1.40M / 2.83M / 3.45M; net/http 0.19M / 0.33M /
0.65M.

On macOS without pipelining, 2+ server cores saturate wrk on this machine; all three
servers land at 220–260k req/s there and net/http edges ahead at 4 cores. Per CPU-second
of server time, anvil serves 328k requests on one core against 237k (fasthttp) and 143k
(net/http).

Why anvil is fast:
- no goroutine scheduling;
- one read and one write per batch of requests;
- requests parsed in place;
- a bump-pointer pool wiped per request instead of garbage collection;
- per-core everything (no locks, no shared cache lines);
- edge-triggered polling;
- JSON encoders generated per type.

**Routing** (`anvil.Router`, measured on an Apple M4 Pro, not the M3 Pro above).
`bench/router` times a lookup (`Match`) and a whole request through the router without
sockets (`Run`: the Req and Out, the lookup, the handler), against the same routes in chi
(`Find`, and `ServeHTTP` with one parsed request reused and a writer that discards):

| routes, request | Tin lookup | chi lookup | Tin request | chi request |
|---|---|---|---|---|
| 1, `GET /res0/42` | 16–17 ns | 36 ns | 39–40 ns | 175 ns |
| 20, `GET /res7/42` | 17–18 ns | 49 ns | 39–41 ns | 185 ns |
| 200, `GET /res37/42/items` | 25–27 ns | 65 ns | 51–55 ns | 209 ns |
| 200, `GET /nope` (404) | 14 ns | 13 ns | 44 ns | 175 ns |

Served on one core with 16 pipelined requests per write (`bin/hammer -c 64 -t 8 -pipeline
16`), so that the server is the bottleneck; median of 3 interleaved rounds, server CPU time
per request from `ps`:

| server | /json | CPU per request | /plaintext | CPU per request |
|---|---|---|---|---|
| plain handler, anvil before the router | 1.93M req/s | 517 ns | 1.95M req/s | 511 ns |
| plain handler, anvil with the router | 1.93M req/s | 516 ns | 1.95M req/s | 511 ns |
| `examples/api.tin` (7 routes, 1 middleware) | 1.88M req/s | 528 ns | 1.88M req/s | 528 ns |
| `bench/http/routes.tin`, 22 routes | 1.89M req/s | 527 ns | 1.90M req/s | 525 ns |
| `bench/http/routes.tin`, 202 routes | 1.88M req/s | 530 ns | 1.89M req/s | 527 ns |

Routing adds 10–15 ns to the 516 ns a pipelined request costs, and a plain handler pays
nothing. Without pipelining, the load generator saturates first on this machine: every
server above measures 181–190k req/s with hammer (`-c 100 -t 4`). The 316k req/s in the
first table was measured with wrk on the M3 Pro before the router, and has not been
re-measured with wrk since.

## 2. CPU benchmarks (bench/v2, best of 3, output identical to Go)

| benchmark | Tin | Go | Tin/Go |
|---|---|---|---|
| binary-trees (depth 18) | 0.31 s | 0.95 s | 0.33 |
| sort 10M i64, stable | 0.68 s | 2.65 s | 0.26 |
| sort 10M i64 | 0.60 s | 0.68 s | 0.89 |
| JSON encode (argo vs encoding/json) | 1.08 s | 1.83 s | 0.59 |
| hash map 5M i64 | 0.54 s | 0.60 s | 0.90 |
| spectral-norm 5500 | 1.30 s | 1.30 s | 1.00 |
| mandelbrot 4000 | 0.69 s | 0.67 s | 1.03 |
| sieve 100M | 0.48 s | 0.46 s | 1.04 |
| SHA-256, 100 MB | 0.037 s | 0.035 s | 1.05 |
| LCG loop | 1.26 s | 1.21 s | 1.04 |
| n-body 50M | 1.89 s | 1.76 s | 1.07 |
| fannkuch 11 | 1.97 s | 1.72 s | 1.15 |
| string building 10M | 0.07 s | 0.06 s | 1.17 |

Mixed demo (`examples/demo.tin` vs `examples/demo_go`): 0.80 s against 1.01 s.

binary-trees uses 917 MB against 37 MB: a plain program never resets its pool.

## 3. Where Go still wins, and why

From `notes/bench_v2.md`, which has the assembly analysis:
- **fannkuch, n-body:**
  - whole-function register allocation runs out of registers in large loops, so some
    loop variables live in stack slots;
  - stores through one struct invalidate loads of another (no alias analysis), so
    fields are reloaded;
  - a few bounds checks the prover cannot remove (`j < n` where `n == len(s)` is only
    known through a separate variable).
- **string building:** `append` of a single byte still checks capacity per call;
  `% 10` uses a division where Go multiplies by a magic constant.
- **Constant materialization:** 64-bit constants are rebuilt with movz/movk inside
  loops.

Planned codegen work in order of payoff: a register allocator with loop-depth spill
weights, length-fact bounds-check elimination, division by constants via
multiply-high, hoisting constant materialization, and alias information for struct
fields.

## 3b. Math functions (gauge)

The transcendental functions are Tin, ported from Go's math package (bench/ref/gauge). 20M calls
in a loop (`x = i%1000*0.01 + 0.001`), best of 9, Apple M3 Pro, one thread, Go 1.26, `clang -O2` against
the system libm. Times in seconds:

| function | Tin | Go | C libm | Tin/Go | Tin/C |
|---|---|---|---|---|---|
| sqrt (one instruction) | 0.015 | 0.015 | 0.015 | 1.02 | 1.01 |
| sin | 0.104 | 0.065 | 0.049 | 1.60 | 2.12 |
| cos | 0.107 | 0.060 | 0.050 | 1.80 | 2.13 |
| tan | 0.103 | 0.064 | 0.064 | 1.61 | 1.60 |
| atan | 0.081 | 0.050 | 0.051 | 1.62 | 1.58 |
| atan2 | 0.116 | 0.081 | 0.102 | 1.43 | 1.13 |
| exp | 0.088 | 0.074 | 0.038 | 1.20 | 2.33 |
| log | 0.105 | 0.069 | 0.042 | 1.53 | 2.47 |
| log1p | 0.107 | 0.070 | 0.054 | 1.53 | 1.96 |
| pow (1.5) | 0.432 | 0.335 | 0.108 | 1.29 | 3.98 |
| sinh | 0.125 | 0.094 | 0.065 | 1.33 | 1.93 |
| cbrt | 0.080 | 0.069 | 0.039 | 1.15 | 2.06 |

Tin runs the same algorithm as Go 1.2 to 1.8 times slower, and libm's tuned kernels are faster
still. `sqrt` shows the harness is fair. The first version of the port was 2 to 4 times slower than
Go (`exp` 0.214 s); the exact fast paths in `Frexp`, `Ldexp`, `Exp` and `Log` (reading and
replacing the exponent field instead of calling) took `exp` to 0.088 s without changing a single
result bit. What is left is the code generator's, and it is the same list as section 3: 64-bit
constants rebuilt with `movz`/`movk` (a 6-term polynomial has a dozen coefficients), no hoisting of
them out of the function, and small functions that Go inlines (`IsNaN`, `Copysign`, the helpers
called by `Pow` and `Atan2`) but Tin does not, because its inliner takes only single-statement
functions. These functions make a good benchmark for that work.

## 3c. Sorting (sift)

`sift.Sort` and `sift.SortFunc` are Go's pattern-defeating quicksort ported to Tin (the same algorithm, so
the order of equal elements matches Go's too). 2,000,000 elements, best of 3, Apple M3 Pro, one thread,
milliseconds:

| sort | Tin | Go | Tin/Go |
|---|---|---|---|
| `sift.Sort` on i64 (generic) | 233 | 182 | 1.28 |
| `sift.Ints` (the older i64-only code, hand-tuned) | 159 | 182 | 0.87 |
| `sift.Sort` on f64 | 267 | 228 | 1.17 |
| `sift.SortFunc` on 16-byte structs by key | 388 | 276 | 1.41 |

The generic code is slower than `Ints` for the same reason the math functions are slower than Go's:
comparisons that Go inlines are calls here (the comparator form), and Tin's inliner takes only
single-statement functions. `Ints` and `Strs` stay for programs that sort those and nothing else.

## 4. Compile times and binary sizes

The compiler (about 20k lines including `lib/std.tin`, all backends) builds itself in 0.07 s
(warm file cache; about 0.6 s cold).

| program | Tin | Go |
|---|---|---|
| hello world (macOS) | 35 KB | 2.5 MB |
| JSON API server (`examples/api.tin`, with a Router, vs net/http / fasthttp) | 91 KB (macOS), 132 KB (Linux ELF, mostly 64 KiB segment padding) | 8.2 MB / 8.1 MB |

Programs need no runtime besides libc (Linux) or libSystem (macOS); the math library is Tin, so libm is not linked.

## 5. Shape dispatch (static, monomorphized)

A call through a shape-constrained type parameter must cost what a hand-written call costs
(roadmap #141, "static dispatch by monomorphization"). `bench/dispatch/dispatch.tin` runs the
same work both ways (build an 8-byte buffer, copy three bytes through `Read`), 2,000,000
iterations per round, best of 5 rounds, on the arm64 development machine:

| form | ns/op (three runs) |
|---|---|
| through `Reader` (shape-constrained, monomorphized) | 10.72, 11.00, 10.67 |
| hand-written `drainBuf(b Buf)` | 10.52, 10.89, 10.85 |
| ratio | 1.019, 1.010, 0.983 |

The two functions' generated bodies are instruction-identical after normalizing labels:
`tinc -S` prints `_drainBuf` and `_Drain[Buf]` as the same instruction sequence. Across the
machines it has been run on, the ratio stays within a few percent (0.97 to 1.02), i.e. there
is no dispatch overhead. The committed check `tests/v2/shapes_dispatch_asm.tin` + `.check`
asserts the direct call (`bl _Buf.Read` on arm64, `call S<n>  # Buf.Read` on amd64) and that
no indirect call follows it in the listing, on every target in CI.

## 6. Dynamic shape dispatch

`bench/dispatch/dyn.tin` compares `Log(w dyn Writer, ...)` with a direct call to the same
concrete method. Each process runs five rounds of 2,000,000 iterations and reports its best
round; the table shows four process runs on the Apple M3 Pro development machine:

| measurement | process runs | median |
|---|---|---|
| dynamic call | 4.54, 4.77, 4.55, 4.89 ns/op | 4.66 ns/op |
| direct call | 2.93, 3.25, 2.97, 2.88 ns/op | 2.95 ns/op |
| dynamic/direct | 1.55, 1.47, 1.53, 1.70 | 1.54 |

The measured loop used zero pool bytes. `tests/v2/shapes_dyn_asm.tin` checks arm64 and
amd64 assembly for exactly one indirect call in the dynamic method and no allocator call.
These numbers describe this microbenchmark and machine; they are not a whole-program estimate.

## Ordered comparisons and conditional increments

`bench/v2/ordered_less` exercises the generic `sift.Less` comparison loop. A native Linux
comparison used seven alternating runs per side and reported medians on GitHub-hosted
`ubuntu-24.04` amd64 and `ubuntu-24.04-arm` runners (Go 1.26.8; load and server work stayed
on each runner). The comparison was from base `e3dbf8c` to head `d27e0b5`, which includes
the conditional-increment change. The [workflow run](https://github.com/yasserreslan/tin/actions/runs/37161195781)
contains the machine details and raw samples.

| architecture | base ms | head ms | head/base | head Tin ms | Go ms | Go/Tin |
|---|---:|---:|---:|---:|---:|---:|
| amd64 | 71.27 | 20.01 | 0.281 | 20.2 | 35.6 | 1.760 |
| arm64 | 39.58 | 30.41 | 0.768 | 30.4 | 32.8 | 1.079 |

Other CPU benchmarks stayed within 5% of base. HTTP stayed within the workflow's 5% review
threshold; the largest change was arm64 `/plaintext` at 0.958 head/base requests per second.

## Single-byte string appends

`append(b, s...)` on `[]u8` now emits a direct byte load/store when the appended string has
length one. Longer strings still use `memcpy`, and capacity growth still uses the existing
runtime path. The native Linux comparison used seven alternating CPU runs per side and five
alternating HTTP rounds on GitHub-hosted amd64 and arm64 runners (Go 1.26.8; the load generator
ran on the same machine). It compared base `7412ef6` (the then-current main plus conditional
increment work) with head `d88cef5` (the same code plus the append optimization). See [workflow
run 37163339932](https://github.com/yasserreslan/tin/actions/runs/37163339932) for raw samples,
HTTP logs and machine details.

| architecture | `strbuild` base ms | head ms | head/base time |
|---|---:|---:|---:|
| amd64 | 154.35 | 148.22 | 0.960 |
| arm64 | 150.69 | 151.42 | 1.005 |

The amd64 result is about 4% faster; arm64 showed no measurable change. Every other CPU
benchmark stayed within 5% of its base.

| architecture | path | base req/s | head req/s | head/base req/s |
|---|---|---:|---:|---:|
| amd64 | `/json` | 104705 | 105673 | 1.009 |
| amd64 | `/plaintext` | 100077 | 107729 | 1.076 |
| arm64 | `/json` | 177246 | 179926 | 1.015 |
| arm64 | `/plaintext` | 175889 | 178189 | 1.013 |
