"""Read-only system CLI checks; never alter credentials or user configuration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from benchmarks.adapters.copilot import system_copilot, verify_version
from benchmarks.adapters.traces import object_dict
from benchmarks.models import Settings


def preflight(settings: Settings, workspace: Path) -> dict[str, object]:
    version = verify_version(settings)
    result = subprocess.run(
        [system_copilot(), "mcp", "list", "--json"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    if object_dict(object_dict(json.loads(result.stdout)).get("mcpServers")):
        raise RuntimeError(
            "Benchmark requires no inherited MCP servers; disable them before running"
        )
    return {"version": version, "inherited_mcp_servers": [], "executable": system_copilot()}
