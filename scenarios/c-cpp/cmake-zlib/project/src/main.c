#include <stdio.h>
#include <string.h>
#include <zlib.h>

int main(void) {
    const char *text = "build_cmake built zlib from git";
    unsigned char packed[128], unpacked[128];
    uLongf packed_size = sizeof packed, unpacked_size = sizeof unpacked;

    compress(packed, &packed_size, (const unsigned char *)text, strlen(text) + 1);
    uncompress(unpacked, &unpacked_size, packed, packed_size);
    printf("zlib %s: %s (%lu bytes packed)\n", zlibVersion(), unpacked, packed_size);
    return 0;
}
