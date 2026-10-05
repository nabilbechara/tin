# Tin architecture and the rules a contributor (human or agent) works within

Tin is a Go-like language whose compiler, runtime and standard library are written in Tin. The goal is
a language as ready as Go, Rust and Odin for servers and tools, with performance as the end goal. The
plan is `notes/roadmap.md`; the design decisions are `notes/design_foundations.md`; this file says where
everything lives and what you may and may not change. If a task does not fit this layout, stop and say so
instead of inventing a new place for it.

## 1. The repository

| Path | What lives there | Who may change it |
|---|---|---|
| `selfhost/` | The compiler `tinc`, written in typed edition 1 (trusted code): `lex`, `parse`, `check`, `lower`, `generics`, `region` (the compile-time memory checker), `inline`, `opt`, back ends `gen` (arm64) and `gen_x64`, assemblers `asm` and `asm_x64`, object writers `macho` and `elf`, `elf_x64`, `main`, host parts `host_darwin` and `host_linux`. | Only a task that is about the compiler. Always finish with `make bootstrap` (a fixed point). |
| `seed/` | Checked-in compiler binaries that build the compiler from source (`tinc-darwin-arm64`, `tinc-linux-arm64`, `tinc-linux-amd64`). | Only through `make seed`, in a PR that says why a new seed is needed. Never edit by hand. |
| `lib/runtime/` | The runtime every program gets: memory (pools, the long-lived heap), strings, slices, maps, formatting, tasks, panics, the OS layer. Not a package: files are loaded together, with `_darwin`, `_linux`, `_linux_arm64`, `_linux_amd64` parts. It imports nothing. | A task about the runtime. Generated parts (`printable.tin`) come from `tools/gen_unicode.py`. |
| `lib/NAME/` | One standard-library package per directory (`package NAME`), imported as `import "NAME"`. Files split by topic, platform parts end in the platform name, `_test.tin` files are skipped by the loader. See `lib/README.md`. | Any library task. |
| `tests/v2/` | The strict test suite: `NAME.tin` plus `NAME.out` (expected stdout, sorted bytewise because the suite sorts lines) or `NAME_bad.tin` plus `NAME_bad.err` (expected compile error). Run by `tools/v2test.sh`. | Every task adds tests here. |
| `tests/regressions/` | One reproducer per fixed bug, with its contract in `cases.json`; every entry needs an `issue` number. Run by `tools/ci/regressions.py`. | Every bug fix. |
| `bench/ref/NAME/` | The Go twin of a Tin test: a Go program printing the same lines. The expected output of the Tin test is Go's. Go is a comparison baseline only, never part of the product. | Library tasks, alongside the Tin test. |
| `bench/`, `bench/v04`, `bench/http`, `bench/router` | Benchmarks and service benchmarks against Go. | Performance tasks. |
| `docs/` | `LANGUAGE.md` (reference), `RUNTIME.md`, `COMPILER.md`, `TOOLING.md`, `PORTING.md`, `PERFORMANCE.md`, `COVERAGE.md` (the inventory of Go's surface against Tin), `STDLIB.md` (generated), `AGENT_PRIMER.md`. | Whoever changes behavior updates the matching doc in the same PR. |
| `notes/` | `roadmap.md` (the plan), `design_foundations.md` (decided designs), `stdlib_verified.md` (what is verified against Go), design and progress notes. | Roadmap boxes and verification rows as work lands. |
| `tools/` | `v2test.sh`, `gendoc.py` (writes `docs/STDLIB.md`), `gen_unicode.py` (writes the Unicode tables), `dist.py`, `ci/` (CI checks). | `tools/ci`: extend existing files only, never add a Python file there. New tooling is written in Tin. |
| `examples/`, `docker/`, `install.sh`, `Makefile`, `VERSION`, `.github/` | Examples, container images, installer, build entry points, CI and the PR template. | Only tasks about distribution or CI. |
| `go.mod` | Left from the retired Go stage; Go remains only as a baseline for twins and the HTTP conformance tools until those are rewritten in Tin. | Do not add Go code to the product. |

Generated files are never edited by hand: `docs/STDLIB.md`, `docs/COVERAGE.md` (from its generator), `lib/glyph/tables.tin`, `lib/runtime/printable.tin`, `bench/ref/*/main.go` and `tests/v2/*.tin` where a generator wrote them. Change the generator and regenerate.

## 2. How a program is built

`tin FILE.tin` (or `bin/tinc`) lexes and parses the program and the packages it imports (`package_files` loads `lib/NAME.tin` or every `.tin` file of `lib/NAME/`, sorted, skipping tests and other platforms), checks types and the region rules, lowers to an intermediate form, monomorphizes generics, inlines and optimizes, generates machine code for arm64 or amd64, and writes a Mach-O or ELF executable directly. There is no linker, no C compiler and no libc dependency to add (libc removal is in the roadmap). The runtime is compiled in with the program; unused functions and data are dropped.

## 3. Rules that every change keeps

Design (notes/design_foundations.md is authoritative):
1. No garbage collector: request-scoped bump pools, `keep` for long-lived data, checked at compile time.
2. Thread-per-core, share-nothing: no mutexes, no work stealing that moves a running task, no preemption. Cross-core communication is `relay` messages and atomics.
3. No interfaces, no reflection, no struct tags: generics (monomorphized), enums with exhaustive `switch`, shapes (when built) and compile-time derivation.
4. Errors are faults (`!T`, `try`, `catch`, `fail`); ignoring one is a compile error. Panics end the request or process; `guard` is the planned recovery.
5. Everything is written in Tin. No C, no new Go in the product, no `cgo`.
6. Tin is not a Go clone: where Go's design conflicts with the rules above, replace it (the roadmap marks those `[-]` with the replacement named) rather than copying it.

Process:
7. A library function is verified against Go: a generated twin (`bench/ref/NAME/main.go`) and the Tin test (`tests/v2/NAME.tin`) come from one description, and the Tin output must be identical to Go's. Prove the test is sensitive by breaking one constant and seeing it fail.
8. Every bug found gets an issue, a regression case in `tests/regressions/` tied to it, and a fix in the same PR (or its own PR). Fix bugs you find along the way.
9. A PR is big enough to be complete: the code, the tests, the twin, the docs and the roadmap boxes it closes. No two-line PRs, no half features.
10. Behavior changes update `docs/LANGUAGE.md` or the matching doc, regenerate `docs/STDLIB.md` (`python3 tools/gendoc.py`) and `docs/COVERAGE.md`, and add the row to `notes/stdlib_verified.md`.
11. Names follow the role of the thing, not a language prefix. A package directory is `lib/<name>/`; Tin's package names are short nouns (`twine` for strings, `link` for net/url).
12. Do not add new Python files under `tools/ci`. Do not add dependencies. Do not weaken or delete a test to make it pass.

## 4. What to run before opening a PR

```
make bootstrap                       # the compiler rebuilds itself to an identical binary (compiler or runtime changes)
tools/v2test.sh                      # the strict suite: every line must PASS
python3 tools/ci/regressions.py      # regression cases
python3 tools/ci/test_tooling.py     # harness tests
python3 tools/gendoc.py              # when package docs or exports changed
bin/tinc -target linux-arm64 -o /tmp/x FILE.tin ; bin/tinc -target linux-amd64 -o /tmp/x FILE.tin   # cross-build what you touched
```

Run long commands (benchmarks, watches) in the background. The PR description uses `.github/pull_request_template.md`: change, evidence against Go, regression coverage, validation. CI must be fully green (all 8 checks) before merging, and every merge to main releases automatically.

## 5. Where new work goes

| Kind of work | Place | Also |
|---|---|---|
| A Go package or function | `lib/<tin name>/` (see `docs/COVERAGE.md` for the Tin name, or pick a short noun and record it there) | `tests/v2/<name>.tin` + `.out`, `bench/ref/<name>/main.go`, `docs/COVERAGE.md` row, `notes/stdlib_verified.md` row |
| A language feature | `selfhost/` (lex, parse, check, lower, back ends) following the nine-step template in roadmap section 12.1 | `tests/v2/<feature>.tin`, `_bad.tin` + `.err` cases, `docs/LANGUAGE.md`, design note first |
| A runtime feature | `lib/runtime/` with platform parts | `docs/RUNTIME.md`, a runtime test, Linux behavior covered |
| A compiler optimization | `selfhost/inline.tin`, `opt.tin`, `gen*.tin` | a benchmark before and after in `docs/PERFORMANCE.md`, `make bootstrap` |
| A new tool or command | written in Tin, under `tools/` (not `tools/ci`) | `docs/TOOLING.md` |
| A bug | the code that is wrong | `tests/regressions/<name>.tin` + `cases.json` entry with the issue number |
| A decision | `notes/design_*.md` first, then code | a roadmap box moves from "Open questions" |

## 6. Limits for fast or parallel agents

- Work in a branch per roadmap item; one item per PR unless items are inseparable.
- Do not touch `seed/`, `Makefile`, `.github/`, `VERSION` or the generated files listed above except as their own task says.
- Do not edit `selfhost/` or `lib/runtime/` unless the task is a compiler or runtime item; if you hit a compiler bug while doing library work, write a minimal reproducer, open an issue, and either fix it in a separate commit with its regression case or work around it and say so in the PR.
- Scratch files go in the session scratchpad, never in the repository.
- When two items conflict (same file), do them in roadmap order, not in parallel.
- Keep `notes/roadmap.md` honest: check a box only when the work is merged and its acceptance test passes; add a sub-item rather than check a box that is partly done.
- If the layout above blocks you, stop and ask; do not add top-level directories, new languages or new build systems.
