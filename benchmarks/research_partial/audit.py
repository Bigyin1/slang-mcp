"""Compare measured module defaults with manually inspected source declarations."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import cast

from benchmarks.dataset import read_object
from benchmarks.research_partial.archive import RAW, expand, object_dict


def call(run: dict[str, object], name: str) -> dict[str, object]:
    return object_dict(object_dict(run["calls"])[name])


def data(run: dict[str, object], name: str) -> dict[str, object]:
    return object_dict(call(run, name)["data"] or {})


def ports(run: dict[str, object]) -> list[tuple[str, str, object]]:
    return [
        (str(item["name"]), str(item["direction"]), item["width"])
        for item in cast("list[dict[str, object]]", data(run, "get_ports").get("items", []))
    ]


STREAM_PORTS = [
    ("clk_i", "in", 1),
    ("rst_ni", "in", 1),
    ("clr_i", "in", 1),
    ("flush_i", "in", 1),
    ("usage_o", "out", 4),
    ("data_i", "in", 32),
    ("valid_i", "in", 1),
    ("ready_o", "out", 1),
    ("data_o", "out", 32),
    ("valid_o", "out", 1),
    ("ready_i", "in", 1),
]
FIFO_PORTS = [
    ("clk_i", "in", 1),
    ("rst_ni", "in", 1),
    ("flush_i", "in", 1),
    ("testmode_i", "in", 1),
    ("full_o", "out", 1),
    ("empty_o", "out", 1),
    ("usage_o", "out", 3),
    ("data_i", "in", 32),
    ("push_i", "in", 1),
    ("data_o", "out", 32),
    ("pop_i", "in", 1),
]


def oracle(run: dict[str, object]) -> bool:
    expected = STREAM_PORTS if run["target"] == "cc_stream_fifo" else FIFO_PORTS
    return ports(run) == expected


def query_seconds(run: dict[str, object]) -> float:
    return sum(
        cast("float", object_dict(value)["seconds"])
        for key, value in object_dict(run["calls"]).items()
        if key != "load"
    )


def milliseconds(runs: list[dict[str, object]], name: str) -> list[float]:
    return [1000 * cast("float", call(run, name)["seconds"]) for run in runs]


def signature_matches(run: dict[str, object], reference: dict[str, object]) -> bool:
    return ports(run) == ports(reference) and data(run, "get_parameters") == data(
        reference, "get_parameters"
    )


def summarize(runs: list[dict[str, object]], reference: dict[str, object]) -> dict[str, object]:
    return {
        "project": runs[0]["project"],
        "scenario": runs[0]["scenario"],
        "sources": runs[0]["sources"],
        "load_ms_median": median(milliseconds(runs, "load")),
        "load_ms_range": [min(milliseconds(runs, "load")), max(milliseconds(runs, "load"))],
        "five_queries_ms_median": median([1000 * query_seconds(run) for run in runs]),
        "load_data": data(runs[0], "load"),
        "source_oracle_matches": sum(oracle(run) for run in runs),
        "default_signature_matches_full": [signature_matches(run, reference) for run in runs],
        "target_instances": data(runs[0], "list_instances").get("total_count"),
        "response_bytes": {
            name: call(runs[0], name)["bytes"] for name in object_dict(runs[0]["calls"])
        },
    }


def main() -> None:
    runs = cast("list[dict[str, object]]", expand(read_object(RAW))["runs"])
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for run in runs:
        groups.setdefault((str(run["project"]), str(run["scenario"])), []).append(run)
    (Path(__file__).parent / "summary.json").write_text(
        json.dumps(
            [
                summarize(group, groups[(str(group[0]["project"]), "full")][0])
                for group in groups.values()
            ],
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
