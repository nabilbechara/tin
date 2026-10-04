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

# The binary is static (no C library); the base image is here for /bin/sleep (coreutils),
# which serves the preStop hook. Nothing else is installed.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin tin
COPY --from=build /out/api /app/api

USER 10001
ENV PORT=8080
# TIN_GRACE (seconds the server keeps serving open connections after SIGTERM) defaults to 25,
# below the Deployment's terminationGracePeriodSeconds of 30.
EXPOSE 8080
ENTRYPOINT ["/app/api"]
