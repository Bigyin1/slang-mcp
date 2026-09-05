"""Small real-compilation harness for semantic regression tests."""

from dataclasses import dataclass
from pathlib import Path

from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService


@dataclass(frozen=True)
class RtlProject:
    source_file: Path
    service: SemanticService

    def reload(self, source: str) -> None:
        self.source_file.write_text(source, encoding="utf-8")
        self.service.project_reload()


def load_rtl(directory: Path, source: str) -> RtlProject:
    source_file = directory / "regression.sv"
    source_file.write_text(source, encoding="utf-8")
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {
                    "regression": ProjectConfig("regression", (source_file,), top_modules=("top",)),
                }
            )
        )
    )
    assert service.project_load("regression").diagnostic_error_count == 0
    return RtlProject(source_file, service)
