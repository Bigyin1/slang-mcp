"""Compiler preflight submits complete inventories as direct build inputs."""

import json
from pathlib import Path

import pytest

from benchmarks.validation import _project_arguments


@pytest.mark.parametrize("includes", [[], ["include", "vendor/include"]])
def test_validation_preserves_complete_ordered_build_inputs(
    tmp_path: Path, includes: list[str]
) -> None:
    sources = [str(tmp_path / name) for name in ("pkg.sv", "top.sv", "unused.sv", "top.sv")]
    directories = [str(tmp_path / name) for name in includes]
    (tmp_path / "source_files.f").write_text("\n" + "\n".join(sources) + "\n\n")
    (tmp_path / "include_directories.f").write_text("\n".join(directories) + "\n")
    (tmp_path / "top_module.txt").write_text("top\n")
    (tmp_path / "projects.json").write_text(
        json.dumps({"probe": {"defines": {"FLAG": None, "WIDTH": "8"}}})
    )
    assert _project_arguments("probe", tmp_path) == {
        "source_files": sources,
        "include_directories": directories,
        "top_module": "top",
        "defines": {"FLAG": None, "WIDTH": "8"},
    }
