"""Isolation, arm parity, and failed attempts remain observable."""

# ruff: noqa: S101 -- Assertions are the pytest API, as in benchmarks/tests.

import json
from pathlib import Path

import pytest

from benchmarks.research_compare.models import Case, Run, Settings
from benchmarks.research_compare.prompts import build_prompt
from benchmarks.research_compare.runner import Request, command, run_one


def _request(tmp_path: Path, executable: Path) -> Request:
    workspace = tmp_path / "input"
    workspace.mkdir()
    (workspace / "design.sv").write_text("module top; endmodule\n")
    (tmp_path / "task.txt").write_text("Explain top.")
    (tmp_path / "skill.txt").write_text("Use semantic facts.")
    return Request(
        Settings(executable, Path("/frozen/slang-mcp"), tmp_path / "skill.txt", "model", "max", 1),
        Case("case", workspace, tmp_path / "task.txt"),
        Run("run", "case", "text-only", 1),
        tmp_path / "output",
    )


def test_prompt_parity() -> None:
    baseline = build_prompt("Question?", "text-only", "FROZEN_SKILL")
    treatment = build_prompt("Question?", "mcp+skill", "FROZEN_SKILL")
    assert treatment == baseline + "\nSlang MCP instructions:\nFROZEN_SKILL\n"
    assert "FROZEN_SKILL" not in baseline


def test_baseline_has_no_mcp_configuration(tmp_path: Path) -> None:
    request = _request(tmp_path, Path("/codex"))
    invocation = command(request, tmp_path, "prompt")
    assert not any("mcp_servers" in argument for argument in invocation.argv)
    assert "--ignore-user-config" in invocation.argv
    assert "--ephemeral" in invocation.argv
    assert invocation.argv[-1] == "prompt"


def test_missing_executable_preserves_failed_attempt(tmp_path: Path) -> None:
    request = _request(tmp_path, tmp_path / "missing")
    result = run_one(request)
    assert result["status"] == "setup_failed"
    assert (request.output / "result.json").exists()
    assert (request.output / "prompt.txt").exists()
    assert (request.output / "workspace/design.sv").read_bytes() == (
        request.case.workspace / "design.sv"
    ).read_bytes()


def test_timeout_retains_trace(tmp_path: Path) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text("#!/bin/sh\nexec sleep 10\n")
    executable.chmod(0o700)
    request = _request(tmp_path, executable)
    result = run_one(request)
    assert result["status"] == "timeout"
    assert result["timed_out"] is True
    assert (request.output / "trace.jsonl").exists()
    assert (request.output / "public_trace.jsonl").exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    request = _request(tmp_path, Path("/codex"))
    request.output.mkdir()
    with pytest.raises(FileExistsError):
        run_one(request)


def test_complete_answer_and_true_usage_are_retained(tmp_path: Path) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        "#!/bin/sh\ncat <<'EVENTS'\n"
        '{"type":"item.completed","item":{"type":"agent_message","text":"The answer."}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":20,'
        '"cache_write_input_tokens":5,"output_tokens":40,"reasoning_output_tokens":30}}\n'
        "EVENTS\n"
    )
    executable.chmod(0o700)
    request = _request(tmp_path, executable)
    result = run_one(request)
    assert result["status"] == "completed"
    assert result["usage"] == {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "cache_write_input_tokens": 5,
        "output_tokens": 40,
        "reasoning_output_tokens": 30,
    }
    assert (request.output / "answer.txt").read_text() == "The answer."
    assert (
        json.loads((request.output / "invocation.json").read_text())["argv"][-1]
        == (request.output / "prompt.txt").read_text()
    )
