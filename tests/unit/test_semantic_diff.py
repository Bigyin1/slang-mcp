"""Snapshot lifecycle and meaningful changes across real compilations."""

from pathlib import Path

import pytest

from slang_mcp.errors import InvalidProjectConfigError, InvalidTopError
from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService

BASE = """
module leaf #(parameter WIDTH=32)(input logic [WIDTH-1:0] data); endmodule
module top; leaf #(.WIDTH(64)) u_leaf('0); endmodule
"""


def create_service(tmp_path: Path, source: str = BASE) -> SemanticService:
    (tmp_path / "diff.sv").write_text(source, encoding="utf-8")
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {
                    "diff": ProjectConfig("diff", (tmp_path / "diff.sv",), top_modules=("top",)),
                }
            )
        )
    )
    service.project_load("diff")
    return service


@pytest.mark.parametrize(
    ("before", "after", "category"),
    [
        (BASE, BASE.replace(" u_leaf('0);", " u_leaf('0); leaf extra('0);"), "instance"),
        (BASE, BASE.replace("leaf #(.WIDTH(64)) u_leaf('0);", ""), "instance"),
        (BASE, BASE.replace("WIDTH=32", "WIDTH=16"), "port"),
        (BASE, BASE.replace("WIDTH(64)", "WIDTH(8)"), "effective_parameter"),
        (BASE, BASE.replace("module top;", "module top; assign absent = missing;"), "diagnostic"),
        (BASE.replace("module top;", "module top; assign absent = missing;"), BASE, "diagnostic"),
        (BASE, BASE + "\nmodule added; endmodule", "definition"),
        (BASE, BASE.replace("parameter WIDTH=32", "parameter WIDTH=32, EXTRA=2"), "parameter"),
    ],
)
def test_changes(tmp_path: Path, before: str, after: str, category: str) -> None:
    service = create_service(tmp_path, before)
    (tmp_path / "diff.sv").write_text(after, encoding="utf-8")
    service.project_reload()
    assert category in {item.category for item in service.semantic_diff().changes.items}


def test_initial_and_unchanged(tmp_path: Path) -> None:
    service = create_service(tmp_path)
    assert service.semantic_diff().status == "no_previous_state"
    service.project_reload()
    assert service.semantic_diff().status == "compared"
    assert service.semantic_diff().changes.total_count == 0


def test_failed_reload_retains_state(tmp_path: Path) -> None:
    service = create_service(tmp_path)
    (tmp_path / "diff.sv").unlink()
    with pytest.raises(InvalidProjectConfigError):
        service.project_reload()
    assert service.rtl.find_instance("top.u_leaf").sv_module == "leaf"
    assert service.semantic_diff().status == "no_previous_state"


def test_failed_elaboration_retains_diff(tmp_path: Path) -> None:
    service = create_service(tmp_path)
    service.project_reload()
    (tmp_path / "diff.sv").write_text("module other; endmodule", encoding="utf-8")
    with pytest.raises(InvalidTopError):
        service.project_reload()
    assert service.semantic_diff().changes.total_count == 0
    assert service.rtl.find_instance("top.u_leaf").sv_module == "leaf"
