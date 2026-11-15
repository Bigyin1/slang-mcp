# slang-mcp

## Purpose and constraints

- This is a read-only MCP server for semantic analysis of SystemVerilog projects
  through the Slang C++ library. It does not modify RTL, act as an LSP, or build
  a regex parser or pseudo-netlist.
- Production code and tests use C++26; LLVM/Clang 23.1.5 is the recommended
  compiler. Slang 12.1 is pinned by commit SHA in `CMakeLists.txt`.
- Python is allowed only under `benchmarks/`. Create its environment with
  `uv sync --project benchmarks --python 3.10`; the lockfile is in that directory.
- Use the Slang C++ API rather than running the Slang executable as a subprocess.

## Architectural boundaries

- Keep MCP handlers thin and delegate to `SemanticService`.
- `ProjectManager` owns the active compilation lifecycle.
- The single public catalog has 13 tools. `project_load` accepts explicit ordered
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
- Do not suppress RTL errors or missing dependencies. Scope hints indicate only a
  possible cause; if the top cannot be built, retain the attempted diagnostics and
  distinguish them from the previous active project.
- Prefer suitable existing libraries for complex operations: Slang's built-in
  visitor for AST traversal and GitPython for Git operations in real-world tests.

## Checks

- `make check` builds the C++ code and runs clang-format, strict clang-tidy,
  Lizard, and CTest. Limits: cyclomatic complexity 6, cognitive complexity 10,
  5 local variables, 4 parameters, 6 branches, nesting depth 3, and 35 statements.
- `make check-benchmarks` checks the separate Python harness with Ruff, Pylint,
  strict mypy, Xenon, and pytest. `make check-all` additionally checks preparation
  and compilation of the pinned projects in `benchmarks/cases/projects.json`
  through the C++ server. Bender `0.32.1` generates sources, include directories,
  and defines; network access may be required.
- Before finishing a change, run the checks relevant to its scope. For production
  code or dependency changes, run `make check-all` if the environment is available.
- Update `benchmarks/uv.lock` when changing benchmark dependencies.

## Ambiguity and developer questions

Ask the developer when reasonable options lead to different external behavior,
public APIs, data formats, compatibility, or risks of data loss. Do not silently
choose an option that is difficult to reverse.
