// nosize_fn.S: three tiny functions that differ only in their ELF symbol attributes,
// to see which ones dladdr() can name on Linux (st_size matters there, type too).
#if defined(__aarch64__)
    .text
    .globl nosize_fn
    .type nosize_fn, %function
nosize_fn:
    nop
    nop
    nop
    ret
    // deliberately no .size

    .globl sized_fn
    .type sized_fn, %function
sized_fn:
    nop
    nop
    nop
    ret
    .size sized_fn, .-sized_fn

    .globl notype_fn
notype_fn:
    nop
    nop
    nop
    ret
    .size notype_fn, .-notype_fn
    .section .note.GNU-stack,"",%progbits
#elif defined(__x86_64__)
    .text
    .globl nosize_fn
    .type nosize_fn, @function
nosize_fn:
    nop
    nop
    nop
    nop
    ret
    // deliberately no .size

    .globl sized_fn
    .type sized_fn, @function
sized_fn:
    nop
    nop
    nop
    nop
    ret
    .size sized_fn, .-sized_fn

    .globl notype_fn
notype_fn:
    nop
    nop
    nop
    nop
    ret
    .size notype_fn, .-notype_fn
    .section .note.GNU-stack,"",@progbits
#else
#error unsupported arch
#endif
