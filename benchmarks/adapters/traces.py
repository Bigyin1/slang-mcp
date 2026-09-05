"""Normalize documented Copilot session events without exposing reasoning text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast


@dataclass
class Trace:
    answer: str = ""
    calls: list[dict[str, object]] = field(default_factory=list)
    models: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    usage: dict[str, int | None] = field(default_factory=dict)
    complete: bool = False


def object_dict(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def parse_trace(path: Path) -> Trace:
    trace = Trace()
    seen: set[str] = set()
    for line in path.read_text().splitlines():
        try:
            event = object_dict(json.loads(line))
        except ValueError:
            trace.errors.append("Malformed JSONL event")
            continue
        if not _duplicate(event, seen):
            _event(trace, event)
    return trace


def _event(trace: Trace, event: dict[str, object]) -> None:
    kind = event.get("type")
    data = object_dict(event.get("data"))
    if kind == "assistant.message" and not data.get("toolRequests"):
        trace.answer = str(data.get("content", ""))
    elif kind == "tool.execution_start":
        trace.calls.append({**data, "category": tool_category(data)})
    elif kind in {"session.start", "session.model_change", "assistant.usage"}:
        _model(trace, data)
    elif kind == "session.error":
        trace.errors.append(str(data.get("message", "Unknown session error")))
    elif kind in {"session.shutdown", "result"}:
        trace.complete = data.get("shutdownType") == "routine" or event.get("exitCode") == 0
        if data.get("modelMetrics"):
            trace.usage = extract_metrics(object_dict(data.get("modelMetrics")))


def _model(trace: Trace, data: dict[str, object]) -> None:
    for name in ("selectedModel", "newModel", "model"):
        if (model := data.get(name)) and model != "auto":
            trace.models.add(str(model))


def tool_category(data: dict[str, object]) -> str:
    name = str(data.get("toolName", ""))
    server = data.get("mcpServerName")
    if server == "slang_benchmark" or name.startswith(("slang_benchmark-", "slang_benchmark_")):
        return "slang_mcp"
    if server:
        return "other_mcp"
    return _builtin_category(name)


def extract_metrics(metrics: dict[str, object]) -> dict[str, int | None]:
    fields = {
        "input_tokens": "inputTokens",
        "output_tokens": "outputTokens",
        "cached_input_tokens": "cacheReadTokens",
    }
    usage = [object_dict(object_dict(value).get("usage")) for value in metrics.values()]
    result = {key: _sum_known(usage, name) for key, name in fields.items()}
    result["total_tokens"] = _total(result["input_tokens"], result["output_tokens"])
    return result


def _sum_known(values: list[dict[str, object]], key: str) -> int | None:
    items = [value.get(key) for value in values]
    if not items or any(not isinstance(item, int) or isinstance(item, bool) for item in items):
        return None
    return sum(cast("list[int]", items))


def load_usage(path: Path) -> dict[str, int | None]:
    if not path.exists():
        return extract_metrics({})
    data = object_dict(json.loads(path.read_text()))
    return extract_metrics(object_dict(data.get("modelMetrics")))


def _duplicate(event: dict[str, object], seen: set[str]) -> bool:
    identity = str(event.get("id", ""))
    if identity and identity in seen:
        return True
    seen.add(identity)
    return False


def _builtin_category(name: str) -> str:
    if name in {"view", "read_file", "grep", "glob", "search", "rg"}:
        return "filesystem"
    if name in {"bash", "powershell", "shell", "read_bash", "write_bash", "stop_bash", "list_bash"}:
        return "shell"
    return "internal"


def _total(inputs: int | None, outputs: int | None) -> int | None:
    return inputs + outputs if inputs is not None and outputs is not None else None


def usage_models(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = object_dict(json.loads(path.read_text()))
    return set(object_dict(data.get("modelMetrics")))
