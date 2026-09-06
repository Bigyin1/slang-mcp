"""Corpus checks independent of agent/API calls and optional compiler preflight."""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

from benchmarks.dataset import ROOT, load_cases, read_object
from benchmarks.runner.projects import prepare_project
from slang_mcp.project import ProjectManager
from slang_mcp.providers.static import StaticProjectProvider
from slang_mcp.services import SemanticService

CORPUS_SIZE = 15
PILOT_SIZE = 10


def validate() -> dict[str, object]:
    cases = load_cases()
    projects = read_object(ROOT / "cases/projects.json")
    for case in cases:
        if case.project not in projects:
            raise ValueError(f"Unknown project: {case.project}")
    if len(cases) != CORPUS_SIZE or sum(case.pilot for case in cases) != PILOT_SIZE:
        raise ValueError("Expected curated 15-case corpus and 10-case pilot")
    return {
        "cases": len(cases),
        "pilot": sum(case.pilot for case in cases),
        "categories": dict(Counter(case.category for case in cases)),
    }


def validate_builds() -> dict[str, object]:
    results: dict[str, object] = {}
    for name in read_object(ROOT / "cases/projects.json"):
        with tempfile.TemporaryDirectory(prefix="slang-validate-", dir="/private/tmp") as directory:
            results[name] = _validate_build(name, Path(directory))
    return results


def _validate_build(name: str, workspace: Path) -> dict[str, object]:
    prepare_project(name, workspace)
    service = SemanticService(
        ProjectManager(StaticProjectProvider.from_json(workspace / "projects.json"))
    )
    summary = service.project_load(name)
    return {"errors": summary.diagnostic_error_count, "sources": summary.source_file_count}
