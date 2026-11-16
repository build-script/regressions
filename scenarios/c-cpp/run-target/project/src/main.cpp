#include <cstdio>

#if defined(__x86_64__)
#define PROCESSOR "x86_64"
#elif defined(__aarch64__)
#define PROCESSOR "aarch64"
#else
#define PROCESSOR "another processor"
#endif

int main(int argc, char **argv) {
    std::printf("hello from %s%s%s\n", PROCESSOR, argc > 1 ? " with " : "", argc > 1 ? argv[1] : "");
    return 0;
}
