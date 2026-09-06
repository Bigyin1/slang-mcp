"""Command-line controller: validate, list, run and report."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

from benchmarks.dataset import load_cases, read_object
from benchmarks.models import MODES, Case, Settings
from benchmarks.reporting.output import generate_report
from benchmarks.runner.experiment import Experiment, run_plan
from benchmarks.runner.reproduction import snapshot_sources
from benchmarks.runner.schedule import Selection, schedule, select_cases
from benchmarks.runner.storage import fingerprint, metadata, write_json
from benchmarks.validation import validate, validate_builds


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("validate", "list", "run", "report"))
    result.add_argument("--profile", choices=("smoke", "pilot", "full"), default="smoke")
    result.add_argument("--model", default="auto")
    result.add_argument("--repetitions", type=int)
    result.add_argument("--timeout", type=float, default=300)
    result.add_argument("--seed", type=int, default=20260905)
    result.add_argument("--mode", choices=MODES)
    result.add_argument("--category")
    result.add_argument("--case", action="append")
    result.add_argument("--output", type=Path, default=Path("benchmark_results"))
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--force", action="store_true")
    result.add_argument("--builds", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "validate":
        print(json.dumps(validate_builds() if args.builds else validate(), indent=2))
    elif args.command == "report":
        _terminal(generate_report(args.output.resolve()), args.output)
    else:
        _experiment(args)


def _settings(args: argparse.Namespace) -> Settings:
    return Settings(
        model=args.model,
        repetitions=args.repetitions
        if args.repetitions is not None
        else (1 if args.profile == "smoke" else 3),
        timeout=args.timeout,
        seed=args.seed,
        profile=args.profile,
    )


def _experiment(args: argparse.Namespace) -> None:
    settings = _settings(args)
    selection = Selection(args.mode, args.category, tuple(args.case or ()))
    cases = select_cases(load_cases(), settings, selection)
    plan = _plan(cases, settings, selection)
    if args.command == "list" or args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _manifest(output, settings, plan)
    run_plan(
        Experiment(settings, selection, output, args.force),
        cases,
    )
    _terminal(generate_report(output), output)


def _plan(
    cases: tuple[Case, ...], settings: Settings, selection: Selection
) -> list[dict[str, object]]:
    lookup = {case.id: case for case in cases}
    return [
        {
            **asdict(key),
            "category": lookup[key.case_id].category,
            "project": lookup[key.case_id].project,
        }
        for key in schedule(cases, settings, selection)
    ]


def _manifest(output: Path, settings: Settings, plan: list[dict[str, object]]) -> None:
    path = output / "experiment.json"
    if path.exists():
        existing = read_object(path)
        if existing["fingerprint"] != fingerprint(settings) or existing["planned"] != plan:
            raise ValueError("Experiment differs; use a new --output directory")
    else:
        snapshot_sources(output)
        write_json(
            path,
            {
                **metadata(settings),
                "planned": plan,
                "seed": settings.seed,
                "effective_effort": None if settings.model == "auto" else settings.effort,
                "isolation": "fresh workspace; shared system CLI profile; no OS sandbox",
            },
        )


def _terminal(summary: dict[str, object], output: Path) -> None:
    print(f"Runs: {summary['completed']}/{summary['planned']}")
    for mode, data in cast("dict[str, dict[str, object]]", summary["modes"]).items():
        print(
            f"{mode}: {data['correct']}/{data['evaluable']}; "
            f"failures={data['infrastructure_failures']}"
        )
    print(f"Report: {output / 'reports/benchmark_report.md'}")
    print(f"Raw: {output / 'raw'}")
