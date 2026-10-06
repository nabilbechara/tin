// REP MOVSB/STOSB handle complete 64-byte chunks; DF is clear under the ABI.
.text
.global mem_copy64
mem_copy64:
    mov %rdx, %rcx
    shl $6, %rcx
    rep movsb
    ret
.global mem_fill64
mem_fill64:
    mov %rsi, %rax
    mov %rdx, %rcx
    shl $6, %rcx
    rep stosb
    ret
