# anvil hardening (2026-10-01)

Conformance client: `bench/http/conformance/main.go` (stdlib only, module `tinbench`).

    cd bench/http && go build -o ../../bin/agent_anvil/conformance ./conformance
    bin/agent_anvil/conformance -addr 127.0.0.1:9201 [-pid N] [-heavy=false] [-only name] [-conns 5000] [-reqs 2000000]

It prints PASS/FAIL per case and exits 1 on any failure or if the server stops answering
between cases. The server pid (for RSS checks) comes from `-pid` or `lsof` on the port.

## Cases (26, all PASS after the fixes; 1 core and all cores)

| case | what it checks |
|---|---|
| pipelined-10 | 10 GETs in one write, 10 responses in order |
| pipelined-mixed | GET, POST+body, HEAD, GET in one write: framing survives |
| slow-1-byte-writes | request line + headers written one byte at a time |
| slow-body-bytes | body trickles in one byte at a time after the headers |
| headers-9KB / headers-40x1KB | large header blocks are served |
| headers-70KB-unterminated | header block past 64KB with no end -> 431 + close |
| request-line-70KB | 70KB request line -> 414 + close |
| post-body-{0,1,65536,5242880} | Content-Length bodies; /echo length matches; connection reusable after |
| transfer-encoding-chunked | -> 501 + close |
| http10-closes / http10-keepalive | HTTP/1.0 closes; `Connection: keep-alive` keeps it open |
| http11-connection-close | `Connection: close` on 1.1 closes after the response |
| head-no-body | HEAD has Content-Length of the GET body and no body bytes (follow-up GET framed) |
| malformed-request-line | 7 variants (garbage, no version, leading/double space, XTTP, empty method, TLS bytes) -> 400 + close |
| bad-content-length | `abc`, `-1`, `1x2`, 20-digit -> 400/413/close, never a hang |
| client-close-mid-request | partial line, partial headers, partial body, 300KB of a 5MB body, RST mid-body; server alive |
| query-param-decoding | 11 cases via /echo: %20, +, UTF-8, bad escapes kept literally, empty, missing, prefix names |
| large-response-pipelined | 5 x 120KB responses pipelined (pending-output path); `HXYZ` is not HEAD |
| pipelined-no-read-backpressure | 300k pipelined requests, client reads nothing for 2s: RSS growth < 8MB, all 300k delivered |
| 5000-conns-idle-reuse | 5000 connections opened gradually, each served, idle 2s, each served again |
| resets-under-load | 16 good clients + 16 RST clients (SO_LINGER 0, at 4 request stages) for 3s: zero good errors |
| rss-flat-2M | 2M pipelined requests: RSS before/mid/after within 10% |

## Bugs found and fixed in lib/anvil.tin

1. Request line > 64KB was served when it arrived complete (only the no-newline case gave
   414). Now `le > maxLine` -> 414 + close.
2. Header block > 64KB was accepted when complete (431 only fired without a newline). Now
   `pos+l > maxLine` inside the header loop -> 431 + close.
3. Content-Length was parsed by skipping non-digits: `abc` -> 0 (served), `-1` -> 1 and
   `1x2` -> 12 (connection hangs waiting for a body that never comes). New `parse_cl`:
   OWS, >=1 digit, OWS, nothing else, else 400 + close; values past maxRequest -> 413.
4. `GET  /json HTTP/1.1` (two spaces) was served with path ` /json` (404). The request line
   now needs exactly two spaces and a `HTTP/1.` version, else 400.
5. No read backpressure: a client that pipelines without reading made the server buffer
   every response in `cOut` (+45MB RSS for 300k requests on one connection, unbounded).
   `flush` now disables EVFILT_READ while output is pending; `on_write` re-enables it when
   drained and re-runs `on_read` for input that was already buffered. Growth is now the
   socket buffers only (+1.3..2.5MB observed).
6. Method matching was by prefix: any 4-letter `H...` method was treated as HEAD (no body
   sent, client hangs), `PO..` as POST, `PU.` as PUT, `D.....` as DELETE. Now exact matches
   (`bytes_are`).
7. `Connection:close` without a space after the colon was not recognised (OWS now skipped).
8. EMFILE/ENFILE on accept spun the level-triggered listen event at 100% CPU while the
   waiting clients hung. Core 0 now keeps a spare fd (`/dev/null`): on EMFILE it closes it,
   accepts and closes one connection (the client gets a clean EOF), and reopens the spare.
   Verified with a server under `ulimit -n 256` and 400 connections: 248 served, 152 EOF,
   case done in 2.1s, server at 0% CPU and still passing the light suite afterwards.

## Perf (hammer, `-path /json -c 100 -t 8 -d 5s`, TIN_CORES=1)

The machine was heavily loaded by other agents during the session (load average 8-22, a
benchmark at 98% CPU), so absolute numbers moved by +-20% between runs. Interleaved
old/new runs are the fair comparison and show no regression:

- before any change: 296,920 req/s (p50 0.290ms, p99 0.766ms)
- interleaved old/new: 254,736 / 212,995, 269,097 / 285,273 (4s runs)
- interleaved old/new under heavier load: 158,398 / 153,009, 175,890 / 171,590 (4s runs)
- final interleaved 5s runs (load average 8): old 267,402 / 295,685, new 282,094 / 297,853
  (new p99 0.800 / 0.707ms vs old 1.251 / 0.734ms)

RSS over 2M pipelined requests: flat (e.g. 2400 -> 2384 KB; 10144 -> 9952 KB).

## Known gaps (not fixed)

- No idle-connection timeout: idle connections live forever (96-byte record + fd each).
- Out of fds, connections are dropped one per listen wake-up rather than queued; raising
  RLIMIT_NOFILE at startup (`setrlimit`, min(hard, OPEN_MAX) on macOS) would be the next step.
- `Expect: 100-continue` is ignored (curl waits 1s before sending the body).
- Absolute-form targets (`GET http://host/p HTTP/1.1`) are routed as path `http://host/p`.
- Missing `Host` on HTTP/1.1 is accepted; duplicate Content-Length: the last one wins.
- Responses to HTTP/1.0 requests carry `HTTP/1.1` in the status line (allowed by RFC 7230).
- During the session lib/argo.tin was temporarily uncompilable by another agent's edit; the
  build used a shadow TIN_ROOT (`bin/agent_anvil/root`, symlinks + the last-good argo.tin).
