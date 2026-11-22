#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <array>

#include <names/names.hpp>

enum class shape { circle, square };

TEST_CASE("reflection names the enumerators") {
    CHECK(names::name_of(shape::circle) == "circle");
    CHECK(names::name_of(shape::square) == "square");
}

TEST_CASE("the names are joined by spaces") {
    std::array<std::string_view, 2> words{"circle", "square"};
    CHECK(names::joined(words) == "circle square");
}
