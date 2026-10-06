// consts.c: prints every libc constant Tin hardcodes (or will need on Linux).
// Build: gcc -O0 -o consts consts.c   (darwin: cc -o consts consts.c)
// Output format: NAME <decimal> <hex>   or   NAME n/a  (not defined on this platform)
#define _GNU_SOURCE
#define _DARWIN_C_SOURCE
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <poll.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <netdb.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <dirent.h>
#include <limits.h>
#include <dlfcn.h>
#include <pthread.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <sys/un.h>
#include <sched.h>
#ifdef __linux__
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/timerfd.h>
#include <sys/random.h>
#include <sys/syscall.h>
#include <sys/prctl.h>
#else
#include <sys/event.h>
#include <pthread/qos.h>
#include <mach-o/dyld.h>
#endif

#define P(x) printf("%-28s %lld 0x%llx\n", #x, (long long)(x), (unsigned long long)(long long)(x))
#define PP(x) printf("%-28s %lld 0x%llx\n", #x, (long long)(intptr_t)(x), (unsigned long long)(intptr_t)(x))
#define NA(x) printf("%-28s n/a\n", #x)

int main(void) {
    puts("## errno");
    P(EPERM); P(ENOENT); P(ESRCH); P(EINTR); P(EIO); P(EBADF); P(ECHILD); P(EAGAIN); P(EWOULDBLOCK);
    P(ENOMEM); P(EACCES); P(EFAULT); P(EEXIST); P(EXDEV); P(ENOTDIR); P(EISDIR); P(EINVAL);
    P(ENFILE); P(EMFILE); P(ENOSPC); P(ESPIPE); P(EROFS); P(EPIPE); P(ERANGE); P(ENAMETOOLONG);
    P(ENOTEMPTY); P(ELOOP); P(ENOSYS); P(EOVERFLOW); P(ENOTSOCK); P(EADDRINUSE); P(EADDRNOTAVAIL);
    P(ENETUNREACH); P(ECONNABORTED); P(ECONNRESET); P(ENOBUFS); P(EISCONN); P(ENOTCONN);
    P(ETIMEDOUT); P(ECONNREFUSED); P(EHOSTUNREACH); P(EALREADY); P(EINPROGRESS); P(ENOTSUP); P(EOPNOTSUPP);
    P(EPROTONOSUPPORT); P(EAFNOSUPPORT); P(EMSGSIZE); P(EDEADLK); P(ENOTTY); P(E2BIG); P(ENOEXEC); P(EBUSY);
    P(ECANCELED); P(EILSEQ); P(EDOM); P(ENOLCK); P(ESTALE); P(EDQUOT);

    puts("## open flags");
    P(O_RDONLY); P(O_WRONLY); P(O_RDWR); P(O_ACCMODE); P(O_CREAT); P(O_TRUNC); P(O_APPEND); P(O_EXCL);
    P(O_NONBLOCK); P(O_NDELAY); P(O_CLOEXEC); P(O_DIRECTORY); P(O_NOFOLLOW); P(O_SYNC); P(O_NOCTTY);
#ifdef O_DSYNC
    P(O_DSYNC);
#else
    NA(O_DSYNC);
#endif
#ifdef O_PATH
    P(O_PATH);
#else
    NA(O_PATH);
#endif
#ifdef O_TMPFILE
    P(O_TMPFILE);
#else
    NA(O_TMPFILE);
#endif
#ifdef O_DIRECT
    P(O_DIRECT);
#else
    NA(O_DIRECT);
#endif
    P(O_WRONLY|O_CREAT|O_TRUNC);
    P(O_WRONLY|O_CREAT|O_APPEND);
    P(O_RDWR|O_CREAT|O_EXCL);
    P(AT_FDCWD); P(AT_SYMLINK_NOFOLLOW); P(AT_REMOVEDIR);
#ifdef AT_EMPTY_PATH
    P(AT_EMPTY_PATH);
#else
    NA(AT_EMPTY_PATH);
#endif
    P(F_OK); P(R_OK); P(W_OK); P(X_OK);
    P(SEEK_SET); P(SEEK_CUR); P(SEEK_END);

    puts("## fcntl");
    P(F_DUPFD); P(F_GETFD); P(F_SETFD); P(F_GETFL); P(F_SETFL); P(FD_CLOEXEC); P(F_DUPFD_CLOEXEC);
    P(F_GETLK); P(F_SETLK); P(F_SETLKW);

    puts("## stat modes / dirent types");
    P(S_IFMT); P(S_IFDIR); P(S_IFREG); P(S_IFLNK); P(S_IFIFO); P(S_IFSOCK); P(S_IFCHR); P(S_IFBLK);
    P(S_IRWXU); P(S_IRUSR); P(S_IWUSR); P(S_IXUSR); P(S_IRWXG); P(S_IRWXO);
    P(DT_UNKNOWN); P(DT_FIFO); P(DT_CHR); P(DT_DIR); P(DT_BLK); P(DT_REG); P(DT_LNK); P(DT_SOCK);

    puts("## socket");
    P(AF_UNSPEC); P(AF_UNIX); P(AF_INET); P(AF_INET6); P(PF_INET); P(SOCK_STREAM); P(SOCK_DGRAM);
#ifdef SOCK_NONBLOCK
    P(SOCK_NONBLOCK);
#else
    NA(SOCK_NONBLOCK);
#endif
#ifdef SOCK_CLOEXEC
    P(SOCK_CLOEXEC);
#else
    NA(SOCK_CLOEXEC);
#endif
    P(SOL_SOCKET); P(SO_REUSEADDR); P(SO_REUSEPORT); P(SO_KEEPALIVE); P(SO_ERROR); P(SO_RCVTIMEO); P(SO_SNDTIMEO);
    P(SO_RCVBUF); P(SO_SNDBUF); P(SO_LINGER); P(SO_BROADCAST); P(SO_TYPE); P(SO_ACCEPTCONN);
#ifdef SO_NOSIGPIPE
    P(SO_NOSIGPIPE);
#else
    NA(SO_NOSIGPIPE);
#endif
#ifdef MSG_NOSIGNAL
    P(MSG_NOSIGNAL);
#else
    NA(MSG_NOSIGNAL);
#endif
    P(MSG_DONTWAIT); P(MSG_PEEK); P(MSG_WAITALL); P(MSG_OOB);
    P(IPPROTO_IP); P(IPPROTO_TCP); P(IPPROTO_UDP); P(IPPROTO_IPV6);
    P(TCP_NODELAY);
#ifdef TCP_KEEPIDLE
    P(TCP_KEEPIDLE);
#else
    NA(TCP_KEEPIDLE);
#endif
#ifdef TCP_KEEPALIVE
    P(TCP_KEEPALIVE);
#else
    NA(TCP_KEEPALIVE);
#endif
    P(TCP_KEEPINTVL); P(TCP_KEEPCNT);
#ifdef TCP_FASTOPEN
    P(TCP_FASTOPEN);
#else
    NA(TCP_FASTOPEN);
#endif
#ifdef TCP_DEFER_ACCEPT
    P(TCP_DEFER_ACCEPT);
#else
    NA(TCP_DEFER_ACCEPT);
#endif
#ifdef TCP_CORK
    P(TCP_CORK);
#else
    NA(TCP_CORK);
#endif
    P(IPV6_V6ONLY);
    P(SHUT_RD); P(SHUT_WR); P(SHUT_RDWR); P(SOMAXCONN); P(INADDR_ANY); P(INADDR_LOOPBACK); P(INET_ADDRSTRLEN); P(INET6_ADDRSTRLEN);
    P(AI_PASSIVE); P(AI_CANONNAME); P(AI_NUMERICHOST); P(AI_NUMERICSERV); P(AI_ADDRCONFIG); P(AI_V4MAPPED); P(AI_ALL);
    P(EAI_AGAIN); P(EAI_FAIL); P(EAI_NONAME); P(EAI_SERVICE); P(EAI_SYSTEM); P(EAI_MEMORY); P(EAI_FAMILY); P(EAI_SOCKTYPE);
    P(NI_MAXHOST); P(NI_MAXSERV); P(NI_NUMERICHOST); P(NI_NUMERICSERV);

    puts("## poll");
    P(POLLIN); P(POLLPRI); P(POLLOUT); P(POLLERR); P(POLLHUP); P(POLLNVAL); P(POLLRDNORM); P(POLLWRNORM);
#ifdef POLLRDHUP
    P(POLLRDHUP);
#else
    NA(POLLRDHUP);
#endif

    puts("## signals");
    P(SIGHUP); P(SIGINT); P(SIGQUIT); P(SIGILL); P(SIGTRAP); P(SIGABRT); P(SIGBUS); P(SIGFPE); P(SIGKILL);
    P(SIGUSR1); P(SIGSEGV); P(SIGUSR2); P(SIGPIPE); P(SIGALRM); P(SIGTERM); P(SIGCHLD); P(SIGCONT); P(SIGSTOP);
    P(SIGTSTP); P(SIGWINCH); P(SIGURG); P(SIGXCPU); P(SIGXFSZ); P(SIGVTALRM); P(SIGPROF); P(SIGSYS);
    PP(SIG_DFL); PP(SIG_IGN); PP(SIG_ERR);
    P(SA_RESTART); P(SA_SIGINFO); P(SA_NOCLDSTOP); P(SA_NODEFER); P(SA_RESETHAND); P(SA_ONSTACK);
    P(SIG_BLOCK); P(SIG_UNBLOCK); P(SIG_SETMASK);
#ifdef NSIG
    P(NSIG);
#else
    NA(NSIG);
#endif
#ifdef SIGRTMIN
    P(SIGRTMIN); P(SIGRTMAX);
#else
    NA(SIGRTMIN); NA(SIGRTMAX);
#endif

    puts("## clocks");
    P(CLOCK_REALTIME); P(CLOCK_MONOTONIC); P(CLOCK_PROCESS_CPUTIME_ID); P(CLOCK_THREAD_CPUTIME_ID);
#ifdef CLOCK_MONOTONIC_RAW
    P(CLOCK_MONOTONIC_RAW);
#else
    NA(CLOCK_MONOTONIC_RAW);
#endif
#ifdef CLOCK_BOOTTIME
    P(CLOCK_BOOTTIME);
#else
    NA(CLOCK_BOOTTIME);
#endif
#ifdef CLOCK_MONOTONIC_COARSE
    P(CLOCK_MONOTONIC_COARSE); P(CLOCK_REALTIME_COARSE);
#else
    NA(CLOCK_MONOTONIC_COARSE); NA(CLOCK_REALTIME_COARSE);
#endif
#ifdef CLOCK_UPTIME_RAW
    P(CLOCK_UPTIME_RAW);
#else
    NA(CLOCK_UPTIME_RAW);
#endif
#ifdef TIMER_ABSTIME
    P(TIMER_ABSTIME);
#else
    NA(TIMER_ABSTIME);
#endif

    puts("## sysconf names");
    P(_SC_NPROCESSORS_ONLN); P(_SC_NPROCESSORS_CONF); P(_SC_PAGESIZE); P(_SC_PAGE_SIZE); P(_SC_CLK_TCK);
    P(_SC_OPEN_MAX); P(_SC_PHYS_PAGES); P(_SC_HOST_NAME_MAX); P(_SC_THREAD_STACK_MIN); P(_SC_ARG_MAX);
#ifdef _SC_AVPHYS_PAGES
    P(_SC_AVPHYS_PAGES);
#else
    NA(_SC_AVPHYS_PAGES);
#endif
#ifdef _SC_LEVEL1_DCACHE_LINESIZE
    P(_SC_LEVEL1_DCACHE_LINESIZE);
#else
    NA(_SC_LEVEL1_DCACHE_LINESIZE);
#endif
    puts("## sysconf runtime values on this machine");
    P(sysconf(_SC_NPROCESSORS_ONLN)); P(sysconf(_SC_NPROCESSORS_CONF)); P(sysconf(_SC_PAGESIZE)); P(sysconf(_SC_CLK_TCK)); P(sysconf(_SC_OPEN_MAX)); P(sysconf(_SC_THREAD_STACK_MIN));
    P(getpagesize());

    puts("## mmap/mprotect");
    P(PROT_NONE); P(PROT_READ); P(PROT_WRITE); P(PROT_EXEC);
    P(MAP_SHARED); P(MAP_PRIVATE); P(MAP_FIXED); P(MAP_ANON); P(MAP_ANONYMOUS); PP(MAP_FAILED);
#ifdef MAP_STACK
    P(MAP_STACK);
#else
    NA(MAP_STACK);
#endif
#ifdef MAP_NORESERVE
    P(MAP_NORESERVE);
#else
    NA(MAP_NORESERVE);
#endif
#ifdef MAP_GROWSDOWN
    P(MAP_GROWSDOWN);
#else
    NA(MAP_GROWSDOWN);
#endif
#ifdef MAP_POPULATE
    P(MAP_POPULATE);
#else
    NA(MAP_POPULATE);
#endif
#ifdef MAP_HUGETLB
    P(MAP_HUGETLB);
#else
    NA(MAP_HUGETLB);
#endif
#ifdef MAP_FIXED_NOREPLACE
    P(MAP_FIXED_NOREPLACE);
#else
    NA(MAP_FIXED_NOREPLACE);
#endif
#ifdef MAP_JIT
    P(MAP_JIT);
#else
    NA(MAP_JIT);
#endif
    P(MADV_NORMAL); P(MADV_DONTNEED); P(MADV_WILLNEED); P(MADV_SEQUENTIAL); P(MADV_RANDOM);
#ifdef MADV_FREE
    P(MADV_FREE);
#else
    NA(MADV_FREE);
#endif
#ifdef MADV_HUGEPAGE
    P(MADV_HUGEPAGE);
#else
    NA(MADV_HUGEPAGE);
#endif
    P(MS_SYNC); P(MS_ASYNC);

    puts("## epoll / eventfd / timerfd / getrandom (Linux only)");
#ifdef __linux__
    P(EPOLLIN); P(EPOLLPRI); P(EPOLLOUT); P(EPOLLERR); P(EPOLLHUP); P(EPOLLRDHUP); P(EPOLLET); P(EPOLLONESHOT);
    P(EPOLLEXCLUSIVE); P(EPOLLWAKEUP); P(EPOLL_CTL_ADD); P(EPOLL_CTL_DEL); P(EPOLL_CTL_MOD); P(EPOLL_CLOEXEC);
    P(EFD_NONBLOCK); P(EFD_CLOEXEC); P(EFD_SEMAPHORE);
    P(TFD_NONBLOCK); P(TFD_CLOEXEC); P(TFD_TIMER_ABSTIME);
#ifdef TFD_TIMER_CANCEL_ON_SET
    P(TFD_TIMER_CANCEL_ON_SET);
#endif
    P(GRND_NONBLOCK); P(GRND_RANDOM);
#ifdef GRND_INSECURE
    P(GRND_INSECURE);
#else
    NA(GRND_INSECURE);
#endif
    P(CPU_SETSIZE);
    P(SYS_getrandom); P(SYS_epoll_create1); P(SYS_epoll_ctl); P(SYS_epoll_pwait); P(SYS_sched_getaffinity);
    P(SYS_clock_gettime); P(SYS_write); P(SYS_exit_group); P(SYS_gettid); P(SYS_futex);
#ifdef SYS_epoll_wait
    P(SYS_epoll_wait);
#else
    NA(SYS_epoll_wait);
#endif
    P(PR_SET_NAME); P(PR_GET_NAME);
#else
    NA(EPOLLIN); NA(EPOLLOUT); NA(EPOLLET); NA(EPOLLRDHUP); NA(EPOLLONESHOT); NA(EPOLLERR); NA(EPOLLHUP);
    NA(EPOLL_CTL_ADD); NA(EPOLL_CTL_DEL); NA(EPOLL_CTL_MOD); NA(EPOLL_CLOEXEC);
    NA(EFD_NONBLOCK); NA(EFD_CLOEXEC); NA(EFD_SEMAPHORE); NA(TFD_NONBLOCK); NA(TFD_CLOEXEC); NA(TFD_TIMER_ABSTIME);
    NA(GRND_NONBLOCK); NA(GRND_RANDOM); NA(GRND_INSECURE); NA(CPU_SETSIZE);
#endif

    puts("## kqueue (darwin only, what Tin uses today)");
#ifndef __linux__
    P(EVFILT_READ); P(EVFILT_WRITE); P(EVFILT_TIMER); P(EVFILT_USER); P(EVFILT_SIGNAL); P(EVFILT_VNODE); P(EVFILT_PROC);
    P(EV_ADD); P(EV_DELETE); P(EV_ENABLE); P(EV_DISABLE); P(EV_ONESHOT); P(EV_CLEAR); P(EV_RECEIPT); P(EV_EOF); P(EV_ERROR);
    P(NOTE_TRIGGER); P(NOTE_SECONDS); P(NOTE_USECONDS); P(NOTE_NSECONDS); P(NOTE_ABSOLUTE);
    P(QOS_CLASS_USER_INTERACTIVE); P(QOS_CLASS_USER_INITIATED); P(QOS_CLASS_DEFAULT); P(QOS_CLASS_UTILITY); P(QOS_CLASS_BACKGROUND);
#else
    NA(EVFILT_READ); NA(EVFILT_WRITE); NA(EVFILT_TIMER); NA(EV_ADD); NA(EV_ENABLE); NA(EV_CLEAR); NA(EV_ONESHOT); NA(EV_DELETE);
    NA(QOS_CLASS_USER_INTERACTIVE);
#endif

    puts("## misc limits / dl / sched / rlimit / wait");
    P(PATH_MAX); P(NAME_MAX); P(IOV_MAX); P(PIPE_BUF);
#ifdef HOST_NAME_MAX
    P(HOST_NAME_MAX);
#else
    NA(HOST_NAME_MAX);
#endif
#ifdef MAXHOSTNAMELEN
    P(MAXHOSTNAMELEN);
#else
    NA(MAXHOSTNAMELEN);
#endif
    P(PTHREAD_STACK_MIN);
#ifdef PTHREAD_CREATE_DETACHED
    P(PTHREAD_CREATE_DETACHED); P(PTHREAD_CREATE_JOINABLE);
#endif
    PP(RTLD_DEFAULT); PP(RTLD_NEXT); P(RTLD_LAZY); P(RTLD_NOW); P(RTLD_GLOBAL); P(RTLD_LOCAL);
#ifdef RTLD_NODELETE
    P(RTLD_NODELETE);
#endif
    P(SCHED_OTHER); P(SCHED_FIFO); P(SCHED_RR);
#ifdef SCHED_BATCH
    P(SCHED_BATCH); P(SCHED_IDLE);
#else
    NA(SCHED_BATCH); NA(SCHED_IDLE);
#endif
    P(RLIMIT_NOFILE); P(RLIMIT_STACK); P(RLIMIT_AS); P(RLIMIT_CORE); PP(RLIM_INFINITY);
    P(WNOHANG); P(WUNTRACED);
    P(STDIN_FILENO); P(STDOUT_FILENO); P(STDERR_FILENO); P(EOF);
    P(sizeof(void*)); P(sizeof(long)); P(sizeof(size_t)); P(sizeof(time_t)); P(sizeof(off_t)); P(sizeof(mode_t)); P(sizeof(socklen_t)); P(sizeof(pid_t)); P(sizeof(nfds_t)); P(sizeof(suseconds_t)); P(sizeof(ino_t)); P(sizeof(dev_t)); P(sizeof(nlink_t)); P(sizeof(blksize_t)); P(sizeof(blkcnt_t)); P(sizeof(clockid_t)); P(sizeof(wchar_t)); P(sizeof(long double));
    return 0;
}
