"""Shared Bender and checkout support for opt-in real-world tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

BENDER_VERSION = "0.32.1"
_DEFINE_PREFIX = "+define+"
_INCLUDE_PREFIX = "+incdir+"
_PROJECT_ROOT = Path(__file__).parents[2]


@dataclass(frozen=True)
class BenderRequest:
    """Inputs that affect a generated Bender source list."""

    checkout: Path
    target: str
    defines: tuple[str, ...] = ()
    top: str | None = None
    no_dependencies: bool = False


@dataclass(frozen=True)
class BenderSourceList:
    """Compilation inputs parsed from ``bender script flist-plus``."""

    sources: tuple[Path, ...]
    include_directories: tuple[Path, ...]
    defines: dict[str, str | None]


def generate_source_list(request: BenderRequest) -> BenderSourceList:
    """Generate ordered sources, include directories, and defines with Bender."""
    base = _bender_command(request)
    sources = tuple(Path(line) for line in _bender_lines(base, "--only-sources"))
    includes = tuple(
        Path(line.removeprefix(_INCLUDE_PREFIX))
        for line in _bender_lines(base, "--only-includes")
        if line.startswith(_INCLUDE_PREFIX)
    )
    defines = dict(
        _parse_define(line.removeprefix(_DEFINE_PREFIX))
        for line in _bender_lines(base, "--only-defines")
        if line.startswith(_DEFINE_PREFIX)
    )
    return BenderSourceList(sources, includes, defines)


def _bender_command(request: BenderRequest) -> list[str]:
    bender = _bender_executable()
    _require_bender_version(bender)
    base = [str(bender), "script", "flist-plus", "-t", request.target]
    if request.no_dependencies:
        base.append("--no-deps")
    if request.top is not None:
        base.extend(("--top", request.top))
    for define in request.defines:
        base.extend(("-D", define))
    base.extend(("-d", str(request.checkout)))

    return base


def checkout_repository(repository: str, revision: str, cache_name: str) -> Path:
    """Clone a repository into the ignored cache and select an exact revision."""
    root = _PROJECT_ROOT / ".realworld-cache" / cache_name
    if not (root / ".git").is_dir():
        root.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", repository, str(root)],
            check=True,
        )
    current = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current != revision:
        subprocess.run(
            ["git", "-C", str(root), "checkout", "--detach", revision],
            check=True,
        )
    return root


def install_lockfile(checkout: Path, lockfile: Path) -> None:
    """Install a checked-in Bender lockfile into an external checkout."""
    shutil.copyfile(lockfile, checkout / "Bender.lock")


def _bender_lines(base: list[str], mode: str) -> tuple[str, ...]:
    output = subprocess.run(
        [*base, mode],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _parse_define(value: str) -> tuple[str, str | None]:
    name, separator, replacement = value.partition("=")
    return name, replacement if separator else None


def _bender_executable() -> Path:
    configured = os.environ.get("BENDER_EXECUTABLE")
    discovered = shutil.which("bender")
    local = _PROJECT_ROOT / ".tools/bender"
    candidates = [Path(configured)] if configured is not None else []
    candidates.extend(Path(path) for path in (discovered, local) if path is not None)
    if (executable := next((path for path in candidates if path.is_file()), None)) is None:
        pytest.fail(f"Bender not found; install {BENDER_VERSION} or set BENDER_EXECUTABLE")
    return executable


def _require_bender_version(executable: Path) -> None:
    output = subprocess.run(
        [str(executable), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if output != f"bender {BENDER_VERSION}":
        pytest.fail(f"expected bender {BENDER_VERSION}, found: {output}")
