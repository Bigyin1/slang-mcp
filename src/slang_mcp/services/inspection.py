"""Compact aggregate views built from shared RTL queries."""

from slang_mcp.rtl_models import (
    Instance,
    InstanceInspection,
    ModuleInspection,
    Page,
    SignalInspection,
    page,
)
from slang_mcp.services.rtl import RtlService


class InspectionService:
    def __init__(self, rtl: RtlService) -> None:
        self.rtl = rtl

    def inspect_signal(self, signal: str, limit: int = 10) -> SignalInspection:
        return SignalInspection(
            self.rtl.manager.design.rtl.resolve_signal(signal),
            self.rtl.get_references(signal, limit=1).total_count,
            self.rtl.get_signal_reads(signal, limit),
            self.rtl.get_signal_writes(signal, limit),
            self.rtl.get_drivers(signal, limit),
            self.rtl.get_loads(signal, limit),
        )

    def inspect_instance(self, instance_path: str, limit: int = 100) -> InstanceInspection:
        return InstanceInspection(
            self.rtl.find_instance(instance_path),
            self.rtl.get_instance_parameters(instance_path, limit),
            self.rtl.get_instance_connections(instance_path, limit),
            self._children(self.rtl.find_instance(instance_path).path, limit),
        )

    def inspect_module(self, sv_module: str, limit: int = 100) -> ModuleInspection:
        definition = self.rtl.manager.design.rtl.definition(sv_module)
        return ModuleInspection(
            definition,
            self.rtl.get_parameters(sv_module, limit),
            self.rtl.get_ports(sv_module, limit),
            self.rtl.list_symbols(sv_module, limit=1).total_count,
            self._module_children(definition.name, limit),
            self.rtl.get_procedural_blocks(sv_module, limit),
            sum(
                item.location.filename == definition.location.filename
                for item in self.rtl.manager.design.diagnostics
            ),
        )

    def _children(self, path: str, limit: int) -> Page[Instance]:
        return page(
            tuple(
                item
                for item in self.rtl.manager.design.rtl.instances.values()
                if item.parent == path
            ),
            limit,
        )

    def _module_children(self, name: str, limit: int) -> Page[Instance]:
        return page(
            tuple(
                child
                for instance in self.rtl.manager.design.rtl.instances.values()
                if instance.sv_module == name
                for child in self._children(instance.path, 500).items
            ),
            limit,
        )
