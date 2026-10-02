# Tin documentation

| document | read it for |
|---|---|
| [LANGUAGE.md](LANGUAGE.md) | the language reference: every type, statement, expression, rule and error, plus the grammar |
| [STDLIB.md](STDLIB.md) | every standard-library package and exported name (generated from `lib/*.tin`) |
| [TOOLING.md](TOOLING.md) | the `tin` command, `tinc`, make targets, tests, Docker, benchmarks, debugging, repository layout |
| [DISTRIBUTION.md](DISTRIBUTION.md) | release archives, verified installer, builder images and source-to-container builds |
| [RUNTIME.md](RUNTIME.md) | memory (pools, ingot heap, regions), cores, value layouts, panics, the HTTP server's internals and its router, request tasks, non-blocking I/O and helper threads, how the redis/mysql/websocket clients share a core, the platform layer |
| [COMPILER.md](COMPILER.md) | how the self-hosted compiler works: passes, data structures, code generation, linkers, bootstrapping, how to change it |
| [PORTING.md](PORTING.md) | targets (macOS, Linux arm64, Linux amd64), ELF details, containers and Kubernetes, adding a target |
| [PERFORMANCE.md](PERFORMANCE.md) | benchmark results against Go, methodology, where Go still wins and why (the v0.4 service benchmark is pending: #74) |
| [AGENT_PRIMER.md](AGENT_PRIMER.md) | a one-page brief to give an AI agent before it writes Tin code |

Design notes and records live in [`../notes/`](../notes): the roadmap (`roadmap.md`), the
v0.4 async-I/O design (`design_v04.md`), the Linux plan and ABI reference (`plan_linux.md`,
`linux_abi.md`), stdlib verification against Go (`stdlib_verified.md`), benchmark analyses
(`bench_v2.md`) and the HTTP edge-case work (`anvil_hardening.md`).

## Where to start

- Writing Tin: AGENT_PRIMER.md, then LANGUAGE.md, then STDLIB.md for the packages you use.
- Building, testing or shipping: TOOLING.md, then PORTING.md §4 for containers.
- Changing the compiler or runtime: COMPILER.md and RUNTIME.md, and the rule in
  TOOLING.md §4 (bootstrap fixed point and all tests green before anything is done).
