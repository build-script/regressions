#include <gtest/gtest.h>

int answer();

TEST(Passing, Answer) { EXPECT_EQ(answer(), 42); }
TEST(Failing, Answer) { EXPECT_EQ(answer(), 41); }
