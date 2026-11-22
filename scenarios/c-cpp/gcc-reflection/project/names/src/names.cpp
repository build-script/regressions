#include <names/names.hpp>

#include <fmt/format.h>
#include <fmt/ranges.h>

namespace names {

std::string joined(std::span<const std::string_view> words) {
    return fmt::format("{}", fmt::join(words, " "));
}

}
