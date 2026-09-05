"""Persist normalized tables, figures and Markdown from a resumable experiment."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import cast

from benchmarks.dataset import read_object
from benchmarks.reporting.aggregate import aggregate
from benchmarks.reporting.figures import generate_figures
from benchmarks.reporting.markdown import render
from benchmarks.reporting.statistics import Record
from benchmarks.runner.storage import write_json


def load_records(folder: Path, identity: str) -> list[Record]:
    records = []
    for run in sorted((folder / "raw").glob("*/*/rep_*")):
        valid = [read_object(path) for path in sorted(run.glob("attempt_*/metadata.json"))]
        if valid := [r for r in valid if r.get("completed") and r.get("fingerprint") == identity]:
            records.append(valid[-1])
    return records


def csv_file(path: Path, records: list[Record]) -> None:
    fields = sorted({key for record in records for key in record})
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else value
                for key, value in record.items()
            }
            for record in records
        )


def generate_report(folder: Path) -> Record:
    manifest = read_object(folder / "experiment.json")
    records = load_records(folder, str(manifest["fingerprint"]))
    summary = aggregate(
        records, cast("list[Record]", manifest["planned"]), int(cast("int", manifest["seed"]))
    )
    _normalized(folder / "normalized", records, summary)
    (folder / "reports").mkdir(exist_ok=True)
    generate_figures(summary, folder / "reports/figures")
    (folder / "reports/benchmark_report.md").write_text(render(summary, manifest, records))
    return summary


def _normalized(normalized: Path, records: list[Record], summary: Record) -> None:
    normalized.mkdir(exist_ok=True)
    (normalized / "runs.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    )
    csv_file(normalized / "runs.csv", records)
    write_json(normalized / "summary.json", summary)
    csv_file(
        normalized / "summary.csv",
        [
            {"mode": mode, **data}
            for mode, data in cast("dict[str, Record]", summary["modes"]).items()
        ],
    )
