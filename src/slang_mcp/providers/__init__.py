"""Project provider implementations."""

from slang_mcp.providers.file_lists import project_from_file_lists
from slang_mcp.providers.static import StaticProjectProvider

__all__ = ["StaticProjectProvider", "project_from_file_lists"]
