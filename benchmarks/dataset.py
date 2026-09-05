"""Load the frozen corpus and validate scoring contracts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

from benchmarks.models import CATEGORIES, Case

ROOT = Path(__file__).resolve().parent


def read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return cast("dict[str, object]", value)


def string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected nonempty string")
    return value


def load_cases(path: Path = ROOT / "cases/corpus.json") -> tuple[Case, ...]:
    document = read_object(path)
    values = document.get("cases")
    if document.get("version") != 1 or not isinstance(values, list):
        raise ValueError("Unsupported corpus schema")
    cases = tuple(_case(value) for value in values)
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case identifier")
    return cases


def _case(value: object) -> Case:
    if not isinstance(value, dict):
        raise TypeError("Expected case object")
    data = cast("dict[str, object]", value)
    case = Case(**_fields(data), oracle=data["oracle"], pilot=data.get("pilot") is True)
    if not re.fullmatch(r"[a-z][a-z0-9_]+", case.id) or case.category not in CATEGORIES:
        raise ValueError(f"Invalid identifier/category: {case.id}")
    _validate_contract(case)
    return case


def _fields(data: dict[str, object]) -> dict[str, str]:
    names = ("id", "category", "project", "question", "response_contract", "rationale")
    return {name: string(data[name]) for name in names}


def _validate_contract(case: Case) -> None:
    types = {"integer": int, "string": str, "path": str, "array": list, "object": dict}
    expected = types.get(case.response_contract)
    if expected is None or not isinstance(case.oracle, expected) or isinstance(case.oracle, bool):
        raise ValueError(f"Invalid oracle/contract: {case.id}")


def corpus_hash() -> str:
    digest = hashlib.sha256()
    for folder in ("cases", "fixtures", "skills"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(ROOT)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()
