# Linux threads without libc (issue #125 design checkpoint)

This design is for the phase 5 cutover. Phase 3 keeps pthread-created cores and helpers
while libc DNS, environment and diagnostics remain reachable. macOS retains pthreads
and libSystem. Approval of this document precedes implementing the raw thread backend.

## Context and TLS

Tin reserves x28 on arm64 and r15 on amd64 for the core context. Task switches preserve
the existing saved-register layout and share that context within a core. Linux's
architecture TLS registers (tpidr_el0 and the fs base) serve a different purpose.
After removing every libc call, Tin needs neither register: globals and syscall error
state belong to the core context. Do not pass CLONE_SETTLS or initialize architecture
TLS. The child trampoline clears the inherited Tin context register before creating
its own context; the signal handler must never observe its parent's current task.

## Creation and child entry

Use clone with CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND | CLONE_THREAD |
CLONE_SYSVSEM | CLONE_PARENT_SETTID | CLONE_CHILD_CLEARTID (0x350f00). The kernel writes
the child's tid before the parent returns, and clears it on final thread exit. There
is no child exit signal. A record holds the tid, stack mapping, alternate-stack
mapping, entry and argument. Publish that record under a lock before starting it.

The compiler emits a leaf trampoline for each CPU. The parent gets clone's result
normally. In the child, execution continues on a new stack with no inherited frame;
load the record and entry from words placed at its aligned top, clear the Tin context
register and frame pointer, then call the normal Tin entry routine. Never return
through a frame on the old stack. A return from the entry calls the thread-only exit
syscall. Register assignments and clone argument order are recorded per architecture
in design/linux_abi.md and tested through repeated core creation and helper jobs.

## Stack lifetime and exit

Allocate an 8 MiB writable stack with a page-rounded guard below it, checking mmap and
mprotect. The parent owns the mapping. A child cannot unmap its own active stack.
The tid word is the completion fence: after the entry's completion counter changes,
the parent still waits for the kernel to clear the tid before freeing either stack.
Use FUTEX_WAIT on a nonzero tid, rechecking after EINTR/EAGAIN; a cleared word permits
reaping. Retain records for live helper threads, which run for the process lifetime.
Keep core heap/context lifetime unchanged; owner retirement remains #176.

The child uses exit, which ends only that thread. Normal program termination, panic
and the OOM path use exit_group, which ends the entire process. hearth's completion
counter continues to describe entry completion; it must not by itself authorize
unmapping. Reap finished records at the core join boundary and before further spawns.

## Masks, signal delivery and return

Before starting server cores or helpers, block SIGTERM and SIGINT on core 0. Children
inherit that mask; core 0's signalfd consumes those signals for graceful shutdown.
Leave synchronous SIGSEGV/SIGBUS unblocked so #175 still reports stack faults. Ignored
SIGPIPE stays process-wide. rt_sigprocmask, rt_sigaction and signalfd4 use the kernel's
8-byte signal set, not the 128-byte libc set. Check all setup errors.

Install kernel sigaction records directly: handler, flags, restorer, 8-byte mask.
Use SA_SIGINFO | SA_ONSTACK | SA_RESTORER for fault handlers on both CPUs. Emit a
restorer leaf with no frame or stack adjustment: arm64 loads syscall 139 into x8 and
executes svc; amd64 loads syscall 15 into rax and executes syscall. Both perform
rt_sigreturn from the kernel's original signal frame. The design deliberately supplies
its own restorer on arm64 as well, although Linux can provide its vDSO trampoline.

Every thread installs its own checked alternate stack before user initializers run.
Clone does not provide an inherited alternate stack for a CLONE_VM child. Allocate
the existing altStackSize from a dedicated mapping, store it in the parent-owned
record, and free it only after tid clearing. Core 0 retains its alternate stack until
process exit. Fault reporting remains static writes followed by exit_group.

## Acceptance

Both native Linux jobs must check repeated returning cores, child-only exit, helper
file jobs and late completions, independent contexts and syscall errors, mask
inheritance, signalfd shutdown, signal handler return, and fault reports on each
thread's alternate stack. Existing task-swap, panic recovery, deadline and lifetime
checks stay required. Static ELF assertions and scratch/Alpine execution cover the
final environment; Linux CPU/HTTP comparison tables cover both architectures.

Kernel references: [clone flags](https://github.com/torvalds/linux/blob/master/include/uapi/linux/sched.h),
[arm64 signal setup](https://github.com/torvalds/linux/blob/master/arch/arm64/kernel/signal.c),
[amd64 signal ABI](https://github.com/torvalds/linux/blob/master/arch/x86/include/uapi/asm/signal.h).
