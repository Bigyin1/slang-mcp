# Checks and experiments

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
`build/cpp/slang_mcp` with the current explicit-file API;
`SLANG_MCP_BINARY` selects another executable.
Previous reports measure the former Python implementation and are not results for
the C++ server. See [benchmarks/README.md](../benchmarks/README.md) before running new
agent experiments.

Research on the C++ server (2026-11-15) is recorded separately:

- [RTL versus RTL + MCP + instruction](../benchmarks/research_compare/README.md):
  paired source-analysis experiments, semantic grading and actual token accounting.
- [Unified catalog](../benchmarks/research_unified/README.md): current 13-tool API,
  compilation-unit tests, catalog size and a fresh Terra Max CVA6 smoke trial.

- [Partial loading](../benchmarks/research_partial/README.md): 72 fresh-server runs,
  four pinned projects, source reduction and missing-dependency checks.
- [Tool utility](../benchmarks/research_tools/README.md): 217 calls exercising the
  previous 29 tools, aggregate/primitive equivalence, payloads and limitations.
- [Terra Max pilot](../benchmarks/research_agents/README.md): four exploratory arms,
  six source-checked questions each; raw answers and MCP traces are retained.
- [Catalog audit](../benchmarks/research_simplify/README.md): usage and mutation checks
  for semantic_diff, upstream methodology review and a 30-versus-12 pilot.
- [Focused analysis](../benchmarks/research_focused/README.md): four real-design tasks,
  native core/full profiles and exact selected-field payload comparisons.

The partial-loading and older studies predate the current unified 13-tool API;
the paired comparison and unified-catalog study use that API.
These exploratory studies support explicit small source scopes and a reversible
compact default; they do not establish universal tool necessity or model superiority.
