// Writes table.h and table.c: the squares of 0 to 15
#include <stdio.h>

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: generator <table.h> <table.c>\n");
        return 1;
    }

    FILE *header = fopen(argv[1], "w");
    FILE *source = fopen(argv[2], "w");
    if (header == NULL || source == NULL) {
        perror("generator");
        return 1;
    }

    fprintf(header, "#pragma once\n\nextern const int squares[16];\n");
    fprintf(source, "#include \"table.h\"\n\nconst int squares[16] = {");
    for (int number = 0; number < 16; number++) {
        fprintf(source, "%s%d", number == 0 ? "" : ", ", number * number);
    }
    fprintf(source, "};\n");

    fclose(header);
    fclose(source);
    return 0;
}
