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
- Use `get_hierarchy` and `list_instances` to locate elaborated instance paths.
- Use `inspect_module` for declaration defaults and `inspect_instance` for
  effective instance parameters and connections. Select `fields`,
  `parameter_names` and `port_names` to keep responses focused.
- Use `list_instance_facts` to compare instances of one module and
  `get_state_elements` for source-level state. These are not netlist queries.

Check truncation and total counts on bounded collections. For constants,
`value` retains the exact SystemVerilog rendering; `integer_value: null` can mean
an unknown value or a value outside signed 64-bit range.

State the analyzed top, configuration and relevant limitations in your answer.
The release archive includes the full reference at `docs/mcp-reference.md` and
the tool schemas at `src/contract.json`.
