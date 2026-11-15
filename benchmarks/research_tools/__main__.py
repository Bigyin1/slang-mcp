"""Run with uv run --project benchmarks python -m benchmarks.research_tools."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.dataset import read_object
from benchmarks.research_tools.fifo import fifo_queries, source_evidence
from benchmarks.research_tools.study import study
from benchmarks.research_tools.transport import Recorder
from benchmarks.runner.projects import prepare_project


async def execute(workspace: Path, output: Path, binary: Path) -> None:
    # Pylint cannot follow SDK async context manager tuple assignment.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(binary), args=["--tool-profile", "full"])
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        await record_workspace(Recorder(session), workspace, output)
    # pylint: enable=used-before-assignment


async def record_workspace(recorder: Recorder, workspace: Path, output: Path) -> None:
    config = cast(
        "dict[str, object]", next(iter(read_object(workspace / "projects.json").values()))
    )
    await recorder.call(
        "project_load",
        {
            "source_file_lists": [str(workspace / "source_files.f")],
            "include_directory_lists": [str(workspace / "include_directories.f")],
            "top_module": str(cast("list[str]", config["top_modules"])[0]),
            "defines": config["defines"],
        },
    )
    results = await study(recorder, cast("list[str]", config["top_modules"])[0])
    results["fifo"] = await fifo_queries(recorder)
    results["source_evidence"] = source_evidence(workspace)
    recorder.save(output.with_suffix(".calls.json"))
    output.with_suffix(".checks.json").write_text(json.dumps(results, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=Path("build/release/slang-mcp"))
    options = parser.parse_args()
    options.workspace.mkdir(parents=True, exist_ok=True)
    if not (options.workspace / "projects.json").exists():
        prepare_project(options.project, options.workspace)
    asyncio.run(execute(options.workspace.resolve(), options.output, options.binary.resolve()))


if __name__ == "__main__":
    main()
