// spcheck.c: run from the hand-written _start in crt_only.S; checks what the kernel/ld.so hand over.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/auxv.h>
#include <link.h>
#include <elf.h>

extern uint64_t tin_entry_sp, tin_entry_rtld_fini;
extern char **environ;
extern const ElfW(Ehdr) __ehdr_start;   // linker-provided, address of our own ELF header

int main(int argc, char **argv, char **envp) {
    printf("entry sp            = 0x%llx  (sp mod 16 = %llu)\n", (unsigned long long)tin_entry_sp, (unsigned long long)(tin_entry_sp % 16));
    long *sp = (long *)(uintptr_t)tin_entry_sp;
    printf("[sp] (argc)         = %ld  argc arg = %d\n", sp[0], argc);
    printf("[sp+8] (argv[0])    = %s  argv[0] = %s\n", (char *)sp[1], argv[0]);
    printf("envp == argv+argc+1 = %s ; environ == envp = %s\n", (envp == argv + argc + 1) ? "yes" : "no", (environ == envp) ? "yes" : "no");
    printf("rtld_fini (x0/rdx)  = 0x%llx (%s)\n", (unsigned long long)tin_entry_rtld_fini, tin_entry_rtld_fini ? "non-null: _dl_fini from ld.so" : "NULL");
    printf("getenv(PATH) works  = %s\n", getenv("PATH") ? "yes" : "no");
    printf("AT_PHDR             = 0x%lx ; &__ehdr_start = %p ; e_phoff = %lu => load bias = 0x%lx\n",
           getauxval(AT_PHDR), (void *)&__ehdr_start, (unsigned long)__ehdr_start.e_phoff,
           (unsigned long)((uintptr_t)&__ehdr_start));
    printf("AT_PAGESZ           = %lu ; AT_ENTRY = 0x%lx ; AT_RANDOM = 0x%lx ; AT_SECURE = %lu\n", getauxval(AT_PAGESZ), getauxval(AT_ENTRY), getauxval(AT_RANDOM), getauxval(AT_SECURE));
    printf("e_type              = %u (2=EXEC, 3=DYN/PIE)\n", __ehdr_start.e_type);
    // [stack] mapping permissions, to see the effect of PT_GNU_STACK.
    FILE *f = fopen("/proc/self/maps", "r");
    char line[512];
    while (f && fgets(line, sizeof line, f)) if (strstr(line, "[stack]")) fputs(line, stdout);
    if (f) fclose(f);
    char buf[64]; memcpy(buf, "memcpy-bound-ok", 16); puts(buf);
    return 0;
}
