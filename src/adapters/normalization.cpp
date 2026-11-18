#include "adapters/internal.hpp"

#include <cctype>
#include <set>

namespace slang_mcp::adapters {
std::string lower(std::string_view text) {
    std::string result(text);
    std::ranges::transform(result, result.begin(), [](unsigned char value) {
        return static_cast<char>(std::tolower(value));
    });
    return result;
}

Text optional_text(std::string text) {
    if (text.empty()) {
        return std::nullopt;
    }
    return text;
}

Text parent_path(const std::string& path) {
    auto separator = path.rfind('.');
    if (separator == std::string::npos) {
        separator = path.rfind("::");
    }
    if (separator == std::string::npos) {
        return std::nullopt;
    }
    return path.substr(0, separator);
}

SourceLocation location(slang::SourceLocation source, const slang::SourceManager& manager) {
    if (!source.valid()) {
        return {};
    }
    return {optional_text(std::string(manager.getFileName(source))), manager.getLineNumber(source),
            manager.getColumnNumber(source)};
}

std::string qualified(const ast::Symbol& symbol) {
    auto result = symbol.getHierarchicalPath();
    if (result.empty()) {
        result = symbol.getLexicalPath();
    }
    return result.empty() ? std::string(symbol.name) : result;
}

std::string kind(const ast::Symbol& symbol) {
    if (auto* definition = symbol.as_if<ast::DefinitionSymbol>()) {
        return lower(ast::toString(definition->definitionKind));
    }
    if (auto* subroutine = symbol.as_if<ast::SubroutineSymbol>()) {
        return lower(ast::toString(subroutine->subroutineKind));
    }
    return lower(ast::toString(symbol.kind));
}

SymbolReference reference(const ast::Symbol& symbol, const slang::SourceManager& manager) {
    const auto path = qualified(symbol);
    return {kind(symbol) + ":" + path, std::string(symbol.name),          path, kind(symbol),
            parent_path(path),         location(symbol.location, manager)};
}

Width packed_width(const ast::Type& type) {
    const auto* current = &type.getCanonicalType();
    while (!current->isPackedArray() && current->getArrayElementType()) {
        current = &current->getArrayElementType()->getCanonicalType();
    }
    return current->isIntegral() ? Width(current->getBitWidth()) : std::nullopt;
}

const ast::Type* symbol_type(const ast::Symbol& symbol) {
    if (symbol.isValue()) {
        return &symbol.as<ast::ValueSymbol>().getType();
    }
    if (auto* value = symbol.as_if<ast::PortSymbol>()) {
        return &value->getType();
    }
    if (auto* value = symbol.as_if<ast::TypeAliasType>()) {
        return &value->targetType.getType();
    }
    if (auto* value = symbol.as_if<ast::TypeParameterSymbol>()) {
        return &value->targetType.getType();
    }
    if (auto* value = symbol.as_if<ast::SubroutineSymbol>()) {
        return &value->getReturnType();
    }
    return nullptr;
}

namespace {
const ast::Expression* implicit_operand(const ast::Expression* expression) {
    if (expression->syntax) {
        return expression;
    }
    if (auto* conversion = expression->as_if<ast::ConversionExpression>()) {
        return &conversion->operand();
    }
    if (auto* assignment = expression->as_if<ast::AssignmentExpression>();
        assignment && assignment->isLValueArg()) {
        return &assignment->left();
    }
    return expression;
}

const ast::Expression* source_expression(const ast::Expression* expression) {
    while (expression) {
        const auto* operand = implicit_operand(expression);
        if (operand == expression) {
            break;
        }
        expression = operand;
    }
    return expression;
}

std::string syntax_text(const slang::syntax::SyntaxNode& syntax) {
    const auto text = syntax.toString();
    const auto start = text.find_first_not_of(" \n\r\t");
    if (start == std::string::npos) {
        return {};
    }
    return text.substr(start,
                       std::min<std::size_t>(text.find_last_not_of(" \n\r\t") - start + 1, 1000));
}
} // namespace

Text expression_text(const ast::Expression* original) {
    const auto* expression = source_expression(original);
    if (!expression) {
        return std::nullopt;
    }
    if (expression->syntax) {
        return syntax_text(*expression->syntax);
    }
    if (auto* value = expression->as_if<ast::ValueExpressionBase>()) {
        return qualified(value->symbol);
    }
    const auto* constant = expression->getConstant();
    return constant ? optional_text(constant->toString()) : std::nullopt;
}

Parameter parameter(const ast::ParameterSymbolBase& symbol) {
    if (auto* type = symbol.symbol.as_if<ast::TypeParameterSymbol>()) {
        return {std::string(type->name), "type",       type->targetType.getType().toString(),
                type->isLocalParam(),    std::nullopt, type->isOverridden()};
    }
    const auto& value = symbol.symbol.as<ast::ParameterSymbol>();
    const auto& constant = value.getValue();
    std::optional<std::int64_t> integer;
    if (constant.isInteger() && !constant.integer().hasUnknown()) {
        integer = constant.integer().as<std::int64_t>();
    }
    return {std::string(value.name),
            value.getType().toString(),
            constant.toString(),
            value.isLocalParam(),
            integer,
            value.isOverridden()};
}

Port port(const ast::Symbol& symbol, const slang::SourceManager& manager) {
    Port result;
    result.name = symbol.name;
    result.location = location(symbol.location, manager);
    if (auto* iface = symbol.as_if<ast::InterfacePortSymbol>()) {
        result.direction = "interface";
        result.type = iface->interfaceDef ? std::string(iface->interfaceDef->name) : "interface";
        result.interface = result.type;
        result.modport = optional_text(std::string(iface->modport));
        return result;
    }
    const auto& value = symbol.as<ast::PortSymbol>();
    result.direction = lower(ast::toString(value.direction));
    result.type = value.getType().toString();
    result.width = packed_width(value.getType());
    result.default_value = expression_text(value.getInitializer());
    const auto* type = &value.getType().getCanonicalType();
    while (auto* array = type->as_if<ast::FixedSizeUnpackedArrayType>()) {
        result.unpacked_dimensions.push_back(array->range.toString());
        type = &array->elementType.getCanonicalType();
    }
    return result;
}

namespace {
struct SymbolCollector : ast::ASTVisitor<SymbolCollector, ast::VisitFlags::AllGood> {
    std::map<std::string, const ast::ValueSymbol*> symbols;
    void handle(const ast::ValueExpressionBase& expression) {
        symbols.emplace(qualified(expression.symbol), &expression.symbol);
    }
};

std::string connection_kind(const ast::Expression* expression) {
    if (!expression) {
        return "unconnected";
    }
    return expression->as_if<ast::ValueExpressionBase>() ? "signal" : "expression";
}
} // namespace

std::vector<const ast::ValueSymbol*> expression_symbols(const ast::Expression& expression) {
    SymbolCollector visitor;
    expression.visit(visitor);
    std::vector<const ast::ValueSymbol*> result;
    result.reserve(visitor.symbols.size());
    for (const auto& [name, symbol] : visitor.symbols) {
        result.push_back(symbol);
    }
    return result;
}

Connection connection(const ast::PortConnection& value, const slang::SourceManager& manager) {
    Connection result;
    result.port = port(value.port, manager);
    if (value.port.kind == ast::SymbolKind::InterfacePort) {
        result.kind = "interface";
        const auto [symbol, modport] = value.getIfaceConn();
        if (symbol) {
            result.symbols.push_back(qualified(*symbol));
        }
        result.location = result.port.location;
        return result;
    }
    const auto* expression = source_expression(value.getExpression());
    result.kind = connection_kind(expression);
    result.expression = expression_text(expression);
    if (expression) {
        result.location = location(expression->sourceRange.start(), manager);
        result.actual_type = expression->type->toString();
        result.actual_width = packed_width(*expression->type);
        for (const auto* symbol : expression_symbols(*expression)) {
            result.symbols.push_back(qualified(*symbol));
        }
    }
    return result;
}

std::string direction_kind(ast::ArgumentDirection direction) {
    switch (direction) {
    case ast::ArgumentDirection::In:
        return "read";
    case ast::ArgumentDirection::Out:
        return "write";
    case ast::ArgumentDirection::InOut:
    case ast::ArgumentDirection::Ref:
        return "read_write";
    }
    return "unknown";
}
} // namespace slang_mcp::adapters
