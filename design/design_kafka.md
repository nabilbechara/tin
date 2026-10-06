# Design: a complete Kafka client (`lib/kafka`) and the codecs it needs (`lib/squash`)

Status: decided for the first complete version. The roadmap box is "Queue and stream clients"
(design/roadmap.md).

## 1. Scope

Everything a service needs from Kafka, as Go's franz-go and sarama provide it:

| Area | Requests |
|---|---|
| Connections | ApiVersions (checked on every connection), SASL PLAIN, SCRAM-SHA-256, SCRAM-SHA-512, TLS 1.3 |
| Cluster | Metadata, FindCoordinator |
| Producer | Produce (acks 0, 1, all), InitProducerId (idempotent and transactional), compression gzip, snappy, lz4, zstd |
| Transactions | AddPartitionsToTxn, AddOffsetsToTxn, TxnOffsetCommit, EndTxn |
| Consumer | Fetch (many partitions at once, read_uncommitted and read_committed with aborted transactions removed, every codec), ListOffsets (earliest, latest, by time) |
| Groups | JoinGroup, SyncGroup, Heartbeat, LeaveGroup, OffsetCommit, OffsetFetch; range and round-robin assignors; static membership |
| Admin | CreateTopics, DeleteTopics, CreatePartitions, DeleteRecords, DescribeConfigs, IncrementalAlterConfigs, ListGroups, DescribeGroups, DeleteGroups |

Out of scope, by decision: the KIP-848 consumer protocol (ConsumerGroupHeartbeat; brokers keep the
classic protocol), share groups (KIP-932), the cooperative-sticky assignor (eager rebalancing only),
delegation tokens, OAUTHBEARER (it needs a token provider per service; PLAIN and SCRAM cover managed
Kafka offerings that use passwords), and ZooKeeper-era APIs.

## 2. Request versions

One version per request, without tagged fields (the last non-flexible version), so the encoder stays one
code path. They are the versions brokers from 2.4 to 4.x accept (run against 3.9 and 4.2); Kafka 4.0 removed only older versions
(KIP-896). On every connection the client sends ApiVersions first; a request whose version the broker
does not list fails with a message naming the request, the version and the broker's range, instead of the
broker closing the connection.

| Request | Version | Request | Version |
|---|---|---|---|
| Produce | 7 | Fetch | 10 |
| ListOffsets | 4 | Metadata | 7 |
| OffsetCommit | 7 | OffsetFetch | 5 |
| FindCoordinator | 2 | JoinGroup | 5 |
| Heartbeat | 3 | LeaveGroup | 3 |
| SyncGroup | 3 | DescribeGroups | 4 |
| ListGroups | 2 | SaslHandshake | 1 |
| ApiVersions | 2 | CreateTopics | 4 |
| DeleteTopics | 3 | DeleteRecords | 1 |
| InitProducerId | 1 | AddPartitionsToTxn | 1 |
| AddOffsetsToTxn | 1 | EndTxn | 1 |
| TxnOffsetCommit | 2 | DescribeConfigs | 2 |
| IncrementalAlterConfigs | 0 | SaslAuthenticate | 1 |
| CreatePartitions | 1 | DeleteGroups | 1 |

Produce 7 and Fetch 10 are the first versions that carry zstd (KIP-110). Brokers before 2.4 are not
supported.

## 3. Where a consumer runs

Tin has no threads to give a consumer, and heartbeats must go out while the application works. The
classic protocol allows a member to heartbeat from its poll loop as long as each poll comes within the
session timeout; the Java client did exactly that before 0.10.1. So:

- `Group.Poll(maxWait)` sends a due heartbeat, rejoins when the coordinator asked for a rebalance,
  commits the previous poll's offsets when auto-commit is on, and fetches. It never waits longer than the
  time to the next heartbeat, so a poll loop with short handlers keeps the membership without anything
  running in the background.
- A handler that may run longer than the session timeout calls `g.Heartbeat()` itself, or the service sets
  `GroupOptions.Session` above its slowest handler.
- A long-running consumer in an anvil service lives in `detach { ... }` started from `on core.start`:
  every core can be a member of the group (members are per core, since nothing is shared between cores),
  and the drain cancels it, which makes it leave the group.
- In a plain program the poll loop runs in `main`; calls block the core, which is the only thing it does.

A member is a value owned by one core: `Group` holds per-core state the same way the connections do.

## 4. Producer

- Records with a key go to murmur2(key) mod partitions (the Java default); the records without a key
  of one call go to one partition, the next call's to the next, so unkeyed records still batch (a
  per-call form of KIP-480's sticky partitioner).
- `Send` waits for the broker's acknowledgement. Sends of one core's tasks to the same partition in the same
  turn of the event loop go out as one record batch: the first sender defers to the core's other ready
  tasks before it encodes, like the redis client's pipelining. One Produce request carries every partition
  that one broker leads.
- Idempotence (`Options.Idempotent`, on by default with acks all as in Kafka 3.0+): the client gets a
  producer id and epoch per core from InitProducerId and numbers each partition's batches, so a retried
  batch is never written twice. OUT_OF_ORDER_SEQUENCE and UNKNOWN_PRODUCER_ID reset the epoch.
- Compression is per client (`Options.Compression`): none, gzip, snappy (xerial framing as Kafka's Java
  client writes it, plain blocks read too), lz4 (frame format), zstd.

## 5. Transactions

A transactional producer is a value (`c.Transactional(id)`) whose transactional id is the caller's choice;
per core, because a producer id cannot be shared between threads that never synchronize. A service with
several cores gives each core its own id (for example `"{name}-{core}"`). `Begin`, `Send`,
`SendOffsets` (consume-transform-produce), `Commit` and `Abort` map one to one onto the protocol.

## 6. Codecs: `lib/squash`

Kafka needs four codecs and the standard library had none. `squash` is a standard package (Go's
`compress/flate`, `compress/gzip`, `compress/zlib`, plus snappy, LZ4 and Zstandard), so other code can use
them too. DEFLATE, gzip and zlib are verified against a Go twin; snappy, LZ4 and Zstandard have no Go
standard package, so they are verified against their specifications' examples, round trips, and against
what Kafka's Java client writes and reads.

## 7. Connections

One connection per broker per client and core carries ordinary requests. A broker answers one request
of a connection at a time, so the requests it may hold (Fetch with a wait, JoinGroup, SyncGroup) go on
a second connection to the same broker; otherwise a long poll or a rebalance would hold up every send of
the core.

## 8. Replay

Every request the client sends is one `kafka@1` effect: its key is the request kind, version and body
(not the correlation id), its result the response body. A replayed request returns the recorded response
without a connection. The connection's handshake is not an effect. A request's effects must not depend
on what the core did before it, so while a tape is active the client asks for metadata on every use
instead of its cache, and sends without batching across requests and without a producer id. Group
members and transactional producers keep per-core state between requests and are not made
deterministic; they belong in `detach` tasks and `on` handlers, which have no tape.

## 9. Tests

- `tests/v2/squash.tin` (+ Go twin `bench/ref/squash`) for the codecs.
- `tests/v2/kafka.tin` needs nothing: protocol encoding, record batches with every codec, the partitioner.
- `tests/v2/kafka_broker.tin` runs a fake cluster in the same process: four brokers on cores 1–4
  (cores do not share memory: they answer from a fixed layout), the client on core 0. It covers
  metadata, a moved leader, a lost acknowledgement with an idempotent retry, an unsupported request
  version, every codec, transactions read both ways, a group with a rebalance, admin requests and a
  wrong password. This is the CI check the roadmap asks for, without Python (`tools/ci` takes no new
  Python files) and without a Kafka install.
- `tests/kafka/integration.tin` against real brokers (Apache Kafka 3.9 and Confluent 8.2, which is Kafka
  4.2), and Java interop in both directions for every codec, by hand (tests/kafka/README.md).
