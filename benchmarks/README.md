# Slang MCP benchmark

Python 3.10 controller around the **system `copilot` executable**. Authentication belongs to
Copilot: log in normally with `copilot login`. No JavaScript wrappers, credential extraction,
private CLI APIs, copied runtime, sockets or proxy servers are used. MCP modes launch
`.venv/bin/slang-mcp --config <workspace>/projects.json` directly over stdio.

Start small (three agent calls, one simple case, one repetition):

```sh
uv sync --python 3.10
.venv/bin/python -m benchmarks validate
.venv/bin/python -m benchmarks list --case hier_generate --repetitions 1
.venv/bin/python -m benchmarks run --case hier_generate --repetitions 1 \
  --model auto --output benchmark_smoke/simple
.venv/bin/python -m benchmarks report --output benchmark_smoke/simple
```

`list`, `validate`, `report` and `run --dry-run` make **no agent/model calls**. Build validation
uses Slang's Python API and Bender, not an agent:

```sh
.venv/bin/python -m benchmarks validate --builds
```

`run` without filters defaults to the one-case `smoke` profile and one repetition (three runs).
Larger studies are opt-in; they have **not** been run as part of the initial smoke:

```sh
# 10 predefined cases x 3 modes x 3 repetitions = 90 agent runs
.venv/bin/python -m benchmarks run --profile pilot --repetitions 3 --output benchmark_results/pilot

# 15 cases x 3 modes x 3 repetitions = 135 agent runs
.venv/bin/python -m benchmarks run --profile full --repetitions 3 --output benchmark_results/full
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

The curated corpus has six synthetic semantic edge cases and eleven multi-file real-world cases,
including six CVA6 cases using the pinned `pulp-v3` revision and the
`cv64a6_imafdc_sv39` Bender target. The frozen ten-case pilot combines the six synthetic cases
with four of the CVA6 cases. The two additional CVA6 cases are reserved for the full experiment
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

`make check` covers benchmark formatting, Ruff, Pylint, strict mypy, Xenon and offline pytest
alongside existing server tests. `make check-all` additionally checks pinned real-world RTL;
it makes no agent calls. Harness unit tests use fake traces and local Python subprocesses.
