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
  net/http) on `ubuntu-24.04` (x86-64) and `ubuntu-24.04-arm` every week and on demand (it
  does not run on pull requests), and writes the tables to the job summary. The same
  job compares the selected revision with a base revision, each built
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

## v0.4 service benchmark (Linux)

`GET /users/{id}` through Redis over MySQL, Tin (`bench/v04/users.tin`) against Go + chi,
go-redis and go-sql-driver/mysql (`bench/v04/go`), under wrk2 (`bench/v04/run.py`, workflow
`.github/workflows/bench.yml`). Three scenarios over random ids 1..10000: **cached** (every
read hits Redis), **db** (`/db/users/{id}`, a MySQL prepared statement per request) and
**mixed** (cached reads with 0.5% `/slow` requests that answer after 50 ms). Each runs at an
open-ended rate (maximum throughput, and requests per CPU-second of server time) and at a
fixed rate of 70% of the slower server's maximum for the latency percentiles (wrk2 corrects
for coordinated omission).

**Machine:** GitHub-hosted `ubuntu-24.04` runner (image 20260927.320.1), AMD EPYC 7763,
4 vCPUs (2 cores × 2 threads) under Hyper-V, Linux 6.17.0-1022-azure x86_64, Go 1.26.8,
Redis 7.2.16, MySQL 8.0.46 (service containers), wrk2 giltene/wrk2@44a94c1, Tin 6e138af.
**Placement:** each server has 2 cores (`TIN_CORES=2`, `GOMAXPROCS=2`) pinned to CPUs 0–1;
wrk2 (2 threads, 128 connections), Redis and MySQL share CPUs 2–3. Each run is 20 s after a
3 s warm-up; rounds alternate the servers, and Redis is emptied before every run so each run
warms its own cache. The table is the median of 5 rounds,
[workflow run 37210593145](https://github.com/yasserreslan/tin/actions/runs/37210593145).

This is a shared runner, so **the ratios are the result**; absolute numbers vary between
runs. Tin/Go ratios of the medians (throughput above 1 and latency below 1 favour Tin):

| scenario | max req/s | req per CPU-s | p50 | p99 | p99.9 |
|---|---:|---:|---:|---:|---:|
| cached | **3.72** | **3.60** | 0.77 | 0.56 | 0.34 |
| db | **1.23** | **1.75** | 1.21 | 1.30 | 0.89 |
| mixed | **3.56** | **3.56** | 0.79 | 0.99 | 0.99 |

An earlier run of the same workflow (run
[37209296644](https://github.com/yasserreslan/tin/actions/runs/37209296644), 3 rounds,
before Redis was emptied per run) gave 3.93 / 1.19 / 3.75 for max req/s and 3.74 / 1.72 /
3.62 for req per CPU-s: the throughput ratios hold within a few percent between runs.

Medians of this run, for scale only:

| scenario | server | max req/s | req per CPU-s | fixed req/s | p50 ms | p99 ms | p99.9 ms | RSS MB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cached | Tin | 81,864 | 54,576 | 15,392 | 1.27 | 2.42 | 2.92 | 50 |
| cached | Go + chi | 21,989 | 15,165 | 15,392 | 1.64 | 4.34 | 8.57 | 25 |
| db | Tin | 17,157 | 21,446 | 9,773 | 1.98 | 5.45 | 6.51 | 28 |
| db | Go + chi | 13,962 | 12,230 | 9,773 | 1.63 | 4.20 | 7.29 | 22 |
| mixed | Tin | 78,636 | 54,187 | 15,444 | 1.23 | 42.43 | 52.06 | 48 |
| mixed | Go + chi | 22,063 | 15,216 | 15,444 | 1.56 | 43.01 | 52.38 | 26 |

What the numbers say:

- **Cached reads:** Tin serves 3.7× the requests and 3.6× the requests per CPU-second, with
  lower latency at every percentile. A core's requests share one Redis connection and their
  commands go out together (`lib/redis`), where go-redis takes a pooled connection per
  command. Tin's fixed-rate p99 was 2.41–2.45 ms in all 5 rounds.
- **Database reads:** Tin's throughput lead is smaller (1.2×, 1.75× per CPU-second) because
  MySQL does most of the work. Latency at the fixed rate is not a clear win either way: Tin's
  p99 per round was 3.17–6.05 ms against Go's 4.10–7.53 ms, with the medians 5.45 against
  4.20 here and 3.30 against 7.95 in the earlier run.
- **Mixed:** the p99 (about 42 ms) and p99.9 (about 52 ms) are the same for both servers.
  This is head-of-line blocking in the client, not the server: wrk2 sends one request at a
  time per HTTP/1.1 connection, so the requests scheduled behind a 50 ms `/slow` on its
  connection wait for it. At about 120 requests per second per connection, each `/slow`
  delays about 6 of them, roughly 3% of all requests, which puts p99 inside that wait. The
  servers themselves are not blocked: Tin's maximum throughput with `/slow` mixed in is 96%
  of its cached-only rate (78.6k against 81.9k req/s), since a waiting request does not
  hold up its core.
- **Memory:** Tin's RSS is higher here (48–50 MB against 25–26 MB in the Redis scenarios,
  28 against 22 MB for db; not broken down in this run), so memory is a trade-off in this
  benchmark, not a win.

**Tin's fixed-rate p99** (about 10 ms in the first noisy trial on a loaded Mac, issue #74)
is not a problem in the Redis client's hand-off between waiting requests: on the runner it
is 2.4 ms in every round. Two artifacts of the harness made the tails jump, for either
server: all cached keys came from one warm-up with a 60 s TTL and expired together in the
middle of a later run (a burst of MySQL reads), and the default Redis configuration forked
a snapshot every minute. In run 37209296644, before the fix, Go had single rounds at 109 ms
and 145 ms p99. `run.py` now empties Redis before every run and turns snapshots off. A
route that does not touch Redis showed the same occasional spikes as `/users/{id}` in a
side-by-side test on a shared VM, and Redis added about 1.5 ms at p99, its round trip.

Run it yourself: Actions, Benchmark v0.4, Run workflow (inputs: rounds, seconds per run).
Locally, `bench/v04/run.py` needs Redis, MySQL seeded by `bench/v04/seed.py` and a wrk2
binary; `SERVER_CPUS` / `WRK_CPUS` pin the servers and wrk2 to separate CPUs.

## Measurement setup of the existing numbers (macOS development machine)

Measured on an Apple M3 Pro (5 performance + 6 efficiency cores), Go 1.26, fasthttp
1.74, wrk 4.2 (4.1 inside Linux containers), the load generator always on the same
machine as the server. Linux numbers come from an arm64 Debian container under Docker
Desktop, running natively. Scripts: TOOLING.md §7.

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

### Signed division by ten (native Linux amd64)

The dedicated `div10q` and `rem10` benchmarks isolate signed `/ 10` and `% 10` in a
100-million-iteration loop. On the shared GitHub runner (Intel Xeon Platinum 8370C,
Go 1.26.8),
the head uses multiply-high lowering while the base uses hardware division:

| operation | base Tin ms | head Tin ms | Go ms | head/base | head Tin/Go |
|---|---:|---:|---:|---:|---:|
| signed `i64 / 10` | 288.89 | 94.01 | 93.6 | 0.325 | 1.00 |
| signed `i64 % 10` | 288.95 | 118.62 | 120.8 | 0.411 | 0.98 |

The benchmark harness checks output on every timed run. The full CPU suite stayed within
the 5% review threshold. HTTP throughput was 2.6% above base for `/json` and 2.2% below
base for `/plaintext`; arm64 is unchanged by this x64-only lowering.

### Cached slice-length bounds checks (native Linux)

The checker proves indexed accesses safe in counter loops bounded by a stable local
length alias. It invalidates the proof when the slice or cached length is rebound, a
mutating call can change the header, or an escaping callback can change a captured slice.
The paired benchmarks produced identical output on every run.

Measurements use the shared GitHub runners (Intel Xeon Platinum 8573C and Neoverse-N2,
4 CPUs each, Go 1.26.8), with seven alternating runs per revision:

| arch | benchmark | base Tin ms | head Tin ms | Go ms | head/base | head Tin/Go |
|---|---|---:|---:|---:|---:|---:|
| amd64 | `indexsum` | 37.04 | 36.50 | 37.8 | 0.986 | 0.966 |
| arm64 | `indexsum` | 40.11 | 38.61 | 59.0 | 0.963 | 0.654 |
| amd64 | `nbody` | 4443.14 | 4366.67 | 4444.3 | 0.983 | 0.983 |
| arm64 | `nbody` | 3701.77 | 3571.38 | 3457.4 | 0.965 | 1.033 |

All other CPU cases and both HTTP routes stayed within the 5% review threshold on both
architectures. HTTP head/base throughput ratios were 1.011 (`/json`) and 1.001
(`/plaintext`) on amd64, and 0.987 and 0.969 on arm64.

## 3. Where Go still wins, and why

From `notes/bench_v2.md`, which has the assembly analysis:
- **fannkuch, n-body:**
  - whole-function register allocation runs out of registers in large loops, so some
    loop variables live in stack slots;
  - stores through one struct invalidate loads of another (no alias analysis), so
    fields are reloaded;
  - bounds checks that require range or alias facts beyond a stable local length alias,
    such as masked or modular indexes.
- **string building:** single-byte string appends now have a direct byte path (see
  [Single-byte string appends](#single-byte-string-appends)); signed `/10` and `%10` use
  multiply-high on x64, while the arm64 backend and other divisors still use hardware
  division.
- **Constant materialization:** 64-bit constants are rebuilt with movz/movk inside
  loops.

Planned codegen work in order of payoff: a register allocator with loop-depth spill
weights, range analysis for masked and modular indexes, generalized division by
constants via multiply-high, hoisting constant materialization, and alias information
for struct fields.

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

The compiler (about 35k lines, all backends) builds itself in 0.07 s
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

## x64 floating-point register homes

The x64 generator keeps local floating-point values in XMM8–XMM14 when the function has
no calls inside loops. If it calls a helper outside loops, it saves and restores those
homes around the call using the existing aligned spill slots. Functions with calls in
loops retain the previous allocation strategy.

The native Linux comparison used seven alternating CPU runs per side and five alternating
HTTP rounds on GitHub-hosted shared runners: four vCPUs, AMD EPYC 7763 on amd64 and
Neoverse-N2 on arm64, Go 1.26.8, with the load generator on the same runner. Run
[37168100638](https://github.com/yasserreslan/tin/actions/runs/37168100638) produced an
arm64 JSON CPU outlier; the rerun
[37169504458](https://github.com/yasserreslan/tin/actions/runs/37169504458) did not reproduce
it. A later run
[37170940420](https://github.com/yasserreslan/tin/actions/runs/37170940420) measured a
separate Intel amd64 attempt. Raw samples, machine details and HTTP logs are attached to
these runs.

| runner | `mandelbrot` base ms | head ms | head/base | head Tin ms | Go ms | Go/Tin |
|---|---:|---:|---:|---:|---:|---:|
| AMD EPYC 7763, run 1 | 3196.80 | 1555.19 | 0.486 | 1555.1 | 1148.6 | 0.739 |
| AMD EPYC 7763, rerun | 3196.80 | 1554.77 | 0.486 | 1554.5 | 1148.5 | 0.739 |
| Intel Xeon Platinum 8573C | 2285.67 | 3568.24 | 1.561 | — | — | — |
| Neoverse-N2 control | 942.74 | 942.73 | 1.000 | 943.2 | 931.7 | 0.988 |

The x64 change cuts the amd64 `mandelbrot` time by about 51%, consistently across both
runs on AMD EPYC 7763. Tin remains about 1.35× slower than Go on that workload. A separate
amd64 attempt on Intel Xeon Platinum 8573C measured a 56% regression; its seven samples per
side clustered tightly, while the second attempt ran on AMD rather than Intel. Other CPU
benchmarks stayed within 5% of base. Arm64 has no corresponding code-generation change:
JSON measured 1.064 head/base in the first run and 0.935 in the rerun, opposite movements
consistent with shared-runner timing noise; the other arm64 CPU results stayed within 5%.

| architecture | `/json` run 1 | `/json` rerun | `/plaintext` run 1 | `/plaintext` rerun |
|---|---:|---:|---:|---:|
| amd64 head/base req/s | 0.977 | 0.951 | 0.963 | 1.049 |
| arm64 head/base req/s | 0.991 | 0.993 | 0.984 | 1.023 |

All HTTP results stayed within the 5% review threshold. The amd64 `/json` rerun is near
the threshold at 0.951. The separate `strbuild` reference still has Tin at 148.5 ms versus
Go at 87.2 ms (Go/Tin 0.587); reducing the remaining constant-modulo cost is a follow-up
optimization target.

## CPU cancellation safepoints

Safepoints are on by default in a program that starts cores, in its own code only (#341);
the standard library and programs without cores (the CPU benchmarks below) have none, so
their cost there is zero. `--nopolls` turns them off, `--polls` puts them everywhere outside
`lib/runtime/`, and a function opts out with `@nopoll`. The cost below is for polls in every
loop (the `--polls` form): a tight loop in a handler pays it; anvil and the rest of `lib/` do not.

The default form was measured in [run 37340338604](https://github.com/yasserreslan/tin/actions/runs/37340338604)
(#341, head against main on the same runners, Linux 6.17.0-1022-azure, AMD EPYC and
Neoverse-N2). HTTP head/base throughput of the anvil server programs, which now poll in
their own code, was 1.012 (`/json`) and 1.003 (`/plaintext`) on amd64 and 0.994 and 0.996 on
arm64; the CPU benchmarks, which start no cores, stayed between 0.982 and 1.018.

The initial [native Linux run](https://github.com/yasserreslan/tin/actions/runs/37197260096)
compared base `b6333ef` with head `9759a6b`, with polls enabled in strict Tin code.
Both runners had four vCPUs, Linux 6.17.0-1022-azure and Go 1.26.8: Neoverse-N2
on arm64 and AMD EPYC 9V74 on amd64.
CPU measurements are medians of seven alternating runs per side. HTTP uses one server
core, wrk on the same runner (`-t2 -c100`, 10 seconds), and medians of five alternating rounds.
Only ratios on these shared runners are meaningful.

| architecture, workload | base ms | polls ms | polls/base time |
|---|---:|---:|---:|
| arm64 indexsum | 38.52 | 42.13 | 1.094 |
| arm64 ordered_less | 30.20 | 32.73 | 1.084 |
| arm64 sieve | 496.22 | 583.00 | 1.175 |
| amd64 indexsum | 35.43 | 57.39 | 1.620 |

HTTP head/base throughput was 0.985 for `/json` and 0.962 for `/plaintext` on arm64,
and 0.952 and 1.028 respectively on amd64.
Output equality is checked on every timed repetition.

The watchdog reads an array of core contexts every millisecond and writes only their
poll words. The ordinary poll is a context load and a cold branch (x86-64 also tests the
loaded word). Cold stubs preserve registers, including leaf-function homes. The compiler
keeps existing allocation and register-home decisions; the poll check stays inside loops.
The watchdog is started only for an opted-in executable.

## Integer overflow checks (Linux)

`+`, `-`, `*`, negation, signed `/`, shifts and float to integer conversions are checked in
user code and library packages (#362; `lib/runtime/` and the compiler are not). Each check is a
flag test and a branch to a cold stub. The compiler drops the checks it can prove cannot fire
(loop counters, and after inlining, constants, lengths, narrow types and locals defined once),
and the crypto kernels are `@wrap`.

[Run 37350166526](https://github.com/yasserreslan/tin/actions/runs/37350166526) measured head
`1d07ed3` against main `c0145f2` on the same runners: Linux 6.17.0-1022-azure, AMD EPYC 9V45 on
amd64, Neoverse-V3 on arm64, Go 1.26.8. CPU figures are medians of seven alternating runs per
side; HTTP uses one server core and wrk `-t2 -c100` on the same runner. Only ratios on these
shared runners are meaningful.

| architecture, workload | main ms | checked ms | checked/main time |
|---|---:|---:|---:|
| arm64 spectral | 889.20 | 1201.88 | 1.352 |
| arm64 ordered_less | 25.48 | 27.35 | 1.074 |
| arm64 indexsum | 33.30 | 35.31 | 1.060 |
| arm64 json | 1294.42 | 1344.69 | 1.039 |
| arm64 sieve | 367.14 | 380.61 | 1.037 |
| amd64 sha512 | 310.23 | 322.68 | 1.040 |
| amd64 spectral | 6162.75 | 6138.30 | 0.996 |

The other 41 benchmark and architecture pairs were within 3.5% (0.978 to 1.034). HTTP
checked/main throughput was 0.997 (`/json`) and 0.994 (`/plaintext`) on amd64, and 0.979
and 0.994 on arm64. Output equality is checked on every timed repetition.

spectral is the one real cost. Its inner loop computes `(i+j)*(i+j+1)`, where `i` and `j` are
bounded only by a slice length, so the multiply keeps its check. On arm64 that is an `smulh`
and a compare in a loop of 0.73 ns an iteration. On x86-64 `imul` sets the overflow flag
itself, so the check is free there. A program that has measured such a loop can write `*%`
in it.

Before the elision pass and `@wrap` on the crypto kernels, the same comparison
([run 37344878578](https://github.com/yasserreslan/tin/actions/runs/37344878578), main
`8b4e916`) cost 1.58 on arm64 x25519, 1.52 on tls13keys and 1.22 on p256ecdh. Those three are
now 1.000, 1.002 and 1.006. Two probes with the checks off measure noise. All changes with the
checks off ([run 37344888270](https://github.com/yasserreslan/tin/actions/runs/37344888270)) was
within 3% on arm64. The same with 12 bytes of padding after `main`
([run 37350044953](https://github.com/yasserreslan/tin/actions/runs/37350044953)) moved
memory_16 by 1.197 on arm64 and aesgcm by 1.113 on amd64. A ratio of a few percent on one
benchmark can be code placement.

## Long-lived blocks above 4 KiB (Linux)

The ingot heap served only blocks up to 4 KiB from slabs: a bigger kept value had a
page-rounded mapping of its own, unmapped when dropped (#345). The classes now continue to
256 KiB about 25% apart, and the mappings of blocks up to 4 MiB are kept for reuse.

`tools/ci/heap_check.py` (fixture `blocks.tin`) runs on every CI build. From the run of
2026-10-05 on GitHub-hosted runners (run 37315794425), after the change:

| workload | ubuntu-24.04 (x86-64) | ubuntu-24.04-arm |
|---|---:|---:|
| 100000 keeps + overwrites of one 5000-byte value | 2257 ms, 3 mappings | 1213 ms, 3 mappings |
| 60000 distinct 5000-byte values kept: resident | 299 MiB | 299 MiB |
| the same after deleting every other one: lines in /proc/self/maps | 10 | 9 |
| the same, kept again: resident | 308 MiB | 308 MiB |
| 20000 times a 300000-byte block made and dropped | 352 ms, 6 mappings | 242 ms, 6 mappings |

The first row includes building the 5000-byte value in request memory each time, which is most
of its time. For comparison, the issue (#345, a Linux arm64 probe of 2026-10-04 before the
change) recorded 490 MB for the 60000 values and 30018 mappings after deleting half of them,
and 1141 ms for 200000 keeps and overwrites of one 5 KB value. The 5000-byte values take 5120
bytes of a slab each instead of a page-rounded 8192, and the memory of deleted values is
reused instead of unmapped. These are not same-machine before and after figures: run
`.github/workflows/bench-linux.yml` for those.

## File reads through io_uring (Linux)

`quarry.ReadFile` in a request task goes through the core's own io_uring ring on Linux (#357);
the helper threads are the fallback (`TIN_IO_URING=0`, kernels or seccomp profiles that refuse
io_uring, FIFOs and network mounts). `bench/files` reads 10000 files of 4 KiB, 1000 per request
over 4 connections per core, in 5 alternating rounds of 3 s per side; the table gives medians.
[Run 37350232975](https://github.com/yasserreslan/tin/actions/runs/37350232975), GitHub's
4-vCPU runners (Linux 6.17.0-1022-azure, AMD EPYC 9V74 and Neoverse-N2); only ratios mean anything there.

| cores | amd64 helper files/s | amd64 io_uring files/s | io_uring/helper | arm64 helper files/s | arm64 io_uring files/s | io_uring/helper |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 158401 | 101909 | 0.64x | 181622 | 161346 | 0.89x |
| 2 | 185771 | 195836 | 1.05x | 275430 | 292280 | 1.06x |
| 4 | 76655 | 317049 | 4.14x | 136593 | 559164 | 4.09x |
| 8 | 165514 | 303163 | 1.83x | 265550 | 550220 | 2.07x |

- Scaling from one core to four: io_uring 3.11x (amd64) and 3.47x (arm64); the helper threads
  0.48x and 0.75x, as every core queues on the same few threads. Eight cores on four vCPUs add
  nothing to either.
- CPU per 1000 files: io_uring 9.8 to 12.8 ms (amd64) and 6.2 to 7.0 ms (arm64), about half
  of the helper path's 17.1 to 23.6 and 11.8 to 14.5 ms.
- On one core io_uring is slower (0.64x, 0.89x): the helper path then runs the reads on other
  CPUs in parallel with the core, which a 4-vCPU runner has to spare. Serving cores take
  those CPUs away, so the multi-core rows are the production case.

## Map growth without stalls (Linux)

A map rebuilt its entries and index when full, so inserting into a map of 2^21 entries stalled
the core (the issue, #346, recorded 94 ms on Linux arm64 before the change). Past 4096 entries
a map now keeps its entries in chunks and moves its index into a bigger one 16 entries per
set or delete. `tools/ci/map_growth_check.py` (fixture `mapgrow.tin`) bounds the slowest
insert of 4 million integer keys and of a million str keys to under a millisecond (best of
five runs: one descheduled thread can make a single run slower). From the same CI run, after
the change:

| workload | ubuntu-24.04 (x86-64) | ubuntu-24.04-arm |
|---|---:|---:|
| 4000000 integer keys: slowest insert (best of 5 runs) | 232 us | 282 us |
| the same: total time for the inserts, then for 4000000 lookups | 1037 ms, 522 ms | 1213 ms, 601 ms |
| 1000000 str keys: slowest insert (best of 5 runs) | 185 us | 278 us |

Lookups in a big map read an entry through a chunk directory; their cost against the old flat
layout has not been measured on Linux, so no claim is made about it.
