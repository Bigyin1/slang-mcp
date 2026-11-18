#pragma once

#include "models.hpp"

namespace slang_mcp {
class SymbolLookupError final : public std::invalid_argument {
  public:
    SymbolLookupError(const std::string& message, Json details)
        : std::invalid_argument(message), details(std::move(details)) {}

    const Json details;
};
} // namespace slang_mcp
