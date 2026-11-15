"""Small Git-backed frozen experiment for audit corruption tests."""

from dataclasses import replace
from pathlib import Path

from git import Actor, Repo

from benchmarks.research_compare.audit import AuditRequest
from benchmarks.research_compare.audit_freeze import DEPENDENCIES
from benchmarks.research_compare.audit_integrity import digest
from benchmarks.runner.storage import write_json


def make_request(tmp_path: Path) -> AuditRequest:
    directory = tmp_path / "benchmarks/research_compare"
    directory.mkdir(parents=True)
    request = AuditRequest(
        tmp_path / "runs",
        tmp_path / "export",
        directory / "inputs.json",
        directory / "protocol.json",
    )
    (tmp_path / "binary").write_text("binary")
    _manifest(request, tmp_path)
    _sources(directory)
    write_json(
        request.inputs,
        {"case": {"files": {"rtl/top.sv": digest(directory / "cases/case/rtl/top.sv")}}},
    )
    write_json(
        request.protocol,
        {
            "total_runs": 2,
            "real_rtl_cases": ["case"],
            "synthetic_controls": [],
            "server_sha256": digest(tmp_path / "binary"),
            "files": {
                name: digest(directory / name)
                for name in (
                    "manifest.json",
                    "skill.md",
                    "cases/case/task.txt",
                    "cases/case/rtl/top.sv",
                )
            },
        },
    )
    return replace(request, revision=_commit(tmp_path))


def _manifest(request: AuditRequest, tmp_path: Path) -> None:
    write_json(
        request.runs / "manifest.json",
        {
            "codex": str(tmp_path / "codex"),
            "binary": str(tmp_path / "binary"),
            "skill": str(request.inputs.parent / "skill.md"),
            "model": "frozen",
            "effort": "max",
            "timeout": 1,
            "cases": [
                {
                    "id": "case",
                    "workspace": str(tmp_path / "input"),
                    "task": str(request.inputs.parent / "cases/case/task.txt"),
                }
            ],
            "runs": [
                {"id": arm, "case_id": "case", "arm": arm, "repetition": 1}
                for arm in ("text-only", "mcp+skill")
            ],
        },
    )
    (request.inputs.parent / "manifest.json").write_bytes(
        (request.runs / "manifest.json").read_bytes()
    )


def _sources(directory: Path) -> None:
    for name in ("models.py", "prompts.py", "runner.py", "traces.py"):
        (directory / name).write_bytes((Path(__file__).parents[1] / name).read_bytes())
    (directory / "skill.md").write_text("Frozen skill")
    (directory / "cases/case/rtl").mkdir(parents=True)
    (directory / "cases/case/task.txt").write_text("Frozen task")
    (directory / "cases/case/rtl/top.sv").write_text("module top; endmodule\n")
    (directory / "oracles").mkdir()
    (directory / "oracles/expected.json").write_text('{"facts": ["frozen"]}\n')
    for name in DEPENDENCIES:
        (directory.parents[1] / name).parent.mkdir(parents=True, exist_ok=True)
        (directory.parents[1] / name).write_bytes((Path(__file__).parents[3] / name).read_bytes())


def _commit(root: Path) -> str:
    with Repo.init(root) as repo:
        repo.index.add(
            [
                str(path.relative_to(root))
                for path in (root / "benchmarks").rglob("*")
                if path.is_file()
            ]
        )
        return repo.index.commit(
            "freeze test fixture",
            author=Actor("Test", "test@example.invalid"),
            committer=Actor("Test", "test@example.invalid"),
        ).hexsha
