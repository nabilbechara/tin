// Strict Tin syscall leaves preserve r15 and all callee-saved registers.
.text
.macro LEAF name, number
.global \name
.type \name, @function
\name:
.endm
.macro RESULT name, number
mov $\number, %eax
syscall
cmp $-4095, %rax
jb 1f
neg %rax
test %r15, %r15
jz 2f
mov %rax, 80(%r15)
2:
mov $-1, %rax
1:
ret
.size \name, .-\name
.endm
LEAF rt_sys_read, NR_READ
RESULT rt_sys_read, NR_READ
LEAF rt_sys_write, NR_WRITE
RESULT rt_sys_write, NR_WRITE
LEAF rt_sys_close, NR_CLOSE
RESULT rt_sys_close, NR_CLOSE
LEAF rt_sys_fcntl, NR_FCNTL
RESULT rt_sys_fcntl, NR_FCNTL
LEAF rt_sys_accept, NR_ACCEPT
RESULT rt_sys_accept, NR_ACCEPT
LEAF rt_sys_recv, NR_RECVFROM
mov %rcx, %r10
xor %r8d, %r8d
xor %r9d, %r9d
RESULT rt_sys_recv, NR_RECVFROM
LEAF rt_sys_epoll_ctl, NR_EPOLL_CTL
mov %rcx, %r10
RESULT rt_sys_epoll_ctl, NR_EPOLL_CTL
LEAF rt_sys_epoll_wait, NR_EPOLL_PWAIT
mov %rcx, %r10
xor %r8d, %r8d
mov $8, %r9d
RESULT rt_sys_epoll_wait, NR_EPOLL_PWAIT
LEAF rt_sys_timerfd_settime, NR_TIMERFD_SETTIME
mov %rcx, %r10
RESULT rt_sys_timerfd_settime, NR_TIMERFD_SETTIME
// The backend loads the shared vDSO function pointer into rdx before this body.
LEAF rt_sys_clock_gettime, NR_CLOCK_GETTIME
test %rdx, %rdx
jz 3f
sub $24, %rsp
mov %rdi, 0(%rsp)
mov %rsi, 8(%rsp)
call *%rdx
mov 0(%rsp), %rdi
mov 8(%rsp), %rsi
add $24, %rsp
test %eax, %eax
jnz 3f
xor %eax, %eax
ret
3:
RESULT rt_sys_clock_gettime, NR_CLOCK_GETTIME
// clone(flags, stack, ptid, ctid, entry, arg): the child starts on the new stack with
// entry and arg stored at its top, no inherited frame and no Tin context, and leaves with exit.
LEAF rt_sys_clone, NR_CLONE
sub $16, %rsi
mov %r8, 0(%rsi)
mov %r9, 8(%rsi)
mov %rcx, %r10
xor %r8d, %r8d
mov $NR_CLONE, %eax
syscall
test %rax, %rax
jz 4f
cmp $-4095, %rax
jb 1f
neg %rax
test %r15, %r15
jz 2f
mov %rax, 80(%r15)
2:
mov $-1, %rax
1:
ret
4:
pop %rax
pop %rdi
xor %ebp, %ebp
xor %r15d, %r15d
call *%rax
xor %edi, %edi
mov $NR_EXIT, %eax
syscall
hlt
.size rt_sys_clone, .-rt_sys_clone
