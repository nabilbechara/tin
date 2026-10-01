# Continuous integration and regression policy

Every push to `main` and every pull request runs native Linux arm64 (`ubuntu-24.04-arm`), Linux x86-64 (`ubuntu-24.04`) and macOS arm64 (`macos-15`) checks. Merge groups and manual runs use the same workflow. The final **CI** check succeeds only when every native job and the issue-policy job succeed; skipped, cancelled and failed dependencies cannot produce a green gate. Main requires this GitHub Actions check and an up-to-date PR branch, including for administrators.

## What is tested

- Clean build from the committed seed and two byte-identical self-hosted compiler rebuilds.
- Every `tests/v2/*.tin`, including negative compilation tests and their exact diagnostics. Missing expected output, compiler crashes, process crashes, nonzero exit and timeouts fail. Each run uses fresh executable paths.
- Legacy native-executable compatibility on every platform; original Go bootstrap and assembly linkage on macOS (the original bootstrap emits Darwin assembly).
- Memory regressions: bounds panics, allocation size overflow and negative lengths, large first allocations, single evaluation of allocation lengths, read-only and region checking through indirect calls, nested zero values, deep `keep` ownership and 200 request-pool reset/reuse cycles.
- Linux HTTP framing/conformance, stable RSS over two million requests after warmup, and graceful shutdown. Throughput is reported, never used as a performance threshold.
- Harness self-tests ensure expected output cannot disguise crashes/timeouts or unexpectedly accepted negative programs.

The Python harness uses only the standard library. Shell entrypoints now require Python 3. Native runtime probes have a 20-second timeout, core dumps disabled, and a 512 MiB virtual-memory limit on Linux. The first-allocation crash reproducer is Linux-only: macOS can map writable memory beyond the undersized allocation, making a SIGSEGV expectation unreliable there. HTTP tests require `ps` (available on hosted Ubuntu).

Linux amd64 is a supported execution gate: the `ubuntu-24.04` job builds the compiler from `seed/tinc-linux-amd64`, checks the self-hosting fixed point and runs every suite natively on x86-64 hardware. Refresh that seed with `make linux-amd64-bootstrap` (emulated container on an arm64 Mac).

## Existing defects versus new regressions

The initial baseline contains explicit `known_failure` contracts for open issues #1–6. These are visible as **XFAIL**, not PASS, in logs, JSON artifacts and the Actions summary. A known failure matches its phase, exit code and specified output/diagnostic; unrelated failures are not exempt. A timeout is never an expected failure.

If a fix makes the expected behavior pass while the exemption still exists, CI reports **XPASS and fails**. Keep the test and remove its `known_failure` field in the same fixing PR. Thereafter a recurrence is a normal blocking failure. Do not delete the test or weaken the expected contract to close an issue. New failures must not be added to the exemption list just to unblock a PR.

The issue audit checks GitHub for every exempted issue. Closing an issue while an exemption remains fails the audit. It runs on pushes/PRs and on issue close/reopen events against the default branch. It reads issue state only; it does not execute issue text, edit workflow code, comment, reopen issues or auto-merge changes. If closing as a duplicate or not planned, explicitly review and explain any corresponding coverage change.

## Resolving an issue

1. Add a small deterministic reproducer and the intended correct behavior. For a language/runtime bug, use `tests/regressions/NAME.tin` and an entry in `cases.json` with the issue number. Every `.tin` file must have exactly one entry; the runner discovers new cases without workflow edits.
2. Implement the fix. If the case already exists, remove its `known_failure` contract and keep its expected behavior. For non-Tin tooling bugs, extend `tools/ci/test_*.py`; unittest discovers them automatically. Issues #7 and #8 are covered by these harness tests.
3. Run the commands below and include the regression test names in the PR. Expand the workflow only when the issue needs a new environment/tool, such as native amd64 or cgroup namespace fixtures.
4. Let CI pass and merge the PR before closing the issue (a `Fixes #N` PR reference closes it on merge).

This avoids a bot rewriting Actions after closure: the regression becomes required **in the fixing PR**, before its code can merge. The issue audit catches forgotten exemptions afterward.

## Local commands

```sh
make bootstrap
python3 -m unittest discover -s tools/ci -p 'test_*.py' -v
tools/v2test.sh bin/tinc
python3 tools/ci/regressions.py
python3 tools/ci/regressions.py --audit   # network; GH_TOKEN optional for public issues
TINC="$PWD/bin/tinc" go test -count=1 ./bootstrap
python3 tools/ci/http_check.py            # Linux HTTP/RSS/shutdown
```

`tools/linuxtest.sh` and `tools/x64fuzz/linuxtest_amd64.sh` use the same strict runner for Docker cross-tests. They check negative diagnostics on the build host and positive outputs/exit codes in the chosen image. `TIN_LINUX_IMAGE` chooses the image; `TIN_ROOT` can select a library tree. The old `X64_TEST_DIR` output option is replaced by unique temporary directories and logs under `bin/ci/`.

Diagnostics are uploaded for 14 days even if a job fails. No compiled output is cached: a stale compiler or test binary cannot make a fresh checkout pass.
