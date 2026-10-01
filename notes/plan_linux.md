# Plan: Tin on Linux (arm64, then amd64)

Status: proposal for review. Owner: selfhost/, lib/ (all packages that call the OS),
Makefile, seed/, tools/. Rule at every step: macOS stays green (`make bootstrap` fixed
point, `make test` passing) before the next step starts.

## Step 0: ready for git, without git

- `.gitignore` (bin/, scratch output); every generated file reproducible (`make`,
  `tools/gendoc.py`); seeds per host: `seed/tinc-darwin-arm64`, later
  `seed/tinc-linux-arm64`, `seed/tinc-linux-amd64` (the Makefile picks the host's).
- Tests and tools stop using machine-specific paths (`/private/tmp/claude-501/...` in
  the flume/quarry/wire tests becomes a per-run directory under `/tmp`, which both systems
  have).
- Moving into git later is then `git init && git add -A && git commit`.

## Phase 1: linux-arm64

### 1.1 Target plumbing (no behavior change on macOS)

- `tinc -target darwin-arm64|linux-arm64|linux-amd64` (default: the host). The target
  picks the object writer, the calling-convention details and the library files.
- Per-target library files: loading `lib/X.tin` also loads `lib/X_<os>.tin` when it
  exists; directory packages skip `*_<otheros>.tin`.
- One OS layer: `lib/runtime_darwin.tin` / `lib/runtime_linux.tin` hold every OS
  extern, constant and struct layout behind `rt_` helpers (`rt_errno`, `rt_sockaddr_in`,
  `rt_mono_ns`, `rt_wall_ns`, `rt_random`, `rt_exe_path`, `rt_pin_core`, `rt_stat_*`,
  `rt_dirent_name`...). Packages that call the OS today (anvil, relay, hearth, wire, quarry,
  flume, tide, herald, seal, dice, crucible) switch to these helpers, so only the two
  runtime files differ per OS. Audit: 98 distinct libc functions; the verified mapping
  and layouts are in notes/linux_abi.md (being produced now).
- An event-poller layer in the runtime used by anvil and relay (and by v0.4 later):
  `rt_poll_new/add/mod/del/wait` with normalized events, plus timers and wakers.
  darwin: kqueue, EVFILT_TIMER, pipes. linux: epoll (edge-triggered), timerfd, eventfd.
  Never io_uring.

### 1.2 Code generation differences

- Variadic C calls: on Linux the variadic arguments go in registers like any others (the
  AAPCS64 standard); `store_varargs` becomes darwin-only.
- C symbol names lose the leading underscore; `-S` prints GNU-as syntax for Linux
  (`:lo12:` instead of `@PAGEOFF`).
- Entry: a `_start` that calls `__libc_start_main(main, argc, argv, 0, 0, rtld_fini,
  stack_end)`, as glibc's crt1 does; `main(argc, argv)` is unchanged.

### 1.3 ELF writer (selfhost/elf.tin, next to macho.tin)

- A position-independent executable (ET_DYN: our code is already PC-relative) with
  PT_PHDR, PT_INTERP (/lib/ld-linux-aarch64.so.1), PT_LOAD R / RX / RW, PT_DYNAMIC,
  PT_GNU_STACK (non-executable).
- Dynamic section: DT_NEEDED libc.so.6 and libm.so.6, DT_HASH, DT_SYMTAB/STRTAB,
  DT_RELA with R_AARCH64_GLOB_DAT for every imported function's GOT slot (the same GOT
  the Mach-O path binds), R_AARCH64_RELATIVE wherever Mach-O needs a rebase, DT_FLAGS
  BIND_NOW. No PLT: calls go through the GOT as on macOS. No code signing.
- Backtraces: our function symbols go into the dynamic symbol table, so `dladdr` names
  frames on Linux too.

### 1.4 Runtime on Linux

- errno via `__errno_location`; all constants and layouts per notes/linux_abi.md
  (sockaddr_in without the length byte, addrinfo's field order, stat, dirent64).
- Clocks: `clock_gettime`; randomness: `getrandom`; executable path: readlink of
  `/proc/self/exe`; thread placement: `sched_setaffinity` pins core i to the i-th CPU of
  the allowed set (replacing the macOS QoS hint).

### 1.5 anvil and relay on Linux

- anvil: epoll (EPOLLET) per core; every core opens its own SO_REUSEPORT listener on the
  same address and accepts its own connections, so the kernel spreads connections and
  there is no handoff pipe (macOS keeps the core-0 handoff, since its SO_REUSEPORT does not
  balance). OnTick uses timerfd; relay wakers use eventfd.

### 1.6 Containers and Kubernetes

- `hearth.Cores()` = min(online CPUs, CPUs in the sched_getaffinity mask, ceil(cgroup
  quota / period)), reading cgroup v2 `/sys/fs/cgroup/cpu.max` and cgroup v1
  `cpu.cfs_quota_us` / `cpu.cfs_period_us`. `TIN_CORES` still overrides downward only.
- Memory: read the limit (v2 `memory.max`, v1 `memory.limit_in_bytes`); the per-core
  pool chunk size and cached-chunk count shrink so cores × pool stays under a fraction
  of the limit (default 50%).
- SIGTERM, without async signal handlers (a handler can run on any thread, where x28 is
  not a core context): all threads block SIGTERM; core 0 receives it through signalfd
  (Linux) or EVFILT_SIGNAL (macOS) in its event loop, then tells every core through relay
  to stop accepting (close listeners), finish in-flight requests, answer with
  `Connection: close`, flush, and exit, within `TIN_GRACE` (default 25 s, below the
  Kubernetes 30 s default).
- `anvil.Serve(":8080", h)` binds 0.0.0.0; if `$PORT` is set it replaces the port.
- Ship `examples/k8s/Dockerfile` (debian:bookworm-slim, the cross-compiled binary only)
  and `examples/k8s/deployment.yaml` (Deployment with CPU/memory limits, readiness and
  liveness probes on a /healthz route, terminationGracePeriodSeconds, a Service).

### 1.7 Verification and gate

- Cross-compile on the Mac, run in a native arm64 debian:bookworm-slim container: every
  tests/v2 program, diffed against the macOS outputs (the same .out files), and the
  `_bad` tests' errors.
- Self-hosting on Linux: cross-compile tinc for linux-arm64, then inside the container
  it compiles itself twice and the two binaries must be identical; the Linux seed is
  checked in only after that passes.
- anvil conformance suite (26 cases) in the container.
- Benchmark in the container (wrk inside the same container): anvil vs Go net/http and
  fasthttp, /json and /plaintext, 1/2/4 cores, req/s and p99.
- GATE: all tests pass in the container and anvil beats Go there on req/s and p99. I
  report the numbers, then continue.

## Phase 2: linux-amd64

- New backend files `selfhost/gen_x64.tin` and `selfhost/asm_x64.tin`; the passes that
  work on the syntax tree (inline, appends, LICM, prefetch, region, generics) are shared.
  `generate()` dispatches on the target architecture.
- Calling convention: System V (rdi, rsi, rdx, rcx, r8, r9, xmm0–7; al = number of vector
  registers for variadic calls). Core context in r15 (callee-saved, as Go keeps g in
  r14). Frame pointer rbp kept for backtraces.
- Registers: homes in rbx, r12–r14 (callee-saved) and the caller-saved set in leaf
  functions; xmm registers are all caller-saved in System V, so float locals live across
  calls in stack slots.
- x86 rules: idiv uses rdx:rax, variable shifts use cl, two-operand forms, compares set
  flags for jcc/setcc/cmov. Optimizations map over: csel to cmov, madd to imul+add or
  lea, prefetchw stays, bounds checks to cmp + jae to a cold stub.
- Encoder: REX, ModRM/SIB, disp8/disp32, RIP-relative addressing for globals, strings
  and the GOT, rel32 branches with short-form relaxation. The ELF writer gains amd64
  (R_X86_64_GLOB_DAT, R_X86_64_RELATIVE, /lib64/ld-linux-x86-64.so.2). The hardware
  SHA-256 path uses SHA-NI where the CPU has it, else the portable code.
- Differential testing: every test gives identical output on darwin-arm64, linux-arm64
  and linux-amd64. The encoder is fuzzed against `objdump -d` (random instructions,
  compare the disassembly with our printer).
- Correctness runs in an emulated amd64 container. Benchmarks need real x86-64 Linux
  hardware (the full bench/ suite and anvil vs Go on the same machine).
- GATE: every test passes on all three targets and Tin beats Go on x86-64, with any loss
  reported with its cause.

## Rough size

Phase 1: 3–4 sessions (ELF and the OS layer are most of it). Phase 2: 5–8 sessions (the
backend and getting its code as fast as the arm64 backend's).

## Needs from the user

1. OK to pull `debian:bookworm-slim` (arm64, and amd64 later) and apt-get install wrk,
   gcc and binutils inside throwaway containers.
2. For the phase 2 benchmark gate: an x86-64 Linux machine (SSH access to a VM or a
   bare-metal box). Without one I can complete everything except that gate.
