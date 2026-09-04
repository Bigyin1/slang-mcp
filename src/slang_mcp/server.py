"""Thin MCP stdio layer."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from slang_mcp.errors import SlangMcpError
from slang_mcp.project import ProjectManager
from slang_mcp.providers import ProjectProvider
from slang_mcp.services import SemanticService

_LOGGER = logging.getLogger(__name__)
_Result = TypeVar("_Result")
_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)


def create_server(provider: ProjectProvider) -> FastMCP[None]:
    """Create a configured read-only MCP server."""
    service = SemanticService(ProjectManager(provider))
    server: FastMCP[None] = FastMCP(
        "slang-mcp",
        instructions="Read-only semantic queries for configured SystemVerilog projects.",
    )

    @server.tool(
        description="Resolve and compile a logical SystemVerilog project.",
        annotations=_READ_ONLY,
    )
    def project_load(logical_module: str) -> dict[str, Any]:
        return _model_dict(_safe(lambda: service.project_load(logical_module)))

    @server.tool(
        description="Re-resolve and rebuild the active logical project.",
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

    return server


def _safe(call: Callable[[], _Result]) -> _Result:
    try:
        return call()
    except (SlangMcpError, ValueError) as error:
        raise ToolError(str(error)) from error
    except Exception as error:
        _LOGGER.exception("unexpected MCP tool failure")
        raise ToolError("internal semantic server failure") from error


def _model_dict(model: Any) -> dict[str, Any]:
    return asdict(model)
