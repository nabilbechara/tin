# Roadmap

## v0.3 (done 2026-10-01): a usable, documented language
1. Land in-flight work (local imports, partial stdlib packages, agent-reported compiler bugs). Done.
2. Robustness: panic backtraces, bounds failures with index and length, defer. Done.
3. Remaining stdlib: stamp, seal, ore, flume, herald, wire, crucible. Done.
4. Docs: docs/LANGUAGE.md, docs/STDLIB.md (generated), README. Done.
5. Final benchmarks (README). Done.

## Linux port (paused 2026-10-01; resume from notes/resume.md)
Phase 1 linux-arm64: done pending final re-verification. Phase 2 linux-amd64: in progress
(notes/x64_progress.md).

## v0.4 (next; design in notes/design_v04.md, waiting for the user's review): non-blocking I/O inside handlers
From the user's spec (2026-10-01):
- Stackful tasks per in-flight request on each core; waiting on a socket registers the fd with
  the core's kqueue and switches to the event loop; resume when ready. Pooled task stacks with
  guard pages; cap in-flight requests per core (backpressure).
- Request pool moves from per-core to per-request; each request's pool is wiped when it
  finishes; the region checker still forbids escapes without keep().
- Non-blocking outbound TCP client; Redis client (pooled per core, pipelined); MySQL client
  (wire protocol, prepared statements, pooled per core); every call takes a timeout and a
  deadline cancels the request.
- Small pool of blocking helper threads (file I/O, DNS) reporting back via relay.
Done when: a 100ms-wait handler on a core does not delay fast requests on that core; GET
/users/{id} via Redis cache backed by MySQL, wrk2 vs the same service in Go with chi: Tin wins
on req/s and p99, including a slow/fast mix. make bootstrap stays a fixed point, tests green.
Show the design (task switching, stack size, pool ownership) before building.
