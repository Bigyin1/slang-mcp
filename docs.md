# Справочник MCP tools

`slang-mcp` — read-only MCP-сервер для семантического анализа SystemVerilog.
Все tools возвращают JSON-совместимые данные и не меняют RTL, build-конфигурацию
или файлы проекта.

Сначала вызовите `project_load`, затем выполняйте запросы к активному проекту.
`project_reload` заново компилирует те же build inputs.

## Общие правила

- `top_module` — единственный SystemVerilog module, который Slang использует
  как top для элаборации.
- `sv_module` — имя объявления `module` или `interface`.
- `instance_path` — элаборированный путь, например `top.u_fifo`.
- `signal` принимает полное имя сигнала; короткое имя допускается только если оно
  однозначно.
- `limit` по умолчанию равен 100 и должен быть от 1 до 500, если конкретный tool
  не указывает другое значение.
- Постраничный ответ имеет вид
  `{"items": [...], "total_count": N, "truncated": false}`. `truncated: true`
  означает, что по указанному limit возвращена только часть результата.
- Контролируемые ошибки MCP включают отсутствие активного проекта, отсутствующий
  file list, отсутствующий или неоднозначный symbol/instance и неверные
  границы параметров.

## Жизненный цикл проекта

### `project_load`

```json
{
  "source_file_lists": ["/work/filelists/packages.f", "/work/filelists/rtl.f"],
  "include_directory_lists": ["/work/filelists/includes.f"],
  "defines": {"SYNTHESIS": null},
  "top_module": "top"
}
```

Читает переданные file lists и создаёт Slang compilation. В `source_file_lists`
сначала передавайте lists packages, затем RTL и models. Каждая непустая строка
list-файла должна быть абсолютным путём: в `source_file_lists` — к source file,
в `include_directory_lists` — к каталогу. Порядок source paths и дубликаты
сохраняются. Возвращает количества source files, include dirs и
defines, configured top и количество error/warning diagnostics. Успешная
компиляция с diagnostics всё равно доступна для анализа.

### `project_reload`

Не принимает аргументы. Пересобирает активные build inputs и возвращает ту же
сводку, что `project_load`. Предыдущая успешная semantic snapshot сохраняется для
`semantic_diff`.

### `project_info`

Не принимает аргументы. Не запускает compilation и возвращает активную build
конфигурацию: source files, include directories, defines, configured tops,
metadata, Slang version и summary.

## `ElaboratedRtlIndex`

После построения Slang compilation `project_load` формирует один
`ElaboratedRtlIndex` для активного проекта. При `project_reload` создаются новая
compilation и новый index; прежний index не используется для последующих
semantic-запросов. Построение index — часть времени загрузки проекта, поэтому не
вызывайте reload, если RTL и build inputs не менялись.

Index обходит элаборированное дерево tops и generate blocks и сохраняет
нормализованные project-owned данные, без выдачи объектов `pyslang` наружу:

- все elaborated instances с path, module type, location и parent;
- effective parameters и resolved formal-to-actual port connections, получаемые
  по конкретному instance;
- source-level reads, writes, declarations и port-connection references, с
  обратным индексом по resolved signal;
- направленные source-level connectivity edges для прямых port bindings,
  continuous assignments и procedural assignments.

Эти данные используют `list_instances`, `find_instance`,
`get_instance_parameters`, `get_instance_connections`, `list_instance_facts`,
`get_references`, signal read/write/driver/load tools, inspections и
`trace_connectivity`. Результаты остаются semantic source-level facts: index не
создаёт netlist, не разворачивает expression actual в межинстансный port hop и не
доказывает timing, simulation, formal, synthesis, CDC или фактическую
электрическую connectivity.

Default signature декларации module/interface не является частью обхода всех
elaborated instances. Когда tool запрашивает default ports или declared
parameters, index при необходимости создаёт и кэширует отдельный минимальный
default instance для этой декларации.

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

Аргументы: `instance_path`, `limit=100`, необязательный `names`.

Возвращает evaluated parameters элаборированного instance с
`value_kind: "effective"`, включая top instances. `names` выбирает параметры по
точному имени; элементы сохраняют declaration order, а отсутствующие имена не
создают ошибку. Используйте его, когда нужен один effective parameter, чтобы не
передавать агенту все типовые и конфигурационные параметры instance.

У non-type parameters поле `value` сохраняет SystemVerilog-представление, а
`integer_value` содержит JSON integer, только если Slang вычислил известную
целую константу. Для type parameters и значений с X/Z `integer_value` равен
`null`.

### `get_instance_connections`

Аргументы: `instance_path`, `limit=100`, необязательный `ports`.

Возвращает formal port, actual expression text, referenced symbols, source
location, actual type и width. `kind` имеет значения `signal`, `expression`,
`unconnected` или `interface`. Списки symbols и expression text ограничены, а
соответствующие признаки truncation передаются в ответе.

`ports` выбирает formal ports по точному имени и сохраняет порядок declaration;
отсутствующие имена не создают ошибку. `expression` — полный direct actual,
например `request.address`; `symbols` — разрешённые базовые symbols, например
`request`. Указывайте в вопросе, какое из этих представлений требуется.

### `list_instance_facts`

Аргументы: `sv_module`, необязательные `parameter_names`, `port_names`,
`limit=100`, `fact_limit=100`.

Возвращает page elaborated instances заданного module type. В каждой записи есть
`instance`, page effective `parameters` и page resolved `connections`.
`parameter_names` и `port_names` выбирают точные имена в declaration order.
`limit` ограничивает число instances, `fact_limit` — каждую вложенную коллекцию;
оба значения должны быть от 1 до 500. Это предпочтительный запрос для inventory
нескольких однотипных instances: он не требует сначала перечислять пути, а затем
вызывать `get_instance_parameters` для каждого из них.

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
