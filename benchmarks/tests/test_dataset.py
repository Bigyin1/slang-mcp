"""Frozen dataset, contracts and workspace exports."""

import json
from pathlib import Path

import pytest

from benchmarks.cli import parser
from benchmarks.dataset import load_cases
from benchmarks.models import Settings
from benchmarks.runner.projects import _bender_targets, _copy_cached_directories, prepare_project
from benchmarks.runner.schedule import Selection, schedule, select_cases
from benchmarks.scorers.exact import normalize, score
from benchmarks.validation import validate


def test_frozen_corpus() -> None:
    assert validate()["cases"] == 19
    assert sum(case.pilot for case in load_cases()) == 10


def test_duplicate_case_rejected(tmp_path: Path) -> None:
    source = Path("benchmarks/cases/corpus.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    data["cases"].append(data["cases"][0])
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate"):
        load_cases(path)


@pytest.mark.parametrize(
    ("answer", "contract", "expected"),
    [
        ("  +7\n", "integer", 7),
        ('["b", "a"]', "array", ["b", "a"]),
        ("top.lanes[3].u_worker\n", "path", "top.lanes[3].u_worker"),
    ],
)
def test_normalization(answer: str, contract: str, expected: object) -> None:
    assert normalize(answer, contract) == expected


@pytest.mark.parametrize("answer", ["3.0", "three", "```\n3\n```", "3 ports", "true"])
def test_no_semantic_repair(answer: str) -> None:
    case = next(case for case in load_cases() if case.id == "hier_generate")
    assert not score(case, answer)


def test_workspace_contains_no_oracles_and_is_fresh(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    prepare_project("hierarchy", first)
    (first / "answer.txt").write_text("contamination")
    prepare_project("hierarchy", second)
    assert not (second / "answer.txt").exists()
    assert not any("oracle" in path.name for path in second.rglob("*"))
    assert not (second / ".git").exists()
    assert (second / "projects.json").exists()


def test_randomization_is_reproducible_and_paired() -> None:
    cases = tuple(case for case in load_cases() if case.pilot)
    plan = schedule(cases, Settings(), Selection())
    assert len(plan) == 90
    assert plan == schedule(cases, Settings(), Selection())
    for offset in range(0, len(plan), 3):
        block = plan[offset : offset + 3]
        assert len({(key.case_id, key.repetition) for key in block}) == 1
        assert {key.mode for key in block} == {"text-only", "mcp", "mcp+skill"}


def test_default_cli_only_schedules_three_runs() -> None:
    args = parser().parse_args(["run"])
    assert args.profile == "smoke"
    assert args.repetitions is None
    settings = Settings(profile="smoke", repetitions=1)
    cases = select_cases(load_cases(), settings, Selection())
    assert len(schedule(cases, settings, Selection())) == 3


def test_cli_accepts_multiple_case_filters() -> None:
    args = parser().parse_args(["list", "--case", "hier_generate", "--case", "type_override"])
    selection = Selection(case=tuple(args.case))
    cases = select_cases(load_cases(), Settings(), selection)
    assert {case.id for case in cases} == {"hier_generate", "type_override"}


def test_json_scalar_not_accepted_for_array() -> None:
    with pytest.raises(ValueError, match="shape"):
        normalize("3", "array")


def test_multiple_bender_targets_are_preserved() -> None:
    assert _bender_targets({"targets": ["rtl", "synth"]}) == ("rtl", "synth")


def test_cached_rtl_directory_is_copied(tmp_path: Path) -> None:
    cache, destination = tmp_path / "cache", tmp_path / "destination"
    source = cache / "vendor/local_dependency"
    source.mkdir(parents=True)
    (source / "module.sv").write_text("module local_dependency; endmodule\n")

    _copy_cached_directories(
        {"cached_directories": ["vendor/local_dependency"]}, cache, destination
    )

    assert (destination / "vendor/local_dependency/module.sv").read_text().startswith("module")


def test_cva6_project_uses_a_pinned_target_and_local_rtl_dependency() -> None:
    projects = json.loads(Path("benchmarks/cases/projects.json").read_text(encoding="utf-8"))
    project = projects["cva6_cv64a6_imafdc_sv39"]
    assert project["commit"] == "76b556c8fcd30585643a579612bf52fcf5b2ff81"
    assert project["bender"]["target"] == "cv64a6_imafdc_sv39"
    assert project["cached_directories"] == ["core/cache_subsystem/hpdcache"]
