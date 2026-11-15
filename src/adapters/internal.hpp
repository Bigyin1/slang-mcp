#pragma once

#include "models.hpp"

#include <slang/ast/ASTVisitor.h>
#include <slang/ast/Compilation.h>
#include <slang/ast/Expression.h>
#include <slang/ast/expressions/AssignmentExpressions.h>
#include <slang/ast/expressions/CallExpression.h>
#include <slang/ast/expressions/ConversionExpression.h>
#include <slang/ast/expressions/MiscExpressions.h>
#include <slang/ast/expressions/OperatorExpressions.h>
#include <slang/ast/expressions/SelectExpressions.h>
#include <slang/ast/statements/MiscStatements.h>
#include <slang/ast/symbols/BlockSymbols.h>
#include <slang/ast/symbols/CompilationUnitSymbols.h>
#include <slang/ast/symbols/InstanceSymbols.h>
#include <slang/ast/symbols/MemberSymbols.h>
#include <slang/ast/symbols/ParameterSymbols.h>
#include <slang/ast/symbols/PortSymbols.h>
#include <slang/ast/symbols/SubroutineSymbols.h>
#include <slang/ast/symbols/VariableSymbols.h>
#include <slang/ast/types/AllTypes.h>
#include <slang/syntax/AllSyntax.h>
#include <slang/text/SourceManager.h>

namespace slang_mcp::adapters {
namespace ast = slang::ast;
[[nodiscard]] std::string lower(std::string_view text);
[[nodiscard]] Text optional_text(std::string text);
[[nodiscard]] Text parent_path(const std::string& path);
[[nodiscard]] SourceLocation location(slang::SourceLocation source,
                                      const slang::SourceManager& manager);
[[nodiscard]] std::string qualified(const ast::Symbol& symbol);
[[nodiscard]] std::string kind(const ast::Symbol& symbol);
[[nodiscard]] SymbolReference reference(const ast::Symbol& symbol,
                                        const slang::SourceManager& manager);
[[nodiscard]] Width packed_width(const ast::Type& type);
[[nodiscard]] const ast::Type* symbol_type(const ast::Symbol& symbol);
[[nodiscard]] Text expression_text(const ast::Expression* original);
[[nodiscard]] Parameter parameter(const ast::ParameterSymbolBase& symbol);
[[nodiscard]] Port port(const ast::Symbol& symbol, const slang::SourceManager& manager);
[[nodiscard]] std::vector<const ast::ValueSymbol*>
expression_symbols(const ast::Expression& expression);
[[nodiscard]] Connection connection(const ast::PortConnection& value,
                                    const slang::SourceManager& manager);
[[nodiscard]] std::string direction_kind(ast::ArgumentDirection direction);
void index_accesses(const ast::InstanceSymbol& instance, const slang::SourceManager& manager,
                    AccessIndex& index);
} // namespace slang_mcp::adapters
