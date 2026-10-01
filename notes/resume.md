# Resume here (updated 2026-10-01 21:04 Beirut)

## State
- Repo: github.com/yasserreslan/tin (public). main is protected: the CI check (native
  linux-arm64 + macOS arm64, docs/CI.md) must pass and branches must be up to date; all
  changes go through PRs.
- All 21 review issues are fixed and closed (PRs #22–#41); each has a regression in
  tests/regressions/ or tools/ci/.
- darwin-arm64 and linux-arm64: complete, tested natively in CI.
- linux-amd64: every tests/v2, tests/regressions and legacy test passes and the compiler
  self-hosts; CI runs it natively on ubuntu-24.04 (seed/tinc-linux-amd64,
  make linux-amd64-bootstrap).

## Next, in order
1. Benchmark anvil vs Go on real x86-64 hardware (CI now runs linux-amd64 natively on
   ubuntu-24.04, but shared runners are too noisy for the benchmark gate).
2. cores-stable.tin failed once on emulated amd64 ("cannot start a core thread"), then passed
   7 runs; probably emulator memory pressure with 11 x 8 MiB stacks. Watch it in native CI.
3. wire: issues #43 (Content-Length trusted up front) and #44 (Transfer-Encoding variants).
4. seal on arm64 CPUs without SHA-2 (AT_HWCAP fallback) is untested on real hardware.
5. Benchmark suites to add (bench/): rest of the Benchmarks Game (fasta, k-nucleotide,
   reverse-complement; pidigits needs bigints, regex-redux a regex package), Are We Fast Yet,
   1BRC.
6. Releases: `make dist` + a tag-triggered release workflow (per-target tarballs, SHA256SUMS,
   install.sh into ~/.tin), no Homebrew.
7. ML serving path: f32, extern for user packages (bind ONNX Runtime), SIMD.
8. v0.4 async I/O: design in notes/design_v04.md waits for the user's review.

## Rules
gh account for this repo: yasserreslan (switch back to yasser-reslan for work). Port 8080
belongs to the user's other program. Downloads need the user's OK.
