# Controller-only compiler corroboration

Initial case tasks, source-derived oracles, per-mutation patches/provenance and workspace hashes were fixed before these checks. Independent pre-freeze review later clarified public IDMA flush wording and renamed configuration fields/files to match the unchanged original skill. Provenance records that task/config-only revision; source, oracle facts and effective compiler settings are unchanged. No follow-up model workload or outcome was used. This corroborates compile effects; it is not a compiler-only grading key. The eight-criterion prose rubrics also require the source behavior/configuration findings and boundary calibration.

The unmodified, frozen server `/private/tmp/slang-compare/bin/slang-mcp` was invoked through MCP `initialize`, `project_load`, and `get_diagnostics`, using its Slang C++ API. Its SHA-256 is in `compiler_corroboration_index.json`. No binary or production code was rebuilt or modified. An initial attempt with the stale `build/slang-mcp` failed tool argument validation (`source_file_lists` instead of the current API); no source was compiled in that failed attempt. Validation then used the same frozen server intended for the comparison.

For each case, controller-only temporary copies were made under `/private/tmp/slang-open-review-corpus/checked/<case>/<variant>`. Each copy retains the explicitly unavailable monitor. Source order was: all `.sv` files defining a package first (lexical path order), remaining supplied `.sv` files (lexical path order), then `integration.sv`. Hidden `.bender/` paths were included. Definitions, includes, top and `single_unit` are exactly the supplied workspace configuration with paths made absolute. No stubs or simulations were used.

| Case/variant | Error diagnostics (warnings retained in raw JSON) |
| --- | --- |
| axi baseline | UnknownModule: intentionally unavailable monitor |
| axi A1 only | UnknownMember at AW push expression; missing monitor |
| axi A2 only | NotAType at W FIFO dtype argument; missing monitor |
| axi A3 only | Missing monitor only; AR depth contract violation is source-derived |
| axi all seeds | UnknownMember + NotAType + missing monitor |
| axi compiler repairs only | Missing monitor only; AR depth violation remains |
| idma baseline | UnknownModule: intentionally unavailable monitor |
| idma I1 only | PortDoesNotExist at generated lane FIFO connection; missing monitor |
| idma I2 only | NotAType at packet FIFO data_t argument; missing monitor |
| idma I3 only | Missing monitor only; flush storage violation is source-derived |
| idma all seeds | PortDoesNotExist + NotAType + missing monitor |
| idma compiler repairs only | Missing monitor only; flush storage violation remains |

Baseline means original upstream source bytes plus the benchmark's adapted integration with the unavailable monitor. Each single-mutation variant applies only its corresponding recorded patch to that baseline. Compiler-repair variants retain only the third, non-compiler contract mutation. All corrections are confined to controller validation copies; worker RTL is unchanged.

Raw responses are stored as `cases/<case>/compiler_<variant>.json`, outside worker workspaces. Locations in those responses refer to the corresponding temporary validation copies. Preexisting warning diagnostics are not automatically extra defects and do not replace source reasoning.

The read-only runtime inputs under `/private/tmp/slang-compare-open/inputs/` were hash-checked against the corpus `workspace.sha256` files after validation. Both workspaces contain no oracle, patches, provenance, compiler report, model output or study-specific outcome data. The controller should freeze manifest/protocol identities and obtain independent case/oracle review before launching either comparison arm.
