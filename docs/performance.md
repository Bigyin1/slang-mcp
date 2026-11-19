# Slang integration and query performance

## Reference paging and JSON project manifests

Direct stdio checks used the local macOS arm64 Release build with Clang 23.1.5
and Slang 12.1. On the pinned RTLMeter OpenTitan configuration below,
`get_references` returned all 3,442 instantiations of `prim_flop` in seven
pages. Comparing the returned paths with Slang's instance inventory verified
the ordering and count. The full fixture had four compilation errors.

On CVA6 and iDMA, the inline and manifest forms returned equal load summaries,
ordered source lists, diagnostic records and the selected instance facts. The
fact queries covered both CVA6 TLB instances and all eight iDMA FIFOs. The
same request selects the same sources in either form.

| Fixture | Sources | Inline arguments | Manifest arguments |
| --- | ---: | ---: | ---: |
| CVA6 | 212 | 26,298 bytes | 84 bytes |
| iDMA | 308 | 41,284 bytes | 81 bytes |

The byte counts include UTF-8 JSON argument keys and paths. Absolute workspace
path lengths affect the comparison. A separate wrapper test removed an explicit
child definition. Both partial-loading forms reported the same missing-module
diagnostic and retained the same local signal width and write reference as the
complete input.

### Repeated reference lookup

Five alternating pairs compared the same Release build before and after
resolving a reference target without constructing its full symbol description.
Each series used a fresh OpenTitan compilation. The table reports the median
of the five per-series medians after discarding the first two rounds.

| Query | Adapter before | Adapter after | MCP stdio before | MCP stdio after |
| --- | ---: | ---: | ---: | ---: |
| UART signal | 2.78 ms | 0.15 ms | 12.74 ms | 12.69 ms |
| UART port by ID | 4.37 ms | 1.74 ms | 12.84 ms | 12.87 ms |
| `prim_flop` instantiations | 2.51 ms | 2.20 ms | 13.34 ms | 13.49 ms |

The adapter's first reference query still took about 1.56–1.57 s at the
median, including access-index construction. Warm adapter queries improved in
each of the five pairs. The wire results were identical, and the stdio timings
showed no consistent practical gain.

## Access index optimization

The access index now groups reference positions by symbol ID, preserving traversal
order without copying reference records into the lookup table. Reference queries
use this lookup instead of scanning every reference in the design. Source-level
read/write classification, declaration fallback and module instantiations are
unchanged.

Public queries no longer construct connectivity edges. The internal connectivity
query explicitly requests an index with edges; if needed, it replaces the lighter
index only after a successful rebuild. Connectivity remains outside the public
tool catalog. The first access query still indexes the entire loaded fragment;
this change does not implement indexing individual instances on demand.

Measurements on 2026-11-17 use the Release configuration described below and
RTLMeter OpenTitan at `69bbe91e8a2e911ef0562da2b0abab95dd4bbfc2`, with 643 ordered
sources, single-unit mode and top `chip_sim_tb` (39,379 elaborated instances).
The first UART signal reference query through MCP decreased from approximately
2.50 s to 1.69 s in the initial comparison. Two additional sequential runs without
concurrent builds measured 2.36–2.64 s before and 1.31–1.38 s after in the adapter
alone. Steady repeated adapter queries decreased from 9–13 ms to about 2.6 ms;
the first repeat was slower in both builds. The original index contained
1,627,605 references and 824,575
connectivity edges; the public-query index retains the same reference count and
builds no edges. These are local observations, not an agent benchmark or a
guarantee for other designs. Peak memory measurements varied too much to claim a
memory reduction.

All 28 post-load MCP results in the comparison sequence matched the original
build, including repeated reference queries, symbol searches, module inspection,
macro expansion, project information and diagnostics. Regression tests compare
complete reference/procedure records before and after enabling connectivity and
check replacement on reload. The benchmark harness remains in the ignored
`benchmarks/` directory.

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
