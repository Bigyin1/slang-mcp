#pragma once

#include "query.hpp"

#include <charconv>
#include <functional>

namespace slang_mcp {
class Pagination {
  public:
    Pagination(const Json& args, const std::string& tool, std::uint64_t revision)
        : prefix_(cursor_prefix(args, tool, revision)), start_(cursor_offset(args)),
          limit_(static_cast<std::size_t>(limit_for(args))) {}

    template <class Range, class Encode>
    Json render(const Range& records, const std::string& key, Encode encode,
                Json metadata = Json::object()) const {
        if (start_ > records.size()) {
            throw std::invalid_argument("cursor is outside the result set");
        }
        auto items = Json::array();
        auto bytes = wire_size(metadata) + envelope_reserve;
        for (auto index = start_; index < std::min(records.size(), start_ + limit_); ++index) {
            auto item = Json(encode(records[index]));
            bytes += wire_size(item) + 2;
            if (bytes > max_wire_bytes) {
                break;
            }
            items.push_back(std::move(item));
        }
        return finish(std::move(items), records.size(), key, std::move(metadata));
    }

  private:
    static constexpr std::size_t max_wire_bytes = 1'048'576;
    // Room for the JSON-RPC and MCP wrappers, page metadata and cursor.
    static constexpr std::size_t envelope_reserve = 4096;
    std::string prefix_;
    std::size_t start_, limit_;

    static std::string cursor_prefix(Json args, const std::string& tool, std::uint64_t revision) {
        if (args.is_null()) {
            args = Json::object();
        }
        args.erase("cursor");
        args.erase("limit");
        return tool + ":" + std::to_string(revision) + ":" +
               std::to_string(std::hash<std::string>{}(args.dump())) + ":";
    }

    [[nodiscard]] std::size_t cursor_offset(const Json& args) const {
        const auto cursor = text_option(args, "cursor");
        if (!cursor) {
            return 0;
        }
        if (!cursor->starts_with(prefix_)) {
            throw std::invalid_argument("cursor belongs to a different query or compilation");
        }
        const auto digits = std::string_view(*cursor).substr(prefix_.size());
        std::size_t offset = 0;
        const auto parsed = std::from_chars(digits.data(), digits.data() + digits.size(), offset);
        if (parsed.ec != std::errc{} || parsed.ptr != digits.data() + digits.size()) {
            throw std::invalid_argument("invalid pagination cursor");
        }
        return offset;
    }

    static std::size_t wire_size(const Json& value) {
        const auto payload = value.dump();
        return payload.size() + Json(payload).dump().size();
    }

    [[nodiscard]] Json finish(Json items, std::size_t total, const std::string& key,
                              Json result) const {
        const auto next = start_ + items.size();
        if (items.empty() && next < total) {
            throw std::invalid_argument("one result exceeds the reply size limit");
        }
        result["returned_count"] = items.size();
        result["total_count"] = total;
        result["truncated"] = next < total;
        result["next_cursor"] = next < total ? Json(prefix_ + std::to_string(next)) : Json(nullptr);
        result[key] = std::move(items);
        return result;
    }
};
} // namespace slang_mcp
