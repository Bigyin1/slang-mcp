# Using the server

## Loading projects

Start with `project_load`: the agent chooses ordered absolute source paths
and a top, inspects diagnostics, then adds dependencies only as needed. The server
does not discover dependencies or load an entire repository automatically.

```json
{
  "source_files": ["/work/pkg.sv", "/work/fifo.sv"],
  "include_directories": ["/work/include"],
  "top_module": "fifo"
}
```

Repeat this load to change the file set or rebuild after source changes. Missing
definitions remain diagnostics; a usable fragment does not establish completeness
or the parameter overrides of a caller that was not loaded.

`single_unit` defaults to `true`: the ordered files share preprocessing macros and
compilation-unit declarations. Set it to `false` for a separate compilation unit
per source file. Defines and include directories apply to every unit; modules and
packages remain visible across units. This option is independent of fragment size.

The server holds one active project. Path validation and compilation finish before
activating a new design; a failed load preserves the previous design. Completed
compilations with error diagnostics remain available for inspection.

`get_diagnostics` reports scope, total count and truncation. Unresolved modules and
packages receive a possible-missing-dependency hint; their errors remain errors,
since a typo can produce the same message. Recoverable syntax/type errors also stay
visible. If no requested top can be built, the failed-load reply retains bounded
candidate diagnostics and explicitly reports that the active project is unchanged.

## Tools

Public catalog:

| Area | Tools |
| --- | --- |
| Project and diagnostics | `project_load`, `project_info`, `get_diagnostics` |
| Symbols | `find_symbol`, `describe_symbol`, `list_symbols`, `get_references` |
| Hierarchy | `get_hierarchy`, `list_instances` |
| Inspection | `inspect_module`, `inspect_instance`, `list_instance_facts` |
| State | `get_state_elements` |

Use `inspect_module` for declaration defaults and `inspect_instance` for effective
instance values. Select sections and exact parameter/port names to bound replies:

```json
{
  "instance_path": "top.u_fifo",
  "fields": ["parameters", "connections"],
  "parameter_names": ["DEPTH"],
  "port_names": ["data_o"]
}
```

Unrequested sections are not evaluated. Identity is always returned. Defaults are
parameters + ports for modules and parameters + connections for instances; use
`fields` for additional sections. Use `list_instance_facts` for several instances
of one module. `get_references` with `kind: "read"` or `"write"` includes read-write
accesses and replaces separate access getters.

The public API has one explicit-file loader and does not provide connectivity
traversal or semantic diff.

See [MCP reference](mcp-reference.md) for arguments and result semantics. Input schemas and descriptions
are retained in [src/contract.json](../src/contract.json). Collections report `items`,
`total_count`, and `truncated`; limits are between 1 and 500. Every tool advertises the
read-only annotation. The server does not write RTL or execute build commands.

Module defaults and effective instance parameters are queried separately. The exact
SystemVerilog rendering is retained in parameter `value`; the numeric convenience
field `integer_value` is null when the constant is unknown or does not fit a signed
64-bit JSON integer in the native implementation.
