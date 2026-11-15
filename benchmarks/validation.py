"""Corpus checks independent of agent/API calls and optional compiler preflight."""

from __future__ import annotations

import asyncio
import tempfile
from collections import Counter
from pathlib import Path
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.dataset import ROOT, load_cases, read_object
from benchmarks.runner.isolation import server_binary
from benchmarks.runner.projects import prepare_project

CORPUS_SIZE = 19
PILOT_SIZE = 10


def validate() -> dict[str, object]:
    cases = load_cases()
    projects = read_object(ROOT / "cases/projects.json")
    for case in cases:
        if case.project not in projects:
            raise ValueError(f"Unknown project: {case.project}")
    if len(cases) != CORPUS_SIZE or sum(case.pilot for case in cases) != PILOT_SIZE:
        raise ValueError("Expected curated 19-case corpus and 10-case pilot")
    return {
        "cases": len(cases),
        "pilot": sum(case.pilot for case in cases),
        "categories": dict(Counter(case.category for case in cases)),
    }


def validate_builds() -> dict[str, object]:
    results: dict[str, object] = {}
    for name in read_object(ROOT / "cases/projects.json"):
        with tempfile.TemporaryDirectory(prefix="slang-validate-", dir="/private/tmp") as directory:
            results[name] = _validate_build(name, Path(directory))
    return results


def _validate_build(name: str, workspace: Path) -> dict[str, object]:
    prepare_project(name, workspace)
    return asyncio.run(_compile_workspace(name, workspace))


async def _compile_workspace(name: str, workspace: Path) -> dict[str, object]:
    # Pylint cannot follow the async context manager's tuple assignment.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(server_binary()), args=["--tool-profile", "full"])
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "project_load",
            {
                "source_file_lists": [str(workspace / "source_files.f")],
                "include_directory_lists": [str(workspace / "include_directories.f")],
                "top_module": (workspace / "top_module.txt").read_text(encoding="utf-8").strip(),
                "defines": cast(
                    "dict[str, object]", read_object(workspace / "projects.json")[name]
                )["defines"],
            },
        )
    # pylint: enable=used-before-assignment
    if result.is_error or result.structured_content is None:
        raise RuntimeError(f"Native compiler validation failed: {result}")
    return {
        "errors": result.structured_content["diagnostic_error_count"],
        "sources": result.structured_content["source_file_count"],
    }
