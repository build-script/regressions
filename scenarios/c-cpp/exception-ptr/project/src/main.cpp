#include <cstdio>
#include <exception>
#include <initializer_list>
#include <stdexcept>

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
            std::printf("%s\n", error.what());
            std::fflush(stdout);
        }
    }

    std::printf("rethrown\n");
}
