"""Denominators, paired outcomes and report artifacts."""

from pathlib import Path

from benchmarks.reporting.aggregate import aggregate, paired
from benchmarks.reporting.output import generate_report
from benchmarks.reporting.statistics import cluster_interval, distribution
from benchmarks.runner.storage import write_json


def _record(mode: str, correct: bool | None) -> dict[str, object]:
    return {
        "case_id": "hier_generate",
        "category": "hierarchy",
        "project": "hierarchy",
        "mode": mode,
        "repetition": 1,
        "correct": correct,
        "execution_status": "TIMEOUT"
        if correct is None
        else "SUCCESS"
        if correct
        else "WRONG_ANSWER",
        "total_tokens": None,
        "calls": [],
    }


def test_accuracy_and_infrastructure_denominators() -> None:
    records = [_record("text-only", False), _record("mcp", True), _record("mcp+skill", None)]
    summary = aggregate(records, records, 1)
    assert summary["completed"] == 3
    outcomes = paired(records, records, "text-only", "mcp")
    assert outcomes["improves"] == 1
    assert outcomes["net_improvement"] == 1
    assert paired(records, records, "mcp", "mcp+skill")["incomplete"] == 1


def test_missing_data_is_not_zero() -> None:
    assert distribution([])["mean"] is None
    assert cluster_interval([_record("mcp", True)], 1) is None


def test_report_generation_without_fabricated_runs(tmp_path: Path) -> None:
    write_json(
        tmp_path / "experiment.json",
        {"fingerprint": "empty", "seed": 1, "planned": [_record("mcp", True)]},
    )
    summary = generate_report(tmp_path)
    assert summary["completed"] == 0
    assert summary["planned"] == 1
    report = (tmp_path / "reports/benchmark_report.md").read_text()
    assert "Недостаточно" in report
    assert (tmp_path / "reports/figures/token_usage.png").exists()
    assert (tmp_path / "normalized/summary.csv").exists()
