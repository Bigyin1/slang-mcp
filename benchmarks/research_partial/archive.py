"""Deduplicate repeated response bodies without changing measured raw values."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from benchmarks.dataset import read_object

RAW = Path(__file__).parent / "raw.json"


def object_dict(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def intern(value: object, payloads: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(encoded.encode()).hexdigest()[:16]
    payloads[key] = value
    return key


def compact_call(call: dict[str, object], payloads: dict[str, object]) -> None:
    call["payload"] = intern({"data": call.pop("data"), "text": call.pop("text")}, payloads)


def compact(output: dict[str, object]) -> dict[str, object]:
    payloads: dict[str, object] = {}
    for run in cast("list[dict[str, object]]", output["runs"]):
        run["source_names"] = intern(run["source_names"], payloads)
        for call in object_dict(run["calls"]).values():
            compact_call(object_dict(call), payloads)
    output["payloads"] = payloads
    return output


def expand(output: dict[str, object]) -> dict[str, object]:
    if "payloads" not in output:
        return output
    payloads = object_dict(output.pop("payloads"))
    for run in cast("list[dict[str, object]]", output["runs"]):
        run["source_names"] = payloads[str(run["source_names"])]
        for call in object_dict(run["calls"]).values():
            object_dict(call).update(object_dict(payloads[str(object_dict(call).pop("payload"))]))
    return output


def save(output: dict[str, object]) -> None:
    RAW.write_text(json.dumps(compact(output), separators=(",", ":")) + "\n")


if __name__ == "__main__":
    save(expand(read_object(RAW)))
