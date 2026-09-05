"""Validated, controller-owned experiment models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["text-only", "mcp", "mcp+skill"]
MODES: tuple[Mode, ...] = ("text-only", "mcp", "mcp+skill")
CATEGORIES = (
    "hierarchy",
    "symbols",
    "types/parameters",
    "preprocessing",
    "diagnostics",
    "local reasoning",
)
EVALUABLE = ("SUCCESS", "WRONG_ANSWER")


@dataclass(frozen=True)
class Case:
    """Oracle is controller-only; never serialize this object into a workspace."""

    id: str
    category: str
    project: str
    question: str
    response_contract: str
    oracle: object
    rationale: str
    pilot: bool = False


@dataclass(frozen=True)
class Settings:
    model: str = "auto"
    effort: str = "medium"
    cli_version: str = "1.0.83"
    repetitions: int = 3
    timeout: float = 300
    seed: int = 20260905
    profile: str = "pilot"


@dataclass(frozen=True)
class RunKey:
    case_id: str
    mode: Mode
    repetition: int

    @property
    def slug(self) -> str:
        return f"{self.case_id}/{self.mode}/rep_{self.repetition:02d}"
