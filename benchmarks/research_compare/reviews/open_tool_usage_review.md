Review of the four finalized open follow-up attempts, using only exported public tool activity, invocation working directories, and result status metadata. All four have `status="completed"`. Raw traces, private reasoning, answers, and grader reports were excluded. These counts are separate from the main 24 attempts and payload probes; no answer-quality conclusion is made.

| Durable public trace | Completed command items | MCP calls | Failed MCP calls |
| --- | ---: | ---: | ---: |
| [AXI, MCP](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl) | 7 | 34 | 4 |
| [AXI, source-only](../open_results/axi_review_text-only_r1/public_trace.jsonl) | 16 | 0 | 0 |
| [IDMA, MCP](../open_results/idma_review_mcp+skill_r1/public_trace.jsonl) | 15 | 22 | 0 |
| [IDMA, source-only](../open_results/idma_review_text-only_r1/public_trace.jsonl) | 14 | 0 | 0 |
| Total, open follow-up only | 52 | 56 | 4 |

All 56 recorded MCP calls target server `slang`; neither source-only attempt calls MCP. The 12 tools used were `describe_symbol` 14 times, `get_references` 10, `find_symbol` 6, `inspect_instance` 6, `inspect_module` 5, `get_hierarchy` 4, `get_diagnostics` 3, `list_instance_facts` 3, `project_load` 2, `project_info` 1, `list_symbols` 1, and `get_state_elements` 1.

All 52 command strings were read directly, without a regex-only compliance verdict. Source/config/build-metadata inspection uses workspace-relative paths, including supplied `.bender` subtrees. No recorded command invokes network access, web search, another compiler/analyzer, subagents, package installation, RTL writes, or reads of outside-workspace oracles/reports/other attempts. One ancillary Git command warrants an explicit protocol note: [AXI source-only, line 31](../open_results/axi_review_text-only_r1/public_trace.jsonl#L31) ran exactly:

```sh
/bin/zsh -lc 'git status --short --branch 2>/dev/null || true'
```

This read-only repository-metadata probe is outside the narrow source-inspection/arithmetic operation set. Captured output is empty; the shell exit is zero because of `|| true`, so it does not establish that Git succeeded. There is no observed repository data or outside-file content returned, and no Git mutation. Preserve this as an ancillary scope deviation for protocol assessment, rather than treating it as either a demonstrated leak or an unqualified compliance pass.

The only nonzero command exit was [AXI source-only, line 3](../open_results/axi_review_text-only_r1/public_trace.jsonl#L3): an `rg --files` inventory with the excluding `!*` glob returned exit 1 and no output. The next plain inventory succeeded. This was a harmless workspace discovery failure.

Both `project_load` calls succeeded. [AXI line 18](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L18) loads four sources with two include directories; [IDMA line 33](../open_results/idma_review_mcp+skill_r1/public_trace.jsonl#L33) loads six sources with one include directory. All ten source entries and three include entries were inspected and resolve beneath their own invocation workspace. They name supplied RTL, checked-out dependencies, and `integration.sv`; no cross-run or outside-workspace load was observed.

The four failed MCP calls were all AXI `get_references` lookups using module-qualified port names. Exact selectors are retained here:

| Durable trace | `symbol` | `kind` |
| --- | --- | --- |
| [Line 69](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L69) | `axi_fifo.slv_resp_o` | `write` |
| [Line 70](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L70) | `axi_fifo.mst_resp_i` | `read` |
| [Line 71](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L71) | `axi_fifo.mst_req_o` | `write` |
| [Line 72](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L72) | `axi_fifo.slv_req_i` | `read` |

Each has `status="failed"`, `error=null`, null structured content, and `unknown symbol: <selector>` in text. [Line 74](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L74) then lists `axi_fifo` members; [lines 79–82](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L79) use returned `default:net:` / `default:variable:` identifiers and are accepted. This is a concrete identifier-discovery workflow; acceptance alone does not establish the completeness or usefulness of the returned reference facts.

Dependency discovery differs visibly between attempts. AXI MCP explicitly enumerates hidden `.bender` files at [line 11](../open_results/axi_review_mcp+skill_r1/public_trace.jsonl#L11), reads `fifo_v3.sv` at line 13, then loads it. AXI source-only uses a depth-limited `find` at [line 20](../open_results/axi_review_text-only_r1/public_trace.jsonl#L20); none of its command strings directly reads the checked-out `fifo_v3.sv`. This describes observed retrieval, not answer correctness. IDMA source-only discovers hidden files with `rg --files -uu` at [line 11](../open_results/idma_review_text-only_r1/public_trace.jsonl#L11) and subsequently reads the checked-out FIFO/package sources. IDMA MCP checks the supplied checkout directories at [line 15](../open_results/idma_review_mcp+skill_r1/public_trace.jsonl#L15), searches definitions with `--hidden` at lines 17 and 23, and reads them before loading.

IDMA also repeats facts already retrieved: [line 55](../open_results/idma_review_mcp+skill_r1/public_trace.jsonl#L55) inspects packet-FIFO parameters and connections; lines 65 and 66 revisit its connections and parameters separately without an intervening load. The instance identities are identical, line 66's parameter result exactly equals line 55's, and all connection facts from line 65 already occur in line 55. Reusing those facts is an observable workflow opportunity; no token/time benefit was measured here.

These findings concern preserved commands and MCP arguments, not operating-system read isolation. Shared startup context and the prompt-based read boundary remain the documented limitations. No model calls or source changes were made for this review.
