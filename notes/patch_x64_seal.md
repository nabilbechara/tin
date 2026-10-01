# Patch: seal.Sha256 falls back to the portable code on x86-64

`seal.hw_blocks` is replaced by hand-assembled ARMv8 SHA-256 instructions in gen.tin; the x86-64
backend compiles its body, which panics ("hardware SHA-256 is not available for this target").
`TARGET_X64` is `true` in `lib/runtime_linux_amd64.tin` and `false` in the other per-arch
runtime files (see `notes/patch_x64_runtime.md`), so `Sha256` can pick the software path at
compile time (the condition is constant, so the dead branch costs nothing).

File: `lib/seal.tin`, in `func Sha256(s str) []u8`, insert as the first statement:

```go
// Sha256 is the SHA-256 digest of s (32 bytes).
func Sha256(s str) []u8 {
	if TARGET_X64 {
		return Sha256Soft(s)
	}
	h := []u32{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19}
	...
```

Nothing else changes: `Sha256Soft`, `HmacSha256` (which calls `Sha256`) and `Sha256Hex` keep
working, and `tests/v2/seal.tin` passes on linux-amd64 with this patch applied (verified with a
patched copy of lib/ via TIN_ROOT).
