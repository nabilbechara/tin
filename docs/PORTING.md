# Targets and porting

| target | status | binary | notes |
|---|---|---|---|
| darwin-arm64 | complete | Mach-O, ad-hoc signed, linked to libSystem | the original target |
| linux-arm64 | working: all strict tests pass, self-hosts, server passes conformance | ELF PIE linked to glibc ≥ 2.34 (tested on 2.36 and 2.41) | container features in progress |
| linux-amd64 | in progress | ELF PIE (x86-64) | encoder done and fuzzed; code generator and linker being written |

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

- PIE (`ET_DYN`), interpreter `/lib/ld-linux-aarch64.so.1`, `DT_NEEDED` libc.so.6 and
  libm.so.6, SysV `DT_HASH`, `BIND_NOW`, one `R_AARCH64_GLOB_DAT` per imported function,
  no PLT, no section headers, segments aligned to 64 KiB.
- `_start` calls `__libc_start_main(main, argc, argv, 0, 0, rtld_fini, stack_end)`.
- No symbol versions are emitted. On arm64, glibc binds unversioned references to the
  base version GLIBC_2.17, which is correct for every function used.
- Minimum glibc: 2.34 (the `stat`/`lstat`/`fstat` symbols appeared in 2.33, and
  libpthread was merged into libc in 2.34). Debian 12+, Ubuntu 22.04+, RHEL 9+.
- musl (Alpine) is not supported (dynamic loader and symbol differences); use
  `debian:bookworm-slim` or a distroless glibc image.

## 3. Linux amd64 (in progress)

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
- Correctness is tested in an emulated amd64 container. Benchmarks need real x86-64
  hardware.

## 4. Containers and Kubernetes

Status: the code below is landing now; the Dockerfile and manifest come with it.

- Build on a Mac: `tin build --target linux-arm64 app.tin -o bin/linux/app`.
- Image: `FROM debian:bookworm-slim`, copy the binary, run as a non-root user.
- `anvil.Serve(":8080", h)` binds 0.0.0.0; `$PORT` overrides the port.
- Cores: anvil runs `hearth.Cores()` event loops. On Linux, `hearth.Cores()` is the
  smallest of the online CPUs, the affinity mask (cpuset) and the cgroup CPU quota
  rounded up (v2 `cpu.max`, else v1 `cpu.cfs_quota_us / cpu.cfs_period_us`); never 0.
  `TIN_CORES` lowers it.
- Pinning: core threads pin themselves to CPUs only when they map one-to-one onto the
  allowed CPUs, or when `TIN_PIN=1`.
- Memory: `hearth.MemLimit()` reads the cgroup limit (v2 `memory.max`, else v1
  `memory.limit_in_bytes`; 0 when unlimited). The per-core pool chunk (normally 4 MiB)
  shrinks to fit it (`hearth.PoolChunk()`). Idle connections cost about 96 bytes.
- SIGTERM and SIGINT are blocked in every thread and read by core 0 from its event loop
  (signalfd on Linux, kqueue `EVFILT_SIGNAL` on macOS), so no asynchronous handler runs.
  Every core then stops accepting, finishes in-flight requests, closes idle connections
  and exits within `TIN_GRACE` seconds (default 25, below Kubernetes' 30 s
  `terminationGracePeriodSeconds`).

## 5. Porting to another target

1. Add a target name in `set_target` (main.tin) and its flags.
2. A backend: instruction list + encoder (+ printer for `-S`) + code generator over the
   lowered AST (see COMPILER.md §7 for what the arm64 one does).
3. A linker for the object format.
4. Platform files: `runtime_<os>.tin` with every helper of RUNTIME.md §8, the event-loop
   functions for anvil (`ev_init`, `ev_level`, `ev_conn`, `ev_conn_write`,
   `ev_conn_read`, `ev_timer`, `ev_timer_ack`, `ev_wait`, `ev_fd`, `ev_writable`,
   `ev_hangup`, `ownListener`, and for shutdown `ev_signals`, `ev_signal`, `ev_signal_ack`,
   `ev_drain_timer`), and the compiler's own `host_<os>.tin`.
5. Verify constants and layouts by compiling C probes on the target, as in
   `notes/linux_probe/`, and record them like `notes/linux_abi.md`.
6. Tests: every `tests/v2` program must produce the same output on every target; the
   compiler must self-host there.
