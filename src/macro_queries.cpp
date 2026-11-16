#include "query.hpp"
#include "semantic_service.hpp"

#include <limits>

namespace slang_mcp {
namespace {
int macro_number(const Json& args, const std::string& key, int fallback = 0) {
    const auto item = args.find(key);
    if (item == args.end()) {
        return fallback;
    }
    if (!item->is_number_integer()) {
        throw std::invalid_argument(key + " must be a positive integer");
    }
    const auto value = item->get<std::int64_t>();
    if (value < 1 || value > std::numeric_limits<int>::max()) {
        throw std::invalid_argument(key + " must be a positive 32-bit integer");
    }
    return static_cast<int>(value);
}
} // namespace

Json SemanticService::expand_macro(const Json& args) {
    return manager_.design().expand_macro({args.at("file").get<std::string>(),
                                           macro_number(args, "line"), macro_number(args, "column"),
                                           macro_number(args, "max_bytes", 8192)});
}
} // namespace slang_mcp
