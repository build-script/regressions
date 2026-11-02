#include <cstdio>

#include "math/square.h"

int main() {
    if (square(-3) != 9) {
        std::printf("square(-3) is %d\n", square(-3));
        return 1;
    }

    return 0;
}
