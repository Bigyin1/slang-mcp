#include "query.hpp"
#include "semantic_service.hpp"

namespace slang_mcp {
namespace {
std::vector<Instance> module_children(const std::vector<Instance>& instances,
                                      const std::string& module) {
    std::set<std::string> parents;
    for (const auto& instance : instances) {
        if (instance.sv_module == module) {
            parents.insert(instance.path);
        }
    }
    return select(instances,
                  [&](const auto& item) { return item.parent && parents.contains(*item.parent); });
}
} // namespace
Json SemanticService::inspect_signal(const Json& args) {
    const auto identifier = args.at("signal").get<std::string>();
    auto query = args;
    query["limit"] = limit_for(args, 10);
    const auto reads = references(query, "read");
    const auto writes = references(query, "write");
    return {{"symbol", manager_.design().signal(identifier)},
            {"reference_count", manager_.design().references(identifier).size()},
            {"reads", reads},
            {"writes", writes},
            {"drivers", writes},
            {"loads", reads}};
}

Json SemanticService::inspect_instance(const Json& args) {
    const auto instance = manager_.design().instance(args.at("instance_path"));
    Json query = args;
    query["instance_path"] = instance.path;
    const auto children = select(manager_.design().instances(),
                                 [&](const auto& item) { return item.parent == instance.path; });
    return {{"instance", instance},
            {"parameters", parameters(query, true)},
            {"connections", connections(query)},
            {"children", page(children, limit_for(args))}};
}

Json SemanticService::inspect_module(const Json& args) {
    const auto definition = manager_.design().describe(args.at("sv_module")).symbol;
    const auto count =
        std::ranges::count_if(manager_.design().diagnostics(), [&](const auto& item) {
            return item.location.filename == definition.location.filename;
        });
    auto query = args;
    query["target"] = definition.symbol_id;
    return {{"definition", definition},
            {"parameters", parameters(query, false)},
            {"ports", page(manager_.design().ports(definition.symbol_id), limit_for(args))},
            {"declaration_count", manager_.design().members(definition.symbol_id).size()},
            {"children", page(module_children(manager_.design().instances(), definition.name),
                              limit_for(args))},
            {"procedures", procedures(args)},
            {"diagnostic_count", count}};
}
} // namespace slang_mcp
