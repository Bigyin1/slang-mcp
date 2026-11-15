"""Derive reproducible protocol metrics from recorded worker MCP exchanges."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parent
PAIRED = (
    "axi_core",
    "axi_full",
    "floo_generate_core",
    "floo_generate_full",
    "cva6_counter_core",
    "cva6_counter_full",
    "idma_partial_core",
    "idma_partial_full",
)


def mapping(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def records(path: Path) -> list[dict[str, object]]:
    return [mapping(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def request(record: dict[str, object]) -> dict[str, object]:
    return mapping(record["request"])


def response(record: dict[str, object]) -> dict[str, object]:
    return mapping(record["response"])


def errors(calls: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {"call_index": index, "request": request(call), "response": response(call)}
        for index, call in enumerate(calls, start=1)
        if response(call).get("isError", False) or "error" in response(call)
    ]


def source_loads(calls: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "call_index": index,
            "arguments": request(call).get("arguments", {}),
            "result": response(call).get("structuredContent"),
        }
        for index, call in enumerate(calls, start=1)
        if request(call).get("name") in {"project_load_partial", "project_load"}
    ]


def fields_usage(calls: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "call_index": index,
            "tool": request(call).get("name"),
            "fields": mapping(request(call).get("arguments", {}))["fields"],
        }
        for index, call in enumerate(calls, start=1)
        if "fields" in mapping(request(call).get("arguments", {}))
    ]


def counts(calls: list[dict[str, object]]) -> dict[str, object]:
    return {
        "requests": len(calls),
        "tool_calls": sum(request(call).get("method") == "tools/call" for call in calls),
        "response_bytes": sum(len(canonical(response(call))) for call in calls),
        "request_bytes": sum(len(canonical(request(call))) for call in calls),
        "by_tool": dict(Counter(str(request(call).get("name", "tools/list")) for call in calls)),
        "errors": len(errors(calls)),
        "successful_tool_calls": sum(
            request(call).get("method") == "tools/call"
            and not response(call).get("isError", False)
            and "error" not in response(call)
            for call in calls
        ),
    }


def catalog_check(calls: list[dict[str, object]]) -> dict[str, object]:
    catalog = set()
    for call in calls:
        for tool in cast("list[dict[str, object]]", response(call).get("tools", [])):
            catalog.add(str(tool["name"]))
    return {
        "catalog_size": len(catalog),
        "calls_outside_catalog": [
            request(call)["name"]
            for call in calls
            if request(call).get("method") == "tools/call"
            and request(call).get("name") not in catalog
        ],
        "catalog_response_bytes": sum(
            len(canonical(response(call))) for call in calls if "tools" in response(call)
        ),
    }


def run_metrics(name: str) -> dict[str, object]:
    calls = records(ROOT / f"{name}.calls.jsonl")
    return {
        "run": name,
        "paired": name in PAIRED,
        "answer_present": (ROOT / f"{name}.answers.json").exists(),
        "counts": counts(calls),
        "catalog_check": catalog_check(calls),
        "errors": errors(calls),
        "fields_usage": fields_usage(calls),
        "source_loads": source_loads(calls),
        "catalog_sizes": [
            len(cast("list[object]", response(call)["tools"]))
            for call in calls
            if "tools" in response(call)
        ],
    }


def main() -> None:
    output = {
        "encoding": (
            "Canonical UTF-8 JSON, ensure_ascii=false, sorted keys; "
            "compact separators; nulls retained"
        ),
        "scope": (
            "MCP requests/responses only; shell/source reads and model/provider tokens unavailable"
        ),
        "call_index": "One-based position in each trace, including tools/list requests",
        "runs": [run_metrics(name) for name in (*PAIRED, "axi_batch_full")],
    }
    (ROOT / "audit_metrics.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
