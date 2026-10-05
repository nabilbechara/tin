# Tin tooling: commands, builds, tests, benchmarks

Everything lives in one tree (`~/Desktop/tin`). Nothing outside it is needed to build
Tin: the checked-in seed compiler builds the compiler, which builds everything else. Go
is used only by the HTTP conformance tools, benchmarks and reference programs; Docker only
for Linux testing.

## 1. Installing

For prebuilt archives, the checksum-verifying installer and the multi-architecture
Docker builder, see [DISTRIBUTION.md](DISTRIBUTION.md). The commands below install
from a source checkout.

```sh
make install                    # builds bin/tinc from seed/ and links `tin` into $(PREFIX)/bin
make install PREFIX=~/.local    # a per-user install: no privileges, ~/.local/bin must be on PATH
make && sudo make install       # a system-wide install where $(PREFIX)/bin is root-owned
```

`PREFIX` defaults to `/opt/homebrew` on a Mac with Homebrew there and to `/usr/local`
everywhere else (Linux, a Mac without Homebrew); an explicit `PREFIX` always wins.
`$(PREFIX)/bin` is created if missing. On most Linux systems `/usr/local/bin` is
root-owned, so either install per user or build first as yourself and run only the
install step with `sudo` (so `bin/` stays yours). The link points into this tree:
moving or deleting the tree breaks it.

`tin` is a shell script (`./tin`); `bin/tinc` is the compiler binary.

## 2. The `tin` command

| command | does |
|---|---|
| `tin FILE.tin [ARGS...]` | compile and run (temporary executable, removed after) |
| `tin run A.tin B.tin -- ARGS` | compile several files as one program and run it |
| `tin build FILE.tin... [-o OUT] [--target T] [--strip]` | write an executable (default name: the first file without `.tin`); `--strip` leaves out a Linux executable's symbol table (§8) |
| `tin asm FILE.tin...` | print the generated ARM64 assembly (clang syntax) |
| `tin fix -edition 1 FILE.tin...` | rewrite edition-0 (Go-like) files to edition 1 in place (LANGUAGE.md §22) |
| `tin audit secrets [-edition 1] FILE.tin...` | check the program and list every place a `secret` leaves the checker's protection: each `reveal(x)` and each secret passed to a library parameter declared `secret`, as `file:line:col: ...` sorted by position, then a count; exit status 1 (with the errors) when the program does not check |
| `tin test [-bench] [DIR]` | build DIR (default `.`) with its `*_test.tin` files and run every `TestXxx(t mut crucible.T)`, then `BenchmarkXxx(b mut crucible.B)` with `-bench`; exit status 1 when a test fails, 2 for a wrong test signature (see §5.1) |
| `tin replay CAPSULE --against BUILD [--live KIND]... [--save-test NAME --issue N]` | run a recorded request again with every effect served from its capsule, and report the first divergence (see §8.1) |
| `tin fix -edition 1 FILE.tin...` | translate each file to edition 1 in place. A file whose translation does not parse as edition 1, or changes when translated again, is left unchanged with the reason (for example a `const` in a nested block, which has to move by hand); exit status 1 when any file was left unchanged |
| `tin vendor [DIR]` | copy every package `DIR/tin.mod` requires (transitively, from local source directories) into `DIR/vendor/<path>` and write `DIR/tin.lock` with each vendored file's SHA-256 (see §2.1) |
| `tin caps FILE.tin...` | check the program and print, per package, the capabilities (`net`, `files`, `spawn`, `exec`, `unsafe`) its exported functions can reach |
| `tin suite` | run the compiler's strict test suite (`tools/v2test.sh`) |
| `tin bootstrap` | rebuild the compiler with itself; the binaries must be identical |
| `tin version` | version and compiler checksum |

Targets (`--target`): `darwin-arm64` (default on a Mac), `linux-arm64` (default on
arm64 Linux), `linux-amd64` (supported and tested natively). Cross-compiling needs nothing extra: the
compiler contains every backend and writes Mach-O or ELF itself.

Programs without a `package` clause use the legacy syntax; `tin` adds `lib/std.tin` to
them.

### 2.1 Dependencies: `tin.mod`, `tin vendor`, `tin.lock`

A dependency is imported by path (`import "github.com/ana/geo"`) and read only from
`vendor/github.com/ana/geo` next to the program. Builds never fetch anything. The details
are in [PACKAGES.md](PACKAGES.md).

```sh
cat tin.mod
#   module example.com/app
#   require github.com/ana/geo ../geo        local directory: a checkout or a mirror
tin vendor                                   # vendor/github.com/ana/geo/... and tin.lock
tin build main.tin                           # offline; refuses a vendored file whose hash changed
```

A dependency's own `tin.mod` declares its capabilities (`caps net files`). The compiler
rejects a call from a vendored package that can reach anything else (`E804 CAPABILITY`,
at the call, with the path to the entry point). `tin vendor` copies each package's
capabilities into `tin.lock`, so an upgrade that asks for more shows up in review.
`tin caps main.tin` prints what each package can reach.

With a `tin.lock`, every vendored file must have the hash the lock records, and every
other listed file is checked too. A changed byte stops the build before the file is
parsed: `E111 LOCK_MISMATCH` names the file and both hashes. Review the change, then run
`tin vendor` again to accept it.

## 3. The compiler, `tinc`

```text
tinc [-o OUT] [-S] [-edition 1] [-target darwin-arm64|linux-arm64|linux-amd64] FILE.tin...
```

- `-o OUT`: write the executable (default `a.out`). `-S`: print assembly instead.
- `-edition 1`: read the program's files as edition 1 (LANGUAGE.md). Without the flag each
  file is read in the edition it is written in. Edition 0, the Go-like syntax before it, is
  retired (#226): the compiler refuses it (E090) and only `tin fix -edition 1` reads it.
- `-audit-secrets`: check the program and print its secret audit instead of building
  (`tin audit secrets`; LANGUAGE.md §18).
- The standard library is found through `$TIN_ROOT` or, without it, relative to the
  executable (`<root>/bin/tinc` means `<root>/lib`). The `tin` script sets `TIN_ROOT`.
- Strict programs get the package `lib/runtime/` (its `*_<os>.tin` and `*_<os>_<arch>.tin`
  files only for the target) automatically; imports are resolved as in LANGUAGE.md §1.
- Errors print as `file:line:col: error E502 TYPE_ARG_COUNT: message` (code and name from
  [ERRORS.md](ERRORS.md)), every error in one run; the exit code is 1. A compiler crash prints a backtrace only under a debugger (see §8).
- `-caps`: check the program and print the capabilities each package can reach instead of
  building (`tin caps`; PACKAGES.md, "Capabilities").
- `-fix -edition 1 FILE.tin` prints the file translated to edition 1 (`tin fix`, which also
  checks the result before writing it).
- `-hash FILE...` prints `<sha256> FILE` for each file (the `tin.lock` lines `tin vendor`
  writes) and builds nothing.
- `TINC_TRACE=1` prints each function as it is generated (to find which one crashes the
  code generator).

## 4. Make targets

| target | does |
|---|---|
| `make` / `make bin/tinc` | build the compiler from the host's seed (`seed/tinc-<os>-<arch>`) |
| `make bootstrap` | `bin/tinc` builds `bin/s2/tinc`, which builds `bin/s3/tinc` (with `TIN_ROOT` set to the tree, because the compiler is a strict program that loads `lib/runtime`); they must be byte-identical |
| `make seed` | bootstrap, then refresh the host's seed from `bin/s3/tinc` |
| `make test` | the strict suite |
| `make linux-test` | cross-compile every strict test for linux-arm64 and run it in an arm64 container (`tools/linuxtest.sh`) |
| `make linux-bootstrap` | cross-compile a Linux compiler, then in the container it must rebuild itself identically; refreshes `seed/tinc-linux-arm64` |
| `make linux-amd64-bootstrap` | the same for x86-64 in `tin-debian-amd64` (emulated on an arm64 Mac); refreshes `seed/tinc-linux-amd64` |
| `make bench` | the legacy CPU benchmarks vs Go (`bench/run.py`) |
| `make install` | link `tin` into `$(PREFIX)/bin` (created if needed; see §1 for the default) |
| `make dist` | package the native compiler, library and sources in a versioned archive with a SHA-256 checksum |
| `make print-VAR` | print a Makefile variable (e.g. `make print-SELF`, the compiler's sources) |
| `make clean` | remove `bin/` |

Rule of the tree: before anything is called done, `make bootstrap` reaches the fixed
point and `make test` (plus `make linux-test` when the library or backend changed)
passes.

## 5. Tests

| suite | where | how it checks |
|---|---|---|
| strict tests | `tests/v2/*.tin` | `tools/v2test.sh`: compiles and runs each, sorts the output and compares it with `NAME.out`; `NAME_bad.tin` must fail to compile with exactly `NAME_bad.err` |
| diagnostic codes | `docs/ERRORS.md` | `tools/v2test.sh` runs `tools/ci/diagnostics_check.py`: the compiler's codes, the page and the `.err` files agree, and every example on the page compiles to exactly the output it shows |
| assembly checks | `tests/v2/*_asm.tin` + `*_asm.check` | `tools/v2test.sh`: compiles with `-S` and matches the listing against ordered `CHECK:`/`CHECK-NOT:` lines, lit-style; a `[arm64]`/`[amd64]` line selects a section, lines before any section apply to every CPU |
| Linux | same files | `tools/linuxtest.sh`: cross-compiles for linux-arm64, runs in `tin-debian-arm64`, compares with the same `.out` files |
| HTTP conformance | `bench/http/conformance` | 26 edge cases against a running server: `bin/conformance -addr 127.0.0.1:9180 -pid PID` |
| x86-64 encoder | `tools/x64fuzz` | `tools/x64fuzz/run.sh [COUNT] [SEED]`: random instructions vs `x86_64-linux-gnu-objdump` |
| stdlib vs Go | `bench/ref/NAME/main.go` | the same cases written with Go's library; outputs diffed (see notes/stdlib_verified.md) |

### 5.1 Testing your own code: `*_test.tin`

<!-- tin-prelude
fn Area(w i64, h i64) i64 {
	return w * h
}

fn clampPos(x i64) i64 {
	return max(x, 0)
}

fn parse(s str) !i64 {
	return len(s)
}
-->
```tin
// geo_test.tin, next to geo.tin (same package; private names are visible)
package geo

import "crucible"

fn TestArea(t mut crucible.T) {
	crucible.Equal(mut t, "2x3", Area(2, 3), 6)   // any comparable type
	t.True("clamp", clampPos(-1) == 0)
	let (n, err) = parse("12")
	t.NoFault("parse", err)
	crucible.Equal(mut t, "parsed", n, 2)
	if t.Failed() {
		t.Log("printed only when the test fails")
	}
}

fn BenchmarkArea(b mut crucible.B) {
	for i in 0..b.N {
		Area(i, 3)
	}
}
```

`tin test ./geo` prints `--- PASS: TestArea` / `--- FAIL: ...` with the failure messages,
then `PASS: N tests` or `FAIL: ...` (exit status 1). `tin test -bench ./geo` also runs each
benchmark, doubling `b.N` until it takes a second, and prints ns/op. `*_test.tin` files are
never part of a normal build or import. Underneath, `tin test` writes a runner calling each
test through `crucible.Run` and compiles the package with `tinc -entry pkg.TinTestMain`.

As in Go, a test is a `TestXxx` (or benchmark `BenchmarkXxx`) in a `*_test.tin` file whose
`Xxx` does not start with a lowercase letter (`Testify` is an ordinary function). It must be
declared on one line as `fn TestXxx(name mut crucible.T) {` (`mut crucible.B` for a
benchmark); any other signature is reported as `FILE:LINE: wrong signature for TestXxx`
with exit status 2, so no test is skipped silently.

Adding a strict test: write `tests/v2/NAME.tin` with deterministic output (no times,
addresses or map-order dependence beyond what sorting hides), run it, check every line
by hand, then save `bin/t | sort > tests/v2/NAME.out`. `v2test.sh` never creates
expected files itself.

Adding a compiler error: report it with `err_code(pos, "E5NN NAME")` (or `err_code_at`,
`err_code_quoted`), reusing the code of the rule it enforces or adding one: a new entry in
`docs/ERRORS.md`, in code order, with the rule, an example, the exact output and the fix.
Never renumber or reuse a code; when a diagnostic goes away, its entry stays, marked `Retired:`.

Writing to files in tests: use paths under `/tmp/tin-test-*` (they work on macOS and
Linux).

## 6. Linux on a Mac (Docker)

Images (built locally, all native arm64 except where noted):

| image | contents | used for |
|---|---|---|
| `tin-debian-arm64` | debian:bookworm-slim (glibc 2.36) | running tests |
| `tin-bench-arm64` | the above + wrk, procps | benchmarks, conformance |
| `tin-debian-amd64` | debian:bookworm-slim amd64 (emulated) | x86-64 correctness |
| `golang:1.27` | Debian 13 + Go + gcc | C probes, Go builds |

Re-create them with:

```sh
docker pull --platform linux/arm64 debian:bookworm-slim && docker tag debian:bookworm-slim tin-debian-arm64
docker pull --platform linux/amd64 debian:bookworm-slim && docker tag debian:bookworm-slim tin-debian-amd64
printf 'FROM tin-debian-arm64\nRUN apt-get update -qq && apt-get install -y -qq wrk procps\n' | docker build -t tin-bench-arm64 -
```

(after pulling both platforms, the bare `debian:bookworm-slim` tag points at the last
one pulled: always use the `tin-*` tags or `--platform`.)

Running something by hand:

```sh
tin build --target linux-arm64 app.tin -o bin/linux/app
docker run --rm -v "$PWD/bin/linux":/w tin-debian-arm64 /w/app
```

Go binaries for the container: `GOOS=linux GOARCH=arm64 go build -o bin/linux/x ./dir`.

## 7. Benchmarks

| script | measures |
|---|---|
| `bench/http/run_wrk.sh CORES THREADS CONNS SECS ROUNDS` | anvil vs fasthttp vs net/http on macOS under wrk: req/s, p99, req per server CPU-second, RSS (medians) |
| `bench/http/run_pipelined.sh "1 2 4"` | the same with 16 pipelined requests per write (wrk Lua script) |
| `bin/linux/bench.sh` (inside `tin-bench-arm64`) | the same comparison on Linux |
| `bench/v2/NAME.tin` + `NAME.go` | CPU benchmarks; build both, time with `/usr/bin/time -l`, outputs must be identical |
| `bench/dispatch/dispatch.tin` | shape dispatch against a hand-written call (Tin only, no Go twin): ns/op of each and their ratio; see PERFORMANCE.md section 5 |
| `bench/dispatch/dyn.tin` | dynamic shape dispatch against a direct method call; reports ns/op and pool bytes, with a paired assembly check in `tests/v2/shapes_dyn_asm.tin` |
| `examples/demo.tin` + `examples/demo_go` | the mixed demo (primes, sort, SHA-256, JSON, maps), self-timing |
| `bench/http/hammer` | a Go load generator (wrk-like) with exact latency histograms |
| `bench/router/router.tin` + `bench/router/go` | routing cost with 1, 20 and 200 routes: a lookup (`Match`) and a whole request through the router (`Run`), against chi's `Find` and `ServeHTTP` |
| `bench/http/routes.tin` | `/json` and `/plaintext` behind a router of `ROUTES` routes (port 9180, like `examples/api.tin`), for routing inside a served request |
| `bench/v04/run.py` | `GET /users/{id}` through Redis over MySQL, Tin vs Go + chi under wrk2: max req/s, req per CPU-second, p50/p99/p99.9 at a fixed rate, RSS (needs Redis, MySQL seeded by `bench/v04/seed.py`, and `WRK2`) |

Servers used: `examples/api.tin` (port 9180, `TIN_CORES=n`), `bench/http/fast` (fasthttp,
9182), `bench/http/gonet` (net/http, 9181), with `GOMAXPROCS=n`. Results and analysis:
[PERFORMANCE.md](PERFORMANCE.md).

## 8. Debugging

| tool | use |
|---|---|
| `tin asm file.tin` / `tinc -S` | read the generated code |
| `tools/try.sh COMPILER FILE.tin` | compile and run; if the compiler crashes, print its backtrace under lldb |
| `tools/crash.sh PROGRAM ARGS` | run under lldb and print a Tin backtrace on a crash (`tools/tinbt.py` walks frame pointers) |
| `TINC_TRACE=1 tinc ...` | which function the backend was generating |
| panics | print the message and a backtrace (inlined frames are missing) |
| `lldb bin/t` | symbols are present (function names as `pkg.Name`, `Type.Method`) |

A compiler change that breaks the compiler itself: build with the previous good
compiler (`bin/s3/tinc` or the seed), never overwrite the seed until `make bootstrap`
passes.

**Profiling a Linux service** (#351). A Linux executable carries section headers and a
symbol table (`.symtab`) naming every function as `pkg.Name`, `pkg.Type.Method` or a
generated name (`keep$N`), with its size. The table is not loaded; it costs about 4% of
the file (33 KiB of the compiler's 812 KiB) and `tin build --strip` (`tinc -strip`) leaves
it out. `nm`, `addr2line -f`, `perf` and `gdb` read it:

```sh
perf record -g -p "$(pidof api)" -- sleep 10    # sample the running server for ten seconds
perf report --sort symbol                         # time per Tin function
```

Frames are walked with the frame pointers Tin always keeps (`perf record -g`, or
`--call-graph fp`). Source lines need DWARF `.debug_line`, which is not emitted yet:
`perf annotate` and `gdb list` show machine code only.

### 8.1 Replaying a recorded request: `tin replay`

A server records a request's effects in a capsule when it runs with `TIN_REPLAY_DIR` and
`TIN_REPLAY_KEY` set (the switches are listed in `notes/interface_replay.md` §1). `tin replay` runs that request again:

```sh
TIN_REPLAY_KEY=<64 hex digits> tin replay spool/00001700000000000000-000-1.tcap --against server.tin
```

- `--against BUILD` is the program to run: a binary, or a `FILE.tin` that `tin` builds
  first. It can be a later build than the one that recorded the capsule.
- Run it with the configuration the server was recording under (the same environment
  variables, `TIN_REPLAY_SECRET_HEADERS` included): effect keys hold what the program sent,
  such as a service's URL, so another address is a divergence. `examples/checkout.tin` is a
  worked example: record a failed checkout against Redis and a payment service, then replay it
  with neither running.
- BUILD runs with `TIN_REPLAY_CAPSULE` set. Its `anvil.Serve` (or `Router.Serve`) does not
  listen. It opens the capsule, checks the tag under `TIN_REPLAY_KEY`, and refuses a schema or
  effect kind the build does not list (`replay.Kinds`). Then it sends the recorded request once
  through the handler or router on one core. Every effect that goes through the replay hook
  gets its recorded result or fault, and none is performed. The clients (clock, randomness,
  HTTP, Redis, SQL, files) join the hook in #241's recording slices.
- Replay stops at the first **divergence**: an effect whose kind or key differs from the next
  recorded one (a different call, or a different order), or an effect after the last one. From
  then on every effect of the request fails with the divergence; replay never falls through to
  a live call.
- `--live KIND` (repeatable, a kind without `@version`, such as `wire.http` or `redis`) makes
  that kind's calls for real. They are still compared with the recording, which they consume.
- The report goes to standard output, followed by the response body:

  ```text
  replay: status 500 (recorded 500)
  replay: divergence at effect 0: got wire.http@1 "POST ...", recorded redis@1 "GET cart:7"
  replay: 2 recorded effects not served
  charge failed: ...
  ```

  The second line appears only after a divergence, and the third only if some recorded effects
  were not used.
- Exit status: 0 when nothing diverged and every recorded effect was used; 3 when the replay
  diverged or left effects; 4 when the capsule cannot be read (wrong key or damaged, unsupported
  schema or kind, missing `TIN_REPLAY_KEY`); 2 for a usage error.
- `--save-test NAME --issue N` (BUILD must be a `FILE.tin`, without `--live`) runs the replay. If
  it exits 0, it turns the capsule into a regression case: `tests/regressions/NAME.tin` (a copy
  of `FILE.tin`), `tests/regressions/NAME.tcap` (the capsule sealed again under a public test
  key), and an entry in `cases.json` (`"replay": {"capsule", "key"}`; the expected output is this
  replay's report and body). `tools/ci/regressions.py` runs the program with the replay switches
  and checks the exit status and output, so CI replays the request on every change. Fix the bug
  first, then save the replay against the fixed build: the case then fails if the old behaviour
  comes back. The saved capsule can be read by anyone. Secret headers are already handles, but
  check the request and the recorded results before you commit them.
- Only the request is replayed. Code that runs before `Serve` (`main`, eager initializers,
  `use` resources, `on app.start`) runs as usual, live. A BUILD that never calls `Serve`
  ignores the capsule.

## 9. Repository layout

```text
tin                 the tin command (shell script)
Makefile            builds, bootstraps, tests
selfhost/           the compiler, in legacy Tin (COMPILER.md)
lib/<package>/      the runtime and each standard-library package, one directory each (lib/README.md)
tests/v2/           strict tests and expected outputs
seed/               tinc-darwin-arm64, tinc-linux-arm64, tinc-linux-amd64: the compilers that start a build
examples/           api.tin (HTTP server), tasks.tin, redis.tin, mysql.tin, websocket.tin, demo.tin, demo_go/
bench/              v2/ CPU benchmarks, http/ HTTP benchmarks and tools, v04/ the service benchmark, ref/ Go references
tools/              test runners, debugging helpers, gendoc.py, gencoverage.tin, x64fuzz/
docs/               this documentation
notes/              design notes, plans, verification records, roadmap
bin/                build output (ignored)
```

## 10. Version control

The tree is ready to become a git repository: `.gitignore` excludes `bin/` and scratch
output, every generated file can be regenerated (`make`, `tools/gendoc.py`,
`tools/gencoverage.tin`), seeds are
plain files, and no script depends on a machine-specific path.

```sh
git init && git add -A && git commit -m "Tin v0.3"
```

Suggested workflow after that: one branch per milestone; a branch merges only when
`make bootstrap`, `make test` and `make linux-test` pass; seeds change only in commits
where the bootstrap passed, together with the compiler change that needed them.

## 11. Regenerating the docs

`python3 tools/gendoc.py` rewrites `docs/STDLIB.md` from the comments in `lib/*.tin`
(package comment, then one line per exported function, type and constant). Write a
one-line comment above every exported declaration.

`bin/tinc -o /tmp/gencoverage tools/gencoverage.tin && /tmp/gencoverage` rewrites
`docs/COVERAGE.md` from the maintained inventory in `notes/coverage.md`.

`python3 tools/gen_unicode.py` rewrites `lib/glyph/tables.tin` and `lib/runtime/printable.tin` (the Unicode
tables) from Go's `unicode/tables.go`; it needs a Go tree only to read that one file.

## CPU cancellation safepoints

`tin build --polls FILE.tin -o app` and `tin run --polls FILE.tin` enable CPU
cancellation safepoints (`bin/tinc -polls` directly). `TINC_POLLS=1` enables the same
compiler option for build scripts and benchmark harnesses. Polls are experimental and
opt-in because native Linux measurements exceed the 2% performance budget; see
[PERFORMANCE.md](PERFORMANCE.md#cpu-cancellation-safepoints).

With polls, loop back-edges and function entries in user code observe watchdog cancellation.
A `within` deadline unwinds to its owner, runs defers, and returns its fault. A request
spinning past its deadline gets HTTP 504 and the core serves queued requests. Linux SIGTERM
drain also stops a spinning request at the grace deadline. `@nopoll fn kernel(...) ...`
(edition 1) omits polls in that function; calls into other functions may still poll. Trusted
`lib/runtime/` functions never poll. Without the option, waits still observe deadlines and
cancellation; CPU-bound code has no cancellation guarantee.
