# Retiring Go from the tree

Written 2026-10-02. Tin is written in Tin: the compiler, the runtime, the standard library and,
from here on, the tools around them. Go stays only where it is the thing being compared with.

## Done

- **Stage 0 is gone.** `bootstrap/` was the original Go compiler (`tinc0`, 1,656 lines) for
  Tin's first syntax. Since the compiler's own sources moved to the new syntax, it could no
  longer build them (`selfhost/lex.tin:545: expected 'fn', found name 'func'`), so it was not a
  bootstrap path any more. The seeds in `seed/` are the root of the build, and `make bootstrap`
  proves the fixed point.
- **The legacy-syntax tests are gone with it.** `tests/*.tin` and `tests/errors/` (28 cases)
  existed only to be run by the Go harness. The language is new and has no users to keep
  compatible, and the compiler still compiles itself in the legacy syntax on every build, so
  there is no replacement runner. `tests/v2` and `tests/regressions` are the suites.

## What Go is left (4,431 lines, 35 files)

| code | lines | decision |
|---|---|---|
| `bench/http/conformance` (the 26 HTTP edge-case checks) | 1,009 | rewrite in Tin: CI runs it (`tools/ci/http_check.py`), and it exercises exactly what `wire` and `anvil` are for |
| `tests/graceful/graceful.go` | 244 | rewrite in Tin: also run by `http_check.py` |
| `bench/http/hammer` (load generator) | 181 | rewrite in Tin: every performance number depends on it, and a Tin load generator on `hearth` cores is a benchmark of Tin itself |
| `bench/ref/*` (stdlib checked against Go's library) | 2,098 | keep: Go's library is the reference |
| `bench/v2/*.go`, `bench/*.go`, `examples/demo_go` | 628 | keep: the comparison |
| `bench/http/fast`, `gonet`, `bench/router/go`, `bench/v04/go` | 271 | keep: fasthttp, net/http and chi are the baselines |

A gap that stops one of these from being written in Tin (a missing `wire` feature, a slow path
in `hearth`) is a standard-library bug, and fixing it is part of the work.

Once the first three are rewritten, CI no longer needs the Go toolchain for anything but the
benchmark workflow, and `setup-go` leaves `ci.yml`.
