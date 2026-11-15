"""Reproduce semantic-diff usage counts and isolated copied-FIFO experiments."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.research_tools.transport import Recorder

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = Path(__file__).resolve().parent
FIFO_ROOT = Path(
    "/private/tmp/slang-partial-research/axi_fifo_core/rtl/.bender/git/checkouts/"
    "common_cells-3e2fcccecd7aee7b"
)


def read_object(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text()))


def attempt_calls(path: Path) -> list[dict[str, object]]:
    calls = path / "tool_calls.json"
    if calls.exists():
        return cast("list[dict[str, object]]", json.loads(calls.read_text()))
    trace = path / "trace.jsonl"
    if not trace.exists():
        return []
    return [
        item["data"]
        for line in trace.read_text().splitlines()
        if (item := json.loads(line)).get("type") == "tool.execution_start"
    ]


def usage_record(path: Path) -> dict[str, object]:
    metadata = read_object(path / "metadata.json") if (path / "metadata.json").exists() else {}
    calls = attempt_calls(path)
    names = Counter(str(item["mcpToolName"]) for item in calls if item.get("mcpToolName"))
    return {
        "path": str(path.relative_to(ROOT)),
        "completed": metadata.get("completed"),
        "execution_status": metadata.get("execution_status"),
        "call_ids": [item.get("toolCallId") for item in calls],
        "mcp_tools": dict(sorted(names.items())),
        "mcp_calls": sum(names.values()),
    }


def historical_usage() -> dict[str, object]:
    attempts = sorted(
        {
            file.parent
            for directory in ("benchmark_results", "benchmark_smoke")
            for pattern in ("tool_calls.json", "trace.jsonl")
            for file in (ROOT / directory).rglob(pattern)
        }
    )
    records = [usage_record(path) for path in attempts]
    return {
        "attempts": records,
        "native_workloads": native_usage(),
        "scripted_probes": scripted_usage(),
    }


def native_usage() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted((ROOT / "benchmarks/research_agents").glob("*.calls.jsonl")):
        requests = [json.loads(line)["request"] for line in path.read_text().splitlines()]
        names = Counter(item["name"] for item in requests if item["method"] == "tools/call")
        records.append({"path": str(path.relative_to(ROOT)), "tools": dict(names)})
    return records


def scripted_usage() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted((ROOT / "benchmarks/research_tools/results").glob("*.calls.json")):
        calls = cast("list[dict[str, object]]", json.loads(path.read_text()))
        names = Counter(str(item["tool"]) for item in calls)
        records.append({"path": str(path.relative_to(ROOT)), "tools": dict(names)})
    return records


def replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f"Expected exactly one fixture edit target: {before}")
    return source.replace(before, after)


async def compare_variant(recorder: Recorder, source: Path, text: str) -> None:
    await recorder.call(
        "project_load_partial",
        {
            "top_module": "fifo_v3",
            "source_files": [str(source)],
            "include_directories": [str(FIFO_ROOT / "include")],
            "defines": {"COMMON_CELLS_ASSERTS_OFF": None},
        },
    )
    source.write_text(text)
    await recorder.call("project_reload", {})
    await recorder.call("semantic_diff", {"limit": 500})


def variants(original: str) -> dict[str, str]:
    return {
        "body_only": replace_once(original, "status_cnt_q + 1;", "status_cnt_q + 2;"),
        "parameter_default": replace_once(original, "DEPTH        = 8,", "DEPTH        = 16,"),
        "port_direction": replace_once(
            original, "input  logic  testmode_i,", "output logic  testmode_i,"
        ),
    }


async def run_variants(recorder: Recorder, source: Path) -> None:
    original = (FIFO_ROOT / "src/fifo_v3.sv").read_text()
    for name, text in variants(original).items():
        source.write_text(original)
        await compare_variant(recorder, source, text)
        recorder.records[-1]["experiment"] = name
    source.write_text(original)
    await compare_variant(recorder, source, original)
    await scope_switch(recorder, source)


async def scope_switch(recorder: Recorder, source: Path) -> None:
    source.with_suffix(".f").write_text(str(source) + "\n")
    source.with_suffix(".includes").write_text(str(FIFO_ROOT / "include") + "\n")
    await recorder.call(
        "project_load",
        {
            "top_module": "fifo_v3",
            "source_file_lists": [str(source.with_suffix(".f"))],
            "include_directory_lists": [str(source.with_suffix(".includes"))],
            "defines": {"COMMON_CELLS_ASSERTS_OFF": None},
        },
    )
    await recorder.call("semantic_diff", {"limit": 500})
    recorder.records[-1]["experiment"] = "same_top_fragment_to_full"


async def probe(directory: Path) -> list[dict[str, object]]:
    async with (
        stdio_client(
            StdioServerParameters(
                command=str(ROOT / "build/release/slang-mcp"), args=["--tool-profile", "full"]
            )
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        recorder = Recorder(session)
        await run_variants(recorder, directory / "fifo_v3.sv")
        return recorder.records


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    usage = historical_usage()
    (DESTINATION / "diff_usage.json").write_text(json.dumps(usage, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="slang-diff-audit-") as temporary:
        records = asyncio.run(probe(Path(temporary)))
    provenance = {
        "fixture": str(FIFO_ROOT / "src/fifo_v3.sv"),
        "fixture_lock": "benchmarks/cases/axi-v0.39.9.Bender.lock",
        "fixture_revision": "1281545696eb3fcba50ec5b4275993476a3c710e",
        "fixture_edits": {
            "body_only": ["status_cnt_q + 1;", "status_cnt_q + 2;"],
            "parameter_default": ["DEPTH        = 8,", "DEPTH        = 16,"],
            "port_direction": ["input  logic  testmode_i,", "output logic  testmode_i,"],
        },
        "fixture_sha256": sha256(FIFO_ROOT / "src/fifo_v3.sv"),
        "binary_sha256": sha256(ROOT / "build/release/slang-mcp"),
        "records": records,
    }
    (DESTINATION / "diff_probe.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
