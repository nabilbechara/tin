# Patch: per-CPU parts of the Linux runtime and anvil

The compiler loads `NAME_linux_amd64.tin` (new, mine) or `NAME_linux_arm64.tin` next to
`NAME_linux.tin`. Two things in the shared Linux files depend on the CPU and must move into the
per-arch files, or the amd64 build gets duplicate definitions. Verified with a patched copy of
lib/ (via TIN_ROOT): tests/v2 pass on linux-amd64 except as listed in `notes/x64_progress.md`.

## 1. `lib/runtime_linux.tin`: remove `rt_stat_mode`

Delete this (st_mode is at 16 on arm64 but at 24 on x86-64; st_size, st_mtim, st_dev, st_ino
are the same on both and stay):

```go
// struct stat on arm64 Linux (st_mode is a u32 at 16; the other fields match x86-64).
func rt_stat_mode(st i64) i64 {
	return __ld(st+16, 2) & 0xffffffff
}
```

and put in its place a one-line comment:

```go
// struct stat: st_mode's offset differs per CPU (runtime_linux_<arch>.tin); the rest is shared.
```

## 2. New file `lib/runtime_linux_arm64.tin`

```go
// arm64 part of the Linux runtime: the struct layouts that differ from x86-64.

const TARGET_X64 = false

// struct stat on arm64 Linux: st_mode is a u32 at 16 (24 on x86-64).
func rt_stat_mode(st i64) i64 {
	return __ld(st+16, 2) & 0xffffffff
}
```

(`lib/runtime_linux_amd64.tin`, already written, has `TARGET_X64 = true` and the offset-24 version.)

## 3. `lib/runtime_darwin.tin`: add the constant

After `const TARGET_LINUX = false` add:

```go
const TARGET_X64 = false
```

## 4. `lib/anvil_linux.tin`: remove the epoll_event layout

`struct epoll_event` is 16 bytes on arm64 (data at 8) but packed to 12 bytes on x86-64 (data at
4), so `evSize`, `ep_set` and `ev_fd` move to the per-arch files. Delete these three pieces:

```go
// struct epoll_event is 16 bytes on arm64: u32 events, padding, u64 data.
const evSize = 16
```

```go
func ep_set(op i64, fd i64, events i64) {
	change[0] = events
	change[1] = fd
	epoll_ctl(kq, op, fd, change)
}
```

```go
func ev_fd(i i64) i64 {
	return (evs + i*evSize + 8)[0]
}
```

and leave a comment where the constant was:

```go
// struct epoll_event's size and data offset differ per CPU: see anvil_linux_<arch>.tin.
```

## 5. New file `lib/anvil_linux_arm64.tin`

```go
// anvil's epoll event layout on arm64: struct epoll_event is 16 bytes (u32 events,
// padding, u64 data at 8), where x86-64 packs it to 12.
package anvil

const evSize = 16

func ep_set(op i64, fd i64, events i64) {
	change[0] = events
	change[1] = fd
	epoll_ctl(kq, op, fd, change)
}

func ev_fd(i i64) i64 {
	return (evs + i*evSize + 8)[0]
}
```

(`lib/anvil_linux_amd64.tin`, already written, has the 12-byte layout.)

## 6. `selfhost/main.tin`: `-S` for the x86-64 target (optional)

`print_asm()` renders the arm64 instruction list; with `-target linux-amd64` the list holds
x86-64 instructions. In `main`, replace

```go
    if asm_only {
        write_all(1, print_asm());
```

with

```go
    if asm_only && tgt_x64 {
        write_all(1, print_asm_x64());
    } else if asm_only {
        write_all(1, print_asm());
```

(`print_asm_x64` is in `selfhost/gen_x64.tin`: Intel syntax with symbolic labels.)
