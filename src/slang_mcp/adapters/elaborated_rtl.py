"""Index an elaborated Slang design for normalized RTL queries."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

import pyslang
from pyslang import ast, syntax

from slang_mcp.adapters.semantic_normalization import connection, location, parameters, port
from slang_mcp.adapters.source_access import AccessContext, SourceAccessIndex, direction_kind
from slang_mcp.errors import (
    AmbiguousSymbolError,
    InstanceNotFoundError,
    SignatureUnavailableError,
    SymbolNotFoundError,
)
from slang_mcp.models import ParameterDescription, SymbolDescription, SymbolReference
from slang_mcp.rtl_models import (
    Connection,
    ConnectivityHop,
    ConnectivityPath,
    ConnectivityTrace,
    Instance,
    Page,
    Port,
    Procedure,
    Reference,
)

if TYPE_CHECKING:
    from slang_mcp.adapters.pyslang import SlangDesign


@dataclass
class ConnectivityTraversalState:
    """Mutable breadth-first traversal state kept private to one trace request."""

    start: str
    pending: deque[tuple[str, tuple[ConnectivityHop, ...], frozenset[str]]]
    paths: list[ConnectivityPath]
    limit: int
    considered: int = 0


class ElaboratedRtlIndex:
    """Own normalized facts extracted once from one elaborated Slang compilation.

    The index owns no public compiler objects: it converts instance, access and
    connectivity facts into project-owned models for the service layer.
    """

    def __init__(self, design: SlangDesign, compilation: Any, manager: Any) -> None:
        self.design = design
        self.compilation = compilation
        self.manager = manager
        self.instances: dict[str, Instance] = {}
        self.raw_instances: dict[str, Any] = {}
        self.defaults: dict[str, Any] = {}
        self.default_compilations: list[Any] = []
        self.access: SourceAccessIndex | None = None
        self.references_by_name: dict[str, list[Reference]] = {}
        self.connectivity: tuple[ConnectivityHop, ...] = ()
        self.connectivity_by_source: dict[str, tuple[ConnectivityHop, ...]] = {}
        self.connectivity_by_target: dict[str, tuple[ConnectivityHop, ...]] = {}
        self._collect_instances()
        self.instances = {
            path: replace(item, parent=self._parent_instance(path))
            for path, item in self.instances.items()
        }
        self._access_indexed: bool = False
        self._connectivity_indexed: bool = False

    def _collect_instances(self) -> None:
        for instance in self.compilation.getRoot().topInstances:
            instance.visit(self._collect)

    def _index_references(self) -> None:
        access = self._access()
        self.references_by_name = defaultdict(list)
        for item in access.references:
            self.references_by_name[item.symbol.qualified_name].append(item)

    def _index_connectivity(self) -> None:
        edges = {self._connectivity_identity(item): item for item in self._access().connectivity}
        self.connectivity = tuple(sorted(edges.values(), key=self._connectivity_key))
        self.connectivity_by_source = {}
        self.connectivity_by_target = {}
        for edge in self.connectivity:
            self.connectivity_by_source[edge.source] = (
                *self.connectivity_by_source.get(edge.source, ()),
                edge,
            )
            self.connectivity_by_target[edge.target] = (
                *self.connectivity_by_target.get(edge.target, ()),
                edge,
            )

    def _ensure_access_index(self) -> None:
        if self._access_indexed:
            return
        self.access = SourceAccessIndex(self.manager)
        for raw in self.raw_instances.values():
            self._scan_instance(raw)
        self._index_references()
        self._access_indexed = True

    def _ensure_connectivity_index(self) -> None:
        if self._connectivity_indexed:
            return
        self._ensure_access_index()
        self._index_connectivity()
        self._connectivity_indexed = True

    def _access(self) -> SourceAccessIndex:
        if self.access is None:
            raise RuntimeError("source access index has not been built")
        return self.access

    def _parent_instance(self, path: str) -> str | None:
        while "." in path:
            if (path := path.rsplit(".", 1)[0]) in self.instances:
                return path
        return None

    def _collect(self, raw: Any) -> Any:
        if isinstance(raw, ast.GenerateBlockSymbol) and raw.isUninstantiated:
            return ast.VisitAction.Skip
        if isinstance(raw, ast.InstanceSymbol):
            self.raw_instances[str(raw.hierarchicalPath)] = raw
            self.instances[str(raw.hierarchicalPath)] = Instance(
                str(raw.hierarchicalPath),
                raw.name,
                raw.definition.name,
                location(raw.location, self.manager),
            )
        return ast.VisitAction.Advance

    def _scan_instance(self, raw: Any) -> None:
        access = self._access()
        access.scan(
            raw.body,
            AccessContext(str(raw.hierarchicalPath), str(raw.hierarchicalPath)),
        )
        for item in raw.portConnections:
            if isinstance(item.port, ast.PortSymbol) and item.expression is not None:
                access.port_actual(
                    item.expression,
                    AccessContext(
                        str(raw.hierarchicalPath).rsplit(".", 1)[0],
                        str(raw.hierarchicalPath),
                        direction_kind(item.port.direction.name.lower()),
                        "port_connection",
                    ),
                )
                access.port_binding(
                    item.expression,
                    item.port,
                    AccessContext(str(raw.hierarchicalPath), str(raw.hierarchicalPath)),
                )

    def resolve_instance(self, query: str) -> Instance:
        if query in self.instances:
            return self.instances[query]
        if not (matches := [item for item in self.instances.values() if item.name == query]):
            raise InstanceNotFoundError(f"unknown instance: {query}")
        if len(matches) != 1:
            raise AmbiguousSymbolError(
                f"ambiguous instance {query}: " + ", ".join(item.path for item in matches[:20])
            )
        return matches[0]

    def definition(self, name: str) -> SymbolReference:
        symbol = self.design.describe_symbol(name).symbol
        if symbol.kind not in {"module", "interface"}:
            raise SymbolNotFoundError(f"not a module or interface: {name}")
        return symbol

    def default_instance(self, name: str) -> Any:
        if (name := self.definition(name).name) not in self.defaults:
            self._build_default(name)
        return self.defaults[name]

    def _build_default(self, name: str) -> None:
        options = ast.CompilationOptions()
        options.topModules = {"__slang_mcp_defaults"}
        compilation = ast.Compilation(pyslang.Bag([options]))
        for tree in self.compilation.getSyntaxTrees():
            compilation.addSyntaxTree(tree)
        compilation.addSyntaxTree(
            syntax.SyntaxTree.fromText(
                f"module __slang_mcp_defaults; {name} __subject(); endmodule",
                self.manager,
            )
        )
        self.default_compilations.append(compilation)
        self._store_default(compilation, name)

    def _store_default(self, compilation: Any, name: str) -> None:
        for instance in compilation.getRoot().topInstances:
            for member in instance.body:
                if isinstance(member, ast.InstanceSymbol) and member.definition.name == name:
                    self.defaults[name] = member
        if name not in self.defaults:
            raise SignatureUnavailableError(f"default elaboration unavailable for {name}")

    def ports(self, name: str) -> tuple[Port, ...]:
        return tuple(port(raw, self.manager) for raw in self.default_instance(name).body.portList)

    def parameters(self, target: str, effective: bool) -> tuple[ParameterDescription, ...]:
        raw = (
            self.raw_instances[self.resolve_instance(target).path]
            if effective
            else (self.default_instance(target))
        )
        return parameters(raw)

    def connections(self, path: str) -> tuple[Connection, ...]:
        return tuple(
            connection(raw, self.manager)
            for raw in self.raw_instances[self.resolve_instance(path).path].portConnections
        )

    def references(self, symbol: str) -> tuple[Reference, ...]:
        resolved = self.resolve_signal(symbol).symbol
        if resolved.kind in {"module", "interface"}:
            return self._definition_references(resolved)
        self._ensure_access_index()
        found = tuple(
            replace(item, symbol=resolved)
            for item in self.references_by_name.get(resolved.qualified_name, ())
        )
        if not any(item.kind == "declaration" for item in found):
            found = (self._declaration(resolved), *found)
        return found

    def trace_connectivity(  # pylint: disable=too-many-locals
        self,
        signal: str,
        direction: str,
        max_depth: int,
        limit: int,
    ) -> ConnectivityTrace:
        self._ensure_connectivity_index()
        resolved = self.resolve_signal(signal).symbol
        start = resolved.qualified_name
        state = ConnectivityTraversalState(
            start,
            deque([(start, (), frozenset({start}))]),
            [],
            limit,
        )
        while state.pending and len(state.paths) < limit and state.considered < limit:
            current, hops, visited = state.pending.popleft()
            edges = self._trace_edges(current, direction)
            if (stop_reason := self._trace_stop_reason(hops, edges, max_depth)) is not None:
                state.paths.append(ConnectivityPath(start, current, hops, stop_reason))
            else:
                self._append_trace_edges(state, edges, hops, visited)
        truncated = bool(state.pending) or state.considered >= limit
        return ConnectivityTrace(
            signal,
            direction,
            resolved,
            Page(tuple(state.paths), len(state.paths), truncated),
            state.considered,
            max_depth,
            truncated,
        )

    @staticmethod
    def _trace_stop_reason(
        hops: tuple[ConnectivityHop, ...],
        edges: tuple[ConnectivityHop, ...],
        max_depth: int,
    ) -> Literal["no_edges", "max_depth"] | None:
        if len(hops) >= max_depth:
            return "max_depth"
        if not edges:
            return "no_edges"
        return None

    @staticmethod
    def _append_trace_edges(  # pylint: disable=too-many-locals
        state: ConnectivityTraversalState,
        edges: tuple[ConnectivityHop, ...],
        hops: tuple[ConnectivityHop, ...],
        visited: frozenset[str],
    ) -> None:
        for edge in edges:
            if len(state.paths) >= state.limit or state.considered >= state.limit:
                break
            state.considered += 1
            next_hops = (*hops, edge)
            if edge.target in visited:
                state.paths.append(ConnectivityPath(state.start, edge.target, next_hops, "cycle"))
            else:
                state.pending.append((edge.target, next_hops, visited | {edge.target}))

    def _trace_edges(  # pylint: disable=too-many-locals
        self, signal: str, direction: str
    ) -> tuple[ConnectivityHop, ...]:
        forward = self.connectivity_by_source.get(signal, ()) if direction != "drivers" else ()
        backward = self.connectivity_by_target.get(signal, ()) if direction != "loads" else ()
        reversed_edges = tuple(
            replace(item, source=item.target, target=item.source) for item in backward
        )
        return tuple(sorted((*forward, *reversed_edges), key=self._connectivity_key))

    @staticmethod
    def _connectivity_key(item: ConnectivityHop) -> tuple[Any, ...]:
        return (
            item.source,
            item.target,
            item.kind,
            item.operation or "",
            item.formal_port or "",
            item.location.filename or "",
            item.location.line or -1,
            item.location.column or -1,
        )

    @staticmethod
    def _connectivity_identity(item: ConnectivityHop) -> tuple[Any, ...]:
        return (*ElaboratedRtlIndex._connectivity_key(item), item.instance_path)

    @staticmethod
    def _declaration(symbol: SymbolReference) -> Reference:
        return Reference(
            symbol,
            "declaration",
            symbol.location,
            symbol.containing_scope or "",
            None,
            "declaration",
        )

    def _definition_references(self, symbol: SymbolReference) -> tuple[Reference, ...]:
        return (
            self._declaration(symbol),
            *(
                Reference(
                    symbol,
                    "instantiation",
                    item.location,
                    item.parent or "",
                    item.path,
                    "instantiation",
                )
                for item in self.instances.values()
                if item.sv_module == symbol.name
            ),
        )

    def resolve_signal(self, symbol: str) -> SymbolDescription:
        matches = [
            item
            for item in self.design.find_symbols(symbol.rsplit(".", 1)[-1])
            if item.qualified_name == symbol and item.kind in {"variable", "net"}
        ]
        return self.design.describe_symbol(matches[0].symbol_id if len(matches) == 1 else symbol)

    def members(self, scope: str) -> tuple[SymbolReference, ...]:
        return self.design.scope_members(scope)

    def procedures(self, name: str) -> tuple[Procedure, ...]:
        self._ensure_access_index()
        name = self.definition(name).name
        return tuple(
            item
            for item in self._access().procedures
            if self.instances[item.instance].sv_module == name
        )

    def procedure_writes(self, block_id: str) -> tuple[str, ...]:
        self._ensure_access_index()
        return self._access().block_writes[block_id]
