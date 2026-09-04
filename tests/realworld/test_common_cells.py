"""Real-world semantic smoke test for PULP common_cells."""

import os
import subprocess
from pathlib import Path

import pytest

from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService

_ENABLED = os.environ.get("SLANG_MCP_REALWORLD") == "1"
_REPOSITORY = "https://github.com/pulp-platform/common_cells.git"
_REVISION = "9afda9abb565971649c2aa0985639c096f351171"


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_common_cells_fifo() -> None:
    checkout = _checkout()
    config = ProjectConfig(
        logical_module="pulp_common_cells_fifo",
        source_files=(checkout / "src/cf_math_pkg.sv", checkout / "src/fifo_v3.sv"),
        include_directories=(checkout / "include",),
        defines={"COMMON_CELLS_ASSERTS_OFF": None},
        top_modules=("fifo_v3",),
        metadata={"repository": _REPOSITORY, "revision": _REVISION},
    )
    service = SemanticService(
        ProjectManager(StaticProjectProvider({config.logical_module: config}))
    )

    summary = service.project_load(config.logical_module)
    package = service.find_symbol("cf_math_pkg")
    fifo = service.describe_symbol("module:fifo_v3")
    hierarchy = service.get_hierarchy()[0]

    assert summary.diagnostic_error_count == 0
    assert summary.top_modules == ("fifo_v3",)
    assert package[0].kind == "package"
    assert len(fifo.parameters) >= 5
    assert len(fifo.ports) >= 10
    assert {child.name for child in hierarchy.children} & {"gen_fifo", "gen_pass_through"}


def _checkout() -> Path:
    root = Path(__file__).parents[2] / ".realworld-cache/common_cells"
    if not (root / ".git").is_dir():
        root.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", _REPOSITORY, str(root)],
            check=True,
        )
    current = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current != _REVISION:
        subprocess.run(
            ["git", "-C", str(root), "checkout", "--detach", _REVISION],
            check=True,
        )
    return root
