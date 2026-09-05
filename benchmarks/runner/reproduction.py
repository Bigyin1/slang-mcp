"""Retain the exact dirty source tree behind a benchmark code hash."""

from __future__ import annotations

import shutil
from pathlib import Path

from benchmarks.dataset import ROOT


def snapshot_sources(output: Path) -> None:
    destination = output / "reproduction"
    destination.mkdir()
    for relative in ("benchmarks", "src/slang_mcp"):
        shutil.copytree(
            ROOT.parent / relative,
            destination / relative,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for name in ("pyproject.toml", "uv.lock", "Makefile"):
        shutil.copyfile(ROOT.parent / name, destination / name)
