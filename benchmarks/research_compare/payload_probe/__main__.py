"""Replay saved bulk queries into a fresh output directory without model calls."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit_freeze import (
    FROZEN_REVISION,
    Snapshot,
    frozen_plan,
    load_snapshot,
)
from benchmarks.research_compare.audit_integrity import binary_audit, digest, workspace_audit
from benchmarks.research_compare.models import Plan
from benchmarks.research_compare.payload_probe.common import Query, comparison
from benchmarks.research_tools.transport import Recorder
from benchmarks.runner.storage import write_json

DIRECTORY = Path(__file__).parent


def _queries(snapshot: Snapshot) -> tuple[Query, ...]:
    return tuple(
        _query(object_dict(data), frozen_plan(snapshot))
        for data in json.loads((DIRECTORY / "queries.json").read_text())
    )


def _query(data: dict[str, object], plan: Plan) -> Query:
    return Query(
        str(data["case"]),
        _rebased(
            object_dict(data["load_arguments"]),
            next(case.workspace for case in plan.cases if case.id == data["case"]),
        ),
        object_dict(data["baseline_arguments"]),
        str(data["empty_filter"]),
        str(data["retained_section"]),
    )


def _rebased(arguments: dict[str, object], workspace: Path) -> dict[str, object]:
    result = dict(arguments)
    for key in ("source_files", "include_directories"):
        values = result[key]
        if not isinstance(values, list):
            raise TypeError("Saved source/include list is malformed")
        result[key] = [_absolute(str(value), workspace) for value in values]
    return result


def _absolute(value: str, workspace: Path) -> str:
    if Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("Saved probe paths must stay relative to the frozen workspace")
    return str(workspace / value)


async def _call(recorder: Recorder, tool: str, arguments: dict[str, object]) -> dict[str, object]:
    answer = await recorder.call(tool, arguments)
    if recorder.records[-1]["is_error"]:
        raise RuntimeError(f"Compiler-only probe call failed: {tool}")
    return answer


async def _compare(recorder: Recorder, query: Query) -> dict[str, object]:
    await _call(recorder, "project_load", query.load_arguments)
    baseline = await _call(recorder, "list_instance_facts", query.baseline_arguments)
    selected = await _call(
        recorder, "list_instance_facts", {**query.baseline_arguments, query.empty_filter: []}
    )
    return comparison(query, baseline, selected)


def _input_audits(snapshot: Snapshot, queries: tuple[Query, ...]) -> dict[str, object]:
    return {
        query.case: workspace_audit(
            next(case.workspace for case in frozen_plan(snapshot).cases if case.id == query.case),
            object_dict(object_dict(snapshot.json("inputs.json")[query.case])["files"]),
        )
        for query in queries
    }


async def run(snapshot: Snapshot, queries: tuple[Query, ...], output: Path) -> dict[str, object]:
    # Pylint cannot follow the SDK async context-manager tuple binding.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(
                command=str(frozen_plan(snapshot).settings.binary), cwd=str(snapshot.root)
            )
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        return await _record(session, queries, output)
    # pylint: enable=used-before-assignment


async def _record(
    session: ClientSession, queries: tuple[Query, ...], output: Path
) -> dict[str, object]:
    recorder = Recorder(session)
    try:
        return {
            "comparisons": [await _compare(recorder, query) for query in queries],
            "semantic_calls": len(recorder.records),
        }
    finally:
        recorder.save(output / "calls.json")


def _provenance(snapshot: Snapshot, queries: tuple[Query, ...]) -> dict[str, object]:
    evidence: dict[str, object] = {
        "revision": snapshot.revision,
        "server_cwd": str(snapshot.root),
        "queries_sha256": digest(DIRECTORY / "queries.json"),
        "binary": binary_audit(
            frozen_plan(snapshot).settings.binary, snapshot.json("protocol.json")["server_sha256"]
        ),
        "inputs_before": _input_audits(snapshot, queries),
    }
    if not object_dict(evidence["binary"])["valid"] or not all(
        object_dict(value).get("valid") for value in object_dict(evidence["inputs_before"]).values()
    ):
        raise RuntimeError("Frozen binary or source inputs differ")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = load_snapshot(DIRECTORY.parent, FROZEN_REVISION)
    queries = _queries(snapshot)
    args.output.mkdir(parents=True)
    write_json(args.output / "provenance.json", _provenance(snapshot, queries))
    result = asyncio.run(asyncio.wait_for(run(snapshot, queries, args.output), timeout=60))
    result.update(
        encoding="UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False",
        model_calls=0,
        inputs_after=_input_audits(snapshot, queries),
        limitation="Query-level payload counterfactual; no worker token/time savings established",
    )
    write_json(args.output / "results.json", result)


if __name__ == "__main__":
    main()
