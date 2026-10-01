# v0.4 design: non-blocking I/O inside handlers

Status: proposal, waiting for review. Nothing below is built yet.

## 1. Tasks: stackful, per in-flight request, per core

- **Task** = a stack + a saved register set + a request pool + a deadline. One task per
  in-flight request; a core runs many tasks, one at a time, on its own thread.
- **Switch**: a new compiler intrinsic `__swap(from, to)` saves and restores what the ABI
  requires across a call: x19–x27, x29 (fp), x30 (lr), sp, d8–d15 (21 words, stp/ldp
  pairs, about 20 instructions, ~10 ns). x28 (the core context) is the same on both sides
  and is not saved. No signals, no setjmp, no kernel involvement.
- **Stacks**: mmap'd from a per-core arena, 256 KiB of address space each, with a 16 KiB
  guard page (the arm64 macOS page) below it (`mprotect(PROT_NONE)`). Only touched pages
  become resident, so a typical handler costs 16–32 KiB of memory. Freed stacks go on a
  per-core free list (no munmap), capped at 1024 cached stacks per core.
- **Overflow**: a SIGSEGV handler on a sigaltstack recognizes a guard-page hit and prints
  "stack overflow in a request task" with a backtrace, instead of a silent crash. The
  compiler emits stack probes in functions with frames larger than the guard.
- **Backpressure**: at most N in-flight tasks per core (default 4096). At the cap the core
  stops reading from its connections (read filters disabled) and core 0 stops dealing it
  new connections, until tasks finish.
- **Ordering**: HTTP/1.1 responses on one connection stay in request order: a
  connection's next pipelined request starts after the previous task finishes.

## 2. Scheduler: the core's kqueue loop

- Ready queue (FIFO) of runnable tasks plus the kqueue. The loop runs every ready task
  until it finishes or waits, then blocks in kevent.
- A task that would block (EAGAIN on a socket) registers the fd with the core's kqueue
  (`udata` = the task, EV_ONESHOT) and switches to the loop; the event resumes it.
- Deadlines: one EVFILT_TIMER per core armed for the earliest deadline (a min-heap of
  waiting tasks). On expiry the waiting call returns the fault `deadline exceeded` and
  its fd registration is dropped; the handler must handle the fault (Tin rejects ignored
  faults).
- Handlers that never wait pay only a task pop/push and two switches (~50 ns against ~3 µs
  of syscalls per request today), so the fast path stays within a few percent.

## 3. Memory: the pool moves from the core to the request

- Today each core has one request pool, wiped after every response. New: each task owns
  a pool made of 64 KiB chunks from a per-core chunk cache. `rt_alloc`'s fast path is
  unchanged (bump pointer and end in the core context); a switch saves and restores those
  two words into the task.
- When a task finishes, the used part of its chunks is zeroed and the chunks go back to
  the core's cache; large blocks are freed.
- **Ownership**: a task owns its pool; the core owns the chunk cache and the ingot heap;
  nothing crosses cores. Suspended tasks keep their pools intact, so several requests can
  hold memory at once.
- **Region checker**: rules unchanged. Request memory (a task's pool) may not be stored
  into globals or anything reachable from them without `keep()`. Per-core shared objects
  (connection pools, caches) are globals, so they already live in the ingot heap. Data a
  client hands back to a handler is copied into the handler's task pool.

## 4. Clients

- **wire** becomes task-aware: non-blocking sockets; inside a task a would-block
  suspends; outside one (plain programs) it falls back to `poll`. Every call takes a
  timeout; the request deadline caps it.
- **Redis client** (proposed name `cask`): RESP2/3, a per-core pool of connections.
  Commands from concurrent tasks on the same connection are pipelined: one write per batch,
  replies matched in FIFO order.
- **MySQL client** (proposed name `ledger`): the client/server protocol with
  `mysql_native_password`, and `caching_sha2_password` (MySQL 8 default) including full
  authentication over the RSA public key exchange. That needs RSA-OAEP and a small bignum
  in `seal`. Prepared statements (COM_STMT_PREPARE/EXECUTE, binary rows), a per-core pool,
  and a statement cache per connection.

## 5. Blocking helpers

- A small process-wide pool of helper threads (default 4) for calls with no non-blocking
  form: getaddrinfo, file reads and writes, fsync. A task posts a job and suspends; the
  helper runs it and sends the result to the owning core through its relay inbox, which
  resumes the task. quarry/flume/wire DNS route through it automatically inside tasks.

## 6. Done when

- A test proves a 100 ms handler on a core does not delay fast requests on that core.
- `GET /users/{id}` reads through a Redis cache backed by MySQL, returns JSON, and beats
  the same service in Go with chi under wrk2 on req/s and p99, including a mix of slow and
  fast requests.
- `make bootstrap` stays at a fixed point; all tests stay green.

## Needs from the user

- Building wrk2 from its GitHub source (it is not in Homebrew core), and adding the
  go-chi/chi module for the Go service.
- Running private Redis and MySQL instances on separate ports with their own data
  directories under /private/tmp (the Homebrew Redis 7.2 and MySQL 8.0 installs are
  present). The existing instances are left alone.
