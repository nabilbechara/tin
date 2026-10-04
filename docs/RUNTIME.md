# The Tin runtime and the server stack: how they work

The runtime is the package in `lib/runtime/`: portable files plus `*_darwin.tin` /
`*_linux.tin` (and `*_linux_<arch>.tin`) for the OS layer, compiled into every strict
program. It is written in strict Tin with the standard-library-only features
(LANGUAGE.md §18). The HTTP server (`anvil`), cores (`hearth`), messages (`relay`) and
JSON (`argo`) are ordinary library packages built on it.

## 1. Value layouts

| value | representation |
|---|---|
| integers, bools | the value, sign- or zero-extended in a 64-bit register; stored at their width |
| `f64` | IEEE double in a d register |
| `str` | pointer to `[length (8 bytes)][bytes][NUL]`; literals live in the executable's constant segment |
| slice | pointer to a 32-byte header `[len, cap, data pointer, region]`; `region` is 1 when the data lives in the ingot heap |
| map | pointer to an 80-byte header `[count, capacity, keys, values, control bytes, string keys?, shift, tombstones, hashes, region]`; open addressing, power-of-two capacity |
| struct | pointer to its fields, laid out widest first with natural alignment, size rounded to 8 |
| `?T` | the T pointer, or 0 for nil |
| fault | a pointer to a str holding the full message (`outer: inner` when wrapped), or 0 for nil; four words before the str hold the record `[trace, joined, identity, cause]` (notes/interface_faults.md) |
| func value | the code address |

A fault is still one word. `fail`, `fail(...)`, `say.Fault` and the `fault` package make it
with `rt_fault_raw` (lib/runtime/runtime.tin): one allocation of
`[trace][joined][identity][cause][len][bytes][NUL]`, and the word points at `len`, so every
reader of the message (`say`, `{err}`, `err.Error()`, argo, `say.Str(err) == "..."`) sees a
plain str. `identity` is nonzero for sentinels (the runtime's own are 1 to 6, package-level
`fault("...")` declarations are numbered from 64 by the compiler), `cause` is the wrapped
fault, `joined` points at `[n][fault]...` for `fault.Join`, and `trace` holds a panic's
backtrace. `keep(err)` deep-copies the chain (`rt_keep_fault`). Runtime code makes the
standard sentinels with `rt_fault_deadline()`, `rt_fault_canceled()`, `rt_fault_limit()`,
`rt_fault_overloaded()`, `rt_fault_draining()` and `rt_fault_panic(msg, trace)` (each an
i64 fault word: `fail cast(fault, rt_fault_deadline())`). The interface is
notes/interface_faults.md.

Map hashing is keyed with 128 random bits drawn once per process in `rt_init` (one key for
every core, so a map built on one core is found on another): strings (and struct or enum
keys, encoded as bytes) use SipHash-1-3, integers the splitmix64 finalizer over `k ^ key`.
A client cannot precompute keys that collide (hash flooding). Iteration follows insertion
order, so no output depends on the key. The table grows at half load.

## 2. The core context (x28)

Every thread that runs Tin code (a core) has a context block; register x28 points at it
for the thread's whole life (callee-saved in both ABIs, so C code never disturbs it).

| word | name | meaning |
|---|---|---|
| 0, 1 | ctxBump, ctxEnd | request-pool bump pointer and the end of the current chunk |
| 2 | ctxFmt | the current `say` format frame |
| 3 | ctxFound | the last map lookup's found flag (comma-ok reads) |
| 4 | ctxID | the core number |
| 6 | ctxIngot | 1 while initializers run: allocations go to the ingot heap |
| 7, 8, 9 | ctxPoolBase, ctxPoolMark, ctxPoolExtra | the pool's first chunk, its high-water mark, overflow chunks and big blocks |
| 10 | syscall error | Linux kernel thread error; compiler offsets stay unchanged |
| 11 | vector mode | x86-64 AVX2 capability after CPUID/OSXSAVE/XGETBV checks; zero on arm64 |
| 12–31 | reserved | preserve compiler offsets; heap state is a per-core global |
| 32+ | | the core's copy of every per-core global (global i at word 32+i) |

Context blocks are allocated on their own 128-byte cache lines (`rt_aligned_alloc`) so
cores never share a line.

## 3. Memory

**Request pool.**
- `rt_alloc(n)` rounds n up to 16 and bumps `ctxBump`; when the chunk is full it takes
  a new 4 MiB chunk.
- Blocks of 256 KiB or more get their own calloc'd block, freed at reset.
- `rt_pool_reset()` zeroes the used part of the first chunk, frees the overflow chunks
  and big blocks, and rewinds the bump pointer.
- anvil calls it after every response, `relay`/tick handlers after each run, and
  `hearth.Reset()` exposes it. The compiler rejects reading a local that may hold request
  memory after a `hearth.Reset()` (called directly or through the program's own functions)
  until it is assigned again, on any path, loops included: keep() it before the reset or
  create it after.
- Plain programs never reset: they release everything at exit.

**Ingot heap.** `rt_ingot_alloc(n)` returns zeroed, 16-byte-aligned memory from the
core's mmap heap. The 16 classes are 16, 32, 48, 64, 96, 128, 192, 256 ... 3072,
4096 bytes, including a 16-byte `[owning heap, size word]` header (the size word's bits
47-62 hold the reclamation count, below). Local free
lists and 1 MiB slab bump sources live in the heap's own page mapping. Larger blocks
have a page-rounded mapping of their own; `rt_ingot_free(p)` releases them with
`munmap`. Request pool chunks use the same checked mapping allocator.

`rt_ingot_free(p)` returns a small block directly when called on its owning core.
A different core appends it to the owner's return queue under an atomic lock; the
owner drains that queue before allocating. Blocks remain tied to their owner even
when returned elsewhere. Heap pages and slabs live for the process lifetime. Maps release
their old ingot tables when they grow. The compiler uses the same memory core with a single heap.

Every allocation and mapping checks its size and failure result. Failure writes
`tin: out of memory (N bytes)` to stderr from static bytes and stack words, then exits
with status 2. This path creates no context, pool, format frame or heap block.
Memory leaves use bounded NEON on arm64 and SSE2 on x86-64. Strict x86-64 programs
cache AVX2 availability in context word 11 after checking CPU support and OS-managed
XMM/YMM state. Medium forward copies and long comparisons/scans use AVX2 when available;
small operations and unsupported CPUs retain SSE2. Legacy compiler programs never read
a Tin context register. `TIN_ALLOC_TEST=1 TIN_MEMORY_SCALAR=1` forces the SSE2 path for
correctness checks.

`TIN_ALLOC_TEST=1` enables the test-only `TIN_FAIL_ALLOC_AFTER=N` counter, including
startup allocations and mappings. Without that explicit flag the variable is ignored.

**Initialization.**
- `rt_init` creates core 0's context in ingot mode.
- Global initializers allocate in the ingot heap.
- `rt_main_begin` switches to the request pool before `main.main`.
- Each extra core runs `__core_init` (the per-core global initializers) in ingot mode,
  then switches to its pool.

**Arenas.** An `arena { }` block (#236) allocates from a pool of its own, made when it is
entered and freed (chunks and big blocks) when it ends; only its value, copied out by a
generated `arenacopy$N`, survives. Arena memory is pool memory: it is never counted or
reclaimed by the ingot heap's machinery. See section 9, "Arenas".

**keep.** `keep(x)` calls a generated `keep$N` function per type. It copies strings
(`rt_keep_str`), structs (`rt_keep_raw`, then their reference fields), slices
(`rt_keep_slice`, then elements) and maps (a new ingot map, entry by entry) into the
ingot heap.

**Reclaiming long-lived memory (#176, notes/interface_mem.md).** Each block of a core's
heap counts the long-lived references to it in its size word. `keep$N` counts what its
copy holds; stores into globals and provably long-lived containers count the new value and
drop the old one; maps and long-lived slices count their own entries and elements. A
block whose count falls to 0 waits in the core's limbo until everything that could have
borrowed it is past: every task alive when it was dropped has ended, and the core's own
stack has reset its pool (the end of a request or tick, `hearth.Reset()`). Then its
children are dropped and it is freed. So `u := cache[k]` stays valid for the rest of the
request even if another request replaces the entry. Values made while a core initializes
its globals, and values stored where the compiler cannot count (through a parameter), are
pinned: they are never freed. `hearth.RcStats()` reports the counted blocks, their bytes
and the limbo length.

## 4. Cores and threads: hearth

- `rt_spawn_core(entry, arg)` starts a pthread with an 8 MiB stack. The thread creates
  its context (`rt_ctx_new`), sets x28, runs `__core_init`, sets its scheduling hint
  (`rt_core_qos`: QoS user-interactive on macOS; CPU pinning on Linux) and calls
  `entry(arg)`.
- `hearth.Run(n, f)` spawns cores 1..n-1, runs `f(0)` on the calling thread, and waits
  for the others (an atomic counter).
- `hearth.Cores()` counts usable CPUs: `sysconf` on macOS. On Linux it is the minimum of
  online CPUs, the affinity mask and the cgroup CPU quota (`cpu.max` /
  `cpu.cfs_quota_us`).
- `TIN_CORES` overrides the count for anvil.

## 5. Messages: relay

Each core has a box in a process-wide array of 256 boxes. A box is:
- a lock-free multi-producer, single-consumer linked queue (Vyukov's algorithm):
  producers swap the head atomically, the owner pops at the tail;
- a wake pipe (an eventfd on Linux is planned);
- a "waiting" flag.

`Send(core, msg)` copies the message into a malloc'd node, links it, and writes one byte
to the wake pipe only if the receiver set its waiting flag. `Recv()` pops, or sets the
flag, re-checks (no lost wake-ups), then blocks in `poll` on the pipe. Event loops
register `relay.WakeFD()`, call `relay.Arm()` before sleeping and `relay.Drain(h)` when it
fires. Messages are copied into the receiver's request pool.

## 6. Output and formatting

- `say` output goes through a 64 KiB stdout buffer guarded by a spinlock (shared by all
  cores). It is flushed when full, at exit, at every newline on a terminal, and by
  `rt_flush()`.
- Formatting uses a per-core frame: the compiler emits one `rt_fmt_*` call per argument
  by static type (`rt_fmt_i`, `_u`, `_s`, `_f`, `_b`, `_e`, slices, maps, structs).
- Floats are printed in their shortest exact form. A fast path finds the fewest decimals
  k for which rint(|x|·10^k)/10^k == |x|, exact for values below 2^53. Otherwise
  the integer-only conversion core finds the shortest decimal in the interval between
  adjacent floats. Precision formats use exact decimal shifts and nearest-even rounding.
  `rt_float_json` uses JSON's exponent rule.

## 7. Panics and backtraces

- `rt_panic(msg)` flushes stdout, prints `panic: msg`, walks the frame-pointer chain from
  `__fp()`, names each return address with `dladdr`, and exits with status 2.
- The walk skips `rt_` frames and stops at the program entry.
- On Linux the linker emits a read-only Tin table of function start/end/name records.
  Backtrace lookup uses image-relative ranges, including under ASLR; printed names stay unchanged.
- `rt_bounds_fail2(i, n)` and `rt_div_fail()` are the cold paths of failed checks.

## 8. The OS layer

Everything that differs between macOS and Linux sits behind `rt_` helpers with the same
names in both OS files:

| helper | macOS | Linux |
|---|---|---|
| `rt_errno()` | `__error()` | core context word 10, set from negative kernel results |
| `rt_mono_ns()`, `rt_wall_ns()` | `clock_gettime_nsec_np(8 / 0)` | kernel vDSO clock with clock_gettime syscall fallback |
| `rt_random(p, n)` | `arc4random_buf` | `getrandom` (loop) |
| `rt_ncpus()` | `sysconf(58)` | affinity mask plus cgroup quota |
| `rt_sockaddr_in(sa, ip, port)` | `sin_len` + family bytes | u16 family |
| `rt_ai_addr(ai)` | addrinfo + 32 | unused; Tin DNS builds sockaddr directly |
| `rt_nosigpipe(fd)` | `SO_NOSIGPIPE` | ignore SIGPIPE process-wide |
| `rt_stat_mode/size/mtime/dev/ino(st)` | struct stat offsets | kernel offsets (st_mode differs between arm64 and amd64: per-arch file) |
| `rt_dirent_name(ent)` | `d_namlen` + `d_name@21` | bounded getdents64 record, name@19 |
| `rt_core_qos(core)` | QoS user-interactive | CPU pinning when safe |

Constants with the same names in both files: `EINTR EAGAIN EINPROGRESS ENOENT EEXIST
ENOTDIR EINVAL EMFILE ENFILE O_WRITE_CREATE O_APPEND_CREATE O_NONBLOCK F_GETFL F_SETFL
SOL_SOCKET SO_REUSEADDR SO_REUSEPORT SO_ERROR SO_RCVTIMEO SO_SNDTIMEO TARGET_LINUX`.
`notes/linux_abi.md` holds every verified value and layout. Linux's `rt_sys_*`
wrappers invoke a compiler-emitted leaf (`svc #0` / `syscall`) and turn kernel
-4095..-1 results into -1 plus the calling thread's error word. No syscall reads libc
errno. Directory handles own a 32 KiB getdents64 buffer, validate each record before
reading it, refill as needed, and resolve unknown types with lstat. The kernel signal
set is 8 bytes; signal handlers return through Tin's frame-free rt_sigreturn leaf.
Pthreads remain until the static cutover; libc environment failures still use its
errno, and the old seed uses a libc syscall fallback only to build stage 1. Clock lookup reads the kernel vDSO from AT_SYSINFO_EHDR (libc auxv until phase 5),
with the raw syscall as fallback. Generated
Linux programs do not import syscall or the removed OS entry points.

UTC calendar/Date formatting, errno messages and Linux backtrace lookup are Tin code.
Darwin errno codes 0..106 use the stable Tin message table. Newer/unknown codes
retain libSystem text because code assignments vary between macOS development releases.
Linux errno messages use Tin exclusively.
Linux TTY detection uses ioctl TCGETS, hostname uses uname, and sleeps use nanosleep.
Environment, auxv, pthread startup and dynamic ELF remain for the final cutover.

## 9. The HTTP server: anvil

**Event loops.** One per core:
- kqueue on macOS, epoll on Linux, behind `ev_*` functions in `anvil_darwin.tin` /
  `anvil_linux.tin`.
- Connections are edge-triggered (`EV_CLEAR` / `EPOLLET`); listeners, pipes and wakers
  are level-triggered.
- Ticks (`anvil.OnTick`) use EVFILT_TIMER on macOS and timerfd on Linux.

**Accepting.**
- macOS: core 0 owns the listener and deals connections round-robin to the cores
  through per-core pipes (macOS's `SO_REUSEPORT` does not balance).
- Linux: every core has its own `SO_REUSEPORT` listener and accepts its own
  connections; balancing on top of the kernel's hashing is being added.
- At most 64 accepts per wake-up.
- When file descriptors run out, a spare `/dev/null` descriptor is closed to accept
  and drop one waiting client instead of spinning.

**A connection** is a 96-byte record: fd, pending input buffer, pending output buffer,
close-after-write flag, writing flag, bytes needed. Idle connections hold no buffers.

**Reading.**
- Each core reads into one 256 KiB scratch buffer.
- A read that fills the buffer is repeated, since an edge-triggered socket must be
  drained.
- Complete requests are parsed in place:
  - request line;
  - headers, scanned with `memchr`; each name must be a token followed by `:`, and
    only `Content-Length`, `Connection` and `Transfer-Encoding` are interpreted;
  - body.
- An incomplete request is copied into the connection's own buffer, sized to the
  request when its length is known (up to 64 MiB).
- A hang-up reported with the last data closes the connection once its output is
  written. A client that only shuts down its sending side still gets the response to a
  request that is waiting; the connection closes after it.

**Handlers** get two per-core objects:
- `anvil.Req`: method (interned for common verbs), path, query (copied into the pool),
  raw header and body pointers for `Header()`, `Body()` and `Param()`;
- `anvil.Out`: `Body []u8`, status, content type, extra headers.

**Responding.**
- After the handler returns, the response goes into a per-core output buffer: the
  status line from a table, then a per-core cached block with `Server` and the `Date`
  header (refreshed when the second changes), then the content type, extra headers,
  `Content-Length` and the body (omitted for HEAD).
- The buffer is reset per request and the request pool is wiped.
- All responses produced from one read go out in one `write`.

**Backpressure.** If the socket does not take everything, the remainder is kept in the
connection, reading is disabled, and write readiness is awaited; when the output drains,
reading resumes and buffered input is served.

**Limits and errors.**
- A request line or header block over 64 KiB gets 414 / 431 and close.
- A malformed request line (including control bytes such as a bare CR, NUL or tab, or a
  version other than `HTTP/1.<digit>`), a header line that is not `name: value` (no colon,
  whitespace before it, obs-fold, a name that is not a token), a CR or NUL inside a header
  line, an HTTP/1.1 request without exactly one `Host`, or a bad `Content-Length` gets
  400; `Transfer-Encoding` gets 501.
- A request with `Expect: 100-continue` whose body has not arrived gets
  `HTTP/1.1 100 Continue` first (clients such as curl and the AWS SDKs wait for it).
- An absolute-form target (`GET http://host/path?q HTTP/1.1`) is routed on its path and
  query; an empty path is `/`.
- Bodies are limited to 64 MiB by default (413); `anvil.Limits` or `TIN_MAX_BODY` changes it.
- **Timeouts** (`anvil.Timeouts`, or the environment): a request's line and headers must
  arrive within 10 s of its first byte (`TIN_HEADER_TIMEOUT_MS`), and the whole request
  within 60 s (`TIN_READ_TIMEOUT_MS`); a keep-alive connection with no request in progress
  is closed after 60 s (`TIN_IDLE_TIMEOUT_MS`); a response the client stops reading is
  dropped after 30 s without progress (`TIN_WRITE_TIMEOUT_MS`). A new connection gets the
  header timeout for its first request. 0 turns one off. While a handler runs, only the
  request deadline (`anvil.Deadline`) applies. Each core checks its connections' deadlines
  once a second, in its event loop (no timer per connection).
- **Closing after an error:** a connection closed after a parse error, 413 or 503 shuts down
  its sending side and reads and drops input for up to 2 s before it closes (a lingering
  close, as nginx does): closing with unread input would reset the connection, and a client
  still sending its body would lose the response.
- **Memory and connections:** the partial requests one core buffers are limited to 256 MiB
  (`TIN_MAX_BUFFERED`): a new partial request past it gets 503 and close. Each core takes at
  most 16384 connections (`TIN_MAX_CONNS`); more are closed at accept.
- HTTP/1.0 closes unless keep-alive is asked for, and a kept HTTP/1.0 connection gets
  `Connection: keep-alive` in every response. `Connection` is read as a token list:
  `close` anywhere closes the connection after the response.
- `$PORT` replaces the port of the address passed to `Serve`.

Balancing: on Linux each core accepts on its own `SO_REUSEPORT` listener, then hands a new
connection to the least-loaded core (per-core live-connection counters) when its own load
is more than one above it. Graceful shutdown on SIGTERM/SIGINT: see PORTING.md §4.

### Request tasks (v0.4)

Every request's handler runs in a **task**: its own 256 KiB stack (mmap'd, with a 16 KiB
`PROT_NONE` guard region below it, so an overflow faults instead of corrupting memory) and
its own request pool. `rt_task_run` switches into a task from the core's stack;
`rt_task_swap`, hand-assembled per CPU, saves and loads only what a call preserves (arm64:
x19–x27, x29, x30, sp, d8–d15; x86-64: rbx, rbp, r12–r14, rsp and the return address), about
ten nanoseconds. x28 / r15, the core context, is the same on every task of a core, and the
core's pool words (bump, end, base, mark, extra) and formatting frame stack are swapped
in and out with the task. Formatting arguments may wait without sharing frames with
another task. Resource cleanup callbacks run before the owning pool is reset.

- A handler that never waits finishes inside `rt_task_run`: two switches and nothing else,
  so the fast path keeps its speed (measured: 308–310k req/s on one core, as before).
- A handler that waits (`tide.Wait`, `tide.Sleep`, `wire` calls, `quarry` file calls) yields: the request's bytes are copied out of the shared read buffer, the
  connection stops serving its later pipelined requests (responses stay in order), and the
  core goes back to its event loop. Sleeping tasks sit in a per-core min-heap; the loop
  waits at most until the earliest wake-up (`ev_wait(ms)`), then resumes due tasks. A task
  that finishes appends its response, flushes, and its connection serves what queued.
- Deadlines: each request's waits give up at `anvil.Deadline(ms)` / `TIN_DEADLINE_MS`
  (default 30 s) after it started: `tide.Wait` then fails with `deadline exceeded`.
- Backpressure: at 4096 waiting requests on a core, new requests get 503.
- A panic in a handler (an index out of range, a division by zero, `panic`) ends only its
  request: `panic: ...` and the backtrace go to stderr, the task's cleanups run and its pool
  is reset, its stack is abandoned and reused, and the request gets 500 and its connection
  closes. Other requests, waiting ones on the same core included, go on. Before the cleanups,
  the deferred calls of every frame the panic leaves run, innermost first (#230: each `defer`
  puts a record on the task's defer chain, made by a generated `defer$N`; a return runs the
  chain back to its function's mark). A panic while they or the cleanups run ends the process
  after printing both messages. Ticks (`anvil.OnTick`) and relay handlers (`anvil.OnRelay`)
  are guarded implicitly too (#230): each tick, and each round of relay messages, runs through
  `rt_guard_call` on a guard stack, so a panic in one logs `panic: ...` and its backtrace, runs
  the deferred calls it registered, ends that tick or that message's handler, and the core goes
  on (the remaining messages are handled at once). A panic in `main` outside a `guard`, or a
  stack overflow, still ends the process.
- A connection closed while its request waits is marked dead and freed when the task ends.
- Finished tasks free overflow pool chunks and big blocks. Each core caches at most
  64 task records; excess records release their base pool and unmap their stacks.
  Heavy cached tasks discard complete base-pool and stack pages with
  `madvise(MADV_DONTNEED)`; stack mappings are released if advice fails. Headers and
  pool boundary pages remain intact. Light tasks reuse their zeroed pools and stack
  pages without an extra syscall per request. Stale timer entries are invalidated
  before a task record is released or reused. The 300-request burst check exercises
  deep suspended stacks and dirty overflow pools, then verifies the Linux RSS bound.

### Non-blocking I/O and helper threads (v0.4)

- `rt_task_wait(fd, want, timeout)` is the one wait primitive: inside a task it registers
  the fd once (kqueue `EV_ONESHOT` / epoll `EPOLLONESHOT`) through the core's `waitHook`,
  pushes a timer for the earlier of the timeout and the request deadline, and yields. The
  event or the timer resumes the task, whichever comes first; a generation number makes the
  loser stale (a stale timer is skipped, a stale fd watch is removed by `waitCancel`).
  Outside a task it falls back to `poll` or a sleep, so the same code works in `main`.
- `wire` sockets are non-blocking: connect, read, write and accept wait with
  `rt_task_wait` on `EAGAIN`. `Conn.SetTimeout` bounds each wait; past it the call fails
  with `wire: read timed out` (or connect/write), past the deadline with `deadline exceeded`.
- Linux DNS uses nonblocking UDP/TCP sockets and task waits (docs/STDLIB.md, wire contract).
- Work with no non-blocking form (macOS DNS `getaddrinfo`, file reads and writes in `quarry`)
  goes to four shared helper threads. `rt_helper_run(f, job, drop)` queues a heap-owned
  job in a bounded queue (4096 outstanding jobs process-wide), signals a non-blocking
  wake pipe and parks within the request deadline. A full queue fails immediately.
  A helper runs `f(job)` and writes the completion to the owning core's done pipe.
  Inputs and results live outside request pools, so an expired request may return and
  reuse its task safely. A late completion calls `drop(job)` and never resumes the old
  task. Already-running system calls can still finish after the caller's deadline;
  their results are discarded. Outside a task the helper runs synchronously.
- Boundaries (Tin 1, notes/interface_boundaries.md): each request task has a root boundary
  record under its core's root, holding its deadline and cancel state; block boundaries nest
  under it. `rt_bnd_cancel(b, reason)` cancels `b` and everything inside it (never its parent
  or siblings) and ends the waits of the tasks inside: `rt_task_wait` returns `waitDeadline`,
  and a wait in a boundary that is already cancelled returns it at once. Clients then fail
  with `rt_wait_fault()`: the reason itself when it is `fault.DeadlineExceeded` or
  `fault.LimitExceeded` (by identity), otherwise a `fault.Canceled` fault reading
  `canceled: <reason>` whose cause is the reason (notes/interface_faults.md).
  `tools/ci/cancel_check.py` checks every client.
- Deadlines (#233, edition 1): `within d { }` enters a `bkWithin` boundary whose deadline is
  the earlier of `now + d` and the enclosing one (the request's `TIN_DEADLINE_MS`, an outer
  `within`); waits past it fail with `fault.DeadlineExceeded`, which the block gives as its
  fault. `task.Deadline()` is the effective deadline of the running code (`tide.Now()`
  nanoseconds, 0 for none) and `task.Canceled()` the fault its next wait would fail with (nil
  while it may go on), for code that does not wait or wants to stop at a point of its own.
- `once { ... }` (#236) runs its block the first time each core reaches it (globals are per
  core, so this is the unit; process-wide one-time work belongs in `on app.start`).
- Arenas (#236, edition 1, notes/interface_arena.md): `arena { }` is `arena$N(c)`, which
  opens a `bkArena` boundary with a fresh pool (`rt_arena_open`), runs the block's closure
  (`rt_arena_run`), gives the context the parent pool back (`rt_arena_out`), copies the fault
  (`rt_arena_fault`) and the value (a generated `arenacopy$N`, the pool twin of `keep$N`)
  into it, and frees the arena's chunks (`rt_arena_close`). The record's `bRegion` points to
  the arena's saved pool words. A pool's words have one home while its code is not running:
  `rt_arena_open` writes the parent's back to theirs first, so scope children that share the
  parent's pool keep allocating in it while the arena body waits, and `rt_task_run` keeps a
  task's arena pool in its innermost arena (`rt_pool_home`). An unwind that passes through
  an arena frees it: `rt_land` (guard, limit and within landings, with the landing fault
  copied out first) and `rt_bnd_task_end` (a task ended by panic, with a scope child's fault
  copied out). Its chunks charged to a `limit` are given back.
- Budgets (#235): `limit memory n, tasks k { }` counts the pool chunks and big blocks taken
  inside it (the bump fast path is not touched) and tasks started in it. Passing the memory
  budget leaves the block with `fault.LimitExceeded` at once (its defers and cleanups run).
  `TIN_REQUEST_MEMORY` (bytes, beyond a request's first pool chunk) bounds every request the
  same way; a request past it ends with 500 and the server goes on.
- Scopes (Tin 1 #232, edition 1): `scope s { s.spawn(fn() ! { ... }) }`. A child is a task
  on the same core with a root boundary under the scope's; it runs when its parent waits,
  allocates in its parent's pool (children share the parent's region) and may store request
  memory in what it captures. The scope's end waits for every child; the first child fault
  cancels the scope, and so its other children, and is the scope's fault (`try` passes it
  on). `t := s.spawn(f)` gives a handle with `t.wait() !` and `t.cancel()`; a child cancelled
  through its handle does not fail the scope. A child with a value (`s.spawn(fn() !T { ... })`)
  gives a `spawnedOf[T]` whose `t.wait() !T` is its value or its fault (waiting again gives the
  same value), usable in `select` like any handle. Leaving a scope body early, by `return` or
  a `try`'s fault, cancels and joins the children still running, then leaves the scope. In a server the event loop resumes children;
  in `main` the scope's end runs them itself. Spawned closures make their captured variables
  cells per spawn, so `for i in 0..n { let k = i; s.spawn(...) }` gives each child its own `k`.
  A handle (`spawned`, `spawnedOf[T]`) and its scope cannot outlive the scope block, which frees the
  children's records: the compiler keeps them in local variables and parameters (and local
  slices, maps and optionals of them), never in a global, a field, a result, a type argument
  or a `dyn` value; a value goes only into a variable declared inside its scope (an assignment,
  a `mut` or scope argument, `append`, `copy`); a closure that may be kept, and `detach`, cannot
  capture one; a child of scope `a` cannot capture a handle of a scope inside `a`; and a
  `defer` inside a scope cannot use one. Any number of tasks may wait for one handle.
- `detach { ... }` (#232) starts a task in the core's background boundary: it has its own pool,
  outlives the request that started it (its closure and captures are `keep`-copied to the
  long-lived heap), runs when the event loop turns, is cancelled by the drain with the rest of
  the core, and logs its fault (`detached task failed: ...`) instead of passing it on.
  What it captures must already be long-lived, as for a global: a capture that may hold
  request memory is a compile error naming it, unless the block reads it only inside `keep()`
  (`detach { flush(keep(event)) }`); otherwise keep it first (`let e = keep(event)`). A task
  handle or a scope cannot be captured at all.
- `select { let x = l.Recv() => ...; t.wait() => ...; after(d) => ...; canceled() => ... }`
  (#232) checks its arms in source order, so ties go to the first one; with none ready it
  watches every source (lanes and task handles wake it), parks until one does or the earliest
  `after` comes, withdraws, and checks again. The winning arm then takes its value, which
  cannot wait. A cancelled boundary with no `canceled()` arm ends the select with its fault.
- `use` and `on` (#238, edition 1). A package-level `use db = open()` is a per-core global
  opened with the core's other globals, on core 0 and on every core `hearth.Run` starts (not on
  helper threads); a fault there ends the process with `startup failed: use db: <msg>` and
  status 1. `on app.start`, `on core.start`, `on core.stop` and `on app.stop` handlers run in
  declaration order, each inside a guard under the core's background boundary (no bindings),
  on the core's own stack, so a wait in one blocks its core (which serves nothing then). Order:
  core 0's globals and uses, `app.start`, core 0's `core.start`, `main`; each other core opens
  its uses and runs `core.start` before any core serves (a startup barrier in `hearth.Run`).
  A fault (or a panic) in a start handler ends startup with status 1. When a core's entry
  returns (after the drain), it runs `core.stop` and closes its uses, last opened first; after
  `main` returns, core 0 does the same and then runs `app.stop`. Stop handlers get a fresh
  core root, so the drain's cancellation does not stop their own waits; their faults are logged.
  A function-level `use x = e` is `let x = try e` plus a deferred `x.Close()` (it also runs
  while a panic unwinds); a fault from `Close` is joined after the function's own fault.
  `anvil.Drain(d)` starts the same graceful shutdown as SIGTERM from code, with grace `d`.
- Admission (#238, design_semantics §11). `anvil.Admit(p)` (before `Serve`) sets a policy that
  decides each new request after the built-in limits and before its handler runs, on the core
  it arrived on: `p(anvil.Load)` sees that core's waiting request tasks, live connections, bytes
  buffered for requests still arriving, and the requests it refused so far. `false` answers 503
  with `Retry-After: 1` from static bytes (no allocation, no handler) and keeps the connection
  when the client does. The first refusal on any core makes the server OVERLOADED and runs the
  `on server.overload` handlers; once every shedding core has admitted a request at least a
  second after its last refusal, the `on server.recovered` handlers run. These run in a
  detached task of the core that saw the transition, so a wait in one does not hold the core.
- Tasks can wait on each other: `rt_task_park(timeout)` waits until another task calls
  `rt_task_wake(t)`; woken tasks go on a per-core ready queue that the loop drains on its
  next turn (it does not block while the queue has tasks). `rt_task_defer()` puts the
  running task on that queue, so it continues after the core's other events of this turn.

### Clients on shared connections: redis (v0.4)

- Each core keeps one connection per `redis.Client`. A command is encoded straight into
  the connection's output buffer and a slot for its replies joins a FIFO.
- One task at a time owns the connection's I/O. The owner first defers (`rt_task_defer`),
  so the other requests of the same event-loop turn add their commands; then it writes
  everything queued in one `write`, reads, and hands each complete reply (checked with
  `resp_len`, copied into the slot in malloc'd memory) to the slot at the front, waking its
  task. When its own replies are in, it passes ownership to the first task still waiting.
  Each woken task parses its reply into its own pool.
- A caller that hits its deadline or timeout marks its slot gone and leaves; the slot stays
  queued so the reply that comes later is consumed in order and freed. A connection error
  fails every waiting slot; the next command reconnects. An idle connection is checked
  with a non-blocking `recv(MSG_PEEK)` before use, so a server restart costs no failures.

### Upgraded connections: websocket (v0.4)

- `Req.Hijack` takes a request's connection out of HTTP: anvil writes the responses queued
  before it, removes the descriptor from the core's poller (so the task can watch it with
  `rt_task_wait`), clears the request deadline and defers once, so the request always ends
  through `finish_request`, which then closes the descriptor instead of answering.
  Hijacked connections do not count toward the 4096 waiting requests per core.
- `websocket.Accept` checks the handshake, hijacks and writes the 101 itself. The
  connection's state belongs to its caller's pool; heap-owned I/O buffers are released
  by `Close` or automatically before the owning task/scope resets. Repeated `Close`
  is safe. An idle connection parks its request task and occupies no thread.
- Tasks on one core may write to the same `Conn`: a frame is written whole before
  the next writer, who waits its turn with `rt_task_defer`.
- `Conn.Each(h)` gives every message callback a reusable pool, reset after the callback
  returns; use `keep()` to retain message data. Objects allocated before `Each`,
  including the Conn, remain valid, and callbacks may wait. Read/callback faults are
  copied into the caller's pool before the scope is released. The echo example uses
  `Each`, so memory use stays bounded for a long-lived stream.
- `Read` continues to return data in the caller's pool, preserving earlier messages
  across later reads. Its fragment accumulator is temporary heap memory, freed on
  every return, and ping/pong payloads are processed in place without pool allocations.
  Client masking keys are generated directly into the frame header. `Read` users who
  retain all messages must manage their pool lifetime explicitly; `Each` is the stream
  API that supplies a safe per-message lifetime.

### Pooled clients: mysql (v0.4)

- MySQL answers one statement at a time per connection, so each core keeps a pool per
  `mysql.Client` (`Options.Pool`, default 16). A task takes an idle connection (checked
  with `MSG_PEEK`), dials a new one while under the limit, or parks in the pool's FIFO;
  a released connection goes straight to the first waiter still waiting.
- The task that holds a connection does its I/O directly (`rt_task_wait` on `EAGAIN`) and
  builds rows in its own pool. A server error (an ERR packet) leaves the connection usable;
  an I/O error, a timeout or the deadline closes it, since its state is unknown.
- A query with values runs as a prepared statement (`COM_STMT_PREPARE` once per text and
  connection, then `COM_STMT_EXECUTE` with binary parameters and rows); one without values
  as `COM_QUERY`. Up to 256 statements are cached per connection.
- Login: `caching_sha2_password` (fast path, or the full exchange: the server's RSA public
  key, fetched once per Client, encrypts the password with `seal.EncryptOAEPSha1`) and
  `mysql_native_password`, including auth-switch requests.

### Routing: Router

```go
r := anvil.NewRouter()
r.Use(logged)                                  // middleware, around every route below
r.Get(`/users/{id}`, user)                     // patterns with {...} are raw strings
r.Get(`/static/{path...}`, files)              // the rest of the path; * is the same, named "*"
r.Route("/admin", func(g mut anvil.Router) {   // a group: a new router mounted at /admin
	g.Use(auth)
	g.Delete(`/users/{id}`, remove)
})
r.Mount("/v2", v2)                             // another router's routes under /v2
r.NotFound(missing)                            // the status is already 404
err := r.Serve(":8080")                        // fails first if a pattern is bad (r.Check)
```

**Matching.**
- A pattern is a path split at `/`: a static segment matches itself, `{name}` any one
  non-empty segment, and a last `{name...}` or `*` the rest of the path, possibly empty
  (`/static/` matches it, `/static` does not). A trailing slash is part of the path:
  `/users` and `/users/` are different routes, and no redirect is made.
- Segment by segment, a static child is tried first, then the `{name}` child, then the
  catch-all, going back when a branch has no route for the rest of the path; so
  `/users/new` beats `/users/{id}` whatever the order of registration, and
  `/users/new/posts/3` still reaches `/users/{id}/posts/{post}`.
- The method takes part: a node only matches with a route for the request's method, then
  GET's for a HEAD request (the body is dropped when written), then `Any`'s. When no route
  matches but routes take the path with other methods, the answer is 405 with `Allow`
  (their names in order, HEAD wherever GET is); otherwise 404.
- Static segments are compared with the path as sent (still %-encoded). `q.PathParam` reads
  the matched segment, %-decoded (`%2F` gives `/` inside one parameter, `+` stays `+`), and
  `q.Pattern()` the route's whole pattern, for logs and metrics.
- Errors are found before serving (`r.Check()`, `Serve`, `Run`): a pattern not starting
  with `/`, a brace inside a static segment, a catch-all before the end, a bad or repeated
  parameter name, a bad method, two routes for the same method whose patterns match the
  same paths (`/users/{id}` and `/users/{uid}`), a mount prefix that ends in `/` or a
  catch-all, two routers mounted at the same prefix, and a router mounted inside itself.

**Groups and middleware.**
- A mounted router's patterns are its prefix plus its own (`""` is the prefix itself), and
  its chain is the outer routers' middleware, then its own, in the order added; `Use`
  covers every route of its router, whenever it is called.
- A miss is answered by the deepest router (scope) whose prefix starts the path, through
  that router's chain, with its `NotFound` / `MethodNotAllowed` handler or the nearest one
  around it (defaults: `Not Found`, `Method Not Allowed`).
- Middleware is a top-level function `func(Req, mut Out, next func(Req, mut Out))`; literals
  cannot capture, so `next` is one anvil function, and the chain's position lives in the
  `Out` (`ep`, the endpoint, and `ci`, the next middleware). A middleware may skip `next`,
  call it more than once, or wait before or after it. It hands data to later handlers with
  `w.SetValue(key, value)` / `w.Value(key)`, a list made on first use in the request's pool.

**The table.**
- Routers are built in `main` (request-pool memory) or by a function a global's initializer
  calls. `Serve` compiles one into an `rtable`: a flat trie (nodes, with indexes for children
  so the type is not recursive and `keep` can copy it), the endpoints (handler, middleware
  chain, pattern, parameter names and segments), one scope per router, and the method names
  (codes 0–8 for GET … TRACE, the others after them; masks hold up to 63).
- The table is `keep`ed into core 0's ingot heap and published in `shared var gRoutes`
  before the cores start; no core writes it afterwards. `run_request` calls
  `dispatch(gRoutes)` instead of the handler, which sets `q.ep` (for `PathParam` and
  `Pattern`) and starts the chain. Matching reads the path in place and allocates nothing.
- Static children are scanned when a node has up to 8, else found through an FNV-1a hash
  table; the method code comes from a switch on the first byte.
- `Run(method, target, body)` and `Match(method, path)` serve tests on the calling thread.
  They reuse their compiled table until any router changes (a per-core counter that every
  change bumps).
- Cost (bench/router, Apple M4 Pro): 15–25 ns per lookup with 1, 20 or 200 routes (chi:
  33–65 ns); 38–49 ns for a whole `Run` (chi's ServeHTTP: 176–212 ns). Served on one core
  with 16 pipelined requests per write, routing adds 10–15 ns of CPU to the 516 ns a request
  takes (see PERFORMANCE.md).

### Pooled clients: postgres

- `postgres.Client` keeps a FIFO pool per core (`Options.Pool`, default 16). Socket
  buffers and the 256-entry named statement cache are heap-owned; returned rows live
  in the calling task's pool. Idle sockets are checked with nonblocking `MSG_PEEK`.
  Waiters park, and a failed dial or a dropped connection wakes the next waiter to retry.
- Parameters use Parse/Bind/Describe/Execute/Sync with binary int8, float8, text, bool
  and bytea encodings. The cache keys on SQL **and parameter OIDs**. At capacity a cache
  miss closes the named statements and drains Sync before rebuilding the cache.
  Queries without values use the simple protocol and may contain multiple statements;
  Query returns the first rowset, Exec the last command's affected count, and both drain
  all replies. Use `INSERT ... RETURNING id` with Query for generated IDs.
- Result format is text, decoded using RowDescription OIDs: int2/4/8 and bool produce
  `Value.Int` (booleans are 0/1), float4/8 produce `Value.Float`, NULL produces `Value.Null`.
  Other OIDs produce `Value.Text`, including numeric, bytea, date/time, uuid and json/jsonb.
  Bytea is the server's text representation (normally `\x` followed by hexadecimal).
- ErrorResponse/NoticeResponse fields are parsed with bounded cursors. SQL errors retain
  the connection only after ReadyForQuery is consumed; I/O faults, malformed messages,
  timeouts and request deadlines drop it. `Options.Timeout` is one absolute budget for
  acquiring, connecting/authenticating, preparing and executing a statement, so notices
  and repeated reads cannot restart it. The earlier request deadline also applies.
- Begin pins a connection; SQL failure leaves it aborted until Rollback. Commit refuses
  an aborted transaction instead of reporting PostgreSQL's implicit rollback as success.
  Tx copies share state, so finishing one finishes all copies. Unfinished transactions
  are dropped at the owning request/scope's end; outside tasks finish explicitly.
- Authentication supports SCRAM-SHA-256, legacy MD5 and cleartext. SCRAM checks the nonce,
  iteration bounds and server verifier, and applies Unicode 3.2 SASLprep with PostgreSQL's
  fallback to original password bytes on invalid UTF-8/prohibited input. The fixed tables
  in `lib/postgres/sasl/sasl.tin` are regenerated by `tools/gen_saslprep.py` using Python's
  built-in Unicode 3.2 database. `seal.Pbkdf2Sha256` and its Timeout form reuse a nested allocation pool across
  rounds, yielding between batches and honoring request/operation deadlines. TLS and SCRAM channel binding are unsupported; connect through a trusted private
  network or a local TLS proxy. SSL-only servers fail clearly. CancelRequest is not sent;
  a timed-out query loses its connection and the server detects that disconnect.

## 10. JSON: argo

- `argo.Put(mut b, v)` compiles to a call of a generated encoder `argo$N(b, x)` per type.
  Constant pieces (`{"name":`) become a few word stores. Strings are scanned and copied
  8 bytes at a time with SWAR checks for `"`, `\` and control bytes. Integers are
  written digit by digit, floats via `shortest_into` straight into the buffer.
- `argo.Get(text, mut v)` compiles to a generated decoder `argo$dN(p, x)` over a `Parser`
  (text, offset, depth, first error). The readers (`robj`, `rarr`, `rkey`, `rstr`, `rint`,
  `rintr`, `ruint`, `rfloat`, `rbool`, `rnull`, `rskip`, `rmore`) record the first
  error and then do nothing, so decoders test the error only at loop boundaries.
  Strings without escapes are returned as substrings without copying.
- `rskip` and the decoders of recursive types take a stack frame per nesting level
  (32 bytes for `rskip`, 80 for a small struct, 240 for one of 32 fields), so `robj` and
  `rarr` fault once 512 arrays and objects are open: even 240-byte frames then fit in
  half of a 256 KiB task stack.

## 11. Startup sequence of a strict program

```
_start (ELF) or dyld (Mach-O) -> main (the generated __start):
  rt_init(argc, argv, number of per-core globals, __core_init)
  shared (process-wide) global initializers
  __core_init()               per-core globals of core 0
  rt_main_begin()             allocations now go to the request pool
  main.main()
  rt_exit()                   flush stdout, exit(0)
```
