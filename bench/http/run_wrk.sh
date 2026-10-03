#!/bin/sh
# Usage: bench/http/run_wrk.sh CORES WRK_THREADS CONNS SECONDS ROUNDS [--base-api PATH --head-api PATH]
exec python3 "$(dirname "$0")/run_wrk.py" "$@"
