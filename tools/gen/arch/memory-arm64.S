// Bulk operations use caller-saved NEON registers and never access a partial chunk.
.text
.global mem_copy64
mem_copy64:
    cbz x2, 2f
1:
    ldp q0, q1, [x1]
    ldp q2, q3, [x1, #32]
    stp q0, q1, [x0]
    stp q2, q3, [x0, #32]
    add x0, x0, #64
    add x1, x1, #64
    subs x2, x2, #1
    b.ne 1b
2:
    ret
.global mem_fill64
mem_fill64:
    cbz x2, 2f
    dup v0.2d, x1
1:
    stp q0, q0, [x0]
    stp q0, q0, [x0, #32]
    add x0, x0, #64
    subs x2, x2, #1
    b.ne 1b
2:
    ret
