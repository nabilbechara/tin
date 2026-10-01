#!/bin/sh
# run_all.sh: runs every probe inside a Linux container and writes raw outputs to out/<platform>-glibc<ver>/.
# docker run --rm -v $PWD:/p -w /p golang:1.27 sh run_all.sh
set -u
ARCH=$(uname -m)
case "$ARCH" in aarch64) PLAT=linux-arm64; ASM=start_arm64.S;; x86_64) PLAT=linux-amd64; ASM=start_amd64.S;; *) echo "unknown arch $ARCH"; exit 1;; esac
GL=$(ldd --version | head -1 | awk '{print $NF}')
OUT=/p/out/$PLAT-glibc$GL
mkdir -p "$OUT"
T=/tmp/probe; mkdir -p $T
log() { echo "### $*"; }

{
  ldd --version | head -1; gcc --version | head -1; ld --version | head -1
  echo "debian $(cat /etc/debian_version)"; uname -a; echo "PAGESIZE $(getconf PAGESIZE)"
  LIBC=$(ls /lib/*-linux-gnu*/libc.so.6 /lib64/libc.so.6 /usr/lib*/libc.so.6 2>/dev/null | head -1); echo "libc: $LIBC -> $(readlink -f $LIBC)"
  LIBM=$(ls /lib/*-linux-gnu*/libm.so.6 /lib64/libm.so.6 /usr/lib*/libm.so.6 2>/dev/null | head -1); echo "libm: $LIBM -> $(readlink -f $LIBM)"
  ls -la /lib/ld-linux-aarch64.so.1 /lib64/ld-linux-x86-64.so.2 2>/dev/null
  echo "libc DT_NEEDED/SONAME:"; readelf -d $LIBC | grep -E 'NEEDED|SONAME'
  echo "libm DT_NEEDED/SONAME:"; readelf -d $LIBM | grep -E 'NEEDED|SONAME'
  echo "libpthread/libdl stubs:"; ls -la /lib/*-linux-gnu*/libpthread.so.0 /lib/*-linux-gnu*/libdl.so.2 2>&1; readelf --dyn-syms -W /lib/*-linux-gnu*/libpthread.so.0 2>/dev/null | grep -c FUNC
} > "$OUT/versions.txt" 2>&1

LIBC=$(ls /lib/*-linux-gnu*/libc.so.6 /lib64/libc.so.6 2>/dev/null | head -1)
LIBM=$(ls /lib/*-linux-gnu*/libm.so.6 /lib64/libm.so.6 2>/dev/null | head -1)
readelf -W --dyn-syms "$LIBC" > "$OUT/libc_dynsyms.txt"
readelf -W --dyn-syms "$LIBM" > "$OUT/libm_dynsyms.txt"
readelf -W -V "$LIBC" | head -80 > "$OUT/libc_versions.txt"

log consts;  gcc -O0 -o $T/consts consts.c && $T/consts > "$OUT/consts.txt"
log structs; gcc -O0 -o $T/structs structs.c && $T/structs > "$OUT/structs.txt"
log funcs;   gcc -O0 -o $T/funcs funcs.c -Wl,--no-as-needed -lm -ldl -lpthread && $T/funcs > "$OUT/funcs.txt"
log misc;    gcc -O0 -o $T/misc misc.c -lpthread -ldl && $T/misc > "$OUT/misc.txt" 2>&1
log cgroup;  gcc -O0 -o $T/cgroup cgroup.c -lpthread && $T/cgroup > "$OUT/cgroup_$(cat /p/cgroup_label 2>/dev/null || echo plain).txt" 2>&1

log hello-elf
gcc -O0 -o $T/hello hello.c -lm
{ echo "=== gcc default (PIE) hello: readelf -lhdSW --dyn-syms -r"; readelf -lhdSW --dyn-syms -r $T/hello; echo; echo "=== imported symbol versions in the binary (nm -D)"; nm -D $T/hello; echo; echo "=== .plt/.plt.got disassembly"; objdump -d -j .plt -j .plt.got -j .plt.sec $T/hello 2>/dev/null; } > "$OUT/hello_pie_readelf.txt" 2>&1
gcc -O0 -no-pie -o $T/hello_nopie hello.c -lm
{ echo "=== gcc -no-pie hello: readelf -lhdSW --dyn-syms -r"; readelf -lhdSW --dyn-syms -r $T/hello_nopie; } > "$OUT/hello_nopie_readelf.txt" 2>&1
gcc -O0 -fno-plt -Wl,-z,now -o $T/hello_noplt hello.c -lm
{ echo "=== gcc -fno-plt -z now hello (GLOB_DAT only, no JUMP_SLOT): readelf -dW -r"; readelf -dW -r $T/hello_noplt; echo; objdump -d $T/hello_noplt | grep -A12 '<main>:'; } > "$OUT/hello_noplt_readelf.txt" 2>&1
{ echo "=== $(gcc -print-file-name=Scrt1.o) (PIE crt) _start"; objdump -dr $(gcc -print-file-name=Scrt1.o); echo; echo "=== $(gcc -print-file-name=crt1.o) (non-PIE crt) _start"; objdump -dr $(gcc -print-file-name=crt1.o); } > "$OUT/crt1_objdump.txt" 2>&1

log handwritten-start
gcc -nostartfiles -o $T/start $ASM && cp $T/start "$OUT/start_pie.bin"
{ echo "=== build: gcc -nostartfiles -o start $ASM (PIE)"; echo "--- run:"; $T/start; echo "exit=$?"; echo "--- LD_DEBUG=bindings (which symbol versions got bound):"; LD_DEBUG=bindings $T/start 2>&1 | grep -E "puts|__libc_start_main" | grep -v "to $T" ; echo; readelf -lhdSW --dyn-syms -r $T/start; echo; echo "=== objdump -d"; objdump -d $T/start; echo; echo "=== hexdump of .dynamic, .got, .rela.dyn"; objdump -s -j .dynamic -j .got -j .rela.dyn -j .interp -j .dynsym -j .dynstr -j .gnu.hash -j .hash $T/start; } > "$OUT/start_pie.txt" 2>&1
gcc -nostartfiles -no-pie -o $T/start_nopie $ASM && cp $T/start_nopie "$OUT/start_nopie.bin"
{ echo "=== build: gcc -nostartfiles -no-pie -o start_nopie $ASM"; echo "--- run:"; $T/start_nopie; echo "exit=$?"; readelf -lhdSW --dyn-syms -r $T/start_nopie; echo; objdump -d $T/start_nopie; } > "$OUT/start_nopie.txt" 2>&1
gcc -nostartfiles -Wl,-z,now -Wl,--hash-style=sysv -o $T/start_sysv $ASM
{ echo "=== build: gcc -nostartfiles -Wl,-z,now -Wl,--hash-style=sysv (DT_HASH instead of DT_GNU_HASH, BIND_NOW)"; $T/start_sysv; echo "exit=$?"; readelf -dW -r -S $T/start_sysv; } > "$OUT/start_sysv_now.txt" 2>&1
# Absolute pointer in data: does PIE need R_*_RELATIVE?  (start + a .quad main in .data)
cat > $T/absptr.S <<EOF
#include "$ASM"
    .data
    .globl tin_abs_ptr
tin_abs_ptr: .quad main
    .quad msg
EOF
cp $ASM $T/
(cd $T && gcc -nostartfiles -I/p -o $T/absptr_pie absptr.S && gcc -nostartfiles -no-pie -I/p -o $T/absptr_nopie absptr.S)
{ echo "=== .data holds '.quad main' and '.quad msg' -- relocations needed? PIE:"; readelf -rW $T/absptr_pie; echo "--- non-PIE:"; readelf -rW $T/absptr_nopie; echo "--- run both:"; $T/absptr_pie; $T/absptr_nopie; } > "$OUT/absptr_relocs.txt" 2>&1

log spcheck
gcc -nostartfiles -o $T/spcheck crt_only.S spcheck.c && cp $T/spcheck "$OUT/spcheck.bin"
gcc -nostartfiles -no-pie -o $T/spcheck_nopie crt_only.S spcheck.c
{ echo "=== spcheck (PIE) from hand-written _start"; $T/spcheck a b c; echo "exit=$?"; echo; echo "=== spcheck (non-PIE)"; $T/spcheck_nopie; echo "exit=$?"; echo; echo "=== bindings for __libc_start_main / memcpy / puts (versioned reference, normal link):"; LD_DEBUG=bindings $T/spcheck 2>&1 | grep -E "symbol .(__libc_start_main|memcpy|puts|printf|getenv)'"; echo; echo "=== nm -D of spcheck (what the linker recorded):"; nm -D $T/spcheck; } > "$OUT/spcheck.txt" 2>&1

log negative-tests
run_patched() { # name file ops...
  name=$1; src=$2; shift 2
  cp "$src" $T/$name
  echo "=== $name: $*"; python3 /p/elfpatch.py $T/$name "$@"
  "$T/$name" x y; echo "exit=$?"
  echo
}
{
  echo "Each test patches a working binary and runs it. 'exit=0' + output means ld.so tolerated the change."
  run_patched unversioned $T/spcheck droptag 0x6ffffff0 droptag 0x6ffffffe droptag 0x6fffffff
  echo "--- bindings of the UNVERSIONED binary (no DT_VERSYM/VERNEED):"; LD_DEBUG=bindings $T/unversioned 2>&1 | grep -E "symbol .(__libc_start_main|memcpy|puts|printf|getenv|realpath)'"; echo
  run_patched nohash $T/spcheck droptag 0x6ffffef5 droptag 0x4
  run_patched nohash_unversioned $T/spcheck droptag 0x6ffffef5 droptag 0x4 droptag 0x6ffffff0 droptag 0x6ffffffe droptag 0x6fffffff
  run_patched nophdr_pie $T/spcheck dropphdr 6
  run_patched nophdr_nopie $T/spcheck_nopie dropphdr 6
  run_patched nognustack $T/spcheck dropphdr 0x6474e551
  run_patched execstack $T/spcheck phflags 0x6474e551 7
  run_patched noshdr $T/spcheck noshdr -
  run_patched noshdr_nohash_unversioned $T/spcheck noshdr - droptag 0x6ffffef5 droptag 0x4 droptag 0x6ffffff0 droptag 0x6ffffffe droptag 0x6fffffff
  echo "=== readelf -S of the no-section-header binary:"; readelf -S $T/noshdr 2>&1 | head -5
  run_patched nodebugtag $T/spcheck droptag 21
  run_patched nobindnow $T/start_sysv droptag 0x6ffffffb droptag 30
} > "$OUT/negative_tests.txt" 2>&1

log dladdr
gcc -O0 -o $T/dl_plain dladdr_test.c nosize_fn.S -ldl
gcc -O0 -rdynamic -o $T/dl_rdyn dladdr_test.c nosize_fn.S -ldl
gcc -O0 -rdynamic -Wl,--hash-style=sysv -o $T/dl_sysv dladdr_test.c nosize_fn.S -ldl
cp $T/dl_rdyn $T/dl_nohash; python3 /p/elfpatch.py $T/dl_nohash droptag 0x6ffffef5 droptag 0x4 > /dev/null
{
  echo "=== plain link (no -rdynamic): functions NOT in .dynsym"; $T/dl_plain
  echo; echo "=== -rdynamic (all globals exported to .dynsym, DT_GNU_HASH)"; $T/dl_rdyn
  echo; echo "=== -rdynamic --hash-style=sysv (DT_HASH)"; $T/dl_sysv
  echo; echo "=== -rdynamic with BOTH hash tags patched out (ld.so scans .dynsym up to .dynstr)"; $T/dl_nohash; echo "exit=$?"
  echo; echo "=== section order (is .dynstr right after .dynsym?)"; readelf -SW $T/dl_rdyn | grep -E "dynsym|dynstr|gnu.hash|\.hash"
  echo; echo "=== .dynsym of -rdynamic build (st_size column matters)"; readelf -W --dyn-syms $T/dl_rdyn | grep -E "fn|main"
} > "$OUT/dladdr.txt" 2>&1

log stat-symbols
cat > $T/statsym.c <<'EOF'
#include <sys/stat.h>
#include <dirent.h>
#include <stdio.h>
int main(void){struct stat s; stat("/",&s); lstat("/",&s); fstat(0,&s); DIR*d=opendir("/"); readdir(d); closedir(d); printf("%lld\n",(long long)s.st_size); return 0;}
EOF
gcc -O0 -o $T/statsym $T/statsym.c
{ echo "=== symbols a gcc-built binary imports for stat/lstat/fstat/readdir on this glibc:"; nm -D $T/statsym | grep -E "stat|readdir|opendir"; echo; echo "=== libc exports (readelf --dyn-syms, grep stat/readdir/errno/clock/random/epoll/timerfd/eventfd/affinity):"; grep -E " (__xstat|__lxstat|__fxstat|__fxstatat|stat|lstat|fstat|fstatat|stat64|lstat64|fstat64|statx|readdir|readdir64|__errno_location|clock_gettime|getrandom|getentropy|arc4random|arc4random_buf|arc4random_uniform|epoll_create1|epoll_ctl|epoll_wait|epoll_pwait2|timerfd_create|timerfd_settime|eventfd|sched_setaffinity|sched_getaffinity|pthread_setaffinity_np|pthread_create|pthread_attr_setstacksize|dladdr|dlsym|__libc_start_main|memcpy|memmove|memset|realpath|strerror|snprintf|strtod|getaddrinfo|freeaddrinfo|posix_memalign|signal|poll|nanosleep|usleep|time|gmtime_r|strftime|sysconf|get_nprocs)(@|$)" "$OUT/libc_dynsyms.txt" | awk '{print $8, $7, $4, $5}' | sort; echo; echo "=== libm exports for Tin's math externs:"; grep -E " (acos|asin|atan|atan2|cbrt|ceil|cos|cosh|exp|exp2|floor|fmod|hypot|log|log10|log1p|log2|pow|rint|round|sin|sinh|sqrt|tan|tanh|trunc)(@|$)" "$OUT/libm_dynsyms.txt" | awk '{print $8, $7, $4, $5}' | sort; } > "$OUT/symbol_versions.txt" 2>&1

log done
ls -la "$OUT"
