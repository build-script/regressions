#include "shout.h"

#include <algorithm>
#include <cctype>
#include <string>

const char *shout(const char *text) {
    static std::string loud;
    loud = text;
    std::transform(loud.begin(), loud.end(), loud.begin(), [](unsigned char c) { return std::toupper(c); });
    return loud.c_str();
}
