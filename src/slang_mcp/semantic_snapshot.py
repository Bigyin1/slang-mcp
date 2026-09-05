"""Compiler-independent semantic snapshots and deterministic reload differences."""

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from slang_mcp.errors import SignatureUnavailableError
from slang_mcp.rtl_models import SemanticChange, SemanticDiff, page

if TYPE_CHECKING:
    from slang_mcp.adapters import SlangDesign


def snapshot(design: "SlangDesign") -> dict[str, str]:
    result = _definitions(design)
    for instance in design.rtl.instances.values():
        result[f"instance:{instance.path}"] = instance.sv_module
        for parameter in design.rtl.parameters(instance.path, effective=True):
            result[f"effective_parameter:{instance.path}.{parameter.name}"] = json.dumps(
                asdict(parameter),
                sort_keys=True,
            )
    result.update(_diagnostics(design))
    return result


def _diagnostics(design: "SlangDesign") -> dict[str, str]:
    return {
        f"diagnostic:{normalized}": normalized
        for normalized in (json.dumps(asdict(item), sort_keys=True) for item in design.diagnostics)
    }


def _definitions(design: "SlangDesign") -> dict[str, str]:
    result: dict[str, str] = {}
    for definition in design.definitions():
        result[f"definition:{definition.symbol_id}"] = definition.kind
        if definition.kind in {"module", "interface"}:
            result.update(_signature(design, definition.symbol_id))
    return result


def _signature(design: "SlangDesign", name: str) -> dict[str, str]:
    try:
        return _available_signature(design, name)
    except SignatureUnavailableError:
        return {f"signature_unavailable:{name}": "default elaboration unavailable"}


def _available_signature(design: "SlangDesign", name: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for port in design.rtl.ports(name):
        result[f"port:{name}.{port.name}"] = json.dumps(
            {key: value for key, value in asdict(port).items() if key != "location"}, sort_keys=True
        )
    for parameter in design.rtl.parameters(name, effective=False):
        result[f"parameter:{name}.{parameter.name}"] = json.dumps(asdict(parameter), sort_keys=True)
    return result


def compare(
    previous: dict[str, str] | None,
    current: dict[str, str],
    limit: int,
) -> SemanticDiff:
    if previous is None:
        return SemanticDiff("no_previous_state", page((), limit))
    return SemanticDiff(
        "compared",
        page(
            tuple(
                SemanticChange(
                    key.partition(":")[0],
                    key.partition(":")[2],
                    previous.get(key),
                    current.get(key),
                )
                for key in sorted(previous.keys() | current.keys())
                if previous.get(key) != current.get(key)
            ),
            limit,
        ),
    )
