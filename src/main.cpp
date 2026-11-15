#include "server.hpp"

#include <exception>
#include <iostream>
#include <optional>
#include <string_view>

namespace {
bool option_selected(int argc, char** argv, std::string_view option) {
    return argc == 2 && std::string_view(argv[1]) == option;
}

std::optional<slang_mcp::ToolProfile> tool_profile(int argc, char** argv) {
    if (argc == 1) {
        return slang_mcp::ToolProfile::Core;
    }
    if (argc != 3 || std::string_view(argv[1]) != "--tool-profile") {
        return std::nullopt;
    }
    if (std::string_view(argv[2]) == "core") {
        return slang_mcp::ToolProfile::Core;
    }
    if (std::string_view(argv[2]) == "full") {
        return slang_mcp::ToolProfile::Full;
    }
    return std::nullopt;
}
} // namespace

int main(int argc, char** argv) {
    if (option_selected(argc, argv, "--version")) {
        std::cout << "slang-mcp " SLANG_MCP_VERSION "\n";
        return 0;
    }
    constexpr std::string_view usage =
        "Usage: slang-mcp [--tool-profile core|full] [--version | --help]\n"
        "  core: focused semantic tools (default); full: all compatibility tools.\n";
    if (option_selected(argc, argv, "--help")) {
        std::cout << usage;
        return 0;
    }
    const auto profile = tool_profile(argc, argv);
    if (!profile) {
        std::cerr << usage;
        return 2;
    }
    try {
        return slang_mcp::run_server(*profile);
    } catch (const std::exception& error) {
        std::cerr << "slang-mcp: " << error.what() << '\n';
        return 1;
    }
}
