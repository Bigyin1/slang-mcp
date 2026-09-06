Use compiler-backed SystemVerilog information when it resolves semantic uncertainty.
Load the logical project from projects.json before semantic queries. Check diagnostics
if compilation state is questionable. Inspect elaborated hierarchy for generated instances
and effective instance parameters for overrides; declaration defaults are different.
Choose the narrowest query: use names on get_instance_parameters and ports on
get_instance_connections when the question identifies them. Connection expression text and
resolved symbols are different evidence; return the one requested. Do not use
trace_connectivity for a question limited to parameters or port bindings.
Use exact symbol lookup and returned identifiers to disambiguate declarations and types.
Prefer resolved semantic evidence for widths, types, hierarchy and cross-file symbols.
Read source for local behavior, comments, naming and intent; simple local questions may
need no MCP calls. Driver/load results describe source-level accesses, not a synthesized
netlist. Unsupported or truncated results do not prove absence. If a query fails, inspect
the available tool description and textual evidence instead of guessing its schema.
Return only the requested answer format.
