#include <cstdio>
#include <exception>
#include <initializer_list>
#include <stdexcept>
#include <string>

static void print(const char* text) {
    std::printf("%s\n", text);
    std::fflush(stdout);
}

// like the formatter of fmt: the message, then that of the nested exception, thrown again in a catch
static void write(const std::exception& error, std::string& out) {
    out += error.what();

    if (auto* nested = dynamic_cast<const std::nested_exception*>(&error)) {
        if (std::exception_ptr pointer = nested->nested_ptr()) {
            out += ": ";

            try {
                std::rethrow_exception(pointer);
            } catch (const std::exception& nested_error) {
                write(nested_error, out);
            } catch (...) {
                out += "unknown exception";
            }
        }
    }
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

    // nested ones through an exception_ptr, written in the catch of the outer one
    std::exception_ptr chain;

    try {
        try {
            throw std::runtime_error("inner");
        } catch (...) {
            std::throw_with_nested(std::runtime_error("outer"));
        }
    } catch (...) {
        chain = std::current_exception();
    }

    try {
        std::rethrow_exception(chain);
    } catch (const std::exception& error) {
        std::string out;
        write(error, out);
        print(out.c_str());
    }

    print("rethrown");
}
