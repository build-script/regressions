#include <cstdio>

int main() {
#if defined(__x86_64__)
    std::printf("tests on x86_64\n");
#else
    std::printf("tests on another processor\n");
#endif
    return 0;
}
