# kafka

`lib/kafka/` is a Kafka client: producer, fetching, consumer groups, transactions and administration.
The design and its decisions are in `notes/design_kafka.md`; the API in `docs/STDLIB.md`. It is written
like `lib/redis`: per-core connections shared by the core's request tasks, waits that park the task.

## Files

| File | Holds |
|---|---|
| `kafka.tin` | `Options`, `Client`, `Open`, the sentinels and error names, the per-core cluster view (metadata, leaders, controller), retries |
| `conn.tin` | connections: frames, the slot queue, the handshake (ApiVersions, SASL, KIP-368 session renewal), TLS, reconnects, timeouts, lanes for requests a broker holds, reuse of idle connections, `call`, `Close`, replay (`kafka@1`) |
| `scram.tin` | SCRAM-SHA-256 and SCRAM-SHA-512 |
| `proto.tin` | request versions, the wire format, record batches (codecs, producer ids, transactional and control batches, aborted-transaction filtering), murmur2 |
| `produce.tin` | per-partition accumulators: batching, one batch in flight per partition, idempotent sequences, `Send`, `SendTo`, `SendBatch`, `SendBatchTo` |
| `fetch.tin` | `Fetch`, `FetchAll` (one request per leader), `Offsets`, `OffsetAt` |
| `group.tin` | `Group`: JoinGroup, SyncGroup, Heartbeat, LeaveGroup, range and round-robin assignors, `Poll`, commits; `Commit` and `Committed` without membership |
| `txn.tin` | `Transactional`: `Begin`, `Send`, `SendBatch`, `SendOffsets`, `Commit`, `Abort` |
| `admin.tin` | topics, partitions, records, groups, configs |
| `syscalls_darwin.tin` | the libSystem calls the connection layer needs on macOS |

## Design notes beyond notes/design_kafka.md

- A broker answers one request of a connection at a time, so a request it may hold (Fetch with a wait,
  JoinGroup, SyncGroup) goes on a second connection to the broker: produce, commit and heartbeat
  traffic never waits behind a long poll or a rebalance. Found by the anvil example: a member's
  JoinGroup held by a rebalance stalled every send of its core. A group's JoinGroup and SyncGroup go
  on a connection of the group's own (#445), so one group's rebalance holds up neither the fetches
  nor another group of the core, whose member would otherwise miss its session timeout and set off
  a cascade of rebalances.
- Requests wait at most `Options.Timeout` (30 s by default, Java's `request.timeout.ms`; negative for
  no limit) plus what the broker may hold them for (#445). At the timeout the broker is taken to be
  gone: the connection is dropped, every request on it fails with `ErrNetwork` (retried as any
  dropped connection), and the next request connects again. Before, a request without a timeout
  could wait forever on a broker that vanished without a reset, and with one, the requests behind
  the unanswered one queued on the same connection. A caller's own deadline or cancellation leaves
  its request on the connection for the others (its answer is read and dropped), also during a
  handshake other callers queued behind.
- `Close` from another task while a request is in flight (a held fetch) shuts the socket down
  instead of closing it: the task doing the connection's I/O wakes, fails the line's requests with
  `ErrClosed` (not retried) and closes the descriptor itself. A descriptor closed under a task's
  wait would leave the task asleep, and its number could be reused for another connection while
  the task's timer still referred to it.
- TLS reads go straight into the connection's frame buffer (`tls.Conn.ReadNowTo`): a 16 MiB fetch
  used to allocate a fresh copy of the frame's remainder for each 16 KiB record, about 8 GiB of
  request memory.
- A client keeps at most 64 connections per core; when they are all taken, the one no task has used
  for longest is closed and reused (a broker gone from the cluster, a group's lane), so brokers whose
  addresses change no longer use the slots up. Up to 65536 clients may be opened in a process (128
  before), a bound against opening one per request.
- A SASL session the broker limits (KIP-368, `connections.max.reauth.ms`: `session_lifetime_ms` in
  SaslAuthenticate) is renewed at 85% of its lifetime: an idle connection is closed and made again
  (authenticating anew), and one with requests in flight is retired: they finish there while new
  requests go on a new connection, which closes the retired one once it is drained. The broker
  closes a connection that sends a request after its session ended.
- A new connection is opened before the first request is queued on it, so the broker's versions are
  known and an unsupported request fails with a message naming it and both version ranges.
- Records without a key go to one partition per call, the next call to the next partition.
- A topic missing from the metadata (created a moment ago) is asked about again for about two
  seconds, as the Java producer waits for metadata.
- Metadata is refreshed on retriable errors (moved leader, election, unknown topic, timeouts, dropped
  connections, not enough replicas): up to five attempts, 50 ms doubling to a second. Coordinator
  errors retry up to ten times.
- A lost producer state (OUT_OF_ORDER_SEQUENCE_NUMBER, UNKNOWN_PRODUCER_ID, a fenced epoch) makes the
  core ask for a new producer id; that batch may then be written twice, as with the Java client's
  epoch bump. A DUPLICATE_SEQUENCE_NUMBER answer is success without an offset (`Ack.Offset` -1).
- `Poll` commits what the previous `Poll` returned (unless `ManualCommit`), heartbeats when due, rejoins
  after a rebalance, and never waits past the next heartbeat. A member rebalanced away while
  processing commits with an old generation and gets `ErrRebalance`; its records may be delivered
  again to the new owner (at least once, as with the Java consumer).
- While a request is recorded or replayed, the client asks for metadata on every use and sends
  without batching across requests and without a producer id (`notes/interface_replay.md`, kafka@1).

## Verified

- `tests/v2/kafka.tin` (35 lines, no broker): murmur2 against the six vectors of Kafka's `UtilsTest`
  and the empty key, record batches with every codec, cut batches, a changed byte.
- `tests/v2/kafka_conn.tin` and `tools/ci/kafka_check.py` (#445, fake brokers): a request the broker
  never answers ends at the timeout and the next connects again; 70 dead brokers before a live one;
  200 more clients; a 6 MiB fetch over TLS inside `limit memory 64mb`; one-second SASL sessions
  renewed for 5 s by sequential and concurrent requests with no connection ended by the broker. In an
  event loop (anvil, one core, the fake broker as tasks): Close from another task ends a held fetch
  with ErrClosed at once; a fetch beside another group's held JoinGroup takes milliseconds; a
  caller's deadline in a handshake is its own DeadlineExceeded, and a caller queued behind it fails
  on its own timeout. Against the client before #445 these fail (three time out, the 200 clients
  crash).
- `tests/v2/kafka_broker.tin` (26 checks, no Kafka needed, so it runs in CI): a fake four-broker
  cluster on cores 1 to 4 written from the protocol's schemas. A moved leader (the send lands once), an
  acknowledgement lost after the write (the idempotent retry is answered DUPLICATE_SEQUENCE_NUMBER and
  the partition holds each record once), a broker without Produce v7 (named in the fault), every
  codec through the broker, two leaders in one FetchAll, offsets, out-of-range offsets, topic
  creation, an aborted and a committed transaction read with read_uncommitted and read_committed, a
  member made to rejoin with the coordinator's member id, a rebalance (generation 2), commits, leaving,
  a wrong password. Identical in 10 runs. Making a retried batch take a new sequence fails 5 checks.
- `tests/kafka/integration.tin` (59 checks) against Apache Kafka 3.9.0 and Confluent Platform 8.2.0
  (Kafka 4.2), single-node KRaft, on linux-amd64: admin (topics with configs, ListTopics, broker and
  topic configs set and reset, CreatePartitions, DeleteRecords, DeleteTopics), keyed partitioning,
  every codec at 200 records per batch, Linger, a BatchMax that splits one call into several batches,
  acks all, leader and none, FetchAll, OffsetAt, too-large
  records, 500 ordered sends, simple commits, transactions (abort, commit, read_committed, offsets in a
  transaction, fencing), and a group of two members on two cores that splits four partitions and reads
  400 records with no duplicates (3 runs on each broker). The same suite passes over SASL PLAIN,
  SCRAM-SHA-256 and SCRAM-SHA-512 (a wrong password is `ErrAuth`) and over TLS 1.3 with the certificate
  check off.
- Java interop with Kafka 3.9's own tools: six keys land on the same partitions from the Java producer
  and from `PartitionFor` (7 partitions); single 300-record batches the Java producer wrote with gzip,
  snappy, lz4 and zstd decode in Tin, and the Java consumer reads Tin's (keys, headers; the broker log
  shows them compressed, with a producer id and sequences 0 to 299); a Java console consumer and a Tin
  member share a group with Tin as leader and with Java as leader, and Java's `kafka-consumer-groups`
  shows the range split (two partitions each).
- `examples/kafka.tin` under anvil on two cores: 400 concurrent sends all acknowledged, and the two
  per-core group members consume the 400 records; the connection survives a broker restart.
- Replay: a request that sends and fetches, recorded by anvil (`TIN_REPLAY_SAMPLE=1`), replays through
  `tin replay` with the broker address unreachable: same status and body, exit 0.

Not run: a multi-broker cluster (leader moves and coordinator moves are covered only by the fake
cluster), brokers 2.4 to 3.8, managed services (Confluent Cloud, MSK), linux-arm64 and macOS (the code
cross-compiles for both), certificate verification (the `tls` package cannot verify yet, #124 phase 2).
No throughput was measured.

## Known gaps

- The KIP-848 consumer protocol, share groups (KIP-932) and the cooperative-sticky assignor: groups
  use the classic protocol with eager rebalancing (range and round-robin).
- OAUTHBEARER and delegation tokens.
- Fetch sessions (KIP-227) and leader epochs (KIP-320, KIP-392): every fetch is a full one and epochs
  are not checked; there is no fetching from followers.
- Metadata is refreshed on errors only, not on a timer.
- `squash`'s zstd encoder compresses less than the reference one (`notes/stdlib_squash.md`).
