#pragma once

#include "models.hpp"

#include <filesystem>

namespace slang_mcp {
inline Text canonical_absolute_path(const std::string& file) {
    const std::filesystem::path path(file);
    if (!path.is_absolute()) {
        return std::nullopt;
    }
    std::error_code error;
    const auto canonical = std::filesystem::weakly_canonical(path, error);
    return error ? std::nullopt : Text(canonical.string());
}
} // namespace slang_mcp
