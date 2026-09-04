"""Static in-memory and JSON-backed project provider."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from slang_mcp.errors import InvalidProjectConfigError, UnknownLogicalModuleError
from slang_mcp.models import ProjectConfig


class StaticProjectProvider:
    """Resolve logical modules from an immutable in-memory mapping."""

    def __init__(self, projects: Mapping[str, ProjectConfig]) -> None:
        self._projects = dict(projects)

    def resolve(self, logical_module: str) -> ProjectConfig:
        try:
            return self._projects[logical_module]
        except KeyError as error:
            message = f"unknown logical module: {logical_module}"
            raise UnknownLogicalModuleError(message) from error

    @classmethod
    def from_json(cls, path: Path) -> StaticProjectProvider:
        """Load project descriptions, resolving paths relative to the JSON file."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            message = f"cannot read static project config {path}: {error}"
            raise InvalidProjectConfigError(message) from error
        if not isinstance(raw, dict):
            raise InvalidProjectConfigError("static project config must be a JSON object")
        projects = _parse_projects(cast("Mapping[str, object]", raw), path.parent)
        return cls(projects)


def _parse_projects(raw: Mapping[str, object], base: Path) -> dict[str, ProjectConfig]:
    projects: dict[str, ProjectConfig] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            raise InvalidProjectConfigError(f"project '{name}' must be a JSON object")
        item = cast("Mapping[str, object]", value)
        projects[name] = _parse_project(name, item, base)
    return projects


def _parse_project(name: str, raw: Mapping[str, object], base: Path) -> ProjectConfig:
    sources = _path_tuple(raw.get("source_files"), base, "source_files", required=True)
    includes = _path_tuple(raw.get("include_directories", []), base, "include_directories")
    tops = _string_tuple(raw.get("top_modules", []), "top_modules")
    defines = _defines(raw.get("defines", {}))
    metadata = _string_mapping(raw.get("metadata", {}), "metadata")
    return ProjectConfig(name, sources, includes, defines, tops, metadata)


def _path_tuple(
    value: object,
    base: Path,
    field_name: str,
    *,
    required: bool = False,
) -> tuple[Path, ...]:
    values = _string_tuple(value, field_name)
    if required and not values:
        raise InvalidProjectConfigError(f"{field_name} must not be empty")
    return tuple(
        (base / item).resolve() if not Path(item).is_absolute() else Path(item) for item in values
    )


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InvalidProjectConfigError(f"{field_name} must be an array of strings")
    return tuple(cast("list[str]", value))


def _defines(value: object) -> Mapping[str, str | None]:
    if not isinstance(value, dict):
        raise InvalidProjectConfigError("defines must be an object")
    result: dict[str, str | None] = {}
    for key, item in cast("Mapping[object, object]", value).items():
        if not isinstance(key, str) or (item is not None and not isinstance(item, str)):
            raise InvalidProjectConfigError("defines values must be strings or null")
        result[key] = item
    return result


def _string_mapping(value: object, field_name: str) -> Mapping[str, str]:
    if not isinstance(value, dict):
        raise InvalidProjectConfigError(f"{field_name} must be an object of strings")
    result = cast("Mapping[object, object]", value)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in result.items()):
        raise InvalidProjectConfigError(f"{field_name} must be an object of strings")
    return cast("Mapping[str, str]", result)
