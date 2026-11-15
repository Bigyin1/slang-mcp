# Catalog simplification study

The default catalog should prioritize bounded fragment analysis. The agent chooses
an explicit ordered file set, top, includes and defines, and expands that set when
the question needs more evidence. No automatic dependency closure is proposed.
This study adds benchmark profiles and evidence; the production catalog remains
30 tools, including the recently added `project_load_partial`.

## semantic_diff decision

Recommend excluding it from the compact default catalog while retaining optional
compatibility access. [Detailed audit](diff_findings.md) and its raw JSON distinguish
actual workload calls from scripted coverage. There are zero diff calls among 994
historical MCP calls and 20 earlier native workload calls. There are also zero
historical reload calls: this corpus cannot establish that an edit/reload feature
is useless. Eight explicit diff calls in the four-design survey are researcher
probes, not agent demand.

Copied-source experiments show the current boundary: changing FIFO occupancy
increment from +1 to +2 produces zero changes, while changing a port direction is
detected. This is a signature/parameter/hierarchy/diagnostic comparison, not a
behavioral change detector. Comparing different analysis scopes with the same top
name is accepted without a scope warning. Hiding the tool does not remove the
unconditional snapshot work currently performed on load; its runtime cost remains
unmeasured.

## Evidence from ariklapid/pyslang-mcp

Reviewed upstream revision
[`3effff5b547bd9424bab138f0a17a84eb89f0568`](https://github.com/ariklapid/pyslang-mcp/tree/3effff5b547bd9424bab138f0a17a84eb89f0568).
Its README lists 15 tools, without semantic_diff. A smaller count is a useful
reference, not evidence that its exact decomposition is optimal for our tasks.

Two different experiment types must remain separate:

| Upstream experiment | Text | MCP | Skill + MCP | Interpretation |
| --- | --- | --- | --- | --- |
| 25 local deterministic cases | 13/25 | 20/25 | 25/25 | Scripted answer extraction/rules |
| 75 public RTL deterministic cases | 47/75 | 75/75 | 75/75 | Compiler-grounded scalar probes |
| Actual Codex, 20 cases × 3 trials | 39/60 | Not run | 57/60 | gpt-5.5 xhigh, two bundled treatments |

Sources: [deterministic report](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/skills/pyslang-verilog-context/evals/reports/comprehensive-comparison-2026-05-23.md),
[public RTL report](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/reports/real_examples_75/summary.md),
[Codex results](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/reports/codex_ab_20260614/summary.md).
The often quoted combined 60/95/100% is the first two deterministic rows, not a
three-arm autonomous LLM experiment.

Source inspection makes the distinction stronger. The deterministic runner's five
text bug handlers return unknown, and its skill handlers implement fixture-specific
regex/order rules. The extra five successes are programmed rule coverage, not
observed improvement in agent reasoning.
[Rule implementations](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/scripts/run_mcp_comparison.py#L376-L469),
[treatment execution](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/scripts/run_mcp_comparison.py#L1275-L1290).

The live Codex experiment excludes those five bug cases, supplies required tool
names in the MCP prompt, and has no MCP-only treatment. It scores stripped strings
exactly: a path prefix or a prose-wrapped scalar can count as wrong. It therefore
measures the bundle of tools, skill and guidance, with some formatting sensitivity;
it cannot identify the independent value of skill or natural tool discoverability.
[Prompt](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/scripts/run_codex_ab_evals.py#L204-L225),
[case selection](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/scripts/run_codex_ab_evals.py#L177-L194),
[scoring](https://github.com/ariklapid/pyslang-mcp/blob/3effff5b547bd9424bab138f0a17a84eb89f0568/scripts/run_codex_ab_evals.py#L498-L516).

Useful directions to borrow are diagnostic evidence, resolved type/parameter
information, focused instance connections and explicit analysis limitations.
Neither successful prescribed tool calls nor a larger task count establishes that
every API operation is necessary. Their 75-case corpus is mostly three repeated
question shapes, with expected answers derived from the same compiler tool.

## Candidate catalog

`profiles.json` defines a full control and a deliberately aggregate-oriented compact
12-tool treatment. These are experimental allowlists, not a production migration.

| Purpose | Compact tools |
| --- | --- |
| Load and scope | `project_load_partial`, `project_info`, `get_diagnostics` |
| Discover symbols and instances | `find_symbol`, `get_hierarchy`, `list_instances` |
| Inspect signatures and connections | `inspect_module`, `inspect_instance`, `list_instance_facts` |
| Accesses and state | `get_signal_reads`, `get_signal_writes`, `get_state_elements` |

The number 12 is not an optimization result. The point is to test distinct
capabilities with fewer overlapping entry points. The existing bridge's `--allow`
flags filter both tools/list and tools/call; no hidden fallback tools are permitted.
Queries needing richer references, syntax, scope member listing or transitive
connectivity can expose genuine gaps in this candidate.

Prior [four-design measurements](../research_tools/README.md) support these choices:

- `get_drivers`/`get_loads` duplicate writes/reads in the sampled answers. Their
  netlist-sounding names also need care; source accesses are the actual semantics.
- `inspect_signal` duplicates read/write pages under aliases, roughly doubling
  those sampled payloads. Consolidating operations should not duplicate evidence.
- `list_instance_facts` preserves a useful batch path: one call replaces discovery
  plus six queries for three instances. Fewer tool names must not force N+1 calls.
- Aggregate module/instance inspection contains focused facts but can return more
  bytes. A future fields selector is a candidate, not an implemented feature.
- State ownership and transitive subsystem state must be distinguished. Zero
  direct wrapper state does not mean zero state in its children.
- Connectivity needs separate directional tasks; current truncated and reverse-edge
  results do not yet justify promoting it to the compact default.

`project_reload` can be omitted in this read-only task because another explicit
partial load rebuilds the selected inputs. That is not a claim that reload is
redundant in editing workflows. Likewise, hiding full-filelist loading here does
not remove full-project analysis from the server.

## Agent-selected fragment pilot

Two fresh GPT-6.1 Terra workers, max reasoning, receive identical `task.txt`, with
the catalog as the only intended treatment difference. Both can read a copy of
the pinned iDMA common_cells src/include tree. No file set or dependency sequence
is prescribed. The task asks about standalone width, wrapper versus child state,
push connection/assignment, and unavailable parent-instance configuration.

Restrictions on controller reports and other workspaces are prompt-enforced,
not OS-enforced. There is one worker per arm, one multi-part question and no
randomized repeats. This is a feasibility probe; it cannot establish a quality,
latency or token advantage. Model identity is the requested native spawn setting,
not provider-observed telemetry. Token counts and total agent seconds are null.

Reproduction uses `benchmarks.research_agents.bridge` with the release binary and
one `--allow NAME` per compact profile entry; omit allow flags for full. Give each
worker a fresh context and trace/answer paths. Source copies contain src/include
from the pinned common_cells dependency of `idma_desc64`; see `protocol.json` for
revision and hashes. Prepare source workspaces using
`python -m benchmarks.research_partial.prepare` in the benchmark environment.
`task.txt` contains the pilot copy path, which must exist before launching workers.
Both profiles must see the same RTL contents. Record raw calls and final answers.

`python -m benchmarks.research_simplify.catalog_audit` recomputes catalog counts,
serialized SDK JSON sizes, tool counts and actual load arguments from the two logs.
These sizes are not token counts or total transport traffic. Task scoring is a
separate source-based review, not inferred from successful calls.

Completed results are retained in `full.answers.json`, `compact.answers.json`,
their `.calls.jsonl` logs, `catalog_results.json` and `scoring.json`:

| Observation | Full, 30 tools | Compact, 12 tools |
| --- | ---: | ---: |
| Correct answerable questions | 3/3 | 3/3 |
| Correct unavailable-parent abstention | 1/1 | 1/1 |
| Successful MCP calls | 19 | 16 |
| Rejected malformed bridge requests | 1 | 1 |
| Catalog SDK JSON bytes | 17,759 | 7,569 |
| All tools/call response JSON bytes, including rejection | 60,126 | 62,817 |
| Initial / final explicit source count | 1 / 3 | 1 / 3 |
| Initial / final diagnostic error count | 2 / 0 | 2 / 0 |

Both workers independently chose wrapper-only loading, observed unresolved cc_pkg
and cc_fifo, and added exactly the package and child implementation. The initial
usage_o width was unknown; after expansion it resolved to four bits. Both
distinguished zero direct wrapper state from state in fifo_i, resolved push_i to
local push and its separate assignment, and left the unavailable caller's Depth
unknown. Both final loads retained two packed-array conversion warnings. The
source-based oracle is independently documented in `scoring.json`.

Both workers initially sent standard nested MCP params to the bridge, which expects
top-level name/arguments. Each rejection was retained and corrected. This is a
bridge usability artifact shared by both arms, not a server semantic error or an
excluded-tool call. The summarizer counts these attempts explicitly rather than
discarding them. Subsequent calls all succeeded; compact used no excluded tools.

This pair demonstrates a viable compact workflow. It does not select an optimal
catalog: the compact arm used three fewer successful calls but returned 2,691 more
response bytes. Aggregate inspection can save round trips while returning extra
fields. The smaller catalog saved 10,190 serialized catalog bytes, but no token or
end-to-end speed claim follows. The full arm also used trace_connectivity and both
driver/write names; one trial cannot establish that these were harmful distractions.

Verification: `make check-benchmarks` covers the new audit code with the repository's
formatting, lint, type, complexity and offline test checks. The live server calls
are the integration evidence. Production C++ and dependencies are unchanged.

## Next discriminating experiments

Use fresh contexts per task and arm, repeated runs, randomized order and independent
source-derived oracles. Compare the same compiler evidence with full versus compact
catalogs before changing payloads; then test field selection separately. Do not
prescribe tool names in task prompts. Include partial-boundary recovery, unresolved
type/package widths, large repeated-instance inventories, sequential ownership,
read-modify-write accesses, direction-specific paths and actual edit/reload deltas.
Measure answer correctness, unjustified claims, dependency expansion, rejected calls,
response size and available model usage. Retain tasks where text-only already works
as controls, but avoid another all-correct easy suite as the sole justification for
removing capabilities.
