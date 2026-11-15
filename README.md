# slang-mcp

A read-only C++26 MCP server for compiler-backed SystemVerilog analysis. It links
directly to Slang 12.1. One catalog exposes 13 tools for explicit
fragment loading, diagnostics, symbols, hierarchy, selected inspection fields and
source accesses. There are no compatibility profiles.

The design was inspired by [pyslang-mcp](https://github.com/ariklapid/pyslang-mcp).
[slang-server](https://github.com/hudson-trading/slang-server) is the reference for
integrating the Slang C++ library. The server runs without Python or Python bindings.
Only the separate experiment harness under `benchmarks/` uses Python.

## Build and run

Use CMake 3.28 or newer and a C++26 compiler. The implementation is tested with
LLVM/Clang 23.1.5. Slang's build uses Python to generate its parser and diagnostic
sources; Python is not required to run the resulting executable.

```sh
CXX=/path/to/llvm/bin/clang++ cmake --preset dev
cmake --build --preset dev --parallel 6
build/cpp/slang-mcp
```

CMake fetches pinned versions of Slang, the MCP C++ SDK, nlohmann/json, and Catch2.
Upstream tools, Python bindings, and upstream tests are excluded. On macOS, all
targets use the system SDK's libc++ headers and runtime consistently.
Release builds with upstream LLVM on macOS also use matching `llvm-ar`,
`llvm-ranlib`, and `ld64.lld` tools for the MCP SDK's ThinLTO archives.

For a release build, use the `release` configure and build presets. To install:

```sh
cmake --install build/release --prefix /your/install/prefix
```

Configure the MCP client to launch the executable over stdio:

```json
{
  "mcpServers": {
    "slang": {
      "command": "/absolute/path/to/slang-mcp/build/cpp/slang-mcp",
      "args": []
    }
  }
}
```

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

The public API has one explicit-file loader and no legacy aliases, launch profiles,
connectivity traversal or semantic diff. Historical experiments retain their original
results and require the server revision recorded in their reports.

See [docs.md](docs.md) for arguments and result semantics. Input schemas and descriptions
are retained in [src/contract.json](src/contract.json). Collections report `items`,
`total_count`, and `truncated`; limits are between 1 and 500. Every tool advertises the
read-only annotation. The server does not write RTL or execute build commands.

Module defaults and effective instance parameters are queried separately. The exact
SystemVerilog rendering is retained in parameter `value`; the numeric convenience
field `integer_value` is null when the constant is unknown or does not fit a signed
64-bit JSON integer in the native implementation.

## Architecture

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
of an instance in an unavailable parent. See [docs.md](docs.md) for an example.

## Checks and experiments

```sh
uv sync --project benchmarks --python 3.10
make check
make check-benchmarks
make check-all
```

`make check` builds the C++ executable and Catch2 tests, checks formatting with
clang-format, runs clang-tidy with warnings as errors, and runs Lizard and CTest.
Limits include cyclomatic complexity 6, cognitive complexity 10, 5 local variables,
4 parameters, 6 branches, nesting depth 3, and 35 statements. Checks apply to project
code; dependency sources are excluded. `CLANG_FORMAT` and `CLANG_TIDY` can be supplied
as CMake cache variables if the tools are not beside the compiler or on PATH.

`make check-benchmarks` runs the retained harness's Ruff, Pylint, strict mypy, Xenon,
and pytest checks. `make check-all` also compiles the pinned benchmark projects through
the C++ server. This uses Bender 0.32.1 at `.tools/bender` and may need network access.
Some generic top modules intentionally produce diagnostic errors; validation reports
their counts. These commands make no model calls.

The experiment harness compares `text-only`, `mcp`, and `mcp+skill`. It launches
`build/cpp/slang-mcp` with the current explicit-file API;
`SLANG_MCP_BINARY` selects another executable.
Previous reports measure the former Python implementation and are not results for
the C++ server. See [benchmarks/README.md](benchmarks/README.md) before running new
agent experiments.

Research on the C++ server (2026-11-15) is recorded separately:

- [RTL versus RTL + MCP + instruction](benchmarks/research_compare/README.md):
  paired source-analysis experiments, semantic grading and actual token accounting.
- [Unified catalog](benchmarks/research_unified/README.md): current 13-tool API,
  compilation-unit tests, catalog size and a fresh Terra Max CVA6 smoke trial.

- [Partial loading](benchmarks/research_partial/README.md): 72 fresh-server runs,
  four pinned projects, source reduction and missing-dependency checks.
- [Tool utility](benchmarks/research_tools/README.md): 217 calls exercising the
  previous 29 tools, aggregate/primitive equivalence, payloads and limitations.
- [Terra Max pilot](benchmarks/research_agents/README.md): four exploratory arms,
  six source-checked questions each; raw answers and MCP traces are retained.
- [Catalog audit](benchmarks/research_simplify/README.md): usage and mutation checks
  for semantic_diff, upstream methodology review and a 30-versus-12 pilot.
- [Focused analysis](benchmarks/research_focused/README.md): four real-design tasks,
  native core/full profiles and exact selected-field payload comparisons.

The partial-loading and older studies predate the current unified 13-tool API;
the paired comparison and unified-catalog study use that API.
These exploratory studies support explicit small source scopes and a reversible
compact default; they do not establish universal tool necessity or model superiority.
