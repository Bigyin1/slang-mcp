"""Summarize recorded catalog trials without inferring task correctness or tokens."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import cast

DIRECTORY = Path(__file__).resolve().parent


def json_bytes(value: object) -> int:
    return len(json.dumps(value, separators=(",", ":")).encode())


def summarize(path: Path) -> dict[str, object]:
    records = [json.loads(line) for line in path.read_text().splitlines()]
    catalogs = [item["response"] for item in records if item["request"]["method"] == "tools/list"]
    calls = [item for item in records if item["request"]["method"] == "tools/call"]
    return {
        "trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "catalog_counts": [len(item["tools"]) for item in catalogs],
        "catalog_json_bytes": [json_bytes(item) for item in catalogs],
        **summarize_calls(calls),
        "tokens": None,
        "total_agent_seconds": None,
    }


def summarize_calls(calls: list[dict[str, dict[str, object]]]) -> dict[str, object]:
    """Count attempted calls, including bridge rejections, separately from catalogs."""
    return {
        "call_count": len(calls),
        "tool_counts": dict(
            Counter(item["request"].get("name", "<missing_name>") for item in calls)
        ),
        "response_json_bytes": sum(json_bytes(item["response"]) for item in calls),
        "error_count": sum(
            bool(item["response"].get("isError") or item["response"].get("bridge_error"))
            for item in calls
        ),
        "loads": [
            item["request"]
            for item in calls
            if str(item["request"].get("name", "")).startswith("project_load")
        ],
    }


def main() -> None:
    profiles = cast(
        "dict[str, list[str] | None]", json.loads((DIRECTORY / "profiles.json").read_text())
    )
    results = {name: summarize(DIRECTORY / f"{name}.calls.jsonl") for name in profiles}
    (DIRECTORY / "catalog_results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
