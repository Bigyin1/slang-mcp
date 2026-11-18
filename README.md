# slang-mcp

A read-only MCP server for SystemVerilog analysis, implemented in C++26 and
linked directly to Slang. An agent can load an entire design or a selected
fragment, inspect compiler diagnostics, and query the elaborated design
alongside the RTL source. Analysis remains available for fragments with
missing dependencies or RTL errors when Slang can elaborate the selected top.

The C++ integration also draws on [slang-server](https://github.com/hudson-trading/slang-server).

## What you can query

| Task | Main tools |
| --- | --- |
| Load an ordered file set and check diagnostics | `project_load`, `project_info`, `get_diagnostics` |
| Navigate elaborated hierarchy and count instances | `get_hierarchy`, `list_instances` |
| Inspect effective parameters and port connections | `inspect_instance`, `list_instance_facts` |
| Find symbols, inspect their types and see source-level uses | `find_symbol`, `describe_symbol`, `get_references` |
| See a macro expansion at its invocation | `expand_macro` |

Configure your MCP client to run `slang_mcp` over stdio. The server runs without
Python. The Linux x86-64 archive includes `AGENTS.md` with guidance for using
the tools. [Download the latest release](https://github.com/Bigyin1/slang-mcp/releases/latest).

## Documentation

- [Build, install and connect a client](docs/build-and-install.md)
- [Agent instructions](docs/agent-instructions.md)
- [Load a fragment and use the tools](docs/usage.md)
- [MCP tool reference](docs/mcp-reference.md)
- [Architecture and analysis limits](docs/architecture.md)
- [Performance measurements and Slang integration](docs/performance.md)
- [Development checks](docs/development.md)
- [Linux x86-64 release artifacts](docs/releases.md)

Released under the [MIT License](LICENSE).
