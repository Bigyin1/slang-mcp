# Partial-design loading experiment

Historical API notice: reproduce the commands below with the server and harness
revision recorded in this report. The current server has one 13-tool catalog,
uses direct-path `project_load`, and no longer accepts core/full profile flags.
The last revision containing both profiles and these historical entry points is
`5b448e8`; use that checkout for the old CLI/API. Saved measurements remain unchanged.


The additive `project_load_partial` API was implemented after the 72-run study.
`native_api.py` validates it directly against real iDMA and CVA6 sources:
`uv run --project benchmarks python -m benchmarks.research_partial.native_api`.
The retained `native_api.json` contains five successful assertion sets and the
new executable hash: complete iDMA closure, missing child, missing package,
restored closure, and isolated CVA6 FIFO. These are functional validations of
the new API, separate from the original performance measurements below.

This experiment measures source-scope isolation in the actual C++ Release MCP
server. Complete dependency closures preserve the tested **module default**
signatures. Missing dependencies can still produce successful, plausible answers
with unresolved widths. A successful `project_load` is therefore insufficient to
establish semantic fidelity.

## Method

On 2026-11-15, four pinned real projects were prepared using
`benchmarks.runner.projects.prepare_project`, the repository caches, and Bender
0.32.1. Revisions, build defines, include directories, and ordered source-content
hashes are in `provenance.json`. The actual executable SHA-256 and machine platform
are in `raw.json`. The executable was `build/release/slang-mcp`; no model calls,
subprocess Slang, RTL rewriting, or production changes were used.

The primary matrix contains four projects × five scenarios × three sequential
fresh-server repetitions. An additional twelve runs remove dependencies from the
reduced IDMA/FlooNoC source sets. There are 72 runs and 432 measured MCP calls.
Every run initializes a new MCP stdio session, loads once, and queries, in order:

1. `get_hierarchy(max_depth=2)`;
2. `get_ports` for the selected source module, limit 100;
3. `get_parameters` for that module's declared defaults, limit 100;
4. `list_instances` filtered to that module, limit 100;
5. `summarize_diagnostics_by_code`, limit 100.

The timer surrounds each Python MCP `call_tool` round trip. Initialization and
process startup/shutdown are excluded. Byte counts are UTF-8 bytes of the MCP SDK
result JSON, including content and structured content; they are not transport
frame sizes or token counts. Scenarios run in fixed order with warm filesystem
caches, three repetitions rather than a statistical sample, and no randomized
crossover. The primary runs held an exclusive heavy-server timing slot. Additional
omission runs followed the tool-utility measurements; a tiny separate AXI pilot
may have overlapped. Preparation cost, peak memory, indexing subphases, and
end-to-end agent latency were not measured.

`full` uses the manifest's complete ordered files and original top.
`subtree_top` changes only the top to the selected module.
`reduced_subtree` retains only the selected module and its dependencies: one FIFO
file for AXI/CVA6; `cc_pkg.sv`, `cc_fifo.sv`, and `cc_stream_fifo.sv` for IDMA/FlooNoC.
All original include directories and defines remain. These reduced lists were
manually selected, not discovered by a production dependency resolver.
`missing_child`/`missing_package` remove one source from the original full list,
keeping the original top. The additional `reduced_missing_*` variants remove
`cc_fifo.sv`/`cc_pkg.sv` from the reduced list, keeping `cc_stream_fifo` as top.

The selected modules are AXI `fifo_v3`, CVA6 `cva6_fifo_v3`, and IDMA/FlooNoC
`cc_stream_fifo`. Full reference elaborations contain respectively 5, 11, 8, and
**0** instances of these modules. Thus the FlooNoC test isolates an included source
module, not an actual elaborated descendant. Labels `subtree_top` and
`reduced_subtree` name the experimental operations, not claims of preserved
in-context elaboration.

## Results

Median load milliseconds, three repetitions each:

| Project | Original sources | Full top | Same sources, selected top | Reduced sources | Reduced top |
|---|---:|---:|---:|---:|---:|
| AXI FIFO | 4 | 14.12 | 14.60 | 1 | 14.60 |
| CVA6 | 212 | 267.46 | 138.99 | 1 | 13.83 |
| IDMA | 308 | 313.51 | 301.62 | 3 | 14.07 |
| FlooNoC | 30 | 88.89 | 13.81 | 3 | 13.83 |

Absolute savings are modest here: CVA6 saves about 254 ms and IDMA about 299 ms
with reduced source sets. AXI is already at the measurement floor. Same-source
IDMA remains around 302 ms: changing top alone does not remove the cost and errors
of parsing all 308 inputs. These results cannot be extrapolated to larger SoCs.
The five-query bundles take about 62–66 ms across scenarios, indicating a roughly
13 ms per-call client/stdio scheduling floor; tiny differences below that scale
are not interpreted as server CPU differences.

Full-top error counts are AXI 40, CVA6 0, IDMA 22, and FlooNoC 12. AXI's
`InvalidMemberAccess` errors arise from the original top's scalar default channel
and request/response type parameters. IDMA has missing include/identifier/package
member diagnostics; FlooNoC has conversion errors. Only CVA6 is an error-free
full-build reference. Reduced selected tops all have zero errors; warnings are
1, 0, 2, and 2 respectively. This removes irrelevant invalid source context; it
is not evidence that the original full designs are correct.

The measured response total for full load plus five queries is AXI 18,040 bytes,
CVA6 50,294, IDMA 30,074, and FlooNoC 25,766. Reduced-source totals are 11,920,
11,096, 12,234, and 12,390 bytes. Most reduction comes from hierarchy and diagnostics,
not the fixed 11-port module signatures. Exact per-tool bytes, latency ranges,
diagnostics and counts are in `summary.json`; full response bodies are retained
in `raw.json` through content-addressed deduplication.

## Fact fidelity and incomplete dependencies

The independent source oracle is manually transcribed from the pinned FIFO
module declarations, not generated from MCP answers or text parsing. `audit.py`
checks all 11 port names, directions, and default widths. AXI/CVA6 have 32-bit
`data_i/data_o` and 3-bit `usage_o` for the declared default depth 8. IDMA/FlooNoC
have 32-bit data and 4-bit `usage_o`, following `cc_pkg::cnt_width(8)`. The latter
helper computes the width required to represent a count including the full
queue. Source locations are retained in raw port responses, enabling inspection
against the recorded files and line numbers.

All original, same-source selected-top, and reduced-source selected-top runs
match this source oracle and the full reference's declared default parameter
response. This tests default signatures only. It does not establish equivalence
of actual instance parameters, generated hierarchy, connections, reads/writes,
state, or drivers/loads. Selecting a module as top replaces enclosing overrides
with its declared defaults. No in-context equivalence or generic accuracy
percentage is claimed.

The damage tests distinguish useful negative controls from relevant omissions:

| Omission | Observed result |
|---|---|
| AXI `fifo_v3.sv`, full top | Errors 40→45; target symbol disappears; five matching instances→0 |
| AXI `axi_pkg.sv`, full top | Errors remain 40; default FIFO facts remain; unused-package negative control |
| CVA6 `cva6_fifo_v3.sv`, full top | Errors 0→10; target symbol disappears; eleven instances→0 |
| CVA6 `ariane_pkg.sv`, full top | Errors 0→311; unrelated FIFO default signature remains correct |
| IDMA `cc_fifo.sv`, full top | Errors 22→23; wrapper signatures and eight matching wrapper instances remain |
| IDMA `idma_pkg.sv`, full top | Errors 22→31; selected FIFO default signature remains correct |
| FlooNoC `cc_fifo.sv`, full top | Unchanged 12 errors and zero matching wrapper instances; unelaborated-source negative control |
| FlooNoC `floo_pkg.sv`, full top | Errors 12→65; selected FIFO default signature remains correct |
| IDMA/FlooNoC `cc_fifo.sv`, reduced top | 1 error; matching default signature survives, but `fifo_i` child disappears |
| IDMA/FlooNoC `cc_pkg.sv`, reduced top | 3 errors; successful port query returns `usage_o` width **null instead of 4** |

Each targeted result repeats three times. All 72 loads return MCP success, even
when error diagnostics exist. The missing-package unresolved-width example shows why
plausible returned facts require a completeness check. The missing-child example
shows that a correct wrapper signature says nothing about child completeness.

For use in the benchmark runner, prefer a verified dependency closure for a
specific source-scope task and label the answer with its selected top and default
configuration. Keep package/include/define inputs intact and inspect diagnostics
before accepting semantic facts. Use the full original elaboration for questions
about actual configured instances. Do not interpret a faster damaged load, fewer
hierarchy entries, or disappearance of unrelated errors as a correctness win.

## Reproduction and artifacts

Run from the repository root, with the existing benchmark environment and Release
server already built:

```sh
benchmarks/.venv/bin/python -m benchmarks.research_partial.prepare
benchmarks/.venv/bin/python -m benchmarks.research_partial.measure
benchmarks/.venv/bin/python -m benchmarks.research_partial.extra
benchmarks/.venv/bin/python -m benchmarks.research_partial.provenance
benchmarks/.venv/bin/python -m benchmarks.research_partial.audit
benchmarks/.venv/bin/python -m benchmarks.research_partial.archive
```

`prepare` uses `/private/tmp/slang-partial-research` and reuses any existing
`projects.json` there without re-verifying its original provenance. The recorded
run created these workspaces fresh through `prepare_project`. To reproduce from
fresh sources, choose a new workspace path in `prepare.py` or move that temporary
directory first. `provenance.json` records manifest intent and measured ordered
source contents, not an independent verification of every included header.
Network availability and cached generated files/submodules remain prerequisites.
The tracked compact raw file contains all measured observations, not just medians.

Scoped checks: Ruff lint/format, strict mypy, configured Pylint and Xenon A limits.
No production code or dependencies changed; the compiler/server test suite was
not rerun for this research-only artifact. `audit.py` is the executable source
oracle and full-reference consistency check.
