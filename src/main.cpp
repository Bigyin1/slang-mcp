#include "server.hpp"

#include <exception>
#include <iostream>
#include <string_view>

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view(argv[1]) == "--version") {
        std::cout << "slang-mcp " SLANG_MCP_VERSION "\n";
        return 0;
    }
    if (argc != 1) {
        std::cerr << "Usage: slang-mcp [--version]\n";
        return 2;
    }
    try {
        return slang_mcp::run_server();
    } catch (const std::exception& error) {
        std::cerr << "slang-mcp: " << error.what() << '\n';
        return 1;
    }
}
