# slang-mcp

`slang-mcp` is a read-only MCP server for project-oriented semantic analysis of
SystemVerilog. It uses the Python bindings for Slang as a compiler frontend, so
queries operate on resolved and elaborated semantics rather than regular-expression
parsing or raw syntax nodes.

The MVP loads one logical project at a time over stdio. It requires CPython 3.10
and is intentionally constrained to `>=3.10,<3.11`.

## Install and run

Create the pinned development environment:

```sh
uv sync --python 3.10
```

Create a static project file, for example `projects.json`:

```json
{
  "chip": {
    "source_files": ["rtl/types_pkg.sv", "rtl/leaf.sv", "rtl/top.sv"],
    "include_directories": ["rtl/include"],
    "defines": {
      "SYNTHESIS": null,
      "DATA_WIDTH": "32"
    },
    "top_modules": ["top"],
    "metadata": {
      "owner": "rtl-team"
    }
  }
}
```

Paths are resolved relative to the JSON file. Source order is preserved. A `null`
define has no replacement text; a string becomes `NAME=value`.

Run the server directly:

```sh
.venv/bin/slang-mcp --config projects.json
# or
SLANG_MCP_CONFIG=projects.json .venv/bin/python -m slang_mcp
```

A minimal stdio client configuration is:

```json
{
  "mcpServers": {
    "slang": {
      "command": "/absolute/path/to/slang-mcp/.venv/bin/slang-mcp",
      "args": ["--config", "/absolute/path/to/projects.json"]
    }
  }
}
```

## Tools

- `project_load(logical_module)` resolves, validates, compiles, and activates a project.
- `project_reload()` rebuilds the active logical project from its provider.
- `project_info()` reports build inputs, configured and elaborated tops, metadata, and version.
- `get_diagnostics(limit=100, severity=null)` returns structured Slang diagnostics. The hard
  limit is 500; severity can be `ignored`, `note`, `warning`, `error`, or `fatal`.
- `find_symbol(name)` performs exact-name lookup for definitions, packages, typedefs,
  subroutines, parameters, ports, variables, and nets.
- `describe_symbol(identifier)` accepts a stable returned `symbol_id`, qualified name, or an
  unambiguous exact name and reports type, width, direction, ports, parameters, and members.
- `get_hierarchy(root=null, max_depth=null)` returns elaborated instances and generate blocks.
- `describe_instance(path)` reports an elaborated instance's module type, parameters, ports,
  simple connection syntax when available, and direct hierarchy children.

All tools declare the MCP read-only annotation. They only read RTL and retain compiler state in
memory; they never modify source files.

## Architecture and providers

Thin MCP handlers call `SemanticService`, which uses `ProjectManager` for the active compilation.
`ProjectManager` depends only on the `ProjectProvider` protocol. `StaticProjectProvider` can be
constructed from typed in-memory `ProjectConfig` objects or the JSON format above. All dynamic
`pyslang` interaction and object traversal stays inside `adapters/pyslang.py`; only project-owned
dataclasses cross that boundary.

A future `SVBuildProjectProvider` should implement only:

```python
def resolve(logical_module: str) -> ProjectConfig: ...
```

It should translate SVBuild's ordered sources, include directories, defines, tops, and metadata
into `ProjectConfig`. No MCP handler or semantic query needs to change.

The public terminology is deliberate: `logical_module` is a build-system entity, `sv_module` is
a SystemVerilog module declaration, and `instance` is an elaborated occurrence.

## Development and tests

The Makefile exposes deterministic commands:

```sh
make format
make format-check
make lint
make typecheck
make complexity
make test-unit
make test-integration
make check
```

`make check` runs formatting, strict Ruff, strict mypy, Xenon complexity gates, unit tests, and
integration tests. Integration includes a real MCP stdio subprocess round trip.

The network-backed suite requires Bender `0.32.1` and uses
`pulp-platform/common_cells` at exact commit
`9afda9abb565971649c2aa0985639c096f351171` (tag `v1.38.0`). It clones into the ignored
`.realworld-cache` directory. The test invokes `bender script flist-plus` with the `synthesis`
target to obtain the ordered sources, include directories, and defines; no source list is
duplicated in Python. It exercises packages, parameterized `fifo_v3`, includes, defines, ports,
and conditional generate elaboration:

```sh
make test-realworld
make check-all
```

Install Bender through its official installer or set `BENDER_EXECUTABLE` to the `0.32.1`
binary. For local development, a binary at `.tools/bender` is also detected automatically.

Normal unit and integration tests never require network access.

## MVP limitations

- Only one active logical project is retained.
- Reload is a complete rebuild; there is no incremental compilation.
- Symbol search is exact-name only. Stable IDs should be used to resolve ambiguity.
- Module descriptions use the first elaborated representative for parameterized port details;
  uninstantiated definitions therefore have declaration identity but may lack a signature.
- Port connection text is best-effort because some elaborated expressions have no source syntax.
- Driver/load and fan-in/fan-out connectivity are not implemented. No pseudo-netlist is inferred.
- This is an MCP server, not an LSP, source rewriter, SVBuild implementation, or Bender parser.

The recommended next milestone is `SVBuildProjectProvider`.
