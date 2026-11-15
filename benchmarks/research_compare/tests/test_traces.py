"""Usage is measured from terminal events and reasoning is kept private."""

# ruff: noqa: S101, PLR2004 -- Match the repository's pytest assertion conventions.

import json
from pathlib import Path

import pytest

from benchmarks.research_compare.traces import parse_trace, write_public_trace


def test_missing_usage_stays_unknown(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text('{"type":"turn.completed","usage":{"input_tokens":17}}\n')
    usage = parse_trace(path).usage()
    assert usage["input_tokens"] == 17
    assert usage["output_tokens"] is None
    assert usage["reasoning_output_tokens"] is None
    assert usage["cache_write_input_tokens"] is None


def test_completed_turns_are_summed_without_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    events = [
        {"type": "turn.completed", "id": "one", "usage": {"input_tokens": 12}},
        {"type": "turn.completed", "id": "one", "usage": {"input_tokens": 12}},
        {"type": "turn.completed", "id": "two", "usage": {"input_tokens": 8}},
    ]
    path.write_text("\n".join(json.dumps(event) for event in events))
    trace = parse_trace(path)
    assert trace.usage()["input_tokens"] == 20
    assert trace.completed_turns == 2


@pytest.mark.parametrize("counter", [True, "12", None])
def test_noninteger_counter_is_unknown(tmp_path: Path, counter: object) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps({"type": "turn.completed", "usage": {"input_tokens": counter}}))
    assert parse_trace(path).usage()["input_tokens"] is None


def test_public_trace_omits_reasoning_and_preserves_answer(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    events = [
        {"type": "item.completed", "item": {"type": "reasoning", "text": "private content"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}},
    ]
    path.write_text("\n".join(json.dumps(event) for event in events))
    trace = parse_trace(path)
    write_public_trace(tmp_path / "public.jsonl", trace)
    assert "private content" not in (tmp_path / "public.jsonl").read_text()
    assert trace.answer == "answer"


def test_parse_failure_is_retained(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text("not JSON\n")
    trace = parse_trace(path)
    assert trace.errors == ["Malformed JSONL event"]
    assert all(value is None for value in trace.usage().values())
