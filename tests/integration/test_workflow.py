"""End-to-end service and MCP boundary tests."""

import sys
from typing import Any, cast

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.server import create_server
from slang_mcp.services import SemanticService
from tests.conftest import FixtureProject, project_load_arguments, replacement_design


@pytest.mark.integration
def test_service_workflow_and_reload(fixture_project: FixtureProject) -> None:
    service = SemanticService(
        ProjectManager(StaticProjectProvider({"demo": fixture_project.config}))
    )

    summary = service.project_load("demo")
    symbol = service.find_symbol("top")[0]
    description = service.describe_symbol(symbol.symbol_id)

    assert summary.logical_module == "demo"
    assert service.project_info().summary == summary
    assert description.symbol.name == "top"
    assert service.get_hierarchy()[0].name == "top"
    assert service.describe_instance("top.u_b.u_c").sv_module == "leaf"
    assert isinstance(service.get_diagnostics(), tuple)
    assert service.find_symbol("reloaded_signal") == ()

    fixture_project.design_file.write_text(replacement_design(), encoding="utf-8")
    service.project_reload()

    assert service.find_symbol("reloaded_signal")[0].qualified_name == "top.reloaded_signal"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fastmcp_schema_and_handlers(fixture_project: FixtureProject) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))

    tools = await server.list_tools()
    result = await server.call_tool("project_load", project_load_arguments(fixture_project))
    hierarchy = await server.call_tool("get_hierarchy", {"root": "top", "max_depth": 1})

    assert {tool.name for tool in tools} == {
        "project_load",
        "project_reload",
        "project_info",
        "get_diagnostics",
        "find_symbol",
        "describe_symbol",
        "get_hierarchy",
        "describe_instance",
        "get_references",
        "list_symbols",
        "get_ports",
        "get_parameters",
        "get_instance_connections",
        "list_instance_facts",
        "list_instances",
        "find_instance",
        "get_instance_parameters",
        "get_signal_reads",
        "get_signal_writes",
        "get_drivers",
        "get_loads",
        "trace_connectivity",
        "get_procedural_blocks",
        "get_state_elements",
        "inspect_signal",
        "inspect_module",
        "inspect_instance",
        "semantic_diff",
    }
    assert all(tool.annotations is not None and tool.annotations.readOnlyHint for tool in tools)
    reload_tool = next(tool for tool in tools if tool.name == "project_reload")
    assert reload_tool.description is not None
    assert "only after RTL or build inputs change" in reload_tool.description
    assert cast(tuple[object, dict[str, Any]], result)[1]["logical_module"] == "top"
    assert cast(tuple[object, dict[str, Any]], hierarchy)[1]["roots"][0]["name"] == "top"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_server_round_trip(
    fixture_project: FixtureProject,
) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "slang_mcp"],
    )
    await _check_stdio_session(parameters, project_load_arguments(fixture_project))


async def _check_stdio_session(  # pylint: disable=too-many-locals
    parameters: StdioServerParameters, project_arguments: dict[str, object]
) -> None:

    # Pylint cannot follow the async context manager's tuple assignment.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(parameters) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        result = await session.call_tool("project_load", project_arguments)
        info = await session.call_tool("project_info", {})
    # pylint: enable=used-before-assignment

    assert not result.isError
    assert result.structuredContent is not None
    assert result.structuredContent["logical_module"] == "top"
    assert info.structuredContent is not None
    assert info.structuredContent["summary"]["top_modules"] == ["top"]
