#include "shout/shout.hpp"

#include <cctype>

std::string shout(const std::string &text) {
    std::string loud = text;
    for (char &c : loud) {
        c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }
    return loud;
}
