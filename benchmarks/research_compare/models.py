"""Load the explicit, externally frozen execution schedule."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Arm = Literal["text-only", "mcp+skill"]


@dataclass(frozen=True)
class Settings:
    codex: Path
    binary: Path
    skill: Path
    model: str
    effort: str
    timeout: float


@dataclass(frozen=True)
class Case:
    id: str
    workspace: Path
    task: Path


@dataclass(frozen=True)
class Run:
    id: str
    case_id: str
    arm: Arm
    repetition: int


@dataclass(frozen=True)
class Plan:
    settings: Settings
    cases: tuple[Case, ...]
    runs: tuple[Run, ...]


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise ValueError(f"Invalid schedule identifier: {value!r}")
    if value in {".", ".."}:
        raise ValueError(f"Invalid schedule identifier: {value!r}")
    return value


def _run(value: dict[str, object]) -> Run:
    if (arm := value["arm"]) not in {"text-only", "mcp+skill"}:
        raise ValueError(f"Unknown arm: {arm!r}")
    repetition = value["repetition"]
    if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
        raise ValueError("repetition must be a positive integer")
    return Run(
        _identifier(value["id"]),
        _identifier(value["case_id"]),
        arm,
        repetition,
    )


def load_plan(path: Path) -> Plan:
    """Read manifest paths as absolute paths; preserve the supplied run order."""
    data = json.loads(path.read_text())
    settings = Settings(
        Path(data["codex"]).resolve(),
        Path(data["binary"]).resolve(),
        Path(data["skill"]).resolve(),
        data["model"],
        data["effort"],
        float(data["timeout"]),
    )
    cases = tuple(
        Case(_identifier(case["id"]), Path(case["workspace"]), Path(case["task"]))
        for case in data["cases"]
    )
    plan = Plan(settings, cases, tuple(_run(run) for run in data["runs"]))
    _validate(plan)
    return plan


def _validate(plan: Plan) -> None:
    if plan.settings.timeout <= 0:
        raise ValueError("timeout must be positive")
    _validate_cases(plan.cases)
    _validate_runs(plan.runs, {case.id for case in plan.cases})


def _validate_cases(cases: tuple[Case, ...]) -> None:
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case identifiers")
    if any(not case.workspace.is_absolute() or not case.task.is_absolute() for case in cases):
        raise ValueError("Case workspace and task paths must be absolute")


def _validate_runs(runs: tuple[Run, ...], case_ids: set[str]) -> None:
    if len({run.id for run in runs}) != len(runs):
        raise ValueError("Duplicate run identifiers")
    if len({(run.case_id, run.arm, run.repetition) for run in runs}) != len(runs):
        raise ValueError("Duplicate case/arm/repetition")
    if any(run.case_id not in case_ids for run in runs):
        raise ValueError("Run references an unknown case")
