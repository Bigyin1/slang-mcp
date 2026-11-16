#include "adapters/design.hpp"
#include "adapters/internal.hpp"
#include "compilation_error.hpp"

#include <set>
#include <slang/diagnostics/DiagnosticEngine.h>
#include <slang/parsing/Preprocessor.h>
#include <slang/syntax/SyntaxTree.h>
#include <slang/util/Bag.h>
#include <slang/util/VersionInfo.h>

namespace slang_mcp::adapters {
namespace {
bool searchable(ast::SymbolKind value) {
    static const std::set kinds = {ast::SymbolKind::ClassType,     ast::SymbolKind::Definition,
                                   ast::SymbolKind::Net,           ast::SymbolKind::Package,
                                   ast::SymbolKind::Parameter,     ast::SymbolKind::Port,
                                   ast::SymbolKind::Subroutine,    ast::SymbolKind::TypeAlias,
                                   ast::SymbolKind::TypeParameter, ast::SymbolKind::Variable};
    return kinds.contains(value);
}

struct HierarchyRecord {
    HierarchyNode node;
    std::string parent;
};

bool matches_name(const SymbolReference& symbol, const std::string& query) {
    return symbol.qualified_name == query || symbol.name == query;
}

bool signal_reference(const SymbolReference& symbol, const std::string& query) {
    return symbol.qualified_name == query && (symbol.kind == "variable" || symbol.kind == "net");
}

void append_instantiations(std::vector<Reference>& references, const SymbolReference& symbol,
                           const std::vector<Instance>& instances) {
    if (symbol.kind != "module" && symbol.kind != "interface") {
        return;
    }
    for (const auto& instance : instances) {
        if (instance.sv_module == symbol.name) {
            references.push_back({symbol, "instantiation", instance.location,
                                  instance.parent.value_or(""), instance.path, "instantiation",
                                  std::nullopt});
        }
    }
}

struct IndexVisitor : ast::ASTVisitor<IndexVisitor> {
    std::vector<const ast::Symbol*> symbols;
    std::vector<const ast::InstanceSymbol*> instances;
    std::vector<HierarchyRecord> hierarchy;
    std::string parent;

    template <class T> void handle(const T& symbol) {
        if constexpr (std::is_base_of_v<ast::Symbol, T>) {
            if (searchable(symbol.kind)) {
                symbols.push_back(&symbol);
            }
        }
        visitDefault(symbol);
    }

    void descend(const ast::Symbol& symbol, const std::string& node_kind, Text module) {
        const auto path = qualified(symbol);
        hierarchy.push_back(
            {{path, std::string(symbol.name), node_kind, std::move(module), {}}, parent});
        parent = path;
    }

    void handle(const ast::InstanceSymbol& symbol) {
        const auto previous = parent;
        descend(symbol, "instance", std::string(symbol.getDefinition().name));
        instances.push_back(&symbol);
        visitDefault(symbol);
        parent = previous;
    }

    void handle(const ast::GenerateBlockSymbol& symbol) {
        if (symbol.isUninstantiated) {
            return;
        }
        const auto previous = parent;
        descend(symbol, "generateblock", std::nullopt);
        visitDefault(symbol);
        parent = previous;
    }

    void handle(const ast::GenerateBlockArraySymbol& symbol) {
        const auto previous = parent;
        descend(symbol, "generateblockarray", std::nullopt);
        visitDefault(symbol);
        parent = previous;
    }

    void handle(const ast::InstanceArraySymbol& symbol) {
        const auto previous = parent;
        descend(symbol, "instancearray", std::nullopt);
        visitDefault(symbol);
        parent = previous;
    }
};

slang::Bag compilation_options(const ProjectConfig& config) {
    slang::parsing::PreprocessorOptions parser;
    parser.additionalIncludePaths.assign(config.include_directories.begin(),
                                         config.include_directories.end());
    for (const auto& define : config.defines) {
        parser.predefines.push_back(define.second ? define.first + "=" + *define.second
                                                  : define.first);
    }
    ast::CompilationOptions compiler;
    for (const auto& top : config.top_modules) {
        compiler.topModules.emplace(top);
    }
    compiler.flags |= ast::CompilationFlags::DisableInstanceCaching;
    slang::Bag options;
    options.set(parser);
    options.set(compiler);
    return options;
}

void add_unit(ast::Compilation& compilation, std::span<const std::string_view> sources,
              slang::SourceManager& manager, const slang::Bag& options) {
    auto tree = slang::syntax::SyntaxTree::fromFiles(sources, manager, options);
    if (!tree) {
        throw std::runtime_error("Slang source read failed: " + tree.error().first.message());
    }
    compilation.addSyntaxTree(*tree);
}

std::unique_ptr<ast::Compilation> compile(const ProjectConfig& config,
                                          slang::SourceManager& manager) {
    const auto options = compilation_options(config);
    const std::vector<std::string_view> sources(config.source_files.begin(),
                                                config.source_files.end());
    auto result = std::make_unique<ast::Compilation>(options);
    if (config.single_unit) {
        add_unit(*result, sources, manager, options);
    } else {
        for (const auto& source : sources) {
            add_unit(*result, std::span(&source, 1), manager, options);
        }
    }
    result->getRoot();
    result->getAllDiagnostics();
    return result;
}

std::unique_ptr<ast::Compilation> compile_default(const ProjectConfig& config,
                                                  const ast::Compilation& active) {
    auto result = std::make_unique<ast::Compilation>(compilation_options(config));
    for (const auto& tree : active.getSyntaxTrees()) {
        result->addSyntaxTree(tree);
    }
    result->getRoot();
    return result;
}

std::vector<Diagnostic> diagnostics(ast::Compilation& compilation, slang::SourceManager& manager) {
    slang::DiagnosticEngine engine(manager);
    std::vector<Diagnostic> result;
    for (const auto& diagnostic : compilation.getAllDiagnostics()) {
        result.push_back(
            {lower(slang::toString(engine.getSeverity(diagnostic.code, diagnostic.location))),
             std::string(slang::toString(diagnostic.code)), engine.formatMessage(diagnostic),
             location(diagnostic.location, manager)});
    }
    return result;
}

std::vector<Parameter> instance_parameters(const ast::InstanceSymbol& instance) {
    std::vector<Parameter> result;
    for (const auto* item : instance.body.getParameters()) {
        result.push_back(parameter(*item));
    }
    return result;
}

std::vector<Port> instance_ports(const ast::InstanceSymbol& instance,
                                 const slang::SourceManager& manager) {
    std::vector<Port> result;
    for (const auto* item : instance.body.getPortList()) {
        if (item->kind == ast::SymbolKind::Port || item->kind == ast::SymbolKind::InterfacePort) {
            result.push_back(port(*item, manager));
        }
    }
    return result;
}
} // namespace

struct Design::Impl {
    ProjectConfig config;
    slang::SourceManager manager;
    std::unique_ptr<ast::Compilation> compilation;
    std::vector<Diagnostic> diagnostic_items;
    std::vector<SymbolReference> symbols;
    std::map<std::string, const ast::Symbol*> raw_symbols;
    std::map<std::string, SymbolReference> default_symbols;
    std::vector<Instance> instance_items;
    std::map<std::string, std::size_t> instance_positions;
    std::map<std::string, const ast::InstanceSymbol*> raw_instances;
    std::vector<HierarchyRecord> hierarchy;
    std::map<std::string, std::vector<std::size_t>> hierarchy_children;
    std::map<std::string, std::unique_ptr<ast::Compilation>> defaults;
    std::optional<AccessIndex> access_index;

    explicit Impl(const ProjectConfig& value)
        : config(value), compilation(compile(config, manager)) {
        diagnostic_items = adapters::diagnostics(*compilation, manager);
        index();
        for (const auto& top : config.top_modules) {
            if (!raw_instances.contains(top)) {
                throw CompilationError("Cannot elaborate requested top: " + top +
                                           ". Any previously active project is unchanged.",
                                       diagnostic_items, config);
            }
        }
    }

    void index() {
        for (const auto* symbol : compilation->getDefinitions()) {
            add_symbol(*symbol);
        }
        IndexVisitor visitor;
        for (const auto* top : compilation->getRoot().topInstances) {
            top->visit(visitor);
        }
        visit_units(visitor);
        index_hierarchy(std::move(visitor.hierarchy));
        for (const auto* symbol : visitor.symbols) {
            add_symbol(*symbol);
        }
        for (const auto* instance : visitor.instances) {
            add_instance(*instance);
        }
    }

    void index_hierarchy(std::vector<HierarchyRecord> records) {
        hierarchy = std::move(records);
        for (std::size_t index = 0; index < hierarchy.size(); ++index) {
            hierarchy_children[hierarchy[index].parent].push_back(index);
        }
    }

    void visit_units(IndexVisitor& visitor) const {
        for (const auto* unit : compilation->getRoot().compilationUnits) {
            unit->visit(visitor);
        }
    }

    void add_symbol(const ast::Symbol& symbol) {
        auto item = reference(symbol, manager);
        if (raw_symbols.emplace(item.symbol_id, &symbol).second) {
            symbols.push_back(std::move(item));
        }
    }

    void add_instance(const ast::InstanceSymbol& symbol) {
        const auto path = qualified(symbol);
        instance_positions.emplace(path, instance_items.size());
        instance_items.push_back({path, std::string(symbol.name),
                                  std::string(symbol.getDefinition().name),
                                  location(symbol.location, manager), std::nullopt});
        raw_instances.emplace(path, &symbol);
        auto* scope = symbol.getParentScope();
        while (scope && scope->asSymbol().kind != ast::SymbolKind::InstanceBody) {
            scope = scope->asSymbol().getParentScope();
        }
        if (scope) {
            instance_items.back().parent = qualified(scope->asSymbol());
        }
    }

    const ast::Symbol& resolve(const std::string& query) const {
        if (auto item = raw_symbols.find(query); item != raw_symbols.end()) {
            return *item->second;
        }
        std::vector<const ast::Symbol*> matches;
        for (const auto& symbol : symbols) {
            if (matches_name(symbol, query)) {
                matches.push_back(raw_symbols.at(symbol.symbol_id));
            }
        }
        if (matches.size() != 1) {
            throw std::invalid_argument(
                (matches.empty() ? "unknown symbol: " : "ambiguous symbol: ") + query);
        }
        return *matches.front();
    }

    std::vector<SymbolReference> default_members(const std::string& query) {
        std::vector<SymbolReference> result;
        const std::string name(resolve(query).name);
        for (const auto& member : default_instance(query).body.members()) {
            if (!searchable(member.kind)) {
                continue;
            }
            auto item = reference(member, manager);
            item.qualified_name = name + "." + std::string(member.name);
            item.containing_scope = name;
            item.symbol_id = "default:" + item.kind + ":" + item.qualified_name;
            raw_symbols.emplace(item.symbol_id, &member);
            default_symbols.try_emplace(item.symbol_id, item);
            result.push_back(std::move(item));
        }
        return result;
    }

    const ast::InstanceSymbol* representative(const ast::Symbol& symbol) const {
        if (symbol.kind != ast::SymbolKind::Definition) {
            return nullptr;
        }
        for (const auto& item : raw_instances) {
            if (item.second->getDefinition().name == symbol.name) {
                return item.second;
            }
        }
        return nullptr;
    }

    void describe_signature(SymbolDescription& result, const ast::Symbol& symbol) const {
        const auto* instance = representative(symbol);
        if (!instance) {
            return;
        }
        result.parameters = instance_parameters(*instance);
        for (const auto& item : instance_ports(*instance, manager)) {
            result.ports.push_back({item.name, item.direction, item.type, item.width});
        }
    }

    const ast::InstanceSymbol& default_instance(const std::string& query) {
        const auto& definition = resolve(query);
        if (definition.kind != ast::SymbolKind::Definition) {
            throw std::invalid_argument("not a module or interface: " + query);
        }
        const std::string name(definition.name);
        if (!defaults.contains(name)) {
            auto inputs = config;
            inputs.top_modules = {name};
            auto candidate = compile_default(inputs, *compilation);
            if (candidate->getRoot().topInstances.size() != 1) {
                throw std::invalid_argument("default signature unavailable: " + name);
            }
            defaults.emplace(name, std::move(candidate));
        }
        return *defaults.at(name)->getRoot().topInstances.front();
    }

    HierarchyNode node(const HierarchyRecord& record, int depth) const {
        auto result = record.node;
        if (depth == 0) {
            return result;
        }
        if (const auto children = hierarchy_children.find(result.path);
            children != hierarchy_children.end()) {
            for (const auto child : children->second) {
                result.children.push_back(node(hierarchy[child], depth - 1));
            }
        }
        return result;
    }
};

Design::Design(const ProjectConfig& config) : impl_(std::make_unique<Impl>(config)) {}
Design::~Design() = default;

MacroExpansion Design::expand_macro(const MacroQuery& query) const {
    return adapters::expand_macro(*impl_->compilation, impl_->manager, query);
}

const std::vector<Diagnostic>& Design::diagnostics() const {
    return impl_->diagnostic_items;
}

std::string Design::version() const {
    return std::to_string(slang::VersionInfo::getMajor()) + "." +
           std::to_string(slang::VersionInfo::getMinor()) + "." +
           std::to_string(slang::VersionInfo::getPatch()) + "+" +
           std::string(slang::VersionInfo::getHash());
}

std::vector<std::string> Design::tops() const {
    std::vector<std::string> result;
    for (const auto* top : impl_->compilation->getRoot().topInstances) {
        result.push_back(qualified(*top));
    }
    return result;
}

std::vector<SymbolReference> Design::find_symbols(const std::string& name) const {
    if (name.empty()) {
        throw std::invalid_argument("name must not be empty");
    }
    std::vector<SymbolReference> result;
    std::ranges::copy_if(impl_->symbols, std::back_inserter(result),
                         [&](const auto& item) { return item.name == name; });
    return result;
}

std::vector<SymbolReference> Design::definitions() const {
    std::vector<SymbolReference> result;
    std::ranges::copy_if(impl_->symbols, std::back_inserter(result), [](const auto& item) {
        return item.kind == "module" || item.kind == "interface" || item.kind == "package";
    });
    return result;
}

std::vector<SymbolReference> Design::members(const std::string& scope) {
    auto path = scope;
    if (std::ranges::none_of(impl_->hierarchy, [&](const auto& item) {
            return !item.parent.empty() && item.node.path == scope;
        })) {
        const auto& symbol = impl_->resolve(scope);
        if (symbol.kind == ast::SymbolKind::Definition) {
            return impl_->default_members(scope);
        }
        path = qualified(symbol);
    }
    std::vector<SymbolReference> result;
    std::ranges::copy_if(impl_->symbols, std::back_inserter(result),
                         [&](const auto& item) { return item.containing_scope == path; });
    return result;
}

SymbolReference Design::definition_reference(const std::string& identifier) const {
    const auto& symbol = impl_->resolve(identifier);
    if (symbol.kind != ast::SymbolKind::Definition) {
        throw std::invalid_argument("not a module or interface: " + identifier);
    }
    return reference(symbol, impl_->manager);
}

SymbolDescription Design::describe(const std::string& identifier, int type_depth) {
    const auto& symbol = impl_->resolve(identifier);
    SymbolDescription result;
    result.symbol = reference(symbol, impl_->manager);
    if (const auto item = impl_->default_symbols.find(identifier);
        item != impl_->default_symbols.end()) {
        result.symbol = item->second;
    }
    if (const auto* type = symbol_type(symbol)) {
        result.type = type->toString();
        result.width = packed_width(*type);
        if (type_depth >= 0) {
            result.type_info = describe_type(*type, type_depth);
        }
    }
    if (auto* value = symbol.as_if<ast::PortSymbol>()) {
        result.direction = lower(ast::toString(value->direction));
    }
    result.members = members(identifier);
    impl_->describe_signature(result, symbol);
    return result;
}

std::vector<HierarchyNode> Design::hierarchy(const Text& root, int depth) const {
    std::vector<HierarchyNode> result;
    for (const auto& item : impl_->hierarchy) {
        if (root ? item.node.path == *root : item.parent.empty()) {
            result.push_back(impl_->node(item, depth));
        }
    }
    if (root && result.empty()) {
        throw std::invalid_argument("unknown hierarchy root: " + *root);
    }
    return result;
}

const std::vector<Instance>& Design::instances() const {
    return impl_->instance_items;
}

Instance Design::instance(const std::string& query) const {
    if (const auto position = impl_->instance_positions.find(query);
        position != impl_->instance_positions.end()) {
        return instances()[position->second];
    }
    std::optional<Instance> result;
    for (const auto& item : instances()) {
        if (item.name != query) {
            continue;
        }
        if (result) {
            throw std::invalid_argument("ambiguous instance: " + query + "; use exact path");
        }
        result = item;
    }
    if (!result) {
        throw std::invalid_argument("unknown elaborated instance: " + query);
    }
    return *result;
}

std::vector<Port> Design::ports(const std::string& module) {
    return instance_ports(impl_->default_instance(module), impl_->manager);
}

std::vector<Parameter> Design::parameters(const std::string& target, bool effective) {
    if (!effective) {
        return instance_parameters(impl_->default_instance(target));
    }
    return instance_parameters(*impl_->raw_instances.at(instance(target).path));
}

std::vector<Connection> Design::connections(const std::string& path) const {
    std::vector<Connection> result;
    for (const auto* item : impl_->raw_instances.at(instance(path).path)->getPortConnections()) {
        result.push_back(connection(*item, impl_->manager));
    }
    return result;
}

const AccessIndex& Design::accesses(bool connectivity) {
    if (!impl_->access_index || (connectivity && !impl_->access_index->connectivity)) {
        AccessIndex candidate;
        candidate.connectivity = connectivity;
        for (const auto& item : instances()) {
            index_accesses(*impl_->raw_instances.at(item.path), impl_->manager, candidate);
        }
        impl_->access_index = std::move(candidate);
    }
    return *impl_->access_index;
}

SymbolDescription Design::signal(const std::string& identifier) {
    if (const auto item = std::ranges::find_if(
            impl_->symbols,
            [&](const auto& symbol) { return signal_reference(symbol, identifier); });
        item != impl_->symbols.end()) {
        return describe(item->symbol_id);
    }
    const auto& raw = impl_->resolve(identifier);
    if (auto* port = raw.as_if<ast::PortSymbol>(); port && port->internalSymbol) {
        return describe(reference(*port->internalSymbol, impl_->manager).symbol_id);
    }
    return describe(identifier);
}

std::vector<Reference> Design::references(const std::string& identifier) {
    const auto symbol = signal(identifier).symbol;
    std::vector<Reference> result;
    const auto& index = accesses();
    if (const auto found = index.references_by_symbol.find(symbol.symbol_id);
        found != index.references_by_symbol.end()) {
        for (const auto position : found->second) {
            result.push_back(index.references[position]);
        }
    }
    if (std::ranges::none_of(result, [](const auto& item) { return item.kind == "declaration"; })) {
        result.insert(result.begin(),
                      {symbol, "declaration", symbol.location, symbol.containing_scope.value_or(""),
                       std::nullopt, "declaration", std::nullopt});
    }
    append_instantiations(result, symbol, instances());
    return result;
}
} // namespace slang_mcp::adapters
