// hello.c: the reference gcc-built binary whose readelf output Tin's ELF writer imitates.
#include <stdio.h>
#include <string.h>
#include <math.h>
int main(int argc, char **argv) {
    char b[32];
    memcpy(b, "hello", 6);
    printf("%s %d %f\n", b, argc, sqrt((double)argc));
    return 0;
}
