# Unified catalog and compilation-unit support

This change replaces the public core/full split at `5b448e8` with one 13-tool
catalog. `project_load` receives explicit ordered source paths and a top;
`single_unit=true` combines files, while false creates one syntax tree per file.
Both modes preserve explicit fragment scope. The default was already implicitly
single-unit before this change. No compatibility clients are assumed.

`get_references(kind=read|write)` includes read_write accesses and replaces two
public access getters. Inspectors default to signature sections; other sections
remain opt-in. Semantic diff is absent from MCP and snapshots are disabled there.
Experimental internal service handlers remain covered by native tests but are not
registered MCP tools; their presence does not expand the public catalog.

## Deterministic catalog measurement

`metrics.json` compares compact UTF-8 JSON for checked-in contract entries using
`json.dumps(..., separators=(",", ":"), ensure_ascii=False)`, without a trailing
newline. Previous core entries are selected by the old server's 15-name allowlist.
These are contract bytes, not MCP-envelope bytes, model tokens, or measured latency.

| Catalog | Tools | Bytes |
| --- | ---: | ---: |
| Previous full | 30 | 18,839 |
| Previous default core | 15 | 10,117 |
| Unified | 13 | 7,579 |

The new contract is 25.1% smaller than core and 59.8% smaller than full. Input
schemas omit redundant titles and null alternatives for optional arguments; null
values remain valid in defines. This does not establish improved model accuracy.

## Fresh workload smoke trial

One fresh worker requested as `gpt-6.1-terra`, reasoning `max`, analyzed only
`core/cva6_fifo_v3.sv` from the pinned RTL tree used in the previous focused study.
The source hash matches that study's independently constructed
[oracle](../research_focused/oracle.json). Researchers and the separate code review
used GPT-6.1 Sol. Model identity is the spawn configuration, not provider telemetry.

The worker saw the current tools/list, selected the file itself, used standalone
parameters, and was prohibited from reading controller oracles and previous
answers. The bridge enforced real server calls; source restrictions were prompt
instructions, not OS isolation. `cva6.task.txt` retains the launch instructions;
`cva6.calls.jsonl` and `cva6.answer.txt` retain raw calls and the answer.

All 14 tools/call requests succeeded. The independent source/oracle review confirms:

- Both counters have packed width 4; defaults DEPTH=8 and ADDR_DEPTH=3.
- q has 9 source reads and 3 writes, n has 1 read and 5 writes, with locations
  correctly grouped into continuous assignments, combinational and clocked blocks.
- Reset and flush clear q; normal updates copy n into q.
- Accepted simultaneous push/pop holds occupancy, but at empty/full only one side
  is accepted. Both boundary requests can violate the source assertions.
- The feedback uses n/q staging; no in-place compound read_write access is present.

One source file was loaded, with zero compiler diagnostics. No repeated or paired
control run was performed, so this is a usability smoke check, not a ranking or
causal comparison against previous catalogs. No token/cost/agent-latency claims
are made. The worker's initial executable hash was not captured; the same-API
binary was relinked during the run for a complexity-only filter refactor. The
recorded final debug executable hash must not be mistaken for start-time provenance.

The worker correctly noted that references include accesses inside parameter-inactive
procedural branches; source-level references are not path-feasibility results.
Reading source alongside MCP is the intended workflow, especially for macro-heavy
RTL. The agent instruction now explicitly asks for source/header inspection and
verification of defines, include paths, file order and compilation-unit mode.
This trial does not justify another tool or a control-flow analysis subsystem.

## Verification

`make check` passed: strict formatting, clang-tidy, Lizard, and 41 native test
cases via CTest. Tests cover shared/isolated macros and unit declarations,
package visibility, per-unit includes and predefines, source order, strict boolean
validation, active-project preservation, default elaboration and stdio behavior.
`make check-benchmarks` passed all quality checks and 54 tests. All 11 pinned
build-validation configurations loaded through the unified API; generic tops
retain their intentional diagnostics (including 40 AXI FIFO errors and 0 CVA6
errors). The historical measurements are unchanged and use their recorded API.
Release build and CTest also passed.
