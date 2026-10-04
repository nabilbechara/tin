#!/bin/sh
# Compile and run all strict tests; stdout and exit status are both required.
cd "$(dirname "$0")/.." || exit 1
compiler=${1:-bin/tinc}
python3 tools/ci/suite.py "$compiler" || exit $?
exec tests/edition1.sh "$compiler"
