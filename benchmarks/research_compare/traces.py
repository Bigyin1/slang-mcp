"""Parse public CLI events and actual usage without publishing reasoning text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from benchmarks.adapters.traces import object_dict

TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
PUBLIC_ITEMS = {"agent_message", "command_execution", "mcp_tool_call"}


@dataclass
class Trace:
    answer: str = ""
    completed_turns: int = 0
    usage_events: list[dict[str, object]] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def usage(self) -> dict[str, int | None]:
        """Sum completed-turn counters; an absent counter remains unknown."""
        return {name: _sum_counter(self.usage_events, name) for name in TOKEN_FIELDS}


def _sum_counter(events: list[dict[str, object]], name: str) -> int | None:
    values = [event.get(name) for event in events]
    if not values or any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        return None
    return sum(value for value in values if isinstance(value, int))


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


def _duplicate(event: dict[str, object], seen: set[str]) -> bool:
    identity = str(event.get("id", ""))
    if identity and identity in seen:
        return True
    seen.add(identity)
    return False


def _event(trace: Trace, event: dict[str, object]) -> None:
    kind = event.get("type")
    if kind == "turn.completed":
        trace.completed_turns += 1
        trace.usage_events.append(object_dict(event.get("usage")))
        trace.events.append({"type": kind, "usage": object_dict(event.get("usage"))})
    elif kind in {"turn.failed", "error"}:
        trace.errors.append(str(event.get("error", event.get("message", kind))))
    elif kind in {"item.started", "item.updated", "item.completed"}:
        _item(trace, str(kind), object_dict(event.get("item")))


def _item(trace: Trace, kind: str, item: dict[str, object]) -> None:
    if item.get("type") not in PUBLIC_ITEMS:
        return
    trace.events.append({"type": kind, "item": item})
    if kind == "item.completed" and item.get("type") == "agent_message":
        trace.answer = str(item.get("text", ""))


def write_public_trace(path: Path, trace: Trace) -> None:
    """Publish only assistant messages, tool activity, and reported counters."""
    path.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in trace.events))
