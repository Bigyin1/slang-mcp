# Development checks and experiments

Install Lizard 1.26.0 in your development environment, then run:

```sh
make check
```

This builds the C++ executable and Catch2 tests, checks formatting with
clang-format, runs clang-tidy with warnings as errors, and runs Lizard and CTest.
Limits include cyclomatic complexity 6, cognitive complexity 10, 5 local variables,
4 parameters, 6 branches, nesting depth 3, and 35 statements. Checks apply to
project code; dependency sources are excluded. `CLANG_FORMAT`, `CLANG_TIDY`, and
`LIZARD_EXECUTABLE` can be supplied as CMake cache variables when needed.

The benchmark harness and its data are local-only. The retained
[benchmark summary](../benchmarks/README.md) describes the results, methods,
and limitations; the original material remains available in Git history.
