
### errno

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `EPERM` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `ENOENT` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `ESRCH` | 3 (0x3) | 3 (0x3) | 3 (0x3) |
| `EINTR` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `EIO` | 5 (0x5) | 5 (0x5) | 5 (0x5) |
| `EBADF` | 9 (0x9) | 9 (0x9) | 9 (0x9) |
| `ECHILD` | 10 (0xa) | 10 (0xa) | 10 (0xa) |
| `EAGAIN` | 35 (0x23) | 11 (0xb) | 11 (0xb) | *
| `EWOULDBLOCK` | 35 (0x23) | 11 (0xb) | 11 (0xb) | *
| `ENOMEM` | 12 (0xc) | 12 (0xc) | 12 (0xc) |
| `EACCES` | 13 (0xd) | 13 (0xd) | 13 (0xd) |
| `EFAULT` | 14 (0xe) | 14 (0xe) | 14 (0xe) |
| `EEXIST` | 17 (0x11) | 17 (0x11) | 17 (0x11) |
| `EXDEV` | 18 (0x12) | 18 (0x12) | 18 (0x12) |
| `ENOTDIR` | 20 (0x14) | 20 (0x14) | 20 (0x14) |
| `EISDIR` | 21 (0x15) | 21 (0x15) | 21 (0x15) |
| `EINVAL` | 22 (0x16) | 22 (0x16) | 22 (0x16) |
| `ENFILE` | 23 (0x17) | 23 (0x17) | 23 (0x17) |
| `EMFILE` | 24 (0x18) | 24 (0x18) | 24 (0x18) |
| `ENOSPC` | 28 (0x1c) | 28 (0x1c) | 28 (0x1c) |
| `ESPIPE` | 29 (0x1d) | 29 (0x1d) | 29 (0x1d) |
| `EROFS` | 30 (0x1e) | 30 (0x1e) | 30 (0x1e) |
| `EPIPE` | 32 (0x20) | 32 (0x20) | 32 (0x20) |
| `ERANGE` | 34 (0x22) | 34 (0x22) | 34 (0x22) |
| `ENAMETOOLONG` | 63 (0x3f) | 36 (0x24) | 36 (0x24) | *
| `ENOTEMPTY` | 66 (0x42) | 39 (0x27) | 39 (0x27) | *
| `ELOOP` | 62 (0x3e) | 40 (0x28) | 40 (0x28) | *
| `ENOSYS` | 78 (0x4e) | 38 (0x26) | 38 (0x26) | *
| `EOVERFLOW` | 84 (0x54) | 75 (0x4b) | 75 (0x4b) | *
| `ENOTSOCK` | 38 (0x26) | 88 (0x58) | 88 (0x58) | *
| `EADDRINUSE` | 48 (0x30) | 98 (0x62) | 98 (0x62) | *
| `EADDRNOTAVAIL` | 49 (0x31) | 99 (0x63) | 99 (0x63) | *
| `ENETUNREACH` | 51 (0x33) | 101 (0x65) | 101 (0x65) | *
| `ECONNABORTED` | 53 (0x35) | 103 (0x67) | 103 (0x67) | *
| `ECONNRESET` | 54 (0x36) | 104 (0x68) | 104 (0x68) | *
| `ENOBUFS` | 55 (0x37) | 105 (0x69) | 105 (0x69) | *
| `EISCONN` | 56 (0x38) | 106 (0x6a) | 106 (0x6a) | *
| `ENOTCONN` | 57 (0x39) | 107 (0x6b) | 107 (0x6b) | *
| `ETIMEDOUT` | 60 (0x3c) | 110 (0x6e) | 110 (0x6e) | *
| `ECONNREFUSED` | 61 (0x3d) | 111 (0x6f) | 111 (0x6f) | *
| `EHOSTUNREACH` | 65 (0x41) | 113 (0x71) | 113 (0x71) | *
| `EALREADY` | 37 (0x25) | 114 (0x72) | 114 (0x72) | *
| `EINPROGRESS` | 36 (0x24) | 115 (0x73) | 115 (0x73) | *
| `ENOTSUP` | 45 (0x2d) | 95 (0x5f) | 95 (0x5f) | *
| `EOPNOTSUPP` | 102 (0x66) | 95 (0x5f) | 95 (0x5f) | *
| `EPROTONOSUPPORT` | 43 (0x2b) | 93 (0x5d) | 93 (0x5d) | *
| `EAFNOSUPPORT` | 47 (0x2f) | 97 (0x61) | 97 (0x61) | *
| `EMSGSIZE` | 40 (0x28) | 90 (0x5a) | 90 (0x5a) | *
| `EDEADLK` | 11 (0xb) | 35 (0x23) | 35 (0x23) | *
| `ENOTTY` | 25 (0x19) | 25 (0x19) | 25 (0x19) |
| `E2BIG` | 7 (0x7) | 7 (0x7) | 7 (0x7) |
| `ENOEXEC` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `EBUSY` | 16 (0x10) | 16 (0x10) | 16 (0x10) |
| `ECANCELED` | 89 (0x59) | 125 (0x7d) | 125 (0x7d) | *
| `EILSEQ` | 92 (0x5c) | 84 (0x54) | 84 (0x54) | *
| `EDOM` | 33 (0x21) | 33 (0x21) | 33 (0x21) |
| `ENOLCK` | 77 (0x4d) | 37 (0x25) | 37 (0x25) | *
| `ESTALE` | 70 (0x46) | 116 (0x74) | 116 (0x74) | *
| `EDQUOT` | 69 (0x45) | 122 (0x7a) | 122 (0x7a) | *

### open flags

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `O_RDONLY` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `O_WRONLY` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `O_RDWR` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `O_ACCMODE` | 3 (0x3) | 3 (0x3) | 3 (0x3) |
| `O_CREAT` | 512 (0x200) | 64 (0x40) | 64 (0x40) | *
| `O_TRUNC` | 1024 (0x400) | 512 (0x200) | 512 (0x200) | *
| `O_APPEND` | 8 (0x8) | 1024 (0x400) | 1024 (0x400) | *
| `O_EXCL` | 2048 (0x800) | 128 (0x80) | 128 (0x80) | *
| `O_NONBLOCK` | 4 (0x4) | 2048 (0x800) | 2048 (0x800) | *
| `O_NDELAY` | 4 (0x4) | 2048 (0x800) | 2048 (0x800) | *
| `O_CLOEXEC` | 16777216 (0x1000000) | 524288 (0x80000) | 524288 (0x80000) | *
| `O_DIRECTORY` | 1048576 (0x100000) | 16384 (0x4000) | 65536 (0x10000) | **≠**
| `O_NOFOLLOW` | 256 (0x100) | 32768 (0x8000) | 131072 (0x20000) | **≠**
| `O_SYNC` | 128 (0x80) | 1052672 (0x101000) | 1052672 (0x101000) | *
| `O_NOCTTY` | 131072 (0x20000) | 256 (0x100) | 256 (0x100) | *
| `O_DSYNC` | 4194304 (0x400000) | 4096 (0x1000) | 4096 (0x1000) | *
| `O_PATH` | n/a | 2097152 (0x200000) | 2097152 (0x200000) | *
| `O_TMPFILE` | n/a | 4210688 (0x404000) | 4259840 (0x410000) | **≠**
| `O_DIRECT` | n/a | 65536 (0x10000) | 16384 (0x4000) | **≠**
| `O_WRONLY|O_CREAT|O_TRUNC` | 1537 (0x601) | 577 (0x241) | 577 (0x241) | *
| `O_WRONLY|O_CREAT|O_APPEND` | 521 (0x209) | 1089 (0x441) | 1089 (0x441) | *
| `O_RDWR|O_CREAT|O_EXCL` | 2562 (0xa02) | 194 (0xc2) | 194 (0xc2) | *
| `AT_FDCWD` | -2 (0xfffffffffffffffe) | -100 (0xffffffffffffff9c) | -100 (0xffffffffffffff9c) | *
| `AT_SYMLINK_NOFOLLOW` | 32 (0x20) | 256 (0x100) | 256 (0x100) | *
| `AT_REMOVEDIR` | 128 (0x80) | 512 (0x200) | 512 (0x200) | *
| `AT_EMPTY_PATH` | n/a | 4096 (0x1000) | 4096 (0x1000) | *
| `F_OK` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `R_OK` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `W_OK` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `X_OK` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `SEEK_SET` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `SEEK_CUR` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `SEEK_END` | 2 (0x2) | 2 (0x2) | 2 (0x2) |

### fcntl

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `F_DUPFD` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `F_GETFD` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `F_SETFD` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `F_GETFL` | 3 (0x3) | 3 (0x3) | 3 (0x3) |
| `F_SETFL` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `FD_CLOEXEC` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `F_DUPFD_CLOEXEC` | 67 (0x43) | 1030 (0x406) | 1030 (0x406) | *
| `F_GETLK` | 7 (0x7) | 5 (0x5) | 5 (0x5) | *
| `F_SETLK` | 8 (0x8) | 6 (0x6) | 6 (0x6) | *
| `F_SETLKW` | 9 (0x9) | 7 (0x7) | 7 (0x7) | *

### stat modes / dirent types

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `S_IFMT` | 61440 (0xf000) | 61440 (0xf000) | 61440 (0xf000) |
| `S_IFDIR` | 16384 (0x4000) | 16384 (0x4000) | 16384 (0x4000) |
| `S_IFREG` | 32768 (0x8000) | 32768 (0x8000) | 32768 (0x8000) |
| `S_IFLNK` | 40960 (0xa000) | 40960 (0xa000) | 40960 (0xa000) |
| `S_IFIFO` | 4096 (0x1000) | 4096 (0x1000) | 4096 (0x1000) |
| `S_IFSOCK` | 49152 (0xc000) | 49152 (0xc000) | 49152 (0xc000) |
| `S_IFCHR` | 8192 (0x2000) | 8192 (0x2000) | 8192 (0x2000) |
| `S_IFBLK` | 24576 (0x6000) | 24576 (0x6000) | 24576 (0x6000) |
| `S_IRWXU` | 448 (0x1c0) | 448 (0x1c0) | 448 (0x1c0) |
| `S_IRUSR` | 256 (0x100) | 256 (0x100) | 256 (0x100) |
| `S_IWUSR` | 128 (0x80) | 128 (0x80) | 128 (0x80) |
| `S_IXUSR` | 64 (0x40) | 64 (0x40) | 64 (0x40) |
| `S_IRWXG` | 56 (0x38) | 56 (0x38) | 56 (0x38) |
| `S_IRWXO` | 7 (0x7) | 7 (0x7) | 7 (0x7) |
| `DT_UNKNOWN` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `DT_FIFO` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `DT_CHR` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `DT_DIR` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `DT_BLK` | 6 (0x6) | 6 (0x6) | 6 (0x6) |
| `DT_REG` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `DT_LNK` | 10 (0xa) | 10 (0xa) | 10 (0xa) |
| `DT_SOCK` | 12 (0xc) | 12 (0xc) | 12 (0xc) |

### socket

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `AF_UNSPEC` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `AF_UNIX` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `AF_INET` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `AF_INET6` | 30 (0x1e) | 10 (0xa) | 10 (0xa) | *
| `PF_INET` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `SOCK_STREAM` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `SOCK_DGRAM` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `SOCK_NONBLOCK` | n/a | 2048 (0x800) | 2048 (0x800) | *
| `SOCK_CLOEXEC` | n/a | 524288 (0x80000) | 524288 (0x80000) | *
| `SOL_SOCKET` | 65535 (0xffff) | 1 (0x1) | 1 (0x1) | *
| `SO_REUSEADDR` | 4 (0x4) | 2 (0x2) | 2 (0x2) | *
| `SO_REUSEPORT` | 512 (0x200) | 15 (0xf) | 15 (0xf) | *
| `SO_KEEPALIVE` | 8 (0x8) | 9 (0x9) | 9 (0x9) | *
| `SO_ERROR` | 4103 (0x1007) | 4 (0x4) | 4 (0x4) | *
| `SO_RCVTIMEO` | 4102 (0x1006) | 20 (0x14) | 20 (0x14) | *
| `SO_SNDTIMEO` | 4101 (0x1005) | 21 (0x15) | 21 (0x15) | *
| `SO_RCVBUF` | 4098 (0x1002) | 8 (0x8) | 8 (0x8) | *
| `SO_SNDBUF` | 4097 (0x1001) | 7 (0x7) | 7 (0x7) | *
| `SO_LINGER` | 128 (0x80) | 13 (0xd) | 13 (0xd) | *
| `SO_BROADCAST` | 32 (0x20) | 6 (0x6) | 6 (0x6) | *
| `SO_TYPE` | 4104 (0x1008) | 3 (0x3) | 3 (0x3) | *
| `SO_ACCEPTCONN` | 2 (0x2) | 30 (0x1e) | 30 (0x1e) | *
| `SO_NOSIGPIPE` | 4130 (0x1022) | n/a | n/a | *
| `MSG_NOSIGNAL` | 524288 (0x80000) | 16384 (0x4000) | 16384 (0x4000) | *
| `MSG_DONTWAIT` | 128 (0x80) | 64 (0x40) | 64 (0x40) | *
| `MSG_PEEK` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `MSG_WAITALL` | 64 (0x40) | 256 (0x100) | 256 (0x100) | *
| `MSG_OOB` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `IPPROTO_IP` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `IPPROTO_TCP` | 6 (0x6) | 6 (0x6) | 6 (0x6) |
| `IPPROTO_UDP` | 17 (0x11) | 17 (0x11) | 17 (0x11) |
| `IPPROTO_IPV6` | 41 (0x29) | 41 (0x29) | 41 (0x29) |
| `TCP_NODELAY` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `TCP_KEEPIDLE` | n/a | 4 (0x4) | 4 (0x4) | *
| `TCP_KEEPALIVE` | 16 (0x10) | n/a | n/a | *
| `TCP_KEEPINTVL` | 257 (0x101) | 5 (0x5) | 5 (0x5) | *
| `TCP_KEEPCNT` | 258 (0x102) | 6 (0x6) | 6 (0x6) | *
| `TCP_FASTOPEN` | 261 (0x105) | 23 (0x17) | 23 (0x17) | *
| `TCP_DEFER_ACCEPT` | n/a | 9 (0x9) | 9 (0x9) | *
| `TCP_CORK` | n/a | 3 (0x3) | 3 (0x3) | *
| `IPV6_V6ONLY` | 27 (0x1b) | 26 (0x1a) | 26 (0x1a) | *
| `SHUT_RD` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `SHUT_WR` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `SHUT_RDWR` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `SOMAXCONN` | 128 (0x80) | 4096 (0x1000) | 4096 (0x1000) | *
| `INADDR_ANY` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `INADDR_LOOPBACK` | 2130706433 (0x7f000001) | 2130706433 (0x7f000001) | 2130706433 (0x7f000001) |
| `INET_ADDRSTRLEN` | 16 (0x10) | 16 (0x10) | 16 (0x10) |
| `INET6_ADDRSTRLEN` | 46 (0x2e) | 46 (0x2e) | 46 (0x2e) |
| `AI_PASSIVE` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `AI_CANONNAME` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `AI_NUMERICHOST` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `AI_NUMERICSERV` | 4096 (0x1000) | 1024 (0x400) | 1024 (0x400) | *
| `AI_ADDRCONFIG` | 1024 (0x400) | 32 (0x20) | 32 (0x20) | *
| `AI_V4MAPPED` | 2048 (0x800) | 8 (0x8) | 8 (0x8) | *
| `AI_ALL` | 256 (0x100) | 16 (0x10) | 16 (0x10) | *
| `EAI_AGAIN` | 2 (0x2) | -3 (0xfffffffffffffffd) | -3 (0xfffffffffffffffd) | *
| `EAI_FAIL` | 4 (0x4) | -4 (0xfffffffffffffffc) | -4 (0xfffffffffffffffc) | *
| `EAI_NONAME` | 8 (0x8) | -2 (0xfffffffffffffffe) | -2 (0xfffffffffffffffe) | *
| `EAI_SERVICE` | 9 (0x9) | -8 (0xfffffffffffffff8) | -8 (0xfffffffffffffff8) | *
| `EAI_SYSTEM` | 11 (0xb) | -11 (0xfffffffffffffff5) | -11 (0xfffffffffffffff5) | *
| `EAI_MEMORY` | 6 (0x6) | -10 (0xfffffffffffffff6) | -10 (0xfffffffffffffff6) | *
| `EAI_FAMILY` | 5 (0x5) | -6 (0xfffffffffffffffa) | -6 (0xfffffffffffffffa) | *
| `EAI_SOCKTYPE` | 10 (0xa) | -7 (0xfffffffffffffff9) | -7 (0xfffffffffffffff9) | *
| `NI_MAXHOST` | 1025 (0x401) | 1025 (0x401) | 1025 (0x401) |
| `NI_MAXSERV` | 32 (0x20) | 32 (0x20) | 32 (0x20) |
| `NI_NUMERICHOST` | 2 (0x2) | 1 (0x1) | 1 (0x1) | *
| `NI_NUMERICSERV` | 8 (0x8) | 2 (0x2) | 2 (0x2) | *

### poll

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `POLLIN` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `POLLPRI` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `POLLOUT` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `POLLERR` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `POLLHUP` | 16 (0x10) | 16 (0x10) | 16 (0x10) |
| `POLLNVAL` | 32 (0x20) | 32 (0x20) | 32 (0x20) |
| `POLLRDNORM` | 64 (0x40) | 64 (0x40) | 64 (0x40) |
| `POLLWRNORM` | 4 (0x4) | 256 (0x100) | 256 (0x100) | *
| `POLLRDHUP` | n/a | 8192 (0x2000) | 8192 (0x2000) | *

### signals

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `SIGHUP` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `SIGINT` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `SIGQUIT` | 3 (0x3) | 3 (0x3) | 3 (0x3) |
| `SIGILL` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `SIGTRAP` | 5 (0x5) | 5 (0x5) | 5 (0x5) |
| `SIGABRT` | 6 (0x6) | 6 (0x6) | 6 (0x6) |
| `SIGBUS` | 10 (0xa) | 7 (0x7) | 7 (0x7) | *
| `SIGFPE` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `SIGKILL` | 9 (0x9) | 9 (0x9) | 9 (0x9) |
| `SIGUSR1` | 30 (0x1e) | 10 (0xa) | 10 (0xa) | *
| `SIGSEGV` | 11 (0xb) | 11 (0xb) | 11 (0xb) |
| `SIGUSR2` | 31 (0x1f) | 12 (0xc) | 12 (0xc) | *
| `SIGPIPE` | 13 (0xd) | 13 (0xd) | 13 (0xd) |
| `SIGALRM` | 14 (0xe) | 14 (0xe) | 14 (0xe) |
| `SIGTERM` | 15 (0xf) | 15 (0xf) | 15 (0xf) |
| `SIGCHLD` | 20 (0x14) | 17 (0x11) | 17 (0x11) | *
| `SIGCONT` | 19 (0x13) | 18 (0x12) | 18 (0x12) | *
| `SIGSTOP` | 17 (0x11) | 19 (0x13) | 19 (0x13) | *
| `SIGTSTP` | 18 (0x12) | 20 (0x14) | 20 (0x14) | *
| `SIGWINCH` | 28 (0x1c) | 28 (0x1c) | 28 (0x1c) |
| `SIGURG` | 16 (0x10) | 23 (0x17) | 23 (0x17) | *
| `SIGXCPU` | 24 (0x18) | 24 (0x18) | 24 (0x18) |
| `SIGXFSZ` | 25 (0x19) | 25 (0x19) | 25 (0x19) |
| `SIGVTALRM` | 26 (0x1a) | 26 (0x1a) | 26 (0x1a) |
| `SIGPROF` | 27 (0x1b) | 27 (0x1b) | 27 (0x1b) |
| `SIGSYS` | 12 (0xc) | 31 (0x1f) | 31 (0x1f) | *
| `SIG_DFL` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `SIG_IGN` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `SIG_ERR` | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) |
| `SA_RESTART` | 2 (0x2) | 268435456 (0x10000000) | 268435456 (0x10000000) | *
| `SA_SIGINFO` | 64 (0x40) | 4 (0x4) | 4 (0x4) | *
| `SA_NOCLDSTOP` | 8 (0x8) | 1 (0x1) | 1 (0x1) | *
| `SA_NODEFER` | 16 (0x10) | 1073741824 (0x40000000) | 1073741824 (0x40000000) | *
| `SA_RESETHAND` | 4 (0x4) | 2147483648 (0x80000000) | 2147483648 (0x80000000) | *
| `SA_ONSTACK` | 1 (0x1) | 134217728 (0x8000000) | 134217728 (0x8000000) | *
| `SIG_BLOCK` | 1 (0x1) | 0 (0x0) | 0 (0x0) | *
| `SIG_UNBLOCK` | 2 (0x2) | 1 (0x1) | 1 (0x1) | *
| `SIG_SETMASK` | 3 (0x3) | 2 (0x2) | 2 (0x2) | *
| `NSIG` | 32 (0x20) | 65 (0x41) | 65 (0x41) | *
| `SIGRTMIN` | n/a | 34 (0x22) | 34 (0x22) | *
| `SIGRTMAX` | n/a | 64 (0x40) | 64 (0x40) | *

### clocks

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `CLOCK_REALTIME` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `CLOCK_MONOTONIC` | 6 (0x6) | 1 (0x1) | 1 (0x1) | *
| `CLOCK_PROCESS_CPUTIME_ID` | 12 (0xc) | 2 (0x2) | 2 (0x2) | *
| `CLOCK_THREAD_CPUTIME_ID` | 16 (0x10) | 3 (0x3) | 3 (0x3) | *
| `CLOCK_MONOTONIC_RAW` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `CLOCK_BOOTTIME` | n/a | 7 (0x7) | 7 (0x7) | *
| `CLOCK_MONOTONIC_COARSE` | n/a | 6 (0x6) | 6 (0x6) | *
| `CLOCK_REALTIME_COARSE` | n/a | 5 (0x5) | 5 (0x5) | *
| `CLOCK_UPTIME_RAW` | 8 (0x8) | n/a | n/a | *
| `TIMER_ABSTIME` | n/a | 1 (0x1) | 1 (0x1) | *

### sysconf names

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `_SC_NPROCESSORS_ONLN` | 58 (0x3a) | 84 (0x54) | 84 (0x54) | *
| `_SC_NPROCESSORS_CONF` | 57 (0x39) | 83 (0x53) | 83 (0x53) | *
| `_SC_PAGESIZE` | 29 (0x1d) | 30 (0x1e) | 30 (0x1e) | *
| `_SC_PAGE_SIZE` | 29 (0x1d) | 30 (0x1e) | 30 (0x1e) | *
| `_SC_CLK_TCK` | 3 (0x3) | 2 (0x2) | 2 (0x2) | *
| `_SC_OPEN_MAX` | 5 (0x5) | 4 (0x4) | 4 (0x4) | *
| `_SC_PHYS_PAGES` | 200 (0xc8) | 85 (0x55) | 85 (0x55) | *
| `_SC_HOST_NAME_MAX` | 72 (0x48) | 180 (0xb4) | 180 (0xb4) | *
| `_SC_THREAD_STACK_MIN` | 93 (0x5d) | 75 (0x4b) | 75 (0x4b) | *
| `_SC_ARG_MAX` | 1 (0x1) | 0 (0x0) | 0 (0x0) | *
| `_SC_AVPHYS_PAGES` | n/a | 86 (0x56) | 86 (0x56) | *
| `_SC_LEVEL1_DCACHE_LINESIZE` | n/a | 190 (0xbe) | 190 (0xbe) | *

### sysconf runtime values on this machine

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sysconf(_SC_NPROCESSORS_ONLN` | ) (11) | ) (11) | ) (11) |
| `sysconf(_SC_NPROCESSORS_CONF` | ) (11) | ) (11) | ) (11) |
| `sysconf(_SC_PAGESIZE)` | 16384 (0x4000) | 4096 (0x1000) | 4096 (0x1000) | *
| `sysconf(_SC_CLK_TCK)` | 100 (0x64) | 100 (0x64) | 100 (0x64) |
| `sysconf(_SC_OPEN_MAX)` | 1048576 (0x100000) | 1048576 (0x100000) | 1048576 (0x100000) |
| `sysconf(_SC_THREAD_STACK_MIN` | ) (16384) | ) (131072) | ) (16384) | **≠**
| `getpagesize()` | 16384 (0x4000) | 4096 (0x1000) | 4096 (0x1000) | *

### mmap/mprotect

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `PROT_NONE` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `PROT_READ` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `PROT_WRITE` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `PROT_EXEC` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `MAP_SHARED` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `MAP_PRIVATE` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `MAP_FIXED` | 16 (0x10) | 16 (0x10) | 16 (0x10) |
| `MAP_ANON` | 4096 (0x1000) | 32 (0x20) | 32 (0x20) | *
| `MAP_ANONYMOUS` | 4096 (0x1000) | 32 (0x20) | 32 (0x20) | *
| `MAP_FAILED` | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) |
| `MAP_STACK` | n/a | 131072 (0x20000) | 131072 (0x20000) | *
| `MAP_NORESERVE` | 64 (0x40) | 16384 (0x4000) | 16384 (0x4000) | *
| `MAP_GROWSDOWN` | n/a | 256 (0x100) | 256 (0x100) | *
| `MAP_POPULATE` | n/a | 32768 (0x8000) | 32768 (0x8000) | *
| `MAP_HUGETLB` | n/a | 262144 (0x40000) | 262144 (0x40000) | *
| `MAP_FIXED_NOREPLACE` | n/a | 1048576 (0x100000) | 1048576 (0x100000) | *
| `MAP_JIT` | 2048 (0x800) | n/a | n/a | *
| `MADV_NORMAL` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `MADV_DONTNEED` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `MADV_WILLNEED` | 3 (0x3) | 3 (0x3) | 3 (0x3) |
| `MADV_SEQUENTIAL` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `MADV_RANDOM` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `MADV_FREE` | 5 (0x5) | 8 (0x8) | 8 (0x8) | *
| `MADV_HUGEPAGE` | n/a | 14 (0xe) | 14 (0xe) | *
| `MS_SYNC` | 16 (0x10) | 4 (0x4) | 4 (0x4) | *
| `MS_ASYNC` | 1 (0x1) | 1 (0x1) | 1 (0x1) |

### epoll / eventfd / timerfd / getrandom (Linux only)

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `EPOLLIN` | n/a | 1 (0x1) | 1 (0x1) | *
| `EPOLLPRI` | ? | 2 (0x2) | 2 (0x2) | *
| `EPOLLOUT` | n/a | 4 (0x4) | 4 (0x4) | *
| `EPOLLERR` | n/a | 8 (0x8) | 8 (0x8) | *
| `EPOLLHUP` | n/a | 16 (0x10) | 16 (0x10) | *
| `EPOLLRDHUP` | n/a | 8192 (0x2000) | 8192 (0x2000) | *
| `EPOLLET` | n/a | 2147483648 (0x80000000) | 2147483648 (0x80000000) | *
| `EPOLLONESHOT` | n/a | 1073741824 (0x40000000) | 1073741824 (0x40000000) | *
| `EPOLLEXCLUSIVE` | ? | 268435456 (0x10000000) | 268435456 (0x10000000) | *
| `EPOLLWAKEUP` | ? | 536870912 (0x20000000) | 536870912 (0x20000000) | *
| `EPOLL_CTL_ADD` | n/a | 1 (0x1) | 1 (0x1) | *
| `EPOLL_CTL_DEL` | n/a | 2 (0x2) | 2 (0x2) | *
| `EPOLL_CTL_MOD` | n/a | 3 (0x3) | 3 (0x3) | *
| `EPOLL_CLOEXEC` | n/a | 524288 (0x80000) | 524288 (0x80000) | *
| `EFD_NONBLOCK` | n/a | 2048 (0x800) | 2048 (0x800) | *
| `EFD_CLOEXEC` | n/a | 524288 (0x80000) | 524288 (0x80000) | *
| `EFD_SEMAPHORE` | n/a | 1 (0x1) | 1 (0x1) | *
| `TFD_NONBLOCK` | n/a | 2048 (0x800) | 2048 (0x800) | *
| `TFD_CLOEXEC` | n/a | 524288 (0x80000) | 524288 (0x80000) | *
| `TFD_TIMER_ABSTIME` | n/a | 1 (0x1) | 1 (0x1) | *
| `TFD_TIMER_CANCEL_ON_SET` | ? | 2 (0x2) | 2 (0x2) | *
| `GRND_NONBLOCK` | n/a | 1 (0x1) | 1 (0x1) | *
| `GRND_RANDOM` | n/a | 2 (0x2) | 2 (0x2) | *
| `GRND_INSECURE` | n/a | 4 (0x4) | 4 (0x4) | *
| `CPU_SETSIZE` | n/a | 1024 (0x400) | 1024 (0x400) | *
| `SYS_getrandom` | ? | 278 (0x116) | 318 (0x13e) | **≠**
| `SYS_epoll_create1` | ? | 20 (0x14) | 291 (0x123) | **≠**
| `SYS_epoll_ctl` | ? | 21 (0x15) | 233 (0xe9) | **≠**
| `SYS_epoll_pwait` | ? | 22 (0x16) | 281 (0x119) | **≠**
| `SYS_sched_getaffinity` | ? | 123 (0x7b) | 204 (0xcc) | **≠**
| `SYS_clock_gettime` | ? | 113 (0x71) | 228 (0xe4) | **≠**
| `SYS_write` | ? | 64 (0x40) | 1 (0x1) | **≠**
| `SYS_exit_group` | ? | 94 (0x5e) | 231 (0xe7) | **≠**
| `SYS_gettid` | ? | 178 (0xb2) | 186 (0xba) | **≠**
| `SYS_futex` | ? | 98 (0x62) | 202 (0xca) | **≠**
| `SYS_epoll_wait` | ? | n/a | 232 (0xe8) | **≠**
| `PR_SET_NAME` | ? | 15 (0xf) | 15 (0xf) | *
| `PR_GET_NAME` | ? | 16 (0x10) | 16 (0x10) | *

### kqueue (darwin only, what Tin uses today)

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `EVFILT_READ` | -1 (0xffffffffffffffff) | n/a | n/a | *
| `EVFILT_WRITE` | -2 (0xfffffffffffffffe) | n/a | n/a | *
| `EVFILT_TIMER` | -7 (0xfffffffffffffff9) | n/a | n/a | *
| `EV_ADD` | 1 (0x1) | n/a | n/a | *
| `EV_ENABLE` | 4 (0x4) | n/a | n/a | *
| `EV_CLEAR` | 32 (0x20) | n/a | n/a | *
| `EV_ONESHOT` | 16 (0x10) | n/a | n/a | *
| `EV_DELETE` | 2 (0x2) | n/a | n/a | *
| `QOS_CLASS_USER_INTERACTIVE` | 33 (0x21) | n/a | n/a | *

### misc limits / dl / sched / rlimit / wait

| name | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `PATH_MAX` | 1024 (0x400) | 4096 (0x1000) | 4096 (0x1000) | *
| `NAME_MAX` | 255 (0xff) | 255 (0xff) | 255 (0xff) |
| `IOV_MAX` | 1024 (0x400) | 1024 (0x400) | 1024 (0x400) |
| `PIPE_BUF` | 512 (0x200) | 4096 (0x1000) | 4096 (0x1000) | *
| `HOST_NAME_MAX` | n/a | 64 (0x40) | 64 (0x40) | *
| `MAXHOSTNAMELEN` | n/a | n/a | n/a |
| `PTHREAD_STACK_MIN` | 16384 (0x4000) | 131072 (0x20000) | 16384 (0x4000) | **≠**
| `PTHREAD_CREATE_DETACHED` | 2 (0x2) | 1 (0x1) | 1 (0x1) | *
| `PTHREAD_CREATE_JOINABLE` | 1 (0x1) | 0 (0x0) | 0 (0x0) | *
| `RTLD_DEFAULT` | -2 (0xfffffffffffffffe) | 0 (0x0) | 0 (0x0) | *
| `RTLD_NEXT` | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) |
| `RTLD_LAZY` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `RTLD_NOW` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `RTLD_GLOBAL` | 8 (0x8) | 256 (0x100) | 256 (0x100) | *
| `RTLD_LOCAL` | 4 (0x4) | 0 (0x0) | 0 (0x0) | *
| `RTLD_NODELETE` | 128 (0x80) | 4096 (0x1000) | 4096 (0x1000) | *
| `SCHED_OTHER` | 1 (0x1) | 0 (0x0) | 0 (0x0) | *
| `SCHED_FIFO` | 4 (0x4) | 1 (0x1) | 1 (0x1) | *
| `SCHED_RR` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `SCHED_BATCH` | n/a | 3 (0x3) | 3 (0x3) | *
| `SCHED_IDLE` | n/a | 5 (0x5) | 5 (0x5) | *
| `RLIMIT_NOFILE` | 8 (0x8) | 7 (0x7) | 7 (0x7) | *
| `RLIMIT_STACK` | 3 (0x3) | 3 (0x3) | 3 (0x3) |
| `RLIMIT_AS` | 5 (0x5) | 9 (0x9) | 9 (0x9) | *
| `RLIMIT_CORE` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `RLIM_INFINITY` | 9223372036854775807 (0x7fffffffffffffff) | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) | *
| `WNOHANG` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `WUNTRACED` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `STDIN_FILENO` | 0 (0x0) | 0 (0x0) | 0 (0x0) |
| `STDOUT_FILENO` | 1 (0x1) | 1 (0x1) | 1 (0x1) |
| `STDERR_FILENO` | 2 (0x2) | 2 (0x2) | 2 (0x2) |
| `EOF` | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) | -1 (0xffffffffffffffff) |
| `sizeof(void*)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(long)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(size_t)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(time_t)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(off_t)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(mode_t)` | 2 (0x2) | 4 (0x4) | 4 (0x4) | *
| `sizeof(socklen_t)` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `sizeof(pid_t)` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `sizeof(nfds_t)` | 4 (0x4) | 8 (0x8) | 8 (0x8) | *
| `sizeof(suseconds_t)` | 4 (0x4) | 8 (0x8) | 8 (0x8) | *
| `sizeof(ino_t)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(dev_t)` | 4 (0x4) | 8 (0x8) | 8 (0x8) | *
| `sizeof(nlink_t)` | 2 (0x2) | 4 (0x4) | 8 (0x8) | **≠**
| `sizeof(blksize_t)` | 4 (0x4) | 4 (0x4) | 8 (0x8) | **≠**
| `sizeof(blkcnt_t)` | 8 (0x8) | 8 (0x8) | 8 (0x8) |
| `sizeof(clockid_t)` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `sizeof(wchar_t)` | 4 (0x4) | 4 (0x4) | 4 (0x4) |
| `sizeof(long double)` | 8 (0x8) | 16 (0x10) | 16 (0x10) | *
