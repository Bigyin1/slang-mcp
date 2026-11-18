#pragma once

#include "adapters/design.hpp"
#include "compilation_error.hpp"
#include <cstdint>

namespace slang_mcp {
enum class SnapshotPolicy : std::uint8_t { Disabled, Track };

class ProjectManager {
  public:
    explicit ProjectManager(SnapshotPolicy snapshots = SnapshotPolicy::Track)
        : snapshot_policy_(snapshots) {}
    [[nodiscard]] Json load(ProjectConfig config);
    [[nodiscard]] Json reload();
    [[nodiscard]] Json info();
    [[nodiscard]] Json summary();
    [[nodiscard]] Json analysis_context() const;
    [[nodiscard]] Json diff(int limit) const;
    [[nodiscard]] adapters::Design& design();
    [[nodiscard]] std::uint64_t revision() const {
        return revision_;
    }
    [[nodiscard]] const CompilationError& failed_attempt(std::uint64_t id) const;

  private:
    using Snapshot = std::map<std::string, std::string>;
    ProjectConfig config_;
    std::unique_ptr<adapters::Design> design_;
    Snapshot snapshot_;
    std::optional<Snapshot> previous_;
    SnapshotPolicy snapshot_policy_;
    std::uint64_t revision_ = 0;
    std::uint64_t attempt_id_ = 0;
    std::optional<CompilationError> failure_;
    [[nodiscard]] std::unique_ptr<adapters::Design> build(const ProjectConfig& config);
    [[nodiscard]] static Snapshot snapshot(adapters::Design& design);
};

[[nodiscard]] ProjectConfig project_from_arguments(const Json& arguments);
} // namespace slang_mcp
