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

Current research includes [the paired source-analysis comparison](../benchmarks/research_compare/README.md)
and [the unified catalog study](../benchmarks/research_unified/README.md).
Older studies used earlier APIs; their reports and data remain in Git history at
commit `eb550e7`. See the [benchmark guide](../benchmarks/README.md).
