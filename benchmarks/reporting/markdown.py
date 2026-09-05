"""A self-contained Russian report generated from measured records only."""

from __future__ import annotations

import json
from collections import Counter
from typing import cast

from benchmarks.dataset import ROOT, load_cases, read_object
from benchmarks.models import MODES
from benchmarks.reporting.statistics import Record


def display(value: object) -> str:
    if value is None:
        return "н/д"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(display(value) for value in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def accuracy_table(modes: dict[str, Record]) -> str:
    return table(
        ["Режим", "Верно / оценено", "%", "Оценено / запланировано", "Сбои", "95% CI"],
        [
            [
                mode,
                f"{data['correct']} / {data['evaluable']}",
                100 * cast("float", data["task_accuracy"])
                if data["task_accuracy"] is not None
                else None,
                f"{data['evaluable']} / {data['planned']}",
                data["infrastructure_failures"],
                data["cluster_95_ci"],
            ]
            for mode, data in modes.items()
        ],
    )


def metric_table(modes: dict[str, Record], field: str) -> str:
    return table(
        ["Режим", "Наблюдений", "Среднее", "Медиана", "SD", "p90", "Сумма", "На верный ответ"],
        [
            [
                mode,
                *[
                    cast("dict[str, Record]", data["efficiency"])[field][name]
                    for name in (
                        "observed",
                        "mean",
                        "median",
                        "stddev",
                        "p90",
                        "total",
                        "per_correct",
                    )
                ],
            ]
            for mode, data in modes.items()
        ],
    )


def render(summary: Record, metadata: Record, records: list[Record]) -> str:
    modes = cast("dict[str, Record]", summary["modes"])
    sections = _opening(summary, metadata, modes, records)
    sections.extend(_quantitative(summary, modes))
    sections.extend(_qualitative(summary, records))
    sections.extend(_closing(summary, modes, records))
    sections.insert(2, _observed_models(records))
    return "\n\n".join(sections) + "\n"


def _opening(
    summary: Record, metadata: Record, modes: dict[str, Record], records: list[Record]
) -> list[str]:
    return [
        "# Бенчмарк Slang MCP / Copilot CLI",
        "## 1. Резюме\n\nИсследуется влияние Slang MCP и семантической инструкции на точность "
        f"агента. Выполнено {summary['completed']} из {summary['planned']} "
        f"запланированных запусков. "
        + _composition(metadata)
        + " "
        + "Полный эксперимент на 450 запусков отложен.\n\n"
        + _gains(modes, records),
        "## 2. Экспериментальная установка\n\nСистемный `copilot` со штатной авторизацией; "
        "Slang подключён непосредственно по stdio. В text-only MCP отключён; в mcp доступен; "
        "в mcp+skill добавлена только фиксированная стратегия. Вопросы одинаковы. "
        "Новый workspace и новая сессия на каждый запуск; один процесс агента одновременно. "
        "Фиксированы seed и лимиты. Нет LLM judge: только строгие контракты "
        "и независимые оракулы.\n\n"
        "```json\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n```\n\n"
        "Task accuracy = верно / оценено (SUCCESS + WRONG_ANSWER). Reliability = оценено / "
        "запланировано. Overall success = верно / запланировано. Сбои и незапущенные задания "
        "не маскируются под неправильные семантические ответы. CI: 2000 bootstrap выборок "
        "с ресэмплингом целых кейсов, сохраняющим связанные повторы. p-values не рассчитываются.",
        "## 3. Общая точность\n\n"
        + accuracy_table(modes)
        + "\n![Точность](figures/accuracy_overall.png)",
    ]


def _quantitative(summary: Record, modes: dict[str, Record]) -> list[str]:
    sections = [
        "## 4. Точность по категориям\n\n"
        + _group_table(cast("dict[str, Record]", summary["categories"]))
        + "\n![Категории](figures/accuracy_by_category.png)",
        "## 5. Парные исходы\n\n" + _paired_table(cast("dict[str, Record]", summary["paired"])),
        "## 6. Токены\n\n"
        + metric_table(modes, "total_tokens")
        + "\n![Токены](figures/token_usage.png)",
    ]
    sections.append(
        "Входные токены:\n\n"
        + metric_table(modes, "input_tokens")
        + "\nВыходные токены:\n\n"
        + metric_table(modes, "output_tokens")
    )
    sections.append(
        "## 7. Инструменты\n\n"
        + metric_table(modes, "tool_call_count")
        + "\n![Вызовы](figures/tool_calls.png)\n\n"
        + metric_table(modes, "mcp_tool_call_count")
        + "\n![Частота MCP](figures/mcp_tool_frequency.png)"
    )
    sections.append(
        "## 8. Время\n\n"
        + metric_table(modes, "duration_seconds")
        + "\n![Время](figures/runtime.png)\n\np50 равен медиане; p90 показан от 10 наблюдений."
    )
    return sections


def _group_table(groups: dict[str, Record]) -> str:
    return table(
        ["Группа", *MODES],
        [
            [name, *[cast("Record", group[mode])["task_accuracy"] for mode in MODES]]
            for name, group in groups.items()
        ],
    )


def _paired_table(pairs: dict[str, Record]) -> str:
    return table(
        ["Сравнение", "Оба верны", "Улучшения", "Регрессии", "Оба неверны", "Неполные", "Нетто"],
        [
            [
                name,
                *[
                    data[key]
                    for key in (
                        "both_correct",
                        "improves",
                        "regresses",
                        "both_wrong",
                        "incomplete",
                        "net_improvement",
                    )
                ],
            ]
            for name, data in pairs.items()
        ],
    )


def _qualitative(summary: Record, records: list[Record]) -> list[str]:
    pairs = cast("dict[str, Record]", summary["paired"])
    return [
        "## 9. Улучшения MCP\n\n" + _examples(pairs["text-only vs mcp"], records, "improves"),
        "## 10. Регрессии MCP\n\n" + _examples(pairs["text-only vs mcp"], records, "regresses"),
        "## 11. Эффект инструкции\n\n"
        + _paired_table({"mcp vs mcp+skill": pairs["mcp vs mcp+skill"]})
        + "\nИзменения точности, токенов, частот инструментов и сбоев приведены выше. "
        "Полезность инструкции заранее не предполагается.",
    ]


def _examples(pair: Record, records: list[Record], outcome: str) -> str:
    sections = [
        _example_for(item, records)
        for item in cast("list[Record]", pair["details"])
        if item["outcome"] == outcome
    ]
    return "\n\n".join(sections) if sections else "Такие исходы в завершённых парах не наблюдались."


def _example_for(item: Record, records: list[Record]) -> str:
    lookup = {
        r["mode"]: r
        for r in records
        if r["case_id"] == item["case_id"] and r["repetition"] == item["repetition"]
    }
    question = next(case.question for case in load_cases() if case.id == item["case_id"])
    return _example(question, lookup["text-only"], lookup["mcp"])


def _example(question: str, left: Record, right: Record) -> str:
    return (
        f"**{right['case_id']}, повтор {right['repetition']}**\n\n{question}\n\n"
        + table(
            ["Oracle", "Text-only", "MCP"], [[right["expected"], left["actual"], right["actual"]]]
        )
        + _trace_interpretation(right)
        + f"\nНаблюдаемые вызовы: text-only — {left['tool_call_count']}, "
        f"MCP — {right['tool_call_count']}, из них Slang — {right['mcp_tool_call_count']}. Трассы: "
        f"`{left['trace_path']}`, `{right['trace_path']}`."
    )


def _trace_interpretation(record: Record) -> str:
    if record["case_id"] == "cc_outputs":
        return (
            "\nНаблюдаемая причина: после `project_load` агент вызвал `get_ports(fifo_v3)`, "
            "но вернул все порты вместо запрошенного подмножества output."
        )
    return "\nПричину нельзя надёжно установить только по числу инструментальных вызовов."


def _closing(summary: Record, modes: dict[str, Record], records: list[Record]) -> list[str]:
    projects = read_object(ROOT / "cases/projects.json")
    pins = {name: value for name, value in projects.items() if name in {"axi", "common_cells"}}
    return [
        "## 12. Real-world проекты\n\n"
        + _realworld_table(cast("dict[str, Record]", summary["projects"]), projects)
        + "\n```json\n"
        + json.dumps(pins, indent=2)
        + "\n```",
        "## 13. Ограничения\n\nМалый пилот не оценивает весь корпус. Выбор задач может быть "
        "смещён в пользу семантических инструментов; scalar-answer задачи не представляют весь "
        "цикл RTL-разработки. Повторы стохастичны и связаны общим кейсом. Результат зависит от "
        "версий агента и модели. Auto может выбирать разные модели: это дополнительный смешивающий "
        "фактор. Латентность сервиса изменчива. MCP описывает source-level семантику, не netlist. "
        "По просьбе пользователя OS sandbox не используется: oracle и результаты вне workspace, "
        "но shell технически может читать внешние файлы. Системный профиль авторизации и кэши CLI "
        "общие; каждая сессия новая, память в prompt-mode по умолчанию отключена. "
        "Launcher не поддерживает надёжное отключение обновления без смены runtime: версия "
        "проверяется перед запуском; изменение версии прерывает эксперимент.",
        "## 14. Выводы\n\n"
        + _gains(modes, records)
        + "\n\nЭто описание наблюдений пилота; универсальное преимущество MCP не доказано.",
        "## 15. Исходные данные\n\n[runs.jsonl](../normalized/runs.jsonl), "
        "[summary.json](../normalized/summary.json), [summary.csv](../normalized/summary.csv), "
        "[raw traces](../raw/). Неудачные и заменённые попытки сохраняются в raw; "
        "основная агрегация использует последнюю завершённую попытку "
        "каждого ключа.",
    ]


def _gains(modes: dict[str, Record], records: list[Record]) -> str:
    values = [modes[mode]["task_accuracy"] for mode in MODES]
    if any(value is None for value in values):
        return (
            "Недостаточно завершённых ответов для сравнения всех режимов; "
            "преимущество MCP не установлено."
        )
    if len(_model_counts(records)) != 1:
        return (
            "Наблюдаемые доли точности не дают валидной причинной оценки MCP: режим `auto` "
            "маршрутизировал запросы к разным моделям. Повторить эксперимент с одной "
            "явно выбранной доступной моделью."
        )
    numbers = cast("list[float]", values)
    return (
        f"MCP − text-only: {(numbers[1] - numbers[0]) * 100:+.2f} процентного пункта. "
        f"MCP+skill − MCP: {(numbers[2] - numbers[1]) * 100:+.2f} процентного пункта."
    )


def _composition(metadata: Record) -> str:
    planned = cast("list[Record]", metadata.get("planned", []))
    return (
        f"Корпус: 50 кейсов. Текущая выборка — кейсы: {len({p['case_id'] for p in planned})}; "
        f"режимы: {len({p['mode'] for p in planned})}; "
        f"повторы: {len({p['repetition'] for p in planned})}. "
        "Проверка одного кейса является smoke, а не исследованием качества."
    )


def _observed_models(records: list[Record]) -> str:
    return "Фактические модели (из usage JSON):\n\n" + table(
        ["Модель", "Запуски"], [[model, count] for model, count in _model_counts(records).items()]
    )


def _model_counts(records: list[Record]) -> Counter[str]:
    return Counter(
        model
        for record in records
        for model in cast("list[str]", record.get("observed_models", []))
    )


def _realworld_table(groups: dict[str, Record], projects: Record) -> str:
    selected = {
        name: value
        for name, value in groups.items()
        if cast("Record", projects.get(name, {})).get("kind") == "git"
    }
    if not selected:
        return "В текущей выборке real-world проекты не запускались. Закреплённые версии корпуса:\n"
    return _group_table(selected)
