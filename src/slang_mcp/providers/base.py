"""Test-only compatibility seam for fixture project resolution."""

from typing import Protocol

from slang_mcp.models import ProjectConfig


class ProjectProvider(Protocol):
    """Resolve a logical build module for tests and offline validation only."""

    def resolve(self, logical_module: str) -> ProjectConfig:
        """Resolve one logical module or raise UnknownLogicalModuleError."""
