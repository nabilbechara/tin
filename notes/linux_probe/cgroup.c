// cgroup.c: what a Linux container exposes for hearth.Cores() and a memory limit.
// Build: gcc -O0 -o cgroup cgroup.c -lpthread
// Run plain, then with --cpus=1.5, --cpuset-cpus=0,1, --memory=256m.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sched.h>
#include <pthread.h>
#include <errno.h>
#include <sys/sysinfo.h>
#include <sys/vfs.h>

static void cat(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("%-45s <%s>\n", path, strerror(errno)); return; }
    char buf[4096]; size_t n = fread(buf, 1, sizeof buf - 1, f); fclose(f);
    buf[n] = 0;
    while (n && (buf[n - 1] == '\n' || buf[n - 1] == ' ')) buf[--n] = 0;
    printf("%-45s %s\n", path, buf);
}

int main(void) {
    struct statfs sf;
    if (statfs("/sys/fs/cgroup", &sf) == 0)
        printf("%-45s 0x%lx (%s)\n", "/sys/fs/cgroup fstype", (long)sf.f_type,
               sf.f_type == 0x63677270 ? "cgroup2fs" : sf.f_type == 0x27e0eb ? "cgroupfs(v1)" : sf.f_type == 0x1021994 ? "tmpfs(v1 root)" : "?");
    cat("/proc/self/cgroup");
    puts("## cgroup v2 (unified) files, relative to the container's own cgroup root");
    cat("/sys/fs/cgroup/cgroup.controllers");
    cat("/sys/fs/cgroup/cpu.max");
    cat("/sys/fs/cgroup/cpu.weight");
    cat("/sys/fs/cgroup/cpuset.cpus");
    cat("/sys/fs/cgroup/cpuset.cpus.effective");
    cat("/sys/fs/cgroup/memory.max");
    cat("/sys/fs/cgroup/memory.high");
    cat("/sys/fs/cgroup/memory.swap.max");
    cat("/sys/fs/cgroup/memory.current");
    puts("## cgroup v1 (legacy) files");
    cat("/sys/fs/cgroup/cpu/cpu.cfs_quota_us");
    cat("/sys/fs/cgroup/cpu/cpu.cfs_period_us");
    cat("/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us");
    cat("/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_period_us");
    cat("/sys/fs/cgroup/cpuset/cpuset.cpus");
    cat("/sys/fs/cgroup/memory/memory.limit_in_bytes");
    puts("## scheduler / libc views");
    cpu_set_t set; CPU_ZERO(&set);
    long r = sched_getaffinity(0, sizeof set, &set);
    printf("%-45s rc=%ld count=%d cpus=", "sched_getaffinity(0, 128, &set)", r, CPU_COUNT(&set));
    for (int i = 0; i < CPU_SETSIZE; i++) if (CPU_ISSET(i, &set)) printf("%d,", i);
    puts("");
    cpu_set_t pset; CPU_ZERO(&pset);
    int prc = pthread_getaffinity_np(pthread_self(), sizeof pset, &pset);
    printf("%-45s rc=%d count=%d\n", "pthread_getaffinity_np(self)", prc, CPU_COUNT(&pset));
    printf("%-45s %ld\n", "sysconf(_SC_NPROCESSORS_ONLN)", sysconf(_SC_NPROCESSORS_ONLN));
    printf("%-45s %ld\n", "sysconf(_SC_NPROCESSORS_CONF)", sysconf(_SC_NPROCESSORS_CONF));
    printf("%-45s %d\n", "get_nprocs()", get_nprocs());
    printf("%-45s %d\n", "get_nprocs_conf()", get_nprocs_conf());
    printf("%-45s %ld\n", "sysconf(_SC_PHYS_PAGES)*pagesize", sysconf(_SC_PHYS_PAGES) * sysconf(_SC_PAGESIZE));
    struct sysinfo si; if (sysinfo(&si) == 0) printf("%-45s %lu (mem_unit %u)\n", "sysinfo.totalram*mem_unit", (unsigned long)si.totalram * si.mem_unit, si.mem_unit);
    cat("/sys/devices/system/cpu/online");
    cat("/sys/devices/system/cpu/possible");
    cat("/proc/sys/kernel/pid_max");
    // Pin to CPU 0 with sched_setaffinity then report (the pthread_set_qos_class_self_np replacement).
    cpu_set_t one; CPU_ZERO(&one); CPU_SET(0, &one);
    int src = sched_setaffinity(0, sizeof one, &one);
    printf("%-45s rc=%d errno=%d; now on cpu %d\n", "sched_setaffinity(0,{0})", src, src ? errno : 0, sched_getcpu());
    return 0;
}
