"""Collect run telemetry while preserving raw files on parser failures."""

from __future__ import annotations

import shutil
from pathlib import Path

from benchmarks.adapters.traces import Trace, load_usage, parse_trace, usage_models
from benchmarks.runner.process import Completion
from benchmarks.runner.storage import write_json


def collect(root: Path, output: Path, record: dict[str, object], result: Completion) -> None:
    record.update(duration_seconds=result.duration, returncode=result.returncode)
    if (root / "usage.json").exists():
        shutil.copyfile(root / "usage.json", output / "usage.json")
    try:
        _parse_and_store(output, record, result)
    except (TypeError, ValueError) as error:
        record.update(execution_status="AGENT_FAILURE", correct=None, error=str(error))


def _parse_and_store(output: Path, record: dict[str, object], result: Completion) -> None:
    trace = parse_trace(output / "trace.jsonl")
    trace.models.update(usage_models(output / "usage.json"))
    record.update(trace.usage or load_usage(output / "usage.json"))
    _telemetry(trace, record)
    record["execution_status"] = classify(result, trace, str(record["model"]))
    (output / "final_answer.txt").write_text(trace.answer)
    write_json(output / "tool_calls.json", trace.calls)


def _telemetry(trace: Trace, record: dict[str, object]) -> None:
    record.update(
        actual=trace.answer,
        calls=trace.calls,
        observed_models=sorted(trace.models),
        errors=trace.errors,
        tool_call_count=len(trace.calls),
        mcp_tool_call_count=sum(call["category"] == "slang_mcp" for call in trace.calls),
        filesystem_tool_call_count=sum(call["category"] == "filesystem" for call in trace.calls),
        shell_tool_call_count=sum(call["category"] == "shell" for call in trace.calls),
    )


def classify(result: Completion, trace: Trace, model: str) -> str:
    if result.timed_out:
        return "TIMEOUT"
    if result.returncode != 0 or not trace.answer or (model != "auto" and trace.models != {model}):
        return "AGENT_FAILURE"
    if trace.errors or not trace.complete or not trace.models:
        return "AGENT_FAILURE"
    return "SUCCESS"
