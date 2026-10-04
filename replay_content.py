# Content of the Replay page, imported by gen.py.
R = []

R.append(dict(id="idea", n="01", title="The idea",
intro="A request that failed in production runs again on your laptop, against any build, with every external effect served from a recording and none performed.",
cards=[
dict(id="promise", title="The promise", sig="record once · replay anywhere",
text="While serving, a Tin server writes a **capsule** for every request that ends in a 5xx or a panic: the request bytes plus the ordered log of everything the handler asked the outside world. `tin replay` runs that request again from the capsule.",
lang="sh",
code='''
# production: record failures into a spool (encrypted with the key)
TIN_REPLAY_DIR=/var/spool/tin TIN_REPLAY_KEY=$(openssl rand -hex 32) ./app

# your laptop: the same request, same answers from Redis, the clock, the payment API
TIN_REPLAY_KEY=... tin replay 00001700000000000000-003-41.tcap --against app.tin
''',
rules=["No Redis, no database, no upstream, no network: every effect is answered from the capsule.",
       "The build you replay against can be newer than the one that recorded: that is the point."],
deeper=[("p","Why the language can promise completeness: user code cannot reach the operating system except through the standard library. Clocks, randomness, sockets, files and databases all pass through one runtime hook, `rt_effect(kind, key, body)`, which records when recording and answers when replaying. There is no `external` keyword to forget."),
        ("rules",["A package that declares the `unsafe` capability is marked not replay-safe.",
                  "Recording off costs one per-core load and a branch per effect call; on, about 110 ns per effect and one copy of the request bytes."])]),
dict(id="solves", title="What it solves", sig="production → laptop",
text="The bugs that are expensive today are the ones you cannot reproduce. A capsule is the reproduction.",
extra=[("table",(["without replay","with a capsule"],[
 ["\"Cannot reproduce\": the 500 depended on a cache state that is gone","the exact Redis reply, as it was at that moment, is in the capsule"],
 ["A timing bug: `select` won the other arm under load","the winning arm and task order are recorded and replayed under any timing"],
 ["A downstream returned something odd once","its response bytes are kept; replay never calls it again"],
 ["Logs with secrets redacted, or secrets leaked","secret headers and query values are stored as keyed hashes that still match on replay"],
 ["A fix \"looks right\"","`tin replay --against fixed.tin` shows the new status next to the recorded one"],
 ["Regression tests written by hand after the fact","`--save-test` turns the capsule into a CI case in one command"],
 ["Sampling real traffic for tests means copying databases","`TIN_REPLAY_SAMPLE` keeps a fraction of successful requests as self-contained capsules"]]))]),
]))

R.append(dict(id="recording", n="02", title="Recording",
intro="Two environment variables turn it on. Nothing in the program changes.",
cards=[
dict(id="switches", title="Switches", sig="read once, before the cores start",
text="Recording is on when both the spool directory and the key are set. A malformed key prints one line and leaves recording off.",
extra=[("table",(["variable","meaning"],[
 ["`TIN_REPLAY_DIR`","spool directory; unset: recording off"],
 ["`TIN_REPLAY_KEY`","64 hex digits; encrypts and authenticates capsules; never written anywhere"],
 ["`TIN_REPLAY_SAMPLE`","fraction (0 to 1) of successful requests kept too; default 0"],
 ["`TIN_REPLAY_MAX_MB`","spool bound, default 256; the oldest capsules go first"],
 ["`TIN_REPLAY_SECRET_HEADERS`","headers stored as keyed hashes, on top of `Authorization`, `Proxy-Authorization`, `Cookie`"],
 ["`TIN_REPLAY_DROP_HEADERS`","headers stored empty (a PII policy)"]]))],
lang="sh",
code='''
# Kubernetes: a secret for the key, an emptyDir for the spool
env:
  - name: TIN_REPLAY_DIR
    value: /spool
  - name: TIN_REPLAY_KEY
    valueFrom: { secretKeyRef: { name: tin-replay, key: key } }
  - name: TIN_REPLAY_SAMPLE
    value: "0.001"
''',
rules=["Requests ending in a 5xx or a panic are always kept; the sample adds a slice of the rest."]),
dict(id="effects", title="What is recorded", sig="kind@version · key · outcome",
text="An **effect** is anything whose result does not follow from the program and its input. Each one is a record: its kind, what was asked, and what came back, in the order they completed on the core.",
extra=[("table",(["effect","kind","recorded at"],[
 ["clock","`tide.now@1`, `tide.wall@1`","`tide.Now`, `Since`, `Wall`"],
 ["randomness","`dice.seed@1`, `seal.random@1`","a request's first draw; `seal.RandomBytes`"],
 ["HTTP client","`wire.http@1`","`wire.Get`, `Post`, `Do`: method, URL, headers, body → status, head, body"],
 ["raw TCP","`wire.dial@1`, `read@1`, `write@1`","`Dial`, `Conn.Read`, `Conn.Write`"],
 ["Redis","`redis@1`","every command and its raw RESP reply"],
 ["MySQL, PostgreSQL","`mysql@1`, `postgres@1`, `*.tx@1`","`Query`, `Exec`, `Begin`, `Commit`, `Rollback`"],
 ["WebSocket","`websocket.dial@1`, `read@1`, `write@1`","client and accepted connections"],
 ["files","`quarry.read@1`, `write@1`, `stat@1`, `dir@1`, `fs@1`","`ReadFile`, `WriteFile`, `Exists`, `ReadDir`, `Remove`…"],
 ["scheduling","`sched.select@1`, `resume@1`, `cancel@1`","which `select` arm won, task resume order, cancels"]]))],
rules=["The request itself: method, path, headers, body as received (secrets as handles).",
       "DNS is inside `wire.http` and `wire.dial`: replay performs neither."],
deeper=[("p","A client records once even when it calls itself: the live call runs with the tape suspended. A recorded fault keeps its identity, so `fault.Is(err, fault.DeadlineExceeded)` is still true on replay."),
        ("sh",'''
// what one record holds (the tape and the capsule share the layout)
word   seq        0, 1, 2 ... completion order on the core
string kind       "redis@1"
string key        "3:GET 6:cart:7\\n"           secrets as handles
word   outcome    0 result, 1 fault
word   ident      the runtime sentinel in a fault's chain, or 0
string data       the encoded result, or the fault's message
'''),
        ("rules",["A kind's version changes when its key or result layout changes; a replayer refuses a kind it does not know, naming it.",
                  "Scope children (`spawn`, `parallel`) share their request's tape. `detach`, ticks, relay and `on` handlers have none: they are not part of a request."])]),
dict(id="capsules", title="Capsules", sig="WALL-CORE-N.tcap",
text="When a request task ends, its tape becomes a capsule: written on the core, after the task, via a `.tmp` file and a rename, so a reader never sees a partial file.",
lang="sh",
code='''
spool/
  00001700000000000000-000-17.tcap     # wall clock, core, sequence
  00001700000000000000-003-41.tcap
''',
rules=["The body (request, status, panic message, effects) is encrypted with an HMAC-SHA256 keystream and authenticated by a tag: a wrong key or a changed byte is refused.",
       "The spool is bounded; the oldest capsules are deleted first, at start and per core.", "Shipping capsules anywhere is operations, not the runtime."]),
dict(id="secrets", title="Secrets never reach a capsule", sig="tin-secret:…",
text="A secret header, a `secret` value in a client call, or a secret written into a query is stored as a keyed handle, never its text. Logins happen inside the live call and are not recorded.",
code='''
// stored in the capsule
Authorization: tin-secret:3f9c0a7e2d1b4c5a6e8f9d0c1b2a3f4e

// a secret in a query: sent to Redis as itself, stored as its handle
fn session(token secret str) ! {
	try cache.Do("GET session:{token}")
}
''',
rules=["A handle is `tin-secret:` plus 16 bytes of HMAC-SHA256 under a key derived from `TIN_REPLAY_KEY`.",
       "On replay the handler reads the handle as the header's value; it hashes to itself, so recorded keys still match."],
deeper=[("p","The language side makes this total: `secret T` values are rejected by every sink at compile time (logging, JSON, fault messages, plain parameters), so the only way a secret reaches an effect is through a library parameter declared `secret`, and that library writes the handle. Query literals carry a `Hidden` bit per argument that the compiler sets."),
        ("rules",["Results are stored as received, encrypted at rest.", "`TIN_REPLAY_DROP_HEADERS` empties headers that must not be stored at all."])]),
]))

R.append(dict(id="replaying", n="03", title="Replaying",
intro="One command, a report on standard output, the response body after it, and an exit status CI can read.",
cards=[
dict(id="tin-replay", title="tin replay", sig="tin replay CAPSULE --against BUILD",
text="`BUILD` is a binary or a `.tin` file that `tin` builds first. Its `Serve` does not listen: it opens the capsule, checks the tag, and sends the recorded request once through the handler or router on one core.",
lang="sh",
code='''
TIN_REPLAY_KEY=$KEY tin replay spool/00001700000000000000-003-41.tcap --against app.tin

replay: status 500 (recorded 500)
charge failed: payments answered 503
''',
rules=["Run it with the same configuration the server recorded under: effect keys hold what the program sent, so another upstream URL is a divergence.",
       "Every effect gets its recorded result or fault; none is performed."],
extra=[("table",(["exit","meaning"],[["0","nothing diverged and every recorded effect was used"],["3","the replay diverged or left effects unserved"],["4","the capsule cannot be read: wrong key, damaged, unknown schema or kind, missing key"],["2","usage error"]]))],
deeper=[("p","`--live KIND` (repeatable, without `@version`) makes one kind's calls for real: useful to re-run the charge against a sandbox while Redis still answers from the tape. The live result is still compared with the recording, which it consumes."),
        ("sh",'''
tin replay cap.tcap --against app.tin --live wire.http
'''),
        ("rules",["The build runs with `TIN_REPLAY_CAPSULE` set, which is how `anvil.Serve` knows to replay instead of listen.",
                  "A handler that waits or panics replays like any other: the panic message and the 500 are part of the report."])]),
dict(id="divergence", title="Divergence", sig="never a live call by accident",
text="Replay stops at the first effect whose kind or key differs from the next recorded one, or that comes after the last. From then on every effect of the request fails with the divergence.",
lang="sh",
code='''
replay: status 500 (recorded 500)
replay: divergence at effect 0: got wire.http@1 "POST https://pay.example/charge ...", recorded redis@1 "3:GET 6:cart:7"
replay: 2 recorded effects not served
''',
rules=["A different call, a different order, or an extra call all diverge. Replay never falls through to the network.",
       "Divergence is information: the new build asks the world a different question than the old one did."]),
dict(id="scheduling", title="Scheduling replays too", sig="select · resume order · cancels",
text="Tasks on a core switch only at waits, so with the events recorded a request's concurrency replays exactly. The winning `select` arm, the order tasks resumed in, and each cancel with its reason are on the tape.",
code='''
select {
	let r = fast.wait() => use(r)       // recorded: this arm won
	after(50ms) => fail "slow"          // replayed: this arm loses, whatever the clock says
}
''',
rules=["A recorded 5 ms deadline replays under a 10 s one and the other way round: deadlines come from the tape, not the clock.",
       "Children whose effects complete in another order than issued get their results in the recorded order.", "A replay in which no task can take the next record diverges instead of hanging."]),
dict(id="save-test", title="From capsule to regression test", sig="--save-test NAME --issue N",
text="When a replay against the fixed build exits 0, one flag turns the capsule into a case CI replays on every change.",
lang="sh",
code='''
tin replay cap.tcap --against fixed.tin --save-test checkout-total --issue 242

tests/regressions/checkout-total.tin     # a copy of fixed.tin
tests/regressions/checkout-total.tcap    # the capsule, sealed again under a public test key
tests/regressions/cases.json             # + an entry with the expected report and body
''',
rules=["The runner sets the replay switches, runs the program and checks the exit status and output.",
       "The case names its capsule and the public key it is sealed under; the production key never leaves production."],
deeper=[("sh",'''
{
  "source": "replay-checkout-total.tin",
  "issue": 242,
  "replay": { "capsule": "replay-checkout-total.tcap", "key": "6663…8989" },
  "expected": { "phase": "run", "exit": 0,
                "stdout": "replay: status 200 (recorded 500)\\ntotal 3800\\n" }
}
'''),
        ("p","Note the expected line: status 200 where 500 was recorded. The test asserts the fix, against the exact production input, forever.")]),
]))

R.append(dict(id="example", n="04", title="A worked example",
intro="The checkout service in `examples/checkout.tin`: a cart in Redis, a charge at a payment service, and a 500 to replay with neither running.",
cards=[
dict(id="checkout", title="Record a failure, replay it offline", sig="examples/checkout.tin",
text="POST `/checkout/{id}` reads the cart from Redis and charges it. The payment service declines, the request answers 500, and anvil keeps the capsule.",
code='''
fn checkout(q anvil.Req, w mut anvil.Out) {
	let id = q.PathParam("id")
	let (items, found) = cache.Get("cart:" + id) catch err {
		w.Status(502)
		w.Text("cart: {fault.Message(err)}\\n")
		return
	}
	if !found {
		w.Status(404)
		w.Text("no cart {id}\\n")
		return
	}
	let r = wire.Post(quarry.Getenv("PAYMENTS_URL") + "/charge", "text/plain", "cart=" + items) catch err {
		w.Status(500)
		w.Text("charge failed: {fault.Message(err)}\\n")
		return
	}
	if r.Status != 200 {
		w.Status(500)
		w.Text("charge failed: payments answered {r.Status}\\n")
		return
	}
	w.Text("paid {r.Body} for {items}\\n")
}
''',
deeper=[("sh",'''
# 1. record, against a real Redis and a declining payment service
REDIS_ADDR=127.0.0.1:6379 PAYMENTS_URL=http://127.0.0.1:9999 \\
TIN_REPLAY_DIR=spool TIN_REPLAY_KEY=$KEY tin examples/checkout.tin
curl -X POST localhost:9186/checkout/7          # -> 500 charge failed: payments answered 503

# 2. stop Redis and the payment service. Replay:
TIN_REPLAY_KEY=$KEY PAYMENTS_URL=http://127.0.0.1:9999 \\
tin replay spool/*.tcap --against examples/checkout.tin
# replay: status 500 (recorded 500)
# charge failed: payments answered 503

# 3. fix the handler, replay against the fix, keep it as a test
tin replay spool/*.tcap --against examples/checkout.tin --save-test checkout-total --issue 242
'''),
        ("rules",["Another `PAYMENTS_URL` is a divergence (exit 3): the key holds the URL the program sent.",
                  "The Redis password was used by the live login and is not on the tape."])]),
dict(id="limits", title="What replay does not do", sig="honest limits",
text="Replay reproduces a request, not a process.",
rules=["Background work is outside it: `detach` tasks, ticks, relay handlers and `on` handlers have no tape.",
       "A later build must ask for the same effects in the same order; a refactor that reorders calls diverges, by design.",
       "A capsule replays on later Tin versions while its effect schemas are supported; an unsupported kind is a clear error, not a wrong replay.",
       "Capsules are stored locally and bounded; shipping, retention and access are yours to operate.",
       "Packages with the `unsafe` capability can reach the OS behind the hook and are marked not replay-safe."]),
]))
