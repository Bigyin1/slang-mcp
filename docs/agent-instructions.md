# Using slang-mcp as an agent

Use the connected MCP server together with the RTL source. Source inspection
explains expressions, macros and intent; Slang supplies semantic facts for the
configuration you loaded. Read the tool catalog for current arguments and limits.
The server is read-only: it does not edit RTL, discover missing dependencies or
execute build commands. The executable runs over stdio with no arguments.

## Load a focused fragment

Choose the relevant module as `top_module` and an ordered list of absolute
`source_files`. Include packages before their users. Obtain include directories,
defines and source order from the design's real build configuration when possible.
Start with the smallest fragment that can answer the question; add dependencies
only as needed. The server will not expand the file set automatically.

Call `project_load`, for example:

```json
{
  "source_files": ["/work/types_pkg.sv", "/work/fifo.sv"],
  "top_module": "fifo",
  "include_directories": ["/work/include"],
  "defines": {"SYNTHESIS": null},
  "single_unit": true
}
```

`single_unit` defaults to `true`: files share macros and compilation-unit
declarations in source order. Set `false` when the design requires a separate
compilation unit per file. Configured defines and includes apply to every unit.
A null define expands to `1`; an empty string gives an empty replacement.
Inspect headers and active macro definitions when interpreting macro-heavy RTL.

The selected top uses its default parameters. It does not inherit overrides from
an absent parent. Query an elaborated instance inside a loaded parent when its
effective parameter values matter. Reload after changing RTL or configuration.

## Analyze incomplete fragments

You may intentionally load a fragment without all its dependencies: for example,
one module file with some child module definitions absent. A complete dependency
closure is not required before trying `project_load`. If Slang can elaborate the
selected top, the server retains that partial compilation despite diagnostics;
local declarations, parameters, ports, available hierarchy and source accesses
can still be inspected. Unresolved portions may have unavailable or unreliable
types, widths and connections.

Do not expand to the full design merely because dependencies are missing. Add
only files needed for the current question, then reload and check diagnostics.
Treat boundary-related errors as limitations of the selected fragment, not as
proof of RTL defects or permission to ignore errors. A missing-dependency hint
can also indicate a typo. Some missing packages or syntax errors prevent top
elaboration entirely; then the failed-load rules below apply and the attempted
fragment does not become the active design.

## Check diagnostics and the active configuration

After a successful load, use `get_diagnostics` before trusting unresolved types,
widths or hierarchy. Missing definitions can be expected at fragment boundaries,
but a `possible_missing_dependency` hint does not establish that an error is
harmless. Report unresolved dependencies and syntax/type errors affecting the answer.
Zero diagnostics do not prove completeness or reproduce a production configuration.

A failed load preserves the previous active design. A reply with
`status: "compilation_failed"` contains diagnostics for the attempted candidate.
Subsequent queries, including `get_diagnostics`, still address the previous
successful load. Use `project_info` to verify active files and options; if no load
has succeeded, there is no active design to query.

## Choose the query that answers the question

- `find_symbol` searches exact short declaration names and returns all matches.
  Select the correct instance when names repeat. Use current `symbol_id` or full
  elaborated `qualified_name` for `get_references` and `describe_symbol`.
- `list_symbols` lists direct members of a known scope with a bounded reply.
  Module names select default members; nested instance/generate paths select
  effective scopes. A default-context member is not an active-instance reference.
- For arrays, structs and unions, call `describe_symbol` on the base declaration.
  Its `type_info` gives dimensions, element types, ordered fields and packed field
  offsets. `width` is packed element width; `total_bits` is the static total size
  when known. Start with default `type_depth=2`; increase up to 8 if `truncated`
  indicates omitted nested types. There are also fixed node/dimension budgets;
  inspect RTL if these are reached. Dynamic array contents and runtime sizes are
  unavailable. Field/element expressions are not independently resolved, and
  references aggregate to the base signal. Unpacked offsets are not packed layouts.
- `get_hierarchy` and `list_instances` locate elaborated instances. Start hierarchy
  requests with a root and small `max_depth`; omitting depth returns the full
  subtree without an item limit. Instance filters are combined with AND;
  `path_prefix` is a literal string prefix, not a hierarchy-boundary match.
- `inspect_module` returns standalone declaration defaults. `inspect_instance`
  returns effective instance parameters and resolved port connections. Prefer
  these focused tools for signatures; `describe_symbol` lists are unbounded and
  its module signature details may come from a representative active instance.
- `list_instance_facts` compares instances of one module type. `limit` bounds
  instances; `fact_limit` separately bounds their parameter and connection lists.
- `get_state_elements` reports signal/block writes in `always_ff` across active
  instances of a module type. It does not infer resets, latches, physical storage
  or state from ordinary `always`/`initial` processes.

Use `fields` to compute only needed inspection sections. For large signatures,
explicitly filter `parameter_names` and `port_names`; filters apply before limits.
Inspection collections default to 100 items and accept `limit` from 1 to 500.
Always inspect `total_count` and `truncated` in each nested collection before
using it as a complete inventory. There is no offset pagination: narrow names or
instance filters when results are too large. Missing requested names are ignored;
verify the returned names rather than assuming every requested item exists.

For constants, `value` retains exact SystemVerilog rendering. `integer_value: null`
can indicate a type parameter, X/Z, or a value outside signed 64-bit range.

## Read and write accesses

Pass a full elaborated path as `symbol`, for example `cpu.bank_sel_ff` when `cpu`
is the loaded top. Inside `soc.u_cpu`, use `soc.u_cpu.bank_sel_ff`; a module type
name is not a substitute for an instance path. Package members use `pkg::member`.
These identifiers address symbols, not arbitrary field/select expressions.

`get_references` with `kind: "read_write"` retrieves all recorded reads and writes
together, excluding declarations and unknowns. Each result retains its precise
kind: `read_write` on an item means a combined access such as `+=`, `++` or an
inout/ref argument. The `read` and `write` filters each include combined accesses.
Omit `kind` to inspect all recorded categories, including unknown accesses.

References are source-level accesses, not hardware fan-in/fan-out. System calls
can have unknown effects, procedural branches can contribute even when their
conditions are inactive, and type references are not currently indexed. Empty
results do not prove absence of uses. Inspect source conditions, expressions and
port bindings alongside the effective configuration. The server does not expose
connectivity tracing or semantic diff.

## Inspect a concrete macro invocation

When a wrapper creates modules, instances or signals through macros, use
`expand_macro` on the actual call: absolute `file`, 1-based physical `line` and
1-based UTF-8 byte `column` on the backtick/name. It returns expanded token text
and the active definition location, including nested expansions and pasted names.
Use the declaration/hierarchy tools to inspect the resulting semantic objects.
The query uses the loaded snapshot; reload after changes. Missing child modules
do not necessarily prevent macro inspection, but preprocessing errors at the call
do. Inactive calls and direct built-ins are not expanded on demand. Repeated include
contexts can be ambiguous. Macro-generated preprocessing directives are unsupported
and return an error. Check `truncated`; `max_bytes` defaults to 8192 and can
be raised to 65536. Read the original source and diagnostics alongside the result.

State the analyzed top, configuration, relevant diagnostics and limitations when
presenting conclusions. Distinguish established local facts from assumptions about
missing parents, dependencies or production behavior.
