"""Typed project-owned models returned by semantic queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

JsonScalar = str | None


@dataclass(frozen=True)
class ProjectConfig:
    """Build inputs resolved for one build-system logical module."""

    logical_module: str
    source_files: tuple[Path, ...]
    include_directories: tuple[Path, ...] = ()
    defines: Mapping[str, JsonScalar] = field(default_factory=dict)
    top_modules: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceLocation:
    filename: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    location: SourceLocation


@dataclass(frozen=True)
class ProjectSummary:
    logical_module: str
    source_file_count: int
    include_directory_count: int
    define_count: int
    top_modules: tuple[str, ...]
    diagnostic_error_count: int
    diagnostic_warning_count: int


@dataclass(frozen=True)
class ProjectInfo:
    summary: ProjectSummary
    source_files: tuple[str, ...]
    include_directories: tuple[str, ...]
    defines: tuple[str, ...]
    configured_top_modules: tuple[str, ...]
    metadata: Mapping[str, str]
    slang_version: str


@dataclass(frozen=True)
class SymbolReference:
    symbol_id: str
    name: str
    qualified_name: str
    kind: str
    containing_scope: str | None
    location: SourceLocation


@dataclass(frozen=True)
class PortDescription:
    name: str
    direction: str
    type: str
    width: int | None


@dataclass(frozen=True)
class ParameterDescription:
    """One declared or elaborated parameter with its rendered and numeric values.

    ``value`` preserves Slang's SystemVerilog rendering. ``integer_value`` is set
    only for integral constants without X or Z bits, so clients need not parse
    Verilog literals when a JSON integer is sufficient.
    """

    name: str
    type: str
    value: str | None
    is_local: bool
    integer_value: int | None = None


@dataclass(frozen=True)
class SymbolDescription:
    symbol: SymbolReference
    type: str | None = None
    width: int | None = None
    direction: str | None = None
    parameters: tuple[ParameterDescription, ...] = ()
    ports: tuple[PortDescription, ...] = ()
    members: tuple[SymbolReference, ...] = ()


@dataclass(frozen=True)
class HierarchyNode:
    path: str
    name: str
    kind: str
    sv_module: str | None
    children: tuple[HierarchyNode, ...] = ()


@dataclass(frozen=True)
class PortConnection:
    port: str
    expression: str | None


@dataclass(frozen=True)
class InstanceDescription:
    path: str
    name: str
    sv_module: str
    location: SourceLocation
    parameters: tuple[ParameterDescription, ...]
    ports: tuple[PortDescription, ...]
    connections: tuple[PortConnection, ...]
    children: tuple[HierarchyNode, ...]
