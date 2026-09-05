"""Real-world semantic smoke test for PULP common_cells."""

import os
from pathlib import Path

import pytest

from slang_mcp.models import HierarchyNode, ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService
from tests.realworld.bender import (
    BENDER_VERSION,
    BenderRequest,
    BenderSourceList,
    checkout_repository,
    generate_source_list,
)

_ENABLED = os.environ.get("SLANG_MCP_REALWORLD") == "1"
_REPOSITORY = "https://github.com/pulp-platform/common_cells.git"
_REVISION = "9afda9abb565971649c2aa0985639c096f351171"


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_common_cells_fifo() -> None:
    source_list = _source_list()
    config = ProjectConfig(
        logical_module="pulp_common_cells_fifo",
        source_files=source_list.sources,
        include_directories=source_list.include_directories,
        defines=source_list.defines,
        top_modules=("fifo_v3",),
        metadata={
            "repository": _REPOSITORY,
            "revision": _REVISION,
            "source_list_generator": f"bender {BENDER_VERSION}",
        },
    )
    service = SemanticService(
        ProjectManager(StaticProjectProvider({config.logical_module: config}))
    )

    summary = service.project_load(config.logical_module)
    fifo = service.describe_symbol("module:fifo_v3")

    assert summary.diagnostic_error_count == 0
    assert summary.source_file_count == 94
    assert summary.include_directory_count == 1
    assert summary.define_count == 3
    assert summary.top_modules == ("fifo_v3",)
    assert service.find_symbol("cf_math_pkg")[0].kind == "package"
    assert len(fifo.parameters) >= 5
    assert len(fifo.ports) >= 10
    assert {child.name for child in service.get_hierarchy()[0].children} & {
        "gen_fifo",
        "gen_pass_through",
    }
    _check_rtl_queries(service)


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_common_cells_lzc_elaborates_non_power_of_two_tree(tmp_path: Path) -> None:
    service = _lzc_service(tmp_path)

    summary = service.project_load("pulp_common_cells_lzc")
    dut = service.inspection.inspect_instance("lzc_realworld_top.dut")

    assert summary.diagnostic_error_count == 0
    assert summary.source_file_count == 3
    assert {item.name: item.value for item in dut.parameters.parameters.items} == {
        "WIDTH": "32'd13",
        "MODE": "1'b1",
        "CNT_WIDTH": "32'd4",
    }
    assert [(item.port.name, item.port.width) for item in dut.connections.items] == [
        ("in_i", 13),
        ("cnt_o", 4),
        ("empty_o", 1),
    ]
    hierarchy_paths = _hierarchy_paths(service.get_hierarchy("lzc_realworld_top")[0])
    assert sum("g_index_lut[" in path for path in hierarchy_paths) == 13
    assert any(path.endswith("g_reduce") for path in hierarchy_paths)
    assert service.rtl.get_procedural_blocks("lzc").items[0].kind == "AlwaysComb"
    assert service.rtl.get_signal_reads("lzc_realworld_top.dut.in_i").total_count == 3


def _lzc_service(tmp_path: Path) -> SemanticService:
    wrapper = tmp_path / "lzc_realworld_top.sv"
    wrapper.write_text(
        """
module lzc_realworld_top;
  logic [12:0] input_data;
  logic [3:0] zero_count;
  logic empty;
  lzc #(.WIDTH(13), .MODE(1'b1)) dut (
    .in_i(input_data), .cnt_o(zero_count), .empty_o(empty)
  );
endmodule
""",
        encoding="utf-8",
    )
    source_list = _source_list("lzc")
    config = ProjectConfig(
        "pulp_common_cells_lzc",
        (*source_list.sources, wrapper),
        source_list.include_directories,
        source_list.defines,
        ("lzc_realworld_top",),
    )
    provider = StaticProjectProvider({config.logical_module: config})
    return SemanticService(ProjectManager(provider))


def _source_list(top: str | None = None) -> BenderSourceList:
    return generate_source_list(
        BenderRequest(
            checkout_repository(_REPOSITORY, _REVISION, "common_cells"),
            target="synthesis",
            defines=("COMMON_CELLS_ASSERTS_OFF",),
            top=top,
            no_dependencies=True,
        )
    )


def _hierarchy_paths(node: HierarchyNode) -> tuple[str, ...]:
    return (node.path, *tuple(path for child in node.children for path in _hierarchy_paths(child)))


def _check_rtl_queries(service: SemanticService) -> None:
    assert service.rtl.get_ports("fifo_v3").total_count >= 10
    assert service.rtl.get_parameters("fifo_v3").parameters.total_count >= 5
    assert service.rtl.get_signal_reads("fifo_v3.push_i").total_count > 0
    assert service.rtl.get_procedural_blocks("fifo_v3").total_count > 0
    assert service.rtl.get_state_elements("fifo_v3").total_count > 0
