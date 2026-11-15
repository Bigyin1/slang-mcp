"""Run a previously frozen research protocol without generating a schedule."""

import argparse
from pathlib import Path

from benchmarks.research_compare.models import load_plan
from benchmarks.research_compare.runner import run_plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    arguments = parser.parse_args()
    plan = load_plan(arguments.manifest)
    arguments.output.mkdir(parents=True, exist_ok=True)
    with (arguments.output / "manifest.json").open("xb") as destination:
        destination.write(arguments.manifest.read_bytes())
    run_plan(plan, arguments.output, arguments.jobs)


if __name__ == "__main__":
    main()
