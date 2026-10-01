#!/bin/sh
# Usage: bench/http/run_pipelined.sh "CORES..." — wrk with 16 pipelined requests per write.
cd "$(dirname "$0")/../.." || exit 1
for cores in ${1:-1 2 4}; do
  for route in /plaintext /json; do
    for srv in anvil fasthttp net/http; do
      case $srv in
        anvil) TIN_CORES=$cores bin/api > /dev/null 2>&1 & pid=$!; port=9180 ;;
        fasthttp) GOMAXPROCS=$cores bin/fast :9182 > /dev/null 2>&1 & pid=$!; port=9182 ;;
        net/http) GOMAXPROCS=$cores bin/gonet :9181 > /dev/null 2>&1 & pid=$!; port=9181 ;;
      esac
      sleep 0.4
      wrk -t4 -c128 -d2s -s bench/http/pipeline.lua "http://127.0.0.1:$port$route" -- 16 > /dev/null 2>&1
      r=$(wrk -t4 -c128 -d5s --latency -s bench/http/pipeline.lua "http://127.0.0.1:$port$route" -- 16 2>&1 | awk '/Requests\/sec/ {rps=$2} $1=="99%" {p=$2} END {printf "%10.0f req/s  p99 %s", rps, p}')
      kill $pid; wait $pid 2>/dev/null
      printf "cores=%s %-10s %-9s %s\n" "$cores" "$route" "$srv" "$r"
    done
  done
done
