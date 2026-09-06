"""Thin MCP stdio layer."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from slang_mcp.project import ProjectManager
from slang_mcp.server_rtl import register_rtl_tools
from slang_mcp.services import SemanticService
from slang_mcp.transport import READ_ONLY as _READ_ONLY
from slang_mcp.transport import model_dict as _model_dict
from slang_mcp.transport import safe as _safe

if TYPE_CHECKING:
    from slang_mcp.providers.static import StaticProjectProvider


def create_server(provider: StaticProjectProvider | None = None) -> FastMCP[None]:
    """Create a read-only MCP server; provider injection is test-only."""
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
        description=(
            "Compile one SystemVerilog top from ordered file lists. Pass package lists first, "
            "then RTL and model lists. Each non-empty list entry must be an absolute path; "
            "source order and duplicates are preserved."
        ),
        annotations=_READ_ONLY,
    )
    def project_load(
        source_file_lists: list[str],
        top_module: str,
        include_directory_lists: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        return _model_dict(
            _safe(
                lambda: service.project_load_file_lists(
                    source_file_lists,
                    top_module,
                    include_directory_lists,
                    defines,
                )
            )
        )

    @server.tool(
        description=(
            "Rebuild and reindex the active project from the same direct build inputs. Call it "
            "only after RTL or build inputs change; batch semantic queries against one load."
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


def _register_symbol_tools(  # pylint: disable=too-many-locals
    server: FastMCP[None], service: SemanticService
) -> None:

    @server.tool(
        description="Return bounded structured Slang diagnostics.",
        annotations=_READ_ONLY,
    )
    def get_diagnostics(limit: int = 100, severity: str | None = None) -> dict[str, Any]:
        items = _safe(lambda: service.get_diagnostics(limit, severity))
        return {"diagnostics": [asdict(item) for item in items], "returned_count": len(items)}

    @server.tool(
        description=(
            "Bounded diagnostic groups by Slang code, with severity counts and one example. "
            "Use get_diagnostics for individual locations and messages."
        ),
        annotations=_READ_ONLY,
    )
    def summarize_diagnostics_by_code(
        severity: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        return _model_dict(_safe(lambda: service.summarize_diagnostics_by_code(severity, limit)))

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
        description=(
            "Return the elaborated instance and generate hierarchy. root accepts an exact "
            "elaborated instance or generate-block path, or a top name."
        ),
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
