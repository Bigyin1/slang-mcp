"""Check trace accounting against explicit successful and rejected exchanges."""

# Ruff: pytest assertions and explicit fixture counts are intentional.
# ruff: noqa: S101, PLR2004

import pytest

from benchmarks.research_focused.audit import catalog_check, counts, errors, fields_usage


@pytest.fixture
def calls() -> list[dict[str, object]]:
    return [
        {
            "request": {"method": "tools/list"},
            "response": {"tools": [{"name": "inspect_instance"}]},
        },
        {
            "request": {
                "method": "tools/call",
                "name": "inspect_instance",
                "arguments": {"fields": []},
            },
            "response": {"isError": False},
        },
        {
            "request": {"method": "tools/call", "name": "unknown"},
            "response": {"isError": True, "content": []},
        },
    ]


def test_call_counts(calls: list[dict[str, object]]) -> None:
    assert counts(calls)["successful_tool_calls"] == 1
    assert counts(calls)["tool_calls"] == 2


def test_rejection_index(calls: list[dict[str, object]]) -> None:
    assert errors(calls)[0]["call_index"] == 3


def test_empty_selection(calls: list[dict[str, object]]) -> None:
    assert fields_usage(calls)[0]["fields"] == []


def test_catalog_membership(calls: list[dict[str, object]]) -> None:
    assert catalog_check(calls)["calls_outside_catalog"] == ["unknown"]
