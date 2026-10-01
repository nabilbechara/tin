#!/bin/sh
# glibc231.sh: the same template + stat/unversioned checks on an older glibc (Ubuntu 20.04 = glibc 2.31).
# docker run --rm --platform linux/<arch> -v $PWD:/p -w /p ubuntu:20.04 sh glibc231.sh
export DEBIAN_FRONTEND=noninteractive
apt-get update > /dev/null 2>&1 && apt-get install -y --no-install-recommends gcc libc6-dev binutils python3 > /dev/null 2>&1
ARCH=$(uname -m); case "$ARCH" in aarch64) PLAT=linux-arm64; ASM=start_arm64.S;; x86_64) PLAT=linux-amd64; ASM=start_amd64.S;; esac
GL=$(ldd --version | head -1 | awk '{print $NF}'); OUT=/p/out/$PLAT-glibc$GL; T=/tmp/probe; mkdir -p $T "$OUT"
{
  ldd --version | head -1; gcc --version | head -1; cat /etc/os-release | head -2
  echo "=== hand-written _start template on glibc $GL"; gcc -nostartfiles -o $T/start $ASM && $T/start; echo "exit=$?"
  LD_DEBUG=bindings $T/start 2>&1 | grep -E "puts|__libc_start_main" | grep -v "to $T" | sed 's/.*normal symbol//'
  echo; echo "=== spcheck (C main from hand-written _start, init/fini = NULL)"; gcc -nostartfiles -o $T/spcheck crt_only.S spcheck.c && $T/spcheck a b | grep -E "sp mod|argc|environ|getenv|memcpy"; echo "exit=$?"
  echo; echo "=== stat/lstat/fstat/readdir symbols a gcc binary imports on glibc $GL (expect __xstat family):"
  printf '#include <sys/stat.h>\n#include <dirent.h>\n#include <stdio.h>\nint main(void){struct stat s; stat("/",&s); lstat("/",&s); fstat(0,&s); DIR*d=opendir("/"); readdir(d); printf("_STAT_VER=%%d size=%%zu\\n", _STAT_VER, sizeof s); return 0;}\n' > $T/st.c
  gcc -O0 -o $T/st $T/st.c && nm -D $T/st | grep -E "stat|readdir"; $T/st
  LIBC=$(ls /lib/*-linux-gnu*/libc.so.6 | head -1); echo "libc exports named stat/lstat/fstat/__xstat/arc4random/getrandom/epoll_pwait2/__libc_start_main/pthread_create/dladdr:"
  readelf -W --dyn-syms $LIBC | awk '{print $8}' | grep -E "^(stat|lstat|fstat|__xstat|__lxstat|__fxstat|arc4random_buf|getrandom|getentropy|epoll_pwait2|__libc_start_main|pthread_create|dladdr|sched_getaffinity|clock_gettime|memcpy|realpath)(@|$)" | sort | tr '\n' ' '; echo
  echo "pthread_create / dladdr live in:"; for l in libpthread.so.0 libdl.so.2; do f=$(ls /lib/*-linux-gnu*/$l | head -1); echo "  $l: $(readelf -W --dyn-syms $f | awk '{print $8}' | grep -E '^(pthread_create|pthread_attr_setstacksize|dladdr|dlsym)@' | tr '\n' ' ')"; done
  echo; echo "=== unversioned binding on glibc $GL (realpath(path,NULL) + dlvsym):"
  sed -n "/^#define _GNU_SOURCE/,/^}/p" bindings.sh > $T/multi.c
  gcc -O0 -fno-plt -Wl,-z,now -o $T/multi $T/multi.c -lm -ldl -lpthread && cp $T/multi $T/multi_unv && python3 elfpatch.py $T/multi_unv droptag 0x6ffffff0 droptag 0x6ffffffe droptag 0x6fffffff > /dev/null
  echo "--- versioned:"; $T/multi | grep -E "realpath|bound|sched"; echo "--- unversioned:"; $T/multi_unv | grep -E "realpath|bound|sched"; echo "exit=$?"
} > "$OUT/glibc231.txt" 2>&1
echo done $OUT
