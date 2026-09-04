"""Build-system integration seam."""

from typing import Protocol

from slang_mcp.models import ProjectConfig


class ProjectProvider(Protocol):
    """Resolve a logical build module into concrete compiler inputs."""

    def resolve(self, logical_module: str) -> ProjectConfig:
        """Resolve one logical module or raise UnknownLogicalModuleError."""
