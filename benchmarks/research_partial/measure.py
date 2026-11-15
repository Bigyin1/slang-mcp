"""Measure controlled source-list reductions against the release MCP server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.dataset import read_object
from benchmarks.research_partial.prepare import PROJECTS, WORKSPACE

ROOT = Path(__file__).resolve().parents[2]
SUBTREES = ("fifo_v3", "cva6_fifo_v3", "cc_stream_fifo", "cc_stream_fifo")
PACKAGES = ("axi_pkg.sv", "ariane_pkg.sv", "idma_pkg.sv", "floo_pkg.sv")
CHILDREN = ("fifo_v3.sv", "cva6_fifo_v3.sv", "cc_fifo.sv", "cc_fifo.sv")


@dataclass(frozen=True)
class Scenario:
    project: str
    name: str
    top: str
    target: str
    sources: tuple[str, ...]
    defines: dict[str, object]


def base_scenario(index: int) -> Scenario:
    workspace = WORKSPACE / PROJECTS[index]
    config = cast("dict[str, object]", read_object(workspace / "projects.json")[PROJECTS[index]])
    return Scenario(
        PROJECTS[index],
        "full",
        (workspace / "top_module.txt").read_text().strip(),
        SUBTREES[index],
        tuple((workspace / "source_files.f").read_text().splitlines()),
        cast("dict[str, object]", config["defines"]),
    )


def reduced_sources(scenario: Scenario) -> tuple[str, ...]:
    names = {scenario.target + ".sv", "cc_pkg.sv", "cc_fifo.sv"}
    return tuple(path for path in scenario.sources if Path(path).name in names)


def exclude(scenario: Scenario, filename: str) -> tuple[str, ...]:
    return tuple(path for path in scenario.sources if Path(path).name != filename)


def scenarios(index: int) -> list[Scenario]:
    base = base_scenario(index)
    return [
        base,
        replace(base, name="subtree_top", top=base.target),
        replace(base, name="reduced_subtree", top=base.target, sources=reduced_sources(base)),
        replace(base, name="missing_child", sources=exclude(base, CHILDREN[index])),
        replace(base, name="missing_package", sources=exclude(base, PACKAGES[index])),
    ]


async def timed_call(
    session: ClientSession, name: str, arguments: dict[str, object]
) -> dict[str, object]:
    start = perf_counter()
    result = await session.call_tool(name, arguments)
    return {
        "seconds": perf_counter() - start,
        "bytes": len(result.model_dump_json().encode()),
        "is_error": result.is_error,
        "data": result.structured_content,
        "text": [item.text for item in result.content if item.type == "text"]
        if result.is_error
        else [],
    }


def load_arguments(scenario: Scenario) -> dict[str, object]:
    workspace = WORKSPACE / scenario.project
    source_list = workspace / (scenario.name + ".f")
    source_list.write_text("\n".join(scenario.sources) + "\n")
    return {
        "source_file_lists": [str(source_list)],
        "include_directory_lists": [str(workspace / "include_directories.f")],
        "top_module": scenario.top,
        "defines": scenario.defines,
    }


async def measure(scenario: Scenario, repeat: int) -> dict[str, object]:
    # Pylint cannot follow the async context manager tuple binding.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(ROOT / "build/release/slang-mcp"), args=[])
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        results = await query_all(session, scenario)
    # pylint: enable=used-before-assignment
    return {
        "project": scenario.project,
        "scenario": scenario.name,
        "repeat": repeat,
        "top": scenario.top,
        "target": scenario.target,
        "sources": len(scenario.sources),
        "source_names": [
            str(Path(path).relative_to(WORKSPACE / scenario.project)) for path in scenario.sources
        ],
        "calls": results,
    }


async def query_all(session: ClientSession, scenario: Scenario) -> dict[str, object]:
    results = {"load": await timed_call(session, "project_load", load_arguments(scenario))}
    for name, arguments in queries(scenario):
        results[name] = await timed_call(session, name, arguments)
    return cast("dict[str, object]", results)


def queries(scenario: Scenario) -> list[tuple[str, dict[str, object]]]:
    return [
        ("get_hierarchy", {"max_depth": 2}),
        ("get_ports", {"sv_module": scenario.target, "limit": 100}),
        ("get_parameters", {"target": scenario.target, "limit": 100}),
        ("list_instances", {"sv_module": scenario.target, "limit": 100}),
        ("summarize_diagnostics_by_code", {"limit": 100}),
    ]


async def main() -> None:
    output: dict[str, object] = {
        "binary_sha256": hashlib.sha256(
            (ROOT / "build/release/slang-mcp").read_bytes()
        ).hexdigest(),
        "platform": platform.platform(),
        "runs": [],
    }
    runs = cast("list[dict[str, object]]", output["runs"])
    for index in range(len(PROJECTS)):
        for scenario in scenarios(index):
            for repeat in range(3):
                print(scenario.project, scenario.name, repeat, flush=True)
                runs.append(await measure(scenario, repeat))
                (Path(__file__).parent / "raw.json").write_text(
                    json.dumps(output, separators=(",", ":")) + "\n"
                )


if __name__ == "__main__":
    asyncio.run(main())
