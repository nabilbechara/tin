#!/usr/bin/env python3
"""Build each benchmark with Tin and Go, check outputs match, report best-of-N times."""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "bench")
OUT = os.path.join(ROOT, "bin", "bench")
TIN = os.path.join(ROOT, "tin")
RUNS = int(os.environ.get("RUNS", "5"))

def best(cmd, runs=RUNS):
    times = []
    out = None
    for _ in range(runs):
        t = time.perf_counter()
        out = subprocess.run(cmd, check=True, capture_output=True).stdout
        times.append(time.perf_counter() - t)
    return min(times), out

os.makedirs(OUT, exist_ok=True)
names = sorted(f[:-4] for f in os.listdir(BENCH) if f.endswith(".tin"))
if len(sys.argv) > 1:
    names = [n for n in names if n in sys.argv[1:]]
print(f"{'bench':10} {'tin build':>10} {'go build':>10} {'tin run':>10} {'go run':>10} {'speedup':>8}")
for name in names:
    tin_exe, go_exe = os.path.join(OUT, name + "_tin"), os.path.join(OUT, name + "_go")
    tb, _ = best([TIN, "build", os.path.join(BENCH, name + ".tin"), "-o", tin_exe], 3)
    gb, _ = best(["go", "build", "-o", go_exe, os.path.join(BENCH, name + ".go")], 3)
    tr, tout = best([tin_exe])
    gr, gout = best([go_exe])
    flag = "" if tout == gout else "  OUTPUT MISMATCH"
    print(f"{name:10} {tb*1000:8.1f}ms {gb*1000:8.1f}ms {tr*1000:8.1f}ms {gr*1000:8.1f}ms {gr/tr:7.2f}x{flag}")
