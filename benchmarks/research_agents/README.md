# Identified workload pilot

Researcher: GPT-6.1 Sol. Four native workload workers completed the pilot with requested model GPT-6.1 Terra and reasoning effort max. No alternative workload model was substituted. Spawn configuration is the identity evidence; provider-observed model identity remains unavailable.

## Runnable transport

Local inspection on 2026-11-15 found codex-cli 0.153.3 and Copilot CLI 1.0.83. Both accept a model string; Copilot advertises max effort. Neither help output establishes that a specific Terra model identifier is accepted or provisioned by its backend. Passing an invented CLI model string would not establish model identity. Native collaboration explicitly exposes `gpt-6.1-terra` and `max`, and therefore provides the available identified pilot route. Use fresh `fork_turns=none` workers, one per treatment. Preserve the spawn configuration as model identity evidence; provider-level observed identity is unavailable.

The bridge uses the existing MCP Python SDK and an actual persistent stdio server process. It initializes once, exposes tools/list and tools/call through JSON stdin lines, and records requests, complete responses and elapsed seconds. `--allow NAME` is repeatable: an allowlist filters the visible catalog and rejects excluded calls. No allow flags exposes the current catalog. It does not implement fake semantics or reload a server per query.

Run from repository root in a PTY; retain its exec session and send JSON lines using write_stdin:

```sh
benchmarks/.venv/bin/python -m benchmarks.research_agents.bridge \
  --binary /Users/svaparin/projects/slang-mcp/build/release/slang-mcp \
  --log /private/tmp/terra-mcp.calls.jsonl
```

Example requests:

```json
{"method":"tools/list"}
{"method":"tools/call","name":"project_load","arguments":{"source_file_lists":["/private/tmp/slang-partial-research/axi_fifo_core/source_files.f"],"include_directory_lists":["/private/tmp/slang-partial-research/axi_fifo_core/include_directories.f"],"top_module":"axi_fifo","defines":{"TARGET_FLIST":null,"TARGET_SYNTHESIS":null,"COMMON_CELLS_ASSERTS_OFF":null}}}
```

Use a distinct controller trace path per worker. End the PTY input after completing queries. This native route is a pilot with prompt-enforced file/tool restrictions, not OS isolation. Controller oracles remain readable to the broader host, so honest blinded workers must follow the explicit prohibition on reading them. Token counts and provider billing remain null; shell/bridge elapsed time is not total agent latency. Full worker latency must be recorded by the controller. Do not interpret missing telemetry as zero.

## Launch inputs and scoring

`real_tasks.agent.json` supplies three real AXI full-design tasks and three disjoint fragments. Matching `real_oracles.controller.json` derives expectations from pinned source, separately from server answers. The first fixture manifests remain an optional independent small smoke suite. Do not mix their outcomes into the real-design pilot.

Prepared runtime copies are under `/private/tmp/slang-terra-fragments/`: `tasks.agent.json`, `prompt.md`, `semantic.md`, and three `.sv` fragments. Durable fragment copies are retained under `fragments/`; copy those into a fresh workspace when rerunning. Full workspace is `/private/tmp/slang-partial-research/axi_fifo_core`, prepared by the deterministic research worker. Fragment source provenance: fifo_v3.sv lines 53–60 for flags, axi_fifo.sv lines 66–82 for missing-child instantiation, fifo_v3.sv lines 15–21 for missing-parent declaration. The manifests distinguish full and fragment scope; fragments may not borrow evidence from the full workspace.

Give each worker `pilot_prompt.md`, the task manifest, its assigned treatment, and explicit bridge invocation. Text-only reads source without semantic calls; mcp adds the real server; core adds the allowlist enforced by the bridge; skill uses the full catalog and `benchmarks/skills/semantic.md`. This pilot used six tasks in each of four workers, with a fresh context per arm. All six tasks share an arm context. Reading the full fifo_v3 source before the missing-child fragment creates potential context contamination despite explicit instructions to ignore that evidence. The 24 outcomes are correlated, not 24 independent trials. A follow-up should use a fresh context per task and arm, physically exclude unavailable source, randomize arm order, and repeat. `protocol.json` distinguishes the completed one-repetition pilot from the unexecuted repeated follow-up.

## Completed exploratory results

`pilot_results.json` retains exact per-task scoring, and `text.answers.json`, `mcp.answers.json`, `core.answers.json`, `skill.answers.json` retain raw final answers. MCP arms also retain complete `.calls.jsonl` bridge traces. Every arm answered all four answerable tasks correctly and correctly abstained on both unavailable-information tasks. There were no wrong answers or unnecessary abstentions in this small suite.

| Arm | Correct answers | Correct abstentions | tools/call requests | Response JSON bytes |
|---|---:|---:|---:|---:|
| Text only | 4/4 | 2/2 | 0 | unavailable |
| Full catalog, 29 tools | 4/4 | 2/2 | 7 | 41,701 |
| Core allowlist, 12 tools | 4/4 | 2/2 | 8 | 39,033 |
| Full catalog plus skill | 4/4 | 2/2 | 5 | 11,397 |

The suite reaches an accuracy ceiling: these easy AXI source questions do not distinguish the treatments. It supports feasibility of all four approaches on these cases. It does not establish that semantic tools, the smaller catalog, or the skill are necessary, unnecessary, or generally superior. Request counts and serialized response sizes describe these observed traces; they do not establish token savings, total latency improvement, or a repeatable causal skill effect. Model token counts and total agent seconds are null in every arm. Bridge query elapsed time excludes agent reasoning and file reading.

Catalog counts and measurements refer to the historical 29-tool server at revision `76387eb`. Separate partial-project loader development changes the public API and is outside these recorded trials; do not label these as measurements of that expanded interface.

## Historical evidence audit

Historical `benchmark_results/**/experiment.json` inspected locally all request `auto`, with effective effort null. They cannot establish Terra Max performance. The largest historical pilot plans 90 runs over 10 cases; other result directories contain overlapping selected cases, repeats, hard-text variants and post-fix checks. These are planned counts, not proof that all attempts completed or that all 19 curated cases received matched three-arm evaluation. Do not pool selected directories as independent experiments.

The 19-case corpus contains six synthetic and thirteen real-world questions; real-world rationales explicitly say “Slang reports” or “elaborates”. Independent source verification of those historical oracles is unproven. Oracle/data provenance must be audited before citing absolute correctness. Earlier shared prompts also instructed text-only workers to call unavailable project_load. The parent fixed the current prompt, but old traces remain confounded. Shared CLI profile, lack of OS sandbox, historical auto routing, case selection and repeated infrastructure fixes further limit causal claims. Old broad query latency or response-byte results are not workload accuracy or token savings.

## Verification

Initial Pylint invocation omitted the repository rcfile and missed its five-local-variable limit. The required `--rcfile benchmarks/pyproject.toml` check exposed two oversized functions; the bridge was refactored to separate dispatch, recording, and the request loop. After correction, configured Pylint passes at 10.00/10, Ruff lint and formatting pass, strict mypy passes, and git diff --check passes. A fresh real-server smoke after refactoring exposed only project_load, rejected excluded get_hierarchy, and loaded the hierarchy fixture with zero diagnostics. The earlier persistent-session smoke also returned hierarchy instances. One earlier malformed smoke supplied RTL as a file list; the real server correctly rejected it, then the corrected ordered-file-list smoke succeeded. No heavy real-world compilation was launched concurrently with timing work.
