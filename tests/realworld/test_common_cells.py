"""Real-world semantic smoke test for PULP common_cells."""

import os

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
)

_ENABLED = os.environ.get("SLANG_MCP_REALWORLD") == "1"
_REPOSITORY = "https://github.com/pulp-platform/common_cells.git"
_REVISION = "9afda9abb565971649c2aa0985639c096f351171"


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_common_cells_fifo() -> None:
    checkout = checkout_repository(_REPOSITORY, _REVISION, "common_cells")
    source_list = generate_source_list(
        BenderRequest(
            checkout,
            target="synthesis",
            defines=("COMMON_CELLS_ASSERTS_OFF",),
            no_dependencies=True,
        )
    )
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
    package = service.find_symbol("cf_math_pkg")
    fifo = service.describe_symbol("module:fifo_v3")
    hierarchy = service.get_hierarchy()[0]

    assert summary.diagnostic_error_count == 0
    assert summary.source_file_count == 94
    assert summary.include_directory_count == 1
    assert summary.define_count == 3
    assert summary.top_modules == ("fifo_v3",)
    assert package[0].kind == "package"
    assert len(fifo.parameters) >= 5
    assert len(fifo.ports) >= 10
    assert {child.name for child in hierarchy.children} & {"gen_fifo", "gen_pass_through"}
