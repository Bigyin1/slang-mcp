#pragma once

#include <algorithm>
#include <cstdint>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace nlohmann {
template <class T> struct adl_serializer<std::optional<T>> {
    static void to_json(json& value, const std::optional<T>& item) {
        value = item ? json(*item) : json(nullptr);
    }
};
} // namespace nlohmann

namespace slang_mcp {
using Json = nlohmann::json;
using Text = std::optional<std::string>;
using Width = std::optional<std::uint64_t>;

struct ProjectConfig {
    bool single_unit = true;
    std::string logical_module;
    std::vector<std::string> source_files;
    std::vector<std::string> include_directories;
    std::map<std::string, Text> defines;
    std::vector<std::string> top_modules;
    std::map<std::string, std::string> metadata;
};

struct SourceLocation {
    Text filename;
    std::optional<std::uint64_t> line;
    std::optional<std::uint64_t> column;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(SourceLocation, filename, line, column)

struct MacroQuery {
    std::string file;
    int line, column;
    int max_bytes = 8192;
};

struct MacroExpansion {
    std::string name;
    SourceLocation invocation, definition;
    std::string expanded_text;
    std::size_t total_bytes = 0;
    bool truncated = false;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(MacroExpansion, name, invocation, definition,
                                                  expanded_text, total_bytes, truncated)

struct Diagnostic {
    std::string severity, code, message;
    SourceLocation location;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(Diagnostic, severity, code, message, location)

struct SymbolReference {
    std::string symbol_id, name, qualified_name, kind;
    Text containing_scope;
    SourceLocation location;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(SymbolReference, symbol_id, name, qualified_name,
                                                  kind, containing_scope, location)

struct Parameter {
    std::string name, type;
    Text value;
    bool is_local = false;
    std::optional<std::int64_t> integer_value;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(Parameter, name, type, value, is_local,
                                                  integer_value)

struct Port {
    std::string name, direction, type;
    Width width;
    SourceLocation location;
    std::vector<std::string> unpacked_dimensions;
    Text interface, modport, default_value;
};
inline void to_json(Json& value, const Port& port) {
    value = {{"name", port.name},
             {"direction", port.direction},
             {"type", port.type},
             {"width", port.width},
             {"location", port.location},
             {"unpacked_dimensions", port.unpacked_dimensions},
             {"interface", port.interface},
             {"modport", port.modport},
             {"default", port.default_value}};
}

struct PortDescription {
    std::string name, direction, type;
    Width width;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(PortDescription, name, direction, type, width)

struct SymbolDescription {
    SymbolReference symbol;
    Text type;
    Width width;
    Text direction;
    std::vector<Parameter> parameters;
    std::vector<PortDescription> ports;
    std::vector<SymbolReference> members;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(SymbolDescription, symbol, type, width, direction,
                                                  parameters, ports, members)

struct HierarchyNode {
    std::string path, name, kind;
    Text sv_module;
    std::vector<HierarchyNode> children;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(HierarchyNode, path, name, kind, sv_module,
                                                  children)

struct Instance {
    std::string path, name, sv_module;
    SourceLocation location;
    Text parent;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(Instance, path, name, sv_module, location, parent)

struct Connection {
    Port port;
    std::string kind;
    Text expression;
    std::vector<std::string> symbols;
    SourceLocation location;
    Text actual_type;
    Width actual_width;
};
inline void to_json(Json& value, const Connection& item) {
    auto symbols = item.symbols;
    symbols.resize(std::min<std::size_t>(symbols.size(), 500));
    value = {{"port", item.port},
             {"kind", item.kind},
             {"expression", item.expression},
             {"symbols", symbols},
             {"location", item.location},
             {"actual_type", item.actual_type},
             {"actual_width", item.actual_width},
             {"symbol_count", item.symbols.size()},
             {"symbols_truncated", item.symbols.size() > 500}};
}

template <class T> struct Page {
    std::vector<T> items;
    std::size_t total_count = 0;
    bool truncated = false;
};
template <class T> void to_json(Json& value, const Page<T>& items) {
    value = {
        {"items", items.items}, {"total_count", items.total_count}, {"truncated", items.truncated}};
}
inline void validate_limit(int limit) {
    if (limit < 1 || limit > 500) {
        throw std::invalid_argument("limit must be between 1 and 500");
    }
}
template <class T> Page<T> page(std::vector<T> items, int limit = 100) {
    validate_limit(limit);
    const auto total = items.size();
    items.resize(std::min(total, static_cast<std::size_t>(limit)));
    return {std::move(items), total, total > static_cast<std::size_t>(limit)};
}

struct Reference {
    SymbolReference symbol;
    std::string kind;
    SourceLocation location;
    std::string scope;
    Text instance;
    std::string context;
    Text block;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(Reference, symbol, kind, location, scope,
                                                  instance, context, block)

struct Procedure {
    std::string block_id, kind, instance;
    SourceLocation location;
    Page<std::string> reads, writes;
    Text sensitivity;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(Procedure, block_id, kind, instance, location,
                                                  reads, writes, sensitivity)

struct ConnectivityHop {
    std::string source, target, kind;
    SourceLocation location;
    Text instance_path, formal_port, operation;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(ConnectivityHop, source, target, kind, location,
                                                  instance_path, formal_port, operation)

struct ConnectivityPath {
    std::string start, end;
    std::vector<ConnectivityHop> hops;
    std::string stop_reason;
};
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_ONLY_SERIALIZE(ConnectivityPath, start, end, hops, stop_reason)

struct AccessIndex {
    std::vector<Reference> references;
    std::vector<Procedure> procedures;
    std::vector<ConnectivityHop> edges;
    std::map<std::string, std::vector<std::string>> block_writes;
};
} // namespace slang_mcp
