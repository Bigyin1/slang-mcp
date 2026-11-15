# Focused semantic analysis experiment

Four single-task worker prompts are declared in `tasks.json`. They use complete copies of pinned real RTL trees under `/private/tmp/slang-focused-pilot`; workers choose concrete sources and dependencies. `source_provenance.json` records upstream pins and prior full-build provenance. It is controller evidence, not worker input. Worker prompts exclude sibling manifests, oracle files and prior results.

`oracle.json` derives expectations directly from pinned source with exact lines and file hashes. It explicitly separates lexical source evidence from compiler-dependent paths, state classification and references. AXI defaults contain invalid member accesses because default request/response types are `logic`; diagnostics and this boundary are part of the task. IDMA asks about missing-package and missing-child boundaries without prescribing a loading sequence. FlooNoC tests nested parameter-dependent generation. CVA6 tests counter reference classification and staged updates. No worker outcomes are claimed here.

`payload.py` uses the installed MCP SDK and the existing prepared full-project source lists solely for controller measurements. For each project it compares full module and root-instance inspection against `fields=["parameters"]`, verifies exact structured-content projection equality including identity, and records canonical SDK-envelope byte counts and SHA256 hashes. Outputs omit large response bodies. These are payload measurements, not token counts or latency benchmarks.

All eight comparisons passed on release binary SHA256 `63bdd05d104449fc2fa56a37e7afd0db75172e3b21f4bdb1f91495828b4a4991`.

| Project | Inspection | Full bytes | Selected bytes | Reduction |
|---|---|---:|---:|---:|
| axi_fifo_core | inspect_module | 10464 | 2672 | 74.5% |
| axi_fifo_core | inspect_instance | 5246 | 2550 | 51.4% |
| cva6_cv64a6_imafdc_sv39 | inspect_module | 48328 | 24604 | 49.1% |
| cva6_cv64a6_imafdc_sv39 | inspect_instance | 30210 | 24488 | 18.9% |
| idma_desc64 | inspect_module | 15248 | 4128 | 72.9% |
| idma_desc64 | inspect_instance | 4832 | 4006 | 17.1% |
| floonoc_nw_2tiles | inspect_module | 15740 | 1686 | 89.3% |
| floonoc_nw_2tiles | inspect_instance | 3020 | 1564 | 48.2% |

Reproduce from repository root:

```sh
benchmarks/.venv/bin/python -m benchmarks.research_focused.payload \
  --binary build/release/slang-mcp \
  --output benchmarks/research_focused/payload.json
```

Prerequisite: `/private/tmp/slang-partial-research` contains the four previously prepared pinned projects. Existing full file lists are intentionally not exposed in worker prompts. Paths and binary hashes are part of the reproducibility boundary. Measurements use one process and fixed order; they establish equality and bytes for these requests only.

Validation: scoped Ruff, Pylint (10.00/10), strict mypy, Xenon, and two projection/encoding pytest tests passed. The deterministic probe executed successfully across all four projects. Production checks and worker trials are coordinated separately by the parent task.

## Fresh paired worker audit

Eight fresh runs cover the four tasks once per native profile, core15 and full30, with the same field-selection API. `protocol.json` records controller-reported launch conditions, pre-fix binary identity, raw-artifact hashes, and limits. Terra/max was requested; actual provider model/reasoning and token use are not observable in retained artifacts. Runs were concurrent, one replicate, and not randomly ordered. Source sets and query strategies were selected by agents and differ within pairs. These observations support descriptive comparison only.

`answer_review.json` contains an independent manual source/trace review with five explicit, equally weighted criteria per task. All eight final answers satisfy all five requested criteria. This is correctness within the task scope, not proof of API completeness or profile equivalence. Both AXI answers disclose invalid default scalar member accesses. Both FlooNoC answers disclose source fallback for missing output-expression text. Both CVA6 answers give width4, preserve conservative inactive procedural references, distinguish staged updates, and correctly handle simultaneous push/pop at empty/full boundaries including assertion caveats. Both IDMA answers experimentally separate package and child boundaries and recover all four stored state elements. No requested-scope substantive unsupported claim was identified.

`audit.py` derives `audit_metrics.json` from raw MCP traces. Successful calls are protocol success (`isError=false` and no error envelope), including loads with diagnostics; they do not imply a valid design. Response bytes include tools/list and repeated structured/text content, canonically encoded as UTF-8 JSON with nulls retained. They are neither tokens nor whole-agent I/O. Shell commands, source reads, deliberation and provider usage are not included. Call indices in the audit are one-based trace positions including tools/list; workers may instead number only tools/call requests.

| Run | Rubric | Tool calls | Protocol success | Errors | Response bytes incl. catalog | Calls selecting fields |
|---|---:|---:|---:|---:|---:|---:|
| axi_core | 5/5 | 5 | 5 | 0 | 75966 | 1 |
| axi_full | 5/5 | 8 | 8 | 0 | 96873 | 0 |
| floo_generate_core | 5/5 | 17 | 15 | 2 | 122890 | 4 |
| floo_generate_full | 5/5 | 14 | 14 | 0 | 95075 | 0 |
| cva6_counter_core | 5/5 | 18 | 18 | 0 | 90111 | 2 |
| cva6_counter_full | 5/5 | 10 | 10 | 0 | 118123 | 0 |
| idma_partial_core | 5/5 | 20 | 20 | 0 | 82107 | 0 |
| idma_partial_full | 5/5 | 21 | 20 | 1 | 118420 | 7 |

Each core catalog response is 10,229 bytes and each full catalog response is 19,145 bytes under the audit encoding. Every recorded tool call belongs to its native listed catalog. Across paired runs, core used 60 tool calls (58 protocol successes) and full used 53 (52 successes); response totals were 371,074 and 428,491 bytes respectively. These totals mix different source loads and strategies, so they do not isolate catalog or selector effects. Field selectors were used in both profiles, with more usage in some core runs; availability alone does not guarantee an agent will use them.

The excluded `axi_batch_full` artifact is a continued-context warmup, not a fresh replicate. It remains in `audit_metrics.json` with `paired=false` and is excluded from paired quality and totals.

Observed gaps and rejected queries:

- FlooNoC core rejected two `list_symbols` requests on indexed generate scopes as unknown symbols (trace positions9 and10). The agent recovered using hierarchy, instance and connection evidence.
- IDMA full rejected `trace_connectivity(direction="upstream")` at position21. The answer explicitly excludes that rejected request from evidence.
- Both FlooNoC arms found null expression text for output-lvalue bindings. Source spelling and resolved symbols allowed correct answers, but the raw pre-fix API evidence remained incomplete. The parent subsequently fixed normalization; these worker traces must retain the old binary attribution.
- AXI core chose two sources and full chose four, causing different warning counts. FlooNoC full initially omitted axi_pkg, observed15 errors, then added it and reached0 errors. IDMA deliberately made four missing-definition configurations; full revisited the package-present/child-missing boundary. All configurations and diagnostic counts are preserved in `source_loads`.
- No non-default parameter elaboration, simulation, formal proof, synthesized-state inference, token-cost comparison or latency claim is supported by these trials.

Recompute trace metrics with `benchmarks/.venv/bin/python -m benchmarks.research_focused.audit`. Validation of this audit: scoped Ruff, Pylint10.00/10, strict mypy, Xenon and six focused pytest cases pass. `payload.json` remains the pre-fix measurement; any later `payload_final.json` must be interpreted using its own binary hash.

## Final process validation

`validation.py` exercised the later release binary SHA256 `df141b9e6f1fe9be5203dc536a6c0222d4f7cda64294c26a341308e04bdf913a` through the installed MCP SDK over stdio in both native profiles. `validation.json` preserves full replies for these bounded fixtures and canonical trace hashes (UTF-8, sorted keys, compact separators, nulls retained). Temporary absolute source paths vary between executions, so trace hashes identify the captured run rather than promise identical hashes across reruns. The generated fixture text is embedded in the probe; the pinned real RTL is read without modification.

All six process cases passed in both profiles:

| Case | Checked behavior |
|---|---|
| Recoverable syntax plus missing child | Load succeeds with error diagnostics; both declared ports remain queryable. `get_diagnostics` reports fragment scope, requested top, source count, completeness not verified, exact totals and no truncation. |
| Independent type error | Invalid scalar member access retains error severity and the unclassified scope hint. Only UnknownModule/UnknownClassOrPackage are classified as possible missing dependencies. |
| Unavailable requested top | MCP reports isError with compilation_failed, attempted-candidate analysis and requested top, diagnostics and preservation flag. Prior project_info is exactly unchanged and prior ports remain queryable. |
| Missing child restored | Adding its definition removes UnknownModule while the independent InvalidMemberAccess remains an error and unclassified. |
| Bounded candidate failure | A generated source with125 separate syntax errors and an unavailable top produces126 diagnostics. Exactly100 are returned, total_count=126 and truncated=true in both profiles. |
| Real FlooNoC output regression | Reuses the exact last source/include/define/top arguments from the pre-fix core worker trace. Channel1 FIFO input/output actual expressions all match the six literal source spellings and all have valid one-bit actual types. Output expressions now include ready_o[n][v], data_out[n][v] and valid_out[n][v]. |

The earlier eight worker answers and `payload.json` remain attributed to their pre-fix binary. No workers were rerun, and the final process checks do not change the earlier descriptive profile comparison. `payload_final.json` repeats all eight payload comparisons on the same final binary as `validation.json`: every projection still matches exactly, and the table's byte counts and 17.1–89.3% reductions remain unchanged. These root-level parameter queries do not exercise the child output bindings corrected separately. The final validation checks explicit malformed fixtures and one real binding regression; it is not exhaustive malformed-language coverage, simulation, synthesis, or formal verification.

Reproduce with `benchmarks/.venv/bin/python -m benchmarks.research_focused.validation --binary build/release/slang-mcp --output benchmarks/research_focused/validation.json`. Final scoped validation passes Ruff, Pylint10.00/10, strict mypy, Xenon, and nine focused pytest cases. Production build/check results are reported separately by the parent task.
