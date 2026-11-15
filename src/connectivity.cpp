#include "query.hpp"
#include "semantic_service.hpp"

#include <deque>
#include <tuple>

namespace slang_mcp {
namespace {
auto edge_key(const ConnectivityHop& edge) {
    return std::tuple(edge.source, edge.target, edge.kind, edge.operation, edge.formal_port,
                      edge.location.filename, edge.location.line, edge.location.column);
}

std::vector<ConnectivityHop> outgoing(const AccessIndex& index, const std::string& current,
                                      const std::string& direction) {
    std::vector<ConnectivityHop> result;
    for (const auto& item : index.edges) {
        if (direction != "drivers" && item.source == current) {
            result.push_back(item);
        }
        if (direction != "loads" && item.target == current) {
            auto reversed = item;
            std::swap(reversed.source, reversed.target);
            result.push_back(std::move(reversed));
        }
    }
    std::ranges::sort(result, [](const auto& left, const auto& right) {
        return edge_key(left) < edge_key(right);
    });
    const auto unique = std::ranges::unique(result, [](const auto& left, const auto& right) {
        return edge_key(left) == edge_key(right);
    });
    result.erase(unique.begin(), unique.end());
    return result;
}

struct PendingPath {
    std::string current;
    std::vector<ConnectivityHop> hops;
    std::set<std::string> visited;
};

struct Traversal {
    std::string start;
    std::deque<PendingPath> pending;
    std::vector<ConnectivityPath> paths;
    std::size_t considered = 0;
    std::size_t limit;

    void append(const PendingPath& current, const std::vector<ConnectivityHop>& edges) {
        for (const auto& edge : edges) {
            if (paths.size() >= limit || considered >= limit) {
                break;
            }
            ++considered;
            auto next = current;
            next.current = edge.target;
            next.hops.push_back(edge);
            if (!next.visited.insert(edge.target).second) {
                paths.push_back({start, edge.target, std::move(next.hops), "cycle"});
            } else {
                pending.push_back(std::move(next));
            }
        }
    }

    void run(const AccessIndex& index, const std::string& direction, int depth) {
        while (!pending.empty() && paths.size() < limit && considered < limit) {
            auto current = std::move(pending.front());
            pending.pop_front();
            const auto edges = outgoing(index, current.current, direction);
            if (current.hops.size() >= static_cast<std::size_t>(depth)) {
                paths.push_back({start, current.current, std::move(current.hops), "max_depth"});
            } else if (edges.empty()) {
                paths.push_back({start, current.current, std::move(current.hops), "no_edges"});
            } else {
                append(current, edges);
            }
        }
    }
};
} // namespace

Json SemanticService::trace(const Json& args) {
    const auto direction = option(args, "direction", std::string("both"));
    if (!std::set<std::string>{"both", "loads", "drivers"}.contains(direction)) {
        throw std::invalid_argument("unknown trace direction: " + direction);
    }
    const auto depth = option(args, "max_depth", 5);
    if (depth < 0 || depth > 50) {
        throw std::invalid_argument("max_depth must be between 0 and 50");
    }
    const auto signal = manager_.design().signal(args.at("signal")).symbol;
    Traversal traversal{signal.qualified_name,
                        {{signal.qualified_name, {}, {signal.qualified_name}}},
                        {},
                        0,
                        static_cast<std::size_t>(limit_for(args))};
    traversal.run(manager_.design().accesses(), direction, depth);
    const bool truncated = !traversal.pending.empty() || traversal.considered >= traversal.limit;
    return {{"query", args.at("signal")},
            {"direction", direction},
            {"resolved_start", signal},
            {"paths", Page<ConnectivityPath>{traversal.paths, traversal.paths.size(), truncated}},
            {"edges_considered", traversal.considered},
            {"max_depth", depth},
            {"truncated", truncated}};
}
} // namespace slang_mcp
