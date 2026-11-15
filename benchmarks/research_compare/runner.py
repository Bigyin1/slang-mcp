"""Execute independent CLI contexts from an explicit frozen run manifest."""

from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.research_compare.models import Case, Plan, Run, Settings
from benchmarks.research_compare.prompts import build_prompt
from benchmarks.research_compare.traces import TOKEN_FIELDS, Trace, parse_trace, write_public_trace
from benchmarks.runner.process import Command, Completion, execute
from benchmarks.runner.storage import write_json


@dataclass(frozen=True)
class Request:
    settings: Settings
    case: Case
    run: Run
    output: Path


def command(request: Request, workspace: Path, prompt: str) -> Command:
    """Use read-only shell access and expose only the treatment's direct MCP."""
    argv = [
        str(request.settings.codex),
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--strict-config",
        "--sandbox",
        "read-only",
        "--disable",
        "multi_agent",
        "--disable",
        "multi_agent_v2",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "-c",
        'web_search="disabled"',
        "--model",
        request.settings.model,
        "-c",
        f"model_reasoning_effort={json.dumps(request.settings.effort)}",
        "-C",
        str(workspace),
        "--json",
    ]
    if request.run.arm == "mcp+skill":
        argv += ["-c", f"mcp_servers.slang.command={json.dumps(str(request.settings.binary))}"]
    return Command([*argv, prompt], workspace, dict(os.environ), request.settings.timeout)


def run_one(request: Request) -> dict[str, object]:
    """Preserve every attempted run, including setup errors and timeouts."""
    request.output.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    record: dict[str, object] = {
        **asdict(request.run),
        "started_utc": started,
        "answer": "",
        "duration_seconds": None,
        "usage": dict.fromkeys(TOKEN_FIELDS),
    }
    try:
        record.update(_execute(request))
    except (OSError, ValueError, RuntimeError) as error:
        record.update(status="setup_failed", error=str(error))
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(request.output / "result.json", record)
    return record


def _execute(request: Request) -> dict[str, object]:
    workspace = request.output / "workspace"
    shutil.copytree(request.case.workspace, workspace)
    invocation = _prepare_invocation(request, workspace)
    completion = execute(invocation, request.output)
    trace = parse_trace(request.output / "trace.jsonl")
    write_public_trace(request.output / "public_trace.jsonl", trace)
    (request.output / "answer.txt").write_text(trace.answer)
    return _result(completion, trace)


def _prepare_invocation(request: Request, workspace: Path) -> Command:
    prompt = build_prompt(
        request.case.task.read_text(), request.run.arm, request.settings.skill.read_text()
    )
    (request.output / "prompt.txt").write_text(prompt)
    invocation = command(request, workspace, prompt)
    write_json(
        request.output / "invocation.json",
        {"argv": invocation.argv, "cwd": str(invocation.cwd), "timeout": invocation.timeout},
    )
    return invocation


def _result(completion: Completion, trace: Trace) -> dict[str, object]:
    return {
        "status": _status(completion, trace),
        "returncode": completion.returncode,
        "duration_seconds": completion.duration,
        "timed_out": completion.timed_out,
        "answer": trace.answer,
        "usage": trace.usage(),
        "usage_events": trace.usage_events,
        "completed_turns": trace.completed_turns,
        "parse_errors": trace.errors,
    }


def _status(completion: Completion, trace: Trace) -> str:
    if completion.timed_out:
        return "timeout"
    if completion.returncode:
        return "agent_failed"
    if trace.errors or not trace.completed_turns or not trace.answer:
        return "invalid_trace"
    return "completed"


def run_plan(plan: Plan, output: Path, jobs: int) -> None:
    """Submit the recorded schedule in order with bounded worker concurrency."""
    if jobs < 1:
        raise ValueError("jobs must be positive")
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for record in executor.map(run_one, _requests(plan, output)):
            print(f"{record['id']}: {record['status']}", flush=True)


def _requests(plan: Plan, output: Path) -> list[Request]:
    requests = [_request(plan, run, output) for run in plan.runs]
    if any(request.output.exists() for request in requests):
        raise FileExistsError("Output already contains a scheduled run; refusing to overwrite")
    return requests


def _request(plan: Plan, run: Run, output: Path) -> Request:
    case = next(case for case in plan.cases if case.id == run.case_id)
    destination = output / run.case_id / run.arm / f"rep_{run.repetition}"
    return Request(plan.settings, case, run, destination)
