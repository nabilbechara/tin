# Build Tin source with the published compiler, then package only the application.
# Build from the repository root:
#   docker build -f examples/k8s/Dockerfile -t tin-api:dev .
ARG TIN_BUILDER=ghcr.io/yasserreslan/tin:0.4.0
FROM ${TIN_BUILDER} AS build
WORKDIR /src
COPY . .
ARG TIN_SOURCE=examples/api.tin
RUN mkdir -p /out && tin build "$TIN_SOURCE" -o /out/api

FROM debian:bookworm-slim

# The binary is dynamically linked against glibc only (libc.so.6, libm.so.6), which the base
# image provides; nothing else is installed. /bin/sleep (coreutils) serves the preStop hook.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin tin
COPY --from=build /out/api /app/api

USER 10001
ENV PORT=8080
# TIN_GRACE (seconds the server keeps serving open connections after SIGTERM) defaults to 25,
# below the Deployment's terminationGracePeriodSeconds of 30.
EXPOSE 8080
ENTRYPOINT ["/app/api"]
