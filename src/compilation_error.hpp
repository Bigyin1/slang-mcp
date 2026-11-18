#pragma once

#include "models.hpp"

#include <stdexcept>
#include <utility>

namespace slang_mcp {
class CompilationError final : public std::invalid_argument {
  public:
    CompilationError(const std::string& message, std::vector<Diagnostic> diagnostics,
                     const ProjectConfig& config)
        : std::invalid_argument(message), diagnostics(std::move(diagnostics)),
          requested_top_modules(config.top_modules),
          analysis_scope(config.metadata.contains("analysis_scope")
                             ? config.metadata.at("analysis_scope")
                             : "configured_sources"),
          source_file_count(config.source_files.size()), single_unit(config.single_unit) {}

    const std::vector<Diagnostic> diagnostics;
    const std::vector<std::string> requested_top_modules;
    const std::string analysis_scope;
    const std::size_t source_file_count;
    const bool single_unit;
    std::uint64_t attempt_id = 0;

    [[nodiscard]] Json context() const {
        return {{"context", "attempted_candidate"}, {"analysis_scope", analysis_scope},
                {"completeness", "not_verified"},   {"top_modules", requested_top_modules},
                {"single_unit", single_unit},       {"source_file_count", source_file_count}};
    }
};
} // namespace slang_mcp
