#!/bin/sh
# bindings.sh: (1) which libc symbol versions an UNVERSIONED reference binds to (DT_VERSYM/VERNEED removed),
# for the symbols that have several versions in glibc; (2) whether a 1-bucket DT_HASH is enough for ld.so + dladdr.
# docker run --rm -v $PWD:/p -w /p <image> sh bindings.sh
ARCH=$(uname -m); case "$ARCH" in aarch64) PLAT=linux-arm64;; x86_64) PLAT=linux-amd64;; esac
GL=$(ldd --version | head -1 | awk '{print $NF}'); OUT=/p/out/$PLAT-glibc$GL; T=/tmp/probe; mkdir -p $T "$OUT"
cat > $T/multi.c <<'CEOF'
#define _GNU_SOURCE
#include <stdio.h>
#include <errno.h>
#include <sched.h>
#include <string.h>
#include <math.h>
#include <pthread.h>
#include <dlfcn.h>
#include <stdlib.h>
static void *thr(void *a) { return a; }
int main(int argc, char **argv) {
    char b[16]; memcpy(b, "hello-memcpy", 13);
    pthread_t t; pthread_create(&t, 0, thr, 0); pthread_join(t, 0);
    volatile double x = argc;
    printf("%s exp=%g log=%g pow=%g fmod=%g hypot=%g log2=%g\n", b, exp(x), log(x + 1), pow(x, 2), fmod(7.5, x + 1), hypot(x, x), log2(x + 7));
    Dl_info di; dladdr((void *)main, &di); char *r = realpath("/proc/self/exe", 0);
    printf("dladdr fname=%s realpath(path,NULL)=%s\n", di.dli_fname, r);
    /* Which version did each GOT slot bind to?  Compare the bound address with dlvsym() of every candidate. */
    const char *vers[] = {"GLIBC_2.2.5", "GLIBC_2.3", "GLIBC_2.3.3", "GLIBC_2.3.4", "GLIBC_2.14", "GLIBC_2.17", "GLIBC_2.29", "GLIBC_2.34", "GLIBC_2.35", "GLIBC_2.38", 0};
    struct { const char *n; void *p; } syms[] = {{"realpath", (void *)realpath}, {"memcpy", (void *)memcpy}, {"__libc_start_main", dlsym(RTLD_DEFAULT, "__libc_start_main")},
        {"exp", (void *)exp}, {"fmod", (void *)fmod}, {"hypot", (void *)hypot}, {"pthread_create", (void *)pthread_create}, {"dladdr", (void *)dladdr},
        {"sched_getaffinity", (void *)sched_getaffinity}, {"pthread_setaffinity_np", (void *)pthread_setaffinity_np}, {0, 0}};
    for (int v = 0; vers[v]; v++) { void *q = dlvsym(RTLD_DEFAULT, "__libc_start_main", vers[v]); if (q) printf("dlvsym(__libc_start_main, %s) = %p\n", vers[v], q); }
    for (int i = 0; syms[i].n; i++) {
        printf("bound %-24s -> ", syms[i].n);
        if (!strcmp(syms[i].n, "__libc_start_main")) { printf("(dlsym: default version)\n"); continue; }
        int hit = 0;
        for (int v = 0; vers[v]; v++) { void *q = dlvsym(RTLD_DEFAULT, syms[i].n, vers[v]); if (q && q == syms[i].p) { printf("%s ", vers[v]); hit++; } }
        puts(hit ? "" : "(no dlvsym candidate matched: IFUNC-resolved or other version)");
    }
    cpu_set_t set; CPU_ZERO(&set); errno = 0; int rc = sched_getaffinity(0, sizeof set, &set);
    printf("sched_getaffinity(0, 128, &set) rc=%d errno=%d count=%d\n", rc, errno, CPU_COUNT(&set));
    return 0;
}
CEOF
gcc -O0 -fno-plt -Wl,-z,now -o $T/multi $T/multi.c -lm -ldl -lpthread
cp $T/multi $T/multi_unv; python3 /p/elfpatch.py $T/multi_unv droptag 0x6ffffff0 droptag 0x6ffffffe droptag 0x6fffffff > /dev/null
PAT="symbol .(memcpy|__libc_start_main|exp|log|pow|fmod|hypot|log2|pthread_create|dladdr|realpath)'"
{
  echo "glibc $GL $ARCH"
  echo "=== versioned (normal gcc link): run, then LD_DEBUG=bindings"; $T/multi
  LD_DEBUG=bindings $T/multi 2>&1 | grep -E "$PAT" | sed 's/.*normal symbol//' | sort
  echo; echo "=== UNVERSIONED (DT_VERSYM/DT_VERNEED/DT_VERNEEDNUM tags removed): run, then LD_DEBUG=bindings"; $T/multi_unv; echo "exit=$?"
  LD_DEBUG=bindings $T/multi_unv 2>&1 | grep -E "$PAT" | sed 's/.*normal symbol//' | sort
  echo; echo "=== readelf -d of the unversioned binary (no version tags left):"; readelf -d $T/multi_unv | grep -iE "ver|NEEDED"
  echo; echo "=== version needs ld recorded in the versioned binary:"; readelf -V $T/multi | sed -n '/Version needs/,$p'
} > "$OUT/bindings_unversioned.txt" 2>&1
gcc -O0 -rdynamic -Wl,--hash-style=sysv -o $T/dl_sysv /p/dladdr_test.c /p/nosize_fn.S -ldl
cp $T/dl_sysv $T/dl_hash1
gcc -nostartfiles -Wl,--hash-style=sysv -o $T/sp_sysv /p/crt_only.S /p/spcheck.c
cp $T/sp_sysv $T/sp_hash1
{
  echo "glibc $GL $ARCH"
  echo "=== DT_HASH rewritten in place to nbucket=1 (every symbol on one chain): dladdr test"; python3 /p/elfpatch.py $T/dl_hash1 hash1 -; $T/dl_hash1 | grep -v "libc.so"; echo "exit=$?"
  echo; echo "=== spcheck with the 1-bucket DT_HASH (environ COPY-reloc lookup through the exe's hash must still work)"; python3 /p/elfpatch.py $T/sp_hash1 hash1 -; $T/sp_hash1 | grep -E "environ|memcpy|argc"; echo "exit=$?"
  echo; echo "=== .hash bytes after the rewrite"; objdump -s -j .hash $T/dl_hash1 | tail -n +4
} > "$OUT/hash1.txt" 2>&1
echo done $OUT
