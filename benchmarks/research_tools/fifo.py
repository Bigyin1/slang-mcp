"""Compare bounded FIFO discovery workflows and inspect stateful source."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from benchmarks.research_tools.study import module_queries, parameters_page, signal_queries
from benchmarks.research_tools.transport import Recorder


def source_evidence(workspace: Path) -> list[dict[str, object]]:
    """Retain independently read RTL excerpts, not compiler-derived expectations."""
    return [source_record(source, workspace) for source in sorted(workspace.rglob("*fifo_v3.sv"))]


def source_record(source: Path, workspace: Path) -> dict[str, object]:
    return {
        "file": str(source.relative_to(workspace)),
        "lines": [
            {"line": number, "text": line.strip()}
            for number, line in enumerate(source.read_text().splitlines(), start=1)
            if any(
                text in line
                for text in (
                    "always_ff",
                    "status_cnt_q    <=",
                    "input  logic  clk_i",
                    "status_cnt_q ==",
                )
            )
        ],
    }


async def fifo_queries(recorder: Recorder) -> dict[str, object]:
    results: dict[str, object] = {}
    module = await choose_module(recorder)
    aggregate = await recorder.call(
        "list_instance_facts", {"sv_module": module, "limit": 3, "fact_limit": 20}
    )
    instances = await recorder.call("list_instances", {"sv_module": module, "limit": 3})
    results["facts_equal"] = await compare_facts(recorder, aggregate)
    if cast("list[object]", instances.get("items", [])):
        results["module"] = await module_queries(recorder, module)
        results["signal"] = await signal_queries(
            recorder,
            str(cast("dict[str, object]", cast("list[object]", instances["items"])[0])["path"])
            + (".status_cnt_q" if module.endswith("fifo_v3") else ".clk_i"),
        )
    return results


async def compare_facts(recorder: Recorder, aggregate: dict[str, object]) -> list[bool]:
    results: list[bool] = []
    for fact in cast("list[dict[str, object]]", aggregate.get("items", [])):
        results.extend(await compare_fact(recorder, fact))
    return results


async def compare_fact(recorder: Recorder, fact: dict[str, object]) -> list[bool]:
    query = {"instance_path": cast("dict[str, object]", fact["instance"])["path"], "limit": 20}
    parameters = await recorder.call("get_instance_parameters", query)
    connections = await recorder.call("get_instance_connections", query)
    return [fact["parameters"] == parameters_page(parameters), fact["connections"] == connections]


async def choose_module(recorder: Recorder) -> str:
    for module in (
        "fifo_v3",
        "cc_fifo_v3",
        "cva6_fifo_v3",
        "cc_stream_fifo",
        "cc_stream_fifo_optimal_wrap",
    ):
        answer = await recorder.call("list_instances", {"sv_module": module, "limit": 1})
        if answer.get("items"):
            return module
    return "fifo_v3"
