# Benchmark results and methodology

These results describe experiments performed on November 15, 2026, using the C++
Slang MCP server. They compare source-only work with source inspection plus MCP
and a detailed instruction. They do not establish general model superiority.
The benchmark harness, Python code, input corpus, and detailed artifacts are
local-only and ignored by Git. The full historical materials remain in Git at
commit `7cb50be`; the main experiment was frozen at `9de333a`, and the exploratory
follow-up at `ebd9989`, before their respective runs.

## Main comparison

Six tasks were run twice in each arm: 24 fresh CLI sessions. Four tasks used
pinned fragments from CVA6, FlooNoC, AXI, and iDMA; two synthetic controls tested
single-unit macros and an invalid fragment with a missing dependency. Agents had
the same source and configuration, chose their own files, and could inspect RTL.
Both arms used the requested `gpt-5.6-terra` model with `max` reasoning effort;
`gpt-6.1-terra` was unavailable through the CLI. Provider routing was not
independently attested.

| Metric, 12 attempts per arm | Source only | Source + MCP + instruction |
| --- | ---: | ---: |
| Correct factual criteria | 96/96 | 96/96 |
| Mean elapsed time | 261.3 s | 335.7 s |
| Input tokens | 1,095,748 | 4,598,823 |
| Cached input tokens | 785,920 | 3,943,680 |
| Input excluding cached tokens | 309,828 | 655,143 |
| Output tokens | 123,363 | 155,671 |
| Reasoning output tokens | 98,623 | 116,611 |

MCP was slower in 10 of 12 matched pairs. On the four real RTL fragments alone,
both arms scored 64/64, with mean times of 356.3 s and 401.4 s respectively.
These small fragments produced a ceiling effect: both arms answered every factual
criterion correctly. Times depend on service load; the sample is too small to
establish statistical significance.

## Exploratory broken-RTL review

A separate follow-up used two real-source fragments with benchmark-inserted
errors and an intentionally unavailable external monitor. Each case had one
run per arm, with no indication of the number or locations of defects. The
source-only arm found 5 of 6 seeded local defects; MCP plus instruction found
all 6. Scores were 13.5/16 and 16/16 respectively. These seeded defects are not
claims about upstream projects.

| Case / arm | Score | Time | Input (cached) | Output (reasoning) |
| --- | ---: | ---: | ---: | ---: |
| AXI / source | 7.5/8 | 269.6 s | 165,773 (114,176) | 10,611 (8,023) |
| AXI / MCP + instruction | 8/8 | 360.8 s | 897,004 (833,792) | 13,417 (9,689) |
| iDMA / source | 6/8 | 542.2 s | 98,753 (71,168) | 21,836 (19,380) |
| iDMA / MCP + instruction | 8/8 | 559.1 s | 703,970 (619,520) | 21,828 (17,080) |

The source-only iDMA answer missed an incorrect named port. Both AXI answers
found all three seeded defects, but the source-only answer also claimed a
supplied FIFO was missing and misstated the complete W-channel width. This
follow-up was chosen after initial main-study results and had only one repetition;
it is exploratory rather than independent confirmation.

## Evaluation and measurement

Two independent GPT-6.1 Sol reviewers scored answers against eight predeclared,
source-derived criteria per case, allowing semantically equivalent prose. Each
criterion received 0, 0.5, or 1. Explanation quality was scored separately for
reasoning, coverage, evidence, and calibration. Reviewers did not receive arm,
time, token, or each other's scores, although answers could reveal tool use.
One AXI scoring disagreement was resolved by an unblinded controller: both original
ratings were retained in the historical record, and the final score reflects the
criterion's stated optional width detail.

CLI-reported `turn.completed` counters supply token totals, summed across model
requests in the session. Cached input is a subset of input; reasoning output is
a subset of output. They are not added twice. The elapsed wall time includes
model and tool work but excludes preparation of the workspace and process spawn.
Neither token totals nor elapsed time are dollar cost. All attempts completed;
there were no selective reruns. The initial protocol and inputs were committed
before the relevant runs, and the exported artifacts were checked against them.

Read restrictions were enforced by prompts and reviewed public commands, not
full OS isolation. Provider cache was not cleared between attempts. The comparison
bundles MCP and its instruction; it does not isolate their individual effects or
compare other compilers. Two repetitions and two follow-up cases do not represent
large industrial projects. The original public traces, scores, source snapshots,
and audit code remain available in Git history for independent inspection.
