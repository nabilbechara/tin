// Bounded memory leaves; caller-saved registers only, no context or TLS changes.
.text
.global memcpy
.type memcpy, @function
memcpy:
mov %rdi, %rax
test %rdx, %rdx
jz .Lret_memcpy
.Lforward_memcpy:
cmp $128, %rdx
jbe .Lsmall_memcpy
mov %rdx, %rcx
rep movsb
ret
.Lsmall_memcpy:
cmp $64, %rdx
jbe .L64_memcpy
movdqu 0(%rsi), %xmm0
movdqu 16(%rsi), %xmm1
movdqu 32(%rsi), %xmm2
movdqu 48(%rsi), %xmm3
movdqu -64(%rsi,%rdx), %xmm4
movdqu -48(%rsi,%rdx), %xmm5
movdqu -32(%rsi,%rdx), %xmm6
movdqu -16(%rsi,%rdx), %xmm7
movdqu %xmm0, 0(%rdi)
movdqu %xmm1, 16(%rdi)
movdqu %xmm2, 32(%rdi)
movdqu %xmm3, 48(%rdi)
movdqu %xmm4, -64(%rdi,%rdx)
movdqu %xmm5, -48(%rdi,%rdx)
movdqu %xmm6, -32(%rdi,%rdx)
movdqu %xmm7, -16(%rdi,%rdx)
jmp .Lret_memcpy
.L64_memcpy:
cmp $32, %rdx
jbe .L32_memcpy
movdqu (%rsi), %xmm0
movdqu 16(%rsi), %xmm1
movdqu -32(%rsi,%rdx), %xmm2
movdqu -16(%rsi,%rdx), %xmm3
movdqu %xmm0, (%rdi)
movdqu %xmm1, 16(%rdi)
movdqu %xmm2, -32(%rdi,%rdx)
movdqu %xmm3, -16(%rdi,%rdx)
jmp .Lret_memcpy
.L32_memcpy:
cmp $16, %rdx
jb .L16_memcpy
movdqu (%rsi), %xmm0
movdqu -16(%rsi,%rdx), %xmm1
movdqu %xmm0, (%rdi)
movdqu %xmm1, -16(%rdi,%rdx)
jmp .Lret_memcpy
.L16_memcpy:
cmp $8, %rdx
jb .L8_memcpy
movq (%rsi), %rcx
movq -8(%rsi,%rdx), %r8
movq %rcx, (%rdi)
movq %r8, -8(%rdi,%rdx)
jmp .Lret_memcpy
.L8_memcpy:
cmp $4, %rdx
jb .L4_memcpy
movl (%rsi), %ecx
movl -4(%rsi,%rdx), %r8d
movl %ecx, (%rdi)
movl %r8d, -4(%rdi,%rdx)
jmp .Lret_memcpy
.L4_memcpy:
cmp $2, %rdx
jb .L2_memcpy
movw (%rsi), %cx
movw -2(%rsi,%rdx), %r8w
movw %cx, (%rdi)
movw %r8w, -2(%rdi,%rdx)
jmp .Lret_memcpy
.L2_memcpy:
movb (%rsi), %cl
movb %cl, (%rdi)
.Lret_memcpy:
ret
.size memcpy, .-memcpy
.global memmove
.type memmove, @function
memmove:
mov %rdi, %rax
test %rdx, %rdx
jz .Lret_memmove
cmp $128, %rdx
jbe .Lsmall_memmove
mov %rdi, %rcx
sub %rsi, %rcx
cmp %rdx, %rcx
jae .Lforward_memmove
lea -1(%rdi,%rdx), %rdi
lea -1(%rsi,%rdx), %rsi
mov %rdx, %rcx
std
rep movsb
cld
ret
.Lforward_memmove:
cmp $128, %rdx
jbe .Lsmall_memmove
mov %rdx, %rcx
rep movsb
ret
.Lsmall_memmove:
cmp $64, %rdx
jbe .L64_memmove
movdqu 0(%rsi), %xmm0
movdqu 16(%rsi), %xmm1
movdqu 32(%rsi), %xmm2
movdqu 48(%rsi), %xmm3
movdqu -64(%rsi,%rdx), %xmm4
movdqu -48(%rsi,%rdx), %xmm5
movdqu -32(%rsi,%rdx), %xmm6
movdqu -16(%rsi,%rdx), %xmm7
movdqu %xmm0, 0(%rdi)
movdqu %xmm1, 16(%rdi)
movdqu %xmm2, 32(%rdi)
movdqu %xmm3, 48(%rdi)
movdqu %xmm4, -64(%rdi,%rdx)
movdqu %xmm5, -48(%rdi,%rdx)
movdqu %xmm6, -32(%rdi,%rdx)
movdqu %xmm7, -16(%rdi,%rdx)
jmp .Lret_memmove
.L64_memmove:
cmp $32, %rdx
jbe .L32_memmove
movdqu (%rsi), %xmm0
movdqu 16(%rsi), %xmm1
movdqu -32(%rsi,%rdx), %xmm2
movdqu -16(%rsi,%rdx), %xmm3
movdqu %xmm0, (%rdi)
movdqu %xmm1, 16(%rdi)
movdqu %xmm2, -32(%rdi,%rdx)
movdqu %xmm3, -16(%rdi,%rdx)
jmp .Lret_memmove
.L32_memmove:
cmp $16, %rdx
jb .L16_memmove
movdqu (%rsi), %xmm0
movdqu -16(%rsi,%rdx), %xmm1
movdqu %xmm0, (%rdi)
movdqu %xmm1, -16(%rdi,%rdx)
jmp .Lret_memmove
.L16_memmove:
cmp $8, %rdx
jb .L8_memmove
movq (%rsi), %rcx
movq -8(%rsi,%rdx), %r8
movq %rcx, (%rdi)
movq %r8, -8(%rdi,%rdx)
jmp .Lret_memmove
.L8_memmove:
cmp $4, %rdx
jb .L4_memmove
movl (%rsi), %ecx
movl -4(%rsi,%rdx), %r8d
movl %ecx, (%rdi)
movl %r8d, -4(%rdi,%rdx)
jmp .Lret_memmove
.L4_memmove:
cmp $2, %rdx
jb .L2_memmove
movw (%rsi), %cx
movw -2(%rsi,%rdx), %r8w
movw %cx, (%rdi)
movw %r8w, -2(%rdi,%rdx)
jmp .Lret_memmove
.L2_memmove:
movb (%rsi), %cl
movb %cl, (%rdi)
.Lret_memmove:
ret
.size memmove, .-memmove
.global memset
.type memset, @function
memset:
mov %rdi, %r8
mov %esi, %eax
test %rdx, %rdx
jz .Lret_memset
cmp $64, %rdx
jbe .Lsmall_memset
mov %rdx, %rcx
rep stosb
jmp .Lret_memset
.Lsmall_memset:
movzbl %al, %eax
imul $0x01010101, %eax, %eax
movd %eax, %xmm0
pshufd $0, %xmm0, %xmm0
cmp $32, %rdx
jbe .L32_memset
movdqu %xmm0, (%rdi)
movdqu %xmm0, 16(%rdi)
movdqu %xmm0, -32(%rdi,%rdx)
movdqu %xmm0, -16(%rdi,%rdx)
jmp .Lret_memset
.L32_memset:
cmp $16, %rdx
jb .L16_memset
movdqu %xmm0, (%rdi)
movdqu %xmm0, -16(%rdi,%rdx)
jmp .Lret_memset
.L16_memset:
movq %xmm0, %rax
cmp $8, %rdx
jb .L8_memset
movq %rax, (%rdi)
movq %rax, -8(%rdi,%rdx)
jmp .Lret_memset
.L8_memset:
cmp $4, %rdx
jb .L4_memset
movl %eax, (%rdi)
movl %eax, -4(%rdi,%rdx)
jmp .Lret_memset
.L4_memset:
cmp $2, %rdx
jb .L2_memset
movw %ax, (%rdi)
movw %ax, -2(%rdi,%rdx)
jmp .Lret_memset
.L2_memset:
movb %al, (%rdi)
.Lret_memset:
mov %r8, %rax
ret
.size memset, .-memset
.global memcmp
.type memcmp, @function
memcmp:
.L64_memcmp:
cmp $64, %rdx
jb .L16_memcmp
movdqu 0(%rdi), %xmm0
movdqu 0(%rsi), %xmm4
pcmpeqb %xmm4, %xmm0
movdqu 16(%rdi), %xmm1
movdqu 16(%rsi), %xmm4
pcmpeqb %xmm4, %xmm1
movdqu 32(%rdi), %xmm2
movdqu 32(%rsi), %xmm4
pcmpeqb %xmm4, %xmm2
movdqu 48(%rdi), %xmm3
movdqu 48(%rsi), %xmm4
pcmpeqb %xmm4, %xmm3
pand %xmm1, %xmm0
pand %xmm3, %xmm2
pand %xmm2, %xmm0
pmovmskb %xmm0, %ecx
cmp $65535, %ecx
jne .L16_memcmp
add $64, %rdi
add $64, %rsi
sub $64, %rdx
jmp .L64_memcmp
.L16_memcmp:
cmp $16, %rdx
jb .Lbyte_memcmp
movdqu (%rdi), %xmm0
movdqu (%rsi), %xmm4
pcmpeqb %xmm4, %xmm0
pmovmskb %xmm0, %ecx
cmp $65535, %ecx
jne .Lfound_memcmp
add $16, %rdi
add $16, %rsi
sub $16, %rdx
jmp .L16_memcmp
.Lfound_memcmp:
xor $65535, %ecx
bsf %ecx, %ecx
movzbl (%rdi,%rcx), %eax
movzbl (%rsi,%rcx), %r8d
sub %r8d, %eax
movslq %eax, %rax
ret
.Lbyte_memcmp:
test %rdx, %rdx
jz .Lzero_memcmp
movzbl (%rdi), %eax
movzbl (%rsi), %ecx
sub %ecx, %eax
jnz .Ldiff_memcmp
inc %rsi
inc %rdi
dec %rdx
jmp .Lbyte_memcmp
.Lzero_memcmp:
xor %eax, %eax
ret
.Ldiff_memcmp:
movslq %eax, %rax
ret
.size memcmp, .-memcmp
.global memchr
.type memchr, @function
memchr:
movd %esi, %xmm4
punpcklbw %xmm4, %xmm4
punpcklwd %xmm4, %xmm4
pshufd $0, %xmm4, %xmm4
.L64_memchr:
cmp $64, %rdx
jb .L16_memchr
movdqu 0(%rdi), %xmm0
pcmpeqb %xmm4, %xmm0
movdqu 16(%rdi), %xmm1
pcmpeqb %xmm4, %xmm1
movdqu 32(%rdi), %xmm2
pcmpeqb %xmm4, %xmm2
movdqu 48(%rdi), %xmm3
pcmpeqb %xmm4, %xmm3
por %xmm1, %xmm0
por %xmm3, %xmm2
por %xmm2, %xmm0
pmovmskb %xmm0, %ecx
test %ecx, %ecx
jnz .L16_memchr
add $64, %rdi
sub $64, %rdx
jmp .L64_memchr
.L16_memchr:
cmp $16, %rdx
jb .Lbyte_memchr
movdqu (%rdi), %xmm0
pcmpeqb %xmm4, %xmm0
pmovmskb %xmm0, %ecx
test %ecx, %ecx
jnz .Lfound_memchr
add $16, %rdi
sub $16, %rdx
jmp .L16_memchr
.Lfound_memchr:
bsf %ecx, %ecx
lea (%rdi,%rcx), %rax
ret
.Lbyte_memchr:
test %rdx, %rdx
jz .Lzero_memchr
movzbl (%rdi), %eax
cmp %sil, %al
je .Lret_memchr
inc %rdi
dec %rdx
jmp .Lbyte_memchr
.Lzero_memchr:
xor %eax, %eax
ret
.Lret_memchr:
mov %rdi, %rax
ret
.size memchr, .-memchr
