// Tin function ABI: number, then six arguments. syscall clobbers rcx/r11, preserves r15.
.text
.global linux_raw
linux_raw:
    mov %rdi, %rax
    mov %rsi, %rdi
    mov %rdx, %rsi
    mov %rcx, %rdx
    mov %r8, %r10
    mov %r9, %r8
    mov 8(%rsp), %r9
    syscall
    ret
.global linux_restorer
linux_restorer:
    mov $15, %rax
    syscall
