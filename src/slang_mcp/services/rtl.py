"""Bounded RTL services shared by primitive and aggregate queries."""

from slang_mcp.models import SymbolReference
from slang_mcp.project import ProjectManager
from slang_mcp.rtl_models import (
    Connection,
    Instance,
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

    def get_instance_parameters(self, instance_path: str, limit: int = 100) -> Parameters:
        return Parameters(
            instance_path,
            "effective",
            page(
                self.manager.design.rtl.parameters(instance_path, effective=True),
                limit,
            ),
        )

    def get_instance_connections(self, instance_path: str, limit: int = 100) -> Page[Connection]:
        return page(self.manager.design.rtl.connections(instance_path), limit)

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
            for name in self.manager.design.rtl.access.block_writes[block.block_id]
        )

    def _state_element(self, name: str, block: Procedure) -> StateElement:
        symbol = self.manager.design.rtl.resolve_signal(name)
        return StateElement(
            symbol.symbol, symbol.type, symbol.width, block.block_id, block.location
        )


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
