"""Compilation configuration and diagnostics tests."""

from pathlib import Path

import pytest

from slang_mcp.errors import InvalidProjectConfigError, InvalidTopError
from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService
from tests.conftest import FixtureProject


def test_valid_project_uses_includes_defines_and_package(
    service: SemanticService,
) -> None:
    summary = service.project_load("demo")

    assert summary.source_file_count == 2
    assert summary.include_directory_count == 1
    assert summary.define_count == 2
    assert summary.top_modules == ("top",)
    assert service.find_symbol("PKG_WIDTH")[0].kind == "parameter"
    assert service.find_symbol("u_extra") == ()
    hierarchy = service.get_hierarchy()
    assert any(child.name == "u_extra" for child in hierarchy[0].children)


def test_syntax_error_is_structured(tmp_path: Path) -> None:
    service = _service_for_text(tmp_path, "module top logic value; endmodule")

    summary = service.project_load("bad")
    diagnostic = service.get_diagnostics()[0]

    assert summary.diagnostic_error_count >= 1
    assert diagnostic.severity == "error"
    assert diagnostic.location.filename is not None
    assert diagnostic.location.filename.endswith("bad.sv")
    assert diagnostic.location.line == 1
    assert diagnostic.location.column is not None


def test_semantic_error_is_structured(tmp_path: Path) -> None:
    service = _service_for_text(
        tmp_path,
        "module top; logic value; assign value = missing; endmodule",
    )

    service.project_load("bad")
    diagnostics = service.get_diagnostics(severity="error")

    assert any("undeclared identifier" in item.message for item in diagnostics)
    assert all(item.code for item in diagnostics)


def test_missing_source_fails_before_compilation(tmp_path: Path) -> None:
    config = ProjectConfig("bad", (tmp_path / "missing.sv",))
    service = SemanticService(ProjectManager(StaticProjectProvider({"bad": config})))

    with pytest.raises(InvalidProjectConfigError, match="source file"):
        service.project_load("bad")


def test_missing_include_directory_fails(
    fixture_project: FixtureProject,
    tmp_path: Path,
) -> None:
    config = ProjectConfig(
        "bad",
        fixture_project.config.source_files,
        (tmp_path / "missing",),
    )
    service = SemanticService(ProjectManager(StaticProjectProvider({"bad": config})))

    with pytest.raises(InvalidProjectConfigError, match="include directory"):
        service.project_load("bad")


def test_diagnostic_limit_and_filter_validation(tmp_path: Path) -> None:
    text = "module top; assign a = b; assign c = d; endmodule"
    service = _service_for_text(tmp_path, text)
    service.project_load("bad")

    assert len(service.get_diagnostics(limit=1)) == 1
    with pytest.raises(ValueError, match="limit"):
        service.get_diagnostics(limit=501)
    with pytest.raises(ValueError, match="severity"):
        service.get_diagnostics(severity="severe")


def test_invalid_configured_top_is_controlled(tmp_path: Path) -> None:
    source = tmp_path / "valid.sv"
    source.write_text("module actual_top; endmodule", encoding="utf-8")
    config = ProjectConfig("bad", (source,), top_modules=("missing_top",))
    service = SemanticService(ProjectManager(StaticProjectProvider({"bad": config})))

    with pytest.raises(InvalidTopError, match="missing_top"):
        service.project_load("bad")


def _service_for_text(tmp_path: Path, text: str) -> SemanticService:
    source = tmp_path / "bad.sv"
    source.write_text(text, encoding="utf-8")
    config = ProjectConfig("bad", (source,), top_modules=("top",))
    return SemanticService(ProjectManager(StaticProjectProvider({"bad": config})))
