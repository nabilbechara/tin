// misc.c (Linux only): behavioural checks of the calls Tin will make on Linux, using the same raw
// byte offsets Tin would use, so the numbers in structs.txt are confirmed by live syscalls.
// Build: gcc -O0 -o misc misc.c -lpthread -ldl
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <poll.h>
#include <dirent.h>
#include <dlfcn.h>
#include <pthread.h>
#include <netdb.h>
#include <sched.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/timerfd.h>
#include <sys/random.h>
#include <sys/mman.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/utsname.h>

static uint64_t ld64(const void *p, size_t off) { uint64_t v; memcpy(&v, (const char *)p + off, 8); return v; }
static uint32_t ld32(const void *p, size_t off) { uint32_t v; memcpy(&v, (const char *)p + off, 4); return v; }
static uint16_t ld16(const void *p, size_t off) { uint16_t v; memcpy(&v, (const char *)p + off, 2); return v; }

static void *thread_main(void *arg) {
    pthread_attr_t at; size_t ss = 0; void *sa = 0;
    pthread_getattr_np(pthread_self(), &at); pthread_attr_getstack(&at, &sa, &ss); pthread_attr_destroy(&at);
    printf("thread: arg=%ld stack size=%zu (requested 8388608) cpu=%d\n", (long)(intptr_t)arg, ss, sched_getcpu());
    return 0;
}

int main(void) {
    struct utsname u; uname(&u); printf("uname: %s %s %s\n", u.sysname, u.release, u.machine);

    puts("## errno via __errno_location");
    int fd = open("/definitely/not/here", O_RDONLY);
    printf("open(missing) = %d, *__errno_location() = %d, errno = %d, ENOENT = %d, strerror = \"%s\"\n", fd, *__errno_location(), errno, ENOENT, strerror(errno));
    printf("strerror(EAGAIN=%d) = \"%s\" ; strerror(EPIPE) = \"%s\" ; strerror(ECONNREFUSED) = \"%s\"\n", EAGAIN, strerror(EAGAIN), strerror(EPIPE), strerror(ECONNREFUSED));

    puts("## clocks");
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);  printf("CLOCK_REALTIME  sec=%lld nsec=%ld (ts bytes: sec@0 nsec@8)\n", (long long)ts.tv_sec, ts.tv_nsec);
    clock_gettime(CLOCK_MONOTONIC, &ts); printf("CLOCK_MONOTONIC sec=%lld nsec=%ld\n", (long long)ts.tv_sec, ts.tv_nsec);
    clock_gettime(CLOCK_BOOTTIME, &ts);  printf("CLOCK_BOOTTIME  sec=%lld nsec=%ld\n", (long long)ts.tv_sec, ts.tv_nsec);
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts); printf("CLOCK_MONOTONIC_RAW sec=%lld nsec=%ld\n", (long long)ts.tv_sec, ts.tv_nsec);
    printf("time(0) = %lld\n", (long long)time(0));

    puts("## randomness");
    unsigned char rb[16]; memset(rb, 0, 16);
    ssize_t gr = getrandom(rb, 16, 0);
    printf("getrandom(16, 0) = %zd bytes: %02x%02x%02x%02x...\n", gr, rb[0], rb[1], rb[2], rb[3]);
    void (*a4)(void *, size_t) = (void (*)(void *, size_t))dlsym(RTLD_DEFAULT, "arc4random_buf");
    if (a4) { memset(rb, 0, 16); a4(rb, 16); printf("arc4random_buf present: %02x%02x%02x%02x...\n", rb[0], rb[1], rb[2], rb[3]); }
    else puts("arc4random_buf MISSING (glibc < 2.36)");
    int ge = getentropy(rb, 16); printf("getentropy(16) = %d\n", ge);

    puts("## stat via raw offsets");
    unsigned char st[256]; memset(st, 0xAA, sizeof st);
    int rc = stat("/etc/hostname", (struct stat *)st);
    struct stat real; stat("/etc/hostname", &real);
    printf("stat rc=%d sizeof=%zu; raw: st_mode@%zu=0%o st_size@%zu=%llu st_mtim.tv_sec@%zu=%lld ; real: mode=0%o size=%lld mtime=%lld\n",
           rc, sizeof(struct stat), offsetof(struct stat, st_mode), ld32(st, offsetof(struct stat, st_mode)),
           offsetof(struct stat, st_size), (unsigned long long)ld64(st, offsetof(struct stat, st_size)),
           offsetof(struct stat, st_mtim), (long long)ld64(st, offsetof(struct stat, st_mtim)),
           real.st_mode, (long long)real.st_size, (long long)real.st_mtime);
    printf("S_IFMT=0x%x S_IFDIR=0x%x ; stat(\"/\") is dir: %s\n", S_IFMT, S_IFDIR, (stat("/", &real) == 0 && S_ISDIR(real.st_mode)) ? "yes" : "no");
    printf("bytes past sizeof(struct stat) untouched: %s\n", st[sizeof(struct stat)] == 0xAA ? "yes" : "NO");
    rc = lstat("/proc/self/exe", &real); printf("lstat(/proc/self/exe) rc=%d is symlink=%s\n", rc, S_ISLNK(real.st_mode) ? "yes" : "no");
    rc = fstat(0, &real); printf("fstat(0) rc=%d\n", rc);

    puts("## readdir");
    DIR *d = opendir("/");
    int shown = 0;
    for (struct dirent *e; (e = readdir(d)) && shown < 4; shown++) {
        const unsigned char *raw = (const unsigned char *)e;
        printf("dirent: d_ino@0=%llu d_off@8=%lld d_reclen@16=%u d_type@18=%u d_name@19=\"%s\" strlen=%zu  (no d_namlen on Linux: use strlen or d_reclen)\n",
               (unsigned long long)ld64(raw, 0), (long long)ld64(raw, 8), ld16(raw, 16), raw[18], (const char *)raw + 19, strlen((const char *)raw + 19));
    }
    closedir(d);

    puts("## gmtime_r + strftime with Tin's Date format");
    time_t now = time(0); struct tm tm; gmtime_r(&now, &tm);
    char datebuf[100]; size_t dn = strftime(datebuf, sizeof datebuf, "Date: %a, %d %b %Y %H:%M:%S GMT\r\n", &tm);
    printf("strftime -> %zu bytes: %.*s (tm_year@%zu=%d tm_mon@%zu=%d)\n", dn, (int)dn - 2, datebuf, offsetof(struct tm, tm_year), tm.tm_year, offsetof(struct tm, tm_mon), tm.tm_mon);

    puts("## fcntl O_NONBLOCK");
    int pfd[2]; pipe(pfd);
    int fl = fcntl(pfd[0], F_GETFL);
    fcntl(pfd[0], F_SETFL, fl | O_NONBLOCK);
    printf("F_GETFL before=0x%x after=0x%x (O_NONBLOCK=0x%x; darwin used 4 which is O_NONBLOCK there but O_ACCMODE-garbage here)\n", fl, fcntl(pfd[0], F_GETFL), O_NONBLOCK);
    char c; ssize_t rr = read(pfd[0], &c, 1); printf("read(empty nonblocking pipe) = %zd errno=%d (EAGAIN=%d)\n", rr, errno, EAGAIN);
    int pfd2[2]; rc = pipe2(pfd2, O_NONBLOCK | O_CLOEXEC); printf("pipe2(O_NONBLOCK|O_CLOEXEC) rc=%d\n", rc);

    puts("## sockets: BSD-style sockaddr_in (sin_len=16, family at byte 1) vs Linux layout");
    int s = socket(AF_INET, SOCK_STREAM, 0);
    unsigned char sa[16]; memset(sa, 0, 16);
    sa[0] = 16; sa[1] = 2; sa[2] = 0; sa[3] = 0;        // Tin's current darwin layout, port 0
    rc = bind(s, (struct sockaddr *)sa, 16);
    printf("bind with darwin layout: rc=%d errno=%d (%s)\n", rc, rc ? errno : 0, rc ? strerror(errno) : "ok");
    memset(sa, 0, 16); sa[0] = 2; sa[1] = 0;            // Linux: sin_family is a u16 at offset 0
    rc = bind(s, (struct sockaddr *)sa, 16);
    printf("bind with linux layout : rc=%d errno=%d (%s)\n", rc, rc ? errno : 0, rc ? strerror(errno) : "ok");
    unsigned char got[16]; socklen_t gl = 16; getsockname(s, (struct sockaddr *)got, &gl);
    printf("getsockname: family@0=%u port@2=%u (network order) len=%u\n", ld16(got, 0), (got[2] << 8) | got[3], gl);
    int one = 1;
    printf("setsockopt SO_REUSEADDR(%d)=%d SO_REUSEPORT(%d)=%d SO_KEEPALIVE(%d)=%d TCP_NODELAY=%d\n", SO_REUSEADDR,
           setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, 4), SO_REUSEPORT, setsockopt(s, SOL_SOCKET, SO_REUSEPORT, &one, 4),
           SO_KEEPALIVE, setsockopt(s, SOL_SOCKET, SO_KEEPALIVE, &one, 4), setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, 4));
    unsigned char tv[16]; memset(tv, 0, 16); ld64(tv, 0); *(int64_t *)tv = 1; *(int64_t *)(tv + 8) = 500000;   // tv_sec@0 (8), tv_usec@8 (8 on Linux!)
    printf("setsockopt SO_RCVTIMEO(%d) with 16-byte timeval = %d ; SO_SNDTIMEO(%d) = %d\n", SO_RCVTIMEO, setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, tv, 16), SO_SNDTIMEO, setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, tv, 16));
    int soerr = -1; socklen_t sl = 4; getsockopt(s, SOL_SOCKET, SO_ERROR, &soerr, &sl); printf("getsockopt SO_ERROR(%d) = %d\n", SO_ERROR, soerr);
    printf("setsockopt with darwin SOL_SOCKET=0xffff: rc=%d errno=%d (%s)\n", setsockopt(s, 0xffff, 4, &one, 4), errno, strerror(errno));
    // MSG_NOSIGNAL instead of SO_NOSIGPIPE: write to a socket whose peer is gone.
    signal(SIGPIPE, SIG_IGN);
    printf("signal(SIGPIPE=%d, SIG_IGN=%ld) ok; write to closed pipe: ", SIGPIPE, (long)SIG_IGN);
    close(pfd[0]); rr = write(pfd[1], "x", 1); printf("rc=%zd errno=%d (EPIPE=%d)\n", rr, errno, EPIPE);
    int sv[2]; socketpair(AF_UNIX, SOCK_STREAM, 0, sv); close(sv[1]);
    rr = send(sv[0], "x", 1, MSG_NOSIGNAL); printf("send(MSG_NOSIGNAL=%d) to closed peer rc=%zd errno=%d (EPIPE=%d)\n", MSG_NOSIGNAL, rr, errno, EPIPE);
    close(s);

    puts("## getaddrinfo: ai_addr pointer offset (24 on Linux, 32 on darwin)");
    unsigned char hints[48]; memset(hints, 0, 48); *(int *)(hints + 4) = AF_INET; *(int *)(hints + 8) = SOCK_STREAM;
    struct addrinfo *res = 0;
    rc = getaddrinfo("localhost", 0, (struct addrinfo *)hints, &res);
    if (rc == 0 && res) {
        const unsigned char *ai = (const unsigned char *)res;
        const unsigned char *addr24 = (const unsigned char *)(uintptr_t)ld64(ai, 24);
        const unsigned char *addr32 = (const unsigned char *)(uintptr_t)ld64(ai, 32);
        printf("rc=0 ai_family@4=%d ai_addrlen@16=%u ; [ai+24] -> family=%u addr=%u.%u.%u.%u ; [ai+32] (ai_canonname) = %p\n",
               ld32(ai, 4), ld32(ai, 16), ld16(addr24, 0), addr24[4], addr24[5], addr24[6], addr24[7], (const void *)addr32);
        freeaddrinfo(res);
    } else printf("getaddrinfo rc=%d (%s)\n", rc, gai_strerror(rc));

    puts("## epoll + eventfd + timerfd via raw epoll_event bytes");
    int ep = epoll_create1(EPOLL_CLOEXEC);
    int ev = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
    int tf = timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC);
    unsigned char e[16]; memset(e, 0, 16);
    *(uint32_t *)e = EPOLLIN | EPOLLET; memcpy(e + offsetof(struct epoll_event, data), &ev, 4);      // data.fd
    printf("sizeof(epoll_event)=%zu data@%zu ; ", sizeof(struct epoll_event), offsetof(struct epoll_event, data));
    rc = epoll_ctl(ep, EPOLL_CTL_ADD, ev, (struct epoll_event *)e); printf("ctl ADD eventfd rc=%d ; ", rc);
    *(uint32_t *)e = EPOLLIN; memcpy(e + offsetof(struct epoll_event, data), &tf, 4);
    rc = epoll_ctl(ep, EPOLL_CTL_ADD, tf, (struct epoll_event *)e); printf("ctl ADD timerfd rc=%d\n", rc);
    struct itimerspec its; memset(&its, 0, sizeof its); its.it_value.tv_nsec = 20 * 1000000; its.it_interval.tv_nsec = 20 * 1000000;
    rc = timerfd_settime(tf, 0, &its, 0); printf("timerfd_settime(20ms periodic) rc=%d (itimerspec it_interval@%zu it_value@%zu size %zu)\n", rc, offsetof(struct itimerspec, it_interval), offsetof(struct itimerspec, it_value), sizeof its);
    uint64_t v = 1; rr = write(ev, &v, 8); printf("eventfd write(8 bytes) rc=%zd ; ", rr);
    unsigned char evs[16 * 8]; memset(evs, 0, sizeof evs);
    int n = epoll_wait(ep, (struct epoll_event *)evs, 8, 1000);
    printf("epoll_wait -> %d: ", n);
    for (int i = 0; i < n; i++) printf("[events=0x%x fd=%d] ", ld32(evs, i * sizeof(struct epoll_event)), ld32(evs, i * sizeof(struct epoll_event) + offsetof(struct epoll_event, data)));
    puts("");
    rr = read(ev, &v, 8); printf("eventfd read -> %zd bytes value=%llu ; ", rr, (unsigned long long)v);
    n = epoll_wait(ep, (struct epoll_event *)evs, 8, 200);
    uint64_t exp = 0; rr = read(tf, &exp, 8);
    printf("second wait -> %d (timerfd fd=%d) read expirations rc=%zd count=%llu\n", n, tf, rr, (unsigned long long)exp);
    rc = epoll_ctl(ep, EPOLL_CTL_DEL, tf, 0); printf("ctl DEL rc=%d ; epoll_pwait2 present=%s\n", rc, dlsym(RTLD_DEFAULT, "epoll_pwait2") ? "yes" : "no");
    unsigned char pf[8]; memset(pf, 0, 8); *(int *)pf = ev; *(short *)(pf + 4) = POLLOUT;
    rc = poll((struct pollfd *)pf, 1, 0); printf("poll(eventfd, POLLOUT) rc=%d revents@6=0x%x\n", rc, *(short *)(pf + 6));

    puts("## threads / affinity / memory");
    pthread_attr_t attr; pthread_attr_init(&attr); pthread_attr_setstacksize(&attr, 8388608);
    pthread_t t; rc = pthread_create(&t, &attr, thread_main, (void *)7); pthread_join(t, 0); printf("pthread_create rc=%d sizeof(pthread_attr_t)=%zu\n", rc, sizeof attr);
    cpu_set_t cs; CPU_ZERO(&cs); sched_getaffinity(0, sizeof cs, &cs); printf("sched_getaffinity count=%d sizeof(cpu_set_t)=%zu ; sysconf(_SC_NPROCESSORS_ONLN=%d)=%ld\n", CPU_COUNT(&cs), sizeof cs, _SC_NPROCESSORS_ONLN, sysconf(_SC_NPROCESSORS_ONLN));
    void *pm = 0; rc = posix_memalign(&pm, 128, 1024); printf("posix_memalign(128,1024) rc=%d aligned=%s\n", rc, ((uintptr_t)pm & 127) == 0 ? "yes" : "no");
    void *mm = mmap(0, 1 << 20, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
    printf("mmap(1MiB, RW, PRIVATE|ANON|STACK) = %s ; mprotect(RW->R) = %d\n", mm == MAP_FAILED ? "FAILED" : "ok", mprotect(mm, 1 << 20, PROT_READ));
    char exe[4096]; ssize_t el = readlink("/proc/self/exe", exe, sizeof exe - 1); if (el > 0) exe[el] = 0; printf("readlink(/proc/self/exe) = %s (%zd bytes, NOT nul-terminated by the call)\n", exe, el);
    char cwd[4096]; printf("getcwd = %s ; ", getcwd(cwd, sizeof cwd)); char hn[256]; printf("gethostname rc=%d (%s) ; getpid=%d\n", gethostname(hn, sizeof hn), hn, getpid());
    char *rp = realpath("/proc/self/exe", 0); printf("realpath(/proc/self/exe) = %s\n", rp); free(rp);
    struct timespec sl2 = {0, 1000000}; rc = nanosleep(&sl2, 0); printf("nanosleep(1ms) rc=%d ; usleep(100) rc=%d\n", rc, usleep(100));
    char nb[64]; n = snprintf(nb, sizeof nb, "%lld|%d|%s|%.2f", (long long)123456789012LL, 42, "s", 3.14159); printf("snprintf -> %d: %s\n", n, nb);
    printf("isatty(1)=%d ; strtod(\"2.5e3\")=%g ; atoi(\"-17\")=%d\n", isatty(1), strtod("2.5e3", 0), atoi("-17"));
    return 0;
}
