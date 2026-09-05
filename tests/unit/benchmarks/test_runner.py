"""End-to-end runner behavior with fake agent events, never API calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchmarks.dataset import load_cases
from benchmarks.models import Mode, RunKey, Settings
from benchmarks.runner.process import Command, Completion
from benchmarks.runner.run import RunRequest, run_one
from benchmarks.runner.scoring import score_record


def _fake_execute(command: Command, output: Path) -> Completion:
    assert not (command.cwd / "corpus.json").exists()
    assert not any("oracle" in path.name for path in command.cwd.rglob("*"))
    events: list[dict[str, object]] = [
        {"type": "assistant.message", "data": {"content": "worker"}},
        {"type": "result", "exitCode": 0},
    ]
    if json.loads((command.cwd.parent / "mcp.json").read_text())["mcpServers"]:
        events.append(
            {
                "type": "session.mcp_server_status_changed",
                "data": {"serverName": "slang_benchmark", "status": "connected"},
            }
        )
    (output / "trace.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    (command.cwd.parent / "usage.json").write_text(
        json.dumps(
            {
                "modelMetrics": {
                    "fake-model": {
                        "usage": {"inputTokens": 40, "outputTokens": 2, "cacheReadTokens": 30}
                    }
                }
            }
        )
    )
    (output / "stderr.txt").touch()
    return Completion(0, 0.01, False)


@pytest.mark.parametrize("mode", ["text-only", "mcp", "mcp+skill"])
def test_runner_exports_and_collects(
    mode: Mode, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("benchmarks.runner.run.preflight", lambda *_args: {"version": "fake"})
    monkeypatch.setattr("benchmarks.runner.run.execute", _fake_execute)
    monkeypatch.setattr("benchmarks.adapters.copilot.system_copilot", lambda: "/fake/copilot")
    record = run_one(
        RunRequest(
            next(case for case in load_cases() if case.id == "hier_generate"),
            RunKey("hier_generate", mode, 1),
            Settings(),
            "test",
            tmp_path,
        )
    )
    assert record["execution_status"] == "SUCCESS"
    assert record["observed_models"] == ["fake-model"]
    assert record["total_tokens"] == 42
    assert (tmp_path / "metadata.json").exists()
    assert (tmp_path / "final_answer.txt").read_text() == "worker"


def test_mode_failure_kept_separate_from_answer(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text("")
    record: dict[str, object] = {"mode": "mcp", "execution_status": "SUCCESS", "actual": "worker"}
    score_record(load_cases()[0], record, path)
    assert record["execution_status"] == "MCP_FAILURE"
    assert record["correct"] is None


def test_scorer_exception_kept_as_infrastructure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("benchmarks.runner.scoring.score", _broken_scorer)
    path = tmp_path / "trace.jsonl"
    path.write_text("")
    record: dict[str, object] = {
        "mode": "text-only",
        "execution_status": "SUCCESS",
        "actual": "worker",
    }
    score_record(load_cases()[0], record, path)
    assert record["execution_status"] == "SCORER_FAILURE"
    assert record["correct"] is None


def _broken_scorer(*_args: object) -> bool:
    raise ValueError("fake scorer fault")
