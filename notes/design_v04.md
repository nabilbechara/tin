# v0.4 design: non-blocking I/O inside handlers

Status: agreed in outline (2026-10-01); built in phases 9–13 of #46, after the v0.5 syntax
phases, so the clients use the final syntax. Targets: darwin-arm64, linux-arm64,
linux-amd64.

Goal: a handler can wait on a database, Redis or another service without stalling the
other requests on its core.

## 1. Tasks: stackful, one per in-flight request, per core

- **Task** = a stack + a saved register set + a request pool + a deadline. A core runs many
  tasks, one at a time, on its own thread.
- **Switch**: a compiler intrinsic `__swap(from, to)` saves and restores only what the ABI
  keeps across a call. No signals, no setjmp, no kernel involvement (~10 ns).
  - arm64: x19–x27, x29 (fp), x30 (lr), sp, d8–d15 (21 words, stp/ldp pairs). x28 (the
    core context) is the same on both sides and is not saved.
  - x86-64 (System V): rbx, rbp, r12–r14, rsp and the return address, plus the MXCSR and
    x87 control words. r15 (the core context) is the same on both sides and is not saved.
- **Stacks**: mmap'd from a per-core arena, 256 KiB of address space each, with a guard
  region below (`mprotect(PROT_NONE)`) of one page: 16 KiB on macOS arm64, 4 KiB on Linux
  (taken from `sysconf(_SC_PAGESIZE)`). Only touched pages become resident, so a typical
  handler costs 16–32 KiB. Freed stacks go on a per-core free list (no munmap), capped at
  1024 per core.
- **Overflow**: every core thread has a sigaltstack; the SIGSEGV handler recognizes an
  address inside a guard region and prints "stack overflow in a request task" with a
  backtrace. The compiler emits stack probes in functions whose frame is larger than the
  smallest guard (4 KiB).
- **Backpressure**: at most 4096 in-flight tasks per core. At the cap the core stops reading
  from its connections and stops taking new connections (handoffs go to other cores),
  until tasks finish.
- **Ordering**: HTTP/1.1 responses on one connection stay in request order: a connection's
  next pipelined request starts after the previous task finishes.

## 2. Scheduler: the core's event loop

- A FIFO ready queue of runnable tasks, plus the core's poller: kqueue on macOS, epoll on
  Linux, both behind the existing `ev_*` layer in `anvil_darwin.tin` / `anvil_linux.tin`.
  The loop runs every ready task until it finishes or waits, then blocks in the poller.
- A task that would block (EAGAIN) registers its fd for the event it needs (kqueue
  EV_ONESHOT; epoll EPOLLONESHOT, re-armed with EPOLL_CTL_MOD) with the task as user data,
  and switches to the loop; the event resumes it.
- Deadlines: one timer per core (EVFILT_TIMER on macOS, a timerfd on Linux) armed for the
  earliest deadline in a min-heap of waiting tasks. On expiry the waiting call returns the
  fault `deadline exceeded` and its registration is dropped; the handler must handle the
  fault (Tin rejects ignored faults).
- A handler that never waits pays only a task pop/push and two switches (~50 ns against
  ~3 µs of syscalls per request today), so the fast path stays within a few percent.

## 3. Memory: the pool moves from the core to the request

- Today each core has one request pool, wiped after every response. New: each task owns a
  pool made of 64 KiB chunks from a per-core chunk cache (sized by `hearth.PoolChunk()`
  under a container memory limit). `rt_alloc`'s fast path is unchanged (bump pointer and end
  in the core context); a switch saves and restores those two words into the task.
- When a task finishes, the used part of its chunks is zeroed and they return to the
  core's cache; big blocks are freed.
- **Ownership**: a task owns its pool; the core owns the chunk cache and the ingot heap;
  nothing crosses cores. Suspended tasks keep their pools intact.
- **Region checker**: rules unchanged. Request memory may not reach globals without
  `keep()`. Per-core shared objects (connection pools, caches) are globals, so they live in
  the ingot heap. Data a client hands back to a handler is copied into the handler's pool.

## 4. Clients (named after what they talk to)

- **`wire`** becomes task-aware: non-blocking sockets. Inside a task a would-block suspends
  the task; outside one (plain programs) it waits with `poll`. Every call takes a timeout,
  capped by the request deadline. The response parsing hardened in #43/#44 is kept.
- **`redis`**: RESP2/3, with replies as an enum (`Str`, `Int`, `Array`, `Err`, `Nil`), and a
  per-core pool of connections. Commands from concurrent tasks on one connection are
  pipelined: one write per batch, replies matched in FIFO order. Commands take a `query`
  (an interpolated literal), so values are always sent as separate arguments.
- **`mysql`**: the client/server protocol with `mysql_native_password` and
  `caching_sha2_password` (the MySQL 8 default), including full authentication over the
  RSA public-key exchange. That needs RSA-OAEP and a small bignum in `seal`. Prepared
  statements (COM_STMT_PREPARE/EXECUTE, binary rows), a per-core pool and a statement cache
  per connection. Queries take a `query`: in `db.Query("SELECT * FROM users WHERE id =
  {id}")` the text becomes `... id = ?` and `id` a bound parameter; a plain `str` is
  rejected at compile time.

## 5. Blocking helpers

- A small process-wide pool of helper threads (default 4) for calls with no non-blocking
  form: getaddrinfo, file reads and writes, fsync. A task posts a job and suspends; the
  helper runs it and sends the result to the owning core through its relay inbox, which
  resumes the task. quarry, flume and wire DNS route through it automatically inside tasks.

## 6. Done when

- A test proves a 100 ms handler on a core does not delay fast requests on that core, on
  all three targets.
- `GET /users/{id}` reads through a Redis cache backed by MySQL, returns JSON, and beats the
  same service in Go with chi under wrk2 on req/s and p99, including a mix of slow and fast
  requests.
- `make bootstrap` stays at a fixed point and CI stays green on all three native platforms.

## Needs from the user (asked before phase 13)

- Building wrk2 from its GitHub source (it is not in Homebrew core), and the go-chi/chi
  module for the Go service.
- Private Redis and MySQL instances on separate ports with their own data directories under
  /private/tmp (the Homebrew Redis 7.2 and MySQL 8.0 installs are present). The existing
  instances are left alone.
