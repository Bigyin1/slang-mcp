"""Check diagnostic assertions reject downgraded or misleading fragment errors."""

import pytest

from benchmarks.research_focused.validation import check_hints


@pytest.mark.parametrize(
    ("code", "hint", "severity"),
    [
        ("InvalidMemberAccess", "possible_missing_dependency", "error"),
        ("UnknownModule", "unclassified", "error"),
        ("UnknownModule", "possible_missing_dependency", "warning"),
    ],
)
def test_error_hint_checks_reject_bad_annotations(code: str, hint: str, severity: str) -> None:
    with pytest.raises(RuntimeError):
        check_hints({"diagnostics": [{"code": code, "scope_hint": hint, "severity": severity}]})
