// start_amd64.S: the smallest crt-less dynamically linked Linux/x86-64 program.
//   _start -> __libc_start_main(main, argc, argv, 0, 0, rtld_fini, stack_end) -> main -> puts
// Every libc call is an indirect call through a GOT slot (call *sym@GOTPCREL(%rip)), never a PLT:
// the linker then emits R_X86_64_GLOB_DAT relocations in .rela.dyn, which is what Tin's ELF writer emits.
// Build: gcc -nostartfiles -o start start_amd64.S          (PIE, Debian default)
//        gcc -nostartfiles -no-pie -o start_nopie start_amd64.S
// Verify: ./start ; LD_DEBUG=bindings ./start 2>&1 | grep -E 'puts|__libc_start_main'
    .text
    .globl _start
    .type _start, @function
_start:
    xor     %ebp, %ebp              # terminate the frame-pointer chain
    mov     %rdx, %r9               # rtld_fini: ld.so passes _dl_fini in %rdx at entry
    pop     %rsi                    # argc   (at entry %rsp is 16-byte aligned and points at argc)
    mov     %rsp, %rdx              # argv
    and     $-16, %rsp              # realign
    push    %rax                    # padding: after the next push %rsp is 16-byte aligned at the call
    push    %rsp                    # stack_end (7th argument, passed on the stack)
    xor     %r8d, %r8d              # fini   (ignored by glibc >= 2.34, must be 0)
    xor     %ecx, %ecx              # init
    lea     main(%rip), %rdi        # main   (RIP-relative: fine for PIE and non-PIE)
    call    *__libc_start_main@GOTPCREL(%rip)   # never returns: calls exit(main(...))
    hlt
    .size _start, .-_start

    .globl main
    .type main, @function
main:
    sub     $8, %rsp                # entry: %rsp = 16n+8; now 16-byte aligned for the call
    lea     msg(%rip), %rdi
    call    *puts@GOTPCREL(%rip)
    xor     %eax, %eax
    add     $8, %rsp
    ret
    .size main, .-main

    .section .rodata
msg:
    .asciz "hello from hand-written _start (x86-64)"

    .section .note.GNU-stack,"",@progbits
