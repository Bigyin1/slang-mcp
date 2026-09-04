"""Public service lifecycle error tests."""

from collections.abc import Callable

import pytest

from slang_mcp.errors import ProjectNotLoadedError, UnknownLogicalModuleError
from slang_mcp.services import SemanticService


@pytest.mark.parametrize(
    "operation",
    [
        lambda service: service.project_info(),
        lambda service: service.project_reload(),
        lambda service: service.get_diagnostics(),
        lambda service: service.find_symbol("top"),
        lambda service: service.get_hierarchy(),
    ],
)
def test_queries_require_loaded_project(
    service: SemanticService,
    operation: Callable[[SemanticService], object],
) -> None:
    with pytest.raises(ProjectNotLoadedError, match="no project"):
        operation(service)


def test_unknown_logical_module(service: SemanticService) -> None:
    with pytest.raises(UnknownLogicalModuleError):
        service.project_load("missing")
