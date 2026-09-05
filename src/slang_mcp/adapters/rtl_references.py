"""Source-level access indexing using Slang's semantic visitor."""

from dataclasses import dataclass, replace
from typing import Any

from pyslang import ast

from slang_mcp.adapters.rtl_values import expression_text, location, reference
from slang_mcp.rtl_models import Procedure, Reference, page


@dataclass(frozen=True)
class Context:
    instance: str
    scope: str
    kind: str = "read"
    operation: str = "expression"
    block: str | None = None


class AccessIndex:
    """One rebuildable index; writes denote source assignments, not synthesized drivers."""

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.references: list[Reference] = []
        self.procedures: list[Procedure] = []
        self.block_writes: dict[str, tuple[str, ...]] = {}

    def scan(self, raw: Any, context: Context) -> None:
        if raw is None:
            return

        def visit(node: Any) -> Any:
            return self._visit(node, context)

        raw.visit(visit)

    def _visit(self, node: Any, context: Context) -> Any:
        if isinstance(node, ast.InstanceSymbol) or (
            isinstance(node, ast.GenerateBlockSymbol) and node.isUninstantiated
        ):
            return ast.VisitAction.Skip
        if isinstance(node, ast.ProceduralBlockSymbol):
            self._procedure(node, context)
            return ast.VisitAction.Skip
        if isinstance(node, ast.AssignmentExpression):
            self._assignment(node, context)
            return ast.VisitAction.Skip
        return self._visit_other(node, context)

    def _visit_other(self, node: Any, context: Context) -> Any:
        if isinstance(node, ast.GenerateBlockSymbol):
            for member in node:
                self.scan(member, replace(context, scope=str(node.hierarchicalPath)))
            return ast.VisitAction.Skip
        if isinstance(node, ast.CallExpression):
            self._call(node, context)
            return ast.VisitAction.Skip
        if isinstance(node, ast.ValueExpressionBase):
            self._record(node.symbol, node.sourceRange.start, context)
        if isinstance(node, ast.UnaryExpression) and node.op.name in {
            "Preincrement",
            "Postincrement",
            "Predecrement",
            "Postdecrement",
        }:
            self.scan(node.operand, replace(context, kind="read_write", operation="increment"))
            return ast.VisitAction.Skip
        return self._visit_symbol(node, context)

    def _visit_symbol(self, node: Any, context: Context) -> Any:
        if isinstance(node, ast.ContinuousAssignSymbol):
            self.scan(node.assignment, replace(context, operation="continuous_assignment"))
            return ast.VisitAction.Skip
        if isinstance(node, ast.SubroutineSymbol):
            self.scan(node.body, replace(context, scope=str(node.hierarchicalPath)))
            return ast.VisitAction.Skip
        if isinstance(node, (ast.VariableSymbol, ast.NetSymbol)):
            self._record(node, node.location, replace(context, kind="declaration"))
            if node.initializer is not None:
                self._initializer(node, context)
            return ast.VisitAction.Skip
        return ast.VisitAction.Advance

    def _initializer(self, node: Any, context: Context) -> None:
        self._record(
            node, node.location, replace(context, kind="write", operation="declaration_assignment")
        )
        self.scan(node.initializer, replace(context, kind="read"))

    def _assignment(self, node: Any, context: Context) -> None:
        if (operation := context.operation) != "continuous_assignment":
            operation = "nonblocking_assignment" if node.isNonBlocking else "blocking_assignment"
        self._lvalue(
            node.left,
            replace(
                context,
                kind="read_write" if node.isCompound else "write",
                operation=operation,
            ),
        )
        self.scan(node.right, replace(context, kind="read", operation=operation))

    def _lvalue(self, node: Any, context: Context) -> None:
        if isinstance(node, ast.ElementSelectExpression):
            self._lvalue(node.value, context)
            self.scan(node.selector, replace(context, kind="read"))
        elif isinstance(node, ast.RangeSelectExpression):
            self._lvalue(node.value, context)
            self.scan(node.left, replace(context, kind="read"))
            self.scan(node.right, replace(context, kind="read"))
        elif isinstance(node, ast.ConcatenationExpression):
            for operand in node.operands:
                self._lvalue(operand, context)
        else:
            self.scan(node, context)

    def port_actual(self, node: Any, context: Context) -> None:
        if context.kind in {"write", "read_write"}:
            self._lvalue(node, context)
        else:
            self.scan(node, context)

    def _call(self, node: Any, context: Context) -> None:
        if node.isSystemCall:
            for argument in node.arguments:
                self.scan(argument, replace(context, kind="unknown", operation="system_call"))
            return
        self._record(
            node.subroutine,
            node.sourceRange.start,
            replace(context, kind="unknown", operation="subroutine_call"),
        )
        for pair in zip(node.subroutine.arguments, node.arguments, strict=False):
            self.port_actual(
                pair[1],
                replace(
                    context,
                    kind=direction_kind(pair[0].direction.name.lower()),
                    operation="call_argument",
                ),
            )

    def _record(self, symbol: Any, source: Any, context: Context) -> None:
        self.references.append(
            Reference(
                reference(symbol, self.manager),
                "parameter_reference" if isinstance(symbol, ast.ParameterSymbol) else context.kind,
                location(source, self.manager),
                context.scope,
                context.instance or None,
                context.operation,
                context.block,
            )
        )

    def _procedure(self, node: Any, context: Context) -> None:
        block = self._block_id(node, context.instance)
        start = len(self.references)
        self.scan(node.body, replace(context, block=block))
        self.block_writes[block] = self._access_names(start, {"write", "read_write"})
        self.procedures.append(
            Procedure(
                block,
                node.procedureKind.name,
                context.instance,
                location(node.location, self.manager),
                page(self._access_names(start, {"read", "read_write"}), 500),
                page(self._access_names(start, {"write", "read_write"}), 500),
                expression_text(node.body.timing)
                if isinstance(node.body, ast.TimedStatement)
                else None,
            )
        )

    def _access_names(self, start: int, kinds: set[str]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.symbol.qualified_name
                    for item in self.references[start:]
                    if item.kind in kinds
                }
            )
        )

    def _block_id(self, node: Any, instance: str) -> str:
        source = location(node.location, self.manager)
        return (
            f"{instance}:{node.procedureKind.name}:{source.filename}:{source.line}:{source.column}"
        )


def direction_kind(direction: str) -> str:
    return {"in": "read", "out": "write", "inout": "read_write", "ref": "read_write"}.get(
        direction,
        "unknown",
    )
