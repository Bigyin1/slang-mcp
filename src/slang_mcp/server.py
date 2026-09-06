"""Thin MCP stdio layer."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from slang_mcp.project import ProjectManager
from slang_mcp.providers import ProjectProvider
from slang_mcp.server_rtl import register_rtl_tools
from slang_mcp.services import SemanticService
from slang_mcp.transport import READ_ONLY as _READ_ONLY
from slang_mcp.transport import model_dict as _model_dict
from slang_mcp.transport import safe as _safe


def create_server(provider: ProjectProvider) -> FastMCP[None]:
    """Create a configured read-only MCP server."""
    service = SemanticService(ProjectManager(provider))
    server: FastMCP[None] = FastMCP(
        "slang-mcp",
        instructions="Read-only semantic queries for configured SystemVerilog projects.",
    )
    _register_project_tools(server, service)
    _register_symbol_tools(server, service)
    _register_hierarchy_tools(server, service)
    register_rtl_tools(server, service)
    return server


def _register_project_tools(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Resolve and compile a logical SystemVerilog project.",
        annotations=_READ_ONLY,
    )
    def project_load(logical_module: str) -> dict[str, Any]:
        return _model_dict(_safe(lambda: service.project_load(logical_module)))

    @server.tool(
        description=(
            "Re-resolve and rebuild the active logical project. This recompiles and reindexes "
            "all configured RTL, so call it only after RTL or build inputs change; batch all "
            "semantic queries against the resulting loaded project."
        ),
        annotations=_READ_ONLY,
    )
    def project_reload() -> dict[str, Any]:
        return _model_dict(_safe(service.project_reload))

    @server.tool(
        description="Return build and elaboration information without rebuilding.",
        annotations=_READ_ONLY,
    )
    def project_info() -> dict[str, Any]:
        return _model_dict(_safe(service.project_info))


def _register_symbol_tools(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Return bounded structured Slang diagnostics.",
        annotations=_READ_ONLY,
    )
    def get_diagnostics(limit: int = 100, severity: str | None = None) -> dict[str, Any]:
        items = _safe(lambda: service.get_diagnostics(limit, severity))
        return {"diagnostics": [asdict(item) for item in items], "returned_count": len(items)}

    @server.tool(
        description="Find semantic declarations by exact name.",
        annotations=_READ_ONLY,
    )
    def find_symbol(name: str) -> dict[str, Any]:
        items = _safe(lambda: service.find_symbol(name))
        return {"symbols": [asdict(item) for item in items], "match_count": len(items)}

    @server.tool(
        description="Describe one semantic symbol by stable id, qualified name, or name.",
        annotations=_READ_ONLY,
    )
    def describe_symbol(identifier: str) -> dict[str, Any]:
        return _model_dict(_safe(lambda: service.describe_symbol(identifier)))


def _register_hierarchy_tools(server: FastMCP[None], service: SemanticService) -> None:

    @server.tool(
        description="Return the elaborated instance and generate hierarchy.",
        annotations=_READ_ONLY,
    )
    def get_hierarchy(
        root: str | None = None,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        items = _safe(lambda: service.get_hierarchy(root, max_depth))
        return {"roots": [asdict(item) for item in items]}

    @server.tool(
        description="Describe an elaborated instance and its direct children.",
        annotations=_READ_ONLY,
    )
    def describe_instance(path: str) -> dict[str, Any]:
        return _model_dict(_safe(lambda: service.describe_instance(path)))
