#pragma once
#include <cstdint>
namespace slang_mcp {
enum class ToolProfile : std::uint8_t { Core, Full };
int run_server(ToolProfile profile = ToolProfile::Core);
} // namespace slang_mcp
