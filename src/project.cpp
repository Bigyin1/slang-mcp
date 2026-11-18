#include "project.hpp"
#include "pagination.hpp"
#include "query.hpp"

#include <filesystem>
#include <set>

namespace slang_mcp {
namespace {
std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return {};
    }
    return value.substr(first, value.find_last_not_of(" \t\r\n") - first + 1);
}

void validate_path(const std::string& path, bool directory) {
    const std::filesystem::path value(path);
    if (!value.is_absolute()) {
        throw std::invalid_argument("expected an absolute path: " + path);
    }
    if (directory ? !is_directory(value) : !is_regular_file(value)) {
        throw std::invalid_argument("missing or invalid path: " + path);
    }
}

std::map<std::string, Text> parse_defines(const Json& values) {
    std::map<std::string, Text> result;
    for (const auto& [name, value] : values.items()) {
        result[name] = value.is_null() ? std::nullopt : Text(value.get<std::string>());
    }
    return result;
}

bool parse_single_unit(const Json& arguments) {
    const auto value = arguments.find("single_unit");
    if (value == arguments.end()) {
        return true;
    }
    if (!value->is_boolean()) {
        throw std::invalid_argument("single_unit must be a boolean");
    }
    return value->get<bool>();
}

void validate_configuration_page(const Json& arguments) {
    const auto limit = arguments.value("limit", Json(100));
    if (!limit.is_number_integer() || limit < 1 || limit > 500) {
        throw std::invalid_argument("limit must be an integer between 1 and 500");
    }
    if (!arguments.value("cursor", Json("")).is_string()) {
        throw std::invalid_argument("cursor must be a string");
    }
}

Json nullable(const std::map<std::string, std::string>& values, const std::string& key) {
    const auto item = values.find(key);
    return item == values.end() ? Json(nullptr) : Json(item->second);
}

void snapshot_signature(std::map<std::string, std::string>& result, adapters::Design& design,
                        const SymbolReference& definition) {
    try {
        for (const auto& port : design.ports(definition.symbol_id)) {
            Json item = port;
            item.erase("location");
            result["port:" + definition.symbol_id + "." + port.name] = item.dump();
        }
        for (const auto& parameter : design.parameters(definition.symbol_id, false)) {
            result["parameter:" + definition.symbol_id + "." + parameter.name] =
                Json(parameter).dump();
        }
    } catch (const std::invalid_argument&) {
        result["signature_unavailable:" + definition.symbol_id] = "default elaboration unavailable";
    }
}

void snapshot_instances(std::map<std::string, std::string>& result, adapters::Design& design) {
    for (const auto& instance : design.instances()) {
        result["instance:" + instance.path] = instance.sv_module;
        for (const auto& parameter : design.parameters(instance.path, true)) {
            result["effective_parameter:" + instance.path + "." + parameter.name] =
                Json(parameter).dump();
        }
    }
}

void add_keys(std::set<std::string>& keys, const std::map<std::string, std::string>& values) {
    for (const auto& item : values) {
        keys.insert(item.first);
    }
}

std::vector<Json> changes_between(const std::map<std::string, std::string>& previous,
                                  const std::map<std::string, std::string>& current) {
    std::vector<Json> result;
    std::set<std::string> keys;
    add_keys(keys, previous);
    add_keys(keys, current);
    for (const auto& key : keys) {
        if (nullable(previous, key) != nullable(current, key)) {
            const auto separator = key.find(':');
            result.push_back({{"category", key.substr(0, separator)},
                              {"identity", key.substr(separator + 1)},
                              {"before", nullable(previous, key)},
                              {"after", nullable(current, key)}});
        }
    }
    return result;
}
} // namespace

ProjectConfig project_from_arguments(const Json& arguments) {
    ProjectConfig result;
    result.logical_module = arguments.at("top_module").get<std::string>();
    if (trim(result.logical_module).empty()) {
        throw std::invalid_argument("top_module must not be empty");
    }
    result.source_files = arguments.at("source_files").get<std::vector<std::string>>();
    if (result.source_files.empty()) {
        throw std::invalid_argument("source_files must contain at least one source file");
    }
    result.include_directories =
        option(arguments, "include_directories", std::vector<std::string>{});
    result.defines = parse_defines(option(arguments, "defines", Json::object()));
    result.single_unit = parse_single_unit(arguments);
    result.top_modules = {result.logical_module};
    result.metadata = {{"load_format", "absolute_paths"},
                       {"analysis_scope", "fragment"},
                       {"parameter_context", "standalone_top"},
                       {"dependency_resolution", "provided_files_only"},
                       {"completeness", "not_verified"}};
    return result;
}

adapters::Design& ProjectManager::design() {
    if (!design_) {
        throw std::invalid_argument("no project is loaded");
    }
    return *design_;
}

Json ProjectManager::load(ProjectConfig config) {
    for (const auto& source : config.source_files) {
        validate_path(source, false);
    }
    for (const auto& include : config.include_directories) {
        validate_path(include, true);
    }
    auto candidate = build(config);
    auto next_snapshot =
        snapshot_policy_ == SnapshotPolicy::Track ? snapshot(*candidate) : Snapshot{};
    auto previous = design_ && config_.logical_module == config.logical_module
                        ? std::optional(snapshot_)
                        : std::nullopt;
    config_ = std::move(config);
    design_ = std::move(candidate);
    snapshot_ = std::move(next_snapshot);
    previous_ = std::move(previous);
    ++revision_;
    failure_.reset();
    return summary();
}

std::unique_ptr<adapters::Design> ProjectManager::build(const ProjectConfig& config) {
    try {
        return std::make_unique<adapters::Design>(config);
    } catch (CompilationError& error) {
        error.attempt_id = ++attempt_id_;
        failure_.emplace(error);
        throw;
    }
}

const CompilationError& ProjectManager::failed_attempt(std::uint64_t id) const {
    if (!failure_ || failure_->attempt_id != id) {
        throw std::invalid_argument("unknown or expired compilation attempt");
    }
    return *failure_;
}

Json ProjectManager::reload() {
    (void)design();
    return load(config_);
}

Json ProjectManager::summary() {
    const auto& diagnostics = design().diagnostics();
    const auto errors = std::ranges::count_if(diagnostics, [](const auto& item) {
        return item.severity == "error" || item.severity == "fatal";
    });
    const auto warnings = std::ranges::count_if(
        diagnostics, [](const auto& item) { return item.severity == "warning"; });
    Json result = {{"logical_module", config_.logical_module},
                   {"source_file_count", config_.source_files.size()},
                   {"single_unit", config_.single_unit},
                   {"include_directory_count", config_.include_directories.size()},
                   {"define_count", config_.defines.size()},
                   {"top_modules", design().tops()},
                   {"diagnostic_error_count", errors},
                   {"diagnostic_warning_count", warnings}};
    for (const auto* key : {"analysis_scope", "parameter_context", "completeness"}) {
        if (config_.metadata.contains(key)) {
            result[key] = config_.metadata.at(key);
        }
    }
    return result;
}

Json ProjectManager::info(const Json& arguments) {
    (void)design();
    if (arguments.contains("section")) {
        return configuration_page(arguments);
    }
    if (arguments.contains("limit") || arguments.contains("cursor")) {
        throw std::invalid_argument("limit and cursor require a project_info section");
    }
    return {{"summary", summary()},
            {"single_unit", config_.single_unit},
            {"configured_top_modules", config_.top_modules},
            {"metadata", config_.metadata},
            {"slang_version", design().version()}};
}

Json ProjectManager::configuration_page(const Json& arguments) const {
    validate_configuration_page(arguments);
    const auto section = text_option(arguments, "section");
    const Pagination page(arguments, "project_info", revision());
    if (section == "source_files") {
        return page.render(config_.source_files, "items", std::identity{});
    }
    if (section == "include_directories") {
        return page.render(config_.include_directories, "items", std::identity{});
    }
    if (section != "defines") {
        throw std::invalid_argument(
            "section must be source_files, include_directories, or defines");
    }
    std::vector<std::string> defines;
    defines.reserve(config_.defines.size());
    for (const auto& [name, value] : config_.defines) {
        defines.push_back(value ? name + "=" + *value : name);
    }
    return page.render(defines, "items", std::identity{});
}

Json ProjectManager::analysis_context() const {
    const auto scope = config_.metadata.find("analysis_scope");
    return {
        {"analysis_scope", scope == config_.metadata.end() ? "configured_sources" : scope->second},
        {"completeness", "not_verified"},
        {"source_file_count", config_.source_files.size()},
        {"single_unit", config_.single_unit},
        {"top_modules", config_.top_modules}};
}

ProjectManager::Snapshot ProjectManager::snapshot(adapters::Design& design) {
    Snapshot result;
    for (const auto& definition : design.definitions()) {
        result["definition:" + definition.symbol_id] = definition.kind;
        if (definition.kind != "package") {
            snapshot_signature(result, design, definition);
        }
    }
    snapshot_instances(result, design);
    for (const auto& diagnostic : design.diagnostics()) {
        const auto normalized = Json(diagnostic).dump();
        result["diagnostic:" + normalized] = normalized;
    }
    return result;
}

Json ProjectManager::diff(int limit) const {
    validate_limit(limit);
    if (snapshot_policy_ == SnapshotPolicy::Disabled) {
        throw std::invalid_argument("semantic snapshots are disabled for this session");
    }
    if (!design_) {
        throw std::invalid_argument("no project is loaded");
    }
    if (!previous_) {
        return {{"status", "no_previous_state"}, {"changes", page(std::vector<Json>{}, limit)}};
    }
    return {{"status", "compared"},
            {"changes", page(changes_between(*previous_, snapshot_), limit)}};
}
} // namespace slang_mcp
