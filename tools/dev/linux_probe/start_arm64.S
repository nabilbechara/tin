// start_arm64.S: the smallest crt-less dynamically linked Linux/aarch64 program.
//   _start -> __libc_start_main(main, argc, argv, 0, 0, rtld_fini, stack_end) -> main -> puts
// Every libc call goes through a GOT slot (adrp/ldr/blr), never a PLT: the linker then emits
// R_AARCH64_GLOB_DAT relocations in .rela.dyn, which is exactly what Tin's ELF writer will emit.
// Build: gcc -nostartfiles -o start start_arm64.S          (PIE, Debian default)
//        gcc -nostartfiles -no-pie -o start_nopie start_arm64.S
// Verify: ./start ; LD_DEBUG=bindings ./start 2>&1 | grep -E 'puts|__libc_start_main'
    .text
    .globl _start
    .type _start, %function
_start:
    mov     x29, #0                 // terminate the frame-pointer chain
    mov     x30, #0
    mov     x5, x0                  // rtld_fini: ld.so passes _dl_fini in x0 at entry
    ldr     x1, [sp]                // argc   (sp is 16-byte aligned here, [sp] = argc)
    add     x2, sp, #8              // argv   (envp = argv + argc + 1, found by libc)
    mov     x6, sp                  // stack_end
    adr     x0, main                // main   (PC-relative: fine for PIE and non-PIE)
    mov     x3, #0                  // init   (ignored by glibc >= 2.34, must be 0)
    mov     x4, #0                  // fini
    adrp    x16, :got:__libc_start_main
    ldr     x16, [x16, #:got_lo12:__libc_start_main]
    blr     x16                     // never returns: calls exit(main(...))
    brk     #0
    .size _start, .-_start

    .globl main
    .type main, %function
main:
    stp     x29, x30, [sp, #-16]!
    mov     x29, sp
    adrp    x0, msg
    add     x0, x0, :lo12:msg
    adrp    x16, :got:puts
    ldr     x16, [x16, #:got_lo12:puts]
    blr     x16
    mov     w0, #0
    ldp     x29, x30, [sp], #16
    ret
    .size main, .-main

    .section .rodata
msg:
    .asciz "hello from hand-written _start (aarch64)"

    .section .note.GNU-stack,"",%progbits
