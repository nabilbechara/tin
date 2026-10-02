# Installing Tin and building containers

Tin releases support macOS arm64, Linux arm64 and Linux amd64. Linux executables use
glibc 2.34 or newer; Debian 12 and Ubuntu 22.04 or newer are suitable. Alpine/musl is
not supported. A Kubernetes node can run the Debian-based image as long as its CPU
architecture matches the image; its host distribution does not need to match Debian.

## Install a compiler

Download the installer from the latest release, then run it (`sh install-tin.sh 0.4.1`
installs a given version instead):

```sh
curl -fL https://github.com/yasserreslan/tin/releases/latest/download/install.sh -o install-tin.sh
sh install-tin.sh
export PATH="$HOME/.tin/bin:$PATH"
tin version
tin build app.tin -o app
```

The installer chooses the host target, verifies the archive against `SHA256SUMS`,
and compiles and runs a small program before activating it. No root, Go or C compiler
is needed. Installs live in `~/.tin/versions/`; upgrades preserve older versions and
update the `tin` and `tinc` symlinks in `~/.tin/bin`. `TIN_INSTALL_DIR` changes this
directory. Running `sh install-tin.sh` without a version selects the latest stable release.

For a manual install, download `tin-0.4.0-<target>.tar.gz` and `SHA256SUMS` from the
same release, verify the SHA-256 digest, extract it and put its root directory on PATH.
The archive includes `bin/tinc`, all libraries, compiler sources, tests and the matching
seed. Moving the whole extracted tree is safe. Python 3 and make are needed for the
compiler's suites/bootstrap; Go is needed only for the legacy harness and Go benchmarks.

## Compile with Docker

The versioned builder is `ghcr.io/yasserreslan/tin:0.4.0`, with native amd64 and arm64
images under one manifest. Docker chooses the host's architecture automatically:

```sh
docker run --rm -v "$PWD:/src" -w /src ghcr.io/yasserreslan/tin:0.4.0 build app.tin -o app
```

The compiler supports cross-compilation too: add `--target linux-amd64` or
`--target linux-arm64` after `build app.tin`. For deployable images, use a multi-stage
Dockerfile so the final image contains the application and glibc, without the compiler:

```dockerfile
FROM ghcr.io/yasserreslan/tin:0.4.0 AS build
WORKDIR /src
COPY . .
RUN tin build app.tin -o /app

FROM debian:bookworm-slim
COPY --from=build /app /app
USER 10001:10001
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app"]
```

Build for the destination nodes with `docker buildx build --platform linux/amd64` or
`linux/arm64`; for both, use `--platform linux/amd64,linux/arm64 --push -t YOUR_IMAGE .`.
The selected builder compiles for that stage's native platform. Pin a version (or image
digest) in production; `latest` tracks the most recently published stable release.

The complete HTTP example is `examples/k8s/Dockerfile`. From the repository root:

```sh
docker build -f examples/k8s/Dockerfile -t tin-api:dev .
docker run --rm -p 9180:8080 tin-api:dev
```

`--build-arg TIN_SOURCE=path/to/main.tin` chooses another source file;
`--build-arg TIN_BUILDER=YOUR_BUILDER_IMAGE` uses a locally built compiler image.

## Maintain releases

Every merge into main is released automatically once its CI gate is green:
`.github/workflows/auto-release.yml` tags the merged commit and runs the release workflow.
The version comes from `VERSION` and the existing tags (`tools/ci/next_version.py`): the
first merge after `VERSION` changes is released as `VERSION` itself, and later merges as
the next patch of its major.minor (`0.4.1`, `0.4.2`, ...). To start a new series, bump
`VERSION`'s major or minor (`0.5.0`) in a PR; a prerelease `VERSION` (`0.6.0-rc.1`) is
released once, then needs another bump. Only the commit at the head of main is released:
when merges land faster than CI, the last one carries all of them.

`make dist` creates a native archive and its SHA-256 sidecar in `bin/dist/`.
`.github/workflows/distribution.yml` verifies relocated archives and self-hosting on all
three native targets, and builds/runs the Linux builder and application images on both
architectures for every PR.

A release can still be made by hand: push a tag for a main commit with green CI
(`git tag v0.4.7 COMMIT_SHA && git push origin v0.4.7`), or rerun one through workflow
dispatch. `.github/workflows/release.yml` rejects tags that are not `VERSION` or a later
patch of it, tags outside main, commits without successful CI and versions already
released. It builds each target natively,
tests the archives and images, pushes the Linux images, combines their manifests, and
publishes three archives, `SHA256SUMS` and `install.sh` as GitHub Release assets, with
notes generated from the merged PRs. A prerelease tag such as `v0.6.0-rc.1` does not move
`latest`. Failed runs before
publication can be retried through workflow dispatch with the same existing tag.

The first GHCR package is private by default. Its owner must change the package's
visibility to public once in GitHub Packages settings, then verify an unauthenticated
pull; subsequent versions use that visibility. Publishing runs with GitHub Actions'
repository token (`packages: write`), so no Docker Hub credentials are required.
