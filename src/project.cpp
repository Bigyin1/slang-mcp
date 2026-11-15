#include "project.hpp"
#include "query.hpp"

#include <filesystem>
#include <fstream>
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

std::vector<std::string> read_list(const std::string& file, bool directories) {
    std::vector<std::string> result;
    validate_path(file, false);
    std::ifstream input(file);
    if (!input) {
        throw std::invalid_argument("cannot read file list: " + file);
    }
    std::string line;
    while (std::getline(input, line)) {
        auto path = trim(line);
        if (!path.empty()) {
            validate_path(path, directories);
            result.push_back(std::move(path));
        }
    }
    return result;
}

std::vector<std::string> read_lists(const Json& lists, bool directories) {
    std::vector<std::string> result;
    for (const auto& item : lists) {
        auto paths = read_list(item.get<std::string>(), directories);
        result.insert(result.end(), paths.begin(), paths.end());
    }
    return result;
}

std::map<std::string, Text> parse_defines(const Json& values) {
    std::map<std::string, Text> result;
    for (const auto& [name, value] : values.items()) {
        result[name] = value.is_null() ? std::nullopt : Text(value.get<std::string>());
    }
    return result;
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
    result.source_files = read_lists(arguments.at("source_file_lists"), false);
    if (result.source_files.empty()) {
        throw std::invalid_argument("source_file_lists must contain at least one source file");
    }
    result.include_directories =
        read_lists(option(arguments, "include_directory_lists", Json::array()), true);
    result.defines = parse_defines(option(arguments, "defines", Json::object()));
    result.top_modules = {result.logical_module};
    result.metadata = {{"load_format", "absolute_path_file_lists"}};
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
    auto candidate = std::make_unique<adapters::Design>(config);
    auto next_snapshot = snapshot(*candidate);
    auto previous = design_ && config_.logical_module == config.logical_module
                        ? std::optional(snapshot_)
                        : std::nullopt;
    config_ = std::move(config);
    design_ = std::move(candidate);
    snapshot_ = std::move(next_snapshot);
    previous_ = std::move(previous);
    return summary();
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
    return {{"logical_module", config_.logical_module},
            {"source_file_count", config_.source_files.size()},
            {"include_directory_count", config_.include_directories.size()},
            {"define_count", config_.defines.size()},
            {"top_modules", design().tops()},
            {"diagnostic_error_count", errors},
            {"diagnostic_warning_count", warnings}};
}

Json ProjectManager::info() {
    (void)design();
    std::vector<std::string> defines;
    defines.reserve(config_.defines.size());
    for (const auto& [name, value] : config_.defines) {
        defines.push_back(value ? name + "=" + *value : name);
    }
    return {{"summary", summary()},
            {"source_files", config_.source_files},
            {"include_directories", config_.include_directories},
            {"defines", defines},
            {"configured_top_modules", config_.top_modules},
            {"metadata", config_.metadata},
            {"slang_version", design().version()}};
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
