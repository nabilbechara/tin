# The Tin runtime and the server stack: how they work

The runtime is `lib/runtime.tin` (portable) plus `lib/runtime_darwin.tin` /
`lib/runtime_linux.tin` (and `runtime_linux_<arch>.tin`), compiled into every strict
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
| fault | a pointer to a str (the message), or 0 for nil |
| func value | the code address |

Map hashing: strings use a 64-bit multiply-mix hash over 8-byte words, integers a
Fibonacci multiply; the table grows at half load.

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
| 10–25 | ctxFree | ingot free lists, one per size class |
| 26, 27 | ctxSlab, ctxSlabEnd | ingot slab bump |
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
  `hearth.Reset()` exposes it.
- Plain programs never reset: they release everything at exit.

**Ingot heap.** `rt_ingot_alloc(n)` serves blocks from 16 size classes (16, 32, 48, 64,
96, 128, 192, 256 ... 3072, 4096 bytes including an 8-byte class header):
- a block is taken from the class's free list, or else carved from a 1 MiB slab;
- bigger blocks come from calloc with a -1 header;
- `rt_ingot_free(p)` pushes a block onto its core's free list. Maps in the ingot heap
  free their old tables when they grow. Blocks never cross cores.

**Initialization.**
- `rt_init` creates core 0's context in ingot mode.
- Global initializers allocate in the ingot heap.
- `rt_main_begin` switches to the request pool before `main.main`.
- Each extra core runs `__core_init` (the per-core global initializers) in ingot mode,
  then switches to its pool.

**keep.** `keep(x)` calls a generated `keep$N` function per type. It copies strings
(`rt_keep_str`), structs (`rt_keep_raw`, then their reference fields), slices
(`rt_keep_slice`, then elements) and maps (a new ingot map, entry by entry) into the
ingot heap.

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
  `snprintf("%.*e")` is tried at increasing precision and checked with `strtod`.
  `rt_float_json` uses JSON's exponent rule.

## 7. Panics and backtraces

- `rt_panic(msg)` flushes stdout, prints `panic: msg`, walks the frame-pointer chain from
  `__fp()`, names each return address with `dladdr`, and exits with status 2.
- The walk skips `rt_` frames and stops at the program entry.
- On Linux the ELF exports functions as `tin.<name>` with sizes, so `dladdr` can name
  them; the prefix is stripped when printing.
- `rt_bounds_fail2(i, n)` and `rt_div_fail()` are the cold paths of failed checks.

## 8. The OS layer

Everything that differs between macOS and Linux sits behind `rt_` helpers with the same
names in both OS files:

| helper | macOS | Linux |
|---|---|---|
| `rt_errno()` | `__error()` | `__errno_location()` |
| `rt_mono_ns()`, `rt_wall_ns()` | `clock_gettime_nsec_np(8 / 0)` | `clock_gettime(CLOCK_MONOTONIC / REALTIME)` |
| `rt_random(p, n)` | `arc4random_buf` | `getrandom` (loop) |
| `rt_ncpus()` | `sysconf(58)` | `sysconf(84)`, plus affinity and cgroups |
| `rt_sockaddr_in(sa, ip, port)` | `sin_len` + family bytes | u16 family |
| `rt_ai_addr(ai)` | addrinfo + 32 | addrinfo + 24 |
| `rt_nosigpipe(fd)` | `SO_NOSIGPIPE` | ignore SIGPIPE process-wide |
| `rt_stat_mode/size/mtime/dev/ino(st)` | struct stat offsets | glibc offsets (st_mode differs between arm64 and amd64: per-arch file) |
| `rt_dirent_name(ent)` | `d_namlen` + `d_name@21` | `strlen(d_name@19)` |
| `rt_core_qos(core)` | QoS user-interactive | CPU pinning when safe |

Constants with the same names in both files: `EINTR EAGAIN EINPROGRESS ENOENT EEXIST
ENOTDIR EINVAL EMFILE ENFILE O_WRITE_CREATE O_APPEND_CREATE O_NONBLOCK F_GETFL F_SETFL
SOL_SOCKET SO_REUSEADDR SO_REUSEPORT SO_ERROR SO_RCVTIMEO SO_SNDTIMEO TARGET_LINUX`.
`notes/linux_abi.md` holds every verified value and layout.

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
  written.

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
- A malformed request line, a header line that is not `name: value` (no colon,
  whitespace before it, obs-fold, a name that is not a token) or a bad
  `Content-Length` gets 400; `Transfer-Encoding` gets 501.
- Bodies are limited to 64 MiB (413).
- HTTP/1.0 closes unless keep-alive is asked for; `Connection: close` is honored.
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
- A connection closed while its request waits is marked dead and freed when the task ends.
- Finished tasks go on a per-core free list with their stacks and pools.

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
- Work with no non-blocking form (DNS `getaddrinfo`, file reads and writes in `quarry`)
  goes to four shared helper threads. `rt_helper_run(f, job, drop)` queues a heap-owned
  job in a bounded queue (4096 outstanding jobs process-wide), signals a non-blocking
  wake pipe and parks within the request deadline. A full queue fails immediately.
  A helper runs `f(job)` and writes the completion to the owning core's done pipe.
  Inputs and results live outside request pools, so an expired request may return and
  reuse its task safely. A late completion calls `drop(job)` and never resumes the old
  task. Already-running system calls can still finish after the caller's deadline;
  their results are discarded. Outside a task the helper runs synchronously.
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
