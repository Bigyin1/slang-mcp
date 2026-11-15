# Development checks

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

Linux CI has separate `linux-x86_64-release` and `linux-x86_64-debug-sanitized`
jobs. The debug job runs real stdio protocol tests under ASan/UBSan, with Linux
leak detection enabled. The release job tests and packages the executable.
`ctest --preset sanitized` runs the same native suite locally.
