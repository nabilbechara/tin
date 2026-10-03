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
