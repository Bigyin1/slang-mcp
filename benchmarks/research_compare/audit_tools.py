"""Count completed public tool events and preserve commands for human review."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.adapters.traces import object_dict


def tool_audit(path: Path | None, workspace: Path) -> dict[str, object]:
    if path is None or not path.exists():
        return {
            "commands": [],
            "mcp_calls": [],
            "project_loads": [],
            "completed_command_count": None,
            "completed_mcp_count": None,
            "failed_mcp_count": None,
        }
    items = _completed_items(path)
    commands = [_command(item) for item in items if item.get("type") == "command_execution"]
    calls = [_mcp(item) for item in items if item.get("type") == "mcp_tool_call"]
    return {
        "commands": commands,
        "mcp_calls": calls,
        "project_loads": [
            _load(item, workspace) for item in calls if item.get("tool") == "project_load"
        ],
        "completed_command_count": len(commands),
        "completed_mcp_count": len(calls),
        "failed_mcp_count": sum(bool(item["failed"]) for item in calls),
    }


def _completed_items(path: Path) -> list[dict[str, object]]:
    items: dict[str, dict[str, object]] = {}
    for line in path.read_text().splitlines():
        event = object_dict(json.loads(line))
        item = object_dict(event.get("item"))
        if item.get("type") == "reasoning":
            raise ValueError("Public trace contains a reasoning item; refusing export")
        if event.get("type") == "item.completed":
            items[str(item.get("id", f"anonymous_{len(items)}"))] = item
    return list(items.values())


def _command(item: dict[str, object]) -> dict[str, object]:
    return {key: item.get(key) for key in ("id", "command", "status", "exit_code")}


def _mcp(item: dict[str, object]) -> dict[str, object]:
    result = object_dict(item.get("result"))
    return {
        **{key: item.get(key) for key in ("id", "server", "tool", "arguments", "status", "error")},
        "failed": item.get("status") == "failed"
        or bool(item.get("error"))
        or bool(result.get("isError", result.get("is_error"))),
    }


def _load(item: dict[str, object], workspace: Path) -> dict[str, object]:
    sources = object_dict(item.get("arguments")).get("source_files")
    if not isinstance(sources, list):
        return {"id": item.get("id"), "source_files": None, "source_bytes": None}
    sizes = [_source_size(str(source), workspace) for source in sources]
    return {
        "id": item.get("id"),
        "source_files": sources,
        "source_count": len(sources),
        "source_bytes": _known_sum(sizes),
        "failed": item.get("failed"),
    }


def _source_size(source: str, workspace: Path) -> int | None:
    path = Path(source)
    if not path.is_absolute():
        path = workspace / path
    if not path.resolve().is_relative_to(workspace.resolve()) or not path.is_file():
        return None
    return path.stat().st_size


def _known_sum(values: list[int | None]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)
