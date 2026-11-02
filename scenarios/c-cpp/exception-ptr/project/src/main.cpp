#include <cstdio>
#include <exception>
#include <initializer_list>
#include <stdexcept>

static void print(const char* text) {
    std::printf("%s\n", text);
    std::fflush(stdout);
}

int main() {
    std::exception_ptr caught;

    try {
        throw std::runtime_error("current_exception");
    } catch (...) {
        caught = std::current_exception();
    }

    std::exception_ptr made = std::make_exception_ptr(std::runtime_error("make_exception_ptr"));

    for (const std::exception_ptr& pointer : {caught, made}) {
        try {
            std::rethrow_exception(pointer);
        } catch (const std::exception& error) {
            print(error.what());
        }
    }

    // throw_with_nested keeps the current exception in a nested_exception, rethrow_if_nested throws it again
    try {
        try {
            throw std::runtime_error("inner");
        } catch (...) {
            std::throw_with_nested(std::runtime_error("outer"));
        }
    } catch (const std::exception& outer) {
        print(outer.what());

        try {
            std::rethrow_if_nested(outer);
        } catch (const std::exception& inner) {
            print(inner.what());
        }
    }

    print("rethrown");
}
