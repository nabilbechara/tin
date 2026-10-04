// Strict Tin syscall leaves preserve x28 and all callee-saved registers.
.text
.macro LEAF name, number
.global \name
.type \name, %function
\name:
.endm
.macro RESULT name, number
mov x8, #\number
svc #0
cmn x0, #4095
b.cc 1f
neg x0, x0
cbz x28, 2f
str x0, [x28, #80]
2:
mov x0, #-1
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
mov x4, #0
mov x5, #0
RESULT rt_sys_recv, NR_RECVFROM
LEAF rt_sys_epoll_ctl, NR_EPOLL_CTL
RESULT rt_sys_epoll_ctl, NR_EPOLL_CTL
LEAF rt_sys_epoll_wait, NR_EPOLL_PWAIT
mov x4, #0
mov x5, #8
RESULT rt_sys_epoll_wait, NR_EPOLL_PWAIT
LEAF rt_sys_timerfd_settime, NR_TIMERFD_SETTIME
RESULT rt_sys_timerfd_settime, NR_TIMERFD_SETTIME
// The backend loads the shared vDSO function pointer into x2 before this body.
LEAF rt_sys_clock_gettime, NR_CLOCK_GETTIME
cbz x2, 3f
stp x0, x1, [sp, #-32]!
str x30, [sp, #16]
blr x2
mov w9, w0
ldr x30, [sp, #16]
ldp x0, x1, [sp], #32
cbnz w9, 3f
mov x0, #0
ret
3:
RESULT rt_sys_clock_gettime, NR_CLOCK_GETTIME
// clone(flags, stack, ptid, ctid, entry, arg): the child starts on the new stack with
// entry and arg stored at its top, no inherited frame and no Tin context, and leaves with exit.
LEAF rt_sys_clone, NR_CLONE
stp x4, x5, [x1, #-16]!
mov x4, x3
mov x3, #0
mov x8, #NR_CLONE
svc #0
cbz x0, 4f
cmn x0, #4095
b.cc 1f
neg x0, x0
cbz x28, 2f
str x0, [x28, #80]
2:
mov x0, #-1
1:
ret
4:
ldp x9, x0, [sp], #16
mov x28, #0
mov x29, #0
mov x30, #0
blr x9
mov x0, #0
mov x8, #NR_EXIT
svc #0
brk #0
.size rt_sys_clone, .-rt_sys_clone
