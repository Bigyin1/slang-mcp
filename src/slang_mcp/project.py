"""Active compilation lifecycle management."""

from pathlib import Path
from typing import TYPE_CHECKING

from slang_mcp.adapters import SlangDesign
from slang_mcp.errors import InvalidProjectConfigError, ProjectNotLoadedError
from slang_mcp.models import ProjectConfig, ProjectInfo, ProjectSummary
from slang_mcp.rtl_models import SemanticDiff
from slang_mcp.semantic_snapshot import compare, snapshot

if TYPE_CHECKING:
    from slang_mcp.providers.static import StaticProjectProvider


class ProjectManager:
    """Validate, compile, and retain one project.

    ``provider`` supports test-only legacy fixtures. Production code calls
    ``load_config`` with direct file-list inputs normalized by the service.
    """

    def __init__(self, provider: "StaticProjectProvider | None" = None) -> None:
        self._provider = provider
        self._config: ProjectConfig | None = None
        self._design: SlangDesign | None = None
        self._previous_snapshot: dict[str, str] | None = None
        self._snapshot: dict[str, str] = {}

    @property
    def design(self) -> SlangDesign:
        if self._design is None:
            raise ProjectNotLoadedError("no project is loaded")
        return self._design

    def load(self, logical_module: str) -> ProjectSummary:
        """Load a test-only legacy logical-module fixture."""
        if self._provider is None:
            raise ValueError("logical-module loading is not configured")
        config = self._provider.resolve(logical_module)
        return self.load_config(config)

    def load_config(self, config: ProjectConfig) -> ProjectSummary:
        _validate_paths(config)
        design = SlangDesign(config)
        normalized = snapshot(design)
        self._previous_snapshot = (
            self._snapshot
            if self._config is not None and (self._config.logical_module == config.logical_module)
            else None
        )
        self._snapshot = normalized
        self._config = config
        self._design = design
        return _summary(config, design)

    def semantic_diff(self, limit: int = 100) -> SemanticDiff:
        if self._design is None:
            raise ProjectNotLoadedError("no project is loaded")
        return compare(self._previous_snapshot, self._snapshot, limit)

    def reload(self) -> ProjectSummary:
        if self._config is None:
            raise ProjectNotLoadedError("no project is loaded")
        return self.load_config(self._config)

    def info(self) -> ProjectInfo:
        if self._config is None:
            raise ProjectNotLoadedError("no project is loaded")
        config = self._config
        design = self.design
        return ProjectInfo(
            _summary(config, design),
            tuple(str(path) for path in config.source_files),
            tuple(str(path) for path in config.include_directories),
            tuple(_format_define(name, value) for name, value in config.defines.items()),
            config.top_modules,
            config.metadata,
            design.slang_version,
        )


def _validate_paths(config: ProjectConfig) -> None:
    for source in config.source_files:
        _require_path(source, "source file", expect_directory=False)
    for include in config.include_directories:
        _require_path(include, "include directory", expect_directory=True)


def _require_path(path: Path, label: str, *, expect_directory: bool) -> None:
    if not (path.is_dir() if expect_directory else path.is_file()):
        raise InvalidProjectConfigError(f"missing or invalid {label}: {path}")


def _summary(config: ProjectConfig, design: SlangDesign) -> ProjectSummary:
    errors = sum(item.severity in {"error", "fatal"} for item in design.diagnostics)
    warnings = sum(item.severity == "warning" for item in design.diagnostics)
    return ProjectSummary(
        config.logical_module,
        len(config.source_files),
        len(config.include_directories),
        len(config.defines),
        design.top_modules,
        errors,
        warnings,
    )


def _format_define(name: str, value: str | None) -> str:
    return name if value is None else f"{name}={value}"
