# Using slang-mcp as an agent

Use this read-only MCP server together with the RTL source. Source inspection
explains expressions, macros and intent; Slang supplies resolved semantics for
the configuration you loaded. The server does not edit RTL, discover dependencies
or execute build commands.

## Start with a small fragment

Choose the relevant module as `top_module` and an ordered list of absolute
`source_files`. Include packages before their users. Supply the project's actual
include directories and defines; inspect file lists or build configuration when
available. Avoid loading an entire design when a fragment answers the question.

```json
{
  "source_files": ["/work/types_pkg.sv", "/work/fifo.sv"],
  "top_module": "fifo",
  "include_directories": ["/work/include"],
  "defines": {"SYNTHESIS": null},
  "single_unit": true
}
```

Call `project_load` with these arguments. `single_unit` defaults to `true`: files
share macros and compilation-unit declarations in source order. Use `false` only
when the design requires separate compilation units. Inspect macro definitions
and headers in the source when interpreting macro-heavy RTL.

## Inspect diagnostics before drawing conclusions

Call `get_diagnostics` and add dependencies explicitly when needed, then reload.
Missing definitions can be expected at a fragment boundary, but a
`possible_missing_dependency` hint is not proof that an error is harmless.
Report unresolved dependencies and syntax/type errors that affect your answer.

A failed load preserves the previous active design. A response with
`status: "compilation_failed"` describes the attempted candidate; subsequent
queries still address the previous successful load. Use `project_info` to check
the active files and configuration. Reload after editing any source.

The fragment top uses its default parameters. It does not inherit overrides
from an absent parent. Zero diagnostics do not prove that the production build
configuration was reproduced or that the fragment is complete.

## Query only what the task needs

- Use `find_symbol`, `list_symbols` and `describe_symbol` to locate declarations;
  use `get_references` for source-level references and read/write accesses.
  Pass the result's stable `symbol_id` or full elaborated `qualified_name` as
  `symbol`. Do not substitute a module type name for an instance path.
  Use `kind: "read_write"` to retrieve all reads and writes together; each result
  retains its precise access kind. This filter excludes declarations and unknowns.
- Use `get_hierarchy` and `list_instances` to locate elaborated instance paths.
- Use `inspect_module` for declaration defaults and `inspect_instance` for
  effective instance parameters and connections. Select `fields`,
  `parameter_names` and `port_names` to keep responses focused.
- Use `list_instance_facts` to compare instances of one module and
  `get_state_elements` for source-level state. These are not netlist queries.

Each inspection collection defaults to at most 100 items (maximum `limit: 500`).
For large modules, explicitly select the needed `parameter_names` and `port_names`;
filters apply before the limit. An unfiltered signature can omit later parameters
and ports. Check `truncated` and `total_count` in every returned collection before
treating it as complete. For constants,
`value` retains the exact SystemVerilog rendering; `integer_value: null` can mean
an unknown value or a value outside signed 64-bit range.

State the analyzed top, configuration and relevant limitations in your answer.
The release archive includes the full reference in `mcp-reference.md`. The MCP
tool catalog supplies current argument schemas; the source repository also keeps
them in `src/contract.json`.
