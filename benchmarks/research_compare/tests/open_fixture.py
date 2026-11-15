"""Two separately committed input packages and four fabricated public runs."""

import json
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from git import Actor, Repo

from benchmarks.research_compare.audit import AuditRequest
from benchmarks.research_compare.audit_freeze import Snapshot, frozen_plan, load_snapshot
from benchmarks.research_compare.audit_integrity import digest
from benchmarks.research_compare.audit_open import SHARED_FILES
from benchmarks.research_compare.prompts import build_prompt
from benchmarks.research_compare.runner import Request, command
from benchmarks.research_compare.tests.audit_fixture import make_request
from benchmarks.research_compare.traces import Trace, parse_trace
from benchmarks.runner.storage import write_json

CASES = ("axi_review", "idma_review")


@dataclass(frozen=True)
class OpenExperiment:
    request: AuditRequest
    builders: Snapshot


def make_open(tmp_path: Path) -> OpenExperiment:
    """Commit open inputs after the original package without changing its files."""
    original = make_request(tmp_path)
    request = replace(
        original,
        runs=tmp_path / "open_runs",
        output=tmp_path / "open_export",
        inputs=original.inputs.parent / "open_review/inputs.json",
        protocol=original.inputs.parent / "open_review/protocol.json",
    )
    builders = load_snapshot(original.inputs.parent, original.revision)
    _package(request, builders)
    return refreeze(OpenExperiment(request, builders))


def refreeze(experiment: OpenExperiment) -> OpenExperiment:
    """Create a new fixture commit to test internally consistent false metadata."""
    protocol = json.loads(experiment.request.protocol.read_text())
    protocol["files"] = {
        name: value
        for name, value in _hashes(experiment.request.inputs.parent).items()
        if name != "protocol.json"
    }
    write_json(experiment.request.protocol, protocol)
    with Repo(experiment.builders.root) as repo:
        repo.index.add(
            [
                str(path.relative_to(experiment.builders.root))
                for path in experiment.request.inputs.parent.rglob("*")
                if path.is_file()
            ]
        )
        commit = repo.index.commit(
            "freeze open test inputs",
            author=Actor("Test", "test@example.invalid"),
            committer=Actor("Test", "test@example.invalid"),
        )
    return replace(experiment, request=replace(experiment.request, revision=commit.hexsha))


def _package(request: AuditRequest, builders: Snapshot) -> None:
    request.inputs.parent.mkdir()
    for case in CASES:
        _case(request, case)
    write_json(request.inputs.parent / "manifest.json", _manifest(request, builders))
    write_json(request.runs / "manifest.json", _manifest(request, builders))
    write_json(request.inputs, {case: _input(request, case) for case in CASES})
    write_json(
        request.protocol,
        {
            "total_runs": 4,
            "real_rtl_cases": list(CASES),
            "synthetic_controls": [],
            "server_sha256": digest(builders.root / "binary"),
            "shared_files": {
                name: digest(builders.root / builders.directory / name) for name in SHARED_FILES
            },
            "files": _hashes(request.inputs.parent),
        },
    )


def _case(request: AuditRequest, case: str) -> None:
    workspace = request.inputs.parent / f"cases/{case}/workspace"
    workspace.mkdir(parents=True)
    (workspace / "task.txt").write_text(f"Review the {case} source.")
    (workspace / "top.sv").write_text(f"module {case}; endmodule\n")
    write_json(workspace / "config.json", {"top_module": case, "single_unit": True})
    (workspace.parent / "oracle.md").write_text("Private source-derived oracle.\n")
    shutil.copytree(workspace, request.runs.parent / f"inputs/{case}")


def _manifest(request: AuditRequest, builders: Snapshot) -> dict[str, object]:
    return {
        **builders.json("manifest.json"),
        "cases": [
            {
                "id": case,
                "workspace": str(request.runs.parent / f"inputs/{case}"),
                "task": str(request.inputs.parent / f"cases/{case}/workspace/task.txt"),
            }
            for case in CASES
        ],
        "runs": [
            {"id": f"{case}_{arm}", "case_id": case, "arm": arm, "repetition": 1}
            for case in CASES
            for arm in ("text-only", "mcp+skill")
        ],
    }


def _input(request: AuditRequest, case: str) -> dict[str, object]:
    return {
        "config": {"top_module": case, "single_unit": True},
        "files": _hashes(request.inputs.parent / f"cases/{case}/workspace"),
    }


def _hashes(directory: Path) -> dict[str, object]:
    return {
        str(path.relative_to(directory)): digest(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def prepare_run(experiment: OpenExperiment, index: int) -> Path:
    """Fabricate artifacts with the real frozen prompt/argv builders, never a worker."""
    request = _request(experiment, index)
    shutil.copytree(request.case.workspace, request.output / "workspace")
    write_artifacts(
        request,
        build_prompt(
            request.case.task.read_text(encoding="utf-8"),
            request.run.arm,
            experiment.builders.read("skill.md").decode(),
        ),
    )
    return request.output


def _request(experiment: OpenExperiment, index: int) -> Request:
    plan = frozen_plan(load_snapshot(experiment.request.inputs.parent, experiment.request.revision))
    run = plan.runs[index]
    return Request(
        plan.settings,
        next(case for case in plan.cases if case.id == run.case_id),
        run,
        experiment.request.runs / run.case_id / run.arm / f"rep_{run.repetition}",
    )


def write_artifacts(request: Request, prompt: str) -> None:
    """Write mutually consistent public artifacts using the real parser and builders."""
    invocation = command(request, request.output / "workspace", prompt)
    trace = _public_trace(request.output / "public_trace.jsonl")
    (request.output / "answer.txt").write_text(trace.answer)
    (request.output / "prompt.txt").write_text(prompt)
    (request.output / "trace.jsonl").write_text("Private raw trace and reasoning.")
    write_json(
        request.output / "result.json",
        {
            **asdict(request.run),
            "status": "completed",
            "duration_seconds": 2,
            "answer": trace.answer,
            "usage": trace.usage(),
            "usage_events": trace.usage_events,
            "completed_turns": trace.completed_turns,
        },
    )
    write_json(
        request.output / "invocation.json",
        {"argv": invocation.argv, "cwd": str(invocation.cwd), "timeout": invocation.timeout},
    )


def _public_trace(path: Path) -> Trace:
    path.write_text(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": "Source-derived public answer.",
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 30},
            }
        )
        + "\n"
    )
    return parse_trace(path)
