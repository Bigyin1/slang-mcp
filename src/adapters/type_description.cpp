#include "adapters/internal.hpp"

namespace slang_mcp::adapters {
namespace {
TypeDimension fixed_dimension(const ast::Type& type) {
    const auto range = type.getFixedRange();
    return {type.isPackedArray() ? "packed" : "unpacked",
            range.toString(),
            std::nullopt,
            range.left,
            range.right,
            range.width(),
            std::nullopt,
            type.isPackedArray() ? std::optional(type.isSigned()) : std::nullopt};
}

Width queue_capacity(const ast::QueueType& queue) {
    return queue.maxBound ? Width(std::uint64_t(queue.maxBound) + 1) : std::nullopt;
}

TypeDimension dimension(const ast::Type& type) {
    if (type.hasFixedRange()) {
        return fixed_dimension(type);
    }
    TypeDimension result;
    result.kind = "dynamic";
    if (auto* queue = type.as_if<ast::QueueType>()) {
        result.kind = "queue";
        result.max_size = queue_capacity(*queue);
    } else if (auto* array = type.as_if<ast::AssociativeArrayType>()) {
        result.kind = "associative";
        result.index_type = array->indexType ? array->indexType->toString() : "*";
    } else if (type.as_if<ast::DPIOpenArrayType>()) {
        result.kind = "open";
    }
    return result;
}

std::string type_kind(const ast::Type& type) {
    if (type.getArrayElementType()) {
        return "array";
    }
    if (type.isStruct()) {
        return type.isIntegral() ? "packed_struct" : "unpacked_struct";
    }
    if (type.isUnion()) {
        return type.isIntegral() ? "packed_union" : "unpacked_union";
    }
    return lower(ast::toString(type.kind));
}

bool tagged(const ast::Type& type) {
    if (auto* value = type.as_if<ast::PackedUnionType>()) {
        return value->isTagged;
    }
    if (auto* value = type.as_if<ast::UnpackedUnionType>()) {
        return value->isTagged;
    }
    return false;
}

const ast::Scope* field_scope(const ast::Type& type) {
    if (auto* value = type.as_if<ast::PackedStructType>()) {
        return value;
    }
    if (auto* value = type.as_if<ast::UnpackedStructType>()) {
        return value;
    }
    if (auto* value = type.as_if<ast::PackedUnionType>()) {
        return value;
    }
    return type.as_if<ast::UnpackedUnionType>();
}

TypeDescription identity(const ast::Type& type) {
    TypeDescription result;
    result.type = type.toString();
    result.kind = type_kind(type.getCanonicalType());
    result.width = packed_width(type);
    const auto bits = type.getBitstreamWidth();
    result.total_bits = bits ? Width(bits) : std::nullopt;
    result.is_signed = type.isSigned();
    result.tagged = tagged(type.getCanonicalType());
    return result;
}

struct TypeBuilder {
    std::size_t remaining = 128;

    TypeDescription describe(const ast::Type& type, int depth) {
        --remaining;
        auto result = identity(type);
        const auto& canonical = type.getCanonicalType();
        if (canonical.getArrayElementType()) {
            array(result, canonical, depth);
        } else if (const auto* scope = field_scope(canonical)) {
            fields(result, *scope, depth);
        }
        return result;
    }

    void array(TypeDescription& result, const ast::Type& type, int depth) {
        const auto* current = &type;
        while (current->getArrayElementType() && result.dimensions.size() < 16) {
            result.dimensions.push_back(dimension(*current));
            current = &current->getArrayElementType()->getCanonicalType();
        }
        if (depth == 0 || remaining == 0 || current->getArrayElementType()) {
            result.truncated = true;
            return;
        }
        result.element_type = std::make_shared<TypeDescription>(describe(*current, depth - 1));
        result.truncated = result.element_type->truncated;
    }

    void fields(TypeDescription& result, const ast::Scope& scope, int depth) {
        for (const auto& member : scope.members()) {
            if (const auto* field = member.as_if<ast::FieldSymbol>()) {
                ++result.field_count;
                append(result, *field, depth);
            }
        }
    }

    void append(TypeDescription& result, const ast::FieldSymbol& field, int depth) {
        if (depth == 0 || remaining == 0) {
            result.truncated = true;
            return;
        }
        auto nested = std::make_shared<TypeDescription>(describe(field.getType(), depth - 1));
        result.truncated = result.truncated || nested->truncated;
        result.fields.push_back(
            {std::string(field.name),
             result.kind.starts_with("packed_") ? Width(field.bitOffset) : std::nullopt,
             std::move(nested)});
    }
};
} // namespace

TypeDescription describe_type(const ast::Type& type, int depth) {
    if (depth < 0 || depth > 8) {
        throw std::invalid_argument("type_depth must be between 0 and 8");
    }
    return TypeBuilder{}.describe(type, depth);
}
} // namespace slang_mcp::adapters
