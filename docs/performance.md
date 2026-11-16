# Slang integration and query performance

## Measured change

Measurements on 2026-11-16 compare v0.1.1 with the hierarchy and instance indexes
added in this change. Both executables use macOS arm64, Clang 23.1.5, CMake
Release (`-O3`), Slang 12.1 and the same pinned MCP SDK. These are local server
measurements, not agent-task benchmarks or a comparison against slang-server.

The synthetic fixture instantiates 1,000, 4,000 or 8,000 copies of one simple
32-bit register module in a named generate loop. Every case has a `top` module
and one leaf instance per generate block. The full hierarchy therefore contains
approximately twice as many nodes as leaf instances.

A client launches a fresh server per case, initializes legacy MCP 2025-11-25,
then sends sequential JSON-RPC requests through real stdio pipes. Timings include
server work, response serialization, transport and client JSON decoding. Values
below are medians of five full `get_hierarchy` calls after loading the project.

| Leaf instances | v0.1.1 | Indexed traversal | Ratio |
| --- | ---: | ---: | ---: |
| 1,000 | 14.5 ms | 15.1 ms | no improvement |
| 4,000 | 72.0 ms | 21.7 ms | 3.3x faster |
| 8,000 | 275.2 ms | 42.1 ms | 6.5x faster |

Previously, each recursive hierarchy node scanned the entire node collection,
giving quadratic traversal cost. A parent-to-children index removes those repeated
scans. Exact instance paths also use an index instead of a vector scan, and
default-member inspection resolves the module name once rather than per member.
The indexes add linear storage in the number of nodes and instances.

Repeated loads showed no consistent material improvement. Small inspections and
500-instance fact queries also showed no reliable end-to-end improvement. The
change addresses hierarchy-query scaling; it does not establish faster parsing,
elaboration, lower memory use or faster agent tasks.

## Real RTL and correctness checks

Additional cases load the unmodified PULP `common_cells` `fifo_v3` and an AXI
fragment containing two differently configured `axi_fifo` instances. Sources are
pinned to common_cells `1281545696eb3fcba50ec5b4275993476a3c710e` and axi
`a256a3b86394fedf19e361047fccfdd7f6ef83e4`. The AXI fixture uses ordered package,
FIFO and integration sources, actual includes, `COMMON_CELLS_ASSERTS_OFF`, and
single-unit mode. Both fragments have zero compilation errors. Their small
queries remain around 12–13 ms; no speedup is established there.

Before/after SHA-256 hashes of complete structured replies match for generated
hierarchies, instance inspections, 500-instance facts and default members, and for
AXI hierarchy, instance inspection and state queries. Regression tests cover
child order, requested depth and replacement of indexes on reload. Benchmark
drivers and materialized fixtures remain in the ignored `benchmarks/` directory.

## Lessons from slang-server

The review used [slang-server at 0541246](https://github.com/hudson-trading/slang-server/tree/0541246eb1b9e4c1c986179cd9a9f1f8b5bb8b44):

- `ServerCompilationAnalysis` reuses parsed syntax trees, indexes instances and
  lazily creates analysis/reference data. Our access index is already lazy, but
  each explicit load currently creates a fresh source manager and compilation.
- `SlangDoc` tracks buffers and syntax trees. Reusing trees across MCP loads could
  help repeated analysis, but requires correct invalidation for edits, includes,
  defines, source order and compilation-unit mode.
- `ShallowCompilation` limits instance depth to three and permits invalid tops.
  This is useful for editor feedback; silently adopting that limit would change
  our hierarchy and diagnostic semantics. Explicit file-selected fragments remain
  the supported way to restrict analysis.
- The server retains Slang's default instance caching. An experimental build of
  our server with caching enabled passed the then-current 43 tests but showed no
  consistent speedup on these fixtures. The existing setting is retained; the
  experiment does not establish that enabling caching is safe for every query.

The pinned MCP SDK's `McpSessionHandler::ResponseWorkerLoop` polls unfinished
response futures at 10 ms intervals. This can account for much of the observed
12–13 ms latency on small requests. Transport scheduling must be separated from
compiler time before using those timings to judge Slang optimizations.
