"""Check agreement among recorded public artifacts, without provider attestation."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.research_compare.traces import Trace, parse_trace


def content_audit(source: Path, result: dict[str, object]) -> dict[str, object]:
    """Use only the sanitized trace; missing counters remain unknown."""
    if not all((source / name).is_file() for name in ("answer.txt", "public_trace.jsonl")):
        return {"valid": False, "error": "Public answer or trace unavailable"}
    trace = parse_trace(source / "public_trace.jsonl")
    checks = _checks((source / "answer.txt").read_text(), result, trace)
    return {
        "valid": all(checks.values()),
        **checks,
        "scope": "Cross-artifact consistency only; no attestation of provider-reported truth",
    }


def _checks(answer: str, result: dict[str, object], trace: Trace) -> dict[str, bool]:
    return {
        "answer_matches_result": answer == result.get("answer"),
        "answer_matches_public_trace": answer == trace.answer,
        "usage_matches_public_trace": _same_json(result.get("usage"), trace.usage()),
        "usage_events_match_public_trace": _same_json(
            result.get("usage_events"), trace.usage_events
        ),
        "completed_turns_match_public_trace": _same_json(
            result.get("completed_turns"), trace.completed_turns
        ),
        "public_trace_parses": not trace.errors,
    }


def _same_json(first: object, second: object) -> bool:
    return json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
