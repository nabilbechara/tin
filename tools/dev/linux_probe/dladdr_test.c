// dladdr_test.c: what dladdr() resolves on Linux depending on how symbols are exported.
// Build A (default):   gcc -O0 -o dl_plain dladdr_test.c nosize_fn.S -ldl
// Build B (-rdynamic): gcc -O0 -rdynamic -o dl_rdyn dladdr_test.c nosize_fn.S -ldl
// Tin's runtime calls dladdr(return_address - 4) and reads dli_sname (Dl_info word 2).
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
#include <stddef.h>

extern void nosize_fn(void);      // asm, STT_FUNC, no .size directive => st_size == 0
extern void sized_fn(void);       // asm, STT_FUNC, with .size
extern void notype_fn(void);      // asm, no .type directive => STT_NOTYPE, with .size

__attribute__((noinline)) void tin_global_fn(void) { __asm__ volatile("" ::: "memory"); }
__attribute__((noinline)) static void tin_static_fn(void) { __asm__ volatile("" ::: "memory"); }

static void probe(const char *what, void *addr) {
    Dl_info di; memset(&di, 0, sizeof di);
    int rc = dladdr(addr, &di);
    printf("dladdr(%-22s) rc=%d sname=%-14s saddr=%p fname=%s\n", what, rc,
           di.dli_sname ? di.dli_sname : "(null)", di.dli_saddr, di.dli_fname ? di.dli_fname : "(null)");
}

int main(void) {
    printf("Dl_info: size=%zu dli_fname@%zu dli_fbase@%zu dli_sname@%zu dli_saddr@%zu\n", sizeof(Dl_info),
           offsetof(Dl_info, dli_fname), offsetof(Dl_info, dli_fbase), offsetof(Dl_info, dli_sname), offsetof(Dl_info, dli_saddr));
    probe("main", (void *)main);
    probe("main+8", (char *)main + 8);
    probe("tin_global_fn", (void *)tin_global_fn);
    probe("tin_global_fn+4", (char *)tin_global_fn + 4);
    probe("tin_static_fn+4", (char *)tin_static_fn + 4);
    probe("nosize_fn", (void *)nosize_fn);
    probe("nosize_fn+4", (char *)nosize_fn + 4);
    probe("sized_fn+4", (char *)sized_fn + 4);
    probe("notype_fn+4", (char *)notype_fn + 4);
    probe("puts (libc)", (void *)puts);
    probe("puts+8 (libc)", (char *)puts + 8);
    tin_static_fn();
    return 0;
}
