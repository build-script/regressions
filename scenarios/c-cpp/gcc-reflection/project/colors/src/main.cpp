#include <array>
#include <iostream>

#include <names/names.hpp>

enum class color { red, green, blue };

int main() {
    std::array words{names::name_of(color::red), names::name_of(color::green), names::name_of(color::blue)};
    std::cout << names::joined(words) << '\n';
}
