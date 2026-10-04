# Targets and porting

| target | role | status | binary | notes |
|---|---|---|---|---|
| linux-arm64 | production, benchmarks | complete: all tests pass, self-hosts, server passes conformance; tested natively in CI | ELF PIE linked to glibc ≥ 2.34 (tested on 2.36 and 2.41) | container limits, graceful shutdown, `examples/k8s/` |
| linux-amd64 | production, benchmarks | complete: all strict and regression tests pass and it self-hosts; tested natively in CI | ELF PIE (x86-64), glibc ≥ 2.34 | performance benchmarks on dedicated x86-64 hardware remain pending |
| darwin-arm64 | development only | complete | Mach-O, ad-hoc signed, linked to libSystem | the original target |

**Platform roles.** Linux is the platform Tin programs are deployed on and the only one
whose performance is a reference: server behaviour (epoll, `SO_REUSEPORT` accept, cgroup
limits, graceful shutdown in containers) and benchmark numbers are judged on Linux.
macOS arm64 is a development platform: the compiler, the tests and `tin run` must keep
working there (it is a native CI gate), but it is not a deployment target, macOS-only
behaviour is never a reason for a design decision, and macOS numbers are never quoted as
results (docs/PERFORMANCE.md, "Benchmark policy").

Choose a target with `tin build --target T` or `tinc -target T`; the default is the
machine the compiler runs on. One compiler binary contains every backend.

## 1. What changes per target

Source code does not change. Differences live in three places:

1. **The backend**: `gen.tin` + `asm.tin` for arm64, `gen_x64.tin` + `asm_x64.tin` for
   x86-64. Everything before code generation (parsing, checking, generics, regions,
   inlining, LICM) is shared.
2. **The linker**: `macho.tin`, `elf.tin` (arm64), `elf_x64.tin`.
3. **Platform library files**: `NAME_darwin.tin`, `NAME_linux.tin`,
   `NAME_linux_arm64.tin`, `NAME_linux_amd64.tin` next to `NAME.tin`, loaded
   automatically for the target. Today: `runtime_*`, `anvil_*`, `seal_*`.

Calling-convention differences inside one architecture (arm64): Apple passes variadic C
arguments on the stack, Linux (AAPCS64) in registers; Apple reserves x18. Both are
handled in `gen.tin` by `tgt_linux`.

## 2. Linux arm64 executables

- PIE (`ET_DYN`), interpreter `/lib/ld-linux-aarch64.so.1`, `DT_NEEDED` libc.so.6 (and
  libm.so.6 only if the program imports a libm function, which the standard library no
  longer does: the math package is Tin and `sqrt`, `floor` ... are instructions), SysV `DT_HASH`, `BIND_NOW`, one `R_AARCH64_GLOB_DAT` per imported function,
  no PLT, no section headers, segments aligned to 64 KiB.
- `_start` calls `__libc_start_main(main, argc, argv, 0, 0, rtld_fini, stack_end)`.
- No symbol versions are emitted. On arm64, glibc binds unversioned references to the
  base version GLIBC_2.17, which is correct for every function used.
- Minimum glibc: 2.34 (the `stat`/`lstat`/`fstat` symbols appeared in 2.33, and
  libpthread was merged into libc in 2.34). Debian 12+, Ubuntu 22.04+, RHEL 9+.
- musl (Alpine) is not supported (dynamic loader and symbol differences); use
  `debian:bookworm-slim` or a distroless glibc image.

## 3. Linux amd64

The plan (`notes/plan_linux.md`) and the work log (`notes/x64_progress.md`):
- System V ABI (rdi, rsi, rdx, rcx, r8, r9; xmm0–7; `al` = vector registers for variadic
  calls). Core context in r15; rbp kept as the frame pointer.
- `/lib64/ld-linux-x86-64.so.2`, `R_X86_64_GLOB_DAT`, and Verneed records, because
  unversioned references bind to the oldest symbol version on x86-64 (for example
  `realpath@GLIBC_2.2.5`).
- Layout differences: `struct epoll_event` is packed (12 bytes), `st_mode` is at offset
  24.
- `seal.Sha256` uses the portable code until SHA-NI is added (also on arm64 CPUs without
  the SHA-2 instructions, detected through `AT_HWCAP`).
- Correctness and self-hosting run natively on GitHub's `ubuntu-24.04` x86-64 runner.
  `tools/x64fuzz/linuxtest_amd64.sh` also checks the strict and regression suites in a
  container, emulated when the host is arm64. Dedicated x86-64 performance benchmarks
  remain pending.

## 4. Containers and Kubernetes

`examples/k8s/` has a Dockerfile, a Deployment + Service manifest and a README.

- Build from source in Docker with the multi-stage example; no host compiler is needed.
  The published builder supports amd64 and arm64; see [DISTRIBUTION.md](DISTRIBUTION.md).
  Or cross-compile on a Mac: `tin build --target linux-arm64 app.tin -o bin/linux/app`.
- Image: `FROM debian:bookworm-slim`, copy the binary, run as a non-root user.
- `anvil.Serve(":8080", h)` binds 0.0.0.0; `$PORT` overrides the port.
- Cores: anvil runs `hearth.Cores()` event loops. On Linux, `hearth.Cores()` is the
  smallest of the online CPUs, the affinity mask (cpuset) and the cgroup CPU quota
  rounded up (v2 `cpu.max`, else v1 `cpu.cfs_quota_us / cpu.cfs_period_us`); never 0.
  The cgroup is the process's own (from `/proc/self/cgroup` and `/proc/self/mountinfo`, so
  private and host cgroup namespaces both work), and the smallest limit over it and its
  ancestors counts. The count is computed once, before core threads pin themselves.
  `TIN_CORES` lowers it.
- Pinning: core threads pin themselves to CPUs only when they map one-to-one onto the
  allowed CPUs, or when `TIN_PIN=1`.
- Memory: `hearth.MemLimit()` reads the cgroup limit the same way (v2 `memory.max`, else v1
  `memory.limit_in_bytes`; 0 when unlimited). The per-core pool chunk (normally 4 MiB)
  shrinks to fit it (`hearth.PoolChunk()`; `hearth.PoolCapacity()` is the size in use). Idle connections cost about 96 bytes.
- SIGTERM and SIGINT are blocked in every thread and read by core 0 from its event loop
  (signalfd on Linux, kqueue `EVFILT_SIGNAL` on macOS), so no asynchronous handler runs.
  Every core then stops accepting and finishes in-flight requests (responses carry
  `Connection: close`); idle keep-alive connections stay open until they send a request or
  the grace period ends. At the end of the grace period (`TIN_GRACE` seconds, default 25, below
  Kubernetes' 30 s `terminationGracePeriodSeconds`) every core cancels the work it still has with
  `draining`: a request that waits wakes with `canceled: draining`, answers and finishes, and the
  process exits 0. Code that never waits cannot see the cancel yet (safepoints, #234), so the
  process exits at most one second later regardless.

## 5. Porting to another target

1. Add a target name in `set_target` (main.tin) and its flags.
2. A backend: instruction list + encoder (+ printer for `-S`) + code generator over the
   lowered AST (see COMPILER.md §7 for what the arm64 one does).
3. A linker for the object format.
4. Platform files: `runtime_<os>.tin` with every helper of RUNTIME.md §8 (and, per CPU,
   `rt_task_init`, plus the hand-assembled `rt_task_swap` in the backend), the event-loop
   functions for anvil (`ev_init`, `ev_level`, `ev_conn`, `ev_conn_write`,
   `ev_conn_read`, `ev_timer`, `ev_timer_ack`, `ev_wait`, `ev_fd`, `ev_writable`,
   `ev_hangup`, `ownListener`, and for shutdown `ev_signals`, `ev_signal`, `ev_signal_ack`,
   `ev_drain_timer`), and the compiler's own `host_<os>.tin`.
5. Verify constants and layouts by compiling C probes on the target, as in
   `notes/linux_probe/`, and record them like `notes/linux_abi.md`.
6. Tests: every `tests/v2` program must produce the same output on every target; the
   compiler must self-host there.

## Linux DNS contract

Linux uses Tin's resolver rather than glibc getaddrinfo: `/etc/hosts` first, then
`/etc/resolv.conf` nameservers/search/domain and ndots/timeout/attempts/rotate options.
A and AAAA use nonblocking UDP, with TCP fallback for truncation; every wait inside a
request is limited by its deadline. Numeric IPv6 addresses and scope IDs are supported.
The systemd-resolved stub works through its resolv.conf address. NSS modules such as
mdns, ldap and nss-resolve are unsupported. Tin prefers IPv4 and returns the first usable
address rather than glibc's RFC 6724 sorting; it performs no IDNA conversion, implicit
hostname search-domain inference or answer caching. Bounds/defaults are in
[the wire contract](STDLIB.md#wire). macOS keeps its existing libSystem DNS behavior.
