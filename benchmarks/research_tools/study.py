"""Exercise aggregate and primitive workflows on one elaborated real design."""

from __future__ import annotations

from benchmarks.research_tools.transport import Recorder

LIMIT = 20


async def module_queries(recorder: Recorder, module: str) -> dict[str, object]:
    aggregate = await recorder.call("inspect_module", {"sv_module": module, "limit": LIMIT})
    answers = {}
    for name in ("get_ports", "get_procedural_blocks"):
        answers[name] = await recorder.call(name, {"sv_module": module, "limit": LIMIT})
    answers["parameters"] = await recorder.call(
        "get_parameters", {"target": module, "limit": LIMIT}
    )
    await recorder.call("get_state_elements", {"sv_module": module, "limit": LIMIT})
    await recorder.call("list_symbols", {"scope": module, "limit": LIMIT})
    return {
        "ports_equal": aggregate.get("ports") == answers["get_ports"],
        "procedures_equal": aggregate.get("procedures") == answers["get_procedural_blocks"],
        "parameters_equal": parameters_page(aggregate.get("parameters"))
        == parameters_page(answers["parameters"]),
    }


async def signal_queries(recorder: Recorder, signal: str) -> dict[str, object]:
    aggregate = await recorder.call("inspect_signal", {"signal": signal, "limit": LIMIT})
    answers = {}
    for name in ("get_signal_reads", "get_signal_writes", "get_drivers", "get_loads"):
        answers[name] = await recorder.call(name, {"signal": signal, "limit": LIMIT})
    await recorder.call("get_references", {"symbol": signal, "limit": LIMIT})
    await recorder.call("trace_connectivity", {"signal": signal, "limit": LIMIT, "max_depth": 3})
    return {
        "reads_equal": aggregate.get("reads") == answers["get_signal_reads"],
        "writes_equal": aggregate.get("writes") == answers["get_signal_writes"],
        "drivers_equal_writes": answers["get_drivers"] == answers["get_signal_writes"],
        "loads_equal_reads": answers["get_loads"] == answers["get_signal_reads"],
    }


async def instance_queries(recorder: Recorder, instance: str) -> dict[str, object]:
    aggregate = await recorder.call("inspect_instance", {"instance_path": instance, "limit": LIMIT})
    answers = {}
    for name in ("parameters", "connections"):
        answers[name] = await recorder.call(
            "get_instance_" + name, {"instance_path": instance, "limit": LIMIT}
        )
    await recorder.call("describe_instance", {"path": instance})
    await recorder.call("find_instance", {"query": instance})
    return {
        "parameters_equal": parameters_page(aggregate.get("parameters"))
        == parameters_page(answers["parameters"]),
        "connections_equal": aggregate.get("connections") == answers["connections"],
    }


async def study(recorder: Recorder, top: str) -> dict[str, object]:
    results: dict[str, object] = {}
    await recorder.call("project_info", {})
    await recorder.call("get_diagnostics", {"limit": LIMIT})
    await recorder.call("summarize_diagnostics_by_code", {"limit": LIMIT})
    await recorder.call("find_symbol", {"name": top})
    await recorder.call("describe_symbol", {"identifier": top})
    await recorder.call("get_hierarchy", {"max_depth": 1})
    results["module"] = await module_queries(recorder, top)
    results["signal"] = await signal_queries(recorder, top + ".clk_i")
    results["instance"] = await instance_queries(recorder, top)
    await recorder.call("list_instances", {"sv_module": "fifo_v3", "limit": LIMIT})
    await recorder.call(
        "list_instance_facts", {"sv_module": "fifo_v3", "limit": LIMIT, "fact_limit": 5}
    )
    results["before_reload_diff"] = await recorder.call("semantic_diff", {"limit": LIMIT})
    await recorder.call("project_reload", {})
    results["unchanged_reload_diff"] = await recorder.call("semantic_diff", {"limit": LIMIT})
    return results


def parameters_page(value: object) -> object:
    """Ignore target identifier spelling while comparing the same fact payload."""
    if isinstance(value, dict):
        return value.get("parameters", value)
    return value
