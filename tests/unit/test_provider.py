"""Static project provider tests."""

import json
from pathlib import Path

import pytest

from slang_mcp.errors import InvalidProjectConfigError, UnknownLogicalModuleError
from slang_mcp.models import ProjectConfig
from slang_mcp.providers import StaticProjectProvider


def test_resolve_preserves_complete_project_config(tmp_path: Path) -> None:
    first = tmp_path / "first.sv"
    second = tmp_path / "second.sv"
    config = ProjectConfig(
        "core", (first, second), (tmp_path / "include",), {"WIDTH": "32"}, ("top",)
    )

    resolved = StaticProjectProvider({"core": config}).resolve("core")

    assert resolved.source_files == (first, second)
    assert resolved.include_directories == (tmp_path / "include",)
    assert resolved.defines == {"WIDTH": "32"}
    assert resolved.top_modules == ("top",)


def test_unknown_logical_module_is_controlled() -> None:
    provider = StaticProjectProvider({})

    with pytest.raises(UnknownLogicalModuleError, match="unknown logical module"):
        provider.resolve("missing")


def test_json_provider_resolves_relative_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "projects.json"
    config_path.write_text(
        json.dumps(
            {
                "core": {
                    "source_files": ["rtl/pkg.sv", "rtl/top.sv"],
                    "include_directories": ["include"],
                    "defines": {"FEATURE": None, "WIDTH": "16"},
                    "top_modules": ["top"],
                    "metadata": {"owner": "rtl"},
                }
            }
        ),
        encoding="utf-8",
    )

    resolved = StaticProjectProvider.from_json(config_path).resolve("core")

    assert resolved.source_files == (
        (tmp_path / "rtl/pkg.sv").resolve(),
        (tmp_path / "rtl/top.sv").resolve(),
    )
    assert resolved.metadata == {"owner": "rtl"}


@pytest.mark.parametrize("content", ["[]", '{"core": []}', '{"core": {"source_files": []}}'])
def test_json_provider_rejects_invalid_shapes(tmp_path: Path, content: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(InvalidProjectConfigError):
        StaticProjectProvider.from_json(path)
