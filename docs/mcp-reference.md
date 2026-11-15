# MCP reference

The server exposes one catalog of 13 read-only tools. It does not modify RTL or
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
and `defines` are optional; a null define has no replacement text. The server
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
`status: "compilation_failed"`, the first 100 diagnostics, `total_count`,
`truncated`, and `active_project_unchanged: true`. The value
`analysis.context: "attempted_candidate"` distinguishes diagnostics from the failed attempt from
those of the previous active project; this context includes the selected
`single_unit`. Subsequent queries refer to the previous successful load, if any.

`project_info()` returns active sources, includes, defines, tops, `single_unit`,
metadata, Slang version, and a summary without recompiling.

`get_diagnostics(severity?, limit=100)` returns diagnostics, `returned_count`,
`total_count`, `truncated`, and the analysis context. Severities are `ignored`,
`note`, `warning`, `error`, and `fatal`. UnknownModule and UnknownClassOrPackage
receive `scope_hint: "possible_missing_dependency"`; other diagnostics receive
`"unclassified"`. This is a possible cause, not proof that the error is harmless:
a typo can produce the same diagnostic. The original severity is never lowered.

## Search and hierarchy

| Tool | Arguments and semantics |
| --- | --- |
| `find_symbol` | `name`: exact short name; returns all matches and `match_count`. |
| `describe_symbol` | `identifier`: full or unambiguous short name; returns kind, type, width, location, and available symbol details. |
| `list_symbols` | `scope`, optional `kind` and `limit`: direct declarations without recursive traversal. Scope can be a module name, symbol identifier, or exact nested instance/generate path. A top name identical to a module name selects the module's default parameters. |
| `get_hierarchy` | Optional `root` and `max_depth` (0–50): elaborated instances and active generate blocks. Without depth, returns the entire selected subtree. |
| `list_instances` | Optional `sv_module`, `name`, `path_prefix`, and `limit`: filter by module type, exact instance name, and path prefix. |

`sv_module` identifies a module/interface declaration; `instance_path` identifies
an elaborated instance, such as `top.u_fifo`. Ambiguous names produce a controlled
error; prefer full paths.

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

```json
{"instance_path":"top.u_fifo","fields":["parameters"],"parameter_names":["DEPTH"]}
```

Parameters retain their exact SystemVerilog representation in `value`. The
`integer_value` convenience field is null for type parameters, X/Z, and constants
outside signed 64-bit range. Module parameters have `value_kind: "declared_default"`;
instance parameters have `"effective"`.

Connections contain the formal port, actual expression, resolved base symbols,
actual type/width, and location. Their `kind` is `signal`, `expression`,
`unconnected`, or `interface`. For example, expression `request.address` and
base symbol `request` describe different aspects of a connection. Expression text
and symbol lists are bounded; truncation indicators are included in the response.

`list_instance_facts(sv_module, parameter_names?, port_names?, limit=100,
fact_limit=100)` returns parameters and connections for multiple instances of
one module type in a single call. `limit` bounds instances and `fact_limit` bounds
each nested collection. This reduces repeated requests for individual paths.

## References and state

`get_references(symbol, kind?, limit=100)` returns the symbol's declaration and
semantic uses with location, scope, instance, context, and procedural block ID
when available. Kinds: `read`, `write`, `read_write`, `declaration`, `unknown`,
`parameter_reference`, `port_connection`, `type_reference`, `instantiation`.
Both `read` and `write` filters include `read_write` (for example, `count += 1`).
These are source accesses, not counts of hardware consumers or drivers. Accesses
inside procedural branches may appear even when parameters make a branch inactive;
the response does not prove branch reachability. Check conditions and right-hand
sides in RTL using the effective parameters.

`get_state_elements(sv_module, limit=100)` returns signals written in `always_ff`,
with type, width, block ID, and location. It does not infer reset behavior, latches,
or synthesis behavior for ordinary `always` blocks.

## Analysis limits

Collections contain `items`, `total_count`, and `truncated`; limits range from
1 to 500. Missing dependencies can leave types, widths, and hierarchy incomplete.
A successful local query does not establish correctness of the rest of the RTL.

The server uses Slang's AST and a shared lazy source-access index, not a regex
parser. Default elaboration uses the original syntax trees with the same
compilation-unit boundaries. Responses do not prove netlist connectivity, timing,
simulation, or formal equivalence.

The server does not provide connectivity tracing or semantic diff. Repeated
loading replaces reload; the server does not build structural snapshots.
