#!/bin/sh
# Compile and run all strict tests; stdout and exit status are both required.
cd "$(dirname "$0")/../.." || exit 1
compiler=${1:-bin/tinc}
python3 tools/ci/suite.py "$compiler" || exit $?
# Diagnostic codes: the compiler, toolchain/docs/ERRORS.md and the .err files agree; examples compile as shown.
python3 tools/ci/diagnostics_check.py "$compiler" || exit $?
exec toolchain/tests/edition1.sh "$compiler"
