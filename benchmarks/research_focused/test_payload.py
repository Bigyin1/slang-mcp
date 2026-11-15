"""Check projection equivalence and canonical payload encoding."""

# Ruff: pytest assertions and literal digest lengths are intentional here.
# ruff: noqa: S101, PLR2004

import pytest
from mcp.types import CallToolResult

from benchmarks.research_focused.payload import encoded, projection_hash


def test_projection_preserves_identity_and_parameters() -> None:
    full = CallToolResult(
        content=[],
        structured_content={"instance": {"path": "top"}, "parameters": [], "children": []},
    )
    selected = CallToolResult(
        content=[], structured_content={"instance": {"path": "top"}, "parameters": []}
    )
    assert len(projection_hash(full, selected)) == 64
    assert encoded({"b": 2, "a": 1}) == encoded({"a": 1, "b": 2})


def test_projection_rejects_changed_identity() -> None:
    with pytest.raises(RuntimeError, match="differs"):
        projection_hash(
            CallToolResult(content=[], structured_content={"instance": "top", "parameters": []}),
            CallToolResult(content=[], structured_content={"instance": "other", "parameters": []}),
        )
