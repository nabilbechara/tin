# Linux libc removal plan (issue #125)

Repository: https://github.com/yasserreslan/tin (`main`). Read first:
- issue #125;
- `AGENTS.md` (platform roles: Linux is production and benchmarks, macOS is development only);
- `docs/RUNTIME.md` section 8;
- `docs/PORTING.md`, `docs/CI.md`, `docs/PERFORMANCE.md` ("Benchmark policy");
- `notes/linux_abi.md`.

## Goal and scope

**End state.** linux-arm64 and linux-amd64 executables are static: no `PT_INTERP`, no
`PT_DYNAMIC` / `.dynamic`, no `DT_NEEDED`, no glibc. They run in `FROM scratch` and on
Alpine.

**macOS.** macOS keeps libSystem for system calls, threads and DNS. Do not use raw system
calls there. macOS must keep building and passing its native CI job (it is the development
platform), but no macOS work is in scope beyond keeping it green.

**Already done.** Phase "math in Tin" is merged (#128).

**Every phase is a separate PR, independently mergeable, with all CI green.**
- Linux stays dynamically linked until the final phase. Nothing before phase 5 may
  require static linking, `scratch` or Alpine.
- Reference #125 in each PR; only the phase 5 PR says "Fixes #125".

## Phase 0: inventory and benchmark baseline (small PR, first)

1. **Symbol inventory.** Write `notes/libc_inventory.md` listing every C symbol a Linux
   binary imports. Build it from the `extern func` and legacy `extern fn` declarations in `lib/` and `selfhost/`
   (about 90 distinct today), plus anything the ELF linkers add (`__libc_start_main` and
   friends). Each row gives:
   - the symbol;
   - its call sites (files);
   - the phase that removes it;
   - the replacement;
   - the test that proves the replacement.

   No symbol may be unassigned. This includes `memcpy`, `memmove`, `memcmp`, `memset`,
   `memchr`, `strlen`, `opendir`/`readdir`/`closedir`, `getauxval`, `sysconf`,
   `sched_getaffinity`, `signal`, `isatty`, `gethostname`, `dladdr`, `strerror`,
   `snprintf`, `strtod` and `atoi`.
2. **CI guard.** Add `tools/ci/test_libc_inventory.py`, picked up by the existing unittest
   discovery. It fails when a Linux-reachable `extern func` / `extern fn` or linker-added import is missing from the inventory,
   or when a symbol the inventory marks as removed reappears.
3. **Benchmark comparison mode.**
   - Extend `bench/run.py` (or add `bench/compare.py`) to compare two compilers: base and
     head.
   - Use separate bootstrapped checkouts and matching `TIN_ROOT` values, so each compiler
     loads its own runtime and libraries. Keep Tin-versus-Go reference runs with
     interleaved medians as well.
   - It builds identical benchmark inputs with both, runs them **interleaved**, at least 7 runs each,
     and reports the median per side and the ratio.
   - Add the same base-versus-head mode to the HTTP script, at least 5 interleaved rounds.
   - Make `.github/workflows/bench-linux.yml` able to run it with the PR's merge base as
     the base compiler, and write the comparison table to the job summary.

**Performance gate for every later phase.** Run the comparison on both Linux runners for
the CPU suite (`bench/v2`) and the HTTP suite (1 core, `/json` and `/plaintext`).
- **Pass:** every CPU benchmark has head/base elapsed time ≤ 1.05, and every HTTP req/s has
  head/base ≥ 0.95.
- **If a case misses:** rerun it once. If it still misses, fix it, or explain it in the
  PR with a profile, and the maintainer decides.
- **Paste the tables in the PR.** macOS numbers are not accepted as evidence.

## Phase 1: number conversion in Tin (both OSes)

Replace `strtod`, `atoi` and **every** `snprintf` use:
- the float formatter (`fmt_float_c`, `lib/runtime/runtime.tin` around line 1909), with
  precision-controlled `%f %e %E %g %G`, width, padding, zero padding, sign flags, and f32
  values;
- the shortest-form fallback (`runtime.tin` around line 2019);
- `mint` (`lib/mint/mint.tin` around line 501);
- the diagnostic messages (`runtime.tin:173` bounds message, `:437` core header);
- the compiler's float literals (`selfhost/lex.tin:555`).

Testing:
- **Parsing:** correctly rounded (Eisel-Lemire with a big-decimal fallback, as in Go's
  `strconv`). Test bit-for-bit against Go on hard cases (the parse-number-fxx test data,
  subnormals, ±0, Inf/NaN spellings, overlong inputs) and a random sweep.
- **Formatting: exact text.** Compare against the current output, and against Go's
  `strconv.FormatFloat` / `fmt` where they agree. Cover precision 0 to 40+, rounding at
  ties, huge and tiny exponents, f32, and width/padding/flag combinations. Put Go twins in
  `bench/ref`.
- Keep the bootstrap a fixed point.

## Phase 2: memory in Tin (both OSes)

- **Allocator.** Replace `malloc`, `calloc`, `realloc`, `free` and `posix_memalign`
  everywhere (runtime, relay, hearth, the libraries) with:
  - mmap-backed per-core page sources;
  - the existing 16 size classes;
  - big blocks as their own mappings, released with `munmap`;
  - mmap'd pool chunks.

  Expose an ingot-heap `free(block)` and a cross-core return path, documented in
  `docs/RUNTIME.md`. Do not design the long-lived reclamation policy: that is #176.
- **Memory functions.** Replace `memcpy`, `memmove`, `memset`, `memcmp`, `memchr` and
  `strlen` with Tin implementations. `memchr` is on anvil's header-scanning hot path, so
  word-at-a-time or SIMD is expected. Cover them in the phase 0 gate and add
  microbenchmarks at 16 B, 1 KiB and 1 MiB.
- **#178, out of memory.**
  - Every mapping and allocation checks for failure.
  - The out-of-memory report path allocates nothing: a static message plus the size,
    written with `write(2)`, then exit.
  - Add **deterministic failure injection** (for example `TIN_FAIL_ALLOC_AFTER=N`, honoured
    only in test builds or behind a runtime flag) and CI tests that the process prints
    `out of memory` and exits non-zero instead of segfaulting.
- **#177, task memory.** Recycled request tasks release extra pool chunks and stack pages
  (`madvise(MADV_DONTNEED)` or unmap), and the free-task list is capped. Test: an RSS check
  after a burst of 300 concurrent heavy requests in a `tools/ci` check.

## Phase 3: Linux system-call backend (still dynamically linked)

- Add a syscall intrinsic per CPU: `svc #0` on arm64, `syscall` on x86-64. Errors come
  from the return value (-4095..-1), not `errno`.
- Move every Linux system-call wrapper in the inventory onto it.
- Directory iteration uses `getdents64` with Tin's own buffer and `linux_dirent64`
  parsing, replacing `opendir`/`readdir`/`closedir`. It must handle buffer refills, `d_type`
  unknown (fall back to `lstat`), and long names.
- Record every number and layout, per architecture, in `notes/linux_abi.md` and the
  per-arch runtime files. Shared code hard-codes nothing.
- **Do not switch threads to raw `clone` in this phase.** While glibc is linked, any glibc
  function running on a thread glibc did not create (`getaddrinfo`, `dladdr`, `strftime`,
  `getenv`, ...) can crash, because glibc's thread-local storage was never set up. Keep
  `pthread_create` until phase 5.
- **Design checkpoint (open the design PR first, implement after the maintainer approves).**
  Write `notes/design_nolibc_threads.md` covering:
  1. Tin's core context register (x28 on arm64, r15 on x86-64) versus the architecture's
     TLS register (`tpidr_el0`, the `fs` base). Does anything need architecture TLS once
     libc is gone? If not, say it stays unset.
  2. `clone` flags. Child entry: a hand-assembled trampoline, because the child starts on
     the new stack with no frame.
  3. Stack allocation, guard page, lifetime and who frees it. Thread exit (`exit`, not
     `exit_group`) and its interaction with process exit.
  4. Signal masks: SIGTERM/SIGINT blocked in every core and helper thread, the signalfd
     on core 0. SIGSEGV/SIGBUS remain available to the stack-overflow handler.
     `rt_sigprocmask` / `rt_sigaction` take the kernel's 8-byte `sigset_t`, not glibc's
     128-byte one.
  5. Verify signal-return ABI separately: x86-64 uses `SA_RESTORER` and a trampoline
     calling `rt_sigreturn`; arm64 can use its kernel-provided vDSO trampoline.
     Record the chosen mechanism and test handler return on each architecture.
  6. One `sigaltstack` per thread for the stack-overflow handler (#175). It must keep
     working.

## Phase 4: DNS and the remaining helpers (still dynamically linked)

**DNS resolver** behind `wire`'s resolve, used on Linux. Do not claim "no behaviour change"
for DNS; document the **supported contract** in `docs/STDLIB.md` and `docs/PORTING.md`:
- supported: `/etc/hosts` first, then `/etc/resolv.conf` (`nameserver`, `search`,
  `ndots`, `timeout`, `attempts`, `rotate`); A and AAAA over UDP, falling back to TCP on
  truncation; non-blocking in tasks within the request deadline;
- not supported: NSS modules from `/etc/nsswitch.conf` (mdns, ldap, nss-resolve and the
  like). systemd-resolved still works through its stub address in resolv.conf;
- list the intentional differences from glibc's `getaddrinfo`, for example address
  ordering.

Test against a fake DNS server in a `tools/ci` check: truncation and TCP fallback,
NXDOMAIN, timeouts, search lists, ndots, and `/etc/hosts` precedence.

**Remaining helpers:**
- backtraces from a Tin symbol table the linker emits, instead of `dladdr`; panic output
  format unchanged;
- calendar and formatting in Tin, instead of `gmtime_r`, `strftime` and `time`;
- per-OS errno-name tables, instead of `strerror`, with exact messages for the errnos
  that tests and docs show;
- `isatty` via `ioctl(TCGETS)`; host name via `uname`;
- `usleep` replaced by `nanosleep`; random bytes via the `getrandom` syscall;
- CPU count and affinity via `sched_getaffinity` plus cgroup files, instead of `sysconf`.

Environment and auxv may still come from libc in this phase (`getenv`, `getauxval`); they
move in phase 5.

## Phase 5: static cutover and distribution validation

- **Startup and threads:**
  - `_start` per CPU reads argc, argv, envp and auxv from the initial stack;
  - `getenv`/`setenv`/`unsetenv` work on Tin's own environment;
  - core threads switch to raw `clone` per the approved design;
  - the vDSO `clock_gettime` is found via `AT_SYSINFO_EHDR`, with the syscall as fallback.
- **Linker:** `selfhost/elf.tin` and `selfhost/elf_x64.tin` emit static executables.
- **New CI step** on both Linux runners:
  - assert with `readelf -lW` and `readelf -dW` that there is no `INTERP` program header,
    no `DYNAMIC` program header, no `.dynamic` section and no `NEEDED` entries;
  - run the strict suite, the regressions, and a hello HTTP server checked with curl, in
    a `FROM scratch` container and an `alpine` container. Python orchestration and curl
    run on the Linux host; Tin executables run in the containers with a writable `/tmp`,
    required fixtures and explicit networking. No shell or timeout binary is assumed
    inside `scratch`; the host harness enforces deadlines and removes containers.
- **Inventory:** the phase 0 inventory shows zero Linux symbols, and the guard test
  enforces it.
- **Docs:**
  - `docs/RUNTIME.md` section 8 lists only the macOS libSystem layer;
  - `docs/DISTRIBUTION.md` and `docs/PORTING.md` drop the glibc 2.34 floor and show a
    `FROM scratch` Dockerfile, with a note that TLS (#124) will need a CA bundle mounted
    or embedded.

## Rules for every phase

**Bootstrap.** `make bootstrap` must stay byte-identical on all three targets.
- Prefer changes the checked-in seeds can compile.
- If a seed refresh is unavoidable, refresh the Linux seeds (natively, or with
  `make linux-bootstrap` / `make linux-amd64-bootstrap`). Leave `seed/tinc-darwin-arm64` to
  the maintainer and say so in the PR.

**CI.** Green on `ubuntu-24.04`, `ubuntu-24.04-arm` and `macos-15` (CI and Distribution).
- Don't weaken, skip or delete tests.
- Don't add `known_failure` exemptions to get green.

**Tests** in the repo's style:
- `tests/v2/*.tin` with expected output;
- `tests/regressions/` + `cases.json` for issue-linked bugs;
- `tools/ci/*_check.py` for runtime, network and RSS behaviour;
- Go twins in `bench/ref` for library behaviour.

**Behaviour.** Outputs and faults are unchanged except where a phase documents a contract,
which today is only DNS.

**Coordination.** Other agents may be fixing these issues at the same time; don't fix them
in your PRs, except #177 and #178, which belong to phase 2:
- #142: `guard`. Keep `rt_task_swap` and the task stack layout unchanged.
- #175: the stack-overflow handler. Keep a `sigaltstack` per thread through phases 3 and 5.
- #170, #171: closure `keep`.
- #172–#174, #183: anvil validation, timeouts and limits.
- #176: long-lived reclamation, which builds on your phase 2 free API.
- #124: TLS.

## Phase 1 implementation and validation

The compiler and runtime share `lib/runtime/number.tin`, written in the legacy function
syntax so the committed seeds can compile it. Decimal parsing uses Eisel-Lemire's
integer multiply/rounding path and an 800-digit exact decimal fallback; hexadecimal
parsing rounds with a sticky tail. Precision formatting uses exact decimal shifts and
nearest-even rounding. Shortest formatting finds the interval between adjacent floats;
the existing small-number fast path remains. Scratch workspaces belong to each core,
and conversion neither yields nor allocates after that workspace is initialized.

`tools/ci/number_check.py` compares 221,604 generated cases with Go and 20,963 pinned
finite cases from parse-number-fxx-test-data on every native CI target. It checks bits,
errors, random decimal/hex values, midpoint ties, subnormals, signed zero, overlong tails,
precision through 100, f32 and width/left/zero/plus flags. The long-integer mantissa case
`1` followed by 2,000 zeroes and `e-2000` is checked with Go's exact `big.Rat` and
nearest-even `big.Float.SetRat`: Go's capped strconv fallback returns zero for that
input, whereas the exact result, Tin and the previous libc parser return one.
`tests/v2/number.tin` also checks compiler literal bits and deterministic outputs against
`bench/ref/number_smoke`. The packed power table is regenerated entirely with Python
integers by `tools/gen_number_powers.py`; the Go adaptations retain their BSD license.

## Phase 2 implementation and validation

`lib/runtime/memory.tin` supplies the seed-compatible mmap heap and memory primitives
for the compiler and runtime. Size-class headers preserve ownership across cores;
remote frees queue to the owner's page source. Individual large mappings are unmapped
on free. The public ingot free API and its lifetime boundary are in `docs/RUNTIME.md`;
no owner-retirement or long-lived reclamation policy is introduced. Bulk copy/fill
leaves use NEON on arm64 and REP on amd64, with bounded word scans for equality and
byte search. The saved-register task layout and swap routines stay unchanged.

`memory_check.py` checks Go-identical outputs, all byte alignments, overlapping moves,
guard pages, allocator zeroing/realloc and cross-core returns. It injects 46 process-wide
allocation/mapping failures only behind `TIN_ALLOC_TEST=1`; `oom-mapping.tin` also
checks a real Linux mapping failure under the regression runner's virtual-memory limit.
`task_memory_check.py` holds 300 heavy requests concurrently, then checks pool/stack
page release and the 64-task cache cap. RSS acceptance is Linux-only. The benchmark
suite adds matching Tin/Go memory cases at 16 B, 1 KiB and 1 MiB.

Phase 2 performance repair: the first native Linux comparison missed the CPU gate in
fannkuch, strbuild and the three memory microbenchmarks; its required rerun is retained.
The seed-compatible Tin bodies now have bounded SSE2/NEON leaf replacements in both
backends. Short copies load the complete range before storing (including overlapping
memmove); 64-byte scans identify the first differing/matching byte. Guard-page tests now
include copy/fill/scan lengths through 259 and overlap distances through 127 at lengths
through 257. Machine code is reproducible from the checked-in relocation-free assembly
with `python3 tools/gen_memory_fast.py --check`. No task swap or saved-register layout
changes are involved.

Phase 2 performance follow-up: the first native x86-64 run missed the 1 KiB memory gate
(1.236 head/base); its required repeat is retained separately. Bounded AVX2 scans and
medium copies now use a per-core capability cache, guarded by CPUID AVX/OSXSAVE, XGETBV
XMM/YMM state, and CPUID AVX2. SSE2 remains the unsupported-CPU and legacy-compiler path.
The corpus runs with automatic selection and forced SSE2, including guard pages and
large overlaps. Native timing tables will be attached after the new head is measured.
