"""Validate the native fragment API against prepared pinned real RTL."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.dataset import read_object
from benchmarks.research_partial.archive import object_dict
from benchmarks.research_partial.measure import ROOT, Scenario, exclude, scenarios, timed_call
from benchmarks.research_partial.prepare import WORKSPACE

PORT_COUNT = 11


def arguments(scenario: Scenario, sources: tuple[str, ...]) -> dict[str, object]:
    config = object_dict(
        read_object(WORKSPACE / scenario.project / "projects.json")[scenario.project]
    )
    return {
        "source_files": list(sources),
        "top_module": scenario.top,
        "include_directories": [
            str(WORKSPACE / scenario.project / str(path))
            for path in cast("list[str]", config["include_directories"])
        ],
        "defines": scenario.defines,
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(result: dict[str, object], expected_width: int | None) -> None:
    require(not bool(result["is_error"]), "get_ports unexpectedly failed")
    ports = cast("list[dict[str, object]]", object_dict(result["data"])["items"])
    require(len(ports) == PORT_COUNT, "FIFO wrapper port declarations disappeared")
    usage = next(port for port in ports if port["name"] == "usage_o")
    require(usage["width"] == expected_width, "usage_o differs from source expectation")


def validate_metadata(loaded: dict[str, object]) -> None:
    for key, expected in {
        "analysis_scope": "fragment",
        "parameter_context": "standalone_top",
        "completeness": "not_verified",
    }.items():
        require(object_dict(loaded["data"])[key] == expected, "fragment metadata missing")


async def load_case(
    session: ClientSession, scenario: Scenario, sources: tuple[str, ...]
) -> dict[str, object]:
    loaded = await timed_call(session, "project_load_partial", arguments(scenario, sources))
    require(not bool(loaded["is_error"]), "fragment load unexpectedly failed")
    validate_metadata(loaded)
    return {
        "load": loaded,
        "ports": await timed_call(session, "get_ports", {"sv_module": scenario.top}),
        "hierarchy": await timed_call(session, "get_hierarchy", {"max_depth": 2}),
        "diagnostics": await timed_call(session, "summarize_diagnostics_by_code", {}),
        "info": await timed_call(session, "project_info", {}),
    }


def validate_case(result: dict[str, object], omission: str) -> None:
    validate(object_dict(result["ports"]), None if omission == "cc_pkg.sv" else 4)
    errors = object_dict(object_dict(result["load"])["data"])["diagnostic_error_count"]
    require((errors == 0) == (omission == ""), "dependency omission diagnostics lost")
    root = cast(
        "list[dict[str, object]]", object_dict(object_dict(result["hierarchy"])["data"])["roots"]
    )[0]
    require(bool(root["children"]) == (omission != "cc_fifo.sv"), "child completeness differs")


async def idma_cases(session: ClientSession) -> list[dict[str, object]]:
    scenario = scenarios(2)[2]
    results: list[dict[str, object]] = []
    for omission in ("", "cc_fifo.sv", "cc_pkg.sv", ""):
        result = await load_case(session, scenario, exclude(scenario, omission))
        validate_case(result, omission)
        results.append({"project": scenario.project, "omitted": omission, "calls": result})
    return results


async def cva_case(session: ClientSession) -> dict[str, object]:
    scenario = scenarios(1)[2]
    result = await load_case(session, scenario, scenario.sources)
    validate(object_dict(result["ports"]), 3)
    require(
        object_dict(object_dict(result["load"])["data"])["diagnostic_error_count"] == 0,
        "isolated CVA6 FIFO has unexpected errors",
    )
    return {"project": scenario.project, "omitted": "", "calls": result}


async def main() -> None:
    # Pylint cannot follow the async context manager tuple binding.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(ROOT / "build/release/slang-mcp"), args=[])
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        results = [*await idma_cases(session), await cva_case(session)]
    # pylint: enable=used-before-assignment
    (Path(__file__).parent / "native_api.json").write_text(
        json.dumps(
            {
                "binary_sha256": hashlib.sha256(
                    (ROOT / "build/release/slang-mcp").read_bytes()
                ).hexdigest(),
                "assertions_passed": True,
                "cases": results,
                "timing_note": "Validation only; concurrent checks may affect latency.",
            },
            separators=(",", ":"),
        )
        + "\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
