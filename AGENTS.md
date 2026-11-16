# slang-mcp

## Purpose and constraints

- This is a read-only MCP server for semantic analysis of SystemVerilog projects
  through the Slang C++ library. It does not modify RTL, act as an LSP, or build
  a regex parser or pseudo-netlist.
- Production code and tests use C++26; LLVM/Clang 23.1.5 is the recommended
  compiler. Slang 12.1 is pinned by commit SHA in `CMakeLists.txt`.
- Use the Slang C++ API rather than running the Slang executable as a subprocess.

## Architectural boundaries

- Keep MCP handlers thin and delegate to `SemanticService`.
- `ProjectManager` owns the active compilation lifecycle.
- The single public catalog has 14 tools. `project_load` accepts explicit ordered
  source paths; the agent chooses dependencies. `single_unit` defaults to true;
  false creates a separate compilation unit for each source file. Do not add a
  fictitious `SVBuildProjectProvider`.
- Slang objects and pointers to its AST must not escape `src/adapters/`. Use only
  typed project-owned models in services and MCP responses.
- Distinguish `logical_module` (a build-system entity), `sv_module` (a
  SystemVerilog module declaration), and `instance` (an elaborated instance).
- Full connectivity tracing is outside the MVP; do not replace it with RTL text analysis.
- RTL read/write and driver/load queries describe source-level semantics, not a
  netlist. Use Slang's built-in visitor and the shared access index.
- Diagnostic errors are accepted for analysis on reload. A build exception must
  not change the active compilation or the latest semantic snapshots.
- The MCP server does not build semantic snapshots. Selecting `fields` in aggregate
  inspections avoids computing unrequested sections while retaining identity.
  Defaults contain parameters plus ports/connections. Legacy compatibility profiles
  are not needed.
- Detailed array/struct/union layouts are built on demand by `describe_symbol`;
  keep bulk queries compact. Preserve type depth/node/dimension limits and explicit
  truncation. Packed element width and static total bits are distinct quantities.
- Do not suppress RTL errors or missing dependencies. Scope hints indicate only a
  possible cause; if the top cannot be built, retain the attempted diagnostics and
  distinguish them from the previous active project.
- Prefer suitable existing libraries for complex operations, including Slang's
  built-in visitor for AST traversal.
- `expand_macro` uses recorded preprocessing metadata and syntax tokens from the
  active compilation. Do not implement textual substitution or reread files to
  guess the preprocessor state at a past invocation.

## Checks

- `make check` builds the C++ code and runs clang-format, strict clang-tidy,
  Lizard, and CTest. Limits: cyclomatic complexity 6, cognitive complexity 10,
  5 local variables, 4 parameters, 6 branches, nesting depth 3, and 35 statements.
- Before finishing a change, run the checks relevant to its scope. `make check`
  requires Lizard to be available on PATH.

## Ambiguity and developer questions

Ask the developer when reasonable options lead to different external behavior,
public APIs, data formats, compatibility, or risks of data loss. Do not silently
choose an option that is difficult to reverse.
