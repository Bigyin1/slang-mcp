#include "adapters/internal.hpp"

#include <slang/syntax/SyntaxTree.h>

namespace slang_mcp::adapters {
namespace {
struct IncludeContext {
    const slang::SourceManager& manager;
    const std::filesystem::path file;
    FileContext result;
    std::map<slang::BufferID, std::vector<std::size_t>> lines;

    SourceLocation directive_location(slang::SourceLocation site) {
        auto& starts = lines[site.buffer()];
        if (starts.empty()) {
            starts = line_starts(manager.getSourceText(site.buffer()));
        }
        return physical_file_location(manager, site, starts);
    }

    void add(const slang::parsing::IncludeMetadata& include) {
        const auto site = manager.getFullyExpandedLoc(include.syntax->directive.location());
        const auto& resolved = manager.getFullPath(include.buffer.id);
        result.is_included = result.is_included || resolved == file;
        if (resolved == file || manager.getFullPath(site.buffer()) == file) {
            result.includes.push_back({directive_location(site), std::string(include.path),
                                       optional_text(resolved.string())});
        }
    }

    void add(const slang::syntax::SyntaxTree& tree) {
        result.is_source =
            result.is_source || std::ranges::any_of(tree.getSourceBufferIds(), [&](auto buffer) {
                return manager.getFullPath(buffer) == file && !manager.getIncludedFrom(buffer);
            });
        for (const auto& include : tree.getIncludeDirectives()) {
            add(include);
        }
    }
};
} // namespace

FileContext file_context(const ast::Compilation& compilation, const slang::SourceManager& manager,
                         const std::string& file) {
    IncludeContext context{manager, file, {}, {}};
    for (const auto& tree : compilation.getSyntaxTrees()) {
        context.add(*tree);
    }
    return std::move(context.result);
}
} // namespace slang_mcp::adapters
