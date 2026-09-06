"""Normalize raw Slang values into project-owned semantic models.

This module deliberately contains stateless conversion functions instead of
classes: each function accepts a raw compiler object and returns a typed value
that is safe to expose outside the adapter boundary.
"""

from typing import Any

import pyslang
from pyslang import ast

from slang_mcp.models import ParameterDescription, SourceLocation, SymbolReference
from slang_mcp.rtl_models import Connection, Port


def location(raw: Any, manager: Any) -> SourceLocation:
    if raw is None:
        return SourceLocation()
    return SourceLocation(
        manager.getFileName(raw) or None,
        manager.getLineNumber(raw) or None,
        manager.getColumnNumber(raw) or None,
    )


def reference(raw: Any, manager: Any) -> SymbolReference:
    name = str(raw.hierarchicalPath or raw.lexicalPath or raw.name)
    kind = raw.kind.name.lower()
    if isinstance(raw, ast.SubroutineSymbol):
        kind = raw.subroutineKind.name.lower()
    return SymbolReference(
        f"{kind}:{name}",
        raw.name,
        name,
        kind,
        name.rsplit(".", 1)[0] if "." in name else None,
        location(raw.location, manager),
    )


def expression_text(expr: Any) -> str | None:
    while isinstance(expr, ast.ConversionExpression) and expr.syntax is None:
        expr = expr.operand
    if expr is None:
        return None
    if expr.syntax is not None:
        return str(expr.syntax).strip()[:1000]
    if isinstance(expr, ast.ValueExpressionBase):
        return str(expr.symbol.hierarchicalPath)
    return str(expr.constant) if expr.constant is not None else None


def parameters(raw: Any) -> tuple[ParameterDescription, ...]:
    return tuple(parameter(item) for item in raw.body.parameters)


def parameter(raw: Any) -> ParameterDescription:
    if isinstance(raw, ast.TypeParameterSymbol):
        return ParameterDescription(raw.name, "type", str(raw.targetType.type), raw.isLocalParam)
    return ParameterDescription(
        raw.name,
        str(raw.type),
        str(raw.value),
        raw.isLocalParam,
        _integer_value(raw.value),
    )


def _integer_value(value: Any) -> int | None:
    """Return a JSON integer only when Slang evaluated an integral known constant."""
    constant = value.value
    if isinstance(constant, pyslang.SVInt) and not constant.hasUnknown:
        return int(constant)
    return constant if isinstance(constant, int) and not isinstance(constant, bool) else None


def dimensions(raw: Any) -> tuple[str, ...]:
    result: list[str] = []
    while isinstance(raw.canonicalType, ast.FixedSizeUnpackedArrayType):
        result.append(str(raw.canonicalType.range))
        raw = raw.canonicalType.elementType
    return tuple(result)


def packed_width(raw: Any) -> int | None:
    while isinstance(raw.canonicalType, ast.FixedSizeUnpackedArrayType):
        raw = raw.canonicalType.elementType
    return int(raw.bitWidth) if raw.isIntegral else None


def port(raw: Any, manager: Any) -> Port:
    if isinstance(raw, ast.InterfacePortSymbol):
        return Port(
            raw.name,
            "interface",
            raw.interfaceDef.name,
            None,
            location(raw.location, manager),
            interface=raw.interfaceDef.name,
            modport=str(raw.modport) or None,
        )
    return Port(
        raw.name,
        raw.direction.name.lower(),
        str(raw.type),
        packed_width(raw.type),
        location(raw.location, manager),
        dimensions(raw.type),
        default=expression_text(raw.initializer),
    )


def connected_symbols(expr: Any) -> tuple[str, ...]:
    result: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, ast.ValueExpressionBase):
            result.add(str(node.symbol.hierarchicalPath))

    if expr is not None:
        expr.visit(collect)
    return tuple(sorted(result))


def connection(raw: Any, manager: Any) -> Connection:
    if isinstance(raw.port, ast.InterfacePortSymbol):
        return Connection(
            port(raw.port, manager),
            "interface",
            None,
            tuple(str(item.hierarchicalPath) for item in raw.ifaceConn if item is not None),
            location(raw.port.location, manager),
        )
    return Connection(
        port(raw.port, manager),
        connection_kind(raw.expression),
        expression_text(raw.expression),
        connected_symbols(raw.expression),
        location(raw.expression.sourceRange.start, manager)
        if raw.expression is not None
        else SourceLocation(),
        str(raw.expression.type) if raw.expression is not None else None,
        packed_width(raw.expression.type) if raw.expression is not None else None,
    )


def connection_kind(expr: Any) -> str:
    if expr is None:
        return "unconnected"
    if isinstance(expr, ast.ConversionExpression):
        return connection_kind(expr.operand)
    if isinstance(expr, ast.ValueExpressionBase):
        return "signal"
    return "expression"
