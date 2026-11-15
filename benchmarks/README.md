# Slang MCP benchmark

Python 3.10 controller around the **system `copilot` executable**. Authentication belongs to
Copilot: log in normally with `copilot login`. No JavaScript wrappers, credential extraction,
private CLI APIs, copied runtime, sockets or proxy servers are used. MCP modes launch
`build/cpp/slang-mcp` directly over stdio and give the agent absolute-path file lists.
Set `SLANG_MCP_BINARY` to select another binary. Build the C++ server before running
compiler validation or MCP treatments. Historical reports refer to the Python server.

Start small (three agent calls, one simple case, one repetition):

```sh
uv sync --project benchmarks --python 3.10
uv run --project benchmarks python -m benchmarks validate
uv run --project benchmarks python -m benchmarks list --case hier_generate --repetitions 1
uv run --project benchmarks python -m benchmarks run --case hier_generate --repetitions 1 \
  --model auto --output benchmark_smoke/simple
uv run --project benchmarks python -m benchmarks report --output benchmark_smoke/simple
```

`list`, `validate`, `report` and `run --dry-run` make **no agent/model calls**. Build validation
uses the native server over MCP and Bender, without agent calls:

```sh
uv run --project benchmarks python -m benchmarks validate --builds
```

`run` without filters defaults to the one-case `smoke` profile and one repetition (three runs).
Larger studies are opt-in; they have **not** been run as part of the initial smoke:

```sh
# 10 predefined cases x 3 modes x 3 repetitions = 90 agent runs
uv run --project benchmarks python -m benchmarks run --profile pilot --repetitions 3 --output benchmark_results/pilot

# 19 cases x 3 modes x 3 repetitions = 171 agent runs
uv run --project benchmarks python -m benchmarks run --profile full --repetitions 3 --output benchmark_results/full
```

Filters: repeatable `--case`, `--category`, `--mode`; limits: `--timeout` (default 300 seconds),
`--repetitions`; randomization: `--seed` (default 20260905). One agent runs at a time.
The installed version must be 1.0.83. Version is checked before each run. In this installation,
`--no-auto-update` caused the system launcher to select its older bundled runtime; the harness
therefore uses the ordinary launcher and fails on version drift. It never updates Copilot itself.

The user selected `auto` because gpt-5.4 was unavailable. Auto does not accept a reasoning-effort
flag. Requested and observed model identifiers are retained separately; model routing is a
confounder, so this setup cannot isolate tool effects as tightly as a fixed-model experiment.
`--model <fixed-id>` uses effort `medium` and verifies observed model identity.

## Experimental modes and isolation

Every run receives the same source tree, build manifest and task question. `text-only` has no
Slang MCP; `mcp` adds the server; `mcp+skill` also prepends `skills/semantic.md`. This instruction
contains strategy only. No case oracle or report is copied into a workspace. Every run uses a
fresh temporary source copy without Git history, a new CLI session and a separate temporary
directory. Repositories are prepared using GitPython at the commits in `cases/projects.json`.
Bender 0.32.1 supplies sources, includes and defines; the AXI dependency lockfile is retained.

At the user's request, there is **no OS sandbox** and Copilot uses its normal system profile
and authentication. Files outside the workspace are technically reachable through shell.
Copilot runtime caches and authentication state are shared. Memory is disabled by default in
noninteractive prompt mode; the harness does not enable it or resume sessions. Built-in MCP,
custom instructions, skill and delegation tools, web access tools and session database tools
are disabled through CLI options. Preflight rejects inherited MCP server configurations instead
of silently contaminating the baseline. This is practical workspace isolation, not a security
boundary or proof that the agent cannot access external answers.

The curated corpus has six synthetic semantic edge cases and thirteen multi-file real-world cases,
including eight CVA6 cases using the pinned `pulp-v3` revision and the
`cv64a6_imafdc_sv39` Bender target. The frozen ten-case pilot combines the six synthetic cases
with four of the CVA6 cases. The four additional CVA6 cases are reserved for the full experiment
and targeted comparisons. Real-world provenance is a separate dimension from semantic category.
Expected answers and human-readable rationales are controller-only. They come from explicit
source declarations, manually evaluated expressions and build configuration, not solely from
the server under test. Compiler checks are supplemental.

## Results and resuming

An output directory contains `experiment.json`, `raw/<case>/<mode>/rep_XX/attempt_XXX/`,
`normalized/{runs.jsonl,runs.csv,summary.json,summary.csv}` and
`reports/benchmark_report.md` with static PNG figures. Raw JSONL includes provider-emitted events;
reports inspect only final answers and observable tool use, never hidden reasoning.

Repeat the **identical command** to resume. Completed matching attempts, including failures, are
retained and skipped; `--force` creates new attempt directories and never overwrites old traces.
A changed corpus, model, code or limits requires a new output directory. Partial attempts do not
enter aggregates. The report uses the last completed matching attempt per run key. Failed runs
are not silently removed. Regeneration does not invoke Copilot.

Accuracy is exact deterministic contract matching. Integers allow surrounding whitespace and
an optional sign; strings/paths allow surrounding whitespace; JSON arrays retain order; JSON
object key order is ignored. Prose, fenced answers, booleans in place of numbers, and semantic
mistakes are not repaired. Missing telemetry is null, not zero. Cache tokens are reported
separately and are not added to input tokens a second time.

Task accuracy uses evaluable answers; reliability and overall success use scheduled runs.
Infrastructure failures and unfinished runs have explicit counts. Bootstrap confidence intervals
resample whole cases, keeping repetitions clustered. A one-case smoke has no meaningful CI and
supports no conclusion about MCP's general effectiveness. Monetary pricing is not assumed.

## Development

`make check-benchmarks` covers harness formatting, Ruff, Pylint, strict mypy, Xenon and
offline pytest. `make check` covers the C++ server. `make check-all` additionally compiles pinned RTL;
it makes no agent calls. Harness unit tests use fake traces and local Python subprocesses.

## Native research, 2026-11-15

Research workers used GPT-6.1 Sol; four blinded exploratory workload workers used
GPT-6.1 Terra with max reasoning effort. Results and reproducible deterministic
measurements are in [research_partial](research_partial/README.md),
[research_tools](research_tools/README.md), and [research_agents](research_agents/README.md).
The follow-up [catalog simplification study](research_simplify/README.md) audits
semantic_diff usage and upstream reports, then compares 30 versus 12 tools with
two fresh Terra Max workers choosing their own fragment source files.
The [focused analysis study](research_focused/README.md) extends this to eight
fresh task/profile runs, selected-field payload comparisons, and malformed-RTL
process checks. Its core/full profiles are enforced by the C++ server itself.
The 29-tool measurements predate the additive partial-load tool. Historical Python
results and the new native measurements must not be pooled.

The current baseline prompt no longer asks text-only agents to call unavailable
MCP tools, and workspace paths now match the launch directory. This correction
does not retroactively repair old experimental results.

The historical runner and older research scripts explicitly launch
`--tool-profile full` to preserve their tool surface. New native profile experiments
use the bridge's `--server-profile core|full`; the executable itself defaults to core.
