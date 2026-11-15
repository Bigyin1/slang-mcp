#pragma once

#include "adapters/design.hpp"

namespace slang_mcp {
class ProjectManager {
  public:
    [[nodiscard]] Json load(ProjectConfig config);
    [[nodiscard]] Json reload();
    [[nodiscard]] Json info();
    [[nodiscard]] Json summary();
    [[nodiscard]] Json diff(int limit) const;
    [[nodiscard]] adapters::Design& design();

  private:
    using Snapshot = std::map<std::string, std::string>;
    ProjectConfig config_;
    std::unique_ptr<adapters::Design> design_;
    Snapshot snapshot_;
    std::optional<Snapshot> previous_;
    [[nodiscard]] static Snapshot snapshot(adapters::Design& design);
};

[[nodiscard]] ProjectConfig project_from_arguments(const Json& arguments);
} // namespace slang_mcp
