#!/usr/bin/env python3
"""Regenerate tools/gen/arch/sha256-amd64.S: seal's SHA-256 compression on the x86-64 SHA extensions
(SHA256RNDS2, SHA256MSG1, SHA256MSG2; #488), and its CPUID check. The instruction list is written
once here; the script runs it on a model of the instructions against hashlib before it writes
the assembly, so a slip in the message schedule or the register shuffles is caught without a
CPU that has the extensions. Then tools/gen/gen_aes_hw.py puts the assembled bytes in selfhost/aes_hw.tin.
Usage: gen_sha256_amd64.py [--check]"""
import argparse
import hashlib
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
     0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
     0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
     0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
     0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
     0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
     0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
     0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]

# Registers: xmm1 = ABEF, xmm2 = CDGH, xmm0 = the message plus constants (rnds2's implicit operand),
# xmm3 = scratch, xmm4..xmm7 = the four message vectors W[4g..4g+3], xmm8 and xmm9 = the state at
# the start of a block, xmm10 = the byte-swap mask. Rows: (mnemonic, operands...).
MSG = ['xmm4', 'xmm5', 'xmm6', 'xmm7']


def block():
    """The instructions that compress one block at [rsi] with the constants at [rcx]."""
    ins = [('movdqa', 'xmm8', 'xmm1'), ('movdqa', 'xmm9', 'xmm2')]
    for g in range(16):
        x, p, n = MSG[g % 4], MSG[(g - 1) % 4], MSG[(g + 1) % 4]
        if g < 4:
            ins += [('movdqu', x, f'[rsi+{16 * g}]'), ('pshufb', x, 'xmm10')]
        ins += [('movdqu', 'xmm0', f'[rcx+{16 * g}]'), ('paddd', 'xmm0', x), ('sha256rnds2', 'xmm2', 'xmm1')]
        if 3 <= g <= 14:
            ins += [('movdqa', 'xmm3', x), ('palignr', 'xmm3', p, 4), ('paddd', n, 'xmm3'), ('sha256msg2', n, x)]
        ins += [('pshufd', 'xmm0', 'xmm0', 0x0e), ('sha256rnds2', 'xmm1', 'xmm2')]
        if 1 <= g <= 12:
            ins += [('sha256msg1', p, x)]
    ins += [('paddd', 'xmm1', 'xmm8'), ('paddd', 'xmm2', 'xmm9')]
    return ins


PROLOGUE = [
    ('movdqu', 'xmm3', '[rdi]'), ('movdqu', 'xmm2', '[rdi+16]'),
    ('pshufd', 'xmm3', 'xmm3', 0xb1), ('pshufd', 'xmm2', 'xmm2', 0x1b),
    ('movdqa', 'xmm1', 'xmm3'), ('palignr', 'xmm1', 'xmm2', 8), ('pblendw', 'xmm2', 'xmm3', 0xf0),
]
EPILOGUE = [
    ('pshufd', 'xmm3', 'xmm1', 0x1b), ('pshufd', 'xmm2', 'xmm2', 0xb1),
    ('movdqa', 'xmm1', 'xmm3'), ('pblendw', 'xmm1', 'xmm2', 0xf0), ('palignr', 'xmm2', 'xmm3', 8),
    ('movdqu', '[rdi]', 'xmm1'), ('movdqu', '[rdi+16]', 'xmm2'),
]


# ---- a model of the instructions, to check the list above against hashlib ----

M = 0xffffffff


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M


def s0(x):
    return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3)


def s1(x):
    return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10)


class Model:
    """xmm registers as four dwords, lowest first; memory as bytes."""

    def __init__(self, state, data, k):
        self.r = {f'xmm{i}': [0, 0, 0, 0] for i in range(16)}
        self.mem = {'rdi': bytearray(struct.pack('<8I', *state)), 'rsi': data, 'rcx': k}
        self.r['xmm10'] = list(struct.unpack('<4I', bytes([3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12])))
        self.shuffle_mask = [3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12]
        self.rsi = 0

    def load(self, ref):
        base, off = (ref[1:-1].split('+') + ['0'])[:2]
        buf = self.mem[base]
        o = int(off) + (self.rsi if base == 'rsi' else 0)
        return list(struct.unpack('<4I', bytes(buf[o:o + 16])))

    def get(self, a):
        return list(self.r[a]) if a in self.r else self.load(a)

    def run(self, ins):
        for op, *a in ins:
            f = getattr(self, 'i_' + op)
            f(*a)

    def i_movdqa(self, d, s):
        if d.startswith('['):
            base, off = (d[1:-1].split('+') + ['0'])[:2]
            self.mem[base][int(off):int(off) + 16] = struct.pack('<4I', *self.r[s])
        else:
            self.r[d] = self.get(s)

    i_movdqu = i_movdqa

    def i_paddd(self, d, s):
        self.r[d] = [(x + y) & M for x, y in zip(self.r[d], self.get(s))]

    def i_pshufb(self, d, s):
        b = struct.pack('<4I', *self.r[d])
        m = struct.pack('<4I', *self.r[s])
        out = bytes(0 if m[i] & 0x80 else b[m[i] & 15] for i in range(16))
        self.r[d] = list(struct.unpack('<4I', out))

    def i_pshufd(self, d, s, imm):
        v = self.r[s]
        self.r[d] = [v[(imm >> (2 * i)) & 3] for i in range(4)]

    def i_palignr(self, d, s, imm):
        cat = struct.pack('<4I', *self.r[s]) + struct.pack('<4I', *self.r[d])
        self.r[d] = list(struct.unpack('<4I', cat[imm:imm + 16]))

    def i_pblendw(self, d, s, imm):
        da, sa = struct.unpack('<8H', struct.pack('<4I', *self.r[d])), struct.unpack('<8H', struct.pack('<4I', *self.r[s]))
        w = [sa[i] if (imm >> i) & 1 else da[i] for i in range(8)]
        self.r[d] = list(struct.unpack('<4I', struct.pack('<8H', *w)))

    def i_sha256msg1(self, d, s):
        w = self.r[d]
        w4 = self.r[s][0]
        self.r[d] = [(w[0] + s0(w[1])) & M, (w[1] + s0(w[2])) & M, (w[2] + s0(w[3])) & M, (w[3] + s0(w4)) & M]

    def i_sha256msg2(self, d, s):
        w = self.r[d]
        w14, w15 = self.r[s][2], self.r[s][3]
        w16 = (w[0] + s1(w14)) & M
        w17 = (w[1] + s1(w15)) & M
        w18 = (w[2] + s1(w16)) & M
        w19 = (w[3] + s1(w17)) & M
        self.r[d] = [w16, w17, w18, w19]

    def i_sha256rnds2(self, d, s):
        # d = CDGH, s = ABEF, xmm0 = the two message+constant dwords; the result (ABEF) goes in d.
        cdgh, abef, wk = self.r[d], self.r[s], self.r['xmm0']
        a, b, e, f = abef[3], abef[2], abef[1], abef[0]
        c, dd, g, h = cdgh[3], cdgh[2], cdgh[1], cdgh[0]
        for i in range(2):
            ch = (e & f) ^ (~e & M & g)
            maj = (a & b) ^ (a & c) ^ (b & c)
            t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ch + wk[i]) & M
            t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + maj) & M
            h, g, f, e, dd, c, b, a = g, f, e, (dd + t1) & M, c, b, a, (t1 + t2) & M
        self.r[d] = [f, e, b, a]


def selftest():
    iv = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
    kb = struct.pack('<64I', *K)
    for nblocks in (1, 2, 5):
        msg = os.urandom(64 * nblocks - 9)
        padded = msg + b'\x80'
        padded += bytes((-len(padded) - 8) % 64) + struct.pack('>Q', len(msg) * 8)
        assert len(padded) % 64 == 0, len(padded)
        m = Model(iv, padded, kb)
        m.run(PROLOGUE)
        for _ in range(len(padded) // 64):
            m.run(block())
            m.rsi += 64
        m.run(EPILOGUE)
        got = bytes(m.mem['rdi'])
        want = hashlib.sha256(msg).digest()
        assert b''.join(struct.pack('>I', w) for w in struct.unpack('<8I', got)) == want, (nblocks, got.hex(), want.hex())


def fmt(row):
    op, *a = row
    return '\t' + op + ' ' + ', '.join(str(x) if not isinstance(x, int) else hex(x) if x > 9 else str(x) for x in a)


def generate():
    selftest()
    out = ['''// SHA-256 on the x86-64 SHA extensions, and its CPUID check (#488). Generated by
// tools/gen/gen_sha256_amd64.py (which checks the instruction list on a model against hashlib);
// tools/gen/gen_aes_hw.py turns it into selfhost/aes_hw.tin. Relocation-free, caller-saved
// registers only (rbx is saved by sha_hw_cpu), never r15 (the core context). Constant-time: no
// branch or address depends on the data or the hash state.
.intel_syntax noprefix
.text

// sha_hw_cpu() -> 1 when the CPU has SHA, SSSE3 and SSE4.1 (CPUID leaf 7 EBX bit 29, leaf 1 ECX
// bits 9 and 19), else 0.
.global sha_hw_cpu
.type sha_hw_cpu, @function
sha_hw_cpu:
	push rbx
	xor eax, eax
	cpuid
	cmp eax, 7
	jb 8f
	mov eax, 1
	cpuid
	mov r8d, ecx
	mov eax, 7
	xor ecx, ecx
	cpuid
	and r8d, 0x00080200
	cmp r8d, 0x00080200
	jne 8f
	bt ebx, 29
	jnc 8f
	mov eax, 1
	pop rbx
	ret
8:	xor eax, eax
	pop rbx
	ret
.size sha_hw_cpu, .-sha_hw_cpu

// hw_blocks(state rdi, data rsi, nblocks rdx, k rcx): compress nblocks >= 1 64-byte blocks at data
// into the eight 32-bit state words at state; k points at the 64 round constants.
.global hw_blocks
.type hw_blocks, @function
hw_blocks:
	test rdx, rdx
	jz 9f
	mov rax, 0x0405060700010203
	movq xmm10, rax
	mov rax, 0x0c0d0e0f08090a0b
	movq xmm3, rax
	punpcklqdq xmm10, xmm3''']
    out += [fmt(r) for r in PROLOGUE]
    out += ['1:']
    out += [fmt(r) for r in block()]
    out += ['\tadd rsi, 64', '\tdec rdx', '\tjnz 1b']
    out += [fmt(r) for r in EPILOGUE]
    out += ['9:\tret', '.size hw_blocks, .-hw_blocks', '']
    return '\n'.join(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'tools/gen/arch/sha256-amd64.S'
    result = generate()
    if args.check:
        assert path.read_text() == result, 'sha256-amd64.S is stale'
    else:
        path.write_text(result)
