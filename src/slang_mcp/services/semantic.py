"""Public semantic service independent of MCP transport and pyslang objects."""

from slang_mcp.models import (
    Diagnostic,
    DiagnosticCodeSummary,
    HierarchyNode,
    InstanceDescription,
    ProjectInfo,
    ProjectSummary,
    SymbolDescription,
    SymbolReference,
)
from slang_mcp.project import ProjectManager
from slang_mcp.providers.file_lists import project_from_file_lists
from slang_mcp.rtl_models import Page, SemanticDiff, page
from slang_mcp.services.inspection import InspectionService
from slang_mcp.services.rtl import RtlService

_MAX_DIAGNOSTICS = 500
_MAX_HIERARCHY_DEPTH = 50
_DIAGNOSTIC_SEVERITIES = {"ignored", "note", "warning", "error", "fatal"}


class SemanticService:
    """Application API used by MCP handlers and integration tests."""

    def __init__(self, manager: ProjectManager) -> None:
        self._manager = manager
        self.rtl = RtlService(manager)
        self.inspection = InspectionService(self.rtl)

    def semantic_diff(self, limit: int = 100) -> SemanticDiff:
        return self._manager.semantic_diff(limit)

    def project_load(self, logical_module: str) -> ProjectSummary:
        if not logical_module.strip():
            raise ValueError("logical_module must not be empty")
        return self._manager.load(logical_module)

    def project_load_file_lists(
        self,
        source_file_lists: list[str],
        top_module: str,
        include_directory_lists: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
    ) -> ProjectSummary:
        return self._manager.load_config(
            project_from_file_lists(
                source_file_lists,
                include_directory_lists or [],
                defines or {},
                top_module,
            )
        )

    def project_reload(self) -> ProjectSummary:
        return self._manager.reload()

    def project_info(self) -> ProjectInfo:
        return self._manager.info()

    def get_diagnostics(
        self,
        limit: int = 100,
        severity: str | None = None,
    ) -> tuple[Diagnostic, ...]:
        if limit < 1 or limit > _MAX_DIAGNOSTICS:
            raise ValueError(f"limit must be between 1 and {_MAX_DIAGNOSTICS}")
        normalized = self._diagnostic_severity(severity)
        selected = (
            item
            for item in self._manager.design.diagnostics
            if normalized is None or item.severity == normalized
        )
        return tuple(list(selected)[:limit])

    def summarize_diagnostics_by_code(  # pylint: disable=too-many-locals
        self, severity: str | None = None, limit: int = 100
    ) -> Page[DiagnosticCodeSummary]:
        """Group diagnostics by compiler code before requesting individual entries."""
        normalized = self._diagnostic_severity(severity)
        groups: dict[str, list[Diagnostic]] = {}
        for diagnostic in self._manager.design.diagnostics:
            if normalized is None or diagnostic.severity == normalized:
                groups.setdefault(diagnostic.code, []).append(diagnostic)
        return page(
            tuple(
                DiagnosticCodeSummary(
                    code,
                    len(items),
                    {
                        name: sum(item.severity == name for item in items)
                        for name in sorted({item.severity for item in items})
                    },
                    items[0].message,
                    items[0].location,
                )
                for code, items in sorted(groups.items())
            ),
            limit,
        )

    @staticmethod
    def _diagnostic_severity(severity: str | None) -> str | None:
        """Validate and normalize an optional diagnostic severity."""
        normalized = severity.lower() if severity is not None else None
        if normalized is not None and normalized not in _DIAGNOSTIC_SEVERITIES:
            raise ValueError(
                f"severity must be one of: {', '.join(sorted(_DIAGNOSTIC_SEVERITIES))}"
            )
        return normalized

    def find_symbol(self, name: str) -> tuple[SymbolReference, ...]:
        if not name:
            raise ValueError("name must not be empty")
        return self._manager.design.find_symbols(name)

    def describe_symbol(self, identifier: str) -> SymbolDescription:
        if not identifier:
            raise ValueError("identifier must not be empty")
        return self._manager.design.describe_symbol(identifier)

    def get_hierarchy(
        self,
        root: str | None = None,
        max_depth: int | None = None,
    ) -> tuple[HierarchyNode, ...]:
        if max_depth is not None and not 0 <= max_depth <= _MAX_HIERARCHY_DEPTH:
            raise ValueError(f"max_depth must be between 0 and {_MAX_HIERARCHY_DEPTH}")
        return self._manager.design.get_hierarchy(root, max_depth)

    def describe_instance(self, path: str) -> InstanceDescription:
        if not path:
            raise ValueError("path must not be empty")
        return self._manager.design.describe_instance(path)
