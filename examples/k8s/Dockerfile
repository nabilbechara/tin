# examples/k8s/Dockerfile: packages the cross-compiled linux-arm64 build of examples/api.tin.
# Build from the repository root (the context must contain bin/linux/api):
#   TIN_ROOT=$PWD bin/tinc -target linux-arm64 -o bin/linux/api examples/api.tin
#   docker build -f examples/k8s/Dockerfile -t tin-api:dev .
FROM debian:bookworm-slim

# The binary is dynamically linked against glibc only (libc.so.6, libm.so.6), which the base
# image provides; nothing else is installed. /bin/sleep (coreutils) serves the preStop hook.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin tin
COPY bin/linux/api /app/api

USER 10001
ENV PORT=8080
# TIN_GRACE (seconds the server keeps serving open connections after SIGTERM) defaults to 25,
# below the Deployment's terminationGracePeriodSeconds of 30.
EXPOSE 8080
ENTRYPOINT ["/app/api"]
