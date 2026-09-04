"""Real-world semantic smoke test for PULP common_cells."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService

_ENABLED = os.environ.get("SLANG_MCP_REALWORLD") == "1"
_REPOSITORY = "https://github.com/pulp-platform/common_cells.git"
_REVISION = "9afda9abb565971649c2aa0985639c096f351171"
_BENDER_VERSION = "0.32.1"
_DEFINE_PREFIX = "+define+"
_INCLUDE_PREFIX = "+incdir+"


@dataclass(frozen=True)
class BenderSourceList:
    sources: tuple[Path, ...]
    include_directories: tuple[Path, ...]
    defines: dict[str, str | None]


@pytest.mark.realworld
@pytest.mark.skipif(not _ENABLED, reason="set SLANG_MCP_REALWORLD=1 to fetch external RTL")
def test_pulp_common_cells_fifo() -> None:
    checkout = _checkout()
    source_list = _source_list(checkout)
    config = ProjectConfig(
        logical_module="pulp_common_cells_fifo",
        source_files=source_list.sources,
        include_directories=source_list.include_directories,
        defines=source_list.defines,
        top_modules=("fifo_v3",),
        metadata={
            "repository": _REPOSITORY,
            "revision": _REVISION,
            "source_list_generator": f"bender {_BENDER_VERSION}",
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


def _source_list(checkout: Path) -> BenderSourceList:
    bender = _bender_executable()
    _require_bender_version(bender)
    base = [
        str(bender),
        "script",
        "flist-plus",
        "--no-deps",
        "-t",
        "synthesis",
        "-D",
        "COMMON_CELLS_ASSERTS_OFF",
        "-d",
        str(checkout),
    ]
    sources = tuple(Path(line) for line in _bender_lines(base, "--only-sources"))
    includes = tuple(
        Path(line.removeprefix(_INCLUDE_PREFIX))
        for line in _bender_lines(base, "--only-includes")
        if line.startswith(_INCLUDE_PREFIX)
    )
    defines = dict(
        _parse_define(line.removeprefix(_DEFINE_PREFIX))
        for line in _bender_lines(base, "--only-defines")
        if line.startswith(_DEFINE_PREFIX)
    )
    return BenderSourceList(sources, includes, defines)


def _bender_lines(base: list[str], mode: str) -> tuple[str, ...]:
    output = subprocess.run(
        [*base, mode],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _parse_define(value: str) -> tuple[str, str | None]:
    name, separator, replacement = value.partition("=")
    return name, replacement if separator else None


def _bender_executable() -> Path:
    configured = os.environ.get("BENDER_EXECUTABLE")
    discovered = shutil.which("bender")
    local = Path(__file__).parents[2] / ".tools/bender"
    candidates = [Path(configured)] if configured is not None else []
    candidates.extend(Path(path) for path in (discovered, local) if path is not None)
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        pytest.fail("Bender not found; install 0.32.1 or set BENDER_EXECUTABLE")
    return executable


def _require_bender_version(executable: Path) -> None:
    output = subprocess.run(
        [str(executable), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if output != f"bender {_BENDER_VERSION}":
        pytest.fail(f"expected bender {_BENDER_VERSION}, found: {output}")


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
