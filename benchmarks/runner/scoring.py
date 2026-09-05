"""Separate infrastructure and scoring failures from semantic wrong answers."""

from __future__ import annotations

from pathlib import Path

from benchmarks.adapters.audit import audit_mode
from benchmarks.models import Case
from benchmarks.scorers.exact import score


def score_record(case: Case, record: dict[str, object], trace: Path) -> None:
    record["mode_audit"] = audit_mode(trace, str(record["mode"]))
    if record["execution_status"] != "SUCCESS":
        return
    if not audit_mode(trace, str(record["mode"]))["valid"]:
        record.update(execution_status="MCP_FAILURE", correct=None)
        return
    try:
        record["correct"] = score(case, str(record["actual"]))
    except (KeyError, TypeError, ValueError) as error:
        record.update(execution_status="SCORER_FAILURE", correct=None, error=str(error))
    else:
        record["execution_status"] = "SUCCESS" if record["correct"] else "WRONG_ANSWER"
