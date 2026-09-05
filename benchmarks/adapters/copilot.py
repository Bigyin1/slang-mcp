"""Launch the system Copilot executable; authentication is owned entirely by the CLI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from benchmarks.models import Settings
from benchmarks.runner.isolation import run_environment
from benchmarks.runner.process import Command


class AgentAdapter(Protocol):
    def command(self, root: Path, prompt: str, settings: Settings) -> Command:
        """Build the same agent invocation for each experimental mode."""


class CopilotAdapter:
    def __init__(self) -> None:
        self.executable = system_copilot()

    def command(self, root: Path, prompt: str, settings: Settings) -> Command:
        arguments = [
            self.executable,
            "-p",
            prompt,
            "--model",
            settings.model,
            "--output-format",
            "json",
            "--usage-output-file",
            str(root / "usage.json"),
            "--no-ask-user",
            "--disable-builtin-mcps",
            "--no-custom-instructions",
            "--no-remote-export",
            "--disallow-temp-dir",
            "--allow-all-tools",
            "--excluded-tools=task,skill,web_fetch,web_search,fetch_copilot_cli_documentation,sql,"
            "session_store_sql,read_agent,list_agents,write_agent",
            "--additional-mcp-config",
            "@" + str(root / "mcp.json"),
        ]
        if settings.model != "auto":
            arguments.extend(("--reasoning-effort", settings.effort))
        return Command(arguments, root / "workspace", run_environment(root), settings.timeout)


def verify_version(settings: Settings) -> str:
    result = subprocess.run(
        [system_copilot(), "--version"], capture_output=True, text=True, check=True, timeout=30
    )
    if f" {settings.cli_version}." not in result.stdout:
        raise RuntimeError(f"Expected Copilot {settings.cli_version}: {result.stdout.strip()}")
    return result.stdout.strip()


def system_copilot() -> str:
    if (executable := shutil.which("copilot")) is None:
        raise RuntimeError("System copilot executable is not on PATH")
    return executable
