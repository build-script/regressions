#include <cstdio>

#include "llvm/ADT/ArrayRef.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/ADT/StringTable.h"

using namespace llvm;

struct Color {
    StringTable::Offset Name;
    unsigned Value;
};

#define GET_Colors_DECL
#define GET_Colors_IMPL
#include "colors.inc"

int main(int argc, char **argv) {
    StringRef name = argc > 1 ? argv[1] : "green";
    const Color *color = lookupColor(name);

    if (color == nullptr) {
        std::printf("no color %s\n", name.str().c_str());
        return 1;
    }

    std::printf("%s = #%06x\n", getColorStr(color->Name).str().c_str(), color->Value);
    return 0;
}
