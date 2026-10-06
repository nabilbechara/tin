#!/bin/sh
# Cross-compile and check positive AND negative tests on Linux arm64.
cd "$(dirname "$0")/../.." || exit 1
exec python3 tools/ci/suite.py "${1:-bin/tinc}" --target linux-arm64 --docker "${TIN_LINUX_IMAGE:-tin-debian-arm64}"
