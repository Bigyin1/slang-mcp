"""Exact semantic changes, baseline management and recovery after failed reloads."""

import json
from pathlib import Path

import pytest

from slang_mcp.errors import InvalidTopError, UnknownLogicalModuleError
from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService
from tests.rtl_support import load_rtl

SOURCE = """
module leaf #(parameter W=4)(input logic [W-1:0] d); endmodule
module top; leaf #(.W(8)) child('0); endmodule
"""


def test_diff_uses_latest_baseline_and_retains_previous_return_value(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, SOURCE)
    project.reload(SOURCE.replace("W(8)", "W(16)"))
    first = project.service.semantic_diff()
    assert first.changes.total_count == 1
    assert first.changes.items[0].category == "effective_parameter"
    assert first.changes.items[0].identity == "top.child.W"
    assert json.loads(first.changes.items[0].before or "null")["value"] == "8"
    project.reload(SOURCE.replace("W(8)", "W(32)"))
    assert json.loads(project.service.semantic_diff().changes.items[0].before or "null")[
        "value"
    ] == ("16")
    assert json.loads(project.service.semantic_diff().changes.items[0].after or "null")[
        "value"
    ] == ("32")
    assert json.loads(first.changes.items[0].after or "null")["value"] == "16"


def test_failed_reload_keeps_nonempty_diff_then_recovers(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, SOURCE)
    project.reload(SOURCE.replace("W(8)", "W(16)"))
    previous = project.service.semantic_diff()
    with pytest.raises(InvalidTopError):
        project.reload("module wrong_top; endmodule")
    assert project.service.semantic_diff() == previous
    assert (
        project.service.rtl.get_instance_parameters("top.child").parameters.items[0].value == "16"
    )
    project.reload(SOURCE)
    assert json.loads(project.service.semantic_diff().changes.items[0].before or "null")[
        "value"
    ] == ("16")
    assert (
        json.loads(project.service.semantic_diff().changes.items[0].after or "null")["value"] == "8"
    )


def test_added_then_removed_instance_has_null_on_correct_side(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, SOURCE)
    project.reload(SOURCE.replace("module top;", "module top; leaf added('0);"))
    added = next(
        item
        for item in project.service.semantic_diff().changes.items
        if item.category == "instance"
    )
    assert (added.identity, added.before, added.after) == ("top.added", None, "leaf")
    project.reload(SOURCE)
    removed = next(
        item
        for item in project.service.semantic_diff().changes.items
        if item.category == "instance"
    )
    assert (removed.identity, removed.before, removed.after) == ("top.added", "leaf", None)


def test_same_path_with_changed_instance_type(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path, "module a; endmodule module b; endmodule module top; a child(); endmodule"
    )
    project.reload("module a; endmodule module b; endmodule module top; b child(); endmodule")
    assert project.service.semantic_diff().changes.total_count == 1
    change = project.service.semantic_diff().changes.items[0]
    assert (change.category, change.identity, change.before, change.after) == (
        "instance",
        "top.child",
        "a",
        "b",
    )


def test_comments_and_line_shifts_leave_signatures_unchanged(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, SOURCE)
    assert not project.service.get_diagnostics()
    project.reload("// Header comment\n\n" + SOURCE.replace("W=4", "W = 4"))
    assert not project.service.get_diagnostics()
    assert project.service.semantic_diff().changes.total_count == 0


def test_diagnostic_add_remove_preserves_normalized_payload(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, "module top; endmodule\n")
    assert not project.service.get_diagnostics()
    project.reload("module top; assign q = missing; endmodule\n")
    assert project.service.project_info().summary.diagnostic_error_count > 0
    added = tuple(
        item
        for item in project.service.semantic_diff().changes.items
        if item.category == "diagnostic"
    )
    assert added
    assert all(item.before is None for item in added)
    assert any(json.loads(item.after or "null")["severity"] == "error" for item in added)
    project.reload("module top; endmodule\n")
    assert {
        (item.identity, item.before) for item in project.service.semantic_diff().changes.items
    } == {(item.identity, item.after) for item in added}
    assert all(item.after is None for item in project.service.semantic_diff().changes.items)


def test_diff_truncation_keeps_stable_prefix_and_total(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, SOURCE)
    project.reload(SOURCE.replace("W=4", "W=5").replace("W(8)", "W(9)"))
    complete = project.service.semantic_diff()
    short = project.service.semantic_diff(limit=1)
    assert complete.changes.total_count == 3
    assert short.changes.total_count == complete.changes.total_count
    assert short.changes.items == complete.changes.items[:1]
    assert short.changes.truncated
    assert not complete.changes.truncated
    assert project.service.semantic_diff() == complete


def test_switch_project_resets_baseline_but_failed_switch_does_not(tmp_path: Path) -> None:
    (tmp_path / "shared.sv").write_text(SOURCE, encoding="utf-8")
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {
                    name: ProjectConfig(name, (tmp_path / "shared.sv",), top_modules=("top",))
                    for name in ("first", "second")
                }
            )
        )
    )
    service.project_load("first")
    (tmp_path / "shared.sv").write_text(SOURCE.replace("W(8)", "W(16)"), encoding="utf-8")
    service.project_load("first")
    previous = service.semantic_diff()
    assert previous.changes.total_count == 1
    with pytest.raises(UnknownLogicalModuleError):
        service.project_load("absent")
    assert service.semantic_diff() == previous
    assert service.project_info().summary.logical_module == "first"
    service.project_load("second")
    assert service.semantic_diff().status == "no_previous_state"
    assert service.semantic_diff().changes.total_count == 0


def test_include_change_rebuilds_ports_and_parameter_defaults(tmp_path: Path) -> None:
    (tmp_path / "width.svh").write_text("`define WIDTH 4\n", encoding="utf-8")
    project = load_rtl(
        tmp_path,
        """
`include "width.svh"
module top #(parameter W=`WIDTH)(input logic [W-1:0] data); endmodule
""",
    )
    assert project.service.rtl.get_ports("top").items[0].width == 4
    (tmp_path / "width.svh").write_text("`define WIDTH 12\n", encoding="utf-8")
    project.service.project_reload()
    assert project.service.rtl.get_ports("top").items[0].width == 12
    assert {item.category for item in project.service.semantic_diff().changes.items} == {
        "port",
        "parameter",
        "effective_parameter",
    }
