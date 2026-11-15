"""Descriptive paired token and time totals without imputation or double counting."""

from __future__ import annotations

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.traces import TOKEN_FIELDS

METRICS = (*TOKEN_FIELDS, "raw_total_tokens", "input_minus_cached_tokens", "duration_seconds")
ARMS = ("text-only", "mcp+skill")


def _number(value: object) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _combine(first: object, second: object, sign: int = 1) -> int | float | None:
    left, right = _number(first), _number(second)
    if left is None or right is None:
        return None
    return left + sign * right


def run_metrics(result: dict[str, object]) -> dict[str, int | float | None]:
    usage = object_dict(result.get("usage"))
    return {
        **{name: _number(usage.get(name)) for name in TOKEN_FIELDS},
        "raw_total_tokens": _combine(usage.get("input_tokens"), usage.get("output_tokens")),
        "input_minus_cached_tokens": _combine(
            usage.get("input_tokens"), usage.get("cached_input_tokens"), -1
        ),
        "duration_seconds": _number(result.get("duration_seconds")),
    }


def paired_metrics(records: list[dict[str, object]]) -> list[dict[str, object]]:
    identities = sorted({(str(row["case_id"]), int(str(row["repetition"]))) for row in records})
    return [_pair(records, case, repetition) for case, repetition in identities]


def _pair(records: list[dict[str, object]], case: str, repetition: int) -> dict[str, object]:
    arms = {
        str(row["arm"]): object_dict(row["metrics"])
        for row in records
        if row["case_id"] == case and row["repetition"] == repetition
    }
    return {
        "case_id": case,
        "repetition": repetition,
        "difference_mcp_minus_text": _deltas(arms),
    }


def _deltas(arms: dict[str, dict[str, object]]) -> dict[str, int | float | None]:
    baseline, treatment = arms.get("text-only", {}), arms.get("mcp+skill", {})
    return {name: _combine(treatment.get(name), baseline.get(name), -1) for name in METRICS}


def group_summaries(
    records: list[dict[str, object]], groups: dict[str, list[str]]
) -> dict[str, object]:
    return {name: _group(records, cases) for name, cases in groups.items()}


def _group(records: list[dict[str, object]], cases: list[str]) -> dict[str, object]:
    selected = [row for row in records if row["case_id"] in cases]
    repetitions = sorted({int(str(row["repetition"])) for row in selected})
    return {
        "all_repetitions": _totals(selected),
        "by_repetition": {
            str(rep): _totals([row for row in selected if row["repetition"] == rep])
            for rep in repetitions
        },
    }


def _totals(records: list[dict[str, object]]) -> dict[str, object]:
    return {name: _metric_totals(records, name) for name in METRICS}


def _metric_totals(records: list[dict[str, object]], name: str) -> dict[str, object]:
    arms = {
        arm: _sum([object_dict(row["metrics"]).get(name) for row in records if row["arm"] == arm])
        for arm in ARMS
    }
    return {
        **arms,
        "difference_mcp_minus_text": _combine(
            arms["mcp+skill"]["sum"], arms["text-only"]["sum"], -1
        ),
    }


def _sum(values: list[object]) -> dict[str, int | float | None]:
    known = [_number(value) for value in values if _number(value) is not None]
    total = sum(value for value in known if value is not None)
    return {
        "sum": total if values and len(known) == len(values) else None,
        "known_count": len(known),
        "expected_count": len(values),
    }
