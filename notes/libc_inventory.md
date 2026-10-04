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
| `__errno_location` | `lib/runtime/syscalls_linux.tin` | 5 | active | Temporary seed fallback and libc environment errors; removed with environment cutover | syscall_check.py forbids syscall imports; static ELF checks in phase 5 |
| `__libc_start_main` | `selfhost/elf.tin`, `selfhost/elf_x64.tin` | 5 | active | Tin _start reads argc/argv/envp/auxv | Bootstrap fixed point; argv/environment and static ELF/container checks (phase 5) |
| `accept` | `lib/anvil/anvil.tin`, `lib/wire/wire.tin` | 3 | removed | accept raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `atoi` | `lib/anvil/anvil.tin` | 1 | removed | Tin decimal integer parser | Anvil environment integer parsing cases (phase 1) |
| `bind` | `lib/anvil/anvil.tin`, `lib/wire/wire.tin` | 3 | removed | bind raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `calloc` | `lib/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `ceil` | `lib/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `chdir` | `lib/quarry/quarry.tin` | 3 | removed | chdir raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `clock_gettime` | `lib/runtime/runtime_linux.tin` | 3 | removed | clock_gettime raw syscall (per-architecture ABI) | Monotonic/wall-clock Go twin; tools/ci/task_check.py deadlines (phases 3/5) |
| `close` | `lib/anvil/anvil.tin`, `lib/flume/flume.tin`, `lib/mysql/mysql.tin`, `lib/postgres/postgres.tin`, `lib/quarry/quarry.tin`, `lib/redis/redis.tin`, `lib/runtime/runtime_linux.tin`, `lib/std.tin`, `lib/websocket/websocket.tin`, `lib/wire/wire.tin` | 3 | removed | close raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `closedir` | `lib/quarry/quarry.tin`, `selfhost/main.tin` | 3 | removed | Tin directory cleanup and close syscall | tests/v2/quarry.tin; directory refill/unknown-type/symlink cases; bootstrap (phase 3) |
| `connect` | `lib/wire/wire.tin` | 3 | removed | connect raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `creat` | `lib/std.tin` | 3 | removed | openat with create/truncate flags | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `dladdr` | `lib/runtime/runtime.tin` | 4 | removed | Linker-emitted Tin function symbol table | Exact panic backtrace and function-boundary tests (phase 4) |
| `epoll_create1` | `lib/anvil/anvil_linux.tin` | 3 | removed | epoll_create1 raw syscall (per-architecture ABI) | tools/ci/http_check.py and task_check.py (phase 3) |
| `epoll_ctl` | `lib/anvil/anvil_linux.tin` | 3 | removed | epoll_ctl raw syscall (per-architecture ABI) | tools/ci/http_check.py and task_check.py (phase 3) |
| `epoll_wait` | `lib/anvil/anvil_linux.tin` | 3 | removed | epoll_wait raw syscall (per-architecture ABI) | tools/ci/http_check.py and task_check.py (phase 3) |
| `exit` | `lib/crucible/crucible.tin`, `lib/runtime/runtime.tin`, `lib/std.tin` | 3 | removed | exit_group for process termination; exit for thread termination | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `fcntl` | `lib/anvil/anvil.tin`, `lib/relay/relay.tin`, `lib/runtime/runtime.tin`, `lib/wire/wire.tin` | 3 | removed | fcntl raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `floor` | `lib/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `free` | `lib/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `freeaddrinfo` | `lib/wire/wire.tin` | 4 | removed | Tin resolver result ownership | DNS repeated lookup memory stability (phase 4) |
| `fstat` | `lib/quarry/quarry.tin` | 3 | removed | Per-architecture fstat syscall and kernel layout | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getaddrinfo` | `lib/wire/wire.tin` | 4 | removed | Task-based hosts/resolv.conf UDP/TCP DNS resolver | tools/ci/dns_check.py fake DNS contract (phase 4) |
| `getauxval` | `lib/runtime/vdso_linux.tin`, `lib/seal/seal_linux.tin`, `selfhost/host_linux.tin` | 5 | active | Initial-stack auxv lookup | tests/v2/seal.tin; auxv/HWCAP/startup tests (phase 5) |
| `getcwd` | `lib/quarry/quarry.tin` | 3 | removed | getcwd raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getenv` | `lib/anvil/anvil.tin`, `lib/quarry/quarry.tin`, `lib/runtime/memory_rt.tin`, `lib/runtime/runtime_linux.tin`, `selfhost/main.tin` | 5 | active | Tin environment initialized from envp | tests/v2/quarry.tin; compiler TIN_ROOT; cgroup/HTTP configuration (phase 5) |
| `gethostname` | `lib/quarry/quarry.tin` | 4 | removed | uname nodename | tests/v2/quarry.tin and uname comparison (phase 4) |
| `getpid` | `lib/quarry/quarry.tin` | 3 | removed | getpid raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getrandom` | `lib/runtime/runtime_linux.tin` | 3 | removed | getrandom raw syscall (per-architecture ABI) | tests/v2/dice.tin and seal.tin; interrupted/short reads (phase 3) |
| `getsockname` | `lib/wire/wire.tin` | 3 | removed | getsockname raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `getsockopt` | `lib/wire/wire.tin` | 3 | removed | getsockopt raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `gmtime_r` | `lib/anvil/anvil.tin` | 4 | removed | Tin UTC calendar decomposition | UTC calendar boundary Go twin; HTTP Date (phase 4) |
| `isatty` | `lib/runtime/runtime.tin` | 4 | removed | ioctl TCGETS | TTY/pipe/file probes (phase 4) |
| `listen` | `lib/anvil/anvil.tin`, `lib/wire/wire.tin` | 3 | removed | listen raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `lstat` | `lib/quarry/quarry.tin` | 3 | removed | newfstatat with symlink-no-follow flag | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `malloc` | `lib/relay/relay.tin`, `lib/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memchr` | `lib/anvil/anvil.tin`, `lib/ore/ore.tin`, `lib/quarry/quarry.tin`, `lib/twine/twine.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memcmp` | `lib/ore/ore.tin`, `lib/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memcpy` | `lib/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memmove` | `lib/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `memset` | `lib/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `mkdir` | `lib/quarry/quarry.tin` | 3 | removed | mkdir raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `mmap` | `lib/runtime/memory.tin` | 3 | removed | mmap raw syscall (per-architecture ABI) | Mapping/error/page-size tests; task stacks (phase 3) |
| `mprotect` | `lib/runtime/runtime.tin` | 3 | removed | mprotect raw syscall (per-architecture ABI) | Task guard-page and issue #175 tests (phase 3) |
| `nanosleep` | `lib/runtime/runtime.tin`, `lib/tide/tide.tin` | 3 | removed | nanosleep raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `open` | `lib/anvil/anvil.tin`, `lib/flume/flume.tin`, `lib/quarry/quarry.tin`, `lib/runtime/runtime_linux.tin`, `lib/std.tin` | 3 | removed | openat | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `opendir` | `lib/quarry/quarry.tin`, `selfhost/main.tin` | 3 | removed | Tin directory handle and getdents64 buffer | tests/v2/quarry.tin; directory refill/unknown-type/symlink cases; bootstrap (phase 3) |
| `pipe` | `lib/anvil/anvil.tin`, `lib/relay/relay.tin`, `lib/runtime/runtime.tin` | 3 | removed | pipe2 | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `poll` | `lib/relay/relay.tin`, `lib/runtime/runtime.tin`, `lib/wire/wire.tin` | 3 | removed | ppoll with timespec timeout | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `posix_memalign` | `lib/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `pthread_attr_init` | `lib/runtime/runtime.tin` | 5 | active | Tin thread stack configuration | Thread stack/guard-page tests (phase 5) |
| `pthread_attr_setstacksize` | `lib/runtime/runtime.tin` | 5 | active | Tin mmap stack and guard page | Thread stack/guard-page tests (phase 5) |
| `pthread_create` | `lib/runtime/runtime.tin` | 5 | active | Raw clone with owned stacks and child trampoline | tools/ci/task_check.py; helper threads; thread-exit/stack-lifetime tests (phase 5) |
| `pthread_sigmask` | `lib/runtime/runtime_linux.tin` | 3 | removed | rt_sigprocmask with kernel sigset_t | tools/ci/http_check.py shutdown; per-thread signal-mask tests (phase 3) |
| `read` | `lib/runtime/runtime.tin`, `lib/std.tin` | 3 | removed | read raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `readdir` | `lib/quarry/quarry.tin`, `selfhost/main.tin` | 3 | removed | Tin linux_dirent64 parsing and buffer refills | tests/v2/quarry.tin; directory refill/unknown-type/symlink cases; bootstrap (phase 3) |
| `readlink` | `selfhost/host_linux.tin` | 3 | removed | readlink raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `realloc` | `lib/runtime/runtime.tin`, `lib/std.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `realpath` | `selfhost/main.tin` | 4 | removed | Tin path canonicalization with symlink traversal | Compiler path discovery with symlinks and missing paths; bootstrap (phase 4) |
| `recv` | `lib/mysql/mysql.tin`, `lib/postgres/postgres.tin`, `lib/redis/redis.tin` | 3 | removed | recv raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `rename` | `lib/quarry/quarry.tin` | 3 | removed | rename raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `rint` | `lib/gauge/gauge.tin`, `lib/runtime/runtime.tin` | 0 | intrinsic | Hardware float intrinsic | tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `rmdir` | `lib/quarry/quarry.tin` | 3 | removed | rmdir raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `round` | `lib/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `sched_getaffinity` | `lib/runtime/runtime_linux.tin` | 3 | removed | sched_getaffinity raw syscall (per-architecture ABI) | CPU mask/cgroup checks and sparse CPU IDs (phase 3) |
| `sched_setaffinity` | `lib/runtime/runtime_linux.tin` | 3 | removed | sched_setaffinity raw syscall (per-architecture ABI) | CPU pinning checks and sparse CPU IDs (phase 3) |
| `setenv` | `lib/quarry/quarry.tin` | 5 | active | Tin owned environment update | tests/v2/quarry.tin overwrite and ownership (phase 5) |
| `setsockopt` | `lib/anvil/anvil.tin`, `lib/wire/wire.tin` | 3 | removed | setsockopt raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `signal` | `lib/anvil/anvil.tin`, `lib/runtime/runtime_linux.tin` | 3 | removed | rt_sigaction and per-architecture signal return | Broken-pipe behavior; signal return; issue #175 handler (phases 3/5) |
| `signalfd` | `lib/runtime/runtime_linux.tin` | 3 | removed | signalfd4 | tools/ci/http_check.py shutdown (phase 3) |
| `snprintf` | `lib/runtime/runtime.tin` | 1 | removed | Tin precision float formatting and diagnostic text | tools/ci/number_check.py; existing bounds/core diagnostics |
| `socket` | `lib/anvil/anvil.tin`, `lib/wire/wire.tin` | 3 | removed | socket raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `sqrt` | `lib/dice/dice.tin`, `lib/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `stat` | `lib/quarry/quarry.tin` | 3 | removed | newfstatat pathname lookup | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `strcmp` | `selfhost/main.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `strerror` | `lib/flume/flume.tin`, `lib/mysql/mysql.tin`, `lib/postgres/postgres.tin`, `lib/quarry/quarry.tin`, `lib/redis/redis.tin`, `lib/websocket/websocket.tin`, `lib/wire/wire.tin` | 4 | removed | Per-OS Tin errno message table | tests/v2/quarry.tin; exact network/file error messages (phase 4) |
| `strftime` | `lib/anvil/anvil.tin` | 4 | removed | Tin time formatting | UTC calendar boundary Go twin; HTTP Date (phase 4) |
| `strlen` | `lib/quarry/quarry.tin`, `lib/runtime/runtime.tin` | 2 | removed | Tin mmap allocator or byte/word operations | Memory/OOM injection; overlap/alignment/microbenchmarks; bootstrap (phase 2) |
| `strtod` | `lib/runtime/runtime.tin`, `selfhost/lex.tin` | 1 | removed | Correctly rounded Tin float parser | tools/ci/number_check.py; tests/v2/mint.tin; bootstrap fixed point |
| `sysconf` | `lib/runtime/runtime_linux.tin`, `selfhost/host_linux.tin` | 4 | removed | Affinity mask and cgroup CPU limits; page size via auxv | CPU quota/affinity tests; page-size kernels (phases 4/5) |
| `time` | `lib/anvil/anvil.tin` | 4 | removed | clock_gettime CLOCK_REALTIME | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 4) |
| `timerfd_create` | `lib/anvil/anvil_linux.tin` | 3 | removed | timerfd_create raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `timerfd_settime` | `lib/anvil/anvil_linux.tin` | 3 | removed | timerfd_settime raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `trunc` | `lib/gauge/gauge.tin` | 0 | intrinsic | Hardware float intrinsic | tests/v2/gauge.tin and gauge_math.tin; both backend instruction checks |
| `uname` | `selfhost/main.tin` | 3 | removed | uname raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `unlink` | `lib/quarry/quarry.tin`, `lib/std.tin` | 3 | removed | unlink raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `unsetenv` | `lib/quarry/quarry.tin` | 5 | active | Tin owned environment removal | tests/v2/quarry.tin deletion (phase 5) |
| `usleep` | `lib/hearth/hearth.tin` | 4 | removed | nanosleep with interruption handling | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 4) |
| `write` | `lib/runtime/runtime.tin`, `lib/std.tin` | 3 | removed | write raw syscall (per-architecture ABI) | Existing strict/runtime/protocol suites plus syscall edge-case Go twin (phase 3) |
| `_exit` | `lib/runtime/memory.tin`, `lib/runtime/runtime.tin` | 3 | removed | exit_group raw syscall | Fault/stack-overflow diagnostics and nonzero exit (issue #175) |
| `shutdown` | `lib/anvil/anvil.tin` | 3 | removed | shutdown raw syscall | HTTP conformance and graceful shutdown |
| `sigaction` | `lib/runtime/runtime.tin` | 3 | removed | rt_sigaction and per-architecture restorer | Existing native stack-overflow/bad-access probes; signal-return tests (phase 3) |
| `sigaltstack` | `lib/runtime/runtime.tin` | 3 | removed | sigaltstack raw syscall | Existing native per-thread stack-overflow probes (issue #175) |
| `munmap` | `lib/runtime/memory.tin` | 3 | removed | munmap raw syscall | memory_check.py; task_memory_check.py |
| `madvise` | `lib/runtime/runtime.tin` | 3 | removed | madvise raw syscall | task_memory_check.py after heavy burst |
| `syscall` | `lib/runtime/syscalls_linux.tin` | 5 | active | Seed-only fallback; generated leaf uses svc/syscall directly | syscall_check.py dynamic-import assertion; bootstrap; removed at final seed cutover |
