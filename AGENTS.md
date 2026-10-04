# Agent instructions

Read [docs/AGENT_PRIMER.md](docs/AGENT_PRIMER.md) first: the language, the build commands
and the files you must not touch. The CI and regression policy is in [docs/CI.md](docs/CI.md).

## Platforms: Linux is production, macOS is development

- **Linux arm64 and Linux x86-64 are the production platforms.** Tin programs are deployed
  on Linux, and server behaviour (epoll, `SO_REUSEPORT`, cgroup limits, signals in
  containers, glibc) is designed and judged there. If behaviour differs between macOS and
  Linux, Linux decides.
- **macOS arm64 is for development only:** writing, building and testing on a Mac. The
  compiler, the strict suite and `tin run` must keep working on macOS (it is a native CI
  gate), but don't add macOS-only features, don't treat macOS as a deployment target, and
  don't justify a design with macOS behaviour.

## Benchmarks are Linux

- **Never quote macOS numbers as results.** That covers Linux containers on a Mac (Docker
  Desktop runs a VM) and emulated CPUs. This applies to PR descriptions, README,
  docs/PERFORMANCE.md and release notes.
- **"No regression" or "faster" claims need Linux numbers:** Tin and Go (or before and
  after) on the same Linux machine in the same run, interleaved, as medians with the
  ratio. State the machine, CPU, kernel and Go version.
- **For PRs that touch performance,** run `.github/workflows/bench-linux.yml` (Actions,
  Run workflow, or a PR that changes `bench/`) and cite its summary. On GitHub's shared
  runners only the ratios are meaningful.
- The full rules are in [docs/PERFORMANCE.md](docs/PERFORMANCE.md#benchmark-policy).

## Tin 1: rules for parallel work (strict)

Several agents work on the [Tin 1 milestone](https://github.com/yasserreslan/tin/milestone/1)
at once (filter `label:tin-1`; titles start with [SYNTAX] or [SEMANTICS]). Each issue states
its wave, dependencies, interface partners and hot files. These rules are not optional.

1. **Work only on an issue assigned to you.** To take another, ask its assignee in the issue
   first.
2. **One issue, one branch, one worktree.** Branch `tin1/<issue>-<slug>` from `origin/main`, in
   its own `git worktree`. Never work in a checkout another agent uses.
3. **Open a draft PR within the first hour** and keep its "Touches hot files" list current, so
   others see what you are changing. Use `.github/pull_request_template.md`.
4. **Start only when the issue's "Needs" are merged.** Stack on an open PR only when its author
   agrees, and say "Part of #N" until the PR targets `main`. Only a PR into `main` says `Fixes #N`.
5. **Interface first for paired issues.** Issues that share a runtime or compiler interface
   (each lists its partners) begin with one small PR that fixes the names and data layout
   (a `notes/` section or stub functions), agreed by every partner, before any of them builds on
   it. Do not change an agreed interface without the partners' approval in that PR.
6. **Hot files** (`selfhost/check.tin`, `lower.tin`, `region.tin`, `parse.tin`, `gen*.tin`,
   `inline.tin`, `lib/runtime/runtime*.tin`, `lib/anvil/anvil*.tin`): add code next to related
   code; never move, rename or reformat existing code; no drive-by cleanups.
7. **Small PRs, rebased often.** `main` requires an up-to-date branch; update and merge within a
   day of green CI. A PR that waits more than two days gets rebased or split.
8. **Seeds.** Changes must compile with the checked-in seeds. A seed refresh is announced in the
   milestone, done by one person, and merged alone.
9. **Syntax freeze (#226).** When the conversion is announced: merge what is ready, open no new
   PRs in the old syntax, and after the conversion commit run `tin fix -edition 1` on every open
   branch before continuing.
10. **Never weaken or delete a test to get green**, and never add a `known_failure` to pass CI
    (docs/CI.md). Benchmarks follow the rules above.
11. **Report blockers in the issue**, naming the issue or PR you are waiting for, instead of
    working around another agent's area.
