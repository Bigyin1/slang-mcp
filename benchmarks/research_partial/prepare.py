"""Materialize pinned projects using the existing benchmark preparation path."""

from pathlib import Path

from benchmarks.runner.projects import prepare_project

WORKSPACE = Path("/private/tmp/slang-partial-research")
PROJECTS = ("axi_fifo_core", "cva6_cv64a6_imafdc_sv39", "idma_desc64", "floonoc_nw_2tiles")


def main() -> None:
    for name in PROJECTS:
        workspace = WORKSPACE / name
        workspace.mkdir(parents=True, exist_ok=True)
        if not (workspace / "projects.json").exists():
            prepare_project(name, workspace)
        print(name, flush=True)


if __name__ == "__main__":
    main()
