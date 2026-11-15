"""Record manifest revisions and hashes of the ordered measured source files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from benchmarks.dataset import read_object
from benchmarks.research_partial.prepare import PROJECTS, WORKSPACE
from benchmarks.runner.projects import project_spec


def fingerprint(workspace: Path) -> str:
    digest = hashlib.sha256()
    for value in (workspace / "source_files.f").read_text().splitlines():
        digest.update(str(Path(value).relative_to(workspace)).encode())
        digest.update(b"\0")
        digest.update(Path(value).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def record(name: str) -> dict[str, object]:
    workspace = WORKSPACE / name
    config = cast("dict[str, object]", read_object(workspace / "projects.json")[name])
    return {
        "manifest_spec": project_spec(name),
        "ordered_source_sha256": fingerprint(workspace),
        "defines": config["defines"],
        "include_directories": config["include_directories"],
        "top_modules": config["top_modules"],
    }


if __name__ == "__main__":
    (Path(__file__).parent / "provenance.json").write_text(
        json.dumps({name: record(name) for name in PROJECTS}, indent=2) + "\n"
    )
