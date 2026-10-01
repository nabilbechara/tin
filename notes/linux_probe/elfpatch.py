#!/usr/bin/env python3
"""elfpatch.py: in-place edits of an ELF64 little-endian file for the negative tests.

usage: elfpatch.py FILE OP ARG [OP ARG ...]
  droptag  0xTAG      rewrite dynamic entries with d_tag == TAG to DT_LOOS (0x60000000, ignored by ld.so)
  dropphdr TYPE       set p_type of every program header of that type to PT_NULL (0)
  phflags  TYPE FLAGS set p_flags of every program header of that type
  noshdr   -          zero e_shoff/e_shnum/e_shstrndx (section-header-less executable)
  hash1    -          rewrite the DT_HASH table in place to nbucket=1 with every symbol on one chain
"""
import struct, sys

PT_DYNAMIC = 2

def main():
    path = sys.argv[1]
    b = bytearray(open(path, 'rb').read())
    assert b[:4] == b'\x7fELF' and b[4] == 2 and b[5] == 1, 'need ELF64 LE'
    e_phoff, e_shoff = struct.unpack_from('<QQ', b, 0x20)
    e_phentsize, e_phnum = struct.unpack_from('<HH', b, 0x36)
    phdrs = [e_phoff + i * e_phentsize for i in range(e_phnum)]

    def phdr(off):
        return struct.unpack_from('<IIQQQQQQ', b, off)  # type flags offset vaddr paddr filesz memsz align

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        op = args[i]
        if op == 'droptag':
            tag = int(args[i + 1], 0); i += 2
            for off in phdrs:
                p = phdr(off)
                if p[0] != PT_DYNAMIC:
                    continue
                dyn_off, dyn_sz = p[2], p[5]
                n = 0
                for k in range(0, dyn_sz, 16):
                    d_tag, = struct.unpack_from('<q', b, dyn_off + k)
                    if d_tag == 0:
                        break
                    if d_tag == tag:
                        struct.pack_into('<q', b, dyn_off + k, 0x60000000)
                        n += 1
                print(f'droptag 0x{tag:x}: rewrote {n} entries')
        elif op == 'dropphdr':
            t = int(args[i + 1], 0); i += 2
            n = 0
            for off in phdrs:
                if phdr(off)[0] == t:
                    struct.pack_into('<I', b, off, 0); n += 1
            print(f'dropphdr 0x{t:x}: rewrote {n} headers')
        elif op == 'phflags':
            t = int(args[i + 1], 0); fl = int(args[i + 2], 0); i += 3
            n = 0
            for off in phdrs:
                if phdr(off)[0] == t:
                    struct.pack_into('<I', b, off + 4, fl); n += 1
            print(f'phflags 0x{t:x} -> {fl}: rewrote {n} headers')
        elif op == 'hash1':
            i += 2
            dyn = None
            for off in phdrs:
                p = phdr(off)
                if p[0] == PT_DYNAMIC:
                    dyn = p
            dyn_off, dyn_sz = dyn[2], dyn[5]
            hash_vaddr = None
            for k in range(0, dyn_sz, 16):
                d_tag, d_val = struct.unpack_from('<qQ', b, dyn_off + k)
                if d_tag == 4:
                    hash_vaddr = d_val
            assert hash_vaddr is not None, 'no DT_HASH'
            hoff = None
            for off in phdrs:
                p = phdr(off)
                if p[0] == 1 and p[3] <= hash_vaddr < p[3] + p[5]:
                    hoff = hash_vaddr - p[3] + p[2]
            nbucket, nchain = struct.unpack_from('<II', b, hoff)
            struct.pack_into('<II', b, hoff, 1, nchain)
            struct.pack_into('<I', b, hoff + 8, 1 if nchain > 1 else 0)          # bucket[0] -> symbol 1
            for sym in range(nchain):
                nxt = sym + 1 if 1 <= sym < nchain - 1 else 0
                struct.pack_into('<I', b, hoff + 12 + 4 * sym, nxt)             # chain[sym]
            print(f'hash1: DT_HASH at 0x{hash_vaddr:x} (file 0x{hoff:x}): nbucket {nbucket}->1, nchain {nchain}, chain 1->2->...->{nchain-1}->0')
        elif op == 'noshdr':
            i += 2
            struct.pack_into('<Q', b, 0x28, 0)
            struct.pack_into('<HH', b, 0x3C, 0, 0)
            print('noshdr: e_shoff=0 e_shnum=0 e_shstrndx=0')
        else:
            sys.exit('unknown op ' + op)
    open(path, 'wb').write(b)

main()
