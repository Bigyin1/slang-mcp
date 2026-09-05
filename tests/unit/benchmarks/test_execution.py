"""Agent-independent subprocess, trace and resume checks."""

import json
import os
import sys
from pathlib import Path

import pytest
from benchmarks.adapters.audit import audit_mode
from benchmarks.adapters.copilot import CopilotAdapter
from benchmarks.adapters.traces import Trace, load_usage, parse_trace
from benchmarks.models import Settings
from benchmarks.runner.collection import classify, collect
from benchmarks.runner.isolation import configure_workspace, mcp_configuration
from benchmarks.runner.process import Command, Completion, execute
from benchmarks.runner.storage import reusable, write_json


def test_direct_system_cli_and_direct_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/system/bin/copilot")
    configure_workspace(tmp_path)
    mcp_configuration(tmp_path, True)
    command = CopilotAdapter().command(tmp_path, "question", Settings())
    assert command.argv[0] == "/system/bin/copilot"
    assert "--reasoning-effort" not in command.argv
    assert command.environment.get("HOME") == os.environ.get("HOME")
    config = json.loads((tmp_path / "mcp.json").read_text())
    server = config["mcpServers"]["slang_benchmark"]
    assert server["command"].endswith("/.venv/bin/slang-mcp")
    assert not any("proxy" in value for value in server["args"])
    mcp_configuration(tmp_path, False)
    assert json.loads((tmp_path / "mcp.json").read_text())["mcpServers"] == {}


def test_trace_parser_and_usage(tmp_path: Path) -> None:
    events = [
        {"type": "session.start", "data": {"selectedModel": "auto"}},
        {"type": "assistant.usage", "data": {"model": "model-a"}},
        {
            "type": "tool.execution_start",
            "id": "unique",
            "data": {
                "toolName": "slang_benchmark-project_load",
                "mcpServerName": "slang_benchmark",
            },
        },
        {"type": "tool.execution_start", "id": "unique", "data": {}},
        {"type": "assistant.message", "data": {"content": "answer", "reasoningText": "private"}},
        {"type": "result", "exitCode": 0},
    ]
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events))
    trace = parse_trace(path)
    assert trace.answer == "answer"
    assert trace.complete
    assert trace.models == {"model-a"}
    assert len(trace.calls) == 1
    assert trace.calls[0]["category"] == "slang_mcp"
    assert load_usage(tmp_path / "missing.json")["total_tokens"] is None


def test_token_totals_do_not_double_count_cache(tmp_path: Path) -> None:
    path = tmp_path / "usage.json"
    write_json(
        path,
        {
            "modelMetrics": {
                "m": {"usage": {"inputTokens": 100, "outputTokens": 10, "cacheReadTokens": 80}}
            }
        },
    )
    assert load_usage(path) == {
        "input_tokens": 100,
        "output_tokens": 10,
        "cached_input_tokens": 80,
        "total_tokens": 110,
    }


def test_timeout_is_separate_from_wrong_answer(tmp_path: Path) -> None:
    completion = execute(
        Command(
            [sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, os.environ.copy(), 0.05
        ),
        tmp_path,
    )
    assert completion.timed_out
    assert classify(completion, parse_trace(tmp_path / "trace.jsonl"), "auto") == "TIMEOUT"


def test_resume_requires_complete_matching_record_and_trace(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    write_json(path, {"completed": True, "fingerprint": "same"})
    assert not reusable(path, "same")
    (tmp_path / "trace.jsonl").touch()
    assert reusable(path, "same")
    assert not reusable(path, "different")


def test_failed_mcp_initialization_is_not_a_semantic_wrong_answer(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps(
            {
                "type": "session.mcp_server_status_changed",
                "data": {"serverName": "slang_benchmark", "status": "failed"},
            }
        )
    )
    assert not audit_mode(trace, "mcp")["valid"]
    assert not audit_mode(trace, "text-only")["valid"]


def test_recovered_mcp_connection_is_valid(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "session.mcp_server_status_changed",
                    "data": {"serverName": "slang_benchmark", "status": status},
                }
            )
            for status in ("failed", "connected")
        )
    )
    assert audit_mode(trace, "mcp")["valid"]


def test_malformed_usage_preserves_agent_failure(tmp_path: Path) -> None:
    (tmp_path / "trace.jsonl").write_text('{"type":"result","exitCode":0}\n')
    (tmp_path / "usage.json").write_text("truncated{")
    root = tmp_path / "runtime"
    root.mkdir()
    record: dict[str, object] = {"model": "auto"}
    collect(root, tmp_path, record, Completion(0, 1.0, False))
    assert record["execution_status"] == "AGENT_FAILURE"
    assert (tmp_path / "usage.json").read_text() == "truncated{"


def test_unknown_actual_model_is_not_silently_accepted() -> None:
    assert (
        classify(Completion(0, 1.0, False), Trace(answer="worker", complete=True), "auto")
        == "AGENT_FAILURE"
    )
