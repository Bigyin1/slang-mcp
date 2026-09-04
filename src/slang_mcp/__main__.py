"""Command-line entry point for the stdio MCP server."""

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from slang_mcp.providers import StaticProjectProvider
from slang_mcp.server import create_server

_CONFIG_ENV = "SLANG_MCP_CONFIG"


def main(argv: Sequence[str] | None = None) -> None:
    """Run the MCP server over stdio."""
    parser = argparse.ArgumentParser(description="Semantic SystemVerilog MCP server")
    parser.add_argument(
        "--config",
        type=Path,
        default=os.environ.get(_CONFIG_ENV),
        help=f"static project JSON file (or set {_CONFIG_ENV})",
    )
    args = parser.parse_args(argv)
    if args.config is None:
        parser.error(f"--config is required when {_CONFIG_ENV} is not set")
    provider = StaticProjectProvider.from_json(args.config.resolve())
    create_server(provider).run(transport="stdio")


if __name__ == "__main__":
    main()
