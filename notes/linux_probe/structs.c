// structs.c: sizeof/offsetof of every libc struct field Tin touches through raw offsets.
// Build: gcc -O0 -o structs structs.c   (darwin: cc -o structs structs.c)
// Output: "sizeof <type> <bytes>" and "offsetof <type> <field> <offset> size <fieldsize>".
#define _GNU_SOURCE
#define _DARWIN_C_SOURCE
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <time.h>
#include <poll.h>
#include <signal.h>
#include <pthread.h>
#include <dirent.h>
#include <dlfcn.h>
#include <netdb.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/uio.h>
#include <sys/resource.h>
#include <sys/utsname.h>
#include <netinet/in.h>
#ifdef __linux__
#include <sys/epoll.h>
#include <sys/timerfd.h>
#include <sched.h>
#include <sys/sysinfo.h>
#else
#include <sys/event.h>
#endif

#define S(t) printf("sizeof %-24s %zu\n", #t, sizeof(t))
#define O(t, f) printf("offsetof %-20s %-16s %zu size %zu\n", #t, #f, offsetof(t, f), sizeof(((t *)0)->f))
#define NA(t, f) printf("offsetof %-20s %-16s n/a\n", #t, #f)

int main(void) {
    puts("## sockaddr");
    S(struct sockaddr); O(struct sockaddr, sa_family); O(struct sockaddr, sa_data);
#ifndef __linux__
    O(struct sockaddr, sa_len);
#else
    NA(struct sockaddr, sa_len);
#endif
    S(struct sockaddr_in);
#ifndef __linux__
    O(struct sockaddr_in, sin_len);
#else
    NA(struct sockaddr_in, sin_len);
#endif
    O(struct sockaddr_in, sin_family); O(struct sockaddr_in, sin_port); O(struct sockaddr_in, sin_addr); O(struct sockaddr_in, sin_zero);
    S(struct sockaddr_in6); O(struct sockaddr_in6, sin6_family); O(struct sockaddr_in6, sin6_port); O(struct sockaddr_in6, sin6_flowinfo); O(struct sockaddr_in6, sin6_addr); O(struct sockaddr_in6, sin6_scope_id);
    S(struct sockaddr_storage); S(struct sockaddr_un); O(struct sockaddr_un, sun_family); O(struct sockaddr_un, sun_path);
    S(sa_family_t); S(in_port_t); S(in_addr_t); S(socklen_t); S(struct in_addr); S(struct in6_addr);

    puts("## addrinfo");
    S(struct addrinfo); O(struct addrinfo, ai_flags); O(struct addrinfo, ai_family); O(struct addrinfo, ai_socktype); O(struct addrinfo, ai_protocol);
    O(struct addrinfo, ai_addrlen); O(struct addrinfo, ai_addr); O(struct addrinfo, ai_canonname); O(struct addrinfo, ai_next);

    puts("## stat");
    S(struct stat); O(struct stat, st_dev); O(struct stat, st_ino); O(struct stat, st_mode); O(struct stat, st_nlink); O(struct stat, st_uid); O(struct stat, st_gid);
    O(struct stat, st_rdev); O(struct stat, st_size); O(struct stat, st_blksize); O(struct stat, st_blocks);
#ifdef __linux__
    O(struct stat, st_atim); O(struct stat, st_mtim); O(struct stat, st_ctim);
    NA(struct stat, st_birthtimespec); NA(struct stat, st_flags); NA(struct stat, st_gen);
#else
    O(struct stat, st_atimespec); O(struct stat, st_mtimespec); O(struct stat, st_ctimespec); O(struct stat, st_birthtimespec); O(struct stat, st_flags); O(struct stat, st_gen);
#endif
    printf("offsetof %-20s %-16s %zu size %zu\n", "struct stat", "st_mtime(sec)", offsetof(struct stat, st_mtime), sizeof(((struct stat *)0)->st_mtime));
    S(off_t); S(ino_t); S(dev_t); S(mode_t); S(nlink_t); S(uid_t); S(gid_t); S(blksize_t); S(blkcnt_t); S(time_t);

    puts("## dirent (as returned by readdir)");
    S(struct dirent); O(struct dirent, d_ino); O(struct dirent, d_reclen); O(struct dirent, d_type); O(struct dirent, d_name);
#ifdef __linux__
    O(struct dirent, d_off); NA(struct dirent, d_namlen); NA(struct dirent, d_seekoff);
#else
    O(struct dirent, d_seekoff); O(struct dirent, d_namlen); NA(struct dirent, d_off);
#endif
    S(DIR *);

    puts("## time");
    S(struct timespec); O(struct timespec, tv_sec); O(struct timespec, tv_nsec);
    S(struct timeval); O(struct timeval, tv_sec); O(struct timeval, tv_usec);
    S(struct tm); O(struct tm, tm_sec); O(struct tm, tm_min); O(struct tm, tm_hour); O(struct tm, tm_mday); O(struct tm, tm_mon); O(struct tm, tm_year); O(struct tm, tm_wday); O(struct tm, tm_yday); O(struct tm, tm_isdst); O(struct tm, tm_gmtoff); O(struct tm, tm_zone);
    S(struct itimerval); S(clockid_t); S(suseconds_t);
#ifdef __linux__
    S(struct itimerspec); O(struct itimerspec, it_interval); O(struct itimerspec, it_value);
#else
    printf("sizeof %-24s n/a (no POSIX timers on darwin)\n", "struct itimerspec"); NA(struct itimerspec, it_interval); NA(struct itimerspec, it_value);
#endif

    puts("## poll / epoll / kevent");
    S(struct pollfd); O(struct pollfd, fd); O(struct pollfd, events); O(struct pollfd, revents); S(nfds_t);
#ifdef __linux__
    S(struct epoll_event); O(struct epoll_event, events); O(struct epoll_event, data); S(epoll_data_t);
    printf("alignof struct epoll_event %zu\n", _Alignof(struct epoll_event));
    S(cpu_set_t); S(struct sysinfo);
#else
    S(struct kevent); O(struct kevent, ident); O(struct kevent, filter); O(struct kevent, flags); O(struct kevent, fflags); O(struct kevent, data); O(struct kevent, udata);
#endif

    puts("## pthread / dl / misc");
    S(pthread_t); S(pthread_attr_t); S(pthread_mutex_t); S(pthread_cond_t); S(pthread_key_t); S(pthread_once_t);
    printf("alignof pthread_attr_t %zu\n", _Alignof(pthread_attr_t));
    S(Dl_info); O(Dl_info, dli_fname); O(Dl_info, dli_fbase); O(Dl_info, dli_sname); O(Dl_info, dli_saddr);
    S(struct iovec); O(struct iovec, iov_base); O(struct iovec, iov_len);
    S(struct linger); O(struct linger, l_onoff); O(struct linger, l_linger);
    S(struct rlimit); O(struct rlimit, rlim_cur); O(struct rlimit, rlim_max); S(rlim_t);
    S(struct rusage); O(struct rusage, ru_utime); O(struct rusage, ru_stime); O(struct rusage, ru_maxrss);
    S(struct sigaction); O(struct sigaction, sa_handler); O(struct sigaction, sa_mask); O(struct sigaction, sa_flags); S(sigset_t); S(struct utsname); O(struct utsname, sysname); O(struct utsname, nodename); O(struct utsname, release); O(struct utsname, machine);
    return 0;
}
