# slang-mcp

A read-only C++26 MCP server for compiler-backed SystemVerilog analysis. It links
directly to Slang 12.1. The default `core` profile exposes 15 tools for explicit
fragment loading, diagnostics, symbols, hierarchy, selected inspection fields and
source accesses. `--tool-profile full` retains all 30 compatibility tools.

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

Start with `project_load_partial`: the agent chooses ordered absolute source paths
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

In the `full` profile, `project_load` accepts ordered UTF-8 file lists. Every source
entry must be an absolute file path; include-list entries must be absolute directory
paths. Supply packages before RTL and models. Source order and duplicate entries are
preserved. A null define has no replacement text; a string becomes `NAME=value`.

```json
{
  "source_file_lists": ["/work/packages.f", "/work/rtl.f"],
  "include_directory_lists": ["/work/includes.f"],
  "top_module": "top",
  "defines": {"SYNTHESIS": null, "WIDTH": "32"}
}
```

The server holds one project. In `full`, `project_reload()` rebuilds the same inputs after RTL
changes. Path validation, compilation, and optional snapshot creation finish before activating
the new design. A failed load preserves the previous design and diff. Completed
compilations with error diagnostics remain available for inspection.

`get_diagnostics` reports scope, total count and truncation. Unresolved modules and
packages receive a possible-missing-dependency hint; their errors remain errors,
since a typo can produce the same message. Recoverable syntax/type errors also stay
visible. If no requested top can be built, the failed-load reply retains bounded
candidate diagnostics and explicitly reports that the active project is unchanged.

## Tools

Default `core` catalog:

| Area | Tools |
| --- | --- |
| Project and diagnostics | `project_load_partial`, `project_info`, `get_diagnostics` |
| Symbols | `find_symbol`, `describe_symbol`, `list_symbols`, `get_references` |
| Hierarchy | `get_hierarchy`, `list_instances` |
| Inspection | `inspect_module`, `inspect_instance`, `list_instance_facts` |
| Accesses and state | `get_signal_reads`, `get_signal_writes`, `get_state_elements` |

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

Unrequested sections are not evaluated. Identity is always returned; omitting
`fields` preserves the complete response. Use `list_instance_facts` to inspect many
instances of the same module in one call.

Existing clients that use `project_load`, focused legacy getters, connectivity or
`semantic_diff` should set MCP launch `"args": ["--tool-profile", "full"]`. The full
profile exposes all 30 tools and preserves complete default inspection sections. Profile selection
applies to both discovery and calls; core rejects tools it does not advertise.
Restart the server to change profile. Core does not construct or retain diff
snapshots. Full retains structural snapshot comparison; a zero diff does not prove
unchanged RTL behavior.

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
and, in full mode, compiler-independent snapshots. Slang objects stay inside `src/adapters/` behind
`Design`; normalized project-owned C++ models cross that boundary. Compiler visitors
build a shared access index lazily. Default elaborations share immutable syntax trees
while keeping their parameters and semantic state separate.

Connectivity describes source dependencies through assignments and direct signal port
bindings. It does not establish synthesized netlist connectivity, timing, simulation,
or formal proof. Expression actuals retain their text and resolved symbols but do not
create direct port hops. State discovery covers `always_ff` only. Reload is a complete
rebuild; symbol search is exact-name only.

For a fragment, call `project_load_partial` with ordered absolute `source_files`,
`top_module`, and optional `include_directories` and `defines`. This compiles the
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

The historical harness still compares `text-only`, `mcp`, and `mcp+skill`. It launches
`build/cpp/slang-mcp --tool-profile full` to preserve its existing experiment API;
`SLANG_MCP_BINARY` selects another executable.
Previous reports measure the former Python implementation and are not results for
the C++ server. See [benchmarks/README.md](benchmarks/README.md) before running new
agent experiments.

Research on the C++ server (2026-11-15) is recorded separately:

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

The first three measurements predate the additive `project_load_partial` API.
These exploratory studies support explicit small source scopes and a reversible
compact default; they do not establish universal tool necessity or model superiority.
