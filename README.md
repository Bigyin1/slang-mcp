# slang-mcp

A read-only MCP server for SystemVerilog analysis, implemented in C++26 and
linked directly to Slang. Agents select the files for a fragment, inspect its
diagnostics and query compiler-backed semantics alongside the RTL source.

Inspired by [pyslang-mcp](https://github.com/ariklapid/pyslang-mcp); the C++
integration also draws on [slang-server](https://github.com/hudson-trading/slang-server).

## Documentation

- [Build, install and connect a client](docs/build-and-install.md)
- [Load a fragment and use the tools](docs/usage.md)
- [MCP tool reference](docs/mcp-reference.md)
- [Architecture and analysis limits](docs/architecture.md)
- [Checks, benchmarks and research](docs/development.md)
- [Linux x86-64 release artifacts](docs/releases.md)

The server runs without Python.
Released under the [MIT License](LICENSE).
