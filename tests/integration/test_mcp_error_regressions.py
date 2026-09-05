"""Controlled MCP failures must leave the active semantic state usable."""

from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from slang_mcp.providers import StaticProjectProvider
from slang_mcp.server import create_server
from tests.conftest import FixtureProject


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_references", {"symbol": "top.data"}),
        ("get_ports", {"sv_module": "leaf"}),
        ("get_instance_connections", {"instance_path": "top.u_a"}),
        ("inspect_signal", {"signal": "top.data"}),
        ("inspect_module", {"sv_module": "leaf"}),
        ("inspect_instance", {"instance_path": "top.u_a"}),
        ("semantic_diff", {}),
    ],
)
async def test_unloaded_rtl_queries_report_controlled_error(
    fixture_project: FixtureProject,
    tool: str,
    arguments: dict[str, str],
) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))
    with pytest.raises(ToolError, match="no project is loaded"):
        await server.call_tool(tool, arguments)
    await server.call_tool("project_load", {"logical_module": "demo"})
    assert isinstance(await server.call_tool(tool, arguments), tuple)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("find_instance", {"query": "u_generated"}, "ambiguous instance"),
        ("find_instance", {"query": "absent"}, "unknown instance"),
        ("get_references", {"symbol": "state"}, "ambiguous symbol"),
        ("get_references", {"symbol": "absent"}, "unknown symbol"),
        ("get_ports", {"sv_module": "top.data"}, "not a module or interface"),
        ("get_references", {"symbol": "top.data", "kind": "guess"}, "unknown reference kind"),
        ("list_instances", {"limit": 0}, "limit must be between"),
        ("get_signal_reads", {"signal": "top.data", "limit": 501}, "limit must be between"),
        ("semantic_diff", {"limit": -1}, "limit must be between"),
    ],
)
async def test_invalid_rtl_query_does_not_poison_session(
    fixture_project: FixtureProject,
    tool: str,
    arguments: dict[str, str | int],
    message: str,
) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))
    await server.call_tool("project_load", {"logical_module": "demo"})
    with pytest.raises(ToolError, match=message):
        await server.call_tool(tool, arguments)
    assert (
        cast(
            tuple[object, dict[str, Any]],
            await server.call_tool("find_instance", {"query": "top.u_a"}),
        )[1]["path"]
        == "top.u_a"
    )
    assert (
        cast(tuple[object, dict[str, Any]], await server.call_tool("semantic_diff", {}))[1][
            "status"
        ]
        == "no_previous_state"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_mcp_reload_preserves_nonempty_diff(fixture_project: FixtureProject) -> None:
    server = create_server(StaticProjectProvider({"demo": fixture_project.config}))
    await server.call_tool("project_load", {"logical_module": "demo"})
    fixture_project.design_file.write_text(
        fixture_project.design_file.read_text(encoding="utf-8").replace("WIDTH(32)", "WIDTH(16)"),
        encoding="utf-8",
    )
    await server.call_tool("project_reload", {})
    previous = cast(tuple[object, dict[str, Any]], await server.call_tool("semantic_diff", {}))[1]
    assert previous["changes"]["total_count"] > 0
    fixture_project.design_file.unlink()
    with pytest.raises(ToolError, match="missing or invalid source file"):
        await server.call_tool("project_reload", {})
    assert cast(tuple[object, dict[str, Any]], await server.call_tool("semantic_diff", {}))[1] == (
        previous
    )
    assert (
        cast(
            tuple[object, dict[str, Any]],
            await server.call_tool("find_instance", {"query": "top.u_a"}),
        )[1]["sv_module"]
        == "leaf"
    )
