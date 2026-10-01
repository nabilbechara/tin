# Resume here (paused 2026-10-01 17:50 Beirut)

## State
- darwin-arm64: complete. linux-arm64 phase 1: all features in, gate met (see below), final
  re-verification pending. linux-amd64 phase 2: milestone 1 (legacy hello runs in the amd64
  container); strict programs, runtime, tests and self-hosting still to do.
- Docs complete in docs/ (index docs/README.md). One placeholder: COMPILE_TIME in
  docs/PERFORMANCE.md §4.

## Phase 1 results (agent A, verified in tin-bench-arm64)
- Accept-time balancing (lib/anvil.tin: gLoad per-core counters, handoff when load > min+1):
  4 cores, 100 conns spread 27/27/28/26.
- 4-core /plaintext vs fasthttp, 7 rounds: server and wrk on separate CPUs: anvil 883k req/s,
  p99 423 µs vs 866k, 990 µs. Shared CPUs: 864k / 397 µs vs 852k / 390 µs (p99 parity).
- hearth.Cores() follows cpuset + cgroup quota, pinning when 1:1 or TIN_PIN=1; MemLimit and
  PoolChunk; graceful SIGTERM/SIGINT (tests/graceful/graceful.go, 5 cases pass on both OSes);
  examples/k8s/ (Dockerfile, deployment.yaml, README); tests/v2/hearth.tin.
- Agent A reported: v2 tests pass, linuxtest 30/30, conformance 26/26 on both.

## To do, in order
1. Apply notes/patch_runtime_memlimit.md to lib/runtime.tin (rt_chunk(), so the pool chunk
   really shrinks under a memory limit). Without it PoolChunk is reported but not used.
2. Re-verify everything (also covers the strict division-by-zero panic added in gen.tin):
   `make bootstrap && make seed && tools/v2test.sh && make test && make linux-bootstrap && tools/linuxtest.sh`
   then conformance (TOOLING.md §5) and `go run tests/graceful/graceful.go bin/api 9381`.
3. Fill COMPILE_TIME in docs/PERFORMANCE.md (`time bin/tinc -o /tmp/x $(make -s print-SELF)`);
   update docs/RUNTIME.md §9 "In progress" (balancing and SIGTERM are done) and the 4-core
   rows in docs/PERFORMANCE.md and README.md with the numbers above; `python3 tools/gendoc.py`.
4. Phase 2 (x86-64): resume from notes/x64_progress.md. Reached: legacy tests 13/13, strict
   tests 27/31 in tin-debian-amd64, and the compiler self-hosts there (byte-identical, 587 KB).
   Open items:
   - apply notes/patch_x64_runtime.md (per-arch rt_stat_mode and epoll_event layout,
     runtime_linux_arm64.tin / anvil_linux_arm64.tin, TARGET_X64): amd64 strict builds fail with
     duplicate definitions until it is in; then notes/patch_x64_seal.md;
   - failing: cairn and lever segfault, quarry one wrong value; all suspect the 7+-argument
     (stack argument) call path; a gdb image recipe is in the progress note;
   - mirror the strict division-by-zero panic in gen_x64.tin (x_divide; edit written in the note);
   - the agent saw "strlen redeclared" on one darwin strict build (lib/quarry.tin and
     lib/runtime.tin both declare extern strlen); tools/v2test.sh passed afterwards, so check
     whether it only happens on some path;
   - seal SHA-NI later. The benchmark gate needs real x86-64 hardware.
5. v0.4 async I/O: design in notes/design_v04.md waits for the user's review.

## Rules still in force
No git yet (ready: `git init && git add -A`). Port 8080 belongs to the user's other program.
At most 2 agents. Downloads need the user's OK.
