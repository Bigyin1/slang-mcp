# Справочник MCP tools

`slang-mcp` — read-only MCP-сервер для семантического анализа SystemVerilog.
Все tools возвращают JSON-совместимые данные и не меняют RTL, build-конфигурацию
или файлы проекта.

По умолчанию сервер запускается с профилем `core` из 15 tools. Начните с
`project_load_partial`: агент выбирает ordered `source_files` и `top_module`,
проверяет диагностику и явно добавляет нужные зависимости. Повторная загрузка
заменяет активный фрагмент; ошибка построения сохраняет прежнее состояние.

Для старых клиентов и дополнительных инструментов запускайте
`slang-mcp --tool-profile full`. Он предоставляет все 30 tools, включая
`project_load`, `project_reload`, `semantic_diff`, connectivity и старые getters.
Скрытые инструменты недоступны и для прямого вызова. Профиль выбирается при старте.

В `core` доступны: `project_load_partial`, `project_info`, `get_diagnostics`,
`find_symbol`, `describe_symbol`, `list_symbols`, `get_references`, `get_hierarchy`,
`list_instances`, `inspect_module`, `inspect_instance`, `list_instance_facts`,
`get_signal_reads`, `get_signal_writes`, `get_state_elements`.
Все остальные описанные ниже инструменты относятся только к `full`.

Сервер реализован на C++26 и напрямую использует библиотеку Slang 12.1.
Полные file lists доступны через `project_load` в профиле `full`. Python остаётся только
в отдельном стенде `benchmarks/`, который вызывает C++ сервер через MCP.

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

Синтаксические и семантические ошибки допустимы, пока Slang смог создать
запрошенный top. Доступность одного локального запроса не означает корректность
остального RTL. Если top построить нельзя, MCP возвращает `isError: true` и JSON
со `status: "compilation_failed"`, диагностикой попытки (первые 100 сообщений,
`returned_count`, `total_count`, `truncated`), `requested_top_modules` и
`active_project_unchanged: true`. Поле `analysis.context: "attempted_candidate"`
отделяет эту диагностику от активного проекта; там же указаны область анализа и
число файлов. Новая compilation не активируется: последующие запросы относятся
к предыдущей успешной загрузке, если она была. Это относится и к `project_load_partial`.

### `project_reload`

Не принимает аргументы. Пересобирает активные build inputs и возвращает ту же
сводку, что `project_load`. Предыдущая успешная semantic snapshot сохраняется для
`semantic_diff`.

### `project_info`

Не принимает аргументы. Не запускает compilation и возвращает активную build
конфигурацию: source files, include directories, defines, configured tops,
metadata, Slang version и summary.

### `project_load_partial`: явный частичный анализ

Для анализа отдельного фрагмента передайте исходники непосредственно, без файловых списков:

```json
{
  "source_files": ["/work/rtl/types_pkg.sv", "/work/rtl/fifo.sv"],
  "top_module": "fifo",
  "include_directories": ["/work/include"],
  "defines": {"SYNTHESIS": null}
}
```

`source_files` — непустой упорядоченный список абсолютных путей. `include_directories`
и `defines` необязательны. Компилируются только переданные source files и подключённые
ими includes. Сервер не ищет отсутствующие modules/packages и не расширяет набор до
всего проекта. Для добавления зависимости агент повторяет вызов с расширенным списком.

Выбранный top элаборируется как самостоятельный модуль с параметрами по умолчанию.
Он не наследует переопределения параметров из отсутствующего родителя.
Отсутствующие определения остаются диагностическими ошибками; доступные локальные
факты можно запрашивать через обычные инструменты. Неразрешённые типы, ширины и
отсутствующие ветви иерархии требуют проверки диагностик.

Сводка загрузки и reload содержит `analysis_scope: "fragment"`,
`parameter_context: "standalone_top"`, `completeness: "not_verified"`.
`project_info.metadata` дополнительно содержит
`dependency_resolution: "provided_files_only"`. Нулевая диагностика не доказывает,
что фрагмент соответствует производственной конфигурации. Эти признаки описывают
активную сессию; отдельные semantic-ответы пока не содержат оценки достоверности
каждого поля. `project_reload` сохраняет выбранный набор файлов и режим фрагмента.
Неудачная загрузка или reload сохраняет предыдущую модель.

## Семантический индекс

После построения Slang compilation `project_load` формирует один
семантический индекс внутри C++ адаптера `Design` для активного проекта. При `project_reload` создаются новая
compilation и новый index; прежний index не используется для последующих
semantic-запросов. Построение index — часть времени загрузки проекта, поэтому не
вызывайте reload, если RTL и build inputs не менялись.

Index обходит элаборированное дерево tops и generate blocks и сохраняет
нормализованные project-owned данные, без выдачи объектов Slang наружу:

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
регистра. Результат содержит `diagnostics`, `returned_count`, `total_count`,
`truncated` и `analysis` с областью анализа, tops, количеством файлов и
`completeness: "not_verified"`. Счётчик `total_count` учитывает фильтр severity,
но не ограничение limit. Каждый diagnostic сохраняет severity, Slang code,
message и source location.

`scope_hint: "possible_missing_dependency"` ставится только для `UnknownModule`
и `UnknownClassOrPackage`. Это подсказка: причиной может быть ограниченный набор
файлов, опечатка или реальный дефект RTL. Для остальных кодов — `"unclassified"`.
Ошибки не подавляются, их severity не понижается. Проверяйте гипотезу добавлением
нужной зависимости и повторной загрузкой. Отсутствие errors не доказывает
полноту проекта, корректность поведения или применимость неизвестных параметров
родительского экземпляра.

### `summarize_diagnostics_by_code`

Аргументы: необязательные `severity`, `limit=100`.

Группирует diagnostics текущей compilation по Slang code. Каждая запись содержит
`code`, общее `count`, `severity_counts`, один `example_message` и
`first_location`. Используйте этот tool перед `get_diagnostics`, когда нужно
понять распределение большого числа сообщений; для всех отдельных locations и
messages вызывайте `get_diagnostics`.

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

Возвращает `roots`: элаборированное instance/generate tree. `root` может быть точным
path любого элаборированного instance или generate-блока; для top также поддерживается
короткое имя. Без `root` возвращаются все tops. `max_depth` должен быть от 0 до 50.
Дочерние узлы содержат path, name, kind, `sv_module` и `children`.

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
целую константу, представимую как signed 64-bit integer. Для type parameters,
более широких констант и значений с X/Z `integer_value` равен
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

Все три `inspect_*` принимают необязательный `fields` — массив имён разделов ответа.
Без него возвращается прежний полный ответ. `fields: []` возвращает только identity:
`definition`, `instance` или `symbol`; identity включается всегда и не указывается
в `fields`. Неизвестный раздел или неверный тип поля дают ошибку. Разделы, которые
не запрошены, не вычисляются. Это позволяет не строить индекс accesses, когда нужны
только параметры или порты. Фильтры непросматриваемых разделов не применяются.

### `inspect_signal`

Аргументы: `signal`, `limit=10`, `fields`.

Разделы: `reference_count`, `reads`, `writes`, `drivers`, `loads`.
`drivers`/`loads` дублируют writes/reads; для компактного ответа выбирайте одну пару.

Собирает в одном ответе normalized symbol description, общее число references и
bounded lists reads, writes, drivers и loads. Default limit меньше, чем у других
tools, чтобы ответ оставался компактным.

### `inspect_module`

Аргументы: `sv_module`, `limit=100`, `fields`, `parameter_names`, `port_names`.

Разделы: `parameters`, `ports`, `declaration_count`, `children`, `procedures`,
`diagnostic_count`. Фильтры выбирают точные имена default parameters/ports перед
ограничением `limit`. Пустой список имён означает пустой результат; отсутствующие
имена не являются ошибкой. Каждый фильтр допускает до 500 имён.

Возвращает definition, default parameters и ports, количество direct declarations,
children active elaborated instances, procedural blocks и количество diagnostics
того же source file.

### `inspect_instance`

Аргументы: `instance_path`, `limit=100`, `fields`, `parameter_names`, `port_names`.

Разделы: `parameters`, `connections`, `children`. Именованные фильтры выбирают
effective parameters и formal ports перед `limit`, аналогично `inspect_module`.

Например, вместо отдельного getter параметров:

```json
{"instance_path":"top.u_fifo","fields":["parameters"],"parameter_names":["DEPTH"]}
```

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

Доступен только в `full`; в `core` снимки вообще не строятся. Diff не сравнивает
выражения и тела процедур: изменение арифметики может дать нулевой результат.
Это не проверка эквивалентности поведения. Сопоставление определяется именем
logical module, поэтому при изменении набора файлов или области анализа нужно
самостоятельно учитывать сопоставимость состояний.
