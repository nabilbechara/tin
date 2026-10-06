// Tin function ABI: number, then six arguments. The context register x28 is preserved.
.text
.global linux_raw
linux_raw:
    mov x8, x0
    mov x0, x1
    mov x1, x2
    mov x2, x3
    mov x3, x4
    mov x4, x5
    mov x5, x6
    svc #0
    ret
.global linux_restorer
linux_restorer:
    mov x8, #139
    svc #0
