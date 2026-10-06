# Linux libc removal inventory (issue #125)

This is the source inventory for both Linux targets, including legacy `extern fn`,
strict `extern func`, and imports inserted by the ELF writers. It describes possible
imports across all programs, rather than the imports of only one executable. Darwin
platform files and package test files are excluded. Call-site files include declaration
owners (compiler-generated calls can have no textual call site).

Phases follow the revised plan: **0** inventory/baseline, **1** number conversion,
**2** memory, **3** syscall backend, **4** DNS/helpers, **5** startup/threads/static cutover.
Linux remains dynamically linked through phase 4; macOS retains its supported libSystem
interfaces. `intrinsic` means a declaration already lowers to a hardware instruction;
it is not a Linux dynamic import. Retain `removed` rows as tombstones to catch regressions.
Verification entries describe the required acceptance coverage, including tests to add
in the assigned phase; they do not claim that future coverage already exists.

Run `python3 tools/ci/libc_inventory.py` or the automatically discovered
`tools/ci/test_libc_inventory.py`. Update the source files when an owner moves, and mark
an entry removed only when no Linux declaration or linker-added import remains.

| Symbol | Call-site files | Phase | Status | Replacement | Verification |
|---|---|---:|---|---|---|
| `__errno_location` | `toolchain/runtime/syscalls_linux.tin` | 5 | removed | The syscall leaf returns -errno; the seed refresh (#339) made the libc fallback dead | syscall_check.py forbids syscall imports; static_check.py: `bin/tinc` and every program are static |
| `__libc_start_main` | `toolchain/compiler/elf.tin`, `toolchain/compiler/elf_x64.tin` | 5 | removed | Tin _start reads argc/argv/envp/auxv; the ELF writers emit only static executables and stop the link if a program would import anything | Bootstrap fixed point in an empty root; static_check.py (no PT_INTERP/PT_DYNAMIC, `FROM scratch`) |
| `accept` | `packages/anvil/anvil.tin`, `packages/wire/wire.tin` | 3 | removed | accept raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `atoi` | `packages/anvil/anvil.tin` | 1 | removed | Tin decimal integer parser | Anvil environment integer parsing cases (phase 1) |
| `bind` | `packages/anvil/anvil.tin`, `packages/wire/wire.tin` | 3 | removed | bind raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `calloc` | `toolchain/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `ceil` | `toolchain/std/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | toolchain/tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `chdir` | `toolchain/std/quarry/quarry.tin` | 3 | removed | chdir raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `clock_gettime` | `toolchain/runtime/runtime_linux.tin` | 3 | removed | clock_gettime raw syscall (per-architecture ABI) | Monotonic/wall-clock Go twin; tools/ci/task_check.py deadlines (phases 3/5) |
| `close` | `packages/anvil/anvil.tin`, `toolchain/std/flume/flume.tin`, `packages/mysql/mysql.tin`, `packages/postgres/postgres.tin`, `toolchain/std/quarry/quarry.tin`, `packages/redis/redis.tin`, `toolchain/runtime/runtime_linux.tin`, `lib/std.tin`, `packages/websocket/websocket.tin`, `packages/wire/wire.tin` | 3 | removed | close raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `closedir` | `toolchain/std/quarry/quarry.tin`, `toolchain/compiler/main.tin` | 3 | removed | Tin directory cleanup and close syscall | toolchain/tests/v2/quarry.tin; directory refill/unknown-type/symlink cases; bootstrap (phase 3) |
| `connect` | `packages/wire/wire.tin` | 3 | removed | connect raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `creat` | `lib/std.tin` | 3 | removed | openat with create/truncate flags | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `dladdr` | `toolchain/runtime/runtime.tin` | 4 | removed | Linker-emitted Tin function symbol table | Exact panic backtrace and function-boundary tests (phase 4) |
| `epoll_create1` | `packages/anvil/anvil_linux.tin` | 3 | removed | epoll_create1 raw syscall (per-architecture ABI) | tools/ci/http_check.py and task_check.py (phase 3) |
| `epoll_ctl` | `packages/anvil/anvil_linux.tin` | 3 | removed | epoll_ctl raw syscall (per-architecture ABI) | tools/ci/http_check.py and task_check.py (phase 3) |
| `epoll_wait` | `packages/anvil/anvil_linux.tin` | 3 | removed | epoll_wait raw syscall (per-architecture ABI) | tools/ci/http_check.py and task_check.py (phase 3) |
| `exit` | `toolchain/std/crucible/crucible.tin`, `toolchain/runtime/runtime.tin`, `lib/std.tin` | 3 | removed | exit_group for process termination; exit for thread termination | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `fcntl` | `packages/anvil/anvil.tin`, `toolchain/std/relay/relay.tin`, `toolchain/runtime/runtime.tin`, `packages/wire/wire.tin` | 3 | removed | fcntl raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `floor` | `toolchain/std/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | toolchain/tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `free` | `toolchain/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `freeaddrinfo` | `packages/wire/wire.tin` | 4 | removed | Tin resolver result ownership | DNS repeated lookup memory stability (phase 4) |
| `fstat` | `toolchain/std/quarry/quarry.tin` | 3 | removed | Per-architecture fstat syscall and kernel layout | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getaddrinfo` | `packages/wire/wire.tin` | 4 | removed | Task-based hosts/resolv.conf UDP/TCP DNS resolver | tools/ci/dns_check.py fake DNS contract (phase 4) |
| `getauxval` | `toolchain/runtime/vdso_linux.tin`, `toolchain/std/seal/seal_linux.tin`, `toolchain/compiler/host_linux.tin` | 5 | removed | Initial-stack auxv lookup (`rt_getauxval`; the compiler's `host_auxval`) | toolchain/tests/v2/seal.tin (AT_HWCAP); vDSO clock (AT_SYSINFO_EHDR); page size (AT_PAGESZ); bootstrap (phase 5) |
| `getcwd` | `toolchain/std/quarry/quarry.tin` | 3 | removed | getcwd raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getenv` | `packages/anvil/anvil.tin`, `toolchain/std/quarry/quarry.tin`, `toolchain/runtime/memory_rt.tin`, `toolchain/runtime/runtime_linux.tin`, `toolchain/compiler/main.tin` | 5 | removed | Tin environment initialized from envp (`rt_getenv`; the compiler's `host_getenv`) | toolchain/tests/v2/quarry.tin; compiler TIN_ROOT; cgroup/HTTP configuration (phase 5) |
| `gethostname` | `toolchain/std/quarry/quarry.tin` | 4 | removed | uname nodename | toolchain/tests/v2/quarry.tin and uname comparison (phase 4) |
| `getpid` | `toolchain/std/quarry/quarry.tin` | 3 | removed | getpid raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getrandom` | `toolchain/runtime/runtime_linux.tin` | 3 | removed | getrandom raw syscall (per-architecture ABI) | toolchain/tests/v2/dice.tin and seal.tin; interrupted/short reads (phase 3) |
| `getsockname` | `packages/wire/wire.tin` | 3 | removed | getsockname raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getsockopt` | `packages/wire/wire.tin` | 3 | removed | getsockopt raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `gmtime_r` | `packages/anvil/anvil.tin` | 4 | removed | Tin UTC calendar decomposition | UTC calendar boundary Go twin; HTTP Date (phase 4) |
| `isatty` | `toolchain/runtime/runtime.tin` | 4 | removed | ioctl TCGETS | TTY/pipe/file probes (phase 4) |
| `listen` | `packages/anvil/anvil.tin`, `packages/wire/wire.tin` | 3 | removed | listen raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `lstat` | `toolchain/std/quarry/quarry.tin` | 3 | removed | newfstatat with symlink-no-follow flag | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `malloc` | `toolchain/std/relay/relay.tin`, `toolchain/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memchr` | `packages/anvil/anvil.tin`, `toolchain/std/ore/ore.tin`, `toolchain/std/quarry/quarry.tin`, `toolchain/std/twine/twine.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memcmp` | `toolchain/std/ore/ore.tin`, `toolchain/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memcpy` | `toolchain/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memmove` | `toolchain/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memset` | `toolchain/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `mkdir` | `toolchain/std/quarry/quarry.tin` | 3 | removed | mkdir raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `mmap` | `toolchain/runtime/memory.tin` | 3 | removed | mmap raw syscall (per-architecture ABI) | Mapping/error/page-size tests; task stacks (phase 3) |
| `mprotect` | `toolchain/runtime/runtime.tin` | 3 | removed | mprotect raw syscall (per-architecture ABI) | Task guard-page and issue #175 tests (phase 3) |
| `nanosleep` | `toolchain/runtime/runtime.tin`, `toolchain/std/tide/tide.tin` | 3 | removed | nanosleep raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `open` | `packages/anvil/anvil.tin`, `toolchain/std/flume/flume.tin`, `toolchain/std/quarry/quarry.tin`, `toolchain/runtime/runtime_linux.tin`, `lib/std.tin` | 3 | removed | openat | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `opendir` | `toolchain/std/quarry/quarry.tin`, `toolchain/compiler/main.tin` | 3 | removed | Tin directory handle and getdents64 buffer | toolchain/tests/v2/quarry.tin; directory refill/unknown-type/symlink cases; bootstrap (phase 3) |
| `pipe` | `packages/anvil/anvil.tin`, `toolchain/std/relay/relay.tin`, `toolchain/runtime/runtime.tin` | 3 | removed | pipe2 | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `poll` | `toolchain/std/relay/relay.tin`, `toolchain/runtime/runtime.tin`, `packages/wire/wire.tin` | 3 | removed | ppoll with timespec timeout | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `posix_memalign` | `toolchain/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `pthread_attr_init` | `toolchain/runtime/runtime.tin` | 5 | removed | Tin thread stack configuration (`rt_thread_start` in runtime_linux.tin) | tools/ci/thread_check.py stacks, guard and reaping (phase 5) |
| `pthread_attr_setstacksize` | `toolchain/runtime/runtime.tin` | 5 | removed | Tin mmap stack and guard page | tools/ci/thread_check.py stacks, guard and reaping (phase 5) |
| `pthread_create` | `toolchain/runtime/runtime.tin` | 5 | removed | Raw clone (`rt_sys_clone` leaf) with parent-owned stacks and child trampoline | tools/ci/thread_check.py returning cores, masks, alternate stacks and child faults; task_check.py helper threads (phase 5) |
| `pthread_sigmask` | `toolchain/runtime/runtime_linux.tin` | 3 | removed | rt_sigprocmask with kernel sigset_t | tools/ci/http_check.py shutdown; per-thread signal-mask tests (phase 3) |
| `read` | `toolchain/runtime/runtime.tin`, `lib/std.tin` | 3 | removed | read raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `readdir` | `toolchain/std/quarry/quarry.tin`, `toolchain/compiler/main.tin` | 3 | removed | Tin linux_dirent64 parsing and buffer refills | toolchain/tests/v2/quarry.tin; directory refill/unknown-type/symlink cases; bootstrap (phase 3) |
| `readlink` | `toolchain/compiler/host_linux.tin` | 3 | removed | readlink raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `realloc` | `toolchain/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `realpath` | `toolchain/compiler/main.tin` | 4 | removed | Tin path canonicalization with symlink traversal | Compiler path discovery with symlinks and missing paths; bootstrap (phase 4) |
| `recv` | `packages/mysql/mysql.tin`, `packages/postgres/postgres.tin`, `packages/redis/redis.tin` | 3 | removed | recv raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `rename` | `toolchain/std/quarry/quarry.tin` | 3 | removed | rename raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `rint` | `toolchain/std/gauge/gauge.tin`, `toolchain/runtime/runtime.tin` | 0 | intrinsic | Hardware float intrinsic | toolchain/tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `rmdir` | `toolchain/std/quarry/quarry.tin` | 3 | removed | rmdir raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `round` | `toolchain/std/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | toolchain/tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `sched_getaffinity` | `toolchain/runtime/runtime_linux.tin` | 3 | removed | sched_getaffinity raw syscall (per-architecture ABI) | CPU mask/cgroup checks and sparse CPU IDs (phase 3) |
| `sched_setaffinity` | `toolchain/runtime/runtime_linux.tin` | 3 | removed | sched_setaffinity raw syscall (per-architecture ABI) | CPU pinning checks and sparse CPU IDs (phase 3) |
| `setenv` | `toolchain/std/quarry/quarry.tin` | 5 | removed | Tin owned environment update (`rt_setenv`) | toolchain/tests/v2/quarry.tin overwrite and ownership (phase 5) |
| `setsockopt` | `packages/anvil/anvil.tin`, `packages/wire/wire.tin` | 3 | removed | setsockopt raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `signal` | `packages/anvil/anvil.tin`, `toolchain/runtime/runtime_linux.tin` | 3 | removed | rt_sigaction and per-architecture signal return | Broken-pipe behavior; signal return; issue #175 handler (phases 3/5) |
| `signalfd` | `toolchain/runtime/runtime_linux.tin` | 3 | removed | signalfd4 | tools/ci/http_check.py shutdown (phase 3) |
| `snprintf` | `toolchain/runtime/runtime.tin` | 1 | removed | Tin precision float formatting and diagnostic text | tools/ci/number_check.py; existing bounds/core diagnostics |
| `socket` | `packages/anvil/anvil.tin`, `packages/wire/wire.tin` | 3 | removed | socket raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `sqrt` | `toolchain/std/dice/dice.tin`, `toolchain/std/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | toolchain/tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `stat` | `toolchain/std/quarry/quarry.tin` | 3 | removed | newfstatat pathname lookup | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `strcmp` | `toolchain/compiler/main.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `strerror` | `toolchain/std/flume/flume.tin`, `packages/mysql/mysql.tin`, `packages/postgres/postgres.tin`, `toolchain/std/quarry/quarry.tin`, `packages/redis/redis.tin`, `packages/websocket/websocket.tin`, `packages/wire/wire.tin` | 4 | removed | Per-OS Tin errno message table | toolchain/tests/v2/quarry.tin; exact network/file error messages (phase 4) |
| `strftime` | `packages/anvil/anvil.tin` | 4 | removed | Tin time formatting | UTC calendar boundary Go twin; HTTP Date (phase 4) |
| `strlen` | `toolchain/std/quarry/quarry.tin`, `toolchain/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `strtod` | `toolchain/runtime/runtime.tin`, `toolchain/compiler/lex.tin` | 1 | removed | Correctly rounded Tin float parser | tools/ci/number_check.py; toolchain/tests/v2/mint.tin; bootstrap fixed point |
| `sysconf` | `toolchain/runtime/runtime_linux.tin`, `toolchain/compiler/host_linux.tin` | 4 | removed | Affinity mask and cgroup CPU limits; page size via auxv | CPU quota/affinity tests; page-size kernels (phases 4/5) |
| `time` | `packages/anvil/anvil.tin` | 4 | removed | clock_gettime CLOCK_REALTIME | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 4) |
| `timerfd_create` | `packages/anvil/anvil_linux.tin` | 3 | removed | timerfd_create raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `timerfd_settime` | `packages/anvil/anvil_linux.tin` | 3 | removed | timerfd_settime raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `trunc` | `toolchain/std/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | toolchain/tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `uname` | `toolchain/compiler/main.tin` | 3 | removed | uname raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `unlink` | `toolchain/std/quarry/quarry.tin`, `lib/std.tin` | 3 | removed | unlink raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `unsetenv` | `toolchain/std/quarry/quarry.tin` | 5 | removed | Tin owned environment removal (`rt_unsetenv`) | toolchain/tests/v2/quarry.tin deletion (phase 5) |
| `usleep` | `packages/hearth/hearth.tin` | 4 | removed | nanosleep with interruption handling | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 4) |
| `write` | `toolchain/runtime/runtime.tin`, `lib/std.tin` | 3 | removed | write raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `_exit` | `toolchain/runtime/memory.tin`, `toolchain/runtime/runtime.tin` | 3 | removed | exit_group raw syscall | Fault/stack-overflow diagnostics and nonzero exit (issue #175) |
| `shutdown` | `packages/anvil/anvil.tin` | 3 | removed | shutdown raw syscall | HTTP conformance and graceful shutdown |
| `sigaction` | `toolchain/runtime/runtime.tin` | 3 | removed | rt_sigaction and per-architecture restorer | Existing native stack-overflow/bad-access probes; signal-return tests (phase 3) |
| `sigaltstack` | `toolchain/runtime/runtime.tin` | 3 | removed | sigaltstack raw syscall | Existing native per-thread stack-overflow probes (issue #175) |
| `munmap` | `toolchain/runtime/memory.tin` | 3 | removed | munmap raw syscall | memory_check.py; task_memory_check.py |
| `madvise` | `toolchain/runtime/runtime.tin` | 3 | removed | madvise raw syscall | task_memory_check.py after heavy burst |
| `syscall` | `toolchain/runtime/syscalls_linux.tin` | 5 | removed | Generated leaf uses svc/syscall directly; the fallback went with the seed refresh (#339) | syscall_check.py dynamic-import assertion; bootstrap |
