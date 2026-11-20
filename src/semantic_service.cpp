#include "semantic_service.hpp"
#include "pagination.hpp"
#include "paths.hpp"
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
        return 1;
    }
    if (!depth->is_number_integer() || *depth < 0 || *depth > 50) {
        throw std::invalid_argument("max_depth must be between 0 and 50");
    }
    return depth->get<int>();
}

using DiagnosticRefs = std::vector<std::reference_wrapper<const Diagnostic>>;

Json diagnostic_group(const std::string& code, const DiagnosticRefs& items) {
    std::map<std::string, int> counts;
    for (const auto& item : items) {
        ++counts[item.get().severity];
    }
    return {{"code", code},
            {"count", items.size()},
            {"severity_counts", counts},
            {"first_location", items.front().get().location}};
}

std::vector<Json> diagnostic_groups(const DiagnosticRefs& diagnostics) {
    std::map<std::string, DiagnosticRefs> groups;
    for (const auto& item : diagnostics) {
        groups[item.get().code].push_back(item);
    }
    std::vector<Json> result;
    result.reserve(groups.size());
    for (const auto& group : groups) {
        result.push_back(diagnostic_group(group.first, group.second));
    }
    return result;
}

Json diagnostic_with_scope_hint(const Diagnostic& diagnostic) {
    // An unresolved name or include can also be a typo.
    static const std::set<std::string> unresolved = {"UnknownModule", "UnknownClassOrPackage",
                                                     "CouldNotOpenIncludeFile"};
    Json result = diagnostic;
    result["scope_hint"] =
        unresolved.contains(diagnostic.code) ? "possible_missing_dependency" : "unclassified";
    return result;
}

struct DiagnosticFilter {
    Text severity, file, code, physical_file;

    [[nodiscard]] bool matches_file(const Diagnostic& item) const {
        return !file || item.location.filename == file ||
               (physical_file && item.physical_file == physical_file);
    }

    bool operator()(const Diagnostic& item) const {
        return (!severity || item.severity == *severity) && matches_file(item) &&
               (!code || item.code == *code);
    }
};

DiagnosticRefs filtered_diagnostics(const std::vector<Diagnostic>& diagnostics, const Json& args) {
    DiagnosticRefs result;
    const auto file = text_option(args, "file");
    const DiagnosticFilter filter{diagnostic_severity(args), file, text_option(args, "code"),
                                  file ? canonical_absolute_path(*file) : std::nullopt};
    std::ranges::copy_if(diagnostics, std::back_inserter(result), filter);
    return result;
}

std::uint64_t diagnostic_attempt_id(const Json& args) {
    if (!args.contains("attempt_id")) {
        return 0;
    }
    const auto& id = args.at("attempt_id");
    if (!id.is_number_integer() || id <= 0) {
        throw std::invalid_argument("attempt_id must be a positive integer");
    }
    return id.get<std::uint64_t>();
}

struct DiagnosticSource {
    const std::vector<Diagnostic>& records;
    Json analysis;
    std::uint64_t revision;
};

DiagnosticSource diagnostic_source(ProjectManager& manager, std::uint64_t id) {
    if (id == 0) {
        return {manager.design().diagnostics(), manager.analysis_context(), manager.revision()};
    }
    const auto& attempt = manager.failed_attempt(id);
    return {attempt.diagnostics, attempt.context(), id};
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
    tools_["project_info"] = [this](const Json& args) { return manager_.info(args); };
    tools_["semantic_diff"] = [this](const Json& args) { return manager_.diff(limit_for(args)); };
    tools_["get_diagnostics"] = [this](const Json& args) { return diagnostics(args, false); };
    tools_["summarize_diagnostics_by_code"] = [this](const Json& args) {
        return diagnostics(args, true);
    };
}

void SemanticService::register_symbol_tools() {
    tools_["find_symbol"] = [this](const Json& args) { return find_symbol(args); };
    tools_["describe_symbol"] = [this](const Json& args) -> Json {
        const auto identifier = args.at("identifier").get<std::string>();
        auto& design = manager_.design();
        Json result = design.describe(identifier, type_depth_for(args));
        if (option(args, "include_origin", false)) {
            result["origin"] = design.symbol_origin(identifier);
        }
        return result;
    };
    tools_["get_hierarchy"] = [this](const Json& args) { return hierarchy(args); };
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

Json SemanticService::find_symbol(const Json& args) {
    const Pagination page(args, "find_symbol", manager_.revision());
    const auto items = manager_.design().find_symbols(args.at("name"), text_option(args, "scope"));
    return page.render(items, "symbols", [](auto item) -> const auto& { return item.get(); },
                       {{"match_count", items.size()}});
}

Json SemanticService::hierarchy(const Json& args) {
    auto& design = manager_.design();
    const Pagination page(args, "get_hierarchy", manager_.revision());
    const auto positions =
        design.hierarchy_positions(text_option(args, "root"), hierarchy_depth(args));
    return page.render(positions, "items",
                       [&](auto index) { return design.hierarchy_entry(index); });
}

Json SemanticService::diagnostics(const Json& args, bool grouped) {
    const auto source = diagnostic_source(manager_, diagnostic_attempt_id(args));
    const Pagination page(args, "get_diagnostics", source.revision);
    const auto selected = filtered_diagnostics(source.records, args);
    const Json metadata = {{"analysis", source.analysis}};
    if (grouped || option(args, "summary", false)) {
        return page.render(diagnostic_groups(selected), "items", std::identity{}, metadata);
    }
    return page.render(selected, "diagnostics", diagnostic_with_scope_hint, metadata);
}
} // namespace slang_mcp
