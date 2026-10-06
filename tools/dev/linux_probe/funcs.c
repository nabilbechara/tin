// funcs.c: for every extern Tin uses (plus the Linux replacements), report whether the symbol
// exists in the process's libc and which shared object defines it (dlsym + dladdr at runtime).
// Build (linux): gcc -O0 -o funcs funcs.c -Wl,--no-as-needed -lm -ldl -lpthread
// Build (darwin): cc -o funcs funcs.c
// Output: NAME <TAB> <defining object basename or MISSING>
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>

static const char *names[] = {
    // --- Tin externs (lib/*.tin, toolchain/compiler/*.tin) ---
    "_NSGetExecutablePath", "__error", "accept", "acos", "arc4random_buf", "asin", "atan", "atan2", "atoi",
    "bind", "calloc", "cbrt", "ceil", "chdir", "clock_gettime_nsec_np", "close", "closedir", "connect", "cos",
    "cosh", "creat", "dladdr", "exit", "exp", "exp2", "fcntl", "floor", "fmod", "free", "freeaddrinfo", "fstat",
    "getaddrinfo", "getcwd", "getenv", "gethostname", "getpid", "getsockname", "getsockopt", "gmtime_r", "hypot",
    "isatty", "kevent", "kqueue", "listen", "log", "log10", "log1p", "log2", "lstat", "malloc", "memchr", "memcmp",
    "memcpy", "memmove", "memset", "mkdir", "nanosleep", "open", "opendir", "pipe", "poll", "posix_memalign", "pow",
    "pthread_attr_init", "pthread_attr_setstacksize", "pthread_create", "pthread_set_qos_class_self_np", "read",
    "readdir", "realloc", "realpath", "rename", "rint", "rmdir", "round", "setenv", "setsockopt", "signal", "sin",
    "sinh", "snprintf", "socket", "sqrt", "stat", "strcmp", "strerror", "strftime", "strlen", "strtod", "sysconf",
    "tan", "tanh", "time", "trunc", "unlink", "unsetenv", "usleep", "write",
    // --- Linux replacements / candidates ---
    "__errno_location", "clock_gettime", "getrandom", "getentropy", "arc4random", "arc4random_uniform",
    "epoll_create", "epoll_create1", "epoll_ctl", "epoll_wait", "epoll_pwait", "epoll_pwait2",
    "timerfd_create", "timerfd_settime", "timerfd_gettime", "eventfd", "eventfd_read", "eventfd_write",
    "sched_setaffinity", "sched_getaffinity", "pthread_setaffinity_np", "pthread_getaffinity_np", "pthread_setname_np",
    "sched_yield", "sched_getcpu", "readlink", "readlinkat", "dladdr1", "dlsym", "dlopen", "dlerror",
    "__xstat", "__lxstat", "__fxstat", "__xstat64", "__fxstat64", "stat64", "lstat64", "fstat64", "fstatat", "statx",
    "readdir64", "readdir_r", "dirfd", "fdopendir", "scandir",
    "get_nprocs", "get_nprocs_conf", "get_phys_pages", "sysinfo", "getauxval", "gettid", "syscall",
    "accept4", "pipe2", "dup3", "send", "recv", "sendto", "recvfrom", "sendmsg", "recvmsg", "writev", "readv",
    "shutdown", "getpeername", "inet_pton", "inet_ntop", "htons", "ntohs", "htonl", "ntohl", "getnameinfo", "gai_strerror",
    "mmap", "munmap", "mprotect", "madvise", "mremap", "memfd_create",
    "sigaction", "sigprocmask", "pthread_sigmask", "sigemptyset", "sigaddset", "kill", "raise", "abort", "_exit",
    "prctl", "getrlimit", "setrlimit", "prlimit", "getrusage", "uname",
    "ppoll", "select", "pselect", "clock_nanosleep", "gettimeofday", "localtime_r", "timegm", "mktime", "tzset",
    "pthread_self", "pthread_join", "pthread_detach", "pthread_exit", "pthread_attr_destroy", "pthread_attr_setdetachstate",
    "pthread_attr_setguardsize", "pthread_attr_getstack", "pthread_getattr_np", "pthread_mutex_init", "pthread_mutex_lock",
    "pthread_mutex_unlock", "pthread_cond_wait", "pthread_cond_signal", "pthread_key_create", "pthread_getspecific", "pthread_setspecific",
    "__libc_start_main", "__libc_single_threaded", "__cxa_atexit", "atexit", "environ", "__environ", "program_invocation_name",
    "__stack_chk_fail", "__tls_get_addr", "_dl_find_object",
    "backtrace", "backtrace_symbols_fd", "strerror_r", "__xpg_strerror_r", "strsignal", "perror",
    "puts", "printf", "dprintf", "fflush", "setvbuf", "strtol", "strtoll", "strtoul", "strtoull", "qsort", "bsearch",
    "strchr", "strrchr", "strstr", "strncmp", "strnlen", "strdup", "memrchr", "explicit_bzero", "bzero",
    "aligned_alloc", "malloc_usable_size", "mallopt", "reallocarray",
    "openat", "mkdirat", "unlinkat", "renameat", "fchmod", "chmod", "access", "faccessat", "symlink", "link", "lseek",
    "pread", "pwrite", "ftruncate", "fsync", "fdatasync", "dup", "dup2", "utimensat", "futimens", "umask", "fork", "execve", "execvp", "waitpid",
    "getuid", "geteuid", "getppid", "isatty", "ttyname", "ioctl", "tcgetattr", "tcsetattr", "getpagesize",
    "mkstemp", "mkdtemp", "random", "srandom", "rand", "srand", "copy_file_range", "sendfile", "splice",
    // --- darwin-only names, expected MISSING on linux ---
    "__stack_chk_guard", "sysctl", "sysctlbyname", "mach_absolute_time", "mach_timebase_info", "pthread_mach_thread_np",
    "dyld_stub_binder", "_dyld_get_image_name", "os_unfair_lock_lock", "dispatch_async",
    NULL,
};

int main(void) {
    for (int i = 0; names[i]; i++) {
        void *p = dlsym(RTLD_DEFAULT, names[i]);
        if (!p) { printf("%s\tMISSING\n", names[i]); continue; }
        Dl_info di;
        memset(&di, 0, sizeof di);
        if (dladdr(p, &di) && di.dli_fname) {
            const char *b = strrchr(di.dli_fname, '/');
            printf("%s\t%s\n", names[i], b ? b + 1 : di.dli_fname);
        } else {
            printf("%s\t(found, dladdr failed)\n", names[i]);
        }
    }
    return 0;
}
