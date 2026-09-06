"""Materialize exact source revisions and export agent-visible build inputs."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import cast

from git import Repo

from benchmarks.dataset import ROOT, read_object, string

REPO_ROOT = ROOT.parent


def project_spec(name: str) -> dict[str, object]:
    return cast("dict[str, object]", read_object(ROOT / "cases/projects.json")[name])


def prepare_project(name: str, workspace: Path) -> dict[str, object]:
    spec = project_spec(name)
    if spec["kind"] == "synthetic":
        config = _synthetic(spec, workspace)
        provenance: dict[str, object] = {"kind": "synthetic"}
    else:
        config, provenance = _realworld(spec, workspace)
    (workspace / "projects.json").write_text(json.dumps({name: config}, indent=2) + "\n")
    _write_file_lists(config, workspace)
    return provenance


def _write_file_lists(config: dict[str, object], workspace: Path) -> None:
    """Export agent-visible direct-load inputs while retaining legacy JSON for validation."""
    _write_paths(workspace / "source_files.f", cast("list[str]", config["source_files"]), workspace)
    _write_paths(
        workspace / "include_directories.f",
        cast("list[str]", config["include_directories"]),
        workspace,
    )
    tops = cast("list[str]", config["top_modules"])
    (workspace / "top_module.txt").write_text(tops[0] + "\n", encoding="utf-8")


def _write_paths(destination: Path, values: list[str], workspace: Path) -> None:
    paths = [
        str((workspace / item).resolve()) if not Path(item).is_absolute() else item
        for item in values
    ]
    destination.write_text("\n".join(paths) + "\n", encoding="utf-8")


def _synthetic(spec: dict[str, object], workspace: Path) -> dict[str, object]:
    shutil.copytree(ROOT / "fixtures" / string(spec["fixture"]), workspace, dirs_exist_ok=True)
    return {
        "source_files": spec["sources"],
        "include_directories": spec["includes"],
        "defines": spec["defines"],
        "top_modules": spec["tops"],
    }


def _realworld(
    spec: dict[str, object], workspace: Path
) -> tuple[dict[str, object], dict[str, object]]:
    checkout = workspace / "rtl"
    _checkout(spec, checkout)
    config = _build_config(spec, checkout, workspace)
    provenance = _provenance(checkout, spec)
    _remove_git(checkout)
    return config, provenance


def _build_config(spec: dict[str, object], checkout: Path, workspace: Path) -> dict[str, object]:
    command = _bender_command(spec, checkout)
    return {
        "source_files": _bender_paths(command, "--only-sources", workspace),
        "include_directories": _bender_paths(command, "--only-includes", workspace),
        "defines": _bender_defines(command),
        "top_modules": spec["tops"],
    }


def _remove_git(checkout: Path) -> None:
    for git_dir in tuple(checkout.rglob(".git")):
        if git_dir.is_dir():
            shutil.rmtree(git_dir)
        else:
            git_dir.unlink()


def _checkout(spec: dict[str, object], destination: Path) -> None:
    cache = REPO_ROOT / ".realworld-cache" / string(spec["cache"])
    source = str(cache) if cache.exists() else string(spec["repository"])
    with Repo.clone_from(source, destination, no_hardlinks=True) as repo:
        repo.git.checkout("--detach", string(spec["commit"]))
    if (cache / ".bender").exists():
        shutil.copytree(cache / ".bender", destination / ".bender", symlinks=False)
    if "lockfile" in spec:
        shutil.copyfile(ROOT / "cases" / string(spec["lockfile"]), destination / "Bender.lock")
    _copy_cached_directories(spec, cache, destination)
    _copy_generated_files(spec, cache, destination)


def _copy_cached_directories(spec: dict[str, object], cache: Path, destination: Path) -> None:
    """Restore pinned source submodules that Bender manifests address as local paths."""
    for value in cast("list[str]", spec.get("cached_directories", [])):
        _copy_cached_directory(cache, destination, Path(value))


def _copy_cached_directory(cache: Path, destination: Path, relative: Path) -> None:
    source = cache / relative
    if not source.is_dir():
        raise RuntimeError(f"Missing cached RTL directory: {relative}")
    shutil.copytree(
        source,
        destination / relative,
        dirs_exist_ok=True,
        symlinks=False,
        ignore=shutil.ignore_patterns(".git"),
    )


def _copy_generated_files(spec: dict[str, object], cache: Path, destination: Path) -> None:
    for value in cast("list[str]", spec.get("generated_files", [])):
        _copy_cached_file(cache, destination, Path(value))


def _copy_cached_file(cache: Path, destination: Path, relative: Path) -> None:
    generated = cache / relative
    if not generated.is_file():
        raise RuntimeError(f"Missing cached generated RTL: {relative}")
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(generated, target)


def _bender_command(spec: dict[str, object], checkout: Path) -> list[str]:
    options = cast("dict[str, object]", spec["bender"])
    command = [_bender_executable(), "script", "flist-plus", "-d", str(checkout)]
    for target in _bender_targets(options):
        command.extend(("-t", target))
    command.extend(_bender_options(options))
    return command


def _bender_executable() -> str:
    bender = str(REPO_ROOT / ".tools/bender")
    if _output([bender, "--version"]) != ["bender 0.32.1"]:
        raise RuntimeError("Bender 0.32.1 is required")
    return bender


def _bender_targets(options: dict[str, object]) -> tuple[str, ...]:
    if "targets" in options:
        return tuple(string(value) for value in cast("list[object]", options["targets"]))
    return (string(options["target"]),)


def _bender_options(options: dict[str, object]) -> list[str]:
    result = ["--no-deps"] if options.get("no_dependencies") else []
    if "top" in options:
        result.extend(("--top", string(options["top"])))
    for define in cast("list[str]", options["defines"]):
        result.extend(("-D", define))
    return result


def _output(command: list[str]) -> list[str]:
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _bender_paths(command: list[str], option: str, workspace: Path) -> list[str]:
    return [
        str(Path(line.removeprefix("+incdir+")).resolve().relative_to(workspace.resolve()))
        for line in _output([*command, option])
    ]


def _bender_defines(command: list[str]) -> dict[str, str | None]:
    values = (
        line.removeprefix("+define+").partition("=")
        for line in _output([*command, "--only-defines"])
    )
    return {name: replacement if separator else None for name, separator, replacement in values}


def _provenance(checkout: Path, spec: dict[str, object]) -> dict[str, object]:
    revisions: dict[str, str] = {}
    for path in checkout.rglob(".git"):
        with Repo(path.parent) as repo:
            revisions[str(path.parent.relative_to(checkout))] = repo.head.commit.hexsha
    if revisions.get(".") != spec["commit"]:
        raise RuntimeError("RTL revision mismatch")
    return {
        "repository": spec["repository"],
        "commit": spec["commit"],
        "dependencies": revisions,
        "bender": "0.32.1",
    }
