"""Semantic symbol query tests."""

import pytest

from slang_mcp.errors import AmbiguousSymbolError, SymbolNotFoundError
from slang_mcp.services import SemanticService


@pytest.fixture
def loaded(service: SemanticService) -> SemanticService:
    service.project_load("demo")
    return service


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("top", "module"),
        ("bus_if", "interface"),
        ("types_pkg", "package"),
        ("packet", "classtype"),
        ("word_t", "typealias"),
        ("identity", "function"),
        ("clear", "task"),
        ("state", "variable"),
        ("ready", "net"),
    ],
)
def test_find_declaration_kinds(loaded: SemanticService, name: str, kind: str) -> None:
    matches = loaded.find_symbol(name)

    assert matches
    assert kind in {item.kind for item in matches}
    assert all(item.location.filename for item in matches)


def test_describe_module_has_elaborated_signature(loaded: SemanticService) -> None:
    description = loaded.describe_symbol("module:leaf")

    assert description.symbol.kind == "module"
    assert [(port.name, port.direction, port.width) for port in description.ports] == [
        ("i", "in", 32),
        ("o", "out", 32),
    ]
    assert description.parameters[0].name == "WIDTH"
    assert description.parameters[0].value == "32"


def test_describe_port_has_type_width_and_direction(loaded: SemanticService) -> None:
    match = next(item for item in loaded.find_symbol("i") if item.kind == "port")

    description = loaded.describe_symbol(match.symbol_id)

    assert description.type == "logic[31:0]"
    assert description.width == 32
    assert description.direction == "in"


def test_describe_typedef_has_target_type(loaded: SemanticService) -> None:
    description = loaded.describe_symbol("typealias:types_pkg::word_t")

    assert description.type == "logic[7:0]"
    assert description.width == 8


def test_ambiguous_exact_name_requires_stable_id(loaded: SemanticService) -> None:
    assert len(loaded.find_symbol("WIDTH")) > 1

    with pytest.raises(AmbiguousSymbolError, match="use one of"):
        loaded.describe_symbol("WIDTH")


def test_unknown_symbol_is_controlled(loaded: SemanticService) -> None:
    assert loaded.find_symbol("does_not_exist") == ()
    with pytest.raises(SymbolNotFoundError, match="unknown symbol"):
        loaded.describe_symbol("does_not_exist")
