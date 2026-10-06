# x64fuzz

`tools/dev/x64fuzz/run.sh [COUNT] [SEED]` (default 20000 instructions, seed 1) builds `fuzz.tin`
with `bin/tinc`, generates COUNT random x86-64 instructions over every op in
`selfhost/asm_x64.tin` (all 16 integer and xmm registers, every load/store size and
extension, immediates at the imm8/imm32/imm64 boundaries, memory operands with every base,
index and scale, 0/8/32-bit displacements and rip-relative labels and symbols, long and
relaxed short branches), writes the encoded bytes to `out.bin` and our Intel-syntax listing to
`ours.txt`, disassembles the bytes with `x86_64-linux-gnu-objdump -D -b binary -m i386:x86-64
-M intel` inside a `debian:bookworm-slim` container (set `X64FUZZ_IMAGE` to an image that
already has `binutils-x86-64-linux-gnu` to skip the apt-get), and `compare.py` normalizes
both listings and diffs them instruction by instruction, exiting non-zero on any mismatch; the
driver also checks that `x64_layout`, `x64_encode` and `x64_assemble` agree on sizes and bytes.
Work files land in `$X64FUZZ_DIR` (default `$TMPDIR/x64fuzz`).
