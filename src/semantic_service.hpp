#pragma once

#include "project.hpp"
#include <functional>
#include <mutex>

namespace slang_mcp {
class SemanticService {
  public:
    explicit SemanticService(SnapshotPolicy snapshots = SnapshotPolicy::Track);
    [[nodiscard]] Json call(const std::string& name, const Json& arguments);

  private:
    ProjectManager manager_;
    std::mutex mutex_;
    std::map<std::string, std::function<Json(const Json&)>> tools_;
    void register_project_tools();
    void register_symbol_tools();
    void register_rtl_tools();
    void register_inspection_tools();
    [[nodiscard]] Json parameters(const Json& args, bool effective);
    [[nodiscard]] Json connections(const Json& args);
    [[nodiscard]] Json describe_instance(const Json& args);
    [[nodiscard]] Json list_instances(const Json& args);
    [[nodiscard]] Json instance_facts(const Json& args);
    [[nodiscard]] Json references(const Json& args, const Text& access = std::nullopt);
    [[nodiscard]] Json procedures(const Json& args);
    [[nodiscard]] Json state_elements(const Json& args);
    [[nodiscard]] Json trace(const Json& args);
    [[nodiscard]] Json inspect_signal(const Json& args);
    [[nodiscard]] Json inspect_instance(const Json& args);
    [[nodiscard]] Json inspect_module(const Json& args);
    [[nodiscard]] Json diagnostics(const Json& args, bool grouped);
};
} // namespace slang_mcp
