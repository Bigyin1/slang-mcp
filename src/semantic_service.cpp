#include "semantic_service.hpp"
#include "query.hpp"

#include <cctype>

namespace slang_mcp {
namespace {
Text diagnostic_severity(const Json& args) {
    auto severity = text_option(args, "severity");
    if (!severity) {
        return severity;
    }
    std::ranges::transform(*severity, severity->begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    static const std::set<std::string> allowed = {"ignored", "note", "warning", "error", "fatal"};
    if (!allowed.contains(*severity)) {
        throw std::invalid_argument("unknown diagnostic severity: " + *severity);
    }
    return severity;
}

int hierarchy_depth(const Json& args) {
    const auto depth = args.find("max_depth");
    if (depth == args.end() || depth->is_null()) {
        return -1;
    }
    const auto value = depth->get<int>();
    if (value < 0 || value > 50) {
        throw std::invalid_argument("max_depth must be between 0 and 50");
    }
    return value;
}

Json diagnostic_group(const std::string& code, const std::vector<Diagnostic>& items) {
    std::map<std::string, int> counts;
    for (const auto& item : items) {
        ++counts[item.severity];
    }
    return {{"code", code},
            {"count", items.size()},
            {"severity_counts", counts},
            {"example_message", items.front().message},
            {"first_location", items.front().location}};
}

std::vector<Json> diagnostic_groups(const std::vector<Diagnostic>& diagnostics) {
    std::map<std::string, std::vector<Diagnostic>> groups;
    for (const auto& item : diagnostics) {
        groups[item.code].push_back(item);
    }
    std::vector<Json> result;
    result.reserve(groups.size());
    for (const auto& group : groups) {
        result.push_back(diagnostic_group(group.first, group.second));
    }
    return result;
}

Json diagnostic_with_scope_hint(const Diagnostic& diagnostic) {
    // An unresolved name can also be a typo; this never downgrades severity.
    static const std::set<std::string> unresolved = {"UnknownModule", "UnknownClassOrPackage"};
    Json result = diagnostic;
    result["scope_hint"] =
        unresolved.contains(diagnostic.code) ? "possible_missing_dependency" : "unclassified";
    return result;
}

Json diagnostic_page(const std::vector<Diagnostic>& diagnostics, int limit) {
    const auto selected = page(diagnostics, limit);
    Json items = Json::array();
    for (const auto& item : selected.items) {
        items.push_back(diagnostic_with_scope_hint(item));
    }
    return {{"diagnostics", items},
            {"returned_count", items.size()},
            {"total_count", selected.total_count},
            {"truncated", selected.truncated}};
}
} // namespace
SemanticService::SemanticService(SnapshotPolicy snapshots) : manager_(snapshots) {
    register_project_tools();
    register_symbol_tools();
    register_rtl_tools();
    register_inspection_tools();
}

Json SemanticService::call(const std::string& name, const Json& arguments) {
    const std::lock_guard lock(mutex_);
    const auto handler = tools_.find(name);
    if (handler == tools_.end()) {
        throw std::invalid_argument("unknown tool: " + name);
    }
    return handler->second(arguments);
}

void SemanticService::register_project_tools() {
    tools_["expand_macro"] = [this](const Json& args) { return expand_macro(args); };
    tools_["project_load"] = [this](const Json& args) {
        return manager_.load(project_from_arguments(args));
    };
    tools_["project_reload"] = [this](const Json&) { return manager_.reload(); };
    tools_["project_info"] = [this](const Json&) { return manager_.info(); };
    tools_["semantic_diff"] = [this](const Json& args) { return manager_.diff(limit_for(args)); };
    tools_["get_diagnostics"] = [this](const Json& args) { return diagnostics(args, false); };
    tools_["summarize_diagnostics_by_code"] = [this](const Json& args) {
        return diagnostics(args, true);
    };
}

void SemanticService::register_symbol_tools() {
    tools_["find_symbol"] = [this](const Json& args) -> Json {
        auto items = manager_.design().find_symbols(args.at("name"));
        return {{"symbols", items}, {"match_count", items.size()}};
    };
    tools_["describe_symbol"] = [this](const Json& args) -> Json {
        return manager_.design().describe(args.at("identifier"), type_depth_for(args));
    };
    tools_["get_hierarchy"] = [this](const Json& args) -> Json {
        return {{"roots",
                 manager_.design().hierarchy(text_option(args, "root"), hierarchy_depth(args))}};
    };
    tools_["describe_instance"] = [this](const Json& args) { return describe_instance(args); };
    tools_["list_symbols"] = [this](const Json& args) -> Json {
        const auto kind = text_option(args, "kind");
        return page(select(manager_.design().members(args.at("scope")),
                           [&](const auto& item) { return !kind || item.kind == *kind; }),
                    limit_for(args));
    };
    tools_["get_ports"] = [this](const Json& args) -> Json {
        return page(manager_.design().ports(args.at("sv_module")), limit_for(args));
    };
}

void SemanticService::register_rtl_tools() {
    tools_["get_parameters"] = [this](const Json& args) { return parameters(args, false); };
    tools_["get_instance_parameters"] = [this](const Json& args) { return parameters(args, true); };
    tools_["get_instance_connections"] = [this](const Json& args) { return connections(args); };
    tools_["list_instances"] = [this](const Json& args) { return list_instances(args); };
    tools_["find_instance"] = [this](const Json& args) -> Json {
        return manager_.design().instance(args.at("query"));
    };
    tools_["list_instance_facts"] = [this](const Json& args) { return instance_facts(args); };
    tools_["get_references"] = [this](const Json& args) { return references(args); };
    for (const auto& name : {"get_signal_reads", "get_loads"}) {
        tools_[name] = [this](const Json& args) { return references(args, "read"); };
    }
    for (const auto& name : {"get_signal_writes", "get_drivers"}) {
        tools_[name] = [this](const Json& args) { return references(args, "write"); };
    }
    tools_["trace_connectivity"] = [this](const Json& args) { return trace(args); };
    tools_["get_procedural_blocks"] = [this](const Json& args) { return procedures(args); };
    tools_["get_state_elements"] = [this](const Json& args) { return state_elements(args); };
}

void SemanticService::register_inspection_tools() {
    tools_["inspect_signal"] = [this](const Json& args) { return inspect_signal(args); };
    tools_["inspect_instance"] = [this](const Json& args) { return inspect_instance(args); };
    tools_["inspect_module"] = [this](const Json& args) { return inspect_module(args); };
}

Json SemanticService::diagnostics(const Json& args, bool grouped) {
    const auto severity = diagnostic_severity(args);
    const auto selected = select(manager_.design().diagnostics(), [&](const auto& item) {
        return !severity || item.severity == *severity;
    });
    if (!grouped) {
        auto result = diagnostic_page(selected, limit_for(args));
        result["analysis"] = manager_.analysis_context();
        return result;
    }
    return page(diagnostic_groups(selected), limit_for(args));
}
} // namespace slang_mcp
