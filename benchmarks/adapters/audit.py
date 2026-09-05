"""Validate MCP mode exposure from observable CLI server-status events."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.adapters.traces import object_dict


def mcp_statuses(path: Path) -> dict[str, str]:
    statuses = {}
    for line in path.read_text().splitlines():
        try:
            event = object_dict(json.loads(line))
        except ValueError:
            continue
        if event.get("type") == "session.mcp_server_status_changed":
            data = object_dict(event.get("data"))
            statuses[str(data.get("serverName"))] = str(data.get("status"))
    return statuses


def audit_mode(path: Path, mode: str) -> dict[str, object]:
    statuses = mcp_statuses(path)
    foreign = sorted(set(statuses) - {"slang_benchmark"})
    valid = (
        not statuses
        if mode == "text-only"
        else (statuses.get("slang_benchmark") == "connected" and not foreign)
    )
    return {"valid": valid, "server_statuses": statuses, "foreign_servers": foreign}
