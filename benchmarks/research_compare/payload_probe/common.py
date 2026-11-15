"""Canonical structured-payload comparisons for the bounded replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    case: str
    load_arguments: dict[str, object]
    baseline_arguments: dict[str, object]
    empty_filter: str
    retained_section: str


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def projection(answer: dict[str, object], section: str) -> dict[str, object]:
    items = answer["items"]
    if not isinstance(items, list):
        raise TypeError("Bulk result items are malformed")
    return {
        "total_count": answer["total_count"],
        "truncated": answer["truncated"],
        "items": [{"instance": item["instance"], section: item[section]} for item in items],
    }


def metrics(answer: dict[str, object]) -> dict[str, object]:
    return {
        "structured_bytes": len(encoded(answer)),
        "structured_sha256": hashlib.sha256(encoded(answer)).hexdigest(),
    }


def comparison(
    query: Query, baseline: dict[str, object], selected: dict[str, object]
) -> dict[str, object]:
    retained = projection(baseline, query.retained_section)
    if retained != projection(selected, query.retained_section):
        raise RuntimeError("Retained requested facts changed")
    return {
        "case": query.case,
        "empty_filter": query.empty_filter,
        "retained_section": query.retained_section,
        "retained_projection_equal": True,
        "baseline": metrics(baseline),
        "selected": metrics(selected),
        "retained_projection_sha256": hashlib.sha256(encoded(retained)).hexdigest(),
    }
