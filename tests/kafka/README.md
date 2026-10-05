# Kafka against real brokers

`integration.tin` runs the `kafka` client against a broker at `KAFKA_ADDR` (default `127.0.0.1:9092`):
admin, producing with every codec and acks setting, fetching, transactions, simple commits, and a
consumer group with one member on each of two cores. It prints one `ok` or `FAIL` line per check, then
`PASS`, or `FAILED n` and exit status 1. Its topics are named `tin-it-<ms>-*` and left behind. It is not
part of CI (CI has no broker); `tests/v2/kafka_broker.tin` is the CI check, against a fake cluster.

| Environment | Meaning |
|---|---|
| `KAFKA_ADDR` | `host:port` of a bootstrap broker; the broker's advertised address must be reachable from the test too |
| `KAFKA_USER`, `KAFKA_PASSWORD` | SASL |
| `KAFKA_MECHANISM` | `PLAIN` (default), `SCRAM-SHA-256` or `SCRAM-SHA-512` |
| `KAFKA_TLS=1` | TLS 1.3; `KAFKA_TLS_INSECURE=1` skips the certificate check (the `tls` package cannot verify yet) |

The group check needs `group.initial.rebalance.delay.ms=0` on the broker (the default, 3 s, only makes
it slower) and transactions need the transaction log's replication factor to fit the cluster.

## One broker with Docker

```sh
docker network create tin-kafka-net
docker run -d --name tin-kafka-test --network tin-kafka-net \
  -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://tin-kafka-test:9092 \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@tin-kafka-test:9093 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 \
  apache/kafka:3.9.0
```

For Kafka 4.x the same works with `confluentinc/cp-kafka:8.2.0` and `-e CLUSTER_ID=<22 base64
characters>`.

The broker advertises its container name, so run the test on the same network: build it for Linux with
`tin build --target linux-amd64 tests/kafka/integration.tin -o bin/kafka-it` (or `linux-arm64`) and run
it in any Linux container that mounts the binary, with `--network tin-kafka-net` and
`-e KAFKA_ADDR=tin-kafka-test:9092`. On a Linux host with the broker advertising `localhost:9092`, run
`tin tests/kafka/integration.tin` directly.

## SASL

Advertise `SASL_PLAINTEXT://...` (with `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP`, and
`KAFKA_INTER_BROKER_LISTENER_NAME=SASL_PLAINTEXT`), set
`KAFKA_SASL_ENABLED_MECHANISMS=PLAIN,SCRAM-SHA-256,SCRAM-SHA-512`,
`KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL=PLAIN`, and `KAFKA_OPTS=-Djava.security.auth.login.config=...`
pointing at a JAAS file whose `KafkaServer` section lists `PlainLoginModule` (with `username`,
`password` and a `user_<name>="<password>"` line per client) and `ScramLoginModule required;`. SCRAM
users are added after the broker starts, one mechanism per command:

```sh
kafka-configs.sh --bootstrap-server HOST:9092 --command-config admin.properties --alter \
  --add-config 'SCRAM-SHA-256=[iterations=8192,password=PW]' --entity-type users --entity-name tin
```

## TLS

Give the broker an `SSL://` listener with `KAFKA_SSL_KEYSTORE_FILENAME`, `KAFKA_SSL_KEYSTORE_CREDENTIALS`,
`KAFKA_SSL_KEY_CREDENTIALS` (files in `/etc/kafka/secrets`) and, because the broker talks to itself over
it, a truststore set with `KAFKA_SSL_TRUSTSTORE_LOCATION` and `KAFKA_SSL_TRUSTSTORE_PASSWORD` (the image
reads `KAFKA_SSL_TRUSTSTORE_FILENAME` only with client authentication on). Then run the test with
`KAFKA_TLS=1 KAFKA_TLS_INSECURE=1`.

## Java interop

With the broker's own tools (`/opt/kafka/bin` in the image):

- Partitioning: produce keyed records with `kafka-console-producer.sh --property parse.key=true` to a
  topic with several partitions, read each partition with `kafka-console-consumer.sh --partition N`, and
  compare with `kafka.PartitionFor(key, n)`.
- Codecs: `kafka-console-producer.sh --compression-codec gzip|snappy|lz4|zstd` writes batches for the
  client to `Fetch`; records the client sends with `Options.Compression` are read by
  `kafka-console-consumer.sh --property print.key=true --property print.headers=true`.
  `kafka-dump-log.sh --files <segment>` shows each batch's codec, record count, producer id and
  sequences.
- Groups: a `kafka-console-consumer.sh --group G` and a client `Group` with the same name share the
  partitions (`kafka-consumer-groups.sh --describe --group G --members --verbose`), whichever joins
  first and leads.
