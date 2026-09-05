"""Explicit metric denominators and paired comparisons with missing-run accounting."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import cast

from benchmarks.models import EVALUABLE, MODES
from benchmarks.reporting.statistics import Record, cluster_interval, distribution, numbers, ratio


def aggregate(records: list[Record], planned: list[Record], seed: int) -> Record:
    return {
        "modes": {
            mode: mode_summary(
                [r for r in records if r["mode"] == mode],
                sum(p["mode"] == mode for p in planned),
                seed,
            )
            for mode in MODES
        },
        "paired": {
            f"{a} vs {b}": paired(records, planned, a, b) for a, b in combinations(MODES, 2)
        },
        "categories": grouped(records, planned, "category", seed),
        "projects": grouped(records, planned, "project", seed),
        "planned": len(planned),
        "completed": len(records),
    }


def mode_summary(records: list[Record], planned: int, seed: int) -> Record:
    evaluable = [record for record in records if record["execution_status"] in EVALUABLE]
    correct = sum(record["correct"] is True for record in evaluable)
    return {
        "planned": planned,
        "completed": len(records),
        "evaluable": len(evaluable),
        "correct": correct,
        "task_accuracy": ratio(correct, len(evaluable)),
        "reliability": ratio(len(evaluable), planned),
        "overall_success": ratio(correct, planned),
        "infrastructure_failures": len(records) - len(evaluable),
        "statuses": dict(Counter(str(r["execution_status"]) for r in records)),
        "accuracy_by_repetition": _repetitions(evaluable),
        "cluster_95_ci": cluster_interval(evaluable, seed),
        "efficiency": efficiency(records, correct),
        "tool_frequency": _frequency(records),
    }


def _repetitions(records: list[Record]) -> Record:
    values = {
        str(rep): sum(r["correct"] is True for r in records if r["repetition"] == rep)
        / sum(r["repetition"] == rep for r in records)
        for rep in sorted({int(cast("int", r["repetition"])) for r in records})
    }
    return {"values": values, **distribution(list(values.values()))}


def efficiency(records: list[Record], correct: int) -> Record:
    fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "tool_call_count",
        "mcp_tool_call_count",
        "filesystem_tool_call_count",
        "shell_tool_call_count",
        "duration_seconds",
    )
    return {key: _efficiency_metric(numbers(records, key), correct, len(records)) for key in fields}


def _efficiency_metric(values: list[float], correct: int, count: int) -> Record:
    return {
        **distribution(values),
        "observed": len(values),
        "total": sum(values) if values else None,
        "per_correct": ratio(sum(values), correct) if len(values) == count and values else None,
    }


def _frequency(records: list[Record]) -> dict[str, int]:
    return dict(
        Counter(
            str(call.get("mcpToolName", call.get("toolName")))
            for record in records
            for call in cast("list[Record]", record.get("calls", []))
            if call.get("category") == "slang_mcp"
        )
    )


def grouped(records: list[Record], planned: list[Record], field: str, seed: int) -> Record:
    return {
        str(value): {
            mode: mode_summary(
                [r for r in records if r[field] == value and r["mode"] == mode],
                sum(p[field] == value and p["mode"] == mode for p in planned),
                seed,
            )
            for mode in MODES
        }
        for value in sorted({str(p[field]) for p in planned})
    }


def paired(records: list[Record], planned: list[Record], first: str, second: str) -> Record:
    return _paired_counts(_paired_details(records, planned, (first, second)))


def _paired_counts(details: list[Record]) -> Record:
    counts = Counter(str(item["outcome"]) for item in details)
    return {
        **dict.fromkeys(("both_correct", "improves", "regresses", "both_wrong", "incomplete"), 0),
        **counts,
        "details": details,
        "net_improvement": counts["improves"] - counts["regresses"],
    }


def _paired_details(
    records: list[Record], planned: list[Record], modes: tuple[str, str]
) -> list[Record]:
    lookup = {(r["case_id"], r["repetition"], r["mode"]): r for r in records}
    return [
        {
            "case_id": key[0],
            "repetition": key[1],
            "outcome": _outcome(lookup.get((*key, modes[0])), lookup.get((*key, modes[1]))),
        }
        for key in sorted({(str(p["case_id"]), cast("int", p["repetition"])) for p in planned})
    ]


def _outcome(left: Record | None, right: Record | None) -> str:
    if left is None or right is None:
        return "incomplete"
    if left["execution_status"] not in EVALUABLE or right["execution_status"] not in EVALUABLE:
        return "incomplete"
    return {
        (True, True): "both_correct",
        (False, True): "improves",
        (True, False): "regresses",
        (False, False): "both_wrong",
    }[(left["correct"] is True, right["correct"] is True)]
