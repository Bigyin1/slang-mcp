"""Audit a separate task freeze without weakening the original builder anchor."""

# ruff: noqa: S101, PLR2004 -- Assertions and literal values specify audit behavior.

import json
from pathlib import Path

import pytest

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit import PUBLIC_ARTIFACTS
from benchmarks.research_compare.audit_integrity import digest
from benchmarks.research_compare.audit_open import export
from benchmarks.research_compare.tests.open_fixture import make_open, prepare_run, refreeze
from benchmarks.runner.storage import write_json


def _entry(value: object, index: int) -> dict[str, object]:
    assert isinstance(value, list)
    return object_dict(value[index])


def test_open_export_checks_four_runs_and_copies_only_public_artifacts(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    for index in range(4):
        prepare_run(experiment, index)
    report = export(experiment.request, experiment.builders)
    assert report["complete"] is True
    assert report["integrity_valid"] is True
    assert report["scheduled_runs"] == report["finalized_runs"] == 4
    assert object_dict(report["open_inputs"])["shared_revision"] == experiment.builders.revision
    _assert_public_runs(experiment.request.output, report["runs"])


def _assert_public_runs(output: Path, runs: object) -> None:
    assert isinstance(runs, list)
    for run in runs:
        assert set((output / run["id"]).iterdir()) == {
            output / run["id"] / name for name in PUBLIC_ARTIFACTS
        }
        assert object_dict(run["metrics"])["raw_total_tokens"] == 120
        assert object_dict(run["metrics"])["input_minus_cached_tokens"] == 70


def test_open_export_preserves_pending_attempts_and_unknown_tokens(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    prepare_run(experiment, 0)
    report = export(experiment.request, experiment.builders)
    assert report["complete"] is False
    assert report["integrity_valid"] is False
    assert report["finalized_runs"] == 1
    assert isinstance(report["pending_runs"], list)
    assert len(report["pending_runs"]) == 3
    assert object_dict(_entry(report["runs"], 1)["metrics"])["raw_total_tokens"] is None


@pytest.mark.parametrize("name", ["inputs.json", "protocol.json", "cases/axi_review/oracle.md"])
def test_open_metadata_and_oracle_are_bound_to_separate_commit(tmp_path: Path, name: str) -> None:
    experiment = make_open(tmp_path)
    path = experiment.request.inputs.parent / name
    path.write_bytes(path.read_bytes() + b"changed")
    report = export(experiment.request, experiment.builders)
    assert object_dict(report["freeze"])["valid"] is False


@pytest.mark.parametrize("name", ["models.py", "prompts.py", "runner.py", "skill.md"])
def test_shared_builders_and_skill_keep_the_original_anchor(tmp_path: Path, name: str) -> None:
    experiment = make_open(tmp_path)
    prepare_run(experiment, 1)
    path = experiment.builders.root / experiment.builders.directory / name
    path.write_bytes(path.read_bytes() + b"changed")
    report = export(experiment.request, experiment.builders)
    assert object_dict(object_dict(report["freeze"])["builders"])["valid"] is False
    assert report["integrity_valid"] is False


@pytest.mark.parametrize("name", ["prompt.txt", "invocation.json"])
def test_open_actual_prompt_and_argv_are_checked(tmp_path: Path, name: str) -> None:
    experiment = make_open(tmp_path)
    source = prepare_run(experiment, 1)
    (source / name).write_text('"altered runtime artifact"')
    report = export(experiment.request, experiment.builders)
    assert (
        object_dict(
            object_dict(_entry(report["runs"], 1)["artifacts"])[name.split(".", maxsplit=1)[0]]
        )["valid"]
        is False
    )


def test_coordinated_inputs_and_runtime_edits_keep_committed_truth(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    source = prepare_run(experiment, 0)
    (source / "workspace/top.sv").write_text("changed runtime")
    inputs = json.loads(experiment.request.inputs.read_text())
    inputs["axi_review"]["files"]["top.sv"] = digest(source / "workspace/top.sv")
    write_json(experiment.request.inputs, inputs)
    report = export(experiment.request, experiment.builders)
    assert object_dict(_entry(report["runs"], 0)["workspace"])["changed"] == ["top.sv"]
    assert report["integrity_valid"] is False


def test_committed_false_input_map_fails_corpus_cross_check(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    inputs = json.loads(experiment.request.inputs.read_text())
    inputs["axi_review"]["files"].pop("task.txt")
    write_json(experiment.request.inputs, inputs)
    report = export(refreeze(experiment).request, experiment.builders)
    assert object_dict(report["freeze"])["valid"] is True
    assert _entry(object_dict(report["open_inputs"])["cases"], 0)["input_hashes_match"] is False


@pytest.mark.parametrize("field", ["skill", "task"])
def test_committed_path_aliases_cannot_replace_frozen_inputs(tmp_path: Path, field: str) -> None:
    experiment = make_open(tmp_path)
    manifest = json.loads((experiment.request.inputs.parent / "manifest.json").read_text())
    if field == "skill":
        manifest["skill"] = str(tmp_path / "other_skill.md")
    else:
        manifest["cases"][0]["task"] = str(tmp_path / "other_task.txt")
    write_json(experiment.request.inputs.parent / "manifest.json", manifest)
    report = export(refreeze(experiment).request, experiment.builders)
    assert object_dict(report["open_inputs"])["valid"] is False


def test_shared_hash_declarations_are_checked_against_original_commit(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    protocol = json.loads(experiment.request.protocol.read_text())
    protocol["shared_files"]["skill.md"] = "false hash committed with new inputs"
    write_json(experiment.request.protocol, protocol)
    report = export(refreeze(experiment).request, experiment.builders)
    assert object_dict(report["freeze"])["valid"] is True
    assert object_dict(report["open_inputs"])["shared_files_match"] is False


@pytest.mark.parametrize("name", ["binary", "manifest.json"])
def test_open_binary_and_runtime_manifest_drift_are_detected(tmp_path: Path, name: str) -> None:
    experiment = make_open(tmp_path)
    path = tmp_path / "binary" if name == "binary" else experiment.request.runs / name
    path.write_text("changed")
    report = export(experiment.request, experiment.builders)
    if name == "binary":
        assert object_dict(report["binary"])["valid"] is False
    else:
        assert report["manifest_matches"] is False


def test_reasoning_in_public_trace_is_refused_before_copy(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    source = prepare_run(experiment, 0)
    (source / "public_trace.jsonl").write_text(
        '{"type":"item.completed","item":{"type":"reasoning","text":"private"}}'
    )
    with pytest.raises(ValueError, match="reasoning"):
        export(experiment.request, experiment.builders)
    assert not list(experiment.request.output.rglob("public_trace.jsonl"))


def test_open_tools_reuse_completed_failed_call_and_source_size_metrics(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    source = prepare_run(experiment, 1)
    (source / "public_trace.jsonl").write_text(
        (source / "public_trace.jsonl").read_text()
        + json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "failed-load",
                    "type": "mcp_tool_call",
                    "tool": "project_load",
                    "status": "failed",
                    "arguments": {"source_files": ["top.sv"]},
                },
            }
        )
    )
    report = export(experiment.request, experiment.builders)
    assert object_dict(_entry(report["runs"], 1)["tools"])["failed_mcp_count"] == 1
    assert (
        _entry(object_dict(_entry(report["runs"], 1)["tools"])["project_loads"], 0)["source_bytes"]
        == (source / "workspace/top.sv").stat().st_size
    )


def test_malformed_open_config_cannot_leave_a_successful_base_report(tmp_path: Path) -> None:
    experiment = make_open(tmp_path)
    for index in range(4):
        prepare_run(experiment, index)
    (experiment.request.inputs.parent / "cases/axi_review/workspace/config.json").write_text(
        "malformed JSON"
    )
    with pytest.raises(json.JSONDecodeError):
        export(refreeze(experiment).request, experiment.builders)
    assert not (experiment.request.output / "metrics.json").exists()
