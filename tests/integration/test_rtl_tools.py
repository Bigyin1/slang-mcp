"""MCP contracts for the second semantic layer, including reload workflows."""

from typing import Any, cast

import pytest

from slang_mcp.providers import StaticProjectProvider
from slang_mcp.server import create_server
from tests.conftest import FixtureProject


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments", "key"),
    [
        ("get_references", {"symbol": "top.data"}, "total_count"),
        ("list_symbols", {"scope": "types_pkg"}, "items"),
        ("get_ports", {"sv_module": "leaf"}, "items"),
        ("get_parameters", {"target": "leaf"}, "value_kind"),
        ("get_instance_connections", {"instance_path": "top.u_a"}, "items"),
        ("list_instances", {"sv_module": "leaf"}, "total_count"),
        ("find_instance", {"query": "u_a"}, "path"),
        ("get_instance_parameters", {"instance_path": "top.u_a"}, "value_kind"),
        ("get_signal_reads", {"signal": "top.data"}, "items"),
        ("get_signal_writes", {"signal": "top.data"}, "items"),
        ("get_drivers", {"signal": "top.data"}, "items"),
        ("get_loads", {"signal": "top.data"}, "items"),
        ("trace_connectivity", {"signal": "top.data"}, "paths"),
        ("get_procedural_blocks", {"sv_module": "leaf"}, "items"),
        ("get_state_elements", {"sv_module": "leaf"}, "items"),
        ("inspect_signal", {"signal": "top.data"}, "reference_count"),
        ("inspect_module", {"sv_module": "leaf"}, "ports"),
        ("inspect_instance", {"instance_path": "top.u_a"}, "connections"),
        ("semantic_diff", {}, "status"),
    ],
)
async def test_rtl_mcp_tools(
    fixture_project: FixtureProject,
    tool: str,
    arguments: dict[str, str],
    key: str,
) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))
    await server.call_tool("project_load", {"logical_module": "demo"})
    assert key in cast(tuple[object, dict[str, Any]], await server.call_tool(tool, arguments))[1]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_instance_query_filters_over_mcp(fixture_project: FixtureProject) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))
    await server.call_tool("project_load", {"logical_module": "demo"})

    parameters = cast(
        tuple[object, dict[str, Any]],
        await server.call_tool(
            "get_instance_parameters",
            {"instance_path": "top.u_a", "names": ["WIDTH"]},
        ),
    )[1]
    connections = cast(
        tuple[object, dict[str, Any]],
        await server.call_tool(
            "get_instance_connections",
            {"instance_path": "top.u_a", "ports": ["o"]},
        ),
    )[1]

    assert [item["name"] for item in parameters["parameters"]["items"]] == ["WIDTH"]
    assert [item["port"]["name"] for item in connections["items"]] == ["o"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_reload_diff(fixture_project: FixtureProject) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))
    await server.call_tool("project_load", {"logical_module": "demo"})
    fixture_project.design_file.write_text(
        fixture_project.design_file.read_text(encoding="utf-8").replace("WIDTH(32)", "WIDTH(16)"),
        encoding="utf-8",
    )
    await server.call_tool("project_reload", {})
    assert (
        cast(tuple[object, dict[str, Any]], await server.call_tool("semantic_diff", {}))[1][
            "changes"
        ]["total_count"]
        > 0
    )
