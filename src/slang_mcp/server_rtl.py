"""Thin MCP handlers for RTL semantic services."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from slang_mcp.services import SemanticService
from slang_mcp.transport import READ_ONLY, model_dict, safe


def register_rtl_tools(server: FastMCP[None], service: SemanticService) -> None:
    _register_0(server, service)
    _register_1(server, service)
    _register_2(server, service)
    _register_3(server, service)
    _register_4(server, service)
    _register_5(server, service)
    _register_access_summary(server, service)
    _register_inspection_extra(server, service)


def _register_0(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Bounded semantic references with conservative access classification.",
        annotations=READ_ONLY,
    )
    def get_references(symbol: str, kind: str | None = None, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_references(symbol, kind, limit)))

    @server.tool(description="List direct semantic scope members.", annotations=READ_ONLY)
    def list_symbols(scope: str, kind: str | None = None, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.list_symbols(scope, kind, limit)))

    @server.tool(description="Inspect default module or interface ports.", annotations=READ_ONLY)
    def get_ports(sv_module: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_ports(sv_module, limit)))


def _register_1(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Declared defaults for a module, effective values for a nested instance.",
        annotations=READ_ONLY,
    )
    def get_parameters(target: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_parameters(target, limit)))

    @server.tool(
        description="Effective parameters of an elaborated instance, including a top.",
        annotations=READ_ONLY,
    )
    def get_instance_parameters(instance_path: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_instance_parameters(instance_path, limit)))

    @server.tool(
        description="Resolved formal ports and actual expressions; source-level connectivity.",
        annotations=READ_ONLY,
    )
    def get_instance_connections(instance_path: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_instance_connections(instance_path, limit)))


def _register_2(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Filter elaborated instances by type, exact name and path prefix.",
        annotations=READ_ONLY,
    )
    def list_instances(
        sv_module: str | None = None,
        name: str | None = None,
        path_prefix: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return model_dict(
            safe(lambda: service.rtl.list_instances(sv_module, name, path_prefix, limit))
        )

    @server.tool(
        description="Resolve an exact path or unique instance name; report ambiguity.",
        annotations=READ_ONLY,
    )
    def find_instance(query: str) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.find_instance(query)))


def _register_3(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Source-level semantic reads including read_write accesses.",
        annotations=READ_ONLY,
    )
    def get_signal_reads(signal: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_signal_reads(signal, limit)))

    @server.tool(
        description="Source-level writes, with assignment or port context.", annotations=READ_ONLY
    )
    def get_signal_writes(signal: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_signal_writes(signal, limit)))


def _register_access_summary(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Conservative source-level assignment and port drivers, not netlist drivers.",
        annotations=READ_ONLY,
    )
    def get_drivers(signal: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_drivers(signal, limit)))

    @server.tool(
        description="Source-level semantic consumers, not synthesized loads.", annotations=READ_ONLY
    )
    def get_loads(signal: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_loads(signal, limit)))


def _register_4(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Elaborated procedural blocks with bounded read/write sets.",
        annotations=READ_ONLY,
    )
    def get_procedural_blocks(sv_module: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_procedural_blocks(sv_module, limit)))

    @server.tool(
        description="Signals written in always_ff; no reset or synthesis inference.",
        annotations=READ_ONLY,
    )
    def get_state_elements(sv_module: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.rtl.get_state_elements(sv_module, limit)))


def _register_5(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Compact signal description and bounded access summaries.",
        annotations=READ_ONLY,
    )
    def inspect_signal(signal: str, limit: int = 10) -> dict[str, Any]:
        return model_dict(safe(lambda: service.inspection.inspect_signal(signal, limit)))

    @server.tool(
        description="Default signature and elaborated module usage summary.", annotations=READ_ONLY
    )
    def inspect_module(sv_module: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.inspection.inspect_module(sv_module, limit)))


def _register_inspection_extra(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Rich effective instance signature, connections and children.",
        annotations=READ_ONLY,
    )
    def inspect_instance(instance_path: str, limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.inspection.inspect_instance(instance_path, limit)))

    @server.tool(
        description="Normalized semantic differences from the last successful same-project load.",
        annotations=READ_ONLY,
    )
    def semantic_diff(limit: int = 100) -> dict[str, Any]:
        return model_dict(safe(lambda: service.semantic_diff(limit)))
