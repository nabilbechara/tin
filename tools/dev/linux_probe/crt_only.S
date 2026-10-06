// crt_only.S: the same hand-written _start as start_*.S, but it records the entry state
// (initial sp, the rtld_fini register) into globals and then calls a C main (spcheck.c).
// Build: gcc -nostartfiles -o spcheck crt_only.S spcheck.c
    .data
    .globl tin_entry_sp
    .globl tin_entry_rtld_fini
tin_entry_sp:         .quad 0
tin_entry_rtld_fini:  .quad 0

    .text
    .globl _start
#if defined(__aarch64__)
    .type _start, %function
_start:
    mov     x29, #0
    mov     x30, #0
    adrp    x7, tin_entry_sp
    add     x7, x7, :lo12:tin_entry_sp
    mov     x8, sp
    str     x8, [x7]
    adrp    x7, tin_entry_rtld_fini
    add     x7, x7, :lo12:tin_entry_rtld_fini
    str     x0, [x7]
    mov     x5, x0
    ldr     x1, [sp]
    add     x2, sp, #8
    mov     x6, sp
    adrp    x0, :got:main
    ldr     x0, [x0, #:got_lo12:main]
    mov     x3, #0
    mov     x4, #0
    adrp    x16, :got:__libc_start_main
    ldr     x16, [x16, #:got_lo12:__libc_start_main]
    blr     x16
    brk     #0
    .size _start, .-_start
    .section .note.GNU-stack,"",%progbits
#elif defined(__x86_64__)
    .type _start, @function
_start:
    xor     %ebp, %ebp
    mov     %rsp, tin_entry_sp(%rip)
    mov     %rdx, tin_entry_rtld_fini(%rip)
    mov     %rdx, %r9
    pop     %rsi
    mov     %rsp, %rdx
    and     $-16, %rsp
    push    %rax
    push    %rsp
    xor     %r8d, %r8d
    xor     %ecx, %ecx
    mov     main@GOTPCREL(%rip), %rdi
    call    *__libc_start_main@GOTPCREL(%rip)
    hlt
    .size _start, .-_start
    .section .note.GNU-stack,"",@progbits
#else
#error unsupported arch
#endif
