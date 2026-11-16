#pragma once

// in the precompiled headers of every module: no source includes it
inline std::string greeting_of(const std::vector<std::string> &words) {
    std::string greeting;
    for (const auto &word : words) {
        greeting += (greeting.empty() ? "" : " ") + word;
    }
    return greeting;
}
