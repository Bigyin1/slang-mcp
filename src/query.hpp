#pragma once

#include "models.hpp"
#include <set>

namespace slang_mcp {
template <class T> T option(const Json& arguments, const std::string& key, T fallback) {
    const auto value = arguments.find(key);
    return value == arguments.end() || value->is_null() ? std::move(fallback) : value->get<T>();
}
inline Text text_option(const Json& arguments, const std::string& key) {
    const auto value = arguments.find(key);
    return value == arguments.end() || value->is_null() ? std::nullopt
                                                        : Text(value->get<std::string>());
}
inline int limit_for(const Json& arguments, int fallback = 100) {
    const auto limit = option(arguments, "limit", fallback);
    validate_limit(limit);
    return limit;
}
inline int type_depth_for(const Json& arguments) {
    const auto value = arguments.find("type_depth");
    if (value == arguments.end() || value->is_null()) {
        return 2;
    }
    if (!value->is_number_integer() || *value < 0 || *value > 8) {
        throw std::invalid_argument("type_depth must be an integer between 0 and 8");
    }
    return value->get<int>();
}
template <class T, class Predicate>
std::vector<T> select(const std::vector<T>& values, Predicate predicate) {
    std::vector<T> result;
    std::ranges::copy_if(values, std::back_inserter(result), std::move(predicate));
    return result;
}
template <class T, class Name>
std::vector<T> named(std::vector<T> values, const Json& arguments, const std::string& key,
                     Name name) {
    if (!arguments.contains(key) || arguments.at(key).is_null()) {
        return values;
    }
    const auto names = arguments.at(key).get<std::vector<std::string>>();
    if (names.size() > 500) {
        throw std::invalid_argument(key + " must contain at most 500 items");
    }
    const std::set<std::string> requested(names.begin(), names.end());
    return select(values, [&](const auto& item) { return requested.contains(name(item)); });
}
} // namespace slang_mcp
