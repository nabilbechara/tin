#!/bin/sh
# Cross-compile and check positive AND negative tests, then the issue regressions, on Linux amd64.
cd "$(dirname "$0")/../../.." || exit 1
image="${TIN_LINUX_IMAGE:-tin-debian-amd64}"
python3 tools/ci/suite.py "${1:-bin/tinc}" --target linux-amd64 --docker "$image"
strict=$?
python3 tools/ci/regressions.py --compiler "${1:-bin/tinc}" --target linux-amd64 --docker "$image" || exit 1
exit $strict
