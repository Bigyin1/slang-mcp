"""Detect changed public answers/counters in either experiment without raw traces."""

# ruff: noqa: S101 -- Assertions specify audit behavior.

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit import AuditRequest
from benchmarks.research_compare.audit import export as export_main
from benchmarks.research_compare.audit_content import content_audit
from benchmarks.research_compare.audit_freeze import Snapshot, frozen_plan, load_snapshot
from benchmarks.research_compare.audit_open import export as export_open
from benchmarks.research_compare.prompts import build_prompt
from benchmarks.research_compare.runner import Request
from benchmarks.research_compare.tests.audit_fixture import make_request
from benchmarks.research_compare.tests.open_fixture import make_open, prepare_run, write_artifacts
from benchmarks.research_compare.traces import TOKEN_FIELDS
from benchmarks.runner.storage import write_json


@dataclass(frozen=True)
class PreparedExport:
    request: AuditRequest
    builders: Snapshot | None


def _prepare(tmp_path: Path, package: str) -> PreparedExport:
    if package == "main":
        return PreparedExport(_prepare_main(tmp_path), None)
    experiment = make_open(tmp_path)
    for index in range(4):
        prepare_run(experiment, index)
    return PreparedExport(experiment.request, experiment.builders)


def _prepare_main(tmp_path: Path) -> AuditRequest:
    request = make_request(tmp_path)
    snapshot = load_snapshot(request.inputs.parent, request.revision)
    plan = frozen_plan(snapshot)
    for run in plan.runs:
        _main_run(
            Request(
                plan.settings,
                plan.cases[0],
                run,
                request.runs / run.case_id / run.arm / f"rep_{run.repetition}",
            ),
            snapshot,
        )
    return request


def _main_run(request: Request, snapshot: Snapshot) -> None:
    shutil.copytree(
        snapshot.root / snapshot.directory / "cases/case/rtl", request.output / "workspace/rtl"
    )
    write_artifacts(
        request,
        build_prompt(
            snapshot.read("cases/case/task.txt").decode(),
            request.run.arm,
            snapshot.read("skill.md").decode(),
        ),
    )


def _first_run(request: AuditRequest) -> Path:
    run = frozen_plan(load_snapshot(request.inputs.parent, request.revision)).runs[0]
    return request.runs / run.case_id / run.arm / f"rep_{run.repetition}"


def _export(prepared: PreparedExport) -> dict[str, object]:
    if prepared.builders is None:
        return export_main(prepared.request)
    return export_open(prepared.request, prepared.builders)


@pytest.mark.parametrize("package", ["main", "open"])
def test_consistent_public_content_passes_both_exporters(tmp_path: Path, package: str) -> None:
    report = _export(_prepare(tmp_path, package))
    assert report["complete"] is True
    assert report["integrity_valid"] is True


@pytest.mark.parametrize("package", ["main", "open"])
@pytest.mark.parametrize(
    "field",
    [
        "answer",
        "result_answer",
        "public_answer",
        "result_usage",
        "public_usage",
        "usage_events",
        "turns",
    ],
)
def test_changed_public_content_invalidates_export(
    tmp_path: Path, package: str, field: str
) -> None:
    prepared = _prepare(tmp_path, package)
    _tamper(_first_run(prepared.request), field)
    report = _export(prepared)
    assert report["complete"] is True
    assert report["artifacts_complete"] is True
    assert report["integrity_valid"] is False


def _tamper(source: Path, field: str) -> None:
    if field == "answer":
        (source / "answer.txt").write_text("Edited answer only")
    elif field.startswith("public_"):
        _tamper_public(source / "public_trace.jsonl", field)
    else:
        _tamper_result(source / "result.json", field)


def _tamper_public(path: Path, field: str) -> None:
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if field == "public_answer":
        events[0]["item"]["text"] = "Edited final public agent message"
    else:
        events[-1]["usage"]["input_tokens"] = 0
    path.write_text("\n".join(json.dumps(event) for event in events))


def _tamper_result(path: Path, field: str) -> None:
    result = json.loads(path.read_text())
    if field == "result_answer":
        result["answer"] = "Edited result answer only"
    elif field == "result_usage":
        result["usage"]["input_tokens"] = 0
    elif field == "usage_events":
        result["usage_events"][0]["input_tokens"] = 0
    else:
        result["completed_turns"] = 0
    write_json(path, result)


def test_timeout_with_no_answer_or_usage_can_be_consistent(tmp_path: Path) -> None:
    (tmp_path / "answer.txt").write_text("")
    (tmp_path / "public_trace.jsonl").write_text("")
    result: dict[str, object] = {
        "status": "timeout",
        "answer": "",
        "usage": dict.fromkeys(TOKEN_FIELDS),
        "usage_events": [],
        "completed_turns": 0,
    }
    assert content_audit(tmp_path, result)["valid"] is True


def test_partial_usage_is_compared_without_imputing_missing_counters(tmp_path: Path) -> None:
    (tmp_path / "answer.txt").write_text("")
    (tmp_path / "public_trace.jsonl").write_text(
        '{"type":"turn.completed","usage":{"input_tokens":17}}\n'
    )
    result: dict[str, object] = {
        "status": "agent_failed",
        "answer": "",
        "usage": {**dict.fromkeys(TOKEN_FIELDS), "input_tokens": 17},
        "usage_events": [{"input_tokens": 17}],
        "completed_turns": 1,
    }
    assert content_audit(tmp_path, result)["valid"] is True
    object_dict(result["usage"])["output_tokens"] = 0
    assert content_audit(tmp_path, result)["valid"] is False


@pytest.mark.parametrize("package", ["main", "open"])
def test_consistent_failure_stays_included_and_can_pass_integrity(
    tmp_path: Path, package: str
) -> None:
    prepared = _prepare(tmp_path, package)
    result = json.loads((_first_run(prepared.request) / "result.json").read_text())
    result["status"] = "timeout"
    write_json(_first_run(prepared.request) / "result.json", result)
    report = _export(prepared)
    assert report["complete"] is True
    assert report["integrity_valid"] is True
