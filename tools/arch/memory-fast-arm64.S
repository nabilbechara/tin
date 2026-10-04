// Bounded memory leaves; caller-saved registers only, no context or TLS changes.
.text
.global memcpy
.type memcpy, %function
memcpy:
mov x3, x0
cbz x2, .Lret_memcpy
.Lforward_memcpy:
cmp x2, #64
b.ls .Lsmall_memcpy
ldp q0, q1, [x1]
ldp q2, q3, [x1, #32]
stp q0, q1, [x0]
stp q2, q3, [x0, #32]
add x0, x0, #64
add x1, x1, #64
sub x2, x2, #64
b .Lforward_memcpy
.Lsmall_memcpy:
cbz x2, .Lret_memcpy
add x4, x1, x2
add x5, x0, x2
cmp x2, #32
b.ls .L32_memcpy
ldp q0, q1, [x1]
ldp q2, q3, [x4, #-32]
stp q0, q1, [x0]
stp q2, q3, [x5, #-32]
b .Lret_memcpy
.L32_memcpy:
cmp x2, #16
b.lo .L16_memcpy
ldr q0, [x1]
ldur q1, [x4, #-16]
str q0, [x0]
stur q1, [x5, #-16]
b .Lret_memcpy
.L16_memcpy:
cmp x2, #8
b.lo .L8_memcpy
ldr x6, [x1]
ldur x7, [x4, #-8]
str x6, [x0]
stur x7, [x5, #-8]
b .Lret_memcpy
.L8_memcpy:
cmp x2, #4
b.lo .L4_memcpy
ldr w6, [x1]
ldur w7, [x4, #-4]
str w6, [x0]
stur w7, [x5, #-4]
b .Lret_memcpy
.L4_memcpy:
cmp x2, #2
b.lo .L2_memcpy
ldrh w6, [x1]
ldurh w7, [x4, #-2]
strh w6, [x0]
sturh w7, [x5, #-2]
b .Lret_memcpy
.L2_memcpy:
ldrb w6, [x1]
strb w6, [x0]
.Lret_memcpy:
mov x0, x3
ret
.size memcpy, .-memcpy
.global memmove
.type memmove, %function
memmove:
mov x3, x0
cbz x2, .Lret_memmove
cmp x2, #64
b.ls .Lsmall_memmove
sub x4, x0, x1
cmp x4, x2
b.hs .Lforward_memmove
add x0, x0, x2
add x1, x1, x2
.Lback_memmove:
sub x0, x0, #16
sub x1, x1, #16
ldr q0, [x1]
str q0, [x0]
subs x2, x2, #16
cmp x2, #16
b.hs .Lback_memmove
sub x0, x0, x2
sub x1, x1, x2
b .Lsmall_memmove
.Lforward_memmove:
cmp x2, #64
b.ls .Lsmall_memmove
ldp q0, q1, [x1]
ldp q2, q3, [x1, #32]
stp q0, q1, [x0]
stp q2, q3, [x0, #32]
add x0, x0, #64
add x1, x1, #64
sub x2, x2, #64
b .Lforward_memmove
.Lsmall_memmove:
cbz x2, .Lret_memmove
add x4, x1, x2
add x5, x0, x2
cmp x2, #32
b.ls .L32_memmove
ldp q0, q1, [x1]
ldp q2, q3, [x4, #-32]
stp q0, q1, [x0]
stp q2, q3, [x5, #-32]
b .Lret_memmove
.L32_memmove:
cmp x2, #16
b.lo .L16_memmove
ldr q0, [x1]
ldur q1, [x4, #-16]
str q0, [x0]
stur q1, [x5, #-16]
b .Lret_memmove
.L16_memmove:
cmp x2, #8
b.lo .L8_memmove
ldr x6, [x1]
ldur x7, [x4, #-8]
str x6, [x0]
stur x7, [x5, #-8]
b .Lret_memmove
.L8_memmove:
cmp x2, #4
b.lo .L4_memmove
ldr w6, [x1]
ldur w7, [x4, #-4]
str w6, [x0]
stur w7, [x5, #-4]
b .Lret_memmove
.L4_memmove:
cmp x2, #2
b.lo .L2_memmove
ldrh w6, [x1]
ldurh w7, [x4, #-2]
strh w6, [x0]
sturh w7, [x5, #-2]
b .Lret_memmove
.L2_memmove:
ldrb w6, [x1]
strb w6, [x0]
.Lret_memmove:
mov x0, x3
ret
.size memmove, .-memmove
.global memset
.type memset, %function
memset:
mov x3, x0
cbz x2, .Lret_memset
dup v0.16b, w1
.L64_memset:
cmp x2, #64
b.lo .Lsmall_memset
stp q0, q0, [x0]
stp q0, q0, [x0, #32]
add x0, x0, #64
sub x2, x2, #64
b .L64_memset
.Lsmall_memset:
cbz x2, .Lret_memset
add x4, x0, x2
cmp x2, #32
b.ls .L32_memset
stp q0, q0, [x0]
stp q0, q0, [x4, #-32]
b .Lret_memset
.L32_memset:
cmp x2, #16
b.lo .L16_memset
str q0, [x0]
stur q0, [x4, #-16]
b .Lret_memset
.L16_memset:
fmov x5, d0
cmp x2, #8
b.lo .L8_memset
str x5, [x0]
stur x5, [x4, #-8]
b .Lret_memset
.L8_memset:
cmp x2, #4
b.lo .L4_memset
str w5, [x0]
stur w5, [x4, #-4]
b .Lret_memset
.L4_memset:
cmp x2, #2
b.lo .L2_memset
strh w5, [x0]
sturh w5, [x4, #-2]
b .Lret_memset
.L2_memset:
strb w5, [x0]
.Lret_memset:
mov x0, x3
ret
.size memset, .-memset
.global memcmp
.type memcmp, %function
memcmp:
.L64_memcmp:
cmp x2, #64
b.lo .L16_memcmp
ldr q0, [x0, #0]
ldr q4, [x1, #0]
cmeq v0.16b, v0.16b, v4.16b
ldr q1, [x0, #16]
ldr q4, [x1, #16]
cmeq v1.16b, v1.16b, v4.16b
ldr q2, [x0, #32]
ldr q4, [x1, #32]
cmeq v2.16b, v2.16b, v4.16b
ldr q3, [x0, #48]
ldr q4, [x1, #48]
cmeq v3.16b, v3.16b, v4.16b
and v0.16b, v0.16b, v1.16b
and v2.16b, v2.16b, v3.16b
and v0.16b, v0.16b, v2.16b
shrn v0.8b, v0.8h, #4
fmov x4, d0
cmn x4, #1
b.ne .L16_memcmp
add x0, x0, #64
add x1, x1, #64
sub x2, x2, #64
b .L64_memcmp
.L16_memcmp:
cmp x2, #16
b.lo .Lbyte_memcmp
ldr q0, [x0]
ldr q4, [x1]
cmeq v0.16b, v0.16b, v4.16b
shrn v0.8b, v0.8h, #4
fmov x4, d0
cmn x4, #1
b.ne .Lfound_memcmp
add x0, x0, #16
add x1, x1, #16
sub x2, x2, #16
b .L16_memcmp
.Lfound_memcmp:
mvn x4, x4
rbit x4, x4
clz x4, x4
lsr x4, x4, #2
ldrb w5, [x0, x4]
ldrb w6, [x1, x4]
sub x0, x5, x6
ret
.Lbyte_memcmp:
cbz x2, .Lzero_memcmp
ldrb w5, [x0]
ldrb w6, [x1]
sub x4, x5, x6
cbnz x4, .Ldiff_memcmp
add x1, x1, #1
add x0, x0, #1
sub x2, x2, #1
b .Lbyte_memcmp
.Lzero_memcmp:
mov x0, #0
ret
.Ldiff_memcmp:
mov x0, x4
ret
.size memcmp, .-memcmp
.global memchr
.type memchr, %function
memchr:
dup v4.16b, w1
.L64_memchr:
cmp x2, #64
b.lo .L16_memchr
ldr q0, [x0, #0]
cmeq v0.16b, v0.16b, v4.16b
ldr q1, [x0, #16]
cmeq v1.16b, v1.16b, v4.16b
ldr q2, [x0, #32]
cmeq v2.16b, v2.16b, v4.16b
ldr q3, [x0, #48]
cmeq v3.16b, v3.16b, v4.16b
orr v0.16b, v0.16b, v1.16b
orr v2.16b, v2.16b, v3.16b
orr v0.16b, v0.16b, v2.16b
shrn v0.8b, v0.8h, #4
fmov x4, d0
cbnz x4, .L16_memchr
add x0, x0, #64
sub x2, x2, #64
b .L64_memchr
.L16_memchr:
cmp x2, #16
b.lo .Lbyte_memchr
ldr q0, [x0]
cmeq v0.16b, v0.16b, v4.16b
shrn v0.8b, v0.8h, #4
fmov x4, d0
cbnz x4, .Lfound_memchr
add x0, x0, #16
sub x2, x2, #16
b .L16_memchr
.Lfound_memchr:
rbit x4, x4
clz x4, x4
lsr x4, x4, #2
add x0, x0, x4
ret
.Lbyte_memchr:
cbz x2, .Lzero_memchr
ldrb w5, [x0]
and w6, w1, #255
cmp w5, w6
b.eq .Lret_memchr
add x0, x0, #1
sub x2, x2, #1
b .Lbyte_memchr
.Lzero_memchr:
mov x0, #0
ret
.Lret_memchr:
ret
.size memchr, .-memchr
