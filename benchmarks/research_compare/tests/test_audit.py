"""Public export, unknown counters, paired totals, and frozen-file verification."""

# ruff: noqa: S101, PLR2004 -- Match repository pytest assertions and literal expectations.

import json
from pathlib import Path

import pytest

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit import PUBLIC_ARTIFACTS, export
from benchmarks.research_compare.audit_integrity import digest, workspace_audit
from benchmarks.research_compare.audit_metrics import group_summaries, paired_metrics, run_metrics
from benchmarks.research_compare.audit_tools import tool_audit
from benchmarks.research_compare.tests.audit_fixture import make_request
from benchmarks.runner.storage import write_json


def test_workspace_detects_changed_missing_and_extra_files(tmp_path: Path) -> None:
    (tmp_path / "top.sv").write_text("module top; endmodule")
    expected: dict[str, object] = {"top.sv": digest(tmp_path / "top.sv"), "missing.sv": "hash"}
    (tmp_path / "top.sv").write_text("changed")
    (tmp_path / "extra").touch()
    result = workspace_audit(tmp_path, expected)
    assert result["valid"] is False
    assert result["changed"] == ["top.sv"]
    assert result["missing"] == ["missing.sv"]
    assert result["unexpected"] == ["extra"]


def _metrics(inputs: int | None, output: int, cached: int) -> dict[str, int | float | None]:
    return run_metrics(
        {
            "usage": {
                "input_tokens": inputs,
                "output_tokens": output,
                "cached_input_tokens": cached,
                "reasoning_output_tokens": 15,
            }
        }
    )


def test_subsets_are_not_added_to_total_or_imputed() -> None:
    assert _metrics(100, 20, 30)["raw_total_tokens"] == 120
    assert _metrics(100, 20, 30)["input_minus_cached_tokens"] == 70
    assert _metrics(None, 20, 30)["raw_total_tokens"] is None
    assert _metrics(100, 20, 30)["cache_write_input_tokens"] is None


def _rows() -> list[dict[str, object]]:
    return [
        {"case_id": "real", "arm": "text-only", "repetition": 1, "metrics": _metrics(100, 20, 30)},
        {"case_id": "real", "arm": "mcp+skill", "repetition": 1, "metrics": _metrics(80, 25, 10)},
        {"case_id": "real", "arm": "text-only", "repetition": 2, "metrics": _metrics(100, 20, 30)},
        {"case_id": "real", "arm": "mcp+skill", "repetition": 2, "metrics": _metrics(None, 25, 10)},
    ]


def test_pairs_and_each_repetition_remain_visible() -> None:
    pairs = paired_metrics(_rows())
    assert pairs[0]["difference_mcp_minus_text"] == {
        "input_tokens": -20,
        "cached_input_tokens": -20,
        "cache_write_input_tokens": None,
        "output_tokens": 5,
        "reasoning_output_tokens": 0,
        "raw_total_tokens": -15,
        "input_minus_cached_tokens": 0,
        "duration_seconds": None,
    }


def test_summary_preserves_missing_second_repetition() -> None:
    group = object_dict(group_summaries(_rows(), {"real_rtl": ["real"]})["real_rtl"])
    second = object_dict(object_dict(group["by_repetition"])["2"])
    total = object_dict(object_dict(group["all_repetitions"])["input_tokens"])
    assert object_dict(second["input_tokens"])["mcp+skill"] == {
        "sum": None,
        "known_count": 0,
        "expected_count": 1,
    }
    assert object_dict(total["mcp+skill"])["sum"] is None


def test_tool_counts_deduplicate_and_capture_failed_load_size(tmp_path: Path) -> None:
    (tmp_path / "top.sv").write_text("abc")
    item = {
        "id": "mcp1",
        "type": "mcp_tool_call",
        "tool": "project_load",
        "status": "failed",
        "error": None,
        "arguments": {"source_files": ["top.sv"]},
    }
    path = tmp_path / "public.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"type": kind, "item": item})
            for kind in ("item.started", "item.completed", "item.completed")
        )
    )
    result = tool_audit(path, tmp_path)
    assert result["completed_mcp_count"] == 1
    assert result["failed_mcp_count"] == 1
    assert result["completed_command_count"] == 0
    assert result["project_loads"] == [
        {
            "id": "mcp1",
            "source_files": ["top.sv"],
            "source_count": 1,
            "source_bytes": 3,
            "failed": True,
        }
    ]


def test_public_reasoning_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "public.jsonl"
    path.write_text('{"type":"item.completed","item":{"type":"reasoning","text":"private"}}')
    with pytest.raises(ValueError, match="reasoning"):
        tool_audit(path, tmp_path)


def test_export_retains_failure_and_pending_without_copying_private_data(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    source = request.runs / "case/text-only/rep_1"
    (source / "workspace").mkdir(parents=True)
    write_json(
        source / "result.json",
        {
            "id": "text-only",
            "case_id": "case",
            "arm": "text-only",
            "repetition": 1,
            "status": "agent_failed",
        },
    )
    (source / "trace.jsonl").write_text("private reasoning")
    (source / "public_trace.jsonl").write_text("")
    report = export(request)
    assert report["complete"] is False
    assert report["finalized_runs"] == 1
    assert report["pending_runs"] == ["mcp+skill"]
    assert (
        json.loads((request.output / "text-only/result.json").read_text())["status"]
        == "agent_failed"
    )
    assert object_dict(report["binary"])["valid"] is True
    assert report["manifest_matches"] is True
    assert {path.name for path in (request.output / "text-only").iterdir()} <= set(PUBLIC_ARTIFACTS)
    assert not (request.output / "text-only/trace.jsonl").exists()
