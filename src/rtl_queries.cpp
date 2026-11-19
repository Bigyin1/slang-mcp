#include "pagination.hpp"
#include "semantic_service.hpp"

namespace slang_mcp {
namespace {
struct FactSelection {
    const Json& args;
    int limit = option(args, "fact_limit", 100);
    std::set<std::string> fields =
        option(args, "fields", std::set<std::string>{"parameters", "connections"});

    void validate() const {
        validate_limit(limit);
        for (const auto& field : fields) {
            if (field != "parameters" && field != "connections") {
                throw std::invalid_argument("unknown instance facts field: " + field);
            }
        }
    }
};

Json parameter_facts(adapters::Design& design, const std::string& path,
                     const FactSelection& selection) {
    return page(named(design.parameters(path, true), selection.args, "parameter_names",
                      [](const auto& item) { return item.name; }),
                selection.limit);
}

Json connection_facts(adapters::Design& design, const std::string& path,
                      const FactSelection& selection) {
    return page(named(design.connections(path), selection.args, "port_names",
                      [](const auto& item) { return item.port.name; }),
                selection.limit);
}

Json facts_for(const FactSelection& selection, adapters::Design& design, const Json& instance) {
    const auto path = instance.at("path").get<std::string>();
    Json result = {{"instance", instance}};
    if (selection.fields.contains("parameters")) {
        result["parameters"] = parameter_facts(design, path, selection);
    }
    if (selection.fields.contains("connections")) {
        result["connections"] = connection_facts(design, path, selection);
    }
    return result;
}

bool access_matches(const std::string& kind, const std::string& filter) {
    static const std::set<std::string> accesses = {"read", "write", "read_write"};
    return accesses.contains(kind) &&
           (filter == "read_write" || kind == filter || kind == "read_write");
}

bool reference_matches(const Reference& item, const Text& access, const Text& kind) {
    const auto filter = access.value_or(kind.value_or(""));
    if (filter == "read" || filter == "write" || filter == "read_write") {
        return access_matches(item.kind, filter);
    }
    return filter.empty() || item.kind == filter || item.context == filter;
}

std::vector<Procedure> module_procedures(adapters::Design& design, const std::string& module) {
    const auto name = design.describe(module).symbol.name;
    std::set<std::string> paths;
    for (const auto& instance : design.instances()) {
        if (instance.sv_module == name) {
            paths.insert(instance.path);
        }
    }
    return select(design.accesses().procedures,
                  [&](const auto& item) { return paths.contains(item.instance); });
}
} // namespace
Json SemanticService::parameters(const Json& args, bool effective) {
    const auto target = args.at(effective ? "instance_path" : "target").get<std::string>();
    if (!effective && target.contains('.')) {
        effective = std::ranges::any_of(manager_.design().instances(),
                                        [&](const auto& item) { return item.path == target; });
    }
    auto items = named(manager_.design().parameters(target, effective), args, "names",
                       [](const auto& item) { return item.name; });
    return {{"target", target},
            {"value_kind", effective ? "effective" : "declared_default"},
            {"parameters", page(std::move(items), limit_for(args))}};
}

Json SemanticService::connections(const Json& args) {
    auto items = named(manager_.design().connections(args.at("instance_path")), args, "ports",
                       [](const auto& item) { return item.port.name; });
    return page(std::move(items), limit_for(args));
}

Json SemanticService::describe_instance(const Json& args) {
    const auto instance = manager_.design().instance(args.at("path"));
    std::vector<PortDescription> ports;
    std::vector<Json> connections;
    for (const auto& item : manager_.design().connections(instance.path)) {
        ports.push_back({item.port.name, item.port.direction, item.port.type, item.port.width});
        connections.push_back({{"port", item.port.name}, {"expression", item.expression}});
    }
    return {{"path", instance.path},
            {"name", instance.name},
            {"sv_module", instance.sv_module},
            {"location", instance.location},
            {"parameters", manager_.design().parameters(instance.path, true)},
            {"ports", ports},
            {"connections", connections},
            {"children", manager_.design().hierarchy(instance.path, 1).front().children}};
}

Json SemanticService::list_instances(const Json& args) {
    const auto module = text_option(args, "sv_module");
    const auto name = text_option(args, "name");
    const auto prefix = text_option(args, "path_prefix");
    return page(select(manager_.design().instances(),
                       [&](const auto& item) {
                           return (!module || item.sv_module == *module) &&
                                  (!name || item.name == *name) &&
                                  (!prefix || item.path.starts_with(*prefix));
                       }),
                limit_for(args));
}

Json SemanticService::instance_facts(const Json& args) {
    auto instances = list_instances(args);
    std::vector<Json> result;
    const FactSelection selection{args};
    selection.validate();
    for (const auto& instance : instances.at("items")) {
        result.push_back(facts_for(selection, manager_.design(), instance));
    }
    instances["items"] = std::move(result);
    return instances;
}

namespace {
Text reference_kind(const Json& args) {
    const auto kind = text_option(args, "kind");
    static const std::set<std::string> kinds = {"read",
                                                "write",
                                                "read_write",
                                                "declaration",
                                                "unknown",
                                                "parameter_reference",
                                                "port_connection",
                                                "type_reference",
                                                "instantiation"};
    if (kind && !kinds.contains(*kind)) {
        throw std::invalid_argument("unknown reference kind: " + *kind);
    }
    return kind;
}
} // namespace

Json SemanticService::references(const Json& args, const Text& access) {
    const auto identifier = args.at(access ? "signal" : "symbol").get<std::string>();
    const auto kind = reference_kind(args);
    auto items = select(manager_.design().references(identifier),
                        [&](const auto& item) { return reference_matches(item, access, kind); });
    if (access) {
        return page(std::move(items), limit_for(args));
    }
    return Pagination(args, "get_references", manager_.revision())
        .render(items, "items", std::identity{});
}

Json SemanticService::procedures(const Json& args) {
    return page(module_procedures(manager_.design(), args.at("sv_module")), limit_for(args));
}

Json SemanticService::state_elements(const Json& args) {
    std::vector<Json> result;
    for (const auto& block : module_procedures(manager_.design(), args.at("sv_module"))) {
        if (block.kind != "AlwaysFF") {
            continue;
        }
        for (const auto& name : manager_.design().accesses().block_writes.at(block.block_id)) {
            const auto symbol = manager_.design().signal(name);
            result.push_back({{"signal", symbol.symbol},
                              {"type", symbol.type},
                              {"width", symbol.width},
                              {"block", block.block_id},
                              {"location", block.location}});
        }
    }
    return page(std::move(result), limit_for(args));
}
} // namespace slang_mcp
