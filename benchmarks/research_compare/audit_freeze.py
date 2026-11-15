"""Anchor integrity checks to the Git commit made before experimental runs."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from git import Repo
from git.objects import Blob, Tree

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit_integrity import digest
from benchmarks.research_compare.models import Plan, Run, load_plan
from benchmarks.research_compare.prompts import build_prompt
from benchmarks.research_compare.runner import Request, command

# This commit was created before the 24 scheduled CLI runs were started.
FROZEN_REVISION = "9de333a"
DEPENDENCIES = (
    "benchmarks/runner/process.py",
    "benchmarks/runner/storage.py",
    "benchmarks/adapters/traces.py",
)


@dataclass(frozen=True)
class Snapshot:
    root: Path
    directory: Path
    revision: str
    files: dict[str, bytes]

    def read(self, name: str) -> bytes:
        return self.files[str(self.directory / name)]

    def json(self, name: str) -> dict[str, object]:
        return object_dict(json.loads(self.read(name)))


@dataclass(frozen=True)
class ArtifactSource:
    """Reconstruct a task from one package with builders frozen in another."""

    builders: Snapshot
    task: str


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_snapshot(directory: Path, revision: str) -> Snapshot:
    with Repo(directory, search_parent_directories=True) as repo:
        root = Path(str(repo.working_tree_dir))
        commit = repo.commit(revision)
        return Snapshot(
            root,
            directory.resolve().relative_to(root),
            commit.hexsha,
            _files(commit.tree, directory.resolve().relative_to(root)),
        )


def _files(tree: Tree, directory: Path) -> dict[str, bytes]:
    subtree = tree if directory == Path() else tree / str(directory)
    files = {
        str(entry.path): bytes(entry.data_stream.read())
        for entry in subtree.traverse()
        if isinstance(entry, Blob)
    }
    for name in DEPENDENCIES:
        files[name] = bytes((tree / name).data_stream.read())
    return files


def frozen_plan(snapshot: Snapshot) -> Plan:
    """Use committed manifest bytes without changing the frozen working files."""
    with tempfile.TemporaryDirectory(prefix="slang-audit-", dir="/private/tmp") as directory:
        path = Path(directory) / "manifest.json"
        path.write_bytes(snapshot.read("manifest.json"))
        return load_plan(path)


def snapshot_audit(snapshot: Snapshot) -> dict[str, object]:
    files = [_file(snapshot, name, content) for name, content in sorted(snapshot.files.items())]
    declared = [
        _declared(snapshot, name, expected)
        for name, expected in object_dict(snapshot.json("protocol.json").get("files")).items()
    ]
    return {
        "revision": snapshot.revision,
        "valid": all(item["valid"] for item in (*files, *declared)),
        "files": files,
        "protocol_files": declared,
    }


def _file(snapshot: Snapshot, name: str, content: bytes) -> dict[str, object]:
    actual = digest(snapshot.root / name)
    return {
        "path": name,
        "frozen_sha256": _sha(content),
        "actual_sha256": actual,
        "valid": actual == _sha(content),
    }


def _declared(snapshot: Snapshot, name: str, expected: object) -> dict[str, object]:
    frozen = snapshot.files.get(str(snapshot.directory / name))
    actual = digest(snapshot.root / snapshot.directory / name)
    return {
        "path": str(snapshot.directory / name),
        "declared_sha256": expected,
        "frozen_sha256": _sha(frozen) if frozen is not None else None,
        "actual_sha256": actual,
        "valid": frozen is not None and _sha(frozen) == actual == expected,
    }


def artifact_audit(
    snapshot: Snapshot | ArtifactSource, plan: Plan, run: Run, source: Path
) -> dict[str, object]:
    if not _builders_match(snapshot.builders if isinstance(snapshot, ArtifactSource) else snapshot):
        return {"valid": False, "error": "Frozen builder source differs; parity not evaluated"}
    expected = command(
        Request(
            plan.settings, next(case for case in plan.cases if case.id == run.case_id), run, source
        ),
        source / "workspace",
        _expected_prompt(snapshot, run),
    )
    return {
        "prompt": _prompt_audit(source, expected.argv[-1]),
        "invocation": _invocation_audit(source, expected.argv, plan.settings.timeout),
    }


def _expected_prompt(snapshot: Snapshot | ArtifactSource, run: Run) -> str:
    if isinstance(snapshot, ArtifactSource):
        return build_prompt(snapshot.task, run.arm, snapshot.builders.read("skill.md").decode())
    return build_prompt(
        snapshot.read(f"cases/{run.case_id}/task.txt").decode(),
        run.arm,
        snapshot.read("skill.md").decode(),
    )


def _builders_match(snapshot: Snapshot) -> bool:
    return all(
        str(snapshot.directory / name) in snapshot.files
        and digest(snapshot.root / snapshot.directory / name) == _sha(snapshot.read(name))
        for name in ("models.py", "prompts.py", "runner.py")
    )


def _prompt_audit(source: Path, expected: str) -> dict[str, object]:
    observed = digest(source / "prompt.txt")
    return {
        "expected_sha256": _sha(expected.encode()),
        "actual_sha256": observed,
        "valid": observed == _sha(expected.encode()),
    }


def _invocation_audit(source: Path, argv: list[str], timeout: float) -> dict[str, object]:
    try:
        actual = object_dict(json.loads((source / "invocation.json").read_text()))
    except (OSError, ValueError):
        return {"valid": False, "error": "Invocation missing or malformed"}
    expected = {"argv": argv, "cwd": str(source / "workspace"), "timeout": timeout}
    return {
        "valid": actual == expected,
        "changed_fields": [key for key, value in expected.items() if actual.get(key) != value],
        "expected_sha256": _sha(json.dumps(expected, sort_keys=True).encode()),
        "actual_sha256": _sha(json.dumps(actual, sort_keys=True).encode()),
    }
