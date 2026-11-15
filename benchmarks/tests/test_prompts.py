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
