"""Treatment instructions must match the tools available to the agent."""

import pytest

from benchmarks.models import Case
from benchmarks.runner.run import prompt


@pytest.mark.parametrize("mode", ["text-only", "mcp", "mcp+skill"])
def test_prompt_matches_treatment_and_hides_oracle(mode: str) -> None:
    case = Case("probe", "symbols", "symbols", "Find the declaration.", "string", "secret", "why")
    text = prompt(case, mode)
    assert ("Call project_load" in text) == (mode != "text-only")
    assert "workspace/projects.json" not in text
    assert case.question in text
    assert "secret" not in text


@pytest.mark.parametrize("mode", ["mcp", "mcp+skill"])
def test_mcp_prompt_lets_agent_choose_relevant_sources(mode: str) -> None:
    case = Case("probe", "symbols", "symbols", "Find the declaration.", "string", "secret", "why")
    text = prompt(case, mode)
    assert "smallest relevant" in text
    assert "inventory order" in text
    assert "source_files" in text
    assert "include_directories" in text
    assert "dependencies" in text
    assert "single_unit defaults to true" in text
    assert "source_file_lists" not in text
    assert "include_directory_lists" not in text
    assert "project_load_partial" not in text


@pytest.mark.parametrize(
    ("token", "present"),
    [
        ("get_references", True),
        ('kind="read"', True),
        ('kind="write"', True),
        ("read_write", True),
        ('fields=["parameters"]', True),
        ('fields=["connections"]', True),
        ("get_instance_parameters", False),
        ("get_instance_connections", False),
        ("trace_connectivity", False),
        ("get_drivers", False),
        ("get_loads", False),
    ],
)
def test_semantic_skill_uses_current_access_and_inspection_tools(token: str, present: bool) -> None:
    case = Case("probe", "symbols", "symbols", "Find the declaration.", "string", "secret", "why")
    text = prompt(case, "mcp+skill")
    assert (token in text) == present
