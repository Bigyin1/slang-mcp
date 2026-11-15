This compiler-only probe compares two observed bulk queries with explicit empty-name filters. It is separate from the 24 worker attempts and makes no model calls.

| Original query | Counterfactual argument | Canonical structured bytes before | After | Requested facts retained |
| --- | --- | ---: | ---: | --- |
| IDMA `list_instance_facts` from repetition-1 public trace line 24 | `port_names: []` | 23,565 | 2,595 | Parameters and instance/page identity exactly equal |
| Floo `list_instance_facts` from repetition-1 public trace line 88 | `parameter_names: []` | 18,094 | 16,582 | Connections and instance/page identity exactly equal |

The IDMA reduction is 20,970 bytes (88.99%); the Floo reduction is 1,512 bytes (8.36%). These are paired structured-payload measurements, not estimates of worker tokens, wall time, billing, or answer quality. The retained projection comparisons include all instance identities and outer pagination metadata. Removed sections have empty `items`, `total_count: 0`, and `truncated: false`.

The frozen binary was used without changing server code, skill, cases, or original inputs. Exactly two `project_load` calls and four `list_instance_facts` calls succeeded. Actual arguments and structured results are retained in [calls.json](calls.json); canonical structured byte counts and projection hashes are in [results.json](results.json). [provenance.json](provenance.json) records the frozen revision, expected and actual binary SHA-256, frozen source-file hashes, and exact input-inventory verification before calls. The input inventories were verified again after the calls, with no missing, changed, or additional files.

Original input workspaces were used. Source/include paths from the observed load calls were rebased from each worker's workspace to the identical frozen input workspace. The probe server's working directory was the repository, rather than a worker workspace; source-location path formatting therefore differs from worker traces. Compare the paired before/after values within this probe, not its baseline byte count with the earlier trace table.

The byte encoding is UTF-8 JSON with sorted keys, compact separators, and `ensure_ascii=False`. These structured-only measurements exclude the text representation duplicated by the MCP server. The recorder also retains individual call durations and complete SDK-response byte counts as diagnostics; they are not used here to claim performance savings.

The current implementation computes both parameter and connection collections before name filtering, and always returns both section envelopes. An empty name list reduces returned facts; it does not skip collection computation. The bulk tool does not support `fields`. See [facts_for](../../../src/rtl_queries.cpp#L6) and [named](../../../src/query.hpp#L28).

The exact original implementation is archived as [original_probe.py](original_probe.py). Its original `calls.json`, `provenance.json`, and `results.json` remain unchanged; [original_evidence_hashes.json](original_evidence_hashes.json) records their hashes and the archived script hash. The original measurements above used exactly six semantic calls.

The replay entry point was subsequently refactored to read [queries.json](queries.json), derived from the saved original calls with source/include paths made workspace-relative. It rebases those paths using the committed manifest, requires the frozen binary and input trees, and does not read any original worker trace. The output directory must be fresh:

```sh
python -m benchmarks.research_compare.payload_probe --output /private/tmp/my-fresh-payload-replay
```

The replay enforces a 60-second outer timeout and performs exactly the same two loads plus four bulk queries, with zero model calls. The server working directory is explicitly the repository root to reproduce the original source-location formatting. It writes its evidence only inside the requested output directory.

One verification replay ran into `/private/tmp/slang-payload-replay-20261115`. Its before/after structured byte counts and hashes, and both retained projection hashes, exactly matched the original evidence. Both input inventories remained unchanged. [replay_verification.json](replay_verification.json) retains these comparisons, replay provenance, code/query hashes, and confirmation that all original evidence hashes are unchanged. This replay added six compiler-only semantic calls; it did not add worker attempts or model calls.
