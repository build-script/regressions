#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include "math/square.h"
TEST_CASE("square") { CHECK(square_twice(3) == 18); }
