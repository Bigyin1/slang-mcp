"""Atomic result persistence and reproducibility identities."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from git import Repo

from benchmarks.dataset import ROOT, corpus_hash, read_object
from benchmarks.models import Settings
from benchmarks.runner.isolation import server_binary


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _source_files(folder: Path) -> list[Path]:
    suffixes = {".py", ".cpp", ".hpp", ".json", ".in", ".toml", ".lock", ".cmake"}
    return sorted(
        path
        for path in folder.rglob("*")
        if path.suffix in suffixes
        and not any(
            part.startswith(".") or part == "__pycache__" for part in path.relative_to(folder).parts
        )
    )


def code_hash() -> str:
    digest = hashlib.sha256()
    for folder in (ROOT, ROOT.parent / "src", ROOT.parent / "cmake", ROOT.parent / "tests"):
        for path in _source_files(folder):
            digest.update(str(path.relative_to(ROOT.parent)).encode())
            digest.update(path.read_bytes())
    for name in ("CMakeLists.txt", "CMakePresets.json"):
        digest.update((ROOT.parent / name).read_bytes())
    if server_binary().is_file():
        digest.update(server_binary().read_bytes())
    return digest.hexdigest()


def fingerprint(settings: Settings) -> str:
    payload = {"settings": asdict(settings), "corpus": corpus_hash(), "code": code_hash()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def metadata(settings: Settings) -> dict[str, object]:
    with Repo(ROOT.parent) as repo:
        commit = repo.head.commit.hexsha
        dirty = repo.is_dirty(untracked_files=True)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "benchmark_commit": commit,
        "server_commit": commit,
        "server_binary": str(server_binary()),
        "dirty": dirty,
        "code_hash": code_hash(),
        "corpus_hash": corpus_hash(),
        "skill_hash": hashlib.sha256((ROOT / "skills/semantic.md").read_bytes()).hexdigest(),
        "settings": asdict(settings),
        "fingerprint": fingerprint(settings),
    }


def reusable(path: Path, identity: str) -> bool:
    if not path.exists():
        return False
    record = read_object(path)
    return (
        record.get("fingerprint") == identity
        and record.get("completed") is True
        and (path.parent / "trace.jsonl").exists()
    )


def attempt_directory(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    index = 1
    while (path := base / f"attempt_{index:03d}").exists():
        index += 1
    path.mkdir()
    return path
