#!/bin/sh
# Compile and run all strict tests; stdout and exit status are both required.
cd "$(dirname "$0")/.." || exit 1
exec python3 tools/ci/suite.py "${1:-bin/tinc}"
