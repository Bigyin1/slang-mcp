"""Bounded, normalized RTL query results independent of compiler objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from slang_mcp.models import (
    ParameterDescription,
    SourceLocation,
    SymbolDescription,
    SymbolReference,
)

T = TypeVar("T")
MAX_RESULTS = 500


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    total_count: int
    truncated: bool


def page(items: tuple[T, ...], limit: int) -> Page[T]:
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError("limit must be between 1 and 500")
    return Page(items[:limit], len(items), len(items) > limit)


@dataclass(frozen=True)
class Reference:
    symbol: SymbolReference
    kind: str
    location: SourceLocation
    scope: str
    instance: str | None
    context: str
    block: str | None = None


@dataclass(frozen=True)
class Instance:
    path: str
    name: str
    sv_module: str
    location: SourceLocation
    parent: str | None = None


@dataclass(frozen=True)
class Port:
    name: str
    direction: str
    type: str
    width: int | None
    location: SourceLocation
    unpacked_dimensions: tuple[str, ...] = ()
    interface: str | None = None
    modport: str | None = None
    default: str | None = None


@dataclass(frozen=True)
class Parameters:
    target: str
    value_kind: str
    parameters: Page[ParameterDescription]


@dataclass(frozen=True)
class Connection:
    port: Port
    kind: str
    expression: str | None
    symbols: tuple[str, ...]
    location: SourceLocation
    actual_type: str | None = None
    actual_width: int | None = None
    symbol_count: int = field(init=False)
    symbols_truncated: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol_count", len(self.symbols))
        object.__setattr__(self, "symbols_truncated", len(self.symbols) > MAX_RESULTS)
        object.__setattr__(self, "symbols", self.symbols[:MAX_RESULTS])


@dataclass(frozen=True)
class Procedure:
    block_id: str
    kind: str
    instance: str
    location: SourceLocation
    reads: Page[str]
    writes: Page[str]
    sensitivity: str | None = None


@dataclass(frozen=True)
class StateElement:
    signal: SymbolReference
    type: str | None
    width: int | None
    block: str
    location: SourceLocation


@dataclass(frozen=True)
class SignalInspection:
    symbol: SymbolDescription
    reference_count: int
    reads: Page[Reference]
    writes: Page[Reference]
    drivers: Page[Reference]
    loads: Page[Reference]


@dataclass(frozen=True)
class ModuleInspection:
    definition: SymbolReference
    parameters: Parameters
    ports: Page[Port]
    declaration_count: int
    children: Page[Instance]
    procedures: Page[Procedure]
    diagnostic_count: int


@dataclass(frozen=True)
class InstanceInspection:
    instance: Instance
    parameters: Parameters
    connections: Page[Connection]
    children: Page[Instance]


@dataclass(frozen=True)
class ConnectivityHop:
    """One source-level dependency used by a bounded connectivity route."""

    source: str
    target: str
    kind: Literal["port_binding", "continuous_assignment", "procedural_assignment"]
    location: SourceLocation
    instance_path: str | None
    formal_port: str | None = None
    operation: str | None = None


@dataclass(frozen=True)
class ConnectivityPath:
    """A bounded route ending at a leaf, cycle, or requested depth."""

    start: str
    end: str
    hops: tuple[ConnectivityHop, ...]
    stop_reason: Literal["no_edges", "max_depth", "cycle"]


@dataclass(frozen=True)
class ConnectivityTrace:
    """The bounded source-level routes for one resolved signal."""

    query: str
    direction: str
    resolved_start: SymbolReference
    paths: Page[ConnectivityPath]
    edges_considered: int
    max_depth: int
    truncated: bool


@dataclass(frozen=True)
class SemanticChange:
    category: str
    identity: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class SemanticDiff:
    status: str
    changes: Page[SemanticChange]
