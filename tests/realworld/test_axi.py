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
    checkout_repository,
    generate_source_list,
    install_lockfile,
)

_ENABLED = os.environ.get("SLANG_MCP_REALWORLD") == "1"
_REPOSITORY = "https://github.com/pulp-platform/axi.git"
_REVISION = "a256a3b86394fedf19e361047fccfdd7f6ef83e4"
_LOCKFILE = Path(__file__).with_name("axi-v0.39.9.Bender.lock")


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_axi_fifo() -> None:
    checkout = checkout_repository(_REPOSITORY, _REVISION, "axi")
    install_lockfile(checkout, _LOCKFILE)
    source_list = generate_source_list(
        BenderRequest(
            checkout,
            target="synthesis",
            defines=("COMMON_CELLS_ASSERTS_OFF",),
            top="axi_fifo_intf",
        )
    )
    config = ProjectConfig(
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
    service = SemanticService(
        ProjectManager(StaticProjectProvider({config.logical_module: config}))
    )

    summary = service.project_load(config.logical_module)
    package = service.find_symbol("axi_pkg")
    fifo = service.describe_symbol("module:axi_fifo")
    hierarchy = service.get_hierarchy()[0]

    assert summary.diagnostic_error_count == 0
    assert summary.source_file_count == 4
    assert summary.include_directory_count == 2
    assert summary.define_count == 3
    assert summary.top_modules == ("axi_fifo_intf",)
    assert package[0].kind == "package"
    assert len(fifo.parameters) >= 7
    assert len(fifo.ports) >= 7
    assert {child.name for child in hierarchy.children} >= {"i_axi_fifo"}
