"""Resume a frozen execution schedule without altering prior attempts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchmarks.adapters.copilot import verify_version
from benchmarks.models import Case, RunKey, Settings
from benchmarks.runner.run import RunRequest, run_one
from benchmarks.runner.schedule import Selection, schedule
from benchmarks.runner.storage import attempt_directory, fingerprint, reusable


@dataclass(frozen=True)
class Experiment:
    settings: Settings
    selection: Selection
    output: Path
    force: bool = False


def run_plan(experiment: Experiment, cases: tuple[Case, ...]) -> None:
    for index, key in enumerate(schedule(cases, experiment.settings, experiment.selection), 1):
        if _already_complete(experiment, key):
            continue
        verify_version(experiment.settings)
        request = _request(experiment, cases, key)
        if _execute_request(request, index):
            print(
                "CLI/model infrastructure blocker; stopping. Completed attempts retained.",
                flush=True,
            )
            break


def _already_complete(experiment: Experiment, key: RunKey) -> bool:
    return not experiment.force and any(
        reusable(path, fingerprint(experiment.settings))
        for path in (experiment.output / "raw" / key.slug).glob("attempt_*/metadata.json")
    )


def _request(experiment: Experiment, cases: tuple[Case, ...], key: RunKey) -> RunRequest:
    return RunRequest(
        next(case for case in cases if case.id == key.case_id),
        key,
        experiment.settings,
        fingerprint(experiment.settings),
        attempt_directory(experiment.output / "raw" / key.slug),
    )


def global_failure(record: dict[str, object], output: Path) -> bool:
    if record["execution_status"] not in {"AGENT_FAILURE", "MCP_FAILURE"}:
        return False
    error = (output / "stderr.txt").read_text()
    return any(
        fragment in error
        for fragment in ("No authentication", "not available", "not support", "quota", "rate limit")
    )


def _execute_request(request: RunRequest, index: int) -> bool:
    record = run_one(request)
    print(f"[{index}] {request.key.slug}: {record['execution_status']}", flush=True)
    return global_failure(record, request.output)
