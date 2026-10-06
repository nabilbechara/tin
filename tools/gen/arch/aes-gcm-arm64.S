// AES-CTR and GHASH leaves for seal (ARMv8 Crypto Extensions: AESE/AESMC and PMULL).
// tools/gen/gen_aes_hw.py turns them into toolchain/compiler/aes_hw.tin. Relocation-free; they use only
// caller-saved registers (x0-x9, v0-v7, v16-v21) and keep x28 (the core context).
// Constant-time: no branch or address depends on keys, data or the hash state.
	.text
	.arch armv8-a+crypto

// aes_hw_ctr(rk x0, nr x1, ctr x2, src x3, dst x4, nblocks x5): dst = src ^ AES(rk, counter)
// for nblocks 16-byte blocks; the counter block at ctr is incremented (big-endian, last four
// bytes) once per block and stored back.
	.globl aes_hw_ctr
	.type aes_hw_ctr, %function
aes_hw_ctr:
	cbz	x5, 9f
	ld1	{v16.16b}, [x2]
	ldr	w6, [x2, #12]
	rev	w6, w6
1:	mov	v0.16b, v16.16b
	rev	w7, w6
	mov	v0.s[3], w7
	mov	x8, x0
	sub	x9, x1, #1
	ld1	{v1.16b}, [x8], #16
2:	aese	v0.16b, v1.16b
	aesmc	v0.16b, v0.16b
	ld1	{v1.16b}, [x8], #16
	subs	x9, x9, #1
	b.ne	2b
	aese	v0.16b, v1.16b
	ld1	{v1.16b}, [x8]
	eor	v0.16b, v0.16b, v1.16b
	ld1	{v2.16b}, [x3], #16
	eor	v2.16b, v2.16b, v0.16b
	st1	{v2.16b}, [x4], #16
	add	w6, w6, #1
	subs	x5, x5, #1
	b.ne	1b
	rev	w7, w6
	str	w7, [x2, #12]
9:	ret
	.size aes_hw_ctr, .-aes_hw_ctr

// aes_hw_subword(w w0) -> the AES S-box on each byte of w. AESE with a zero key on w in every
// column is SubBytes(ShiftRows(state)), and ShiftRows moves nothing between equal columns.
	.globl aes_hw_subword
	.type aes_hw_subword, %function
aes_hw_subword:
	dup	v0.4s, w0
	movi	v1.16b, #0
	aese	v0.16b, v1.16b
	umov	w0, v0.s[0]
	ret
	.size aes_hw_subword, .-aes_hw_subword

// ghash_hw(state x0, h x1, data x2, nblocks x3): state = (state ^ block) * H for each
// 16-byte block, in GCM's byte order in memory. Inside, RBIT on each byte turns a block into
// a polynomial with x^i at bit i, so PMULL multiplies it directly; the product is reduced
// mod x^128 + x^7 + x^2 + x + 1 with two more PMULLs by 0x87.
	.globl ghash_hw
	.type ghash_hw, %function
ghash_hw:
	cbz	x3, 9f
	ld1	{v0.16b}, [x0]
	rbit	v0.16b, v0.16b
	ld1	{v20.16b}, [x1]
	rbit	v20.16b, v20.16b
	ext	v19.16b, v20.16b, v20.16b, #8
	mov	x4, #0x87
	dup	v21.2d, x4
	movi	v7.16b, #0
1:	ld1	{v1.16b}, [x2], #16
	rbit	v1.16b, v1.16b
	eor	v0.16b, v0.16b, v1.16b
	pmull	v2.1q, v0.1d, v20.1d
	pmull2	v3.1q, v0.2d, v20.2d
	pmull	v5.1q, v0.1d, v19.1d
	pmull2	v6.1q, v0.2d, v19.2d
	eor	v5.16b, v5.16b, v6.16b
	ext	v6.16b, v7.16b, v5.16b, #8
	eor	v2.16b, v2.16b, v6.16b
	ext	v6.16b, v5.16b, v7.16b, #8
	eor	v3.16b, v3.16b, v6.16b
	pmull	v4.1q, v3.1d, v21.1d
	pmull2	v5.1q, v3.2d, v21.2d
	ext	v6.16b, v7.16b, v5.16b, #8
	eor	v2.16b, v2.16b, v6.16b
	eor	v2.16b, v2.16b, v4.16b
	ext	v6.16b, v5.16b, v7.16b, #8
	pmull	v6.1q, v6.1d, v21.1d
	eor	v0.16b, v2.16b, v6.16b
	subs	x3, x3, #1
	b.ne	1b
	rbit	v0.16b, v0.16b
	st1	{v0.16b}, [x0]
9:	ret
	.size ghash_hw, .-ghash_hw
