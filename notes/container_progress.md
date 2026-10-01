# Container work: progress, verification state, how to resume

Stopped on request (2026-10-01 ~17:50). Everything below compiles with the current `bin/tinc`
(`examples/api.tin` builds for darwin and linux-arm64, last checked right before this note). No
containers or servers of mine are left running; image `tin-api:dev` still exists locally.

## Done and verified

| item | files | verification |
|---|---|---|
| Connection balancing across cores (Linux SO_REUSEPORT): per-core live-connection counters (`gLoad`, one cache line each), `accept_all` hands an fd to the least-loaded core through its handoff pipe when `load[me] > load[j]+1`, crediting `load[j]` at hand-off; `take_handoffs` registers without recounting | lib/anvil.tin | epoll registrations 27/27/28/26 (was 29/24/32/23). 7 rounds wrk -t4 -c100 -d5s /plaintext in tin-bench-arm64, TIN_CORES=4 vs `GOMAXPROCS=4 ./fast`: CPU-separated (server 0-3, wrk 4-7) medians anvil 883k req/s p99 423µs vs 866k / 990µs; shared CPUs medians 864k / 397µs vs 852k / 390µs (p99 parity, was 2x worse) |
| `hearth.Cores()` on Linux = min(sysconf online, popcount(sched_getaffinity), ceil(cgroup v2 cpu.max), v1 cfs quota/period), never 0 | lib/runtime_linux.tin (`rt_ncpus`, `rt_cpu_quota`, `rt_affinity_count`, `rt_read_file`, `rt_num_at`, `rt_read_num`) | bin/agentA/coresprobe.tin in tin-debian-arm64: unlimited 11, `--cpus=1.5` 2, `--cpuset-cpus=0,1` 2, both 2 |
| Core pinning: `rt_pin_setup(n)` (called by `hearth.Run`) pins only when n == allowed CPUs or TIN_PIN=1 with n ≤ allowed; `rt_core_qos(id)` → `sched_setaffinity` to the id-th allowed CPU | lib/runtime_linux.tin, lib/hearth.tin | probe shows cores on CPUs 0..n-1 when pinned; unpinned with `--cpus=1.5` (2 of 11); never pins when TIN_CORES > allowed |
| Memory limit: `rt_mem_limit()` (v2 memory.max / v1 memory.limit_in_bytes), `hearth.MemLimit()`, `hearth.PoolChunk()`, `pool_tune(n)` sets `rtPoolChunk` when n × 4 MiB > limit/4 | lib/runtime_linux.tin, lib/runtime_darwin.tin, lib/hearth.tin | `--memory=64m` → memlimit 67108864, poolchunk 1507328 |
| Graceful SIGTERM/SIGINT: signals blocked in all threads (`rt_sig_block_term` in ServeN), core 0 takes them via signalfd (Linux) / kqueue EVFILT_SIGNAL (macOS), `-1` on each handoff pipe starts draining (listener closed, in-flight served, `Connection: close` afterwards), exit 0 when every core's count is 0 or at the TIN_GRACE deadline (monotonic, default 25 s), second signal exits at once | lib/anvil.tin, lib/anvil_darwin.tin, lib/anvil_linux.tin, lib/runtime_*.tin | tests/graceful/graceful.go: 14 checks pass on macOS (`go run tests/graceful/graceful.go bin/api 9381`) and on Linux (cross-built, in tin-debian-arm64) |
| k8s example: Dockerfile, deployment.yaml (limits cpu 2 / 256Mi, probes on /healthz, grace 30 s, preStop sleep 3, Service), README; `/healthz` route in examples/api.tin | examples/k8s/*, examples/api.tin | `docker build -f examples/k8s/Dockerfile -t tin-api:dev .`; run `--cpus=2 --memory=256m`: /json, /healthz 200 ok, uid 10001, 2 core threads; `docker stop` ≤ 1 s, exit code 0 |
| Test suites | tests/v2/hearth.tin + .out | macOS `tools/v2test.sh` → "v2 tests pass"; Linux `tools/linuxtest.sh` → 30 ok / 0 fail; conformance 26/26 on macOS and in tin-bench-arm64 |

## Unverified / open

- **lib/runtime.tin patch not applied** (I may not edit it): `rtPoolChunk` is computed but the
  allocator still uses the `chunkSize` constant. Exact edits in `notes/patch_runtime_memlimit.md`.
  After applying: `make -s bin/tinc && tools/v2test.sh`, then rerun the `--memory=64m` probe below and
  check that a 1 MiB allocation per core still works.
- Conformance in `tin-debian-arm64` reports `rss-flat-2M` FAIL with rss -1: that image has no `ps`;
  the same binary passes 26/26 in `tin-bench-arm64`. Not a server problem.
- Balancing p99 on shared CPUs is at parity, not a win (397 vs 390 µs median); with CPU separation
  anvil wins (423 vs 990 µs). Not re-benchmarked after the graceful-shutdown edits (only the
  balancing edit was in during the benchmark; the shutdown code adds one `ev_signal` test per event).
- Draining keeps idle keep-alive connections until they send a request or TIN_GRACE expires (as
  specified). Not tested with wrk-style clients holding hundreds of idle connections.
- `lib/anvil_linux.tin` hardcodes `evSize = 16` (arm64 `epoll_event`); linux-amd64 needs 12 / data@4.
- The k8s manifests were not applied to a real cluster (no cluster here); only the image was run.

## Resume

```sh
cd /Users/yasserreslan/Desktop/tin
make -s bin/tinc
TIN_ROOT=$PWD bin/tinc -o bin/api examples/api.tin
TIN_ROOT=$PWD bin/tinc -target linux-arm64 -o bin/linux/api examples/api.tin

# Balancing re-bench (needs bin/linux/fast; scripts already in bin/linux):
docker run -d --name tin-agentA-bench -v "$PWD/bin/linux":/w -w /w tin-bench-arm64 sleep infinity
docker exec tin-agentA-bench sh /w/agentA_bench.sh     # epoll registrations per core + 5 rounds
docker exec tin-agentA-bench sh /w/agentA_bench2.sh    # 7 rounds, taskset server 0-3 / wrk 4-7
docker exec tin-agentA-bench sh /w/agentA_bench3.sh    # 7 rounds, shared CPUs
docker rm -f tin-agentA-bench

# Cores / memory / pinning probe:
TIN_ROOT=$PWD bin/tinc -target linux-arm64 -o bin/linux/coresprobe bin/agentA/coresprobe.tin
for f in "" --cpus=1.5 --cpuset-cpus=0,1 --memory=64m "-e TIN_PIN=1 --cpus=3"; do
  docker run --rm $f -v "$PWD/bin/linux":/w tin-debian-arm64 sh -c '/w/coresprobe | sort'; done

# Graceful shutdown harness:
go run tests/graceful/graceful.go bin/api 9381
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o bin/linux/graceful tests/graceful/graceful.go
docker run --rm -v "$PWD/bin/linux":/w tin-debian-arm64 /w/graceful /w/api 9381

# Conformance (macOS; the 5000-conns case can be flaky from the 128 backlog: rerun once):
TIN_CORES=4 bin/api & bin/conformance -addr 127.0.0.1:9180 -pid $!; kill $!
# Conformance (Linux, use the bench image: it has ps for the rss cases):
docker run --rm -v "$PWD/bin/linux":/w -w /w tin-bench-arm64 sh -c 'TIN_CORES=4 ./api & sleep 0.5; ./conformance -addr 127.0.0.1:9180 -pid $!'

# Dockerfile / k8s check:
docker build -f examples/k8s/Dockerfile -t tin-api:dev .
docker run -d --name tin-api --cpus=2 --memory=256m -p 8080:8080 tin-api:dev
curl -s localhost:8080/json; curl -s localhost:8080/healthz
docker stop tin-api; docker inspect --format '{{.State.ExitCode}}' tin-api; docker rm tin-api
# then: kind load docker-image tin-api:dev && kubectl apply -f examples/k8s/deployment.yaml

# Full suites:
tools/v2test.sh && tools/linuxtest.sh
```
