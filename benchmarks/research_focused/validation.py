"""Validate malformed-fragment recovery and real RTL bindings over MCP stdio."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.research_focused.audit import canonical, mapping, records

ROOT = Path(__file__).parent
FAILURE_CAP = 100
RECOVERY_PORT_COUNT = 2


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


@dataclass
class Recorder:
    session: ClientSession
    calls: list[dict[str, object]] = field(default_factory=list)

    async def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = await self.session.call_tool(name, arguments)
        self.calls.append(
            {
                "tool": name,
                "arguments": arguments,
                "response": result.model_dump(mode="json", by_alias=True),
            }
        )
        return {"is_error": result.is_error, "data": result.structured_content}

    async def success(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = await self.call(name, arguments)
        require(not bool(result["is_error"]), f"Unexpected failure: {name}")
        return mapping(result["data"])

    async def failure(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = await self.call(name, arguments)
        require(bool(result["is_error"]), f"Unexpected success: {name}")
        return mapping(result["data"])

    async def load(self, paths: list[Path], top: str) -> dict[str, object]:
        return await self.success(
            "project_load_partial",
            {"source_files": [str(path) for path in paths], "top_module": top},
        )


def diagnostic_items(page: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", page["diagnostics"])


def check_context(page: dict[str, object], source_count: int, top: str) -> None:
    require(mapping(page["analysis"])["completeness"] == "not_verified", "Completeness claim")
    require(mapping(page["analysis"])["source_file_count"] == source_count, "Source count")
    require(mapping(page["analysis"])["analysis_scope"] == "fragment", "Analysis scope")
    require(mapping(page["analysis"])["top_modules"] == [top], "Analysis top")
    require(page["returned_count"] == len(diagnostic_items(page)), "Diagnostic count mismatch")
    require(page["total_count"] == len(diagnostic_items(page)), "Unexpected truncation")
    require(page["truncated"] is False, "Unexpected truncation flag")


def check_hints(page: dict[str, object]) -> None:
    for item in diagnostic_items(page):
        expected = "unclassified"
        if item["code"] in {"UnknownModule", "UnknownClassOrPackage"}:
            expected = "possible_missing_dependency"
        require(item["scope_hint"] == expected, f"Wrong hint for {item['code']}")
        require(item["severity"] == "error", "Fixture error was downgraded")


async def recovery(recorder: Recorder, root: Path) -> dict[str, object]:
    path = root / "recover.sv"
    path.write_text(
        "module recover(input logic a, output logic o);\n"
        "missing_child u();\nassign o = ;\nendmodule\n"
    )
    await recorder.load([path], "recover")
    page = await recorder.success("get_diagnostics", {"limit": 100})
    check_context(page, 1, "recover")
    check_hints(page)
    require(
        any(item["code"] == "UnknownModule" for item in diagnostic_items(page)), "No child error"
    )
    require(
        any(item["scope_hint"] == "unclassified" for item in diagnostic_items(page)),
        "No syntax error",
    )
    ports = await recorder.success("inspect_module", {"sv_module": "recover", "fields": ["ports"]})
    require(mapping(ports["ports"])["total_count"] == RECOVERY_PORT_COUNT, "Recovery lost ports")
    return {"case": "recoverable_syntax_and_missing_child", "passed": True}


async def type_error(recorder: Recorder, root: Path) -> dict[str, object]:
    path = root / "typed.sv"
    path.write_text(
        "module typed(output logic o); logic scalar; assign o=scalar.member; endmodule\n"
    )
    await recorder.load([path], "typed")
    page = await recorder.success("get_diagnostics", {"limit": 100})
    check_context(page, 1, "typed")
    check_hints(page)
    require(
        any(item["code"] == "InvalidMemberAccess" for item in diagnostic_items(page)),
        "No type error",
    )
    require(
        all(item["scope_hint"] == "unclassified" for item in diagnostic_items(page)), "Type hint"
    )
    return {"case": "type_error_unclassified", "passed": True}


async def failed_candidate(recorder: Recorder, root: Path) -> dict[str, object]:
    before = await recorder.success("project_info", {})
    page = await recorder.failure(
        "project_load_partial",
        {"source_files": [str(root / "typed.sv")], "top_module": "unavailable_top"},
    )
    require(page["status"] == "compilation_failed", "Missing failure status")
    require(page["active_project_unchanged"] is True, "Missing preservation flag")
    require(page["requested_top_modules"] == ["unavailable_top"], "Attempt top lost")
    require(mapping(page["analysis"])["context"] == "attempted_candidate", "Candidate context lost")
    require(bool(diagnostic_items(page)), "Attempt diagnostics lost")
    check_context(page, 1, "unavailable_top")
    require(await recorder.success("project_info", {}) == before, "Active project changed")
    ports = await recorder.success("inspect_module", {"sv_module": "typed", "fields": ["ports"]})
    require(mapping(ports["ports"])["total_count"] == 1, "Active semantic design changed")
    return {"case": "unavailable_top_preserves_active", "passed": True}


async def restore_dependency(recorder: Recorder, root: Path) -> dict[str, object]:
    path = root / "restore.sv"
    path.write_text(
        "module restore(output logic o); logic scalar; "
        "missing_child u(); assign o=scalar.member; endmodule\n"
    )
    (root / "child.sv").write_text("module missing_child; endmodule\n")
    await recorder.load([path], "restore")
    before = await recorder.success("get_diagnostics", {"limit": 100})
    await recorder.load([root / "child.sv", path], "restore")
    after = await recorder.success("get_diagnostics", {"limit": 100})
    check_context(after, 2, "restore")
    check_hints(after)
    require(
        any(item["code"] == "UnknownModule" for item in diagnostic_items(before)),
        "Missing boundary",
    )
    require(
        all(item["code"] != "UnknownModule" for item in diagnostic_items(after)), "Child unresolved"
    )
    require(
        any(item["code"] == "InvalidMemberAccess" for item in diagnostic_items(after)),
        "Type error hidden",
    )
    return {"case": "dependency_restore_retains_other_errors", "passed": True}


async def bounded_failure(recorder: Recorder, root: Path) -> dict[str, object]:
    path = root / "many.sv"
    path.write_text(
        "\n".join(
            f"module bad_{index}(output logic o); assign o = ; endmodule" for index in range(125)
        )
        + "\n"
    )
    result = await recorder.call(
        "project_load_partial", {"source_files": [str(path)], "top_module": "unavailable_top"}
    )
    require(bool(result["is_error"]), "Bounded candidate unexpectedly succeeded")
    page = mapping(result["data"])
    require(len(diagnostic_items(page)) <= FAILURE_CAP, "Failure page exceeded cap")
    require(page["returned_count"] == len(diagnostic_items(page)), "Failure returned count")
    if cast("int", page["total_count"]) <= FAILURE_CAP:
        return {
            "case": "failure_page_cap",
            "passed": True,
            "overflow_exercised": False,
            "limitation": ("Compiler returned at most100 diagnostics; overflow cap not exercised."),
        }
    require(
        page["returned_count"] == FAILURE_CAP and page["truncated"] is True,
        "Bad failure truncation",
    )
    return {"case": "failure_page_cap", "passed": True, "overflow_exercised": True}


def floo_load_arguments() -> dict[str, object]:
    loads = [
        mapping(mapping(item["request"])["arguments"])
        for item in records(ROOT / "floo_generate_core.calls.jsonl")
        if mapping(item["request"]).get("name") == "project_load_partial"
    ]
    return loads[-1]


async def floo_bindings(recorder: Recorder) -> dict[str, object]:
    await recorder.success("project_load_partial", floo_load_arguments())
    expected = {
        "data_i": "data_i[n]",
        "valid_i": "valid_i[n][v]",
        "ready_o": "ready_o[n][v]",
        "data_o": "data_out[n][v]",
        "valid_o": "valid_out[n][v]",
        "ready_i": "ready_in[n][v]",
    }
    result = await recorder.success(
        "inspect_instance",
        {
            "instance_path": "floo_fifo.gen_floo_fifo.gen_virt_channels.gen_channel[1]."
            "gen_virt_channel[0].i_stream_fifo",
            "fields": ["connections"],
            "port_names": list(expected),
        },
    )
    for item in cast("list[dict[str, object]]", mapping(result["connections"])["items"]):
        name = str(mapping(item["port"])["name"])
        require(name in expected, "Unexpected Floo port")
        require(item["expression"] == expected[name], f"Wrong actual text for {name}")
        require(item["actual_width"] == 1, f"Wrong actual width for {name}")
        require(item["actual_type"] not in (None, "<error>"), f"Invalid actual type for {name}")
        expected.pop(name)
    require(not expected, "Missing requested Floo ports")
    return {"case": "real_floo_output_lvalue_expressions", "passed": True}


async def session_cases(session: ClientSession, root: Path, profile: str) -> dict[str, object]:
    recorder = Recorder(session)
    results = [
        await recovery(recorder, root),
        await type_error(recorder, root),
        await failed_candidate(recorder, root),
        await restore_dependency(recorder, root),
        await bounded_failure(recorder, root),
        await floo_bindings(recorder),
    ]
    return {
        "profile": profile,
        "cases": results,
        "calls": recorder.calls,
        "calls_sha256": hashlib.sha256(canonical(recorder.calls)).hexdigest(),
    }


async def profile_probe(binary: Path, profile: str, root: Path) -> dict[str, object]:
    # Pylint cannot follow async context-manager tuple binding.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(
            StdioServerParameters(command=str(binary), args=["--tool-profile", profile])
        ) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        return await session_cases(session, root, profile)
    # pylint: enable=used-before-assignment


async def run(binary: Path) -> dict[str, object]:
    with TemporaryDirectory(prefix="slang-final-validation-") as temporary:
        return {
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "encoding": "Canonical UTF-8 JSON; sorted keys; compact separators; nulls retained",
            "runs": [
                await profile_probe(binary, profile, Path(temporary))
                for profile in ("core", "full")
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    options.output.write_text(
        json.dumps(asyncio.run(run(options.binary.resolve())), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
