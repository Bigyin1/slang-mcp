"""Parse the intentionally small absolute-path file-list format for MCP loads."""

from __future__ import annotations

from pathlib import Path

from slang_mcp.errors import InvalidProjectConfigError
from slang_mcp.models import ProjectConfig


def project_from_file_lists(
    source_file_lists: list[str],
    include_directory_lists: list[str],
    defines: dict[str, str | None],
    top_module: str,
) -> ProjectConfig:
    """Build compiler inputs from ordered lists of absolute source and include paths."""
    if not top_module.strip():
        raise ValueError("top_module must not be empty")
    return ProjectConfig(
        logical_module=top_module,
        source_files=_read_paths(source_file_lists, "source_file_lists", expect_directory=False),
        include_directories=_read_paths(
            include_directory_lists, "include_directory_lists", expect_directory=True
        ),
        defines=defines,
        top_modules=(top_module,),
        metadata={"load_format": "absolute_path_file_lists"},
    )


def _read_paths(
    list_files: list[str], argument: str, *, expect_directory: bool
) -> tuple[Path, ...]:
    if not list_files:
        if expect_directory:
            return ()
        raise ValueError("source_file_lists must contain at least one file list")
    paths = _list_entries(list_files, argument)
    kind = "include directory" if expect_directory else "source file"
    return _validated_unique_paths(paths, kind, expect_directory)


def _list_entries(  # pylint: disable=too-many-locals
    list_files: list[str], argument: str
) -> list[Path]:
    result: list[Path] = []
    for list_file in list_files:
        path = _absolute(Path(list_file), argument)
        if not path.is_file():
            raise InvalidProjectConfigError(f"missing or invalid file list: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not (entry := line.strip()):
                continue
            result.append(_absolute(Path(entry), f"entry in {path}"))
    return result


def _validated_unique_paths(  # pylint: disable=too-many-locals
    paths: list[Path], kind: str, expect_directory: bool
) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[Path] = set()
    for item in paths:
        if not (item.is_dir() if expect_directory else item.is_file()):
            raise InvalidProjectConfigError(f"missing or invalid {kind}: {item}")
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _absolute(path: Path, argument: str) -> Path:
    if not path.is_absolute():
        raise InvalidProjectConfigError(f"{argument} must contain absolute paths: {path}")
    return path
