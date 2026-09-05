"""Elaborated RTL query adapter and normalized access indexes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pyslang
from pyslang import ast, syntax

from slang_mcp.adapters.rtl_references import AccessIndex, Context, direction_kind
from slang_mcp.adapters.rtl_values import connection, location, parameters, port
from slang_mcp.errors import (
    AmbiguousSymbolError,
    InstanceNotFoundError,
    SignatureUnavailableError,
    SymbolNotFoundError,
)
from slang_mcp.models import ParameterDescription, SymbolDescription, SymbolReference
from slang_mcp.rtl_models import Connection, Instance, Port, Procedure, Reference

if TYPE_CHECKING:
    from slang_mcp.adapters.pyslang import SlangDesign


class RtlIndex:
    """Reuse Slang traversal once per compilation, retaining normalized query data."""

    def __init__(self, design: SlangDesign, compilation: Any, manager: Any) -> None:
        self.design = design
        self.compilation = compilation
        self.manager = manager
        self.instances: dict[str, Instance] = {}
        self.raw_instances: dict[str, Any] = {}
        self.defaults: dict[str, Any] = {}
        self.default_compilations: list[Any] = []
        self.access = AccessIndex(manager)
        self._collect_instances()
        self.instances = {
            path: replace(item, parent=self._parent_instance(path))
            for path, item in self.instances.items()
        }
        for raw in self.raw_instances.values():
            self._scan_instance(raw)
        self._index_references()

    def _collect_instances(self) -> None:
        for instance in self.compilation.getRoot().topInstances:
            instance.visit(self._collect)

    def _index_references(self) -> None:
        self.references_by_name: dict[str, list[Reference]] = defaultdict(list)
        for item in self.access.references:
            self.references_by_name[item.symbol.qualified_name].append(item)

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
        self.access.scan(raw.body, Context(str(raw.hierarchicalPath), str(raw.hierarchicalPath)))
        for item in raw.portConnections:
            if isinstance(item.port, ast.PortSymbol) and item.expression is not None:
                self.access.port_actual(
                    item.expression,
                    Context(
                        str(raw.hierarchicalPath).rsplit(".", 1)[0],
                        str(raw.hierarchicalPath),
                        direction_kind(item.port.direction.name.lower()),
                        "port_connection",
                    ),
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
        found = tuple(
            replace(item, symbol=resolved)
            for item in self.references_by_name.get(resolved.qualified_name, ())
        )
        if resolved.kind in {"module", "interface"}:
            return self._definition_references(resolved)
        if not any(item.kind == "declaration" for item in found):
            found = (self._declaration(resolved), *found)
        return found

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
        name = self.definition(name).name
        return tuple(
            item
            for item in self.access.procedures
            if self.instances[item.instance].sv_module == name
        )
