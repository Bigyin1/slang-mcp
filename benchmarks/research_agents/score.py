"""Score the exploratory native suites without invoking workload models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parent


def objects(path: Path) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", json.loads(path.read_text()))


def outcome(answer: dict[str, object], oracle: dict[str, object]) -> str:
    if not oracle["answerable"]:
        return "correct_abstention" if answer["status"] == "abstained" else "unsupported_answer"
    if answer["status"] == "abstained":
        return "unnecessary_abstention"
    expected = json.dumps(oracle["answer"], sort_keys=True)
    actual = json.dumps(answer["answer"], sort_keys=True)
    return "correct" if actual == expected else "wrong"


def score(arm: str, oracles: list[dict[str, object]]) -> dict[str, object]:
    answers = {item["id"]: item for item in objects(ROOT / f"{arm}.answers.json")}
    results = {str(item["id"]): outcome(answers[item["id"]], item) for item in oracles}
    return {"arm": arm, "outcomes": results, "telemetry": telemetry(arm)}


def telemetry(arm: str) -> dict[str, object]:
    if arm == "text":
        return {"mcp_calls": 0, "tokens": None, "agent_seconds": None}
    records = [json.loads(line) for line in (ROOT / f"{arm}.calls.jsonl").read_text().splitlines()]
    calls = [item for item in records if item["request"]["method"] == "tools/call"]
    return {
        "mcp_calls": len(calls),
        "mcp_seconds": sum(item["seconds"] for item in calls),
        "response_json_bytes": sum(len(json.dumps(item["response"]).encode()) for item in calls),
        "tokens": None,
        "agent_seconds": None,
    }


def main() -> None:
    oracles = json.loads((ROOT / "real_oracles.controller.json").read_text())["oracles"]
    result = {
        "model_requested": "gpt-6.1-terra",
        "effort_requested": "max",
        "provider_observed_model": None,
        "identity_evidence": "native collaboration spawn configuration",
        "design": "one fresh worker per arm; six tasks share context; exploratory only",
        "arms": [score(arm, oracles) for arm in ("text", "mcp", "core", "skill")],
    }
    (ROOT / "pilot_results.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
