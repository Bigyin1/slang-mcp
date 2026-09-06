"""Command-line entry point for the stdio MCP server."""

import argparse
from collections.abc import Sequence

from slang_mcp.server import create_server


def main(argv: Sequence[str] | None = None) -> None:
    """Run the MCP server over stdio."""
    parser = argparse.ArgumentParser(description="Semantic SystemVerilog MCP server")
    parser.parse_args(argv)
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
