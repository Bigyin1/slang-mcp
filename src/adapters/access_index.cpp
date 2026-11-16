#include "adapters/internal.hpp"

#include <set>

namespace slang_mcp::adapters {
namespace {
struct AccessContext {
    std::string instance, scope;
    std::string kind = "read";
    std::string operation = "expression";
    Text block;
};

struct Dependency {
    std::vector<const ast::ValueSymbol*> sources, targets;
    std::string kind;
    slang::SourceLocation location;
    std::string operation;
};

Text sensitivity(const ast::Statement& statement) {
    if (auto* timed = statement.as_if<ast::TimedStatement>(); timed && timed->timing.syntax) {
        return timed->timing.syntax->toString();
    }
    return std::nullopt;
}

std::string assignment_operation(const ast::AssignmentExpression& expression,
                                 const std::string& enclosing) {
    if (enclosing == "continuous_assignment") {
        return enclosing;
    }
    return expression.isNonBlocking() ? "nonblocking_assignment" : "blocking_assignment";
}

class AccessVisitor : public ast::ASTVisitor<AccessVisitor, ast::VisitFlags::AllGood> {
  public:
    AccessVisitor(const slang::SourceManager& manager, AccessIndex& index, AccessContext context)
        : manager_(manager), index_(index), context_(std::move(context)) {}

    template <class T> void scan(const T& node, AccessContext context) {
        AccessVisitor visitor(manager_, index_, std::move(context));
        node.visit(visitor);
    }

    void handle(const ast::InstanceSymbol&) {}

    void handle(const ast::GenerateBlockSymbol& symbol) {
        if (symbol.isUninstantiated) {
            return;
        }
        auto context = context_;
        context.scope = qualified(symbol);
        for (const auto& member : symbol.members()) {
            scan(member, context);
        }
    }

    void handle(const ast::ValueExpressionBase& expression) {
        record(expression.symbol, expression.sourceRange.start(), context_);
    }

    void record(const ast::Symbol& symbol, slang::SourceLocation source,
                const AccessContext& context) {
        index_.references.push_back(
            {reference(symbol, manager_),
             symbol.kind == ast::SymbolKind::Parameter ? "parameter_reference" : context.kind,
             location(source, manager_), context.scope, optional_text(context.instance),
             context.operation, context.block});
        index_.references_by_symbol[index_.references.back().symbol.symbol_id].push_back(
            index_.references.size() - 1);
    }

    void handle(const ast::ContinuousAssignSymbol& symbol) {
        auto context = context_;
        context.operation = "continuous_assignment";
        scan(symbol.getAssignment(), context);
    }

    void handle(const ast::SubroutineSymbol& symbol) {
        auto context = context_;
        context.scope = qualified(symbol);
        scan(symbol.getBody(), context);
    }

    void handle(const ast::VariableSymbol& symbol) {
        variable(symbol);
    }

    void handle(const ast::NetSymbol& symbol) {
        variable(symbol);
    }

    void variable(const ast::ValueSymbol& symbol) {
        auto declaration = context_;
        declaration.kind = "declaration";
        record(symbol, symbol.location, declaration);
        const auto* initializer = symbol.getInitializer();
        if (!initializer) {
            return;
        }
        auto write = context_;
        write.kind = "write";
        write.operation = "declaration_assignment";
        record(symbol, symbol.location, write);
        scan(*initializer, context_);
        if (!index_.connectivity) {
            return;
        }
        dependency({expression_symbols(*initializer),
                    {&symbol},
                    "procedural_assignment",
                    symbol.location,
                    write.operation});
    }

    void handle(const ast::AssignmentExpression& expression) {
        auto context = context_;
        context.operation = assignment_operation(expression, context.operation);
        context.kind = expression.isCompound() ? "read_write" : "write";
        lvalue(expression.left(), context);
        context.kind = "read";
        scan(expression.right(), context);
        if (index_.connectivity) {
            assignment_dependency(expression, context);
        }
    }

    void assignment_dependency(const ast::AssignmentExpression& expression,
                               const AccessContext& context) {
        auto sources = expression_symbols(expression.right());
        const auto targets = expression_symbols(expression.left());
        if (expression.isCompound()) {
            sources.insert(sources.end(), targets.begin(), targets.end());
        }
        dependency({sources, targets,
                    context.operation == "continuous_assignment" ? "continuous_assignment"
                                                                 : "procedural_assignment",
                    expression.sourceRange.start(),
                    expression.isCompound() ? "compound_" + context.operation : context.operation});
    }

    void lvalue(const ast::Expression& expression, const AccessContext& context) {
        auto read = context;
        read.kind = "read";
        if (auto* select = expression.as_if<ast::ElementSelectExpression>()) {
            lvalue(select->value(), context);
            scan(select->selector(), read);
        } else if (auto* range = expression.as_if<ast::RangeSelectExpression>()) {
            lvalue(range->value(), context);
            scan(range->left(), read);
            scan(range->right(), read);
        } else if (auto* concatenation = expression.as_if<ast::ConcatenationExpression>()) {
            for (const auto* operand : concatenation->operands()) {
                lvalue(*operand, context);
            }
        } else {
            scan(expression, context);
        }
    }

    void handle(const ast::UnaryExpression& expression) {
        const auto operation = ast::toString(expression.op);
        if (operation == "Preincrement" || operation == "Postincrement" ||
            operation == "Predecrement" || operation == "Postdecrement") {
            auto context = context_;
            context.kind = "read_write";
            context.operation = "increment";
            lvalue(expression.operand(), context);
            return;
        }
        visitDefault(expression);
    }

    void handle(const ast::CallExpression& expression) {
        auto context = context_;
        if (expression.isSystemCall()) {
            context.kind = "unknown";
            context.operation = "system_call";
            for (const auto* argument : expression.arguments()) {
                scan(*argument, context);
            }
            return;
        }
        const auto& function = *std::get<0>(expression.subroutine);
        context.kind = "unknown";
        context.operation = "subroutine_call";
        record(function, expression.sourceRange.start(), context);
        context.operation = "call_argument";
        const auto formals = function.getArguments();
        for (std::size_t index = 0; index < std::min(formals.size(), expression.arguments().size());
             ++index) {
            context.kind = direction_kind(formals[index]->direction);
            actual(*expression.arguments()[index], context);
        }
    }

    void actual(const ast::Expression& expression, const AccessContext& context) {
        if (context.kind == "write" || context.kind == "read_write") {
            lvalue(expression, context);
        } else {
            scan(expression, context);
        }
    }

    void handle(const ast::ProceduralBlockSymbol& symbol) {
        auto context = context_;
        const auto source = location(symbol.location, manager_);
        const std::string procedure_kind(ast::toString(symbol.procedureKind));
        context.block = context.instance + ":" + procedure_kind + ":" +
                        source.filename.value_or("") + ":" +
                        std::to_string(source.line.value_or(0)) + ":" +
                        std::to_string(source.column.value_or(0));
        const auto start = index_.references.size();
        scan(symbol.getBody(), context);
        index_.block_writes[context.block.value()] = all_names(start, "write");
        index_.procedures.push_back({context.block.value(), procedure_kind, context.instance,
                                     source, names(start, "read"), names(start, "write"),
                                     sensitivity(symbol.getBody())});
    }

    void binding(const ast::PortConnection& connection) {
        if (connection.port.kind != ast::SymbolKind::Port) {
            return;
        }
        const auto* expression = connection.getExpression();
        if (!expression) {
            return;
        }
        const auto& port = connection.port.as<ast::PortSymbol>();
        auto context = context_;
        context.kind = direction_kind(port.direction);
        context.operation = "port_connection";
        actual(*expression, context);
        if (auto* assignment = expression->as_if<ast::AssignmentExpression>()) {
            expression = &assignment->left();
        }
        if (auto* value = expression->as_if<ast::NamedValueExpression>();
            value && port.internalSymbol) {
            port_edges(value->symbol, port, expression->sourceRange.start());
        }
    }

  private:
    const slang::SourceManager& manager_;
    AccessIndex& index_;
    AccessContext context_;

    void dependency(const Dependency& edge) {
        for (const auto* from : edge.sources) {
            for (const auto* to : edge.targets) {
                add_edge(*from, *to, edge);
            }
        }
    }

    void add_edge(const ast::ValueSymbol& from, const ast::ValueSymbol& to,
                  const Dependency& edge) {
        if (qualified(from) != qualified(to)) {
            index_.edges.push_back(
                {qualified(from), qualified(to), edge.kind, location(edge.location, manager_),
                 optional_text(context_.instance), std::nullopt, edge.operation});
        }
    }

    void port_edges(const ast::ValueSymbol& actual, const ast::PortSymbol& port,
                    slang::SourceLocation source) {
        if (!index_.connectivity) {
            return;
        }
        const auto from = qualified(actual);
        const auto to = qualified(*port.internalSymbol);
        if (port.direction != ast::ArgumentDirection::Out) {
            index_.edges.push_back({from, to, "port_binding", location(source, manager_),
                                    context_.scope, std::string(port.name),
                                    lower(ast::toString(port.direction))});
        }
        if (port.direction != ast::ArgumentDirection::In) {
            index_.edges.push_back({to, from, "port_binding", location(source, manager_),
                                    context_.scope, std::string(port.name),
                                    lower(ast::toString(port.direction))});
        }
    }

    std::vector<std::string> all_names(std::size_t start, const std::string& access_kind) const {
        std::set<std::string> result;
        for (std::size_t index = start; index < index_.references.size(); ++index) {
            const auto& item = index_.references[index];
            if (item.kind == access_kind || item.kind == "read_write") {
                result.insert(item.symbol.qualified_name);
            }
        }
        return {result.begin(), result.end()};
    }

    Page<std::string> names(std::size_t start, const std::string& access_kind) const {
        return page(all_names(start, access_kind), 500);
    }
};
} // namespace

void index_accesses(const ast::InstanceSymbol& instance, const slang::SourceManager& manager,
                    AccessIndex& index) {
    const auto path = qualified(instance);
    AccessVisitor visitor(manager, index, {path, path, "read", "expression", std::nullopt});
    for (const auto& member : instance.body.members()) {
        member.visit(visitor);
    }
    AccessVisitor ports(
        manager, index,
        {parent_path(path).value_or(path), path, "read", "port_connection", std::nullopt});
    for (const auto* connection : instance.getPortConnections()) {
        ports.binding(*connection);
    }
}
} // namespace slang_mcp::adapters
