# Справочник MCP tools

`slang-mcp` — read-only MCP-сервер для семантического анализа уже
сконфигурированных SystemVerilog-проектов. Все tools возвращают JSON-совместимые
данные и не меняют RTL, build-конфигурацию или файлы проекта.

Сначала вызовите `project_load`, затем выполняйте запросы к активному проекту.
`project_reload` заново разрешает и компилирует тот же logical module.

## Общие правила

- `logical_module` — имя build-конфигурации, а не SystemVerilog module.
- `sv_module` — имя объявления `module` или `interface`.
- `instance_path` — элаборированный путь, например `top.u_fifo`.
- `signal` принимает полное имя сигнала; короткое имя допускается только если оно
  однозначно.
- `limit` по умолчанию равен 100 и должен быть от 1 до 500, если конкретный tool
  не указывает другое значение.
- Постраничный ответ имеет вид
  `{"items": [...], "total_count": N, "truncated": false}`. `truncated: true`
  означает, что по указанному limit возвращена только часть результата.
- Контролируемые ошибки MCP включают отсутствие активного проекта, неизвестный
  logical module, отсутствующий или неоднозначный symbol/instance и неверные
  границы параметров.

## Жизненный цикл проекта

### `project_load`

```json
{"logical_module": "demo"}
```

Разрешает build-конфигурацию, проверяет source/include paths и создаёт Slang
compilation. Возвращает `logical_module`, количества source files, include dirs и
defines, configured tops и количество error/warning diagnostics. Успешная
компиляция с diagnostics всё равно доступна для анализа.

### `project_reload`

Не принимает аргументы. Пересобирает активный logical module и возвращает ту же
сводку, что `project_load`. Предыдущая успешная semantic snapshot сохраняется для
`semantic_diff`.

### `project_info`

Не принимает аргументы. Не запускает compilation и возвращает активную build
конфигурацию: source files, include directories, defines, configured tops,
metadata, Slang version и summary.

## Symbols, diagnostics и hierarchy

### `get_diagnostics`

Аргументы: `limit=100`, необязательный `severity`.

`severity` принимает `ignored`, `note`, `warning`, `error` или `fatal` без учёта
регистра. Результат содержит `diagnostics` и `returned_count`; каждый diagnostic
содержит severity, Slang code, message и source location.

### `find_symbol`

Аргументы: `name`.

Ищет семантические declarations по точному короткому имени. Возвращает `symbols`
и `match_count`. Для дальнейшего запроса предпочтительнее использовать `symbol_id`
или `qualified_name` из ответа.

### `describe_symbol`

Аргументы: `identifier` — stable `symbol_id`, qualified name или однозначное имя.

Возвращает symbol identity, location, kind, type, packed width, direction,
parameters, ports и непосредственных members, когда эти поля применимы.

### `get_hierarchy`

Аргументы: необязательные `root`, `max_depth`.

Возвращает `roots`: элаборированное instance/generate tree. `root` — top instance;
без него возвращаются все tops. `max_depth` должен быть от 0 до 50. Дочерние узлы
содержат path, name, kind, `sv_module` и `children`.

### `describe_instance`

Аргументы: `path`.

Возвращает компактное описание элаборированного instance: path, name, `sv_module`,
location, effective parameters, ports, source-level port connections и direct
children. Для richer connections используйте `inspect_instance`.

## Declarations и instances

### `list_symbols`

Аргументы: `scope`, необязательные `kind`, `limit=100`.

Возвращает direct semantic members scope. `kind` фильтрует по Slang semantic kind,
например `port`, `variable`, `net`, `module` или `interface`.

### `get_ports`

Аргументы: `sv_module`, `limit=100`.

Возвращает default signature module/interface: имя, direction, normalized type,
packed width, unpacked dimensions, default value и сведения об interface/modport.
Это не effective signature конкретного parameterized instance.

### `get_parameters`

Аргументы: `target`, `limit=100`.

Возвращает `target`, `value_kind` и paged `parameters`. Для module declaration
`value_kind` равен `declared_default`. Вложенный instance path автоматически
обрабатывается как запрос effective values; для top instance используйте явный
`get_instance_parameters`.

### `get_instance_parameters`

Аргументы: `instance_path`, `limit=100`.

Возвращает evaluated parameters элаборированного instance с
`value_kind: "effective"`, включая top instances.

### `get_instance_connections`

Аргументы: `instance_path`, `limit=100`.

Возвращает formal port, actual expression text, referenced symbols, source
location, actual type и width. `kind` имеет значения `signal`, `expression`,
`unconnected` или `interface`. Списки symbols и expression text ограничены, а
соответствующие признаки truncation передаются в ответе.

### `list_instances`

Аргументы: необязательные `sv_module`, `name`, `path_prefix`, `limit=100`.

Фильтрует elaborated instances. `name` — точное instance name, `path_prefix` —
начало full hierarchical path. Каждый элемент содержит path, module type,
declaration location и parent instance.

### `find_instance`

Аргументы: `query`.

Возвращает instance для точного path или уникального short instance name. Несколько
совпадений short name возвращают controlled ambiguity error с кандидатами.

## References и source-level access

### `get_references`

Аргументы: `symbol`, необязательные `kind`, `limit=100`.

Возвращает declaration и semantic uses выбранного symbol. Допустимые `kind`:
`read`, `write`, `read_write`, `declaration`, `unknown`, `parameter_reference`,
`port_connection`, `type_reference`, `instantiation`. Reference содержит location,
scope, instance, context assignment/port operation и, когда применимо,
procedural block id.

### `get_signal_reads` и `get_signal_writes`

Аргументы: `signal`, `limit=100`.

Возвращают соответственно source-level reads или writes. `read_write` access входит
в обе категории. Это locations accesses, не число уникальных hardware consumers
или drivers.

### `get_drivers` и `get_loads`

Аргументы: `signal`, `limit=100`.

Псевдонимы source-level writes и reads. Они полезны для быстрых ответов «где
сигнал записывается?» и «где он читается?», но не являются synthesized netlist
driver/load analysis.

### `get_procedural_blocks`

Аргументы: `sv_module`, `limit=100`.

Возвращает elaborated `always`, `always_comb`, `always_ff`, initial и другие
procedural blocks экземпляров указанного module: block id, kind, instance,
location, bounded read/write sets и sensitivity syntax.

### `get_state_elements`

Аргументы: `sv_module`, `limit=100`.

Возвращает signals, записываемые в `always_ff`, вместе с type, width, block id и
location. Tool не выводит reset behavior, latches или synthesis inference для
обычных `always` blocks.

## Connectivity traversal

### `trace_connectivity`

Аргументы: `signal`, `direction="both"`, `max_depth=5`, `limit=100`.

Строит bounded breadth-first routes через:

- direct signal port actuals: input — actual → formal, output — formal → actual,
  inout/ref — в обоих направлениях;
- continuous assignments: RHS signal → LHS signal;
- procedural, declaration и compound assignments как source-level dependencies.

`direction="loads"` идёт к потребителям, `"drivers"` — к источникам, `"both"`
исследует оба направления. `max_depth` должен быть от 0 до 50. Результат содержит
resolved start symbol, paged `paths`, `edges_considered`, requested depth и
`truncated`.

Каждый path содержит ordered `hops`, конечный signal и `stop_reason`: `no_edges`,
`max_depth` или `cycle`. Hop содержит source, target, `kind`, source location,
instance path, optional formal port и assignment operation.

Tool не разворачивает port actual expressions, selects, casts, concatenations,
constants, open ports или interfaces в inter-instance hops. Результат не является
netlist, timing, formal или simulation evidence.

## Aggregate inspection

### `inspect_signal`

Аргументы: `signal`, `limit=10`.

Собирает в одном ответе normalized symbol description, общее число references и
bounded lists reads, writes, drivers и loads. Default limit меньше, чем у других
tools, чтобы ответ оставался компактным.

### `inspect_module`

Аргументы: `sv_module`, `limit=100`.

Возвращает definition, default parameters и ports, количество direct declarations,
children active elaborated instances, procedural blocks и количество diagnostics
того же source file.

### `inspect_instance`

Аргументы: `instance_path`, `limit=100`.

Возвращает instance identity, effective parameters, rich connections и direct
children. Это расширенная альтернатива `describe_instance` для исследовательских
запросов.

## Semantic diff

### `semantic_diff`

Аргументы: `limit=100`.

Сравнивает current normalized snapshot с предыдущей успешной snapshot того же
logical module. Возвращает `status: "no_previous_state"` после первой загрузки или
после смены logical module; после reload возвращает `status: "compared"` и paged
`changes`.

Change содержит `category`, `identity`, `before` и `after`; `null` обозначает
addition/removal. Snapshot включает definitions, default ports/parameters,
effective instance parameters, instances и diagnostics. Он хранится только в
памяти MCP process и теряется при перезапуске сервера.
