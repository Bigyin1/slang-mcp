"""The active research bridge starts the server without removed profile options."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from mcp import StdioServerParameters

from benchmarks.research_agents import bridge


def test_bridge_uses_default_server_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve = AsyncMock()
    monkeypatch.setattr(bridge, "serve", serve)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bridge",
            "--binary",
            str(tmp_path / "slang-mcp"),
            "--log",
            str(tmp_path / "calls.jsonl"),
            "--allow",
            "project_load",
        ],
    )
    bridge.main()
    serve.assert_awaited_once_with(
        StdioServerParameters(command=str(tmp_path / "slang-mcp")),
        tmp_path / "calls.jsonl",
        frozenset({"project_load"}),
    )
