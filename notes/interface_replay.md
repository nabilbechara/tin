# Interface: production replay (runtime, capsules, secrets, scheduling) — #241

Status: **proposed**, for approval by the members of the interface: #239 (`secret`), #242
(replay tooling), #243 (scheduling replay) and #232 (structured concurrency). Nothing builds on
it before each has approved the PR that adds this file (AGENTS.md, Tin 1 rule 5). After that, a
change to a name, a layout or a rule below needs the same approvals.

Spec: `notes/design_semantics.md` §12 (replay), §9 (secrets in replay), §6 (deterministic
order on a core). This file fixes the runtime names, the byte layouts and who implements
what. It changes no rule of the spec.

Words below are 8-byte little-endian integers; a **string** is a word (its length) followed by
its bytes, no padding.

---

## 1. Switches (environment, read once by anvil before the cores start)

| variable | meaning |
|---|---|
| `TIN_REPLAY_DIR` | spool directory. Unset or empty: recording is off. |
| `TIN_REPLAY_KEY` | 64 hex digits (32 bytes). Required with `TIN_REPLAY_DIR`; missing or malformed: recording stays off and anvil prints one line on stderr. Never written anywhere. |
| `TIN_REPLAY_SAMPLE` | fraction (`0` to `1`, decimal) of requests ending below 500 that are also captured. Default `0`. |
| `TIN_REPLAY_MAX_MB` | spool bound in MiB, default 256: the oldest capsules are deleted first (section 6). |
| `TIN_REPLAY_SECRET_HEADERS` | extra header names (comma list) stored as keyed hashes; added to the defaults `Authorization`, `Proxy-Authorization`, `Cookie`. |
| `TIN_REPLAY_DROP_HEADERS` | header names whose values are not stored at all (PII policy); the value becomes empty. |
| `TIN_REPLAY_CAPSULE` | set by `tin replay` (#242): the program replays this one capsule instead of serving. |
| `TIN_REPLAY_LIVE` | with `TIN_REPLAY_CAPSULE`: effect kinds (comma list, without `@version`) served by real calls (`--live KIND`). |

## 2. The tape (runtime)

A **tape** is the effect log of one request, recording or replaying. It is a block of
`tpWords` words from `malloc` (never pool memory: it outlives a panic's unwind and is not
charged to a `limit`), owned by the request.

| task word | meaning |
|---|---|
| `tTape = 56` | the task's tape, 0: none. `taskWords` becomes 57 (word 55 is `tScopeWait`, #232). |

- anvil sets `tTape` on a request task before it first runs, when recording or replaying.
- `s.spawn`, `parallel` (scope children, `bkTask` under a scope of a taped task) copy the
  spawning task's `tTape`: a request's children share its tape. `detach`, ticks, relay
  handlers and `on` handlers start with 0: they are not part of a request.
- Code on a core's own stack (`main`, initializers, the event loop) has no tape.

| tape word | name | meaning |
|---|---|---|
| 0 | `tpMode` | 1 recording, 2 replaying |
| 1–3 | `tpBuf`, `tpLen`, `tpCap` | the effect records (section 3.3), malloc'd bytes |
| 4 | `tpSeq` | effects so far |
| 5 | `tpPos` | replaying: offset of the next recorded effect in `tpBuf` |
| 6 | `tpDiverged` | replaying: 0, or the first divergence (a malloc'd string, section 3.4) |
| 7 | `tpRand` | dice: this request's generator (a `dice.Rand` in the request pool), 0 until first use |
| 8, 9 | `tpReq`, `tpReqLen` | the request bytes as received (malloc'd copy) |
| 10 | `tpStatus` | the response status (anvil sets it before responding) |
| 11, 12 | `tpPanic`, `tpPanicLen` | the panic message, if the request panicked (malloc'd) |
| 13 | `tpWall` | wall clock (ns) when the request started |
| 14 | `tpLive` | replaying: the `TIN_REPLAY_LIVE` kinds (a malloc'd comma list), 0: none |
| 15 | `tpSched` | reserved for #243 (scheduling state) |

`tpWords = 16`. Functions (all in `lib/runtime/replay.tin`, a new file of the runtime package):

| function | does |
|---|---|
| `rt_tape() i64` | the running task's tape, 0 when off: one per-core load and a branch. Every effect call site tests it first, so recording off costs that and nothing else. |
| `rt_tape_new(mode i64) i64` | a zeroed tape |
| `rt_tape_free(tp i64)` | frees the tape and everything it owns |
| `rt_tape_load(tp i64, p i64, n i64)` | replaying: the effect section of a decoded capsule becomes the records to serve (copied) |
| `rt_tape_diverged(tp i64) str` | the first divergence, "" if none |
| `rt_tape_left(tp i64) i64` | replaying: recorded effects not yet served (a replay that ends with some left diverged too) |

## 3. The hook

### 3.1 Calls with a result that can fail

```
func rt_effect(tp i64, kind str, key str, body func() !str) !str
```

- **Recording:** runs `body`; appends `(seq, kind, key, outcome)` (3.3) where the outcome is
  `body`'s result or fault; returns that result or fault unchanged. `body` runs with the
  calling task's tape **suspended** (`tTape` holds the tape with its low bit set, and
  `rt_tape()` gives 0), so `body` may call the client's own public function again and that
  live call is not recorded twice. `rt_tape_of(t)` gives a task's tape either way.
- **Replaying:** takes the next record. If its `kind` and `key` equal the arguments, returns its
  result, or fails with its fault rebuilt (3.3), **without running `body`**. Otherwise it is a
  divergence (3.4). If the kind (before `@`) is in `tpLive`, `body` runs and its outcome is
  returned instead (the record is still compared and consumed).
- `body` returns the result **encoded** as a string (the kind's layout, section 4); the client
  decodes it. Encoding happens only when a tape exists.

### 3.2 Values that cannot fail

```
func rt_effect_word(tp i64, kind str, key str, live i64) i64
func rt_effect_bytes(tp i64, kind str, key str, live str) str
```

The caller computes `live` (reading a clock or the OS random source has no outside effect).
Recording appends it and returns it; replaying returns the recorded value. A divergence here
panics with the divergence message, since there is no fault to return.

### 3.3 Effect records (the tape's bytes and the capsule's effect section)

```
word   seq        0, 1, 2 ... in the order the effects completed on the core
string kind       "name@version", e.g. "redis@1"
string key        what was asked, in the kind's key layout (section 4); secrets as handles (section 5)
word   outcome    0: result; 1: fault
word   ident      fault only: the runtime sentinel in its chain (faultCanceled ... faultPanic, 1–6), else 0
string data       result: the encoded value; fault: its message (the text say.Str gives)
```

A recorded fault is rebuilt as a fault with that message whose cause is the sentinel
`rt_fault_std(ident, ...)` when `ident != 0`, so `fault.Is(err, fault.DeadlineExceeded)` and
the messages tests read stay true. Library sentinels compare by message today (`wire.IsEOF`)
and keep working.

### 3.4 Divergence

The first effect whose `kind` or `key` differs from the next record, or that comes after the
last record, is a divergence. The tape keeps the first one:

```
replay: divergence at effect N: got KIND "KEY", recorded KIND "KEY"
replay: divergence at effect N: got KIND "KEY", recorded nothing more
```

(keys shortened to 200 bytes in the message). From then on every effect of the tape fails (or
panics, 3.2) with that message: replay never falls through to a live call.

## 4. Effect kinds

Every kind is `name@version`. A version changes when its key or result layout changes; the
replayer (#242) refuses a capsule with a kind or version this build does not list, naming it.

| kind | key | result | recorded in |
|---|---|---|---|
| `tide.now@1` | "" | word: mono ns | `tide.Now` (and `Since`) |
| `tide.wall@1` | "" | word: wall ns | `tide.Wall` |
| `dice.seed@1` | "" | word: the seed of this request's generator | `dice` package functions, at the first draw of a request (they then draw from `tpRand`, not the core's generator) |
| `seal.random@1` | decimal n | the n bytes | `seal.RandomBytes` |
| `wire.http@1` | method, " ", URL, then for each header "\n" name ": " value, then "\n\n" and the body | word status, string head, string body | `wire.DoWith` (so `Get`, `Post`, `Do`) |
| `wire.dial@1` | address | word: the connection's number in this request (1, 2, ...) | `wire.Dial`, `DialTimeout` (raw TCP) |
| `wire.read@1` | connection number, " ", max | the bytes (EOF: the `EOF` fault) | `Conn.Read` and what reads through it |
| `wire.write@1` | connection number, " ", the bytes | "" | `Conn.Write`, `WriteBytes` |
| `redis@1` | the commands: each word as its decimal length, ":" and its bytes, words separated by " ", each command ended by "\n" (`3:GET 6:cart:7\n`) | the raw RESP replies as received | `Do` and `Pipe` (so every helper on them) |
| `mysql@1` | "Q " or "E " (Query or Exec), the query parts and arguments (section 5.3) | Rows or Result, encoded by the client | `Query`, `Exec`, and the same on `Tx`; `Begin`, `Commit`, `Rollback` as `mysql.tx@1` |
| `postgres@1` | as `mysql@1` | as `mysql@1` | as `mysql@1` (`postgres.tx@1`) |
| `websocket.dial@1`, `.read@1`, `.write@1` | as `wire.*`; read result: word kind, string data | | the client and an accepted connection |
| `quarry.read@1` | path | the content | `ReadFile` |
| `quarry.write@1` | "w " or "a ", path, "\n", data | "" | `WriteFile`, `AppendFile` |
| `quarry.stat@1` | "exists " / "isdir " / "size " / "mtime " + path | word | `Exists`, `IsDir`, `Size`, `ModTime` |
| `quarry.dir@1` | path | the names, each a string | `ReadDir` |
| `quarry.fs@1` | "rm " / "rmall " / "mv " / "mkdir " / "mkdirall " + paths | "" | `Remove`, `RemoveAll`, `Rename`, `Mkdir`, `MkdirAll` |
| `sched.*@1` | section 7 | | #243 |

DNS is not a kind of its own: it happens inside `wire.http`/`wire.dial`, which replay does not
perform. A library that adds an effect adds a row here (approval by #241's owner).

## 5. Secrets

The runtime never sees `secret` (#239): it is erased below the checker. A secret reaches an
effect only through a library parameter declared `secret` or a policy, and the library puts its
**handle** in the key instead of its text.

### 5.1 Handles

```
func rt_secret_key(s str) str
```

returns `tin-secret:` followed by 32 lower-case hex digits: the first 16 bytes of
HMAC-SHA256(*K*s, s), where *K*s = HMAC-SHA256(`TIN_REPLAY_KEY`, "tin replay secret"). The
hash is computed by `lib/replay` (which imports `seal`) through the shared hook
`rtSecretHash func(str) str` it installs before the cores start; the runtime holds no key.
A string that already is a handle is returned unchanged, so on replay the **stand-in** (the
handle itself) hashes to the recorded handle: the same keys compare equal.

### 5.2 What is hashed

- **Request headers** named in the secret list (section 1) are stored with their value
  replaced by its handle; on replay the handler reads the handle as the header's value.
  Dropped headers are stored empty. The body and the URL are stored as received.
- **`wire.http@1` keys**: the values of headers in the same list.
- **Library parameters declared `secret`** that reach a key: always their handle.
- **Query arguments (5.3).**

Results are stored as received (encrypted at rest, section 6). A capsule never holds the text
of a value that the program had typed `secret`.

### 5.3 Query arguments

`query` gains a field: `struct { Parts []str; Args []qarg; Hidden u64 }`. Bit `i` of `Hidden` is
set when the value written in `{...}` for `Args[i]` (i < 64) has a secret type; the compiler sets
it, and a query literal may then take a secret value where a `query` is wanted (the client opts in
by taking a `query`). Clients write an argument with its bit set as `rt_secret_key(text)`. Until
this lands (a later #241 slice, in `selfhost/secret.tin` and `lower.tin`, approved by #239),
a secret cannot reach a query at all (the #239 sink rule), so none reaches a key.

Key layout of a query (redis words, SQL text): the parts and arguments in order, each argument
as `I` decimal, `F` the shortest float text, `S` string, `B` `true`/`false`, `X` hex bytes, or
`H` handle, each part and argument followed by "\n".

## 6. Capsules and the spool

**Capture.** When a request task ends, anvil asks `lib/replay` to keep its tape if the status is
500 or more, or it panicked, or it is in the sample; otherwise the tape is dropped. Writing
happens on the core after the task ended (no tape is active then), so it is never recorded.

**File.** `TIN_REPLAY_DIR/<wall ns, 20 digits>-<core, 3 digits>-<n>.tcap`, written to a
`.tmp` name and renamed. The bound: at start, anvil deletes the oldest `.tcap` files (by name)
while the directory holds more than `TIN_REPLAY_MAX_MB`; then each core keeps the capsules it
wrote under `MAX_MB / cores` and deletes its oldest first.

**Envelope (encrypted at rest).**

```
8 bytes   "TINCAP\x01\x00"  magic and envelope version
16 bytes  nonce (seal.RandomBytes)
n bytes   body XOR keystream; keystream block i = HMAC-SHA256(Ke, nonce || word i)
32 bytes  tag = HMAC-SHA256(Km, magic || nonce || ciphertext)
```

Ke = HMAC-SHA256(K, "tin replay enc"), Km = HMAC-SHA256(K, "tin replay mac"), K the 32 bytes of
`TIN_REPLAY_KEY`. A wrong key or a changed byte fails the tag: "capsule: wrong key or damaged".
(A PRF in counter mode with encrypt-then-MAC; Python's `hmac` checks it with the standard
library.)

**Body.**

```
word   schema      1
string tin         the Tin version (`VERSION`, "dev")
string program     argv[0]
word   wall        tpWall
word   core
word   status      tpStatus (500 or 504 after a panic)
word   flags       1 panicked, 2 sampled
string request     the request bytes with secret headers as handles (5.2)
string panic       the panic message, "" if none
word   count       effect records
...    records     section 3.3
```

## 7. Scheduling events (#243)

Recorded in the same log, in completion order, with these kinds (result layouts fixed here; the
hooks are #243's, placed next to #232's code):

| kind | key | result | recorded when |
|---|---|---|---|
| `sched.select@1` | the select's site: file ":" line | word: the winning arm, 0-based in source order | a `select` picks an arm |
| `sched.resume@1` | "" | word: the task's number in the request (0 the request task, then children in spawn order) | a task of the request resumes after a wait |
| `sched.cancel@1` | the canceled boundary's kind and its task's number | fault outcome: the reason | a boundary of the request is cancelled |

Replaying, a `select` waits for the recorded arm only; the run queue of a request's tasks is
ordered by the recorded `sched.resume` events. Recording these is #243's slice; #241 records
no scheduling.

### 7.1 Details (#243)

- **Select site.** `file` is the base name of the source file (`sched.tin:17`), so a capsule
  replays against a build made in another directory.
- **Select arm.** 0 to n-1 for the arms in source order; n (the number of arms) when the select
  left with its boundary's fault (a cancelled boundary and no `canceled()` arm). Replaying, a
  select checks, watches and waits for the recorded arm only; a cancelled boundary still ends
  it, and an arm other than the recorded one is a divergence. A select whose record diverges
  runs live: the first divergence is what the replay reports.
- **Resumes.** `sched.resume@1` is appended each time a task of the request is switched in,
  a child's first run included, except while its tape is suspended (inside an effect's body:
  a replayed effect does not wait, so the waits inside a live call are not events). Task
  numbers come from `tpSched`: the request task is 0; a child gets the next number when it is
  spawned.
- **Effects of several tasks.** The tape holds effects in completion order, which can differ
  from the order a request's tasks issue them. Replaying, a task whose effect is not the next
  record waits until it is (a task's own effects keep their order). When no task of the
  request can move on (each waits for its turn or is held for its resume), the replay has
  diverged, with the message of the effect that could not be served.
- **Cancels.** The key of `sched.cancel@1` is the boundary's kind (`request`, `task`, `guard`,
  `within`, `limit`, `scope`, `arena`, `with`), " " and its task's number (`within 0`); the
  outcome is the reason as a fault (section 3.3, with its sentinel). One record per cancel of a
  request's boundary: the boundary cancelled, or for a drain (the core's boundary) each request
  boundary it reaches. A deadline is recorded when it ends a wait of the request (before that
  task's resume) or when a running task finds it past.
- **Replaying cancels.** Deadlines and drains do not cancel a replaying request by the clock:
  their records are applied when they are the next record (their waits are not cut by the
  deadline; `task.Deadline()` still reads it). Every other cancel (a child's fault, a handle's
  `cancel`, a scope left early, a budget) happens as the program runs and must match the next
  record; a cancel with no record, or a record with no cancel, is a divergence.

## 8. Replay mode (#242)

`tin replay CAPSULE [--against BUILD] [--live KIND]...` runs BUILD (a binary, or a program
compiled from FILE.tin) with `TIN_REPLAY_CAPSULE` and `TIN_REPLAY_KEY` set. anvil's `Serve`
then, instead of listening, decodes the capsule (`lib/replay`), runs its request once through
the program's handler or router on a task whose tape replays (`tpMode = 2`), and prints:

```
replay: status S (recorded R)
replay: divergence at effect N: ...        (only if diverged)
replay: K recorded effects not served      (only if some are left)
```

then the response body. Exit status: 0 when nothing diverged, 3 when it diverged, 4 when the
capsule cannot be read (wrong key, damaged, an unsupported schema or kind). `--save-test NAME`
is #242's.

## 9. Who implements what

| part | issue |
|---|---|
| `tTape`, `lib/runtime/replay.tin` (sections 2, 3, `rt_secret_key`), the copy at spawn, the panic message into `tpPanic` | #241 |
| `lib/replay`: switches, keys, `rtSecretHash`, capsule body and envelope, spool and bound | #241 |
| anvil: tape per request, `tpStatus`, capture at the end of a request | #241 |
| recording in `tide`, `dice`, `seal`, `wire`, `redis`, `mysql`, `postgres`, `websocket`, `quarry` (section 4) | #241, one slice per group |
| `query.Hidden` and secret query arguments (5.3) | #241, with #239's approval |
| capsule reader, replay mode in anvil, `tin replay`, the report, `--live`, `--save-test` and its CI | #242 |
| `sched.*` recording and replay | #243, hooks next to #232's `select`, scope and cancel code |

## 10. Cost when off

Per request: anvil tests one shared flag. Per effect call: `rt_tape()` (one load of the running
task, one of its word) and a branch. No allocation, no encoding. Measured on the Linux HTTP
benchmark before the recording PR merges (AGENTS.md).
