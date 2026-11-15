"""Compare recorded runtime files with frozen input and binary digests."""

from __future__ import annotations

import hashlib
from pathlib import Path


def digest(path: Path) -> str | None:
    """Return an actual file digest, keeping an unavailable artifact unknown."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_audit(workspace: Path, expected: dict[str, object]) -> dict[str, object]:
    if not workspace.is_dir():
        return {"valid": None, "error": "Workspace unavailable"}
    observed = {
        str(path.relative_to(workspace)): digest(path)
        for path in workspace.rglob("*")
        if path.is_file()
    }
    differences = {
        "missing": sorted(expected.keys() - observed.keys()),
        "changed": sorted(
            name for name in expected.keys() & observed.keys() if expected[name] != observed[name]
        ),
        "unexpected": sorted(observed.keys() - expected.keys()),
    }
    return {
        "valid": not any(differences.values()),
        "expected_files": len(expected),
        "observed_files": len(observed),
        **differences,
    }


def binary_audit(binary: Path, expected: object) -> dict[str, object]:
    actual = digest(binary)
    return {
        "path": str(binary),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "valid": actual is not None and actual == expected,
    }
