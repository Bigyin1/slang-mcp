#pragma once

#include "models.hpp"
#include <memory>

namespace slang_mcp::adapters {
class Design {
  public:
    explicit Design(const ProjectConfig& config);
    ~Design();
    Design(const Design&) = delete;
    Design& operator=(const Design&) = delete;
    [[nodiscard]] const std::vector<Diagnostic>& diagnostics() const;
    [[nodiscard]] std::vector<std::string> tops() const;
    [[nodiscard]] std::string version() const;
    [[nodiscard]] std::vector<SymbolReference> definitions() const;
    [[nodiscard]] std::vector<SymbolReference> find_symbols(const std::string& name) const;
    [[nodiscard]] SymbolDescription describe(const std::string& identifier);
    [[nodiscard]] std::vector<SymbolReference> members(const std::string& scope);
    [[nodiscard]] std::vector<HierarchyNode> hierarchy(const Text& root, int depth) const;
    [[nodiscard]] const std::vector<Instance>& instances() const;
    [[nodiscard]] Instance instance(const std::string& query) const;
    [[nodiscard]] std::vector<Port> ports(const std::string& module);
    [[nodiscard]] std::vector<Parameter> parameters(const std::string& target, bool effective);
    [[nodiscard]] std::vector<Connection> connections(const std::string& path) const;
    [[nodiscard]] std::vector<Reference> references(const std::string& identifier);
    [[nodiscard]] SymbolDescription signal(const std::string& identifier);
    [[nodiscard]] const AccessIndex& accesses();

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace slang_mcp::adapters
