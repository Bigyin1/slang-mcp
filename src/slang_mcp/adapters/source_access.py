"""Extract source accesses and dependency edges with Slang's semantic visitor."""

from dataclasses import dataclass, replace
from typing import Any, Literal

from pyslang import ast

from slang_mcp.adapters.semantic_normalization import expression_text, location, reference
from slang_mcp.rtl_models import ConnectivityHop, Procedure, Reference, page


@dataclass(frozen=True)
class AccessContext:
    """Semantic context attached to references found during one visitor traversal."""

    instance: str
    scope: str
    kind: str = "read"
    operation: str = "expression"
    block: str | None = None


@dataclass(frozen=True)
class ConnectivityDependency:
    """Raw compiler symbols and context used to create one dependency edge."""

    sources: tuple[Any, ...]
    targets: tuple[Any, ...]
    kind: Literal["port_binding", "continuous_assignment", "procedural_assignment"]
    source: Any
    context: AccessContext
    operation: str
    formal_port: str | None = None


class SourceAccessIndex:
    """Collect source reads, writes, procedures and connectivity dependencies.

    Writes describe source assignments and port semantics; they are not inferred
    synthesized or simulation drivers.
    """

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.references: list[Reference] = []
        self.procedures: list[Procedure] = []
        self.block_writes: dict[str, tuple[str, ...]] = {}
        self.connectivity: list[ConnectivityHop] = []

    def scan(self, raw: Any, context: AccessContext) -> None:
        if raw is None:
            return

        def visit(node: Any) -> Any:
            return self._visit(node, context)

        raw.visit(visit)

    def _visit(self, node: Any, context: AccessContext) -> Any:
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

    def _visit_other(self, node: Any, context: AccessContext) -> Any:
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

    def _visit_symbol(self, node: Any, context: AccessContext) -> Any:
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

    def _initializer(self, node: Any, context: AccessContext) -> None:
        self._record(
            node, node.location, replace(context, kind="write", operation="declaration_assignment")
        )
        self.scan(node.initializer, replace(context, kind="read"))
        self._dependency(
            ConnectivityDependency(
                self._expression_symbols(node.initializer),
                (node,),
                "procedural_assignment",
                node.location,
                context,
                "declaration_assignment",
            )
        )

    def _assignment(self, node: Any, context: AccessContext) -> None:  # pylint: disable=too-many-locals
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
        sources = self._expression_symbols(node.right)
        targets = self._expression_symbols(node.left)
        if node.isCompound:
            sources = (*sources, *targets)
        self._dependency(
            ConnectivityDependency(
                sources,
                targets,
                "continuous_assignment"
                if operation == "continuous_assignment"
                else "procedural_assignment",
                node.sourceRange.start,
                context,
                f"compound_{operation}" if node.isCompound else operation,
            )
        )

    def _lvalue(self, node: Any, context: AccessContext) -> None:
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

    def port_actual(self, node: Any, context: AccessContext) -> None:
        if context.kind in {"write", "read_write"}:
            self._lvalue(node, context)
        else:
            self.scan(node, context)

    def port_binding(  # pylint: disable=too-many-locals
        self, node: Any, port_symbol: Any, context: AccessContext
    ) -> None:
        """Index only direct signal actuals, never expressions or interface ports."""
        if (actual := self._direct_port_actual(node)) is None:
            return
        direction = port_symbol.direction.name.lower()
        for source, target in _port_pairs(actual.symbol, port_symbol, direction):
            self._dependency(
                ConnectivityDependency(
                    (source,),
                    (target,),
                    "port_binding",
                    actual.sourceRange.start,
                    context,
                    direction,
                    port_symbol.name,
                )
            )

    @staticmethod
    def _direct_port_actual(node: Any) -> Any | None:
        if isinstance(node, ast.AssignmentExpression):
            node = node.left
        return node if isinstance(node, ast.NamedValueExpression) else None

    def _expression_symbols(self, node: Any) -> tuple[Any, ...]:
        symbols: dict[str, Any] = {}

        def visit(item: Any) -> Any:
            if isinstance(item, ast.ValueExpressionBase):
                symbols.setdefault(reference(item.symbol, self.manager).qualified_name, item.symbol)
            return ast.VisitAction.Advance

        node.visit(visit)
        return tuple(symbols.values())

    def _dependency(self, dependency: ConnectivityDependency) -> None:  # pylint: disable=too-many-locals
        for source_symbol in dependency.sources:
            source_name = reference(source_symbol, self.manager).qualified_name
            for target_symbol in dependency.targets:
                target_name = reference(target_symbol, self.manager).qualified_name
                if source_name != target_name:
                    self.connectivity.append(
                        ConnectivityHop(
                            source_name,
                            target_name,
                            dependency.kind,
                            location(dependency.source, self.manager),
                            dependency.context.instance or None,
                            dependency.formal_port,
                            dependency.operation,
                        )
                    )

    def _call(self, node: Any, context: AccessContext) -> None:
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

    def _record(self, symbol: Any, source: Any, context: AccessContext) -> None:
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

    def _procedure(self, node: Any, context: AccessContext) -> None:
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


def _port_pairs(actual: Any, formal: Any, direction: str) -> tuple[tuple[Any, Any], ...]:
    if direction == "in":
        return ((actual, formal),)
    if direction == "out":
        return ((formal, actual),)
    if direction in {"inout", "ref"}:
        return ((actual, formal), (formal, actual))
    return ()
