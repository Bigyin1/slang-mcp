"""Execute isolated runs; preserve failed attempts and never silently repair answers."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from benchmarks.adapters.copilot import CopilotAdapter
from benchmarks.adapters.preflight import preflight
from benchmarks.dataset import ROOT
from benchmarks.models import Case, RunKey, Settings
from benchmarks.runner.collection import collect
from benchmarks.runner.isolation import configure_workspace, mcp_configuration
from benchmarks.runner.process import execute
from benchmarks.runner.projects import prepare_project
from benchmarks.runner.scoring import score_record
from benchmarks.runner.storage import write_json


@dataclass(frozen=True)
class RunRequest:
    case: Case
    key: RunKey
    settings: Settings
    fingerprint: str
    output: Path


def prompt(case: Case, mode: str) -> str:
    base = (
        "Analyze the supplied SystemVerilog RTL. Your working directory is the workspace. "
        "Read projects.json and top_module.txt in that directory. "
        "Do not modify RTL. Return only the requested response format.\n\n"
    )
    if mode != "text-only":
        base += (
            "Slang MCP is available. Read source_files.f as an ordered inventory. "
            "Choose the smallest relevant set of source files and its dependencies, "
            "preserving their inventory order. Call project_load with those actual absolute "
            "paths in source_files, actual directories from include_directories.f in "
            "include_directories, and defines from projects.json. Choose the relevant "
            "top_module; use top_module.txt when the question needs the supplied project top. "
            "Add dependencies and call project_load again if diagnostics or the question "
            "require them. single_unit defaults to true; set it to false only when separate "
            "compilation units are needed.\n\n"
        )
    base += case.question
    if mode == "mcp+skill":
        return (ROOT / "skills/semantic.md").read_text() + "\n" + base
    return base


def run_one(request: RunRequest) -> dict[str, object]:
    record = _initial_record(request)
    (request.output / "trace.jsonl").touch()
    try:
        _isolated_run(request, record)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        record.update(execution_status="PROJECT_SETUP_FAILURE", error=str(error))
    record["completed"] = True
    write_json(request.output / "metadata.json", record)
    return record


def _initial_record(request: RunRequest) -> dict[str, object]:
    return {
        **asdict(request.key),
        "category": request.case.category,
        "project": request.case.project,
        "model": request.settings.model,
        "fingerprint": request.fingerprint,
        "expected": request.case.oracle,
        "actual": "",
        "correct": None,
        "execution_status": "PROJECT_SETUP_FAILURE",
        "duration_seconds": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "tool_call_count": None,
        "mcp_tool_call_count": None,
        "trace_path": str(request.output / "trace.jsonl"),
        "calls": [],
    }


def _isolated_run(request: RunRequest, record: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory(prefix="slang-bench-", dir="/private/tmp") as directory:
        root = Path(directory)
        configure_workspace(root)
        record["rtl"] = prepare_project(request.case.project, root / "workspace")
        _invoke(request, root, record)


def _invoke(request: RunRequest, root: Path, record: dict[str, object]) -> None:
    record["cli"] = preflight(request.settings, root / "workspace")
    shutil.copyfile(
        mcp_configuration(root, request.key.mode != "text-only"), request.output / "mcp_config.json"
    )
    shutil.copyfile(root / "workspace/projects.json", request.output / "project_config.json")
    command = CopilotAdapter().command(
        root, prompt(request.case, request.key.mode), request.settings
    )
    write_json(
        request.output / "invocation.json",
        {"argv": command.argv, "cwd": str(command.cwd), "timeout": command.timeout},
    )
    result = execute(command, request.output)
    collect(root, request.output, record, result)
    score_record(request.case, record, request.output / "trace.jsonl")
