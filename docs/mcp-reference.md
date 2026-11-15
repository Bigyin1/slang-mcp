# Справочник MCP

Сервер предоставляет один каталог из 13 инструментов. Все запросы read-only:
RTL не изменяется, build-команды не запускаются. Агент сам выбирает исходники,
проверяет диагностику и добавляет зависимости по необходимости.

Рабочий сценарий — совместное чтение RTL и запросы MCP. Исходники и заголовки
объясняют выражения, условия, макросы и намерение автора; MCP даёт разрешённую
семантику выбранной конфигурации. Для кода с большим количеством макросов
проверяйте `defines`, include paths, порядок файлов и `single_unit`: определение
макроса в репозитории ещё не означает, что оно активно в загруженном фрагменте.

## Загрузка и диагностика

`project_load` принимает два обязательных поля — `source_files` и `top_module`:

```json
{
  "source_files": ["/work/types_pkg.sv", "/work/fifo.sv"],
  "top_module": "fifo",
  "include_directories": ["/work/include"],
  "defines": {"SYNTHESIS": null, "WIDTH": "32"},
  "single_unit": true
}
```

`source_files` — непустой упорядоченный список абсолютных путей. Includes и
`defines` необязательны; null define означает отсутствие replacement text.
Сервер читает только выбранные исходники и их includes, не ищет недостающие
modules/packages и не расширяет область анализа автоматически. Повторите
`project_load` для другого набора файлов или после изменения RTL.

`single_unit` — необязательный boolean, по умолчанию `true`:

- `true`: все исходники образуют одну compilation unit в указанном порядке;
  макросы и объявления уровня `$unit` доступны последующим файлам.
- `false`: каждый исходник образует отдельную compilation unit; макросы и
  `$unit`-объявления из соседнего файла не переносятся. Defines и include paths
  применяются к каждой unit. Modules и packages остаются доступны всей compilation.

Это независимые настройки: небольшой фрагмент тоже может требовать single unit.
Режим не добавляет файлы и не выбирает зависимости. Неверный тип `single_unit`,
включая null или строку `"false"`, возвращает ошибку без замены активного проекта.

Top элаборируется самостоятельно с параметрами по умолчанию. Он не наследует
переопределения из отсутствующего родителя. Сводка сообщает `single_unit`, число
файлов, errors/warnings, `analysis_scope: "fragment"`,
`parameter_context: "standalone_top"` и `completeness: "not_verified"`.
Нулевая диагностика не доказывает соответствия производственной конфигурации.

Синтаксические/семантические ошибки допустимы, пока Slang может построить top.
Если это невозможно, ответ MCP имеет `isError: true` и JSON с
`status: "compilation_failed"`, первыми 100 diagnostics, `total_count`, `truncated`
и `active_project_unchanged: true`. `analysis.context: "attempted_candidate"`
отделяет диагностику неудавшейся попытки от прежнего активного проекта; этот
контекст включает выбранный `single_unit`. Последующие запросы относятся к
предыдущей успешной загрузке, если она была.

`project_info()` возвращает активные sources/includes/defines, tops, `single_unit`,
metadata, версию Slang и сводку без повторной компиляции.

`get_diagnostics(severity?, limit=100)` возвращает diagnostics, `returned_count`,
`total_count`, `truncated` и контекст анализа. Severity: `ignored`, `note`,
`warning`, `error`, `fatal`. UnknownModule/UnknownClassOrPackage получают
`scope_hint: "possible_missing_dependency"`; прочие — `"unclassified"`.
Это возможная причина, а не признание ошибки безвредной: опечатка даёт ту же
диагностику. Исходная severity никогда не понижается.

## Поиск и иерархия

| Инструмент | Аргументы и семантика |
| --- | --- |
| `find_symbol` | `name`: точное короткое имя; все совпадения и `match_count`. |
| `describe_symbol` | `identifier`: полное или однозначное короткое имя; kind, type, width, location и доступные сведения о symbol. |
| `list_symbols` | `scope`, необязательный `kind`, `limit`: непосредственные объявления scope; без рекурсивного обхода. Scope может быть именем модуля, идентификатором symbol или точным путём вложенного instance/generate. Имя top, совпадающее с именем модуля, выбирает параметры по умолчанию модуля. |
| `get_hierarchy` | Необязательные `root`, `max_depth` (0–50): элаборированные instances и активные generate blocks; без depth возвращается всё выбранное поддерево. |
| `list_instances` | Необязательные `sv_module`, `name`, `path_prefix`, `limit`: фильтры по module type, точному имени instance и префиксу пути. |

`sv_module` обозначает объявление module/interface, `instance_path` — конкретный
элаборированный экземпляр, например `top.u_fifo`. Неоднозначные имена дают
контролируемую ошибку; полные пути предпочтительнее.

## Инспекция

`inspect_module(sv_module, ...)` по умолчанию возвращает `definition`, default
`parameters` и `ports`. Дополнительные разделы доступны через `fields`:
`declaration_count`, `children`, `procedures`, `diagnostic_count`.
Children/procedures относятся к активным экземплярам данного module; diagnostic
count относится к тому же source file, а не только к выбранному объявлению.

`inspect_instance(instance_path, ...)` по умолчанию возвращает `instance`, effective
`parameters` и `connections`. Через `fields` можно также запросить `children`.

Оба инструмента принимают необязательные `fields`, `parameter_names`, `port_names`
и `limit=100`. Identity возвращается всегда; `fields: []` оставляет только identity.
Незапрошенные разделы не вычисляются. Именованные фильтры выбирают точные имена
до ограничения limit, сохраняют declaration order и допускают до 500 имён.
Отсутствующее имя не вызывает ошибку; пустой список выбирает ноль элементов.

```json
{"instance_path":"top.u_fifo","fields":["parameters"],"parameter_names":["DEPTH"]}
```

Parameters содержат точное SystemVerilog-представление `value`. Удобное
`integer_value` равно null для type parameters, X/Z и констант за пределами
signed 64-bit integer. Module parameters имеют `value_kind: "declared_default"`,
instance parameters — `"effective"`.

Connections содержат formal port, actual expression, базовые resolved symbols,
actual type/width и location. `kind`: `signal`, `expression`, `unconnected`,
`interface`. Например, expression `request.address` и базовый symbol `request`
описывают разные аспекты одного подключения. Текст выражений и списки symbols
ограничены; признаки truncation передаются в ответе.

`list_instance_facts(sv_module, parameter_names?, port_names?, limit=100,
fact_limit=100)` возвращает параметры и connections нескольких однотипных
instances за один вызов. `limit` ограничивает число instances, `fact_limit` —
каждую вложенную коллекцию. Это сокращает повторные запросы по каждому пути.

## Обращения и состояние

`get_references(symbol, kind?, limit=100)` возвращает declaration и semantic uses
символа с location, scope, instance, context и при наличии procedural block id.
Kinds: `read`, `write`, `read_write`, `declaration`, `unknown`,
`parameter_reference`, `port_connection`, `type_reference`, `instantiation`.
Фильтры `read` и `write` оба включают `read_write` (например, `count += 1`).
Это обращения в исходнике, не число аппаратных consumers/drivers.
Обращения внутри процедурных ветвей могут присутствовать даже при параметрах,
делающих ветвь неактивной; ответ не содержит доказательства выполнимости ветвей.
Условия и RHS следует проверять по RTL с учётом effective parameters.

`get_state_elements(sv_module, limit=100)` возвращает signals, записываемые в
`always_ff`, с type, width, block id и location. Не выводит reset behavior,
latches или synthesis inference для обычных `always`.

## Границы анализа

Коллекции имеют `items`, `total_count`, `truncated`; limit допустим от 1 до 500.
Отсутствующие зависимости могут сделать типы/ширины и иерархию неполными.
Локальный успешный запрос не подтверждает корректности остального RTL.

Сервер использует Slang AST и общий ленивый индекс source-level accesses, не
regex-парсер. Default elaboration использует исходные syntax trees с теми же
границами compilation units. Ответы не доказывают netlist connectivity, timing,
simulation или formal equivalence.

Старые профили `core`/`full`, отдельные read/write getters, file-list loader,
connectivity и `semantic_diff` не входят в публичный API. Повторная загрузка
заменяет reload; структурные snapshots сервер не строит. Исторические эксперименты
с прежним API следует воспроизводить на указанной в отчёте ревизии.
