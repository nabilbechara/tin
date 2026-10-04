# Continuous integration and regression policy

Every push to `main` and every pull request runs native Linux arm64 (`ubuntu-24.04-arm`), Linux x86-64 (`ubuntu-24.04`) and macOS arm64 (`macos-15`) checks. Merge groups and manual runs use the same workflow. The final **CI** check succeeds only when every native job and the issue-policy job succeed; skipped, cancelled and failed dependencies cannot produce a green gate. Main requires this GitHub Actions check and an up-to-date PR branch, including for administrators.

## What is tested

- Clean build from the committed seed and two byte-identical self-hosted compiler rebuilds.
- Every `tests/v2/*.tin`, including negative compilation tests and their exact diagnostics. Missing expected output, compiler crashes, process crashes, nonzero exit and timeouts fail. Each run uses fresh executable paths. `tests/v2/*_asm.tin` files are compiled with `-S` instead and their listing matched against the ordered `CHECK:`/`CHECK-NOT:` lines in `*_asm.check` (the CPU's section), so a codegen change that loses a direct call, or turns it into an indirect one, fails.
- Exact number conversion: a generated Go `strconv`/`fmt` corpus and pinned parse-number-fxx hard cases check float bits, faults, ties, subnormals, long inputs, precision and f32/format flags on all three native targets (`number_check.py`).
- Memory primitives (`memory_check.py`): Go twins check every alignment, overlap, zeroing, reallocation, guard-page boundaries and 1000 cross-core returns. Deterministic failure injection checks 46 allocation/mapping failures, including startup and later allocations (#178).
- Task memory (`task_memory_check.py`): 300 concurrent heavy requests dirty pool and deep stack pages; after release, the cache holds at most 64 tasks and Linux RSS returns to within 32 MiB of baseline (#177). macOS checks task reuse and cache invariants.
- Remaining helpers (`helpers_check.py`): exact errno messages, 2010 UTC/calendar values against Go and the former C output, hostname, PTYs/pipes/files, Linux affinity/page size and linker-symbol boundaries. `compiler_paths_check.py` checks copied installations, spaces/Unicode, symlink traversal and missing paths against Go/C.
- Linux DNS (`dns_check.py`): fake UDP/TCP servers check hosts precedence, A/AAAA and IPv6 sockets, CNAMEs, malformed compression, wrong IDs, truncation/TCP fragments, NXDOMAIN, search/ndots, rotation/retries/timeouts, concurrent request deadlines and memory stability over 1000 lookups.
- Memory regressions: bounds panics, allocation size overflow and negative lengths, large first allocations, single evaluation of allocation lengths, read-only and region checking through indirect calls, nested zero values, deep `keep` ownership and 200 request-pool reset/reuse cycles.
- Linux HTTP framing/conformance, stable RSS over two million requests after warmup, and graceful shutdown. Throughput is reported, never used as a performance threshold.
- Linux syscall ABI (`syscall_check.py`): kernel errors, mappings, poll, stat fields, 5004 long/linked directory entries with refills and forced unknown types, returning signal handlers on an alternate stack, independent core errors, and ELF assertions excluding libc syscall imports.
- Request tasks (`task_check.py`): waits on one core overlap, fast requests stay fast behind waiting ones (timers, proxied `wire` calls, helper-thread file I/O), deadlines give 504, refused upstreams 502, and pipelined responses keep their order.
- Router (`router_check.py`, server `tools/ci/fixtures/router.tin`): on one core and on two, 1200 keep-alive requests interleave routes whose middleware and handlers wait, and every answer must carry its own path parameter and middleware trace; waits in a routed handler or middleware overlap; 404, 405 with `Allow`, HEAD, bodies, a catch-all and pipelined order go through the router; and 20 WebSocket connections are accepted by a routed handler. The router's matching rules and errors are in `tests/v2/router.tin` and `router*_bad.tin`.
- Runtime lifetimes (`lifetime_check.py`): overlapping formatting on one core, deadlines for running and queued helper jobs, safe late read/write completion after task reuse, per-message WebSocket pool bounds, fragmented/control traffic, retained `Read` results, and automatic buffer cleanup after 300 connection cycles. Private probes are injected into temporary library copies.
- Boundary cancellation (`cancel_check.py`, Tin 1 #231): a cancel wakes a task parked in each client (`tide`, `wire`, `redis`, `mysql` including a pool wait, `postgres`, `websocket`, a helper-thread file read) within milliseconds with `canceled: <reason>`; cancelling one request or a block inside it never reaches a sibling or the parent; a block's earlier deadline gives `deadline exceeded`; requests past `TIN_REQUEST_MEMORY` get 500 while the server keeps serving; at the end of the grace period after SIGTERM, waiting requests end with `canceled: draining` and the process exits 0.
- Clients and protocols, each against a small server written in Python inside the check, so no service has to be installed: `redis_check.py` (concurrent load, command batching, deadlines that keep replies in step, reconnects, AUTH), `mysql_check.py` (bound values, pool waits, deadlines, both auth plugins including the RSA exchange, wrong passwords, reconnects), `postgres_check.py` (SCRAM/MD5/cleartext, Unicode passwords, typed binary parameters, OID results, statement cache eviction, transactions, pool waits, deadlines, malformed frames and 1000 inserts) and `websocket_check.py` (RFC 6455 rules, 300 idle connections and 20 concurrent streams on one core, the Tin client). On `ubuntu-24.04` the MySQL check also runs against the runner's own MySQL 8 and the PostgreSQL check runs against its preinstalled PostgreSQL with a SCRAM user; `REDIS_ADDR` / `MYSQL_ADDR` / `POSTGRES_ADDR` point the checks at real servers locally.
- The v0.4 service benchmark (`.github/workflows/bench.yml`) is separate and runs only on demand: Redis and MySQL service containers, wrk2 built from source, Tin vs Go + chi. It is never a merge gate.
- Linux benchmarks (`.github/workflows/bench-linux.yml`): the CPU suite (`bench/v2`) and the HTTP suite (`bench/http/run_wrk.sh`) on `ubuntu-24.04` and `ubuntu-24.04-arm`, weekly, on demand and on PRs that change `bench/`, `lib/` or `selfhost/`. Each job keeps Tin/Go reference measurements and compares the head against its merge base using matching compiler/library trees. Reference performance is Linux only; macOS is a development platform (docs/PERFORMANCE.md, "Benchmark policy"). Output mismatches, crashes, timeouts and failed HTTP measurements fail the workflow; timing thresholds flag review and never act as an automatic merge gate. Raw JSON samples and HTTP logs are retained.
- Harness self-tests ensure expected output cannot disguise crashes/timeouts or unexpectedly accepted negative programs. Benchmark self-tests check alternating medians, output equality on every repetition, matching revision library trees, and failed measurements.
- The libc inventory guard (`test_libc_inventory.py`) checks Linux `extern func` and legacy `extern fn` declarations plus ELF startup imports against `notes/libc_inventory.md`; new, reintroduced, unassigned or stale entries fail.

The Python harness uses only the standard library. Shell entrypoints now require Python 3. Native runtime probes have a 20-second timeout, core dumps disabled, and a 512 MiB virtual-memory limit on Linux. The first-allocation crash reproducer is Linux-only: macOS can map writable memory beyond the undersized allocation, making a SIGSEGV expectation unreliable there. HTTP tests require `ps` (available on hosted Ubuntu).

Linux amd64 is a supported execution gate: the `ubuntu-24.04` job builds the compiler from `seed/tinc-linux-amd64`, checks the self-hosting fixed point and runs every suite natively on x86-64 hardware. Refresh that seed with `make linux-amd64-bootstrap` (emulated container on an arm64 Mac).

## Existing defects versus new regressions

The initial baseline contains explicit `known_failure` contracts for open issues #1–6. These are visible as **XFAIL**, not PASS, in logs, JSON artifacts and the Actions summary. A known failure matches its phase, exit code and specified output/diagnostic; unrelated failures are not exempt. A timeout is never an expected failure.

If a fix makes the expected behavior pass while the exemption still exists, CI reports **XPASS and fails**. Keep the test and remove its `known_failure` field in the same fixing PR. Thereafter a recurrence is a normal blocking failure. Do not delete the test or weaken the expected contract to close an issue. New failures must not be added to the exemption list just to unblock a PR.

The issue audit checks GitHub for every exempted issue. Closing an issue while an exemption remains fails the audit. It runs on pushes/PRs and on issue close/reopen events against the default branch. It reads issue state only; it does not execute issue text, edit workflow code, comment, reopen issues or auto-merge changes. If closing as a duplicate or not planned, explicitly review and explain any corresponding coverage change.

## Resolving an issue

1. Add a small deterministic reproducer and the intended correct behavior. For a language/runtime bug, use `tests/regressions/NAME.tin` and an entry in `cases.json` with the issue number. Every `.tin` file must have exactly one entry; the runner discovers new cases without workflow edits.
2. Implement the fix. If the case already exists, remove its `known_failure` contract and keep its expected behavior. For non-Tin tooling bugs, extend `tools/ci/test_*.py`; unittest discovers them automatically. Issues #7 and #8 are covered by these harness tests.
3. Run the commands below and include the regression test names in the PR. Expand the workflow only when the issue needs a new environment/tool, such as native amd64 or cgroup namespace fixtures.
4. Let CI pass and merge the PR before closing the issue (a `Fixes #N` PR reference closes it on merge).

This avoids a bot rewriting Actions after closure: the regression becomes required **in the fixing PR**, before its code can merge. The issue audit catches forgotten exemptions afterward.

## Local commands

```sh
make bootstrap
python3 -m unittest discover -s tools/ci -p 'test_*.py' -v
tools/v2test.sh bin/tinc
python3 tools/ci/number_check.py          # exact number bits/text against Go and hard cases
python3 tools/ci/regressions.py
python3 tools/ci/regressions.py --audit   # network; GH_TOKEN optional for public issues
python3 tools/ci/http_check.py            # Linux HTTP/RSS/shutdown
python3 tools/ci/task_check.py            # request tasks, deadlines, helpers
python3 tools/ci/router_check.py          # routed server: parameters, middleware, 404/405 under load
python3 tools/ci/lifetime_check.py        # formatting, helper deadlines, WebSocket lifetimes
python3 tools/ci/cancel_check.py          # boundary cancellation in every client
python3 tools/ci/redis_check.py           # REDIS_ADDR=host:port for a real Redis
python3 tools/ci/mysql_check.py           # MYSQL_ADDR, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE for a real MySQL
python3 tools/ci/postgres_check.py        # POSTGRES_ADDR, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DATABASE for a real PostgreSQL
python3 tools/ci/websocket_check.py
```

`tools/linuxtest.sh` and `tools/x64fuzz/linuxtest_amd64.sh` use the same strict runner for Docker cross-tests. They check negative diagnostics on the build host and positive outputs/exit codes in the chosen image. `TIN_LINUX_IMAGE` chooses the image; `TIN_ROOT` can select a library tree. The old `X64_TEST_DIR` output option is replaced by unique temporary directories and logs under `bin/ci/`.

Diagnostics are uploaded for 14 days even if a job fails. No compiled output is cached: a stale compiler or test binary cannot make a fresh checkout pass.

PostgreSQL checks use a private users table in the selected database; choose a throwaway
instance/database for local real-server checks. They exercise `examples/postgres.tin`
with extra test routes compiled only into the fixture service. No downloads are needed
for the fake checks. The native Ubuntu x86-64 CI job starts the runner's PostgreSQL and
creates a dedicated `tin` database/user with a SCRAM verifier; it does not install packages.
`POSTGRES_TIMEOUT_MS` configures the example's operation timeout independently of
`TIN_DEADLINE_MS`. The crypto suite checks published PBKDF2/RFC 1321 vectors and Unicode
normalization/bidirectional/prohibited-input cases; `tools/gen_saslprep.py` regenerates
fixed Unicode 3.2 tables with Python's standard library.
