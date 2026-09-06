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

### RTL inspection tools

The following tools extend the original eight tools. Collections use
`{"items": [...], "total_count": N, "truncated": false}`. Their `limit` defaults to 100
(10 for `inspect_signal`) and must be between 1 and 500.

| Tool | Arguments besides `limit` | Result |
| --- | --- | --- |
| `get_references` | `symbol`, optional `kind` | Declaration and elaborated semantic uses |
| `list_symbols` | `scope`, optional `kind` | Direct scope members; kinds match `find_symbol` |
| `get_ports` | `sv_module` | Default port types, packed widths, fixed unpacked dimensions, interface/modport |
| `get_parameters` | `target` | Module defaults or effective values for a nested instance path |
| `get_instance_parameters` | `instance_path` | Effective parameters, including top instances |
| `get_instance_connections` | `instance_path` | Formal ports, actual expression text and referenced symbols |
| `list_instances` | optional `sv_module`, `name`, `path_prefix` | Elaborated instance occurrences |
| `find_instance` | `query` (no `limit`) | Exact path or unique exact name; ambiguity lists candidates |
| `get_signal_reads`, `get_signal_writes` | `signal` | Access locations and assignment/port contexts |
| `get_drivers`, `get_loads` | `signal` | Source-level writes and reads, respectively |
| `trace_connectivity` | `signal`, optional `direction`, `max_depth` | Bounded source-level routes through direct port bindings and assignments |
| `get_procedural_blocks` | `sv_module` | Elaborated blocks, sensitivity syntax and bounded read/write sets |
| `get_state_elements` | `sv_module` | Variables written in `always_ff` blocks |
| `inspect_signal` | `signal` | Description, reference count and capped access summaries |
| `inspect_module` | `sv_module` | Default signature, declaration count and elaborated usage summaries |
| `inspect_instance` | `instance_path` | Effective parameters, resolved connections and child instances |
| `semantic_diff` | none | Bounded changes since the preceding successful same-project load |

For example, `get_parameters("leaf")` returns `value_kind: "declared_default"`, while
`get_instance_parameters("top.u_leaf")` returns `value_kind: "effective"`. A default `WIDTH=32`
and an overridden `WIDTH=64` are evaluated in separate Slang elaborations. Bare top names in
`get_parameters` denote declarations; use the explicit instance tool for effective top values.
Default-scope member IDs start with `default:` and can be passed to `describe_symbol`.
Nested module definitions that cannot be independently instantiated report an explicit unavailable
default-signature error; their effective instance queries still work. Snapshots retain their
definition and mark `signature_unavailable`, without preventing project loading.

Connections distinguish `signal`, `expression`, `unconnected`, and `interface`. Actual expression
text is capped at 1,000 characters; referenced symbols are capped at 500 with `symbol_count` and
`symbols_truncated` metadata. For `.d(a & b)`,
the actual remains an expression with both resolved symbols; it is not collapsed to one signal.
Named, positional, wildcard and unconnected ports are supported. Interface connections expose
the resolved interface and formal modport; individual modport driver paths are not expanded.
`describe_instance` retains its original compact schema; `inspect_instance` adds richer connections.

`trace_connectivity` follows `loads` forward and `drivers` backward; `both` explores both
directions. It returns bounded breadth-first routes, with a terminal reason of `no_edges`,
`max_depth`, or `cycle`. A child input produces an actual-to-formal hop and a child output a
formal-to-actual hop; `inout` ports provide both. For example, a trace from `top.a` can pass
through `top.u_leaf.d`, a continuous assignment, and `top.u_leaf.q` to an output actual:

```text
trace_connectivity("top.a", direction="loads", max_depth=5)
```

Only direct resolved-signal actuals create port hops. Open ports, interfaces, constants, selects,
concatenations, casts, and other expressions are excluded from those hops. Continuous and
procedural assignments participate as explicit source-level dependencies; they do not establish
netlist connectivity, timing, formal proof, or simulation behavior.

The access index uses Slang's semantic visitor, not token matching. Reads and writes are derived
from assignments, selectors, increments, declaration initializers, user subroutine arguments and
port directions. `read_write` participates in both sets. References retain source locations,
scope, instance and procedural block identity. Fully qualified port names resolve to their internal
signal for these new queries; identical short names in different instances remain ambiguous.
Module references include declaration and instantiation entries. Parameter value references are
classified separately. System-call arguments are conservatively `unknown`; exhaustive type-use
indexing, macro expansion provenance and transitive subroutine side-effect analysis are unsupported.
Empty results do not prove that an unsupported construct has no effects.

Drivers and loads describe source uses, not synthesized hardware. Counts are access sites, not
unique hardware drivers or execution counts; accesses in subroutine bodies are not expanded at
each call. Procedure summaries cover active elaborated instances of the requested module and may
therefore contain multiple specializations. State discovery covers `always_ff` only; generic edge
triggered `always`, inferred latches and reset behavior are not inferred. Module diagnostic counts
are file-level counts. Optional fan-in/fan-out is deferred until these unsupported cases can be
represented reliably. Existing unbounded MVP tools retain their schemas for compatibility.

### Semantic diff lifecycle

Initial load reports `status: "no_previous_state"`. A successful load/reload of the same logical
project compares its previous and current normalized snapshots. Loading a different logical project
starts a new baseline. Failed path validation, construction, elaboration or snapshot creation leaves
both the active project and the previous diff intact. As in the original API, a completed compilation
with error diagnostics is accepted, so an agent can inspect errors and their changes.

Changes contain `category`, `identity`, `before` and `after`; null denotes an addition/removal.
Compound values are deterministic JSON strings. Categories cover definitions, default ports and
parameters, effective instance parameters, instance presence/type and diagnostics. Port snapshots
omit declaration positions so shifting source lines alone does not change a port. Diagnostics
include positions, so moving a diagnostic is an addition/removal. Internal signal changes and
connection changes are not currently diffed. Snapshots contain no compiler pointers and are captured
before activating a new design; no old compilation is retained for diffing.

For example, a parameter override change includes:

```json
{"category": "effective_parameter", "identity": "top.u_leaf.WIDTH",
 "before": "{\"is_local\": false, \"name\": \"WIDTH\", \"type\": \"int\", \"value\": \"32\"}",
 "after": "{\"is_local\": false, \"name\": \"WIDTH\", \"type\": \"int\", \"value\": \"64\"}"}
```

### Implementation layers

Thin MCP handlers call `SemanticService`, which uses `ProjectManager` for the active compilation.
`ProjectManager` depends only on the `ProjectProvider` protocol. `StaticProjectProvider` can be
constructed from typed in-memory `ProjectConfig` objects or the JSON format above. All dynamic
`pyslang` interaction and object traversal stays inside `adapters/`; only project-owned
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

`make check` runs formatting, strict Ruff, Pylint with the configured extension checks, strict
mypy, Xenon complexity gates, unit tests, and integration tests. Integration includes a real MCP
stdio subprocess round trip.

Linting includes security, logging, pytest, pathlib, and blanket-suppression checks;
mypy also checks unreachable code. Ruff and Pylint limit functions to 6 branches,
5 local variables, 4 returns, and 35 statements. Pylint additionally limits nesting to 3 blocks and
modules to 500 lines. Security exceptions are scoped to pytest assertions and the
Bender fixture helper's subprocess calls. Git checkouts use GitPython.

The network-backed suite requires Bender `0.32.1` and uses exact revisions of:

- `pulp-platform/common_cells` commit `9afda9abb565971649c2aa0985639c096f351171`
  (tag `v1.38.0`);
- `pulp-platform/axi` commit `a256a3b86394fedf19e361047fccfdd7f6ef83e4`
  (tag `v0.39.9`), with its transitive dependency revisions captured in a checked-in Bender
  lockfile.

The repositories are cloned into the ignored `.realworld-cache` directory. Each test invokes
`bender script flist-plus` with the `synthesis` target to obtain ordered sources, include
directories, and defines; no source list is duplicated in Python. The suite exercises packages,
parameterized `fifo_v3`, AXI typedef and assignment macros, includes, defines, ports, and
conditional generate elaboration:

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
- Driver/load queries cover conservative source-level accesses. Fan-in/fan-out and synthesized
  netlist connectivity are not implemented.
- This is an MCP server, not an LSP, source rewriter, SVBuild implementation, or Bender parser.

The recommended next milestone is `SVBuildProjectProvider`.

## Agent benchmark

The standalone Python 3.10 harness compares `text-only`, `mcp` and `mcp+skill` through the
system Copilot CLI. Start with one case and one repetition (three agent runs):

```sh
.venv/bin/python -m benchmarks run --case hier_generate --repetitions 1 \
  --model auto --output benchmark_smoke/simple
```

See [benchmarks/README.md](benchmarks/README.md) for the curated 15-case corpus, offline checks,
resume behavior, result artifacts and the limitations of the user-selected `auto` model and
workspace isolation. The 90-run pilot and 135-run full experiment are separate opt-in commands.
