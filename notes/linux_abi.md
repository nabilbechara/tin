# Linux ABI reference for the Tin port (glibc, dynamically linked)

Every number in this document was produced by compiling and running the C probes in
`notes/linux_probe/` (sources) and reading their raw outputs in `notes/linux_probe/out/`:

| column | environment | glibc | gcc / ld | kernel page size |
|---|---|---|---|---|
| darwin-arm64 | this Mac, macOS 14.6, Apple clang 16 | libSystem | — | 16384 |
| linux-arm64 | `golang:1.27` (Debian 13 trixie), Docker native arm64 | **2.41** (Debian 2.41-12+deb13u4) | gcc 14.2, ld 2.44 | 4096 |
| linux-amd64 | `golang:1.27 --platform linux/amd64` (emulated) | **2.41** | gcc 14.2, ld 2.44 | 4096 |
| cross-check | `debian:bookworm-slim` + gcc (both arches) | **2.36** (2.36-9+deb12u14) | gcc 12.2, ld 2.40 | 4096 |
| cross-check | `ubuntu:20.04` + gcc (both arches) | **2.31** | gcc 9.4 | 4096 |

Constants and struct layouts were identical on glibc 2.36 and 2.41 (`diff` of `consts.txt`/`structs.txt`: zero lines),
so the Linux columns below hold for both. Where 2.31 differs (`stat`, `pthread_create` location) it is called out.
Linux kernel in all containers: 6.10.14-linuxkit. The Mac ran Docker 27.3.1 (cgroup v2).

Rerun everything with:

```sh
cd notes/linux_probe
docker run --rm --platform linux/arm64 -v "$PWD":/p -w /p golang:1.27 sh run_all.sh   # -> out/linux-arm64-glibc2.41/
docker run --rm --platform linux/amd64 -v "$PWD":/p -w /p golang:1.27 sh run_all.sh   # -> out/linux-amd64-glibc2.41/
docker run --rm --platform linux/arm64 -v "$PWD":/p -w /p golang:1.27 sh bindings.sh  # symbol-version experiments
cc -o /tmp/consts consts.c && /tmp/consts > out/darwin-arm64/consts.txt                # darwin column
```

(`--platform` is mandatory: once both variants of `golang:1.27` are pulled, the bare tag resolves to amd64.)

---

## 0. What will bite the port (read first)

1. **`struct sockaddr_in` has no `sin_len` on Linux.** `wire.tin` writes `sa[0]=16, sa[1]=2` (BSD layout); on Linux
   `sin_family` is a 16-bit field at offset 0, so that buffer means family 0x0210 and `bind()` fails with
   `EAFNOSUPPORT` (probed). Write `sa[0]=2, sa[1]=0`. Same for `getsockname`/`accept` results: family is `u16@0`.
2. **`struct addrinfo` swaps `ai_addr` and `ai_canonname`.** darwin: `ai_canonname@24`, `ai_addr@32`.
   Linux: `ai_addr@24`, `ai_canonname@32`. `wire.tin` reads `(ai+32)[0]` as the sockaddr pointer; on Linux that is
   the canonname pointer (NULL in the probe). `ai_family@4`, `ai_socktype@8`, `ai_addrlen@16`, `ai_next@40` are the same.
3. **`struct stat` is completely different and differs between the two Linux arches.** `quarry.tin` uses
   `stMode=4 (2 bytes), stSize=96, stMtime=48`. Linux: `st_size@48` (both), `st_mtim@88` (both),
   `st_mode@16` (arm64) vs `st_mode@24` (amd64), 4 bytes; `sizeof` 128 (arm64) vs 144 (amd64). `st_dev` is 8 bytes.
4. **`struct dirent` has no `d_namlen` on Linux.** darwin `d_namlen@18, d_type@20, d_name@21`;
   Linux `d_reclen@16, d_type@18, d_name@19` (`sizeof` 280, `d_name[256]`). Name length = `strlen(d_name)`
   (probed; `d_reclen` is padded to 8 so it is not the length). `selfhost/main.tin` uses `ent + 21` too.
5. **Every socket option number changes**: `SOL_SOCKET` 0xffff -> **1**, `SO_REUSEADDR` 4 -> **2**, `SO_ERROR`
   0x1007 -> **4**, `SO_RCVTIMEO` 0x1006 -> **20**, `SO_SNDTIMEO` 0x1005 -> **21**, `SO_KEEPALIVE` 8 -> **9**,
   `SO_REUSEPORT` 0x200 -> **15**. `SO_NOSIGPIPE` (0x1022) does not exist: use `send(..., MSG_NOSIGNAL=0x4000)`
   or `signal(SIGPIPE=13, SIG_IGN=1)` (anvil already does the latter; probed: write to a dead peer then returns
   `EPIPE=32`). `setsockopt(fd, 0xffff, ...)` on Linux fails with `ENOPROTOOPT`/`EAFNOSUPPORT`.
   `IPPROTO_TCP=6`, `TCP_NODELAY=1`, `AF_INET=2`, `SOCK_STREAM=1` are unchanged.
6. **`O_NONBLOCK` is 0x800, not 4.** `fcntl(fd, F_SETFL=4, 4)` as in anvil/relay/wire sets nothing useful on Linux
   (probed: `F_GETFL` stays 0). `O_CREAT=0x40`, `O_TRUNC=0x200`, `O_APPEND=0x400`, `O_EXCL=0x80`,
   `O_CLOEXEC=0x80000`; so flume's `0x601` becomes **0x241** and quarry's `0x209` becomes **0x441**.
   `O_DIRECTORY`/`O_NOFOLLOW`/`O_DIRECT`/`O_TMPFILE` even differ between arm64 and amd64 Linux.
7. **`EAGAIN` is 11, not 35** (anvil's `errno()==35`). Most network errnos move: `ECONNREFUSED` 61 -> 111,
   `ETIMEDOUT` 60 -> 110, `EINPROGRESS` 36 -> 115, `ECONNRESET` 54 -> 104, `EADDRINUSE` 48 -> 98,
   `ENOTEMPTY` 66 -> 39, `ENAMETOOLONG` 63 -> 36. `ENOENT=2 EINTR=4 EEXIST=17 ENOTDIR=20 EISDIR=21 EINVAL=22
   EMFILE=24 ENFILE=23 EPIPE=32` are unchanged. errno lives at `*__errno_location()` (int), not `*__error()`.
8. **`sysconf(58)` is not the CPU count on Linux** (`_SC_NPROCESSORS_ONLN` = **84**; 58 is something else).
   And even `_SC_NPROCESSORS_ONLN` ignores containers: with `--cpuset-cpus=0,1` it still returned 11 (probed).
   `hearth.Cores()` must use `sched_getaffinity` + `/sys/fs/cgroup/cpu.max` (section 5).
9. **`clock_gettime_nsec_np` does not exist**: `clock_gettime(clk, &timespec)` with `CLOCK_REALTIME=0`,
   `CLOCK_MONOTONIC=1` (darwin 6), `CLOCK_MONOTONIC_RAW=4`, `CLOCK_BOOTTIME=7`. There is no `CLOCK_UPTIME_RAW` (8 on
   darwin = tide's `Now()`/crucible's clock): use `CLOCK_MONOTONIC` (1) or `CLOCK_BOOTTIME` (7).
10. **Symbol versioning decides semantics on x86-64.** An ELF without `DT_VERSYM`/`DT_VERNEED` runs fine (probed on
    2.31/2.36/2.41), but unversioned references bind to the **oldest** version of each symbol (glibc rule quoted in
    4.6). On x86-64 that means `realpath@GLIBC_2.2.5` (returns NULL when `resolved==NULL` - probed), the SVID
    `exp/log/pow/fmod/hypot@GLIBC_2.2.5`, `memcpy@GLIBC_2.2.5`. On arm64 the oldest version is GLIBC_2.17
    everywhere, so nothing changes. Either emit version info (section 4.7, ~100 bytes) or never rely on post-2.2.5
    semantics (Tin's `realpath(raw, real)` with a buffer is fine).
11. **`dladdr` needs a hash table and `st_size`.** Function names for `rt_backtrace` come only from `.dynsym`
    entries that are `STB_GLOBAL`/`STB_WEAK` **and** reachable through `DT_HASH`/`DT_GNU_HASH`; with no hash table
    glibc 2.41 "treats the object as if it has no symbol" (probed: every name `(null)`). A symbol with `st_size=0`
    only matches its exact start address, so `dladdr(ret-4)` returns `(null)` unless each Tin function has its real
    size. A one-bucket `DT_HASH` (header `1,N`, `bucket[0]=1`, `chain[i]=i+1`) is enough (probed, 4.5).
12. **PIE needs `PT_PHDR` and `R_*_RELATIVE`.** Without `PT_PHDR` a PIE segfaults in ld.so (ET_EXEC does not care).
    Every absolute pointer stored in data (`.quad main`, string headers, function tables) needs an
    `R_AARCH64_RELATIVE(1027)`/`R_X86_64_RELATIVE(8)` in a PIE; a non-PIE ET_EXEC at 0x400000 needs none (probed).
    Recommendation: emit ET_EXEC first (like the current fixed-address Mach-O), PIE later.
13. **Two libraries, not one.** `sin/cos/.../sqrt` are in `libm.so.6`; everything else incl. `pthread_*` and `dladdr`
    is in `libc.so.6` on glibc >= 2.34. On glibc 2.31 `pthread_create` is in `libpthread.so.0` and `dladdr` in
    `libdl.so.2` (probed); those two still exist as stubs on 2.36/2.41, so listing all four as `DT_NEEDED` works everywhere.
14. **`stat`/`lstat`/`fstat` exist as symbols only since glibc 2.33** (`stat@@GLIBC_2.33`). On 2.31 a gcc binary
    imports `__xstat(ver, path, buf)` with `_STAT_VER` = **0 on arm64, 1 on x86-64** (probed). `__xstat` is still
    exported on 2.41, so calling `__xstat` is the portable choice if 2.31 matters; `readdir` is unversioned-safe.
15. **`struct epoll_event` is packed on x86-64**: 12 bytes, `data@4`; on arm64 16 bytes, `data@8` (probed with a
    live epoll loop through raw bytes). `timeval.tv_usec` is 8 bytes on Linux (4 on darwin), `mode_t` 4 (2),
    `nfds_t` 8 (4), `sa_family_t` 2 (1), `sigset_t` 128 (4), `pthread_attr_t` 64 (arm64) / 56 (amd64).
16. **Apple's arm64 variadic convention is the odd one.** On Linux (both arches) variadic arguments go in the
    normal argument registers; on x86-64 `al` must additionally hold the number of vector registers used (0..8)
    before calling `snprintf`/`open`/`fcntl` (ABI rule, not probed). `gen.tin` already keys this on `tgt_linux`.
17. **x28 as the context register is fine on Linux aarch64** (callee-saved in AAPCS64). Do not move it to x18:
    Linux does not reserve x18 and glibc may clobber it.
18. **`atexit` is not in `libc.so.6`'s dynamic symbol table** (it lives in `libc_nonshared.a`); use `__cxa_atexit`
    (probed via `dlsym`). Irrelevant today, listed because it is the only "normal" function that was MISSING.
19. Page size: Linux arm64 containers here use 4 KiB pages, but arm64 distros may run 16K/64K kernels; GNU ld
    therefore aligns aarch64 `PT_LOAD` to **0x10000** and x86-64 to 0x1000. Copy that.

---

## 1. Extern functions Tin uses

Source list: `grep -h "^extern func\|^extern fn" lib/*.tin selfhost/*.tin`. Presence and defining object were taken at
run time with `dlsym(RTLD_DEFAULT)` + `dladdr` (`funcs.c` -> `out/*/funcs.txt`); versions from
`readelf --dyn-syms libc.so.6 libm.so.6` (`out/*/symbol_versions.txt`, `libc_dynsyms.txt`, `libm_dynsyms.txt`).
"base" = `GLIBC_2.17` on arm64, `GLIBC_2.2.5` on amd64 (the oldest version; what an unversioned reference binds to).

### 1.1 Available unchanged (same name, same signature)

| symbol | darwin-arm64 (libSystem sub-library) | linux-arm64 | linux-amd64 | version(s) | notes |
|---|---|---|---|---|---|
| `accept bind connect listen socket getsockname getsockopt setsockopt` | libsystem_kernel | libc.so.6 | libc.so.6 | base | constants and `sockaddr` layout differ (sections 2, 3) |
| `close read write open pipe fcntl creat unlink rename mkdir rmdir chdir getcwd getpid gethostname isatty` | kernel / c | libc.so.6 | libc.so.6 | base | `open`/`fcntl` flag values differ; `fcntl64@GLIBC_2.28`/`open64` also exist (not needed) |
| `fstat lstat stat` | libsystem_kernel | libc.so.6 | libc.so.6 | **`@@GLIBC_2.33` only** | absent before 2.33: `__xstat(ver,path,buf)`, `__lxstat`, `__fxstat(ver,fd,buf)` with ver 0 (arm64) / 1 (amd64); still exported on 2.41 |
| `opendir readdir closedir` | libsystem_c | libc.so.6 | libc.so.6 | base | returns `struct dirent` (Linux layout, section 3); `readdir64` is the same function on 64-bit |
| `malloc calloc realloc free posix_memalign` | libsystem_malloc | libc.so.6 | libc.so.6 | base | `posix_memalign(…,128,…)` probed OK |
| `memcpy memmove memset memcmp memchr strlen strcmp` | libsystem_platform | libc.so.6 | libc.so.6 | base; **amd64 `memcpy@@GLIBC_2.14` + `@GLIBC_2.2.5`** | IFUNC-resolved; the 2.2.5 one has memmove semantics (harmless) |
| `getenv setenv unsetenv atoi strtod strerror snprintf exit time usleep nanosleep signal` | libsystem_c | libc.so.6 | libc.so.6 | base | `strerror(EAGAIN)` = "Resource temporarily unavailable" on both |
| `gmtime_r strftime` | libsystem_c | libc.so.6 | libc.so.6 | base | `struct tm` identical (section 3); anvil's `Date:` format probed |
| `getaddrinfo freeaddrinfo` | libsystem_info | libc.so.6 | libc.so.6 | base | `addrinfo` field order differs (section 3); `EAI_*` are **negative** on Linux |
| `poll` | libsystem_kernel | libc.so.6 | libc.so.6 | base | `pollfd` identical; `nfds_t` is 8 bytes |
| `realpath` | libsystem_c | libc.so.6 | libc.so.6 | arm64 base; **amd64 `@@GLIBC_2.3` + `@GLIBC_2.2.5`** | 2.2.5 version rejects `resolved==NULL` (probed) |
| `sysconf` | libsystem_c | libc.so.6 | libc.so.6 | base | names differ: `_SC_NPROCESSORS_ONLN` 58 -> 84, `_SC_PAGESIZE` 29 -> 30 |
| `pthread_attr_init pthread_attr_setstacksize pthread_create` | libsystem_pthread | libc.so.6 (2.34+) | libc.so.6 (2.34+) | `@@GLIBC_2.34` + base compat (`pthread_attr_init` base only) | **glibc 2.31: `libpthread.so.0`**. 8 MiB stack request honoured (probed) |
| `dladdr` | libdyld | libc.so.6 (2.34+) | libc.so.6 (2.34+) | `@@GLIBC_2.34` + base | **glibc 2.31: `libdl.so.2`**; needs hash table + `st_size` (4.5) |
| math: `acos asin atan atan2 cbrt ceil cos cosh exp exp2 floor fmod hypot log log10 log1p log2 pow rint round sin sinh sqrt tan tanh trunc` | libsystem_m | **libm.so.6** | **libm.so.6** | base, except `exp exp2 log log2 pow @@GLIBC_2.29`, `hypot @@GLIBC_2.35`, `fmod @@GLIBC_2.38` (2.41 only; 2.36 has only base) | add `DT_NEEDED libm.so.6`; libm itself needs libc |

### 1.2 macOS-only: replacement on Linux

| darwin symbol (Tin use) | Linux replacement | version | notes |
|---|---|---|---|
| `__error()` -> `int*` | `__errno_location()` -> `int*` | base | identical shape (probed: `*__errno_location()==2==ENOENT` after a failed open) |
| `clock_gettime_nsec_np(8)` (tide.Now, crucible), `(0)` (tide.Wall) | `clock_gettime(clk, ts)`; ns = `ts[0]*1e9 + ts[1]` | arm64 base; amd64 `@@GLIBC_2.17` + `@2.2.5` | `CLOCK_MONOTONIC=1` or `CLOCK_BOOTTIME=7` for Now, `CLOCK_REALTIME=0` for Wall; `timespec` = `{i64 sec@0, i64 nsec@8}` |
| `arc4random_buf(p, n)` (seal) | `getrandom(p, n, 0)` -> bytes read (ssize_t, may be short, retry on `EINTR`) | `@@GLIBC_2.25` | `arc4random_buf`/`arc4random`/`arc4random_uniform` exist as `@@GLIBC_2.36` (present on 2.36 and 2.41, absent on 2.31); `getentropy(p, n<=256)` `@@GLIBC_2.25` also works |
| `kqueue()` | `epoll_create1(EPOLL_CLOEXEC)` | `@@GLIBC_2.9` (amd64) / base (arm64) | |
| `kevent(kq, ch, nch, ev, nev, ts)` add/modify | `epoll_ctl(ep, EPOLL_CTL_ADD=1 / MOD=3 / DEL=2, fd, &event)` | `@@GLIBC_2.3.2` / base | `event = {u32 events; u64 data}` packed on amd64 (section 3); `EPOLLIN=1 EPOLLOUT=4 EPOLLET=0x80000000 EPOLLRDHUP=0x2000 EPOLLONESHOT=0x40000000 EPOLLERR=8 EPOLLHUP=0x10` |
| `kevent(kq, 0, 0, evs, n, 0)` wait | `epoll_wait(ep, evs, n, timeout_ms)` (-1 = block) | `@@GLIBC_2.3.2` / base | `epoll_pwait2` (timespec timeout) is `@@GLIBC_2.35` - avoid for 2.31/2.34 compatibility. Edge-triggered (`EV_CLEAR`) = `EPOLLET` |
| `EVFILT_TIMER` kevent (anvil tick) | `timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK\|TFD_CLOEXEC)` + `timerfd_settime(fd, 0, &itimerspec, 0)`, read 8-byte expiry count, add fd to epoll | `@@GLIBC_2.8` / base | `itimerspec = {it_interval@0 (16), it_value@16 (16)}`; probed: 20 ms periodic fired |
| pipe wake-ups (relay) | `eventfd(0, EFD_NONBLOCK\|EFD_CLOEXEC)`; write/read 8-byte counters | `@@GLIBC_2.7` / base | or keep the pipe (`pipe2(fds, O_NONBLOCK\|O_CLOEXEC)` exists) |
| `pthread_set_qos_class_self_np(0x21, 0)` | `sched_setaffinity(0, 128, &cpu_set_t)` or `pthread_setaffinity_np(pthread_self(), 128, &set)` (or do nothing) | `@@GLIBC_2.3.4` (+ `@2.3.3` with a **different signature**, hidden) / `@@GLIBC_2.34` | there is no QoS on Linux; pinning each core thread to one CPU from `sched_getaffinity` is the equivalent (probed `sched_setaffinity(0,{0})` -> rc 0, `sched_getcpu()==0`) |
| `_NSGetExecutablePath(buf, &size)` | `readlink("/proc/self/exe", buf, n)` -> length, **not NUL-terminated**; or `realpath("/proc/self/exe", buf)` | base | probed both |
| `sysconf(58)` (`_SC_NPROCESSORS_ONLN`) | `sysconf(84)` **but see section 5** | base | |

### 1.3 Same name, different struct contract

| symbol | difference |
|---|---|
| `stat lstat fstat` | `struct stat` layout (section 3); `st_mode` is 4 bytes |
| `readdir` | `struct dirent` layout; no `d_namlen` |
| `getaddrinfo` | `ai_addr@24` / `ai_canonname@32` |
| `bind accept getsockname connect` | `sockaddr_in.sin_family` is `u16@0`, no `sin_len` |
| `setsockopt(SO_RCVTIMEO/SO_SNDTIMEO)` | `struct timeval` is 16 bytes on both but `tv_usec` is **8** bytes at offset 8 on Linux; zero the buffer and store 8 bytes |
| `poll` | identical layout; `POLLIN=1 POLLOUT=4 POLLERR=8 POLLHUP=16 POLLNVAL=32` same |
| `signal(13, 1)` | same numbers (`SIGPIPE=13`, `SIG_IGN=1`); glibc `signal` has BSD (restarting) semantics like macOS |
| `open(path, flags, mode)` | flag bits differ (section 2); variadic passing differs (gotcha 16) |
| `fcntl(fd, cmd, arg)` | `F_GETFL=3 F_SETFL=4 F_GETFD=1 F_SETFD=2 FD_CLOEXEC=1` identical; `O_NONBLOCK` value differs |

### 1.4 Full presence table

`out/merged_funcs.md` lists 300+ symbols (Tin externs, Linux replacements, darwin-only names) with the defining
object on each platform. Highlights: `__errno_location getrandom epoll_* timerfd_* eventfd sched_*affinity
pthread_*affinity_np sched_getcpu get_nprocs sysinfo getauxval gettid accept4 pipe2 dup3 mremap memfd_create prctl
ppoll clock_nanosleep statx readdir64 memrchr explicit_bzero reallocarray copy_file_range splice _dl_find_object`
exist only on Linux; `__error clock_gettime_nsec_np kqueue kevent pthread_set_qos_class_self_np _NSGetExecutablePath
sysctl sysctlbyname mach_absolute_time` exist only on darwin; `getentropy arc4random* clock_gettime readlink
pthread_setname_np sched_yield` exist on both.

---

## 2. Constants

Source: `consts.c` -> `out/{darwin-arm64,linux-arm64-glibc2.41,linux-amd64-glibc2.41}/consts.txt`; merged table
with every probed name in `out/merged_consts.md`. `*` = Linux differs from darwin, **bold** = the two Linux arches differ.

### 2.1 errno

| name | darwin | linux (both) | | name | darwin | linux (both) |
|---|---|---|---|---|---|---|
| `EPERM` | 1 | 1 | | `ENOTSOCK` | 38 | 88 * |
| `ENOENT` | 2 | 2 | | `EADDRINUSE` | 48 | 98 * |
| `EINTR` | 4 | 4 | | `EADDRNOTAVAIL` | 49 | 99 * |
| `EIO` | 5 | 5 | | `ENETUNREACH` | 51 | 101 * |
| `EBADF` | 9 | 9 | | `ECONNABORTED` | 53 | 103 * |
| `EAGAIN` / `EWOULDBLOCK` | 35 | **11** * | | `ECONNRESET` | 54 | 104 * |
| `ENOMEM` | 12 | 12 | | `ENOBUFS` | 55 | 105 * |
| `EACCES` | 13 | 13 | | `EISCONN` | 56 | 106 * |
| `EFAULT` | 14 | 14 | | `ENOTCONN` | 57 | 107 * |
| `EBUSY` | 16 | 16 | | `ETIMEDOUT` | 60 | 110 * |
| `EEXIST` | 17 | 17 | | `ECONNREFUSED` | 61 | 111 * |
| `EXDEV` | 18 | 18 | | `EHOSTUNREACH` | 65 | 113 * |
| `ENOTDIR` | 20 | 20 | | `EALREADY` | 37 | 114 * |
| `EISDIR` | 21 | 21 | | `EINPROGRESS` | 36 | 115 * |
| `EINVAL` | 22 | 22 | | `ENOTSUP` / `EOPNOTSUPP` | 45 / 102 | 95 / 95 * |
| `ENFILE` | 23 | 23 | | `EAFNOSUPPORT` | 47 | 97 * |
| `EMFILE` | 24 | 24 | | `EPROTONOSUPPORT` | 43 | 93 * |
| `ENOTTY` | 25 | 25 | | `EMSGSIZE` | 40 | 90 * |
| `ENOSPC` | 28 | 28 | | `ENAMETOOLONG` | 63 | 36 * |
| `ESPIPE` | 29 | 29 | | `ENOTEMPTY` | 66 | 39 * |
| `EROFS` | 30 | 30 | | `ELOOP` | 62 | 40 * |
| `EPIPE` | 32 | 32 | | `ENOSYS` | 78 | 38 * |
| `EDOM` | 33 | 33 | | `EOVERFLOW` | 84 | 75 * |
| `ERANGE` | 34 | 34 | | `ECANCELED` | 89 | 125 * |
| `EDEADLK` | 11 | 35 * | | `EILSEQ` | 92 | 84 * |
| `ENOLCK` | 77 | 37 * | | `ESTALE` / `EDQUOT` | 70 / 69 | 116 / 122 * |

### 2.2 open / at / fcntl / access

| name | darwin | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `O_RDONLY O_WRONLY O_RDWR O_ACCMODE` | 0 1 2 3 | 0 1 2 3 | 0 1 2 3 |
| `O_CREAT` | 0x200 | 0x40 * | 0x40 |
| `O_TRUNC` | 0x400 | 0x200 * | 0x200 |
| `O_APPEND` | 0x8 | 0x400 * | 0x400 |
| `O_EXCL` | 0x800 | 0x80 * | 0x80 |
| `O_NONBLOCK` / `O_NDELAY` | 0x4 | 0x800 * | 0x800 |
| `O_CLOEXEC` | 0x1000000 | 0x80000 * | 0x80000 |
| `O_DIRECTORY` | 0x100000 | **0x4000** | **0x10000** |
| `O_NOFOLLOW` | 0x100 | **0x8000** | **0x20000** |
| `O_NOCTTY` | 0x20000 | 0x100 * | 0x100 |
| `O_SYNC` / `O_DSYNC` | 0x80 / 0x400000 | 0x101000 / 0x1000 * | same as arm64 |
| `O_DIRECT` | n/a | **0x10000** | **0x4000** |
| `O_PATH` / `O_TMPFILE` | n/a | 0x200000 / **0x404000** | 0x200000 / **0x410000** |
| `O_WRONLY\|O_CREAT\|O_TRUNC` (flume `0x601`) | 0x601 | **0x241** | 0x241 |
| `O_WRONLY\|O_CREAT\|O_APPEND` (quarry `0x209`) | 0x209 | **0x441** | 0x441 |
| `O_RDWR\|O_CREAT\|O_EXCL` | 0xa02 | 0xc2 | 0xc2 |
| `AT_FDCWD` | -2 | **-100** | -100 |
| `AT_SYMLINK_NOFOLLOW` / `AT_REMOVEDIR` / `AT_EMPTY_PATH` | 0x20 / 0x80 / n/a | 0x100 / 0x200 / 0x1000 | same |
| `F_DUPFD F_GETFD F_SETFD F_GETFL F_SETFL FD_CLOEXEC` | 0 1 2 3 4 1 | 0 1 2 3 4 1 | same |
| `F_DUPFD_CLOEXEC` | 67 | 1030 * | 1030 |
| `F_GETLK F_SETLK F_SETLKW` | 7 8 9 | 5 6 7 * | same |
| `F_OK R_OK W_OK X_OK` / `SEEK_SET CUR END` | 0 4 2 1 / 0 1 2 | same | same |
| `S_IFMT S_IFDIR S_IFREG S_IFLNK S_IFIFO S_IFSOCK S_IFCHR S_IFBLK` | 0xf000 0x4000 0x8000 0xa000 0x1000 0xc000 0x2000 0x6000 | same | same |
| `DT_UNKNOWN DT_FIFO DT_CHR DT_DIR DT_BLK DT_REG DT_LNK DT_SOCK` | 0 1 2 4 6 8 10 12 | same | same |
| `PATH_MAX` / `NAME_MAX` / `PIPE_BUF` / `IOV_MAX` / `HOST_NAME_MAX` | 1024 / 255 / 512 / 1024 / n/a | 4096 / 255 / 4096 / 1024 / 64 | same |

### 2.3 Sockets

| name | darwin | linux (both) |
|---|---|---|
| `AF_UNSPEC AF_UNIX AF_INET PF_INET` | 0 1 2 2 | 0 1 2 2 |
| `AF_INET6` | 30 | 10 * |
| `SOCK_STREAM SOCK_DGRAM` | 1 2 | 1 2 |
| `SOCK_NONBLOCK` / `SOCK_CLOEXEC` | n/a | 0x800 / 0x80000 (OR into `socket()` type; also `accept4` flags) |
| `SOL_SOCKET` | 0xffff | **1** * |
| `SO_REUSEADDR` | 4 | **2** * |
| `SO_REUSEPORT` | 0x200 | **15** * |
| `SO_KEEPALIVE` | 8 | **9** * |
| `SO_ERROR` | 0x1007 | **4** * |
| `SO_RCVTIMEO` / `SO_SNDTIMEO` | 0x1006 / 0x1005 | **20 / 21** * |
| `SO_RCVBUF` / `SO_SNDBUF` | 0x1002 / 0x1001 | 8 / 7 * |
| `SO_LINGER` / `SO_BROADCAST` / `SO_TYPE` / `SO_ACCEPTCONN` | 0x80 / 0x20 / 0x1008 / 2 | 13 / 6 / 3 / 30 * |
| `SO_NOSIGPIPE` | 0x1022 | **n/a** (use `MSG_NOSIGNAL` or ignore `SIGPIPE`) |
| `MSG_NOSIGNAL` | 0x80000 | **0x4000** * |
| `MSG_DONTWAIT` / `MSG_PEEK` / `MSG_WAITALL` / `MSG_OOB` | 0x80 / 2 / 0x40 / 1 | 0x40 / 2 / 0x100 / 1 * |
| `IPPROTO_IP IPPROTO_TCP IPPROTO_UDP IPPROTO_IPV6` | 0 6 17 41 | 0 6 17 41 |
| `TCP_NODELAY` | 1 | 1 |
| `TCP_KEEPIDLE` (darwin `TCP_KEEPALIVE`=16) / `TCP_KEEPINTVL` / `TCP_KEEPCNT` | — 16 / 0x101 / 0x102 | 4 / 5 / 6 * |
| `TCP_FASTOPEN` / `TCP_DEFER_ACCEPT` / `TCP_CORK` | 0x105 / n/a / n/a | 23 / 9 / 3 |
| `IPV6_V6ONLY` | 27 | 26 * |
| `SHUT_RD SHUT_WR SHUT_RDWR` | 0 1 2 | 0 1 2 |
| `SOMAXCONN` | 128 | 4096 * |
| `INADDR_ANY` / `INADDR_LOOPBACK` | 0 / 0x7f000001 | same |
| `AI_PASSIVE AI_CANONNAME AI_NUMERICHOST` | 1 2 4 | 1 2 4 |
| `AI_NUMERICSERV AI_ADDRCONFIG AI_V4MAPPED AI_ALL` | 0x1000 0x400 0x800 0x100 | 0x400 0x20 0x8 0x10 * |
| `EAI_AGAIN EAI_FAIL EAI_NONAME EAI_SERVICE EAI_SYSTEM EAI_MEMORY EAI_FAMILY EAI_SOCKTYPE` | 2 4 8 9 11 6 5 10 | **-3 -4 -2 -8 -11 -10 -6 -7** * |
| `NI_MAXHOST NI_MAXSERV` / `NI_NUMERICHOST NI_NUMERICSERV` | 1025 32 / 2 8 | 1025 32 / 1 2 * |
| `POLLIN POLLPRI POLLOUT POLLERR POLLHUP POLLNVAL POLLRDNORM` | 1 2 4 8 0x10 0x20 0x40 | same |
| `POLLWRNORM` / `POLLRDHUP` | 4 / n/a | 0x100 / 0x2000 * |

### 2.4 Signals, clocks, sysconf, mmap, scheduling

| name | darwin | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `SIGHUP SIGINT SIGQUIT SIGILL SIGTRAP SIGABRT SIGFPE SIGKILL SIGSEGV SIGPIPE SIGALRM SIGTERM` | 1 2 3 4 5 6 8 9 11 13 14 15 | same | same |
| `SIGBUS` | 10 | 7 * | 7 |
| `SIGUSR1 SIGUSR2` | 30 31 | 10 12 * | 10 12 |
| `SIGCHLD SIGCONT SIGSTOP SIGTSTP` | 20 19 17 18 | 17 18 19 20 * | same |
| `SIGURG SIGSYS` / `SIGWINCH SIGXCPU SIGXFSZ SIGVTALRM SIGPROF` | 16 12 / 28 24 25 26 27 | 23 31 / same * | same |
| `SIG_DFL SIG_IGN SIG_ERR` | 0 1 -1 | 0 1 -1 | same |
| `SA_RESTART SA_SIGINFO SA_NOCLDSTOP SA_NODEFER SA_RESETHAND SA_ONSTACK` | 2 0x40 8 0x10 4 1 | 0x10000000 4 1 0x40000000 0x80000000 0x8000000 * | same |
| `SIG_BLOCK SIG_UNBLOCK SIG_SETMASK` | 1 2 3 | 0 1 2 * | same |
| `NSIG` / `SIGRTMIN` / `SIGRTMAX` | 32 / n/a / n/a | 65 / 34 / 64 | same |
| `CLOCK_REALTIME` | 0 | 0 | 0 |
| `CLOCK_MONOTONIC` | 6 | **1** * | 1 |
| `CLOCK_MONOTONIC_RAW` | 4 | 4 | 4 |
| `CLOCK_PROCESS_CPUTIME_ID` / `CLOCK_THREAD_CPUTIME_ID` | 12 / 16 | 2 / 3 * | same |
| `CLOCK_BOOTTIME` / `CLOCK_MONOTONIC_COARSE` / `CLOCK_REALTIME_COARSE` | n/a | 7 / 6 / 5 | same |
| `CLOCK_UPTIME_RAW` (tide `Now`) | 8 | **n/a** | n/a |
| `TIMER_ABSTIME` | n/a | 1 | 1 |
| `_SC_NPROCESSORS_ONLN` (hearth `sysconf(58)`) | 58 | **84** * | 84 |
| `_SC_NPROCESSORS_CONF` | 57 | 83 * | 83 |
| `_SC_PAGESIZE` / `_SC_PAGE_SIZE` | 29 | 30 * | 30 |
| `_SC_CLK_TCK` / `_SC_OPEN_MAX` / `_SC_ARG_MAX` | 3 / 5 / 1 | 2 / 4 / 0 * | same |
| `_SC_PHYS_PAGES` / `_SC_AVPHYS_PAGES` | 200 / n/a | 85 / 86 * | same |
| `_SC_HOST_NAME_MAX` / `_SC_THREAD_STACK_MIN` / `_SC_LEVEL1_DCACHE_LINESIZE` | 72 / 93 / n/a | 180 / 75 / 190 * | same |
| runtime `sysconf(_SC_PAGESIZE)` | 16384 | 4096 | 4096 |
| runtime `sysconf(_SC_THREAD_STACK_MIN)` = `PTHREAD_STACK_MIN` | 16384 | **131072** | **16384** |
| `PROT_NONE PROT_READ PROT_WRITE PROT_EXEC` | 0 1 2 4 | same | same |
| `MAP_SHARED MAP_PRIVATE MAP_FIXED` | 1 2 0x10 | same | same |
| `MAP_ANON` / `MAP_ANONYMOUS` | 0x1000 | **0x20** * | 0x20 |
| `MAP_STACK` / `MAP_NORESERVE` / `MAP_GROWSDOWN` / `MAP_POPULATE` / `MAP_HUGETLB` / `MAP_FIXED_NOREPLACE` | n/a / 0x40 / n/a / n/a / n/a / n/a | 0x20000 / 0x4000 / 0x100 / 0x8000 / 0x40000 / 0x100000 | same |
| `MAP_JIT` | 0x800 | n/a | n/a |
| `MAP_FAILED` | -1 | -1 | -1 |
| `MADV_NORMAL MADV_RANDOM MADV_SEQUENTIAL MADV_WILLNEED MADV_DONTNEED` | 0 1 2 3 4 | same | same |
| `MADV_FREE` / `MADV_HUGEPAGE` | 5 / n/a | 8 / 14 * | same |
| `MS_ASYNC` / `MS_SYNC` | 1 / 0x10 | 1 / 4 * | same |
| `PTHREAD_CREATE_JOINABLE` / `PTHREAD_CREATE_DETACHED` | 1 / 2 | 0 / 1 * | same |
| `RTLD_DEFAULT` / `RTLD_NEXT` / `RTLD_LAZY` / `RTLD_NOW` / `RTLD_GLOBAL` / `RTLD_LOCAL` | -2 / -1 / 1 / 2 / 8 / 4 | 0 / -1 / 1 / 2 / 0x100 / 0 * | same |
| `SCHED_OTHER SCHED_FIFO SCHED_RR` / `SCHED_BATCH SCHED_IDLE` | 1 4 2 / n/a | 0 1 2 / 3 5 * | same |
| `RLIMIT_NOFILE RLIMIT_STACK RLIMIT_AS RLIMIT_CORE` / `RLIM_INFINITY` | 8 3 5 4 / 0x7fff…ffff | 7 3 9 4 / -1 * | same |
| `WNOHANG WUNTRACED` / `STDIN STDOUT STDERR` / `EOF` | 1 2 / 0 1 2 / -1 | same | same |

### 2.5 Linux-only: epoll, eventfd, timerfd, getrandom, cpu sets, syscall numbers

| name | linux-arm64 | linux-amd64 |
|---|---|---|
| `EPOLLIN EPOLLPRI EPOLLOUT EPOLLERR EPOLLHUP` | 1 2 4 8 0x10 | same |
| `EPOLLRDHUP` | 0x2000 | same |
| `EPOLLET` / `EPOLLONESHOT` / `EPOLLEXCLUSIVE` / `EPOLLWAKEUP` | 0x80000000 / 0x40000000 / 0x10000000 / 0x20000000 | same |
| `EPOLL_CTL_ADD EPOLL_CTL_DEL EPOLL_CTL_MOD` | 1 2 3 | same |
| `EPOLL_CLOEXEC` | 0x80000 | same |
| `EFD_NONBLOCK EFD_CLOEXEC EFD_SEMAPHORE` | 0x800 0x80000 1 | same |
| `TFD_NONBLOCK TFD_CLOEXEC TFD_TIMER_ABSTIME TFD_TIMER_CANCEL_ON_SET` | 0x800 0x80000 1 2 | same |
| `GRND_NONBLOCK GRND_RANDOM GRND_INSECURE` | 1 2 4 | same |
| `CPU_SETSIZE` (bits) / `sizeof(cpu_set_t)` | 1024 / 128 | same |
| `PR_SET_NAME PR_GET_NAME` | 15 16 | same |
| `SYS_write SYS_clock_gettime SYS_getrandom SYS_epoll_create1 SYS_epoll_ctl SYS_epoll_pwait SYS_sched_getaffinity SYS_exit_group SYS_gettid SYS_futex` | 64 113 278 20 21 22 123 94 178 98 | **1 228 318 291 233 281 204 231 186 202** |
| `SYS_epoll_wait` | n/a (only `epoll_pwait`) | 232 |

### 2.6 kqueue constants Tin uses today (darwin only, for the translation table)

`EVFILT_READ=-1 EVFILT_WRITE=-2 EVFILT_TIMER=-7 EV_ADD=1 EV_DELETE=2 EV_ENABLE=4 EV_ONESHOT=0x10 EV_CLEAR=0x20`,
`QOS_CLASS_USER_INTERACTIVE=0x21`. anvil's `kadd(fd,-1,1)` = `EPOLL_CTL_ADD` with `EPOLLIN`; `kadd(fd,-1,0x21)`
(`EV_ADD|EV_CLEAR`) = `EPOLLIN|EPOLLET`; `EVFILT_WRITE` = `EPOLLOUT`; the `EVFILT_TIMER` tick = a timerfd in the set.

---

## 3. Struct layouts

Source: `structs.c` -> `out/*/structs.txt`; merged in `out/merged_structs.md`. Format: `offset (size)`.
Live confirmation of the Linux numbers by real syscalls through raw byte offsets: `misc.c` -> `out/*/misc.txt`.

### 3.1 `struct sockaddr_in` (16 bytes everywhere)

| field | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sin_len` | 0 (1) | — | — |
| `sin_family` | 1 (1) | **0 (2)** | 0 (2) |
| `sin_port` (network order) | 2 (2) | 2 (2) | 2 (2) |
| `sin_addr` | 4 (4) | 4 (4) | 4 (4) |
| `sin_zero` | 8 (8) | 8 (8) | 8 (8) |
| `sizeof sa_family_t` | 1 | 2 | 2 |
| `struct sockaddr_in6` (28): `sin6_family` / `sin6_port` / `sin6_flowinfo` / `sin6_addr` / `sin6_scope_id` | 1(1) / 2 / 4 / 8 / 24 | 0(2) / 2 / 4 / 8 / 24 | same |
| `struct sockaddr_un`: `sizeof` / `sun_family` / `sun_path` | 106 / 1(1) / 2(104) | 110 / 0(2) / 2(108) | same |
| `sizeof socklen_t` / `struct sockaddr_storage` | 4 / 128 | 4 / 128 | same |

### 3.2 `struct addrinfo` (48 bytes everywhere)

| field | darwin-arm64 | linux (both) |
|---|---|---|
| `ai_flags` | 0 (4) | 0 (4) |
| `ai_family` | 4 (4) | 4 (4) |
| `ai_socktype` | 8 (4) | 8 (4) |
| `ai_protocol` | 12 (4) | 12 (4) |
| `ai_addrlen` | 16 (4) | 16 (4) |
| `ai_canonname` | **24 (8)** | **32 (8)** |
| `ai_addr` | **32 (8)** | **24 (8)** |
| `ai_next` | 40 (8) | 40 (8) |

### 3.3 `struct stat`

| field | darwin-arm64 (144) | linux-arm64 (**128**) | linux-amd64 (**144**) |
|---|---|---|---|
| `st_dev` | 0 (4) | 0 (8) | 0 (8) |
| `st_ino` | 8 (8) | 8 (8) | 8 (8) |
| `st_mode` | 4 (2) | **16 (4)** | **24 (4)** |
| `st_nlink` | 6 (2) | 20 (4) | 16 (8) |
| `st_uid` / `st_gid` | 16 / 20 (4) | 24 / 28 (4) | 28 / 32 (4) |
| `st_rdev` | 24 (4) | 32 (8) | 40 (8) |
| `st_size` | 96 (8) | **48 (8)** | **48 (8)** |
| `st_blksize` | 112 (4) | 56 (4) | 56 (8) |
| `st_blocks` | 104 (8) | 64 (8) | 64 (8) |
| `st_atim` / `st_atimespec` | 32 (16) | 72 (16) | 72 (16) |
| `st_mtim` / `st_mtimespec` (quarry `stMtime`) | **48 (16)** | **88 (16)** | **88 (16)** |
| `st_ctim` / `st_ctimespec` | 64 (16) | 104 (16) | 104 (16) |
| `st_birthtimespec` / `st_flags` / `st_gen` | 80 / 116 / 120 | — | — |
| `sizeof mode_t nlink_t dev_t blksize_t` | 2 2 4 4 | 4 4 8 4 | 4 8 8 8 |

Probed: `stat("/etc/hostname")` through raw offsets gave `st_mode@16=0100644` (arm64) / `@24` (amd64),
`st_size@48=13`, `st_mtim.tv_sec@88`; bytes past `sizeof` untouched (a 256-byte buffer is safe on all three).
`isDirMode` (`m & 0xf000 == 0x4000`) stays valid; `mode()` must load 4 bytes (loading 2 and masking 0xffff also works).

### 3.4 `struct dirent` as returned by `readdir`

| field | darwin-arm64 (1048) | linux (both, 280) |
|---|---|---|
| `d_ino` | 0 (8) | 0 (8) |
| `d_seekoff` / `d_off` | 8 (8) | 8 (8) |
| `d_reclen` | 16 (2) | 16 (2) |
| `d_namlen` | **18 (2)** | **none** |
| `d_type` | 20 (1) | **18 (1)** |
| `d_name` | 21 (1024) | **19 (256)** |

Probed on Linux: `d_reclen=24` for "sbin" (padded), so the name length is `strlen(d_name)`.

### 3.5 Time

| struct / field | darwin-arm64 | linux (both) |
|---|---|---|
| `struct timespec` (16): `tv_sec` / `tv_nsec` | 0 (8) / 8 (8) | 0 (8) / 8 (8) |
| `struct timeval` (16): `tv_sec` / `tv_usec` | 0 (8) / 8 (**4**) | 0 (8) / 8 (**8**) |
| `struct itimerspec` (32): `it_interval` / `it_value` | n/a | 0 (16) / 16 (16) |
| `struct tm` (56): `tm_sec tm_min tm_hour tm_mday tm_mon tm_year tm_wday tm_yday tm_isdst` | 0 4 8 12 16 20 24 28 32 (4 each) | identical |
| `struct tm`: `tm_gmtoff` / `tm_zone` | 40 (8) / 48 (8) | 40 (8) / 48 (8) |
| `sizeof time_t clockid_t suseconds_t` | 8 4 4 | 8 4 8 |

### 3.6 Event structures

| struct / field | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `struct pollfd` (8): `fd` / `events` / `revents` | 0 (4) / 4 (2) / 6 (2) | same | same |
| `sizeof nfds_t` | 4 | 8 | 8 |
| `struct epoll_event`: `sizeof` / `events` / `data` / alignment | — | **16** / 0 (4) / **8 (8)** / 8 | **12 (packed)** / 0 (4) / **4 (8)** / 1 |
| `struct kevent` (32): `ident filter flags fflags data udata` | 0(8) 8(2) 10(2) 12(4) 16(8) 24(8) | — | — |

Probed: an `epoll_event` array indexed with stride 16 (arm64) / 12 (amd64) and `data.fd` read at +8 / +4
received both an eventfd and a timerfd wake-up correctly.

### 3.7 Threads, dl, misc

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof pthread_t` | 8 | 8 | 8 |
| `sizeof pthread_attr_t` (runtime allocates `calloc(16,8)`=128: enough) | 64 | **64** | **56** |
| `sizeof pthread_mutex_t` / `pthread_cond_t` | 64 / 48 | 48 / 48 | 40 / 48 |
| `sizeof pthread_key_t` / `pthread_once_t` | 8 / 16 | 4 / 4 | 4 / 4 |
| `sizeof cpu_set_t` | — | 128 | 128 |
| `Dl_info` (32): `dli_fname dli_fbase dli_sname dli_saddr` | 0 8 16 24 | same | same |
| `struct iovec` (16): `iov_base` / `iov_len` | 0 / 8 | same | same |
| `struct linger` (8): `l_onoff` / `l_linger` | 0 (4) / 4 (4) | same | same |
| `struct rlimit` (16) / `struct rusage` (144, `ru_maxrss@32`) | same | same | same |
| `struct sigaction`: `sizeof` / `sa_handler` / `sa_mask` / `sa_flags` | 16 / 0 / 8 (4) / 12 | 152 / 0 / 8 (128) / 136 | same as arm64 |
| `sizeof sigset_t` | 4 | 128 | 128 |
| `struct utsname`: `sizeof` / field stride | 1280 / 256 | 390 / 65 | 390 / 65 |
| `sizeof long double` | 8 | 16 | 16 |

---

## 4. ELF dynamic linking facts for Tin's linker

Sources: `hello.c` built three ways (`out/*/hello_pie_readelf.txt`, `hello_nopie_readelf.txt`, `hello_noplt_readelf.txt`),
the hand-written templates `start_arm64.S` / `start_amd64.S` (`out/*/start_pie.txt`, `start_nopie.txt`,
`start_sysv_now.txt`, binaries `start_pie.bin`/`start_nopie.bin`), the crt disassembly (`crt1_objdump.txt`),
`spcheck.txt`, `absptr_relocs.txt`, the patch experiments (`negative_tests.txt`, `elfpatch.py`),
`dladdr.txt`, `hash1.txt`, `bindings_unversioned.txt`, `out/version_sections.txt`.

### 4.1 Header and program headers

| item | linux-arm64 | linux-amd64 |
|---|---|---|
| `e_ident` | `7f 45 4c 46 02 01 01 00` + 8 zero bytes (ELF64, LE, version 1, SYSV ABI) | same |
| `e_type` | 2 = `ET_EXEC` (fixed address) or 3 = `ET_DYN` (PIE) | same |
| `e_machine` | **183** (0xB7, AArch64) | **62** (0x3E) |
| `e_version` / `e_flags` | 1 / 0 | 1 / 0 |
| `e_ehsize` / `e_phentsize` / `e_shentsize` | 64 / 56 / 64 | same |
| `e_phoff` | 64 (headers follow the ELF header) | 64 |
| `e_shoff/e_shnum/e_shstrndx` | may all be **0**: ld.so never reads section headers (probed `noshdr`) | same |
| interpreter (`PT_INTERP` contents, NUL included in `p_filesz`) | `/lib/ld-linux-aarch64.so.1` (27 bytes) | `/lib64/ld-linux-x86-64.so.2` (28 bytes) |
| gcc default `PT_LOAD` alignment | **0x10000** | **0x1000** |
| non-PIE base address used by ld | 0x400000 | 0x400000 |
| kernel page size seen (`AT_PAGESZ`) | 4096 | 4096 |

Program header order emitted by GNU ld for the minimal template (PIE, aarch64; x86-64 identical except four
`PT_LOAD`s R / R E / R / RW and an extra `GNU_PROPERTY`):

```
Type      Offset   VirtAddr  FileSiz  MemSiz  Flg Align
PHDR      0x000040 0x000040  0x1c0    0x1c0   R   0x8      <- required for PIE, optional for ET_EXEC (probed)
INTERP    0x000224 0x000224  0x1b     0x1b    R   0x1
LOAD      0x000000 0x000000  0x3e5    0x3e5   R E 0x10000  <- headers + .interp + .dynsym/.dynstr/.rela.dyn + .text + .rodata
LOAD      0x00fe90 0x01fe90  0x170    0x170   RW  0x10000  <- .dynamic + .got (p_vaddr % align == p_offset % align)
DYNAMIC   0x00fe90 0x01fe90  0x140    0x140   RW  0x8
NOTE      ...                                              <- optional (build-id)
GNU_STACK 0        0         0        0       RW  0x10     <- emit it: flags 7 gives an rwx stack (probed); absent -> rw-p on 6.10 but emit anyway
GNU_RELRO ...                                              <- optional
```

Patch experiments on the working template (`negative_tests.txt`, identical results on both arches):

| removed / changed | PIE | ET_EXEC |
|---|---|---|
| `PT_PHDR` -> `PT_NULL` | **segfault in ld.so** | runs |
| `PT_GNU_STACK` removed | runs, stack `rw-p` | runs |
| `PT_GNU_STACK` flags = 7 | runs, stack **`rwxp`** | — |
| section headers zeroed | runs | — |
| `DT_GNU_HASH` removed (no hash at all) | runs (`dladdr` names gone; see 4.5) | — |
| `DT_VERSYM`/`DT_VERNEED`/`DT_VERNEEDNUM` removed | runs (binds oldest versions; 4.6) | — |
| `DT_DEBUG` removed | runs | — |
| `DT_FLAGS`/`DT_FLAGS_1` removed | runs | — |

### 4.2 Minimal dynamic section (what the template actually has)

```
DT_NEEDED   (1)  "libc.so.6"           (+ "libm.so.6" for math; glibc<2.34 also "libpthread.so.0", "libdl.so.2")
DT_GNU_HASH (0x6ffffef5) or DT_HASH (4) optional for running; one of them required for dladdr names (4.5)
DT_STRTAB   (5)  vaddr of .dynstr
DT_SYMTAB   (6)  vaddr of .dynsym       (entry 0 = all zeros)
DT_STRSZ    (10) size of .dynstr
DT_SYMENT   (11) 24
DT_RELA     (7)  vaddr of .rela.dyn
DT_RELASZ   (8)  bytes
DT_RELAENT  (9)  24
DT_FLAGS_1  (0x6ffffffb) 0x08000000 = DF_1_PIE   (PIE only; informational)
DT_DEBUG    (21) 0                     (optional, for gdb)
DT_VERSYM/DT_VERNEED/DT_VERNEEDNUM      (optional, see 4.7)
DT_NULL
```

Not needed when every import goes through the GOT without a PLT: `DT_PLTGOT DT_PLTRELSZ DT_PLTREL DT_JMPREL`
(the `-fno-plt -z now` hello has only `R_*_GLOB_DAT` entries and no `.rela.plt`). `DT_FLAGS=8` (`DF_BIND_NOW`)
and `DT_FLAGS_1 |= 1` (`DF_1_NOW`) are what ld emits for `-z now`; they are irrelevant without a PLT because
`GLOB_DAT` relocations are always processed at load time. `DT_INIT/DT_FINI/DT_INIT_ARRAY` are not needed:
`__libc_start_main` runs constructors only if those tags exist.

Dynamic tag values seen in the hexdump (`start_pie.txt`): `01 → NEEDED, f5feff6f → GNU_HASH, 05 STRTAB,
06 SYMTAB, 0a STRSZ, 0b SYMENT, 15 DEBUG, 07 RELA, 08 RELASZ, 09 RELAENT, fbffff6f FLAGS_1 (val 0x08000000),
feffff6f VERNEED, ffffff6f VERNEEDNUM, f0ffff6f VERSYM`.

### 4.3 Symbols and relocations for calling libc through the GOT

`Elf64_Sym` (24 bytes): `st_name u32 @0, st_info u8 @4, st_other u8 @5, st_shndx u16 @6, st_value u64 @8, st_size u64 @16`.
An import is `st_info = 0x12` (`STB_GLOBAL<<4 | STT_FUNC`), `st_shndx = 0`, value/size 0 (hexdump:
`06000000 12000000 00000000…` = name offset 6, GLOBAL FUNC, UND).

`Elf64_Rela` (24 bytes): `r_offset u64` (vaddr of the GOT slot), `r_info u64 = (symidx << 32) | type`, `r_addend i64 = 0`.

| purpose | linux-arm64 | linux-amd64 |
|---|---|---|
| bind a GOT slot to a libc function (no PLT) | `R_AARCH64_GLOB_DAT` = **1025** (0x401) | `R_X86_64_GLOB_DAT` = **6** |
| lazy PLT slot (not needed) | `R_AARCH64_JUMP_SLOT` = 1026 | `R_X86_64_JUMP_SLOT` = 7 |
| absolute pointer in data, PIE only | `R_AARCH64_RELATIVE` = **1027** (0x403), symidx 0, addend = unrelocated value | `R_X86_64_RELATIVE` = **8**, same |
| 64-bit absolute with symbol | `R_AARCH64_ABS64` = 257 | `R_X86_64_64` = 1 |

Probed (`absptr_relocs.txt`): `.data: .quad main; .quad msg` produced two `R_*_RELATIVE` entries in the PIE build and
**no relocations at all** in the `-no-pie` build; both ran. So an ET_EXEC Tin binary needs exactly one `GLOB_DAT` per
imported function and nothing else, as on Mach-O today.

GOT-indirect call sequences (from the templates, identical to Tin's Mach-O stubs on arm64):

```
aarch64:  adrp x16, got_page ; ldr x16, [x16, #got_lo12] ; blr x16        (or br x16 in a stub)
x86-64:   call *disp32(%rip)          ; ff 15 <rel32 to GOT slot>        (jmp *disp32(%rip) = ff 25 in a stub)
```

### 4.4 `_start`, `__libc_start_main`, stack at entry

Kernel/ld.so hand-over at `_start` (probed via `crt_only.S` + `spcheck.c`, PIE and non-PIE, glibc 2.31/2.36/2.41):

| fact | linux-arm64 | linux-amd64 |
|---|---|---|
| `sp` at entry | 16-byte aligned (`sp % 16 == 0`), points at `argc` | same (`rsp % 16 == 0`, points at `argc`) |
| stack layout from `sp` | `argc, argv[0..argc-1], NULL, envp..., NULL, auxv...` | same |
| `rtld_fini` (`_dl_fini`) | **x0** (non-NULL) | **rdx** (non-NULL) |
| frame pointer / link register | set `x29 = x30 = 0` | `xor %ebp,%ebp` |
| `AT_PHDR` | load bias + 64 | same |
| `main` is called with | `(argc, argv, envp)`; `envp == argv+argc+1`, `environ` set by libc | same |

`__libc_start_main(main, argc, argv, init, fini, rtld_fini, stack_end)` never returns; it calls `exit(main(...))`.
`init` and `fini` must be **0**: `__libc_start_main@@GLIBC_2.34` ignores them and runs `DT_INIT_ARRAY` itself; the
compat `@GLIBC_2.2.5/2.17` version (the only one on 2.31) only calls `init` when non-NULL. The template (NULL init)
ran on glibc 2.31, 2.36 and 2.41. glibc's own `Scrt1.o` does exactly this (see `crt1_objdump.txt`); its only
differences from the template are `bti c` at the start (aarch64) and loading `main` through the GOT.

```
aarch64 (x0..x6 = 7 args)                        x86-64 (6 register args + 1 stack arg)
mov  x29, #0 ; mov x30, #0                      xor  %ebp, %ebp
mov  x5, x0            // rtld_fini             mov  %rdx, %r9          # rtld_fini
ldr  x1, [sp]          // argc                  pop  %rsi               # argc
add  x2, sp, #8        // argv                  mov  %rsp, %rdx         # argv
mov  x6, sp            // stack_end             and  $-16, %rsp
adr  x0, main                                   push %rax               # pad -> rsp%16==0 at call
mov  x3, #0 ; mov x4, #0   // init, fini         push %rsp               # stack_end (7th arg)
adrp x16, :got:__libc_start_main                xor  %r8d, %r8d ; xor %ecx, %ecx   # fini, init
ldr  x16, [x16, #:got_lo12:__libc_start_main]   lea  main(%rip), %rdi
blr  x16                                        call *__libc_start_main@GOTPCREL(%rip)
brk  #0                                         hlt
```

Full template sources: `notes/linux_probe/start_arm64.S`, `start_amd64.S`; readelf/objdump/hexdump of the resulting
binaries: `out/linux-*-glibc2.41/start_pie.txt` (PIE) and `start_nopie.txt` (ET_EXEC, 14 KB each, 8/10 program
headers, 2 relocations, `.dynsym` of 3-4 entries, `.dynstr` of 56-57 bytes). Both print and exit 0 on all probed glibcs.
`LD_DEBUG=bindings` shows the versioned template binding `__libc_start_main [GLIBC_2.34]` and `puts [GLIBC_2.17 / 2.2.5]`.

Exact `.dynstr` of the arm64 template: `\0puts\0__libc_start_main\0libc.so.6\0GLIBC_2.17\0GLIBC_2.34\0` (56 bytes).
Exact `.gnu.hash` ld emits for an executable exporting nothing (28 bytes, little-endian u32s):
`nbuckets=1, symoffset=1, bloom_size=1, bloom_shift=0, bloom[0]=0, bucket[0]=0`.

### 4.5 `dladdr` requirements (for `rt_backtrace`)

Probed with `dladdr_test.c` + `nosize_fn.S` (`out/*/dladdr.txt`, `hash1.txt`) on glibc 2.41, both arches:

| build | `dladdr(fn)` | `dladdr(fn+4)` | notes |
|---|---|---|---|
| default link (functions not in `.dynsym`) | `(null)` | `(null)` | libc symbols still resolve |
| `-rdynamic` (`.dynsym` + `DT_GNU_HASH`) | name | name | `static` functions: `(null)` (STB_LOCAL) |
| `-rdynamic --hash-style=sysv` (`DT_HASH`) | name | name | |
| `-rdynamic` with both hash tags removed | `(null)` | `(null)` | glibc 2.41 `dl-addr.c`: "In the absence of a hash table, treat the object as if it has no symbol." |
| symbol with `st_size == 0` | name | **`(null)`** | `DL_ADDR_SYM_MATCH` requires `addr == st_value` when `st_size == 0`, else `addr < st_value + st_size` |
| symbol `STT_NOTYPE` with size | name | name | type does not matter, binding (GLOBAL/WEAK) and size do |
| **`DT_HASH` rewritten to `nbucket=1`, all symbols on one chain** | name | name | ld.so lookups through it also work (`environ` copy-reloc test) |

Recipe for Tin: put every Tin function into `.dynsym` as `STB_GLOBAL STT_FUNC` with its real `st_size`, and emit a
`DT_HASH` of `4*(2+1+N)` bytes: `u32 nbucket=1, u32 nchain=N (= number of .dynsym entries), u32 bucket[0]=1,
u32 chain[0]=0, chain[i]=i+1 (1<=i<N-1), chain[N-1]=0`. Point `DT_HASH` (tag 4) at it. `dladdr(ret-4)` then
returns the enclosing function (`dli_sname` at `Dl_info+16`, same as darwin). Without a hash table the executable's
symbols are also invisible to ld.so lookups from libc (probed: a `COPY`-relocated `environ` went stale on amd64),
which only matters if Tin ever defines symbols libc must see.

### 4.6 Symbol versioning: what an unversioned reference binds to

glibc 2.41 `elf/dl-lookup.c`, `check_match`, unversioned branch (quoted from the source):

> In the case of the old unversioned application the oldest (default) version should be used. In case of a dlsym()
> call the latest and public interface should be returned.
> `if ((verstab[symidx] & 0x7fff) >= ((flags & DL_LOOKUP_RETURN_NEWEST) ? 2 : 3)) { if ((verstab[symidx] & 0x8000) == 0 && (*num_versions)++ == 0) *versioned_sym = sym; return NULL; }`

and in `do_lookup_x`: `sym = num_versions == 1 ? versioned_sym : NULL;` ("If we have seen exactly one versioned
symbol while we are looking for an unversioned symbol and the version is not the default version we still accept
this symbol since there are no possible ambiguities"). So: version index 1 or 2 (the base version: `GLIBC_2.17` on
arm64, `GLIBC_2.2.5` on x86-64) wins even if hidden; otherwise the unique non-hidden (default) version is used.

Probed by removing the version tags from a binary and comparing bound addresses with `dlvsym`
(`bindings_unversioned.txt`, glibc 2.31 / 2.36 / 2.41):

| symbol | arm64 unversioned -> | amd64 unversioned -> | amd64 versioned (gcc) -> | consequence |
|---|---|---|---|---|
| `__libc_start_main` | GLIBC_2.17 (same code as 2.34) | GLIBC_2.2.5 (same code as 2.34) | GLIBC_2.34 | none (init=NULL works in both) |
| `memcpy` | 2.17 | 2.2.5 (= memmove alias) | 2.14 | none |
| `realpath` | 2.17 | **2.2.5: `realpath(p, NULL)` returns NULL** | 2.3 | Tin passes a buffer: fine |
| `exp log log2 pow` (libm) | 2.17 | 2.2.5 (SVID wrappers, set errno) | 2.29 | none for Tin |
| `fmod` | 2.17 | 2.2.5 | 2.38 (2.41) / 2.2.5 (2.36) | none |
| `hypot` | 2.17 | 2.2.5 | 2.35 | none |
| `pthread_create dladdr` | 2.17 | 2.2.5 (same address as 2.34) | 2.34 | none |
| `sched_getaffinity pthread_setaffinity_np` | 2.17 | 2.3.4 (the 2.3.3 one with the old signature is hidden) | 2.3.4 | none |
| `stat lstat fstat getrandom arc4random_buf epoll_*` | single version | single version | — | bound as the unique default |

Either strategy works; emitting versions is safer and costs a few bytes (4.7). If Tin emits versions, pick the
oldest version name that has the semantics Tin relies on, so the binary still loads on older glibc: base version
for everything except `__libc_start_main` (base is fine), `memcpy` (base is fine), `realpath@GLIBC_2.3` (if NULL buffer
is ever used), `clock_gettime@GLIBC_2.17` (x86-64; base exists too), `stat/lstat/fstat@GLIBC_2.33` (or call
`__xstat@base`), `getrandom@GLIBC_2.25`, `pthread_*/dladdr@base` (then also list `libpthread.so.0`/`libdl.so.2` in
`DT_NEEDED` for glibc < 2.34). ld.so refuses to start a binary that requires a version the installed libc lacks
("version `GLIBC_2.38' not found"), which is why the gcc-built binary from this container would not run on 2.36.

### 4.7 Version structures, if Tin emits them (bytes taken from the template)

`.gnu.version` (`DT_VERSYM`): one `u16` per `.dynsym` entry: 0 = local, 1 = global/unversioned, >=2 = `vna_other` of a
`Vernaux`. Template (arm64): `00 00 | 00 00 | 02 00 | 03 00` for `[null, .text section sym, __libc_start_main, puts]`.

`.gnu.version_r` (`DT_VERNEED`, `DT_VERNEEDNUM` = number of `Verneed` records), 8-byte aligned:

```
Elf64_Verneed { u16 vn_version=1; u16 vn_cnt; u32 vn_file (dynstr off of "libc.so.6"); u32 vn_aux (=16); u32 vn_next (0 or bytes to next Verneed) }
Elf64_Vernaux { u32 vna_hash (SysV ELF hash of the version name); u16 vna_flags=0; u16 vna_other (index used in .gnu.version); u32 vna_name (dynstr off); u32 vna_next (16 or 0) }
```

Template bytes (arm64): `01000200 18000000 10000000 00000000 | 97919606 0000 0300 22000000 10000000 | b4919606 0000 0200 2d000000 00000000`
= one Verneed for "libc.so.6" (dynstr 0x18) with two Vernaux: `GLIBC_2.17` hash 0x06969197 index 3, `GLIBC_2.34` hash 0x069691b4 index 2.

SysV hash (`h = (h<<4)+c; g = h & 0xf0000000; if g: h ^= g>>24; h &= ~g`) of the names Tin may need, verified against
the bytes above: `GLIBC_2.2.5=0x09691a75 GLIBC_2.3=0x0d696913 GLIBC_2.3.2=0x09691972 GLIBC_2.3.4=0x09691974
GLIBC_2.14=0x06969194 GLIBC_2.17=0x06969197 GLIBC_2.25=0x06969185 GLIBC_2.29=0x06969189 GLIBC_2.33=0x069691b3
GLIBC_2.34=0x069691b4 GLIBC_2.35=0x069691b5 GLIBC_2.36=0x069691b6 GLIBC_2.38=0x069691b8`.

---

## 5. Containers: `hearth.Cores()` and memory limits

Source: `cgroup.c` run under Docker 27.3.1 (cgroup v2, `cgroupns=private`) -> `out/linux-arm64-glibc2.41/cgroup_*.txt`,
`out/linux-amd64-glibc2.41/cgroup_combined.txt`, `out/linux-arm64-glibc2.36/cgroup_combined.txt`. Host had 11 CPUs online.

| docker flag | `/sys/fs/cgroup/cpu.max` | `cpuset.cpus.effective` | `sched_getaffinity` count | `sysconf(_SC_NPROCESSORS_ONLN)` / `get_nprocs()` | `memory.max` |
|---|---|---|---|---|---|
| none | `max 100000` | `0-10` | 11 | 11 | `max` |
| `--cpus=1.5` | **`150000 100000`** | `0-10` | 11 | 11 | `max` |
| `--cpus=0.5` | `50000 100000` | `0-10` | 11 | 11 | `max` |
| `--cpuset-cpus=0,1` | `max 100000` | **`0-1`** | **2** | **11** (wrong) | `max` |
| `--memory=256m` | `max 100000` | `0-10` | 11 | 11 | **`268435456`** (`memory.swap.max` also 268435456) |
| all three (+`--memory-swap=256m`) | `150000 100000` | `0-1` | 2 | 11 | `268435456` (`memory.swap.max 0`) |

Facts:

- `/proc/self/cgroup` is `0::/` inside the container and `/sys/fs/cgroup` is `cgroup2fs` (magic 0x63677270), so the
  container's own limits are at the root: read `/sys/fs/cgroup/cpu.max` = `"<quota> <period>"` in microseconds, or
  the literal `max` for no quota. CPU limit = `ceil(quota / period)`.
- cgroup v1 (`/sys/fs/cgroup/cpu/cpu.cfs_quota_us`, `cpu.cfs_period_us`, `/sys/fs/cgroup/memory/memory.limit_in_bytes`,
  `/sys/fs/cgroup/cpuset/cpuset.cpus`) does not exist here (all `ENOENT`); on a v1 host those files hold the same
  numbers as separate decimal values (quota `-1` = unlimited), with the process's own path from `/proc/self/cgroup`
  (`N:cpu,cpuacct:/path`) appended under the controller mount. Not verifiable on this Mac.
- `sched_getaffinity(0, 128, &set)` returns 0 and the set reflects `--cpuset-cpus`; `CPU_COUNT` = popcount of the
  128-byte mask. `pthread_getaffinity_np` agrees. `sysconf(_SC_NPROCESSORS_ONLN)`, `_SC_NPROCESSORS_CONF`,
  `get_nprocs()` and `/sys/devices/system/cpu/online` all report the **host** count.
- Memory: `memory.max` (bytes or `max`), `memory.high`, `memory.swap.max`, `memory.current`; `sysconf(_SC_PHYS_PAGES)`
  and `sysinfo()` report host RAM (8217825280 here) regardless of `--memory`.
- `sched_setaffinity(0, 128, {cpu0})` succeeds in the container and `sched_getcpu()` then returns 0: the
  `pthread_set_qos_class_self_np` stand-in works.

Suggested `hearth.Cores()` (what Go 1.25's container-aware `GOMAXPROCS` does): `n = CPU_COUNT(sched_getaffinity)`;
if `cpu.max` has a quota, `n = min(n, max(1, ceil(quota/period)))`; fall back to `sysconf(84)` only if both fail.

---

## 6. Probe inventory

| file | purpose | outputs |
|---|---|---|
| `consts.c` | every constant above (darwin + linux) | `out/*/consts.txt`, merged `out/merged_consts.md` |
| `structs.c` | sizeof/offsetof of every struct field above | `out/*/structs.txt`, merged `out/merged_structs.md` |
| `funcs.c` | `dlsym`/`dladdr` presence + defining object of 300+ symbols | `out/*/funcs.txt`, merged `out/merged_funcs.md` |
| `misc.c` | live checks through raw offsets: errno, clocks, getrandom, stat, readdir, strftime, fcntl, sockaddr/addrinfo layouts, epoll+eventfd+timerfd, threads, affinity, mmap, readlink | `out/linux-*/misc.txt` |
| `cgroup.c` | cgroup v2/v1 files, `sched_getaffinity`, `sysconf`, `sysinfo` | `out/*/cgroup_*.txt` |
| `hello.c` | gcc reference binary (PIE, `-no-pie`, `-fno-plt -z now`) | `out/*/hello_*_readelf.txt`, `crt1_objdump.txt` |
| `start_arm64.S`, `start_amd64.S` | the crt-less template Tin's writer copies | `out/*/start_pie.txt`, `start_nopie.txt`, `start_sysv_now.txt`, `*.bin` |
| `crt_only.S` + `spcheck.c` | entry state (sp alignment, argc/argv/envp, rtld_fini, auxv, `[stack]` perms) | `out/*/spcheck.txt`, `negative_tests.txt` |
| `elfpatch.py` | drop dynamic tags / program headers / section headers, 1-bucket `DT_HASH` | used by `run_all.sh`, `bindings.sh` |
| `dladdr_test.c` + `nosize_fn.S` | what `dladdr` names | `out/*/dladdr.txt`, `hash1.txt` |
| `bindings.sh` | unversioned binding + `dlvsym` comparison, 1-bucket hash | `out/*/bindings_unversioned.txt`, `hash1.txt` |
| `glibc231.sh` | the same on Ubuntu 20.04 / glibc 2.31 | `out/linux-*-glibc2.31/glibc231.txt` |
| `run_all.sh` | driver for everything above inside one container | `out/<plat>-glibc<ver>/` |
| `out/*/libc_dynsyms.txt`, `libm_dynsyms.txt`, `libc_versions.txt`, `symbol_versions.txt`, `versions.txt` | full export tables and toolchain versions | |
