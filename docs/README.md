# Tin documentation

| document | read it for |
|---|---|
| [LANGUAGE.md](LANGUAGE.md) | the language reference: every type, statement, expression, rule and error, plus the grammar |
| [ERRORS.md](ERRORS.md) | every compiler error code (`E502 TYPE_ARG_COUNT`): its rule, an example and the fix |
| [STDLIB.md](STDLIB.md) | every standard-library package and exported name (generated from `lib/*.tin`) |
| [TOOLING.md](TOOLING.md) | the `tin` command, `tinc`, make targets, tests, Docker, benchmarks, debugging, repository layout |
| [DISTRIBUTION.md](DISTRIBUTION.md) | release archives, verified installer, builder images and source-to-container builds |
| [RUNTIME.md](RUNTIME.md) | memory (pools, ingot heap, regions), cores, value layouts, panics, the HTTP server's internals and its router, request tasks, non-blocking I/O and helper threads, how the redis/mysql/websocket clients share a core, the platform layer |
| [COMPILER.md](COMPILER.md) | how the self-hosted compiler works: passes, data structures, code generation, linkers, bootstrapping, how to change it |
| [PORTING.md](PORTING.md) | targets (macOS, Linux arm64, Linux amd64), ELF details, containers and Kubernetes, adding a target |
| [PERFORMANCE.md](PERFORMANCE.md) | benchmark results against Go, methodology, where Go still wins and why (including the v0.4 Redis + MySQL service benchmark on Linux) |
| [COVERAGE.md](COVERAGE.md) | every Go standard package and language feature with Tin's status (done, partial, missing, design, n/a) and the order to build the rest in |
| [AGENT_PRIMER.md](AGENT_PRIMER.md) | a one-page brief to give an AI agent before it writes Tin code |

Design decisions, interfaces and the roadmap live in [`../design/`](../design): the roadmap (`roadmap.md`), the
decisions for the foundations (`design_foundations.md`), the semantics and syntax of Tin 1 (`design_semantics.md`,
`design_syntax.md`), the interfaces between the parts (`interface_*.md`), the Linux ABI reference (`linux_abi.md`)
and the stdlib verification against Go (`stdlib_verified.md`).

## Where to start

- Writing Tin: AGENT_PRIMER.md, then LANGUAGE.md, then STDLIB.md for the packages you use.
- Building, testing or shipping: TOOLING.md, then PORTING.md §4 for containers.
- Changing the compiler or runtime: COMPILER.md and RUNTIME.md, and the rule in
  TOOLING.md §4 (bootstrap fixed point and all tests green before anything is done).
