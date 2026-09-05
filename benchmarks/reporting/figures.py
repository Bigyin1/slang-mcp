"""Static matplotlib figures, including explicit missing-data panels."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import cast

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from benchmarks.models import MODES
from benchmarks.reporting.statistics import Record

_CHARTS = (
    ("total_tokens", "token_usage.png", "Средние токены на запуск"),
    ("tool_call_count", "tool_calls.png", "Средние вызовы инструментов на запуск"),
    ("duration_seconds", "runtime.png", "Среднее время запуска, секунды"),
)


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else math.nan


def bar_chart(path: Path, title: str, labels: list[str], values: list[float]) -> None:
    axis = Figure(figsize=(9, 5), layout="constrained").add_subplot()
    axis.set_title(title)
    if values and not all(math.isnan(value) for value in values):
        axis.bar(labels, values)
        axis.tick_params(axis="x", labelrotation=20)
    else:
        axis.text(
            0.5, 0.5, "Нет доступных данных", ha="center", va="center", transform=axis.transAxes
        )
    _save(axis, path)


def _save(axis: Axes, path: Path) -> None:
    figure = cast("Figure", axis.figure)
    FigureCanvasAgg(figure)
    figure.savefig(path, dpi=160)
    figure.clear()


def generate_figures(summary: Record, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    modes = cast("dict[str, Record]", summary["modes"])
    bar_chart(
        folder / "accuracy_overall.png",
        "Task accuracy (0-1)",
        list(MODES),
        [_number(modes[mode]["task_accuracy"]) for mode in MODES],
    )
    for chart in _CHARTS:
        bar_chart(
            folder / chart[1],
            chart[2],
            list(MODES),
            [_metric(modes[mode], chart[0]) for mode in MODES],
        )
    _tool_frequency(modes, folder)
    _categories(cast("dict[str, Record]", summary["categories"]), folder)


def _metric(mode: Record, field: str) -> float:
    return _number(cast("dict[str, Record]", mode["efficiency"])[field]["mean"])


def _tool_frequency(modes: dict[str, Record], folder: Path) -> None:
    frequency: Counter[str] = Counter()
    for mode in modes.values():
        frequency.update(cast("dict[str, int]", mode["tool_frequency"]))
    ordered = sorted(frequency, key=lambda name: frequency[name], reverse=True)
    bar_chart(
        folder / "mcp_tool_frequency.png",
        "Частота инструментов Slang MCP",
        ordered,
        [float(frequency[name]) for name in ordered],
    )


def _categories(categories: dict[str, Record], folder: Path) -> None:
    axis = Figure(figsize=(11, 5), layout="constrained").add_subplot()
    for index, mode in enumerate(MODES):
        _category_bars(axis, categories, (index, mode))
    axis.set_xticks(
        [position + 0.25 for position in range(len(categories))],
        list(categories),
        rotation=20,
        ha="right",
    )
    axis.set_ylim(0, 1)
    axis.set_title("Task accuracy по категориям")
    axis.legend()
    _save(axis, folder / "accuracy_by_category.png")


def _category_bars(axis: Axes, categories: dict[str, Record], group: tuple[int, str]) -> None:
    axis.bar(
        [position + group[0] * 0.25 for position in range(len(categories))],
        [
            _number(cast("Record", category[group[1]])["task_accuracy"])
            for category in categories.values()
        ],
        width=0.25,
        label=group[1],
    )
