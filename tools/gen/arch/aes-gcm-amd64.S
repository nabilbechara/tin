// AES-CTR and GHASH leaves for seal (AES-NI and PCLMULQDQ), and their CPUID check.
// tools/gen/gen_aes_hw.py turns them into toolchain/compiler/aes_hw.tin. Relocation-free; they use only
// caller-saved registers (rbx is saved by aes_hw_cpu) and never touch r15 (the core context).
// Constant-time: no branch or address depends on keys, data or the hash state (PSHUFB
// shuffles registers, it does not read memory).
.intel_syntax noprefix
.text

// aes_hw_cpu() -> 1 when the CPU has AES-NI, PCLMULQDQ, SSSE3 and SSE4.1, else 0.
.global aes_hw_cpu
.type aes_hw_cpu, @function
aes_hw_cpu:
	push rbx
	mov eax, 1
	cpuid
	xor eax, eax
	and ecx, 0x02080202
	cmp ecx, 0x02080202
	sete al
	pop rbx
	ret
.size aes_hw_cpu, .-aes_hw_cpu

// aes_hw_ctr(rk rdi, nr rsi, ctr rdx, src rcx, dst r8, nblocks r9): dst = src ^ AES(rk,
// counter) for nblocks 16-byte blocks; the counter block at ctr is incremented (big-endian,
// last four bytes) once per block and stored back.
.global aes_hw_ctr
.type aes_hw_ctr, @function
aes_hw_ctr:
	test r9, r9
	jz 9f
	movdqu xmm6, [rdx]
	mov eax, [rdx+12]
	bswap eax
1:	movdqa xmm0, xmm6
	mov r10d, eax
	bswap r10d
	pinsrd xmm0, r10d, 3
	mov r11, rdi
	movdqu xmm1, [r11]
	pxor xmm0, xmm1
	mov r10, rsi
	dec r10
2:	add r11, 16
	movdqu xmm1, [r11]
	aesenc xmm0, xmm1
	dec r10
	jnz 2b
	movdqu xmm1, [r11+16]
	aesenclast xmm0, xmm1
	movdqu xmm2, [rcx]
	pxor xmm2, xmm0
	movdqu [r8], xmm2
	add rcx, 16
	add r8, 16
	inc eax
	dec r9
	jnz 1b
	bswap eax
	mov [rdx+12], eax
9:	ret
.size aes_hw_ctr, .-aes_hw_ctr

// aes_hw_subword(w edi) -> the AES S-box on each byte of w: AESENCLAST with a zero key on w
// in every column (ShiftRows moves nothing between equal columns).
.global aes_hw_subword
.type aes_hw_subword, @function
aes_hw_subword:
	movd xmm0, edi
	pshufd xmm0, xmm0, 0
	pxor xmm1, xmm1
	aesenclast xmm0, xmm1
	movd eax, xmm0
	ret
.size aes_hw_subword, .-aes_hw_subword

// rbit reverses the bits of every byte of \x (PSHUFB on nibbles; xmm13 = 0x0f bytes,
// xmm14 = reversed nibbles, xmm15 = reversed nibbles << 4; clobbers xmm8, xmm9).
.macro rbit x
	movdqa xmm8, \x
	pand xmm8, xmm13
	psrlw \x, 4
	pand \x, xmm13
	movdqa xmm9, xmm15
	pshufb xmm9, xmm8
	movdqa xmm8, xmm14
	pshufb xmm8, \x
	por xmm9, xmm8
	movdqa \x, xmm9
.endm

// ghash_hw(state rdi, h rsi, data rdx, nblocks rcx): state = (state ^ block) * H for each
// 16-byte block, in GCM's byte order in memory. Bit-reversing each byte turns a block into
// a polynomial with x^i at bit i; PCLMULQDQ multiplies it and two more by 0x87 reduce it
// mod x^128 + x^7 + x^2 + x + 1 (the same steps as the ARMv8 leaf).
.global ghash_hw
.type ghash_hw, @function
ghash_hw:
	test rcx, rcx
	jz 9f
	mov eax, 0x0f0f0f0f
	movd xmm13, eax
	pshufd xmm13, xmm13, 0
	mov rax, 0x0e060a020c040800
	movq xmm14, rax
	mov rax, 0x0f070b030d050901
	pinsrq xmm14, rax, 1
	mov rax, 0xe060a020c0408000
	movq xmm15, rax
	mov rax, 0xf070b030d0509010
	pinsrq xmm15, rax, 1
	mov eax, 0x87
	movq xmm12, rax
	punpcklqdq xmm12, xmm12
	movdqu xmm0, [rdi]
	rbit xmm0
	movdqu xmm10, [rsi]
	rbit xmm10
1:	movdqu xmm1, [rdx]
	rbit xmm1
	pxor xmm0, xmm1
	movdqa xmm2, xmm0
	pclmulqdq xmm2, xmm10, 0x00
	movdqa xmm3, xmm0
	pclmulqdq xmm3, xmm10, 0x11
	movdqa xmm4, xmm0
	pclmulqdq xmm4, xmm10, 0x10
	movdqa xmm5, xmm0
	pclmulqdq xmm5, xmm10, 0x01
	pxor xmm4, xmm5
	movdqa xmm5, xmm4
	pslldq xmm5, 8
	pxor xmm2, xmm5
	psrldq xmm4, 8
	pxor xmm3, xmm4
	movdqa xmm4, xmm3
	pclmulqdq xmm4, xmm12, 0x00
	movdqa xmm5, xmm3
	pclmulqdq xmm5, xmm12, 0x01
	pxor xmm2, xmm4
	movdqa xmm6, xmm5
	pslldq xmm6, 8
	pxor xmm2, xmm6
	psrldq xmm5, 8
	pclmulqdq xmm5, xmm12, 0x00
	pxor xmm2, xmm5
	movdqa xmm0, xmm2
	add rdx, 16
	dec rcx
	jnz 1b
	rbit xmm0
	movdqu [rdi], xmm0
9:	ret
.size ghash_hw, .-ghash_hw
