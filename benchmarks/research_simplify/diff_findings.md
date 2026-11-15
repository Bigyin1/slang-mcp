# semantic_diff: workload usage and observable scope

Recommendation: exclude `semantic_diff` from the default compact catalog, retain it as an optional compatibility/debug capability. This is a catalog recommendation, not a recommendation to delete implementation. Its useful, bounded function is a signature/hierarchy/parameter/diagnostic delta between two loads; it does not establish RTL behavioral equivalence.

## Usage audit

Reproduction: `benchmarks/.venv/bin/python -m benchmarks.research_simplify.diff_audit` from repository root. Prerequisites: the built `build/release/slang-mcp`, the benchmark virtual environment, and the prepared `/private/tmp/slang-partial-research` workspace. Prepare that upstream workspace first with `uv run --project benchmarks python -m benchmarks.research_partial.prepare` (uses pinned manifests, repository caches and Bender 0.32.1; network may be required). The script intentionally hardcodes the existing AXI Bender checkout path shown in `diff_probe.json`; if a different preparer chooses another cache path, update `FIFO_ROOT` to the matching pinned checkout before rerunning. The script does not prepare or fetch dependencies itself. `diff_usage.json` retains each historical attempt and per-tool counts, separate native workload logs, and separate scripted survey counts. This is a census of available repository artifacts, not a claim about external users or all past executions.

| Evidence population | Denominator | Actual semantic_diff calls |
| --- | --- | --- |
| Historical `benchmark_results` | 218 attempt directories, 990 MCP calls | 0 |
| Historical `benchmark_smoke` | 3 attempt directories, 4 MCP calls | 0 |
| Historical completed attempts | 220 `completed=true`, 994 MCP calls; 148 attempts use MCP | 0 |
| Historical metadata-less attempt | 1 text-only trace, 21 non-MCP calls | 0 |
| Native `research_agents` workloads | 3 tool-enabled arms, 20 MCP calls | 0 |
| Scripted `research_tools/results` survey | 4 project files, 217 calls | 8 |
| This audit's controlled probes | 14 calls, 5 explicit diff calls | 5 |

Historical attempts include successes and failures: 194 SUCCESS, 22 WRONG_ANSWER, 3 AGENT_FAILURE, 1 TIMEOUT, and 1 without metadata. They are attempts, not independent users or unique tasks; five directories are `attempt_002`. Completion flags describe harness records rather than correctness. The 221 attempt directories contain modes mcp=75, mcp+skill=74, text-only=72. Some tool-enabled attempts make no MCP calls.

`tool_calls.json` is used when available (220 directories); only the single trace-only attempt falls back to `tool.execution_start` events. Thus tool-call mirrors in 220 traces and metadata are not double counted. All 2,114 extracted tool-call IDs, including non-MCP tools, are unique across this population. All 220 trace/tool_calls mirrors have exactly matching ordered call IDs, and no slang-classified call lacks mcpToolName. Merely searching trace text would mislead: 148 traces mention `semantic_diff` in catalog/prompt content, while zero execution-start records invoke it. The workload corpus has 166 `project_load` calls and zero `project_reload` calls. Consequently this evidence has little exposure to the longitudinal edit/reload use case the tool serves.

Native logs are `core.calls.jsonl` (8 calls), `mcp.calls.jsonl` (7), and `skill.calls.jsonl` (5). Each request is counted once; tools/list catalog entries are excluded. The text-only arm has no MCP log. The four scripted survey files each call diff twice: before reload and after unchanged reload. These eight calls show explicit researcher coverage, not autonomous workload demand. C++ tests in `tests/cpp/semantics.cpp` also exercise diff and preserve its regression value, but are not workload usage.

## Controlled real-server experiments

`diff_probe.json` preserves complete SDK answers, error flags, and recorder timings. SHA256 hashes identify binary and original source. The experiment uses `build/release/slang-mcp` through the MCP SDK, a temporary copy of the AXI pinned common_cells `src/fifo_v3.sv`, original include files, and `COMMON_CELLS_ASSERTS_OFF`. The checked-in AXI Bender lock pins common_cells 1.40.0 to revision `1281545696eb3fcba50ec5b4275993476a3c710e`; the unpacked checkout has no Git metadata, so the fixture byte hash is the direct identity evidence. It never writes original RTL. Exact substitutions are guarded to match once; this is a controlled fixture edit, not an RTL parser. Each mutation begins from original source, loads a baseline, writes the changed copy, then reloads in the same server. Source path varies per reproduction; response values/counts below are deterministic, timings are not a performance experiment.

| Edit | Load/reload errors | Diff result |
| --- | --- | --- |
| Body only: `status_cnt_q + 1;` → `status_cnt_q + 2;` | 0/0 | `compared`, 0 changes |
| Parameter default: DEPTH 8 → 16 | 0/0 | 9 changes: 3 parameter, 3 effective_parameter, 1 port, 2 diagnostic |
| Port direction: testmode_i input → output | 0/0 | 1 port change |
| Unchanged source reload control | 0/0 | `compared`, 0 changes |
| Same top/source/includes/defines, fragment → file-list full load | 0/0 | `compared`, 0 changes |

Each compilation has zero diagnostic errors; warnings are retained. All 14 tool responses succeed. The body-only change modifies the FIFO occupancy update while preserving its signature, instance tree and diagnostics: zero reported changes is therefore not evidence that RTL behavior stayed unchanged. The parameter edit changes DEPTH, ADDR_DEPTH, and local FifoDepth both at definition and effective-instance levels, widens usage_o, and changes one warning's content (represented as removal plus addition). The port-direction edit demonstrates useful detection without requiring a parameter cascade.

The scope experiment records fragment metadata in the baseline and its absence in the following full-load summary. Its zero diff demonstrates that analysis-scope metadata is not part of the comparison. It does not assert that this standalone FIFO is incomplete; the concern is that a genuinely incomplete fragment and a full project with the same top name would also be accepted as comparable without a scope warning.

## Implementation evidence and cost boundary

`src/project.cpp:68–94` snapshots declared ports (excluding location), parameters, instance paths/module names, and effective parameters. `src/project.cpp:229–243` additionally records definition identity/kind and diagnostics. It does not snapshot procedural expressions, read/write accesses, instance connection expressions, source text or a behavioral representation. These omissions explain the observed body-only false negative; additional behavioral mutations have not been measured here.

`ProjectManager::load` (`src/project.cpp:163–184`) unconditionally calls `snapshot(*candidate)` before replacing active state. Both `project_load` and `project_load_partial` reach this path, and reload delegates to it. Therefore hiding diff from tools/list alone does not remove snapshot work. Every load enumerates definitions, queries every non-package definition's signature, enumerates instances/effective parameters, serializes diagnostics, and builds an ordered string map. A comparable next load also copies the prior map into `previous_` before installing the new snapshot. Two retained maps and transient construction/copy work exist even if diff is never called. No percentage overhead, latency saving, or memory size is claimed: a controlled lazy-versus-eager production implementation benchmark was not run.

The previous-state guard checks only `config_.logical_module == config.logical_module` (`src/project.cpp:176`). It does not compare source sets, include directories, defines, load format, or analysis scope. Different projects or fragments sharing a top name can thus produce a delta labeled `compared`. Only the immediately prior comparable state is retained; there is no explicit named baseline or historical comparison API.

The evidence supports a small default discovery catalog because no observed workload requested this capability and the current name is broader than its measured guarantees. Optional retention preserves signature/configuration regression and diagnostics workflows. If it is later promoted, document the narrow snapshot categories and scope/baseline contract explicitly; consider lazy snapshot policy separately, since catalog filtering alone cannot reduce current eager work. Zero use in this corpus does not prove the tool is useless.
