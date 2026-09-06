"""Elaborated hierarchy and instance description tests."""

import pytest

from slang_mcp.errors import InstanceNotFoundError, InvalidTopError
from slang_mcp.models import HierarchyNode
from slang_mcp.services import SemanticService


@pytest.fixture
def loaded(service: SemanticService) -> SemanticService:
    service.project_load("demo")
    return service


def test_nested_instance_hierarchy(loaded: SemanticService) -> None:
    top = loaded.get_hierarchy()[0]
    branch = _child(top, "u_b")

    assert top.path == "top"
    assert top.sv_module == "top"
    assert _child(branch, "u_c").sv_module == "leaf"


def test_parameterized_instance_description(loaded: SemanticService) -> None:
    instance = loaded.describe_instance("top.u_a")

    assert instance.sv_module == "leaf"
    assert instance.parameters[0].name == "WIDTH"
    assert instance.parameters[0].value == "32"
    assert [port.name for port in instance.ports] == ["i", "o"]
    assert [connection.port for connection in instance.connections] == ["i", "o"]


def test_generate_blocks_are_elaborated(loaded: SemanticService) -> None:
    top = loaded.get_hierarchy()[0]
    generated = _child(top, "generated")

    assert generated.kind == "generate_array"
    assert len(generated.children) == 2
    assert {node.path for node in generated.children} == {"top.generated[0]", "top.generated[1]"}
    assert all(_child(node, "u_generated").sv_module == "leaf" for node in generated.children)
    assert _child(_child(top, "enabled"), "u_conditional").sv_module == "leaf"


def test_max_depth_bounds_result(loaded: SemanticService) -> None:
    top = loaded.get_hierarchy(max_depth=1)[0]

    assert top.children
    assert all(not child.children for child in top.children)


def test_select_root_and_invalid_root(loaded: SemanticService) -> None:
    assert loaded.get_hierarchy(root="top")[0].name == "top"
    nested = loaded.get_hierarchy(root="top.u_b")[0]
    assert nested.path == "top.u_b"
    assert [child.path for child in nested.children] == ["top.u_b.u_c"]

    generated = loaded.get_hierarchy(root="top.generated[0]")[0]
    assert [child.path for child in generated.children] == ["top.generated[0].u_generated"]

    with pytest.raises(InvalidTopError, match="unknown hierarchy root"):
        loaded.get_hierarchy(root="missing")


def test_invalid_instance_path_is_controlled(loaded: SemanticService) -> None:
    with pytest.raises(InstanceNotFoundError, match="unknown elaborated instance"):
        loaded.describe_instance("top.missing")


def _child(node: HierarchyNode, name: str) -> HierarchyNode:
    return next(child for child in node.children if child.name == name)
