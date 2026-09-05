"""Typed query boundary around the dynamic pyslang object graph."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

import pyslang
from pyslang import ast as slang_ast
from pyslang import parsing as slang_parsing
from pyslang import syntax as slang_syntax

from slang_mcp.adapters.elaborated_rtl import ElaboratedRtlIndex
from slang_mcp.adapters.semantic_normalization import parameters as _parameters
from slang_mcp.errors import (
    AmbiguousSymbolError,
    CompilationError,
    InstanceNotFoundError,
    InvalidTopError,
    SymbolNotFoundError,
)
from slang_mcp.models import (
    Diagnostic,
    HierarchyNode,
    InstanceDescription,
    ParameterDescription,
    PortConnection,
    PortDescription,
    ProjectConfig,
    SourceLocation,
    SymbolDescription,
    SymbolReference,
)

_SEARCHABLE_KINDS = {
    "ClassType",
    "Definition",
    "Net",
    "Package",
    "Parameter",
    "Port",
    "Subroutine",
    "TypeAlias",
    "TypeParameter",
    "Variable",
}
_HIERARCHY_KINDS = {"GenerateBlock", "GenerateBlockArray", "Instance", "InstanceArray"}


@dataclass(frozen=True)
class _IndexedSymbol:
    reference: SymbolReference
    raw: Any


@dataclass(frozen=True)
class _HierarchyRecord:
    path: str
    parent: str
    name: str
    kind: str
    sv_module: str | None
    raw: Any


class SlangDesign:
    """One fully elaborated Slang compilation and its compact semantic index."""

    def __init__(self, config: ProjectConfig) -> None:
        self._config = config
        self._source_manager = pyslang.SourceManager()
        self._compilation = self._compile(config)
        self._diagnostics = self._convert_diagnostics()
        self._symbols = self._index_symbols()
        self._hierarchy = self._index_hierarchy()
        self._validate_configured_tops()
        self._default_symbols: dict[str, _IndexedSymbol] = {}
        self.rtl = ElaboratedRtlIndex(self, self._compilation, self._source_manager)

    def scope_members(self, scope: str) -> tuple[SymbolReference, ...]:
        resolved = self._resolve_symbol(scope)
        if isinstance(resolved.raw, slang_ast.DefinitionSymbol):
            return self._default_members(resolved.raw.name)
        return tuple(
            item.reference
            for item in self._symbols
            if item.reference.containing_scope == resolved.reference.qualified_name
        )

    def definitions(self) -> tuple[SymbolReference, ...]:
        return tuple(
            item.reference
            for item in self._symbols
            if item.reference.kind in {"module", "interface", "package"}
        )

    def _default_members(self, name: str) -> tuple[SymbolReference, ...]:
        body = self.rtl.default_instance(name).body
        return tuple(
            self._default_member(raw, name)
            for raw in (*body.portList, *body)
            if raw.kind.name in _SEARCHABLE_KINDS
        )

    def _default_member(self, raw: Any, scope: str) -> SymbolReference:
        indexed = self._to_indexed(raw, _public_kind(raw))
        normalized = replace(
            indexed.reference,
            symbol_id=f"default:{indexed.reference.kind}:{scope}.{raw.name}",
            qualified_name=f"{scope}.{raw.name}",
            containing_scope=scope,
        )
        self._default_symbols[normalized.symbol_id] = _IndexedSymbol(normalized, raw)
        return normalized

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return self._diagnostics

    @property
    def top_modules(self) -> tuple[str, ...]:
        return tuple(record.path for record in self._hierarchy if not record.parent)

    @property
    def slang_version(self) -> str:
        version = pyslang.VersionInfo
        return f"{version.getMajor()}.{version.getMinor()}.{version.getPatch()}+{version.getHash()}"

    def find_symbols(self, name: str) -> tuple[SymbolReference, ...]:
        return tuple(item.reference for item in self._symbols if item.reference.name == name)

    def describe_symbol(self, identifier: str) -> SymbolDescription:
        indexed = self._resolve_symbol(identifier)
        type_name, width = _symbol_type(indexed.raw)
        return SymbolDescription(
            indexed.reference,
            type_name,
            width,
            _direction(indexed.raw),
            *self._definition_details(indexed.raw),
            members=tuple(
                item.reference
                for item in self._symbols
                if item.reference.containing_scope == indexed.reference.qualified_name
            ),
        )

    def get_hierarchy(self, root: str | None, max_depth: int | None) -> tuple[HierarchyNode, ...]:
        roots = [record for record in self._hierarchy if not record.parent]
        if root is not None and not (
            roots := [record for record in roots if root in (record.path, record.name)]
        ):
            raise InvalidTopError(f"unknown top module: {root}")
        return tuple(self._make_node(record, max_depth, 0) for record in roots)

    def describe_instance(self, path: str) -> InstanceDescription:
        matches = [
            record
            for record in self._hierarchy
            if record.path == path and record.kind == "instance"
        ]
        if not matches:
            raise InstanceNotFoundError(f"unknown elaborated instance path: {path}")
        record = matches[0]
        return InstanceDescription(
            record.path,
            record.name,
            record.sv_module or "",
            _source_location(record.raw, self._source_manager),
            *_instance_signature(record.raw),
            _port_connections(record.raw),
            tuple(self._make_node(item, 0, 0) for item in self._children(path)),
        )

    def _compile(self, config: ProjectConfig) -> Any:
        try:
            return self._create_compilation(config)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise CompilationError(f"Slang compilation failed: {error}") from error

    def _create_compilation(self, config: ProjectConfig) -> Any:
        options = _compilation_options(config)
        tree = slang_syntax.SyntaxTree.fromFiles(
            [str(path) for path in config.source_files], self._source_manager, options
        )
        compilation = slang_ast.Compilation(options)
        compilation.addSyntaxTree(tree)
        compilation.getRoot()
        compilation.getSemanticDiagnostics()
        return compilation

    def _convert_diagnostics(self) -> tuple[Diagnostic, ...]:
        engine = pyslang.DiagnosticEngine(self._source_manager)
        converted: list[Diagnostic] = []
        for item in self._compilation.getAllDiagnostics():
            severity = engine.getSeverity(item.code, item.location).name.lower()
            converted.append(
                Diagnostic(
                    severity,
                    repr(item.code).removeprefix("DiagCode(").removesuffix(")"),
                    engine.formatMessage(item),
                    _source_location(item, self._source_manager),
                )
            )
        return tuple(converted)

    def _index_symbols(self) -> tuple[_IndexedSymbol, ...]:
        indexed = [
            self._to_indexed(definition, _definition_kind(definition))
            for definition in self._compilation.getDefinitions()
        ]

        def collect(raw: Any) -> None:
            if isinstance(raw, slang_ast.Symbol) and raw.kind.name in _SEARCHABLE_KINDS:
                indexed.append(self._to_indexed(raw, _public_kind(raw)))

        self._compilation.getRoot().visit(collect)
        unique: dict[str, _IndexedSymbol] = {}
        for item in indexed:
            unique.setdefault(item.reference.symbol_id, item)
        return tuple(unique.values())

    def _to_indexed(self, raw: Any, kind: str) -> _IndexedSymbol:
        qualified = _qualified_name(raw)
        reference = SymbolReference(
            f"{kind}:{qualified}",
            raw.name,
            qualified,
            kind,
            _containing_scope(qualified),
            _source_location(raw, self._source_manager),
        )
        return _IndexedSymbol(reference, raw)

    def _index_hierarchy(self) -> tuple[_HierarchyRecord, ...]:
        records: list[_HierarchyRecord] = []

        def collect(raw: Any) -> None:
            if not isinstance(raw, slang_ast.Symbol) or raw.kind.name not in _HIERARCHY_KINDS:
                return
            path = raw.hierarchicalPath
            if not path or path.startswith("\\$root"):
                return
            records.append(_hierarchy_record(raw, path))

        self._compilation.getRoot().visit(collect)
        top_paths = {item.hierarchicalPath for item in self._compilation.getRoot().topInstances}
        records = [record for record in records if _top_path(record.path) in top_paths]
        paths = {record.path for record in records}
        return tuple(
            replace(record, parent=record.parent if record.parent in paths else "")
            for record in records
        )

    def _resolve_symbol(self, identifier: str) -> _IndexedSymbol:
        if identifier in self._default_symbols:
            return self._default_symbols[identifier]
        if by_id := [item for item in self._symbols if item.reference.symbol_id == identifier]:
            return by_id[0]
        matches = [
            item
            for item in self._symbols
            if identifier in (item.reference.name, item.reference.qualified_name)
        ]
        if not matches:
            raise SymbolNotFoundError(f"unknown symbol: {identifier}")
        if len(matches) > 1:
            ids = ", ".join(item.reference.symbol_id for item in matches[:5])
            raise AmbiguousSymbolError(f"ambiguous symbol '{identifier}'; use one of: {ids}")
        return matches[0]

    def _definition_details(
        self,
        raw: Any,
    ) -> tuple[tuple[ParameterDescription, ...], tuple[PortDescription, ...]]:
        if not isinstance(raw, slang_ast.DefinitionSymbol):
            return (), ()
        instances = [
            record.raw
            for record in self._hierarchy
            if record.kind == "instance" and record.sv_module == raw.name
        ]
        return _instance_signature(instances[0]) if instances else ((), ())

    def _children(self, path: str) -> list[_HierarchyRecord]:
        return [record for record in self._hierarchy if record.parent == path]

    def _validate_configured_tops(self) -> None:
        if missing := set(self._config.top_modules).difference(self.top_modules):
            names = ", ".join(sorted(missing))
            raise InvalidTopError(f"configured top module was not elaborated: {names}")

    def _make_node(
        self,
        record: _HierarchyRecord,
        max_depth: int | None,
        depth: int,
    ) -> HierarchyNode:
        children: Sequence[_HierarchyRecord] = self._children(record.path)
        if max_depth is not None and depth >= max_depth:
            children = ()
        return HierarchyNode(
            record.path,
            record.name,
            record.kind,
            record.sv_module,
            tuple(self._make_node(child, max_depth, depth + 1) for child in children),
        )


def _predefines(config: ProjectConfig) -> list[str]:
    return [name if value is None else f"{name}={value}" for name, value in config.defines.items()]


def _compilation_options(config: ProjectConfig) -> Any:
    preprocessor = slang_parsing.PreprocessorOptions()
    preprocessor.additionalIncludePaths = list(config.include_directories)
    preprocessor.predefines = _predefines(config)
    compilation = slang_ast.CompilationOptions()
    compilation.topModules = set(config.top_modules)
    return pyslang.Bag([preprocessor, compilation])


def _definition_kind(raw: Any) -> str:
    return str(raw.definitionKind.name).lower()


def _public_kind(raw: Any) -> str:
    if isinstance(raw, slang_ast.SubroutineSymbol):
        return str(raw.subroutineKind.name).lower()
    return str(raw.kind.name).lower()


def _qualified_name(raw: Any) -> str:
    path = raw.hierarchicalPath
    return str(path or raw.lexicalPath or raw.name)


def _containing_scope(qualified: str) -> str | None:
    separator = "::" if "::" in qualified and "." not in qualified else "."
    return qualified.rsplit(separator, 1)[0] if separator in qualified else None


def _source_location(raw: Any, manager: Any) -> SourceLocation:
    try:
        filename, line, column = _location_parts(raw.location, manager)
    except RuntimeError:
        return SourceLocation()
    return SourceLocation(filename or None, line or None, column or None)


def _location_parts(location: Any, manager: Any) -> tuple[str, int, int]:
    return (
        manager.getFileName(location),
        manager.getLineNumber(location),
        manager.getColumnNumber(location),
    )


def _symbol_type(raw: Any) -> tuple[str | None, int | None]:
    if isinstance(raw, (slang_ast.PortSymbol, slang_ast.ValueSymbol)):
        return str(raw.type), raw.type.bitWidth
    if isinstance(raw, slang_ast.SubroutineSymbol):
        return str(raw.returnType), raw.returnType.bitWidth
    if isinstance(raw, slang_ast.TypeAliasType):
        target = raw.targetType.type
        return str(target), target.bitWidth
    return None, None


def _direction(raw: Any) -> str | None:
    if isinstance(raw, (slang_ast.PortSymbol, slang_ast.FormalArgumentSymbol)):
        return str(raw.direction.name).lower()
    return None


def _ports(raw: Any) -> tuple[PortDescription, ...]:
    result: list[PortDescription] = []
    for port in raw.body.portList:
        if isinstance(port, slang_ast.PortSymbol):
            result.append(
                PortDescription(
                    port.name, port.direction.name.lower(), str(port.type), port.type.bitWidth
                )
            )
        elif isinstance(port, slang_ast.InterfacePortSymbol):
            result.append(PortDescription(port.name, "interface", port.interfaceDef.name, None))
    return tuple(result)


def _instance_signature(
    raw: Any,
) -> tuple[tuple[ParameterDescription, ...], tuple[PortDescription, ...]]:
    if not isinstance(raw, slang_ast.InstanceSymbol):
        return (), ()
    return _parameters(raw), _ports(raw)


def _port_connections(raw: Any) -> tuple[PortConnection, ...]:
    result: list[PortConnection] = []
    for connection in raw.portConnections:
        expression = connection.expression
        syntax = getattr(expression, "syntax", None)
        result.append(
            PortConnection(connection.port.name, str(syntax) if syntax is not None else None)
        )
    return tuple(result)


def _hierarchy_record(raw: Any, path: str) -> _HierarchyRecord:
    parent = _parent_path(path)
    if isinstance(raw, slang_ast.InstanceSymbol):
        return _HierarchyRecord(path, parent, raw.name, "instance", raw.definition.name, raw)
    kind = "generate_block" if isinstance(raw, slang_ast.GenerateBlockSymbol) else "generate_array"
    name = path.rsplit(".", 1)[-1]
    return _HierarchyRecord(path, parent, name, kind, None, raw)


def _parent_path(path: str) -> str:
    last_component = path.rsplit(".", 1)[-1]
    if last_component.endswith("]") and "[" in last_component:
        return path[: path.rfind("[")]
    return path.rsplit(".", 1)[0] if "." in path else ""


def _top_path(path: str) -> str:
    return path.split(".", 1)[0].split("[", 1)[0]
