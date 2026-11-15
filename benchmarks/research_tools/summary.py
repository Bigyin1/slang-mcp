"""Extract deterministic cost comparisons from captured native answers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast


def costs(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "calls": len(records),
        "response_bytes": sum(cast("int", record["response_bytes"]) for record in records),
        "seconds": sum(cast("float", record["seconds"]) for record in records),
    }


def compare(
    records: list[dict[str, object]], tool: str, primitives: tuple[str, ...]
) -> list[dict[str, object]]:
    return [
        comparison_row(records, index, primitives)
        for index, record in enumerate(records)
        if record["tool"] == tool
    ]


def comparison_row(
    records: list[dict[str, object]], index: int, primitives: tuple[str, ...]
) -> dict[str, object]:
    return {
        "arguments": records[index]["arguments"],
        "aggregate": costs([records[index]]),
        "primitive": costs(
            [item for item in records[index + 1 :] if item["tool"] in primitives][: len(primitives)]
        ),
    }


def summarize(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "total": costs(records),
        "unique_tools": len({item["tool"] for item in records}),
        "errors": sum(bool(item["is_error"]) for item in records),
        "signal": compare(records, "inspect_signal", ("get_signal_reads", "get_signal_writes")),
        "module": compare(
            records, "inspect_module", ("get_ports", "get_procedural_blocks", "get_parameters")
        ),
        "instance": compare(
            records, "inspect_instance", ("get_instance_parameters", "get_instance_connections")
        ),
    }


def main() -> None:
    directory = Path(__file__).parent / "results"
    result = {
        path.name: summarize(json.loads(path.read_text()))
        for path in sorted(directory.glob("*.calls.json"))
    }
    (directory / "summary.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
