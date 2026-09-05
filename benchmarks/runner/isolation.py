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


def mcp_configuration(root: Path, enabled: bool) -> Path:
    servers = {}
    if enabled:
        servers["slang_benchmark"] = {
            "type": "local",
            "command": str(ROOT.parent / ".venv/bin/slang-mcp"),
            "args": ["--config", str(root / "workspace/projects.json")],
            "tools": ["*"],
        }
    path = root / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}, indent=2))
    return path
