# Native tool utility experiment

Historical API notice: reproduce the commands below with the server and harness
revision recorded in this report. The current server has one 13-tool catalog,
uses direct-path `project_load`, and no longer accepts core/full profile flags.
The last revision containing both profiles and these historical entry points is
`5b448e8`; use that checkout for the old CLI/API. Saved measurements remain unchanged.


Measured 2026-11-15 using the native release binary and MCP Python SDK, with no external model calls. [Provenance](results/provenance.json) records the repository commit, executable SHA-256 and exact four pinned project specifications. Existing `prepare_project` workspaces from the partial-source experiment were reused read-only. This experiment changes no production behavior.

Run from the repository root:

```sh
UV_CACHE_DIR=/private/tmp/uv-cache uv run --project benchmarks python -m benchmarks.research_tools axi_fifo_core /private/tmp/utility-axi --output benchmarks/research_tools/results/axi
UV_CACHE_DIR=/private/tmp/uv-cache uv run --project benchmarks python -m benchmarks.research_tools.summary
```

An absent workspace is materialized with the existing pinned project preparer; an existing workspace must contain its exported `projects.json` and file lists. Substitute the other names in provenance for the remaining designs. Calls use the default release binary, overridable with `--binary`. Retain provenance separately when changing the executable or source revision.

The queries ask: which instances of a repeated FIFO implementation exist, what are their effective parameters and actual connections; what ports/default parameters/procedures does a module expose; where is a clock or FIFO occupancy counter read/written; what sequential state is owned by that module; what paths does a bounded connectivity query show; and what changes after an unchanged reload. These add explicit state, reference, connectivity, lifecycle and aggregate workflows beyond measuring whether a tool appeared in a 19-question agent corpus.

## Captured results

Each `*.calls.json` retains tool arguments, structured answers, SDK response bytes, latency and error flag. Each `*.checks.json` retains equivalence checks, reload diffs and independently read source excerpts. The bytes are compact JSON serialization of the SDK result (including both text and structured content), not tokenizer counts, complete transport framing or requests. `summary.json` reports aggregate costs against selected primitive fact payloads. Extra aggregate fields are excluded from equivalence claims.

| Project | Calls | Distinct tools | Errors | Repeated module | Instances |
|---|---:|---:|---:|---|---:|
| AXI | 52 | 29 | 0 | fifo_v3 | 5 |
| FlooNoC | 56 | 29 | 0 | cc_stream_fifo_optimal_wrap | 80 |
| iDMA | 55 | 29 | 0 | cc_stream_fifo | 8 |
| CVA6 | 54 | 29 | 0 | cva6_fifo_v3 | 11 |

The batch task returns the first three instances with up to 20 parameters/connections each. Both alternatives return identical parameter and connection pages for all 12 sampled instances (24 successful equality comparisons). Parameter envelopes are normalized because aggregate facts embed a page while the primitive adds target/value-kind metadata. Instance discovery in the primitive alternative is charged as one call plus two calls per instance. The aggregate returns the same instance prefix; every batch is explicitly truncated at the instance level, so these are **not complete project inventories**.

| Project | Aggregate calls / bytes | Primitive calls / bytes | Exploratory latency ms, aggregate / primitive |
|---|---:|---:|---:|
| AXI | 1 / 46,229 | 7 / 47,355 | 15.58 / 95.17 |
| FlooNoC | 1 / 58,177 | 7 / 59,725 | 12.24 / 89.39 |
| iDMA | 1 / 54,675 | 7 / 56,011 | 13.70 / 87.33 |
| CVA6 | 1 / 51,173 | 7 / 52,463 | 13.41 / 88.71 |

For the top module and selected repeated module in every project, `inspect_module` returns identical port, procedure and normalized declared-parameter pages to three primitive calls. For the top instance, `inspect_instance` returns identical effective parameter/connection payloads to two primitives. Aggregate module/instance replies contain additional information and cost more bytes: e.g. AXI top module 10,509 versus 7,495 bytes; AXI top instance 5,291 versus 2,352. This supports keeping aggregate and focused access paths for different question shapes; call count alone is insufficient.

For eight successful signal queries, `get_drivers` equals `get_signal_writes`, and `get_loads` equals `get_signal_reads`, including page metadata. `inspect_signal` also matches these pages, but includes each read/write page twice under aliases: AXI occupancy counter 45,417 bytes versus 22,322 for reads+writes; CVA6 occupancy counter 50,177 versus 24,636. These are measured redundancy candidates, not proof that public alias removal is compatible or that the duplicated semantics constitute physical driver/load analysis. Other projects used clock signals because the selected stream FIFO wrapper owns no occupancy counter.

## Source checks and limits

The AXI pinned `fifo_v3.sv` independently declares `status_cnt_q` at line47, uses it in continuous full/empty assignments at57/58, and assigns it inside `always_ff` beginning116 (reset120, update129). Native results identify that instance-qualified signal as state, return reads at the corresponding full/empty expressions, and trace edges to those output assignments. Thus this selected answer has direct RTL support, beyond comparing two tools implemented by the same server. CVA6 source excerpts independently show its FIFO `always_ff` and counter reset/update, and the sampled state/reference answers identify that counter. These checks validate selected facts, not exhaustive semantic correctness. Raw source excerpts preserve file paths and line numbers; aggregate equality itself is not independent ground truth.

Measured gaps and caveats:

- `get_state_elements(fifo_v3)` returns20 state entries across AXI's five instances; CVA6 returns total66 with only20 shown. The stream wrappers in iDMA/FlooNoC return zero **direct** state despite containing FIFO children. A wrapper-level zero cannot answer whether the subsystem contains state. Clock/reset interpretation and deep recursive state inventory remain separate needs.
- Clock references return totals6/3/2/12 for AXI/FlooNoC/iDMA/CVA6. They are source-level accesses/connections, not all transitive uses. Counter queries return13 references in AXI and CVA6. This set does not validate all reference kinds, class/package references or read-modify-write cases.
- Seven of eight bounded `trace_connectivity` calls report truncation at20 considered edges. `both` direction can traverse one binding forward and back, returning a cycle after two hops. AXI clock returns five such cycles without truncation; this is a graph traversal result, not proof of a hardware feedback loop. Direction-specific data-path investigations and completeness claims require more evidence.
- `semantic_diff` reports `no_previous_state` before reload and zero changes with `compared` afterward in all four designs. Changed-source/package-dependency invalidation is not measured here; missing dependency/completeness status is addressed by the separate partial-source experiment. Diagnostic counts or a usable query alone do not certify a complete project.
- All29 tool families ran successfully, including discovery/descriptions, diagnostics and project lifecycle. A successful or empty probe establishes exercised behavior, not universal utility. This is a deterministic workflow study, not an agent task success or tool necessity experiment.
- Latencies are one ordered warm-process pass; final passes could overlap the separate small agent pilot. No confidence intervals or isolated performance claim is justified. Calls and bytes are the main evidence. No external model costs/tokens were incurred.

Scoped verification: Ruff format/check, strict mypy, Pylint (10.00/10), and Xenon A/A/A pass for this directory. The native runs provide integration checks; production checks were not rerun because production code/dependencies were unchanged.
