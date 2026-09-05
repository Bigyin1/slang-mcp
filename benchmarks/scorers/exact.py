"""Exact scoring; no LLM judge and no semantic repair."""

from __future__ import annotations

import json
import re

from benchmarks.models import Case


def normalize(answer: str, contract: str) -> object:
    answer = answer.strip()
    if contract in {"string", "path"}:
        return answer
    if contract == "integer":
        if not re.fullmatch(r"[+-]?\d+", answer):
            raise ValueError("Expected one integer")
        return int(answer)
    value: object = json.loads(answer)
    if not _shape_matches(value, contract):
        raise ValueError("Wrong JSON answer shape")
    return value


def score(case: Case, answer: str) -> bool:
    try:
        actual = normalize(answer, case.response_contract)
    except ValueError:
        return False
    return _typed_equal(actual, case.oracle)


def _typed_equal(left: object, right: object) -> bool:
    # JSON booleans must not compare equal to numbers; order of object keys is harmless.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _shape_matches(value: object, contract: str) -> bool:
    return (contract == "array" and isinstance(value, list)) or (
        contract == "object" and isinstance(value, dict)
    )
