#!/bin/sh
# Usage: bench/http/run_wrk.sh CORES WRK_THREADS CONNS SECONDS ROUNDS
# anvil vs fasthttp vs net/http under wrk, rounds interleaved; prints the median of each.
cd "$(dirname "$0")/../.." || exit 1
cores=$1; t=$2; c=$3; d=$4; rounds=${5:-3}
out=bin/wrk_results.txt; : > $out
one() { # name port path pid
  wrk -t"$t" -c"$c" -d2s "http://127.0.0.1:$2$3" > /dev/null 2>&1
  c0=$(cpusecs "$4")
  wrk -t"$t" -c"$c" -d"${d}s" --latency "http://127.0.0.1:$2$3" > bin/wrk.out 2>&1
  c1=$(cpusecs "$4")
  rps=$(awk '/Requests\/sec/ {print $2}' bin/wrk.out)
  p99=$(awk '$1=="99%" {v=$2; if (v ~ /ms$/) {sub(/ms/,"",v); v=v*1000} else if (v ~ /us$/) {sub(/us/,"",v)} else if (v ~ /s$/) {sub(/s/,"",v); v=v*1000000}; print v}' bin/wrk.out)
  errs=$(awk '/Socket errors|Non-2xx/ {print}' bin/wrk.out | tr '\n' ' ')
  rss=$(ps -o rss= -p "$4" | tr -d ' ')
  total=$(awk '/requests in/ {print $1}' bin/wrk.out)
  per=$(awk -v n="$total" -v a="$c0" -v b="$c1" 'BEGIN { if (b > a) printf "%.0f", n/(b-a); else print 0 }')
  echo "$1 $3 $rps $p99 $rss $per $errs" >> $out
}
cpusecs() { # cumulative CPU seconds of pid
  ps -o time= -p "$1" | awk -F: '{ if (NF == 3) print $1*3600+$2*60+$3; else print $1*60+$2 }'
}
for r in $(seq 1 $rounds); do
  for path in /json /plaintext; do
    TIN_CORES=$cores bin/api > /dev/null 2>&1 & pid=$!; sleep 0.4
    one anvil 9180 $path $pid; kill $pid; wait $pid 2>/dev/null
    GOMAXPROCS=$cores bin/fast :9182 > /dev/null 2>&1 & pid=$!; sleep 0.4
    one fasthttp 9182 $path $pid; kill $pid; wait $pid 2>/dev/null
    GOMAXPROCS=$cores bin/gonet :9181 > /dev/null 2>&1 & pid=$!; sleep 0.4
    one net/http 9181 $path $pid; kill $pid; wait $pid 2>/dev/null
  done
done
for path in /json /plaintext; do
  for name in anvil fasthttp net/http; do
    grep "^$name $path " $out | awk -v n="$name" -v p="$path" '
      { r[NR]=$3; l[NR]=$4; m[NR]=$5; c[NR]=$6; if ($7 != "") e=" errors"; }
      END {
        cnt=NR; for (i=1;i<=cnt;i++) for (j=i+1;j<=cnt;j++) { if (r[j]<r[i]) {x=r[i];r[i]=r[j];r[j]=x} if (l[j]<l[i]) {x=l[i];l[i]=l[j];l[j]=x} if (m[j]<m[i]) {x=m[i];m[i]=m[j];m[j]=x} if (c[j]<c[i]) {x=c[i];c[i]=c[j];c[j]=x} }
        mid=int((cnt+1)/2)
        printf "%-9s %-10s %9.0f req/s   p99 %7.0f us   %8.0f req/cpu-s   rss %6d KB%s\n", n, p, r[mid], l[mid], c[mid], m[mid], e
      }'
  done
done
