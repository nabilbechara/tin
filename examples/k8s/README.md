# examples/k8s: the anvil API server in a container and on Kubernetes

`examples/api.tin` is an HTTP/1.1 server built on `anvil` (one event loop per core). This
directory builds and packages it: a `Dockerfile`, a `Deployment` + `Service`, and the commands
below. Everything was verified on an arm64 Docker host (Apple silicon).

## Build

```sh
docker build -f examples/k8s/Dockerfile -t tin-api:dev .  # context = repository root
```

The first stage uses the published `ghcr.io/yasserreslan/tin:0.4.0` compiler image to
compile the source. Docker selects arm64 or amd64 for the build. Use
`docker buildx build --platform linux/amd64` to select a different destination, or
`--platform linux/amd64,linux/arm64 --push -t YOUR_IMAGE` for both. The compiler stays
in the build stage. See [distribution](../../docs/DISTRIBUTION.md) for local builder overrides.

The binary is a glibc executable (`libc.so.6` + `libm.so.6`), so the final image is
`debian:bookworm-slim` plus one file; it runs as uid 10001.

## Run locally with the limits a pod would get

```sh
docker run -d --rm --name tin-api --cpus=2 --memory=256m -p 8080:8080 tin-api:dev
curl -s localhost:8080/json; echo        # {"message":"Hello, World!"}
curl -s localhost:8080/healthz; echo     # ok
curl -s localhost:8080/plaintext; echo   # Hello, World!
docker stop tin-api                      # SIGTERM: graceful shutdown, exit code 0
```

Inside the container the server sees `/sys/fs/cgroup/cpu.max = 200000 100000`, so
`hearth.Cores()` is 2 (not the host's CPU count), and `/sys/fs/cgroup/memory.max = 268435456`.
`TIN_CORES=n` overrides the core count; `TIN_PIN=1` pins each core thread to one allowed CPU
(automatic when the cores map one-to-one onto the allowed CPUs).

## Routes

| path | response |
|---|---|
| `/healthz` | `200 ok` (readiness and liveness probe) |
| `/json` | `{"message":"Hello, World!"}` |
| `/plaintext` | `Hello, World!` |
| `/echo?name=x` | JSON echo of path, query, `name`, User-Agent and body length |
| `/hits` | requests served by this core |

## Kubernetes

```sh
kind load docker-image tin-api:dev        # or push to a registry and change the image name
kubectl apply -f examples/k8s/deployment.yaml
kubectl rollout status deploy/tin-api
kubectl port-forward svc/tin-api 8080:80 &
curl -s localhost:8080/healthz
```

`deployment.yaml` sets `resources.limits` (cpu 2, memory 256Mi), both probes on `GET /healthz`,
`PORT=8080`, `terminationGracePeriodSeconds: 30`, a `preStop` sleep of 3 s, and a ClusterIP Service.

## Shutdown behaviour (SIGTERM or SIGINT)

1. The signals are blocked in every thread before the cores start (`pthread_sigmask`); core 0
   receives them through `signalfd` (Linux) or `kqueue EVFILT_SIGNAL` (macOS). No signal handler
   runs, so no Tin code ever runs on a foreign thread.
2. Core 0 tells every core (through the connection hand-off pipes) to stop: each closes its
   listener, keeps serving the requests already in flight, answers any further request on an
   open keep-alive connection with `Connection: close`, and closes it afterwards.
3. The process exits 0 as soon as no core has an open connection, or after `TIN_GRACE`
   seconds (default 25; set it below `terminationGracePeriodSeconds`). A second signal exits
   immediately.

`tests/graceful/graceful.go` exercises all of this against a server binary:

```sh
go run tests/graceful/graceful.go bin/api 9381                                   # macOS
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o bin/linux/graceful tests/graceful/graceful.go
docker run --rm -v $PWD/bin/linux:/w tin-debian-arm64 /w/graceful /w/api 9381     # Linux
```
