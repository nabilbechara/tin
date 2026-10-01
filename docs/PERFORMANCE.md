# Performance

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

## 4. Compile times and binary sizes

The compiler (about 20k lines including `lib/std.tin`, all backends) builds itself in 0.07 s
(warm file cache; about 0.6 s cold).

| program | Tin | Go |
|---|---|---|
| hello world (macOS) | 35 KB | 2.5 MB |
| JSON API server (`examples/api.tin` vs net/http / fasthttp) | 54 KB (macOS), 132 KB (Linux ELF, mostly 64 KiB segment padding) | 8.2 MB / 8.1 MB |

Programs need no runtime besides libc and libm.
