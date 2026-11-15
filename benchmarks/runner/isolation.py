"""Fresh workspaces with the system CLI's normal authentication and configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path

from benchmarks.dataset import ROOT


def run_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["TMPDIR"] = str(root / "tmp")
    return environment


def configure_workspace(root: Path) -> None:
    for name in ("tmp", "workspace"):
        (root / name).mkdir()


def server_binary() -> Path:
    return Path(
        os.environ.get("SLANG_MCP_BINARY", str(ROOT.parent / "build/cpp/slang-mcp"))
    ).resolve()


def mcp_configuration(root: Path, enabled: bool) -> Path:
    servers = {}
    if enabled:
        servers["slang_benchmark"] = {
            "type": "local",
            "command": str(server_binary()),
            "args": [],
            "tools": ["*"],
        }
    path = root / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}, indent=2))
    return path
