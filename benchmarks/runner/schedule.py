"""Seeded blocked randomization, fixed pilot membership and explicit filters."""

from __future__ import annotations

import random
from dataclasses import dataclass

from benchmarks.models import MODES, Case, RunKey, Settings


@dataclass(frozen=True)
class Selection:
    mode: str | None = None
    category: str | None = None
    case: tuple[str, ...] = ()


def select_cases(
    cases: tuple[Case, ...], settings: Settings, selection: Selection
) -> tuple[Case, ...]:
    chosen = _profile_cases(cases, settings.profile, selection.case)
    if not (chosen := tuple(case for case in chosen if _matches(case, selection))):
        raise ValueError("Selection contains no cases")
    return chosen


def schedule(
    cases: tuple[Case, ...], settings: Settings, selection: Selection
) -> tuple[RunKey, ...]:
    if settings.repetitions < 1 or settings.timeout <= 0:
        raise ValueError("Repetitions and timeout must be positive")
    rng = random.Random(settings.seed)
    blocks = [(case.id, rep) for case in cases for rep in range(1, settings.repetitions + 1)]
    rng.shuffle(blocks)
    return tuple(key for block in blocks for key in _block(block, rng, selection))


def _block(block: tuple[str, int], rng: random.Random, selection: Selection) -> list[RunKey]:
    modes = list(MODES)
    rng.shuffle(modes)
    return [
        RunKey(block[0], mode, block[1])
        for mode in modes
        if selection.mode is None or selection.mode == mode
    ]


def _matches(case: Case, selection: Selection) -> bool:
    return (selection.category is None or case.category == selection.category) and (
        not selection.case or case.id in selection.case
    )


def _profile_cases(
    cases: tuple[Case, ...], profile: str, case_ids: tuple[str, ...]
) -> tuple[Case, ...]:
    if profile == "smoke":
        selected = case_ids or ("hier_generate",)
        return tuple(case for case in cases if case.id in selected)
    return tuple(case for case in cases if profile == "full" or case.pilot)
