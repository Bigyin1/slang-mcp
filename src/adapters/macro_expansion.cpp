#include "adapters/internal.hpp"

#include <slang/diagnostics/DiagnosticEngine.h>
#include <slang/syntax/SyntaxTree.h>
#include <slang/syntax/SyntaxVisitor.h>

namespace slang_mcp::adapters {
namespace {
std::string_view source_text(const slang::SourceManager& manager, slang::BufferID buffer) {
    auto text = manager.getSourceText(buffer);
    if (text.ends_with('\0')) {
        text.remove_suffix(1);
    }
    return text;
}

std::vector<std::size_t> line_starts(std::string_view text) {
    std::vector<std::size_t> result{0};
    for (std::size_t index = 0; index < text.size(); ++index) {
        if (text[index] == '\n' ||
            (text[index] == '\r' && (index + 1 == text.size() || text[index + 1] != '\n'))) {
            result.push_back(index + 1);
        }
    }
    return result;
}

std::size_t query_offset(std::string_view text, const MacroQuery& query) {
    const auto starts = line_starts(text);
    const auto row = static_cast<std::size_t>(query.line - 1);
    if (row >= starts.size()) {
        throw std::invalid_argument("line is outside the loaded file");
    }
    const auto start = starts[row];
    const auto length = std::min(text.find_first_of("\r\n", start), text.size()) - start;
    if (static_cast<std::size_t>(query.column) > length) {
        throw std::invalid_argument("column is outside the loaded line");
    }
    return start + static_cast<std::size_t>(query.column - 1);
}

std::filesystem::path query_path(const MacroQuery& query) {
    if (!std::filesystem::path(query.file).is_absolute()) {
        throw std::invalid_argument("file must be an absolute path");
    }
    std::error_code error;
    auto path = std::filesystem::weakly_canonical(query.file, error);
    if (error) {
        throw std::invalid_argument("cannot resolve file path: " + query.file);
    }
    return path;
}

SourceLocation physical_location(const slang::SourceManager& manager, slang::SourceLocation loc) {
    loc = manager.getFullyOriginalLoc(loc);
    if (!loc) {
        return {};
    }
    const auto starts = line_starts(source_text(manager, loc.buffer()));
    const auto row =
        static_cast<std::size_t>(std::ranges::upper_bound(starts, loc.offset()) - starts.begin());
    const auto& path = manager.getFullPath(loc.buffer());
    return {path.empty() ? optional_text(std::string(manager.getRawFileName(loc.buffer())))
                         : Text(path.string()),
            row, loc.offset() - starts[row - 1] + 1};
}

struct MacroMatch {
    slang::syntax::SyntaxTree* tree;
    const slang::syntax::SyntaxNode* usage;
    const slang::syntax::DefineDirectiveSyntax* definition;
};

void validate_expansion(slang::syntax::SyntaxTree& tree, const slang::SourceManager& manager,
                        slang::SourceRange range) {
    slang::DiagnosticEngine engine(manager);
    for (const auto& diagnostic : tree.diagnostics()) {
        const auto subsystem = diagnostic.code.getSubsystem();
        if (subsystem != slang::DiagSubsystem::Preprocessor &&
            subsystem != slang::DiagSubsystem::Lexer) {
            continue;
        }
        if (engine.getSeverity(diagnostic.code, diagnostic.location) >=
                slang::DiagnosticSeverity::Error &&
            range.contains(manager.getFullyExpandedLoc(diagnostic.location))) {
            throw std::invalid_argument(
                "macro invocation has preprocessing errors; inspect get_diagnostics");
        }
    }
}

struct MacroSearch {
    const slang::SourceManager& manager;
    const MacroQuery& query;
    std::filesystem::path path;
    std::map<slang::BufferID, std::size_t> offsets;
    std::optional<MacroMatch> result;

    std::size_t offset(slang::BufferID buffer) {
        const auto [item, inserted] = offsets.try_emplace(buffer, 0);
        if (inserted) {
            item->second = query_offset(source_text(manager, buffer), query);
        }
        return item->second;
    }

    bool matches(const slang::syntax::SyntaxNode& usage) {
        const auto token = usage.getFirstToken();
        if (manager.isMacroLoc(token.location()) ||
            manager.getFullPath(token.location().buffer()) != path) {
            return false;
        }
        return token.range().contains(
            slang::SourceLocation(token.location().buffer(), offset(token.location().buffer())));
    }

    void consider(slang::syntax::SyntaxTree& tree,
                  const slang::parsing::MacroRefMetadata& reference) {
        if (reference.syntax->kind != slang::syntax::SyntaxKind::MacroUsage ||
            !matches(*reference.syntax)) {
            return;
        }
        if (result) {
            throw std::invalid_argument("macro invocation has multiple preprocessing contexts; "
                                        "query an unambiguous source invocation");
        }
        validate_expansion(tree, manager, reference.syntax->sourceRange());
        result = MacroMatch{&tree, reference.syntax, reference.definition};
    }
};

struct ExpansionText {
    std::size_t maximum;
    std::string text;
    std::size_t total = 0;
    bool capped = false;

    void append(std::string_view value) {
        total += value.size();
        if (capped) {
            return;
        }
        auto count = std::min(value.size(), maximum - text.size());
        if (count < value.size()) {
            while (count > 0 && (static_cast<unsigned char>(value[count]) & 0xc0U) == 0x80U) {
                --count;
            }
            capped = true;
        }
        text.append(value.substr(0, count));
    }
};

struct ExpansionVisitor : slang::syntax::SyntaxVisitor<ExpansionVisitor> {
    const slang::SourceManager& manager;
    slang::SourceRange range;
    ExpansionText text;

    ExpansionVisitor(const slang::SourceManager& source, slang::SourceRange selected,
                     std::size_t maximum)
        : manager(source), range(selected), text{maximum, {}} {}

    void directive(const slang::syntax::SyntaxNode& syntax) {
        if (syntax.kind == slang::syntax::SyntaxKind::MacroUsage) {
            return;
        }
        const auto location = syntax.getFirstToken().location();
        if (manager.isMacroLoc(location) && range.contains(manager.getFullyExpandedLoc(location))) {
            throw std::invalid_argument(
                "macro-generated preprocessing directives are not supported");
        }
        if (syntax.kind != slang::syntax::SyntaxKind::DefineDirective) {
            syntax.visit(*this);
        }
    }

    void skipped(const slang::parsing::Trivia& trivia) {
        if (trivia.kind == slang::parsing::TriviaKind::Directive) {
            directive(*trivia.syntax());
        }
        if (trivia.kind == slang::parsing::TriviaKind::SkippedTokens) {
            for (const auto token : trivia.getSkippedTokens()) {
                visitToken(token);
            }
        }
        if (trivia.kind == slang::parsing::TriviaKind::SkippedSyntax) {
            trivia.syntax()->visit(*this);
        }
    }

    // Slang's CRTP visitor intentionally dispatches to this hook.
    // NOLINTNEXTLINE(bugprone-derived-method-shadowing-base-method)
    void visitToken(slang::parsing::Token token) {
        for (const auto& trivia : token.trivia()) {
            skipped(trivia);
        }
        if (token.isMissing() || !manager.isMacroLoc(token.location())) {
            return;
        }
        if (!range.contains(manager.getFullyExpandedLoc(token.location()))) {
            return;
        }
        for (const auto& trivia : token.trivia()) {
            text.append(trivia.getRawText());
        }
        text.append(token.rawText());
    }
};

void validate(const MacroQuery& query) {
    if (query.line < 1 || query.column < 1) {
        throw std::invalid_argument("line and column must be positive 1-based coordinates");
    }
    if (query.max_bytes < 1 || query.max_bytes > 65536) {
        throw std::invalid_argument("max_bytes must be between 1 and 65536");
    }
}
} // namespace

MacroExpansion expand_macro(const ast::Compilation& compilation,
                            const slang::SourceManager& manager, const MacroQuery& query) {
    validate(query);
    MacroSearch search{manager, query, query_path(query), {}, std::nullopt};
    for (const auto& tree : compilation.getSyntaxTrees()) {
        for (const auto& reference : tree->getMacroRefs()) {
            search.consider(*tree, reference);
        }
    }
    if (!search.result) {
        throw std::invalid_argument("no recorded active user/configured macro invocation here; "
                                    "point at its backtick/name and inspect diagnostics");
    }
    const auto& match = *search.result;
    ExpansionVisitor visitor(manager, match.usage->sourceRange(),
                             static_cast<std::size_t>(query.max_bytes));
    match.tree->root().visit(visitor);
    return {std::string(match.definition->name.valueText()),
            physical_location(manager, match.usage->getFirstToken().location()),
            physical_location(manager, match.definition->name.location()),
            std::move(visitor.text.text),
            visitor.text.total,
            visitor.text.capped};
}
} // namespace slang_mcp::adapters
