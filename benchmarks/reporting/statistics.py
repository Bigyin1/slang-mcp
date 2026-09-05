"""Descriptive statistics and case-clustered confidence intervals."""

from __future__ import annotations

import random
import statistics
from collections import defaultdict

from benchmarks.models import EVALUABLE

Record = dict[str, object]
MIN_PERCENTILE_SAMPLE = 10
MIN_CLUSTERS = 2


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def numbers(records: list[Record], key: str) -> list[float]:
    return [
        float(value) for record in records if isinstance(value := record.get(key), (int, float))
    ]


def distribution(values: list[float]) -> Record:
    if not values:
        return dict.fromkeys(("mean", "median", "stddev", "min", "max", "p50", "p90"))
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values),
        "max": max(values),
        "p50": statistics.median(values),
        "p90": percentile(values, 0.9) if len(values) >= MIN_PERCENTILE_SAMPLE else None,
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (
        index - lower
    )


def cluster_interval(records: list[Record], seed: int) -> list[float] | None:
    values = _clusters(records)
    if len(values) < MIN_CLUSTERS:
        return None
    rng = random.Random(seed)
    samples = [_bootstrap_sample(values, rng) for _ in range(2000)]
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def _bootstrap_sample(groups: list[list[float]], rng: random.Random) -> float:
    sample = [value for group in rng.choices(groups, k=len(groups)) for value in group]
    return statistics.mean(sample)


def _clusters(records: list[Record]) -> list[list[float]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for record in records:
        if record.get("execution_status") in EVALUABLE:
            groups[str(record["case_id"])].append(float(record["correct"] is True))
    return list(groups.values())
