#pragma once

#include <meta>
#include <span>
#include <string>
#include <string_view>

namespace names {

// The name of an enumerator, found by reflection instead of a list kept by hand
template <typename E>
constexpr std::string_view name_of(E value) {
    template for (constexpr auto enumerator : std::define_static_array(std::meta::enumerators_of(^^E))) {
        if (value == [:enumerator:]) {
            return std::meta::identifier_of(enumerator);
        }
    }
    return "?";
}

std::string joined(std::span<const std::string_view> words);

}
