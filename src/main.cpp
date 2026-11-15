#include "server.hpp"

#include <exception>
#include <iostream>
#include <string_view>

namespace {
bool option_selected(int argc, char** argv, std::string_view option) {
    return argc == 2 && std::string_view(argv[1]) == option;
}

} // namespace

int main(int argc, char** argv) {
    if (option_selected(argc, argv, "--version")) {
        std::cout << "slang-mcp " SLANG_MCP_VERSION "\n";
        return 0;
    }
    constexpr std::string_view usage = "Usage: slang-mcp [--version | --help]\n";
    if (option_selected(argc, argv, "--help")) {
        std::cout << usage;
        return 0;
    }
    if (argc != 1) {
        std::cerr << usage;
        return 2;
    }
    try {
        return slang_mcp::run_server();
    } catch (const std::exception& error) {
        std::cerr << "slang-mcp: " << error.what() << '\n';
        return 1;
    }
}
