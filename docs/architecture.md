# Architecture

Thin MCP handlers call `SemanticService`. `ProjectManager` owns the active compilation
without constructing diff snapshots. Slang objects stay inside `src/adapters/` behind
`Design`; normalized project-owned C++ models cross that boundary. Compiler visitors
build a shared access index lazily. Default elaborations share immutable syntax trees
while keeping their parameters and semantic state separate.

Accesses describe source semantics, not synthesized netlist connectivity, timing,
simulation or formal proof. State discovery covers `always_ff` only. Reloading is
a complete rebuild; symbol search is exact-name only.

For a fragment, call `project_load` with ordered absolute `source_files`,
`top_module`, and optional `include_directories`, `defines` and `single_unit`. This compiles the
selected files and their includes without discovering missing dependencies or
loading the rest of the project. Add dependencies explicitly in a subsequent load.
Local queries remain available with diagnostics; the load summary identifies
`analysis_scope: "fragment"`, `parameter_context: "standalone_top"`, and
`completeness: "not_verified"`. Standalone defaults do not establish the parameters
of an instance in an unavailable parent. See [MCP reference](mcp-reference.md) for an example.
