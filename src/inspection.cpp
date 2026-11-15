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
using Sections = std::map<std::string, std::function<Json()>>;

std::set<std::string> inspection_fields(const Json& args, const Sections& sections) {
    std::set<std::string> fields;
    if (!args.contains("fields")) {
        for (const auto& [name, section] : sections) {
            fields.insert(name);
        }
        return fields;
    }
    if (!args.at("fields").is_array()) {
        throw std::invalid_argument("fields must be an array of section names");
    }
    fields = args.at("fields").get<std::set<std::string>>();
    for (const auto& name : fields) {
        if (!sections.contains(name)) {
            throw std::invalid_argument("unknown inspection field: " + name);
        }
    }
    return fields;
}

Json inspect_fields(const Json& args, const Sections& sections, Json result) {
    for (const auto& name : inspection_fields(args, sections)) {
        result[name] = sections.at(name)();
    }
    return result;
}

Json inspection_query(const Json& args) {
    auto query = args;
    if (args.contains("parameter_names")) {
        query["names"] = args.at("parameter_names");
    }
    if (args.contains("port_names")) {
        query["ports"] = args.at("port_names");
    }
    return query;
}
} // namespace
Json SemanticService::inspect_signal(const Json& args) {
    const auto identifier = args.at("signal").get<std::string>();
    auto query = args;
    query["limit"] = limit_for(args, 10);
    const Sections sections = {
        {"reference_count", [&] { return Json(manager_.design().references(identifier).size()); }},
        {"reads", [&] { return references(query, "read"); }},
        {"writes", [&] { return references(query, "write"); }},
        {"drivers", [&] { return references(query, "write"); }},
        {"loads", [&] { return references(query, "read"); }}};
    return inspect_fields(args, sections, {{"symbol", manager_.design().signal(identifier)}});
}

Json SemanticService::inspect_instance(const Json& args) {
    const auto instance = manager_.design().instance(args.at("instance_path"));
    auto query = inspection_query(args);
    query["instance_path"] = instance.path;
    const Sections sections = {
        {"parameters", [&] { return parameters(query, true); }},
        {"connections", [&] { return connections(query); }},
        {"children", [&] {
             return page(select(manager_.design().instances(),
                                [&](const auto& item) { return item.parent == instance.path; }),
                         limit_for(args));
         }}};
    return inspect_fields(args, sections, {{"instance", instance}});
}

Json SemanticService::inspect_module(const Json& args) {
    const auto definition = manager_.design().definition_reference(args.at("sv_module"));
    auto query = inspection_query(args);
    query["target"] = definition.symbol_id;
    const Sections sections = {
        {"parameters", [&] { return parameters(query, false); }},
        {"ports",
         [&] {
             return page(named(manager_.design().ports(definition.symbol_id), args, "port_names",
                               [](const auto& item) { return item.name; }),
                         limit_for(args));
         }},
        {"declaration_count",
         [&] { return Json(manager_.design().members(definition.symbol_id).size()); }},
        {"children",
         [&] {
             return page(module_children(manager_.design().instances(), definition.name),
                         limit_for(args));
         }},
        {"procedures", [&] { return procedures(args); }},
        {"diagnostic_count", [&] {
             return Json(
                 std::ranges::count_if(manager_.design().diagnostics(), [&](const auto& item) {
                     return item.location.filename == definition.location.filename;
                 }));
         }}};
    return inspect_fields(args, sections, {{"definition", definition}});
}
} // namespace slang_mcp
