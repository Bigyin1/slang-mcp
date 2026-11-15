"""Reproduce two bulk queries; no model calls and no experiment-worker reruns."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
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
from benchmarks.research_compare.audit_integrity import binary_audit, workspace_audit
from benchmarks.research_tools.transport import Recorder
from benchmarks.runner.storage import write_json

DIRECTORY = Path(__file__).parent


@dataclass(frozen=True)
class Scenario:
    case: str
    line: int
    empty_filter: str
    retained_section: str


SCENARIOS = (
    Scenario("idma_state", 24, "port_names", "parameters"),
    Scenario("floo_config", 88, "parameter_names", "connections"),
)


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _observed(scenario: Scenario) -> tuple[dict[str, object], dict[str, object]]:
    path = (
        Path("/private/tmp/slang-compare/runs")
        / scenario.case
        / "mcp+skill/rep_1/public_trace.jsonl"
    )
    events = [object_dict(json.loads(line)) for line in path.read_text().splitlines()]
    loads = [
        object_dict(event.get("item"))
        for event in events
        if event.get("type") == "item.completed"
        and object_dict(event.get("item")).get("tool") == "project_load"
    ]
    return object_dict(loads[0]["arguments"]), object_dict(
        object_dict(events[scenario.line - 1]["item"])["arguments"]
    )


def _load_arguments(scenario: Scenario, snapshot: Snapshot) -> dict[str, object]:
    workspace = next(
        case.workspace for case in frozen_plan(snapshot).cases if case.id == scenario.case
    )
    previous = Path("/private/tmp/slang-compare/runs") / scenario.case / "mcp+skill/rep_1/workspace"
    return _rebased(_observed(scenario)[0], previous, workspace)


def _rebased(arguments: dict[str, object], previous: Path, workspace: Path) -> dict[str, object]:
    for key in ("source_files", "include_directories"):
        values = arguments[key]
        if not isinstance(values, list):
            raise TypeError("Observed project path list is malformed")
        arguments[key] = [
            str(workspace / Path(str(value)).relative_to(previous)) for value in values
        ]
    return arguments


def _projection(answer: dict[str, object], section: str) -> dict[str, object]:
    items = answer["items"]
    if not isinstance(items, list):
        raise TypeError("Bulk result items are malformed")
    return {
        "total_count": answer["total_count"],
        "truncated": answer["truncated"],
        "items": [{"instance": item["instance"], section: item[section]} for item in items],
    }


def _metrics(answer: dict[str, object]) -> dict[str, object]:
    return {
        "structured_bytes": len(encoded(answer)),
        "structured_sha256": hashlib.sha256(encoded(answer)).hexdigest(),
    }


async def _compare(recorder: Recorder, scenario: Scenario, snapshot: Snapshot) -> dict[str, object]:
    await _call(recorder, "project_load", _load_arguments(scenario, snapshot))
    baseline = await _call(recorder, "list_instance_facts", _observed(scenario)[1])
    selected = await _call(
        recorder, "list_instance_facts", {**_observed(scenario)[1], scenario.empty_filter: []}
    )
    if _projection(baseline, scenario.retained_section) != _projection(
        selected, scenario.retained_section
    ):
        raise RuntimeError("Retained requested facts changed")
    return {
        "case": scenario.case,
        "observed_public_trace_line": scenario.line,
        "empty_filter": scenario.empty_filter,
        "retained_section": scenario.retained_section,
        "retained_projection_equal": True,
        "baseline": _metrics(baseline),
        "selected": _metrics(selected),
        "retained_projection_sha256": hashlib.sha256(
            encoded(_projection(baseline, scenario.retained_section))
        ).hexdigest(),
    }


async def _call(recorder: Recorder, tool: str, arguments: dict[str, object]) -> dict[str, object]:
    answer = await recorder.call(tool, arguments)
    if recorder.records[-1]["is_error"]:
        raise RuntimeError(f"Compiler-only probe call failed: {tool}")
    return answer


def _input_audits(snapshot: Snapshot) -> dict[str, object]:
    return {
        scenario.case: workspace_audit(
            next(
                case.workspace for case in frozen_plan(snapshot).cases if case.id == scenario.case
            ),
            object_dict(object_dict(snapshot.json("inputs.json")[scenario.case])["files"]),
        )
        for scenario in SCENARIOS
    }


async def run(snapshot: Snapshot) -> dict[str, object]:
    # Pylint cannot follow the SDK async context-manager tuple binding.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(frozen_plan(snapshot).settings.binary))
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        recorder = Recorder(session)
        try:
            return {
                "comparisons": [
                    await _compare(recorder, scenario, snapshot) for scenario in SCENARIOS
                ]
            }
        finally:
            recorder.save(DIRECTORY / "calls.json")
    # pylint: enable=used-before-assignment


def main() -> None:
    if any(
        (DIRECTORY / name).exists() for name in ("calls.json", "provenance.json", "results.json")
    ):
        raise FileExistsError("Probe already has recorded evidence; refusing to overwrite")
    snapshot = load_snapshot(DIRECTORY.parent, FROZEN_REVISION)
    provenance = {
        "revision": snapshot.revision,
        "binary": binary_audit(
            frozen_plan(snapshot).settings.binary, snapshot.json("protocol.json")["server_sha256"]
        ),
        "inputs_before": _input_audits(snapshot),
        "frozen_input_hashes": {
            scenario.case: object_dict(snapshot.json("inputs.json")[scenario.case])["files"]
            for scenario in SCENARIOS
        },
    }
    if not object_dict(provenance["binary"])["valid"]:
        raise RuntimeError("Frozen binary differs")
    if not all(
        object_dict(value).get("valid")
        for value in object_dict(provenance["inputs_before"]).values()
    ):
        raise RuntimeError("Frozen source inputs differ")
    write_json(DIRECTORY / "provenance.json", provenance)
    result = asyncio.run(asyncio.wait_for(run(snapshot), timeout=60))
    result.update(
        encoding="UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False",
        model_calls=0,
        semantic_calls=6,
        inputs_after=_input_audits(snapshot),
        limitation="Query-level payload counterfactual; no worker token/time savings established",
    )
    write_json(DIRECTORY / "results.json", result)


if __name__ == "__main__":
    main()
