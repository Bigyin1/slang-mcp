# MCP reference

The server exposes one catalog of 14 read-only tools. It does not modify RTL or
run build commands. The agent selects source files, inspects diagnostics, and
adds dependencies as needed.

Use source inspection and MCP together. RTL and headers explain expressions,
conditions, macros, and intent; MCP supplies resolved semantics for the selected
configuration. For macro-heavy code, check `defines`, include paths, source order,
and `single_unit`: a macro present in the repository is not necessarily active.

## Loading and diagnostics

`project_load` requires `source_files` and `top_module`:

```json
{
  "source_files": ["/work/types_pkg.sv", "/work/fifo.sv"],
  "top_module": "fifo",
  "include_directories": ["/work/include"],
  "defines": {"SYNTHESIS": null, "WIDTH": "32"},
  "single_unit": true
}
```

`source_files` is a nonempty ordered list of absolute paths. Include directories
and `defines` are optional; a null define expands to `1` (Slang's default), while
an empty string supplies an empty replacement. The server
reads only the selected sources and their includes; it does not discover missing
modules or packages or automatically expand the analysis scope. Call `project_load`
again for a different file set or after modifying RTL.

`single_unit` is an optional boolean, defaulting to `true`:

- `true`: all source files form one compilation unit in the given order; macros
  and `$unit` declarations are available to later files.
- `false`: each source file forms a separate compilation unit; macros and `$unit`
  declarations do not carry over from neighboring files. Defines and include
  paths apply to each unit. Modules and packages remain visible to the compilation.

Compilation-unit mode is independent of fragment size: even a small fragment may
require single-unit mode. It does not add files or choose dependencies. An invalid
`single_unit` type, including null or the string `"false"`, returns an error without
replacing the active project.

The top is elaborated independently with its default parameters. It does not inherit
parameter overrides from an absent parent. The summary reports `single_unit`, file
and error/warning counts, `analysis_scope: "fragment"`,
`parameter_context: "standalone_top"`, and `completeness: "not_verified"`. Zero
diagnostics do not prove that the production configuration was reproduced.

Syntax and semantic errors are accepted as long as Slang can build the top. If it
cannot, the MCP response has `isError: true` and JSON containing
`status: "compilation_failed"`, up to 100 diagnostics, `attempt_id`,
`total_count`, `truncated`, and `active_project_unchanged: true`. The value
`analysis.context: "attempted_candidate"` distinguishes diagnostics from the failed attempt from
those of the previous active project; this context includes the selected
`single_unit`. Semantic queries use the previous successful load, if any.

`project_info()` returns the active load summary, configured tops, `single_unit`,
metadata and Slang version without recompiling. To verify the supplied configuration,
request `section: "source_files"`, `"include_directories"` or `"defines"`. Each
section returns a page of strings with `items`, `returned_count`, `total_count`,
`truncated` and `next_cursor`. Pass `limit` (default 100, maximum 500) and `cursor`
only with `section`. Files retain their supplied order and duplicates, include
directories retain their search order, and defines appear in name order as
`NAME` (null) or `NAME=value` (including `NAME=` for an empty value). Continue
with the same section until `next_cursor` is null. A successful load expires
the cursor. A failed load preserves the active configuration and its cursors.

`get_diagnostics` accepts `severity`, exact `file` and `code` filters, and
returns `diagnostics`, counts, a continuation cursor, and the analysis context.
Use `summary: true` for paged `items` grouped by code with severity counts.
Use the `attempt_id` from a failed load to inspect its diagnostics even without
an active project. A newer compilation replaces or clears that attempt.
Severities are `ignored`,
`note`, `warning`, `error`, and `fatal`. UnknownModule and UnknownClassOrPackage
receive `scope_hint: "possible_missing_dependency"`; other diagnostics receive
`"unclassified"`. This is a possible cause, not proof that the error is harmless:
a typo can produce the same diagnostic. The original severity is never lowered.

## Search and hierarchy

| Tool | Arguments and semantics |
| --- | --- |
| `find_symbol` | Exact short `name`, optional qualified `scope`. Returns paged `symbols` and exact `match_count`. |
| `describe_symbol` | `identifier`, optional `type_depth=2` (0–8): identity, type, width, location, signature and bounded `type_info` for arrays, structs and unions. |
| `list_symbols` | `scope`, optional `kind` and `limit`: direct declarations without recursive traversal. Scope can be a module name, symbol identifier, or exact nested instance/generate path. A top name identical to a module name selects the module's default parameters. |
| `get_hierarchy` | Optional `root` and `max_depth` (0–50, default 1). Paged `items` contain flat nodes with `path`, `parent`, `kind`, `sv_module`, and `has_children`. |
| `list_instances` | Optional `sv_module`, `name`, `path_prefix`, and `limit`: filter by module type, exact instance name, and path prefix. |

`sv_module` identifies a module/interface declaration; `instance_path` identifies
an elaborated instance, such as `top.u_fifo`. Ambiguous names produce a controlled
error with candidate IDs when available. For a module name used in place of
an instance path, the error can suggest `list_instances`.

### Arrays, structures and unions

Use `describe_symbol` on the base declaration, for example:

```json
{"identifier":"top.request_queue","type_depth":4}
```

`type_info` preserves the declared type name and resolves typedefs and effective
type parameters for its layout. Arrays have ordered `dimensions` and an
`element_type` describing the type after those dimensions. Fixed dimensions
include left/right bounds, range and size; packed and unpacked dimensions remain
distinct. Dynamic, associative and queue dimensions have no runtime
size. Associative dimensions include `index_type` (`*` for wildcard); bounded
queues include their declared `max_size`, not their current length. Packed
dimensions retain their signedness.

Structs and unions expose fields in declaration order, each with a nested
`type_info`. `bit_offset` is the LSB offset within one packed aggregate; packed
union fields can overlap. Unpacked offsets are null, since they are not a packed
layout. `tagged` identifies tagged unions. These descriptions do not enumerate
array elements, read simulation values or describe simulator memory layout.

`width` consistently means the integral packed width after removing outer
unpacked array dimensions, including in `describe_symbol`, ports and connections.
For `logic [7:0] memory[4]`, it is 8; `type_info.total_bits` is 32. Width is null
for nonintegral or unknown element types. `total_bits` is Slang's static `$bits`,
or null when unavailable. The `is_signed` flag describes the node's type itself;
an unpacked array is not signed, even when its packed elements are signed.

`type_depth` counts field/element-type child levels. At zero, identity,
dimensions and `field_count` remain available. A reply contains at most 128 type
nodes and 16 dimensions per array node. `truncated` propagates to the root if any
descendant was omitted; `field_count` includes omitted fields. Increase depth up
to eight for nested types and use source inspection when size limits are reached.
Scope members and module signatures retain their existing pagination behavior.
Detailed type trees are computed by `describe_symbol`; bulk port/connection
queries retain their compact descriptions.

Selectors such as `request_queue[0]` or `request.data` are not independent indexed
symbols. Query the base declaration and inspect its type tree. References and
driver/load queries aggregate accesses to the base signal, without field, element
or bit-range precision. In `entries[index].data = value`, `entries` is written
and `index` is read; a compound assignment also reads `entries`.

## Inspection

`inspect_module(sv_module, ...)` returns `definition`, default `parameters`, and
`ports` by default. Additional `fields` are `declaration_count`, `children`,
`procedures`, and `diagnostic_count`. Children and procedures refer to active
instances of that module; the diagnostic count covers the same source file, not
just the selected declaration.

`inspect_instance(instance_path, ...)` returns `instance`, effective `parameters`,
and `connections` by default. `fields` can also request `children`.

Both tools accept optional `fields`, `parameter_names`, `port_names`, and
`limit=100`. Identity is always returned; `fields: []` leaves only identity.
Unrequested sections are not computed. Name filters select exact names before the
limit, preserve declaration order, and accept up to 500 names. Missing names do
not cause errors; an empty list selects zero items.

Large signatures are truncated when their collection exceeds `limit` (100 by
default, at most 500). Inspect each collection's `truncated` and `total_count`;
an unfiltered reply is not necessarily the complete module signature. For large
modules, explicitly filter `parameter_names` and `port_names`. Names beyond the
first page remain selectable because filtering happens before truncation.

```json
{"instance_path":"top.u_fifo","fields":["parameters"],"parameter_names":["DEPTH"]}
```

Parameters retain their exact SystemVerilog representation in `value`. The
`integer_value` convenience field is null for type parameters, X/Z, and constants
outside signed 64-bit range. Module parameters have `value_kind: "declared_default"`;
instance parameters have `"effective"`. `is_overridden` indicates that Slang
applied an override, including for type parameters and overrides equal to defaults.

Connections contain the formal port, actual expression, resolved base symbols,
actual type/width, and location. `expression` shows the actual, while `symbols`
lists its referenced declarations. For example, `bus[i]` may reference both
`bus` and `i`, and `{a,b}` may reference both `a` and `b`. Their `kind` is `signal`, `expression`,
`unconnected`, or `interface`. For example, expression `request.address` and
base symbol `request` describe different aspects of a connection. Expression text
and symbol lists are bounded; truncation indicators are included in the response.

`list_instance_facts(sv_module, fields?, parameter_names?, port_names?, limit=100,
fact_limit=100)` returns parameters and connections for multiple instances of
one module type in a single call. `limit` bounds instances and `fact_limit` bounds
each nested collection. Use `fields: ["parameters"]` or `["connections"]`
to compute only that section. Omit `fields` for both, or pass `[]` for identities.

## References and state

`get_references(symbol, kind?, limit=100, cursor?)` returns the symbol's declaration and
semantic uses with location, scope, instance, context, and procedural block ID
when available. Kinds: `read`, `write`, `read_write`, `declaration`, `unknown`,
`parameter_reference`, `port_connection`, `type_reference`, `instantiation`.
Both `read` and `write` filters include `read_write` (for example, `count += 1`).
The filter `kind: "read_write"` returns their union: ordinary reads, ordinary
writes and read-modify-write accesses, with each recorded site included once.
Declarations and unknown accesses are excluded. The `kind` of an individual
returned item still describes that site's precise access: `read_write` on an
item means a read-modify-write operation, such as `+=`, `++` or an inout argument.
The `symbol` argument accepts a stable `symbol_id` or the complete elaborated
`qualified_name` returned by `find_symbol`. For example:

```json
{"symbol":"cpu.bank_sel_ff","kind":"read"}
```

Here `cpu` must be the loaded top or the complete instance path. If the `cpu`
module is instantiated as `soc.u_cpu`, use `soc.u_cpu.bank_sel_ff`; module type
names do not identify an elaborated instance. Package members use `pkg::member`.

`type_reference` is not currently indexed. Port-binding access records cover
ordinary ports; these records do not establish complete interface connectivity.
An empty result is not proof that the symbol has no uses.

These are source accesses, not counts of hardware consumers or drivers. Accesses
inside procedural branches may appear even when parameters make a branch inactive;
the response does not prove branch reachability. Check conditions and right-hand
sides in RTL using the effective parameters.

`get_state_elements(sv_module, limit=100)` returns signals written in `always_ff`,
with type, width, block ID, and location. It does not infer reset behavior, latches,
or synthesis behavior for ordinary `always` blocks.

## Macro expansion

`expand_macro(file, line, column, max_bytes=8192)` returns the recorded expansion
of one user/configured macro invocation in the active compilation. Use the absolute
path of a loaded source or included file, a 1-based physical line, and a 1-based
UTF-8 byte column on the invocation's backtick/name. Tabs count as one byte;
coordinates ignore SystemVerilog `line remapping. Point at the invocation rather
than its definition or arguments.

```json
{"file":"/work/wrapper.sv","line":42,"column":3,"max_bytes":8192}
```

The result contains `name`, physical `invocation` and `definition` locations,
`expanded_text`, `total_bytes` and `truncated`. The text renders emitted syntax
tokens, with nested calls, actual arguments, stringification and pasted identifiers
already handled by Slang. This covers macros that generate complete modules,
instances or signals. Whitespace/comments are retained where available; this is
token rendering, not byte-for-byte original source or a promise of valid standalone RTL.
For a macro used as an include filename, the result is the expanded filename token,
not the contents of the included file. Macros that themselves generate preprocessing
directives are currently rejected explicitly.

The query uses the loaded snapshot without recompiling or rereading source contents.
Includes, configured defines, source order, redefinitions and `single_unit` are
therefore those of the active project. Reload after edits; after a failed load,
queries still refer to the previous successful project. Partial designs with
missing child modules can still expose recorded expansions. Inspect diagnostics
when syntax/semantic errors are present. Preprocessing errors at the selected
invocation produce an error rather than a misleading empty successful expansion.

Only recorded user/configured invocations are selectable. Inactive branches,
undefined macros, direct intrinsic built-ins and `undef` directives are not expanded
on demand; load the appropriate configuration to inspect an inactive branch.
Repeated inclusions of the same file/position are rejected as ambiguous instead
of selecting an arbitrary preprocessing context. An intentionally empty macro
returns empty text with zero bytes and no truncation.

`max_bytes` ranges from 1 to 65,536 and bounds the UTF-8 output prefix without
splitting a code point. `total_bytes` counts the entire rendered expansion;
increase the bound if `truncated` is true. This limits output, not the cost of
visiting the retained syntax tree.

## Analysis limits

Paged semantic collections contain `items`, `total_count`, and `truncated`;
limits range from 1 to 500. Diagnostics instead use `diagnostics` and
`returned_count`, with the same count/truncation distinction. For
`find_symbol`, `get_hierarchy`, `get_references`, and `get_diagnostics`, pass `next_cursor` as
`cursor` with the same filters to continue. A null cursor marks the last page.
An active-project cursor expires when another project loads successfully.
The 1 MiB reply size cap can shorten a page.
Missing dependencies can leave types, widths, and hierarchy incomplete.
A successful local query does not establish correctness of the rest of the RTL.

The server uses Slang's AST and a shared lazy source-access index, not a regex
parser. Default elaboration uses the original syntax trees with the same
compilation-unit boundaries. Responses do not prove netlist connectivity, timing,
simulation, or formal equivalence.

The server does not provide connectivity tracing or semantic diff. Repeated
loading replaces reload; the server does not build structural snapshots.
