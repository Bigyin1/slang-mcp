"""Bounded RTL services shared by primitive and aggregate queries."""

from collections.abc import Callable
from typing import TypeVar

from slang_mcp.models import SymbolReference
from slang_mcp.project import ProjectManager
from slang_mcp.rtl_models import (
    MAX_RESULTS,
    Connection,
    ConnectivityTrace,
    Instance,
    InstanceFacts,
    Page,
    Parameters,
    Port,
    Procedure,
    Reference,
    StateElement,
    page,
)

_REFERENCE_KINDS = {
    "read",
    "write",
    "read_write",
    "declaration",
    "unknown",
    "parameter_reference",
    "port_connection",
    "type_reference",
    "instantiation",
}
_TRACE_DIRECTIONS = {"drivers", "loads", "both"}
_MAX_TRACE_DEPTH = 50
T = TypeVar("T")


class RtlService:
    """Semantic facts with explicit limits and conservative access classification."""

    def __init__(self, manager: ProjectManager) -> None:
        self.manager = manager

    def get_references(
        self,
        symbol: str,
        kind: str | None = None,
        limit: int = 100,
    ) -> Page[Reference]:
        if kind is not None and kind not in _REFERENCE_KINDS:
            raise ValueError(f"unknown reference kind: {kind}")
        return page(
            tuple(
                item
                for item in self.manager.design.rtl.references(symbol)
                if kind is None or kind in {item.kind, item.context}
            ),
            limit,
        )

    def list_symbols(
        self,
        scope: str,
        kind: str | None = None,
        limit: int = 100,
    ) -> Page[SymbolReference]:
        return page(
            tuple(
                item
                for item in self.manager.design.rtl.members(scope)
                if kind is None or item.kind == kind
            ),
            limit,
        )

    def get_ports(self, sv_module: str, limit: int = 100) -> Page[Port]:
        return page(self.manager.design.rtl.ports(sv_module), limit)

    def get_parameters(self, target: str, limit: int = 100) -> Parameters:
        # A bare top name denotes its declaration. Use the explicit instance tool for tops.
        if target in self.manager.design.rtl.instances and "." in target:
            return self.get_instance_parameters(target, limit)
        return Parameters(
            target,
            "declared_default",
            page(
                self.manager.design.rtl.parameters(target, effective=False),
                limit,
            ),
        )

    def get_instance_parameters(
        self,
        instance_path: str,
        limit: int = 100,
        names: list[str] | None = None,
    ) -> Parameters:
        return Parameters(
            instance_path,
            "effective",
            page(
                _named(
                    self.manager.design.rtl.parameters(instance_path, effective=True),
                    names,
                    lambda item: item.name,
                ),
                limit,
            ),
        )

    def get_instance_connections(
        self,
        instance_path: str,
        limit: int = 100,
        ports: list[str] | None = None,
    ) -> Page[Connection]:
        return page(
            _named(
                self.manager.design.rtl.connections(instance_path),
                ports,
                lambda item: item.port.name,
            ),
            limit,
        )

    def list_instance_facts(  # pylint: disable=too-many-locals
        self,
        sv_module: str,
        parameter_names: list[str] | None = None,
        port_names: list[str] | None = None,
        limit: int = 100,
        fact_limit: int = 100,
    ) -> Page[InstanceFacts]:
        """Return selected effective facts for instances of one module type.

        The outer page limits instances; every nested fact collection is paged
        separately to retain bounded MCP responses.
        """
        _validate_names(parameter_names, "parameter_names")
        _validate_names(port_names, "port_names")
        instances = page(
            tuple(
                item
                for item in self.manager.design.rtl.instances.values()
                if _instance_matches(item, sv_module, None, None)
            ),
            limit,
        )
        return Page(
            tuple(
                InstanceFacts(
                    instance,
                    page(
                        _named(
                            self.manager.design.rtl.parameters(instance.path, effective=True),
                            parameter_names,
                            lambda item: item.name,
                        ),
                        fact_limit,
                    ),
                    page(
                        _named(
                            self.manager.design.rtl.connections(instance.path),
                            port_names,
                            lambda item: item.port.name,
                        ),
                        fact_limit,
                    ),
                )
                for instance in instances.items
            ),
            instances.total_count,
            instances.truncated,
        )

    def list_instances(
        self,
        sv_module: str | None = None,
        name: str | None = None,
        path_prefix: str | None = None,
        limit: int = 100,
    ) -> Page[Instance]:
        return page(
            tuple(
                item
                for item in self.manager.design.rtl.instances.values()
                if _instance_matches(item, sv_module, name, path_prefix)
            ),
            limit,
        )

    def find_instance(self, query: str) -> Instance:
        return self.manager.design.rtl.resolve_instance(query)

    def accesses(self, signal: str, kinds: set[str], limit: int) -> Page[Reference]:
        return page(
            tuple(
                item for item in self.manager.design.rtl.references(signal) if item.kind in kinds
            ),
            limit,
        )

    def get_signal_reads(self, signal: str, limit: int = 100) -> Page[Reference]:
        return self.accesses(signal, {"read", "read_write"}, limit)

    def get_signal_writes(self, signal: str, limit: int = 100) -> Page[Reference]:
        return self.accesses(signal, {"write", "read_write"}, limit)

    def get_drivers(self, signal: str, limit: int = 100) -> Page[Reference]:
        return self.get_signal_writes(signal, limit)

    def get_loads(self, signal: str, limit: int = 100) -> Page[Reference]:
        return self.get_signal_reads(signal, limit)

    def trace_connectivity(
        self,
        signal: str,
        direction: str = "both",
        max_depth: int = 5,
        limit: int = 100,
    ) -> ConnectivityTrace:
        if direction not in _TRACE_DIRECTIONS:
            raise ValueError(f"unknown trace direction: {direction}")
        if not 0 <= max_depth <= _MAX_TRACE_DEPTH:
            raise ValueError(f"max_depth must be between 0 and {_MAX_TRACE_DEPTH}")
        if not 1 <= limit <= MAX_RESULTS:
            raise ValueError("limit must be between 1 and 500")
        return self.manager.design.rtl.trace_connectivity(signal, direction, max_depth, limit)

    def get_procedural_blocks(self, sv_module: str, limit: int = 100) -> Page[Procedure]:
        return page(self.manager.design.rtl.procedures(sv_module), limit)

    def get_state_elements(self, sv_module: str, limit: int = 100) -> Page[StateElement]:
        return page(
            tuple(
                element
                for block in self.manager.design.rtl.procedures(sv_module)
                if block.kind == "AlwaysFF"
                for element in self._state_elements(block)
            ),
            limit,
        )

    def _state_elements(self, block: Procedure) -> tuple[StateElement, ...]:
        return tuple(
            self._state_element(name, block)
            for name in self.manager.design.rtl.procedure_writes(block.block_id)
        )

    def _state_element(self, name: str, block: Procedure) -> StateElement:
        symbol = self.manager.design.rtl.resolve_signal(name)
        return StateElement(
            symbol.symbol, symbol.type, symbol.width, block.block_id, block.location
        )


def _named(
    items: tuple[T, ...],
    names: list[str] | None,
    identifier: Callable[[T], str],
) -> tuple[T, ...]:
    """Keep declaration-order items matching optional exact names."""
    if names is None:
        return items
    _validate_names(names, "names")
    requested = frozenset(names)
    return tuple(item for item in items if identifier(item) in requested)


def _validate_names(names: list[str] | None, argument: str) -> None:
    if names is not None and len(names) > MAX_RESULTS:
        raise ValueError(f"{argument} must contain at most 500 items")


def _instance_matches(
    item: Instance,
    sv_module: str | None,
    name: str | None,
    path_prefix: str | None,
) -> bool:
    return (
        (sv_module is None or item.sv_module == sv_module)
        and (name is None or item.name == name)
        and (path_prefix is None or item.path.startswith(path_prefix))
    )
