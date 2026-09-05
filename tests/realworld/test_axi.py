"""Real-world semantic smoke test for PULP AXI."""

import os
from pathlib import Path

import pytest

from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService
from tests.realworld.bender import (
    BENDER_VERSION,
    BenderRequest,
    BenderSourceList,
    checkout_repository,
    generate_source_list,
    install_lockfile,
)

_ENABLED = os.environ.get("SLANG_MCP_REALWORLD") == "1"
_REPOSITORY = "https://github.com/pulp-platform/axi.git"
_REVISION = "a256a3b86394fedf19e361047fccfdd7f6ef83e4"
_LOCKFILE = Path(__file__).with_name("axi-v0.39.9.Bender.lock")


def _axi_config() -> ProjectConfig:
    source_list = _axi_sources("axi_fifo_intf")
    return ProjectConfig(
        logical_module="pulp_axi_fifo",
        source_files=source_list.sources,
        include_directories=source_list.include_directories,
        defines=source_list.defines,
        top_modules=("axi_fifo_intf",),
        metadata={
            "repository": _REPOSITORY,
            "revision": _REVISION,
            "source_list_generator": f"bender {BENDER_VERSION}",
        },
    )


def _axi_sources(top: str) -> BenderSourceList:
    checkout = checkout_repository(_REPOSITORY, _REVISION, "axi")
    install_lockfile(checkout, _LOCKFILE)
    return generate_source_list(
        BenderRequest(
            checkout,
            target="synthesis",
            defines=("COMMON_CELLS_ASSERTS_OFF",),
            top=top,
        )
    )


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_axi_fifo() -> None:
    config = _axi_config()
    service = SemanticService(
        ProjectManager(StaticProjectProvider({config.logical_module: config}))
    )

    summary = service.project_load(config.logical_module)
    fifo = service.describe_symbol("module:axi_fifo")

    assert summary.diagnostic_error_count == 0
    assert summary.source_file_count == 4
    assert summary.include_directory_count == 2
    assert summary.define_count == 3
    assert summary.top_modules == ("axi_fifo_intf",)
    assert service.find_symbol("axi_pkg")[0].kind == "package"
    assert len(fifo.parameters) >= 7
    assert len(fifo.ports) >= 7
    assert {child.name for child in service.get_hierarchy()[0].children} >= {"i_axi_fifo"}
    _check_rtl_queries(service)


def _check_rtl_queries(service: SemanticService) -> None:
    assert service.rtl.list_instances(sv_module="axi_fifo").total_count == 1
    assert service.rtl.get_parameters("axi_fifo").parameters.total_count >= 7
    assert service.rtl.get_ports("axi_fifo_intf").total_count == 5
    assert (
        service.inspection.inspect_instance("axi_fifo_intf.i_axi_fifo").connections.total_count == 7
    )
    assert service.rtl.get_signal_reads("axi_fifo_intf.slv_req").total_count > 0
    assert service.rtl.get_instance_parameters("axi_fifo_intf.i_axi_fifo").value_kind == "effective"


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_axi_multicut_elaborates_three_real_cuts(tmp_path: Path) -> None:
    service = _multicut_service(tmp_path)

    summary = service.project_load("pulp_axi_multicut")
    dut = service.inspection.inspect_instance("axi_multicut_realworld_top.dut")
    cuts = service.rtl.list_instances(sv_module="axi_cut", path_prefix="axi_multicut_realworld_top")

    assert summary.diagnostic_error_count == 0
    assert summary.source_file_count == 7
    assert {item.name: item.value for item in dut.parameters.parameters.items} == {
        "ADDR_WIDTH": "32'd32",
        "DATA_WIDTH": "32'd64",
        "ID_WIDTH": "32'd4",
        "USER_WIDTH": "32'd1",
        "NUM_CUTS": "32'd3",
    }
    assert cuts.total_count == 3
    assert {item.path.rsplit(".", 1)[-1] for item in cuts.items} == {"i_cut"}
    assert service.rtl.get_instance_connections("axi_multicut_realworld_top.dut").total_count == 4
    assert service.rtl.get_ports("axi_multicut_intf").items[2].interface == "AXI_BUS"
    assert service.rtl.get_procedural_blocks("spill_register_flushable").total_count >= 2


def _multicut_service(tmp_path: Path) -> SemanticService:
    wrapper = tmp_path / "axi_multicut_realworld_top.sv"
    wrapper.write_text(
        """
module axi_multicut_realworld_top;
  logic clk, rst_n;
  AXI_BUS #(
    .AXI_ADDR_WIDTH(32), .AXI_DATA_WIDTH(64), .AXI_ID_WIDTH(4), .AXI_USER_WIDTH(1)
  ) upstream(), downstream();
  axi_multicut_intf #(
    .ADDR_WIDTH(32), .DATA_WIDTH(64), .ID_WIDTH(4), .USER_WIDTH(1), .NUM_CUTS(3)
  ) dut (.clk_i(clk), .rst_ni(rst_n), .in(upstream), .out(downstream));
endmodule
""",
        encoding="utf-8",
    )
    source_list = _axi_sources("axi_multicut_intf")
    config = ProjectConfig(
        "pulp_axi_multicut",
        (*source_list.sources, wrapper),
        source_list.include_directories,
        source_list.defines,
        ("axi_multicut_realworld_top",),
    )
    provider = StaticProjectProvider({config.logical_module: config})
    return SemanticService(ProjectManager(provider))
