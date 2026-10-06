
### sockaddr

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct sockaddr` | 16 | 16 | 16 |
| `struct sockaddr.sa_family` | 1 (1B) | 0 (2B) | 0 (2B) | *
| `struct sockaddr.sa_data` | 2 (14B) | 2 (14B) | 2 (14B) |
| `struct sockaddr.sa_len` | 0 (1B) | n/a | n/a | *
| `sizeof struct sockaddr_in` | 16 | 16 | 16 |
| `struct sockaddr_in.sin_len` | 0 (1B) | n/a | n/a | *
| `struct sockaddr_in.sin_family` | 1 (1B) | 0 (2B) | 0 (2B) | *
| `struct sockaddr_in.sin_port` | 2 (2B) | 2 (2B) | 2 (2B) |
| `struct sockaddr_in.sin_addr` | 4 (4B) | 4 (4B) | 4 (4B) |
| `struct sockaddr_in.sin_zero` | 8 (8B) | 8 (8B) | 8 (8B) |
| `sizeof struct sockaddr_in6` | 28 | 28 | 28 |
| `struct sockaddr_in6.sin6_family` | 1 (1B) | 0 (2B) | 0 (2B) | *
| `struct sockaddr_in6.sin6_port` | 2 (2B) | 2 (2B) | 2 (2B) |
| `struct sockaddr_in6.sin6_flowinfo` | 4 (4B) | 4 (4B) | 4 (4B) |
| `struct sockaddr_in6.sin6_addr` | 8 (16B) | 8 (16B) | 8 (16B) |
| `struct sockaddr_in6.sin6_scope_id` | 24 (4B) | 24 (4B) | 24 (4B) |
| `sizeof struct sockaddr_storage` | 128 | 128 | 128 |
| `sizeof struct sockaddr_un` | 106 | 110 | 110 | *
| `struct sockaddr_un.sun_family` | 1 (1B) | 0 (2B) | 0 (2B) | *
| `struct sockaddr_un.sun_path` | 2 (104B) | 2 (108B) | 2 (108B) | *
| `sizeof sa_family_t` | 1 | 2 | 2 | *
| `sizeof in_port_t` | 2 | 2 | 2 |
| `sizeof in_addr_t` | 4 | 4 | 4 |
| `sizeof socklen_t` | 4 | 4 | 4 |
| `sizeof struct in_addr` | 4 | 4 | 4 |
| `sizeof struct in6_addr` | 16 | 16 | 16 |

### addrinfo

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct addrinfo` | 48 | 48 | 48 |
| `struct addrinfo.ai_flags` | 0 (4B) | 0 (4B) | 0 (4B) |
| `struct addrinfo.ai_family` | 4 (4B) | 4 (4B) | 4 (4B) |
| `struct addrinfo.ai_socktype` | 8 (4B) | 8 (4B) | 8 (4B) |
| `struct addrinfo.ai_protocol` | 12 (4B) | 12 (4B) | 12 (4B) |
| `struct addrinfo.ai_addrlen` | 16 (4B) | 16 (4B) | 16 (4B) |
| `struct addrinfo.ai_addr` | 32 (8B) | 24 (8B) | 24 (8B) | *
| `struct addrinfo.ai_canonname` | 24 (8B) | 32 (8B) | 32 (8B) | *
| `struct addrinfo.ai_next` | 40 (8B) | 40 (8B) | 40 (8B) |

### stat

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct stat` | 144 | 128 | 144 | **≠**
| `struct stat.st_dev` | 0 (4B) | 0 (8B) | 0 (8B) | *
| `struct stat.st_ino` | 8 (8B) | 8 (8B) | 8 (8B) |
| `struct stat.st_mode` | 4 (2B) | 16 (4B) | 24 (4B) | **≠**
| `struct stat.st_nlink` | 6 (2B) | 20 (4B) | 16 (8B) | **≠**
| `struct stat.st_uid` | 16 (4B) | 24 (4B) | 28 (4B) | **≠**
| `struct stat.st_gid` | 20 (4B) | 28 (4B) | 32 (4B) | **≠**
| `struct stat.st_rdev` | 24 (4B) | 32 (8B) | 40 (8B) | **≠**
| `struct stat.st_size` | 96 (8B) | 48 (8B) | 48 (8B) | *
| `struct stat.st_blksize` | 112 (4B) | 56 (4B) | 56 (8B) | **≠**
| `struct stat.st_blocks` | 104 (8B) | 64 (8B) | 64 (8B) | *
| `struct stat.st_atim` | — | 72 (16B) | 72 (16B) | *
| `struct stat.st_mtim` | — | 88 (16B) | 88 (16B) | *
| `struct stat.st_ctim` | — | 104 (16B) | 104 (16B) | *
| `struct stat.st_birthtimespec` | 80 (16B) | n/a | n/a | *
| `struct stat.st_flags` | 116 (4B) | n/a | n/a | *
| `struct stat.st_gen` | 120 (4B) | n/a | n/a | *
| `struct stat.st_mtime(sec)` | 48 (8B) | 88 (8B) | 88 (8B) | *
| `sizeof off_t` | 8 | 8 | 8 |
| `sizeof ino_t` | 8 | 8 | 8 |
| `sizeof dev_t` | 4 | 8 | 8 | *
| `sizeof mode_t` | 2 | 4 | 4 | *
| `sizeof nlink_t` | 2 | 4 | 8 | **≠**
| `sizeof uid_t` | 4 | 4 | 4 |
| `sizeof gid_t` | 4 | 4 | 4 |
| `sizeof blksize_t` | 4 | 4 | 8 | **≠**
| `sizeof blkcnt_t` | 8 | 8 | 8 |
| `sizeof time_t` | 8 | 8 | 8 |

### dirent (as returned by readdir)

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct dirent` | 1048 | 280 | 280 | *
| `struct dirent.d_ino` | 0 (8B) | 0 (8B) | 0 (8B) |
| `struct dirent.d_reclen` | 16 (2B) | 16 (2B) | 16 (2B) |
| `struct dirent.d_type` | 20 (1B) | 18 (1B) | 18 (1B) | *
| `struct dirent.d_name` | 21 (1024B) | 19 (256B) | 19 (256B) | *
| `struct dirent.d_off` | n/a | 8 (8B) | 8 (8B) | *
| `struct dirent.d_namlen` | 18 (2B) | n/a | n/a | *
| `struct dirent.d_seekoff` | 8 (8B) | n/a | n/a | *
| `sizeof DIR *` | 8 | 8 | 8 |

### time

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct timespec` | 16 | 16 | 16 |
| `struct timespec.tv_sec` | 0 (8B) | 0 (8B) | 0 (8B) |
| `struct timespec.tv_nsec` | 8 (8B) | 8 (8B) | 8 (8B) |
| `sizeof struct timeval` | 16 | 16 | 16 |
| `struct timeval.tv_sec` | 0 (8B) | 0 (8B) | 0 (8B) |
| `struct timeval.tv_usec` | 8 (4B) | 8 (8B) | 8 (8B) | *
| `sizeof struct tm` | 56 | 56 | 56 |
| `struct tm.tm_sec` | 0 (4B) | 0 (4B) | 0 (4B) |
| `struct tm.tm_min` | 4 (4B) | 4 (4B) | 4 (4B) |
| `struct tm.tm_hour` | 8 (4B) | 8 (4B) | 8 (4B) |
| `struct tm.tm_mday` | 12 (4B) | 12 (4B) | 12 (4B) |
| `struct tm.tm_mon` | 16 (4B) | 16 (4B) | 16 (4B) |
| `struct tm.tm_year` | 20 (4B) | 20 (4B) | 20 (4B) |
| `struct tm.tm_wday` | 24 (4B) | 24 (4B) | 24 (4B) |
| `struct tm.tm_yday` | 28 (4B) | 28 (4B) | 28 (4B) |
| `struct tm.tm_isdst` | 32 (4B) | 32 (4B) | 32 (4B) |
| `struct tm.tm_gmtoff` | 40 (8B) | 40 (8B) | 40 (8B) |
| `struct tm.tm_zone` | 48 (8B) | 48 (8B) | 48 (8B) |
| `sizeof struct itimerval` | 32 | 32 | 32 |
| `sizeof clockid_t` | 4 | 4 | 4 |
| `sizeof suseconds_t` | 4 | 8 | 8 | *
| `sizeof struct itimerspec` | n/a (no POSIX timers on darwin) | 32 | 32 | *
| `struct itimerspec.it_interval` | n/a | 0 (16B) | 0 (16B) | *
| `struct itimerspec.it_value` | n/a | 16 (16B) | 16 (16B) | *

### poll / epoll / kevent

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct pollfd` | 8 | 8 | 8 |
| `struct pollfd.fd` | 0 (4B) | 0 (4B) | 0 (4B) |
| `struct pollfd.events` | 4 (2B) | 4 (2B) | 4 (2B) |
| `struct pollfd.revents` | 6 (2B) | 6 (2B) | 6 (2B) |
| `sizeof nfds_t` | 4 | 8 | 8 | *
| `sizeof struct epoll_event` | — | 16 | 12 | **≠**
| `struct epoll_event.events` | — | 0 (4B) | 0 (4B) | *
| `struct epoll_event.data` | — | 8 (8B) | 4 (8B) | **≠**
| `sizeof epoll_data_t` | — | 8 | 8 | *
| `alignof struct epoll_event` | — | 8 | 1 | **≠**
| `sizeof cpu_set_t` | — | 128 | 128 | *
| `sizeof struct sysinfo` | — | 112 | 112 | *

### pthread / dl / misc

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof pthread_t` | 8 | 8 | 8 |
| `sizeof pthread_attr_t` | 64 | 64 | 56 | **≠**
| `sizeof pthread_mutex_t` | 64 | 48 | 40 | **≠**
| `sizeof pthread_cond_t` | 48 | 48 | 48 |
| `sizeof pthread_key_t` | 8 | 4 | 4 | *
| `sizeof pthread_once_t` | 16 | 4 | 4 | *
| `alignof pthread_attr_t` | 8 | 8 | 8 |
| `sizeof Dl_info` | 32 | 32 | 32 |
| `Dl_info.dli_fname` | 0 (8B) | 0 (8B) | 0 (8B) |
| `Dl_info.dli_fbase` | 8 (8B) | 8 (8B) | 8 (8B) |
| `Dl_info.dli_sname` | 16 (8B) | 16 (8B) | 16 (8B) |
| `Dl_info.dli_saddr` | 24 (8B) | 24 (8B) | 24 (8B) |
| `sizeof struct iovec` | 16 | 16 | 16 |
| `struct iovec.iov_base` | 0 (8B) | 0 (8B) | 0 (8B) |
| `struct iovec.iov_len` | 8 (8B) | 8 (8B) | 8 (8B) |
| `sizeof struct linger` | 8 | 8 | 8 |
| `struct linger.l_onoff` | 0 (4B) | 0 (4B) | 0 (4B) |
| `struct linger.l_linger` | 4 (4B) | 4 (4B) | 4 (4B) |
| `sizeof struct rlimit` | 16 | 16 | 16 |
| `struct rlimit.rlim_cur` | 0 (8B) | 0 (8B) | 0 (8B) |
| `struct rlimit.rlim_max` | 8 (8B) | 8 (8B) | 8 (8B) |
| `sizeof rlim_t` | 8 | 8 | 8 |
| `sizeof struct rusage` | 144 | 144 | 144 |
| `struct rusage.ru_utime` | 0 (16B) | 0 (16B) | 0 (16B) |
| `struct rusage.ru_stime` | 16 (16B) | 16 (16B) | 16 (16B) |
| `struct rusage.ru_maxrss` | 32 (8B) | 32 (8B) | 32 (8B) |
| `sizeof struct sigaction` | 16 | 152 | 152 | *
| `struct sigaction.sa_handler` | 0 (8B) | 0 (8B) | 0 (8B) |
| `struct sigaction.sa_mask` | 8 (4B) | 8 (128B) | 8 (128B) | *
| `struct sigaction.sa_flags` | 12 (4B) | 136 (4B) | 136 (4B) | *
| `sizeof sigset_t` | 4 | 128 | 128 | *
| `sizeof struct utsname` | 1280 | 390 | 390 | *
| `struct utsname.sysname` | 0 (256B) | 0 (65B) | 0 (65B) | *
| `struct utsname.nodename` | 256 (256B) | 65 (65B) | 65 (65B) | *
| `struct utsname.release` | 512 (256B) | 130 (65B) | 130 (65B) | *
| `struct utsname.machine` | 1024 (256B) | 260 (65B) | 260 (65B) | *

### stat

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `struct stat.st_atimespec` | 32 (16B) | — | — | *
| `struct stat.st_mtimespec` | 48 (16B) | — | — | *
| `struct stat.st_ctimespec` | 64 (16B) | — | — | *

### poll / epoll / kevent

| item | darwin-arm64 | linux-arm64 | linux-amd64 |
|---|---|---|---|
| `sizeof struct kevent` | 32 | — | — | *
| `struct kevent.ident` | 0 (8B) | — | — | *
| `struct kevent.filter` | 8 (2B) | — | — | *
| `struct kevent.flags` | 10 (2B) | — | — | *
| `struct kevent.fflags` | 12 (4B) | — | — | *
| `struct kevent.data` | 16 (8B) | — | — | *
| `struct kevent.udata` | 24 (8B) | — | — | *
