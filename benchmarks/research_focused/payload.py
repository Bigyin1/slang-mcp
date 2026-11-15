"""Compare inspection projections against identical full responses on pinned projects."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from benchmarks.research_partial.measure import base_scenario, load_arguments
from benchmarks.research_partial.prepare import PROJECTS


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def summary(result: CallToolResult) -> dict[str, object]:
    payload = encoded(result.model_dump(mode="json", by_alias=True, exclude_none=True))
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def projection_hash(full: CallToolResult, selected: CallToolResult) -> str:
    data = cast("dict[str, object]", full.structured_content)
    projection = {
        key: value for key, value in data.items() if key in {"parameters", "definition", "instance"}
    }
    if selected.structured_content != projection:
        raise RuntimeError("Selected response differs from full projection: inspection")
    return hashlib.sha256(encoded(projection)).hexdigest()


async def compare(
    session: ClientSession, name: str, arguments: dict[str, object]
) -> dict[str, object]:
    full = await session.call_tool(name, arguments)
    selected = await session.call_tool(name, {**arguments, "fields": ["parameters"]})
    if full.is_error or selected.is_error:
        raise RuntimeError(f"Inspection failed: {name} {arguments}")
    return {
        "tool": name,
        "arguments": arguments,
        "full": summary(full),
        "selected": summary(selected),
        "projection_equal": True,
        "projection_sha256": projection_hash(full, selected),
    }


async def project_probe(session: ClientSession, index: int) -> dict[str, object]:
    scenario = base_scenario(index)
    loaded = await session.call_tool("project_load", load_arguments(scenario))
    if loaded.is_error:
        raise RuntimeError(f"Load failed: {scenario.project}")
    return {
        "project": scenario.project,
        "load": summary(loaded),
        "comparisons": [
            await compare(session, "inspect_module", {"sv_module": scenario.top, "limit": 100}),
            await compare(
                session, "inspect_instance", {"instance_path": scenario.top, "limit": 100}
            ),
        ],
    }


async def run(binary: Path) -> dict[str, object]:
    # Pylint cannot follow the async context-manager tuple binding.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(binary), args=["--tool-profile", "full"])
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        return {
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "encoding": (
                "UTF-8 canonical JSON; sorted keys; compact separators; "
                "SDK result aliases; nulls excluded"
            ),
            "runs": [await project_probe(session, index) for index in range(len(PROJECTS))],
        }
    # pylint: enable=used-before-assignment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    options.output.write_text(
        json.dumps(asyncio.run(run(options.binary.resolve())), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
