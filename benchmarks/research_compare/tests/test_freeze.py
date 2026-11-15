"""Detect coordinated input edits and changed prompts, invocation, or builders."""

# ruff: noqa: S101 -- Assertions are the pytest API.

import json
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pytest

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit import AuditRequest, export
from benchmarks.research_compare.audit_freeze import (
    Snapshot,
    artifact_audit,
    frozen_plan,
    load_snapshot,
    snapshot_audit,
)
from benchmarks.research_compare.audit_integrity import digest
from benchmarks.research_compare.models import Plan, Run
from benchmarks.research_compare.prompts import build_prompt
from benchmarks.research_compare.runner import Request, command
from benchmarks.research_compare.tests.audit_fixture import make_request
from benchmarks.runner.storage import write_json


@dataclass(frozen=True)
class Prepared:
    snapshot: Snapshot
    plan: Plan
    run: Run
    source: Path


def _prepare(request: AuditRequest) -> Prepared:
    snapshot = load_snapshot(request.inputs.parent, request.revision)
    plan = frozen_plan(snapshot)
    source = request.runs / "case/text-only/rep_1"
    shutil.copytree(request.inputs.parent / "cases/case/rtl", source / "workspace/rtl")
    prepared = Prepared(snapshot, plan, plan.runs[0], source)
    _write_artifacts(prepared)
    return prepared


def _write_artifacts(prepared: Prepared) -> None:
    prompt = build_prompt(
        prepared.snapshot.read("cases/case/task.txt").decode(),
        prepared.run.arm,
        prepared.snapshot.read("skill.md").decode(),
    )
    invocation = command(
        Request(prepared.plan.settings, prepared.plan.cases[0], prepared.run, prepared.source),
        prepared.source / "workspace",
        prompt,
    )
    (prepared.source / "prompt.txt").write_text(prompt)
    (prepared.source / "public_trace.jsonl").write_text("")
    write_json(prepared.source / "result.json", {**asdict(prepared.run), "status": "completed"})
    write_json(
        prepared.source / "invocation.json",
        {"argv": invocation.argv, "cwd": str(invocation.cwd), "timeout": invocation.timeout},
    )


@pytest.mark.parametrize(
    "name",
    [
        "inputs.json",
        "protocol.json",
        "manifest.json",
        "skill.md",
        "cases/case/task.txt",
        "cases/case/rtl/top.sv",
        "oracles/expected.json",
        "models.py",
        "prompts.py",
        "runner.py",
        "traces.py",
    ],
)
def test_every_frozen_input_is_anchored_to_commit(tmp_path: Path, name: str) -> None:
    request = make_request(tmp_path)
    snapshot = load_snapshot(request.inputs.parent, request.revision)
    assert snapshot_audit(snapshot)["valid"] is True
    (request.inputs.parent / name).write_bytes(
        (request.inputs.parent / name).read_bytes() + b"changed"
    )
    assert snapshot_audit(snapshot)["valid"] is False


def test_prompt_corruption_is_detected(tmp_path: Path) -> None:
    prepared = _prepare(make_request(tmp_path))
    assert (
        object_dict(
            artifact_audit(prepared.snapshot, prepared.plan, prepared.run, prepared.source)[
                "prompt"
            ]
        )["valid"]
        is True
    )
    (prepared.source / "prompt.txt").write_text("altered task")
    assert (
        object_dict(
            artifact_audit(prepared.snapshot, prepared.plan, prepared.run, prepared.source)[
                "prompt"
            ]
        )["valid"]
        is False
    )


@pytest.mark.parametrize("field", ["model", "effort", "config", "cwd", "timeout"])
def test_invocation_corruption_is_detected(tmp_path: Path, field: str) -> None:
    prepared = _prepare(make_request(tmp_path))
    data = json.loads((prepared.source / "invocation.json").read_text())
    _corrupt_invocation(data, field)
    write_json(prepared.source / "invocation.json", data)
    assert (
        object_dict(
            artifact_audit(prepared.snapshot, prepared.plan, prepared.run, prepared.source)[
                "invocation"
            ]
        )["valid"]
        is False
    )


def _corrupt_invocation(data: dict[str, object], field: str) -> None:
    if field in {"cwd", "timeout"}:
        data[field] = "changed"
        return
    assert isinstance(data["argv"], list)
    if field == "model":
        data["argv"][data["argv"].index("--model") + 1] = "changed"
    else:
        prefix = {"effort": "model_reasoning_effort=", "config": "web_search="}[field]
        data["argv"] = [
            "changed" if str(value).startswith(prefix) else value for value in data["argv"]
        ]


def test_consistent_current_input_and_workspace_edits_still_fail(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    prepared = _prepare(request)
    (prepared.source / "workspace/rtl/top.sv").write_text("mutated")
    write_json(
        request.inputs,
        {"case": {"files": {"rtl/top.sv": digest(prepared.source / "workspace/rtl/top.sv")}}},
    )
    report = export(request)
    assert object_dict(report["freeze"])["valid"] is False
    assert report["integrity_valid"] is False
    assert isinstance(report["runs"], list)
    assert object_dict(object_dict(report["runs"][0])["workspace"])["valid"] is False


def test_changed_builder_fails_closed(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    prepared = _prepare(request)
    (request.inputs.parent / "runner.py").write_text("changed builder")
    assert (
        artifact_audit(prepared.snapshot, prepared.plan, prepared.run, prepared.source)["valid"]
        is False
    )


def test_finished_snapshot_with_missing_answers_fails_integrity(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    prepared = _prepare(request)
    source = request.runs / "case/mcp+skill/rep_1"
    shutil.copytree(prepared.source / "workspace", source / "workspace")
    _write_artifacts(Prepared(prepared.snapshot, prepared.plan, prepared.plan.runs[1], source))
    report = export(request)
    assert report["complete"] is True
    assert report["artifacts_complete"] is False
    assert report["integrity_valid"] is False


def test_inconsistent_protocol_path_is_rejected(tmp_path: Path) -> None:
    request = replace(make_request(tmp_path), protocol=tmp_path / "other_protocol.json")
    with pytest.raises(ValueError, match="same frozen package"):
        export(request)
