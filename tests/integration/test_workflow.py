"""End-to-end service and MCP boundary tests."""

import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.server import create_server
from slang_mcp.services import SemanticService
from tests.conftest import FixtureProject, replacement_design


@pytest.mark.integration
def test_service_workflow_and_reload(fixture_project: FixtureProject) -> None:
    provider = StaticProjectProvider({"demo": fixture_project.config})
    service = SemanticService(ProjectManager(provider))

    summary = service.project_load("demo")
    info = service.project_info()
    symbol = service.find_symbol("top")[0]
    description = service.describe_symbol(symbol.symbol_id)
    hierarchy = service.get_hierarchy()
    instance = service.describe_instance("top.u_b.u_c")
    diagnostics = service.get_diagnostics()

    assert summary.logical_module == "demo"
    assert info.summary == summary
    assert description.symbol.name == "top"
    assert hierarchy[0].name == "top"
    assert instance.sv_module == "leaf"
    assert isinstance(diagnostics, tuple)
    assert service.find_symbol("reloaded_signal") == ()

    fixture_project.design_file.write_text(replacement_design(), encoding="utf-8")
    service.project_reload()

    assert service.find_symbol("reloaded_signal")[0].qualified_name == "top.reloaded_signal"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fastmcp_schema_and_handlers(fixture_project: FixtureProject) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))

    tools = await server.list_tools()
    names = {tool.name for tool in tools}
    result = await server.call_tool("project_load", {"logical_module": "demo"})
    hierarchy = await server.call_tool("get_hierarchy", {"root": "top", "max_depth": 1})

    assert names == {
        "project_load",
        "project_reload",
        "project_info",
        "get_diagnostics",
        "find_symbol",
        "describe_symbol",
        "get_hierarchy",
        "describe_instance",
    }
    assert all(tool.annotations is not None and tool.annotations.readOnlyHint for tool in tools)
    result_data = cast(tuple[object, dict[str, Any]], result)[1]
    hierarchy_data = cast(tuple[object, dict[str, Any]], hierarchy)[1]
    assert result_data["logical_module"] == "demo"
    assert hierarchy_data["roots"][0]["name"] == "top"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_server_round_trip(
    fixture_project: FixtureProject,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "projects.json"
    config_path.write_text(
        json.dumps(
            {
                "demo": {
                    "source_files": [str(path) for path in fixture_project.config.source_files],
                    "include_directories": [
                        str(path) for path in fixture_project.config.include_directories
                    ],
                    "defines": fixture_project.config.defines,
                    "top_modules": ["top"],
                }
            }
        ),
        encoding="utf-8",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "slang_mcp", "--config", str(config_path)],
    )

    # Pylint cannot follow the async context manager's tuple assignment.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool("project_load", {"logical_module": "demo"})
        info = await session.call_tool("project_info", {})
    # pylint: enable=used-before-assignment

    assert not result.isError
    assert result.structuredContent is not None
    assert result.structuredContent["logical_module"] == "demo"
    assert info.structuredContent is not None
    assert info.structuredContent["summary"]["top_modules"] == ["top"]
