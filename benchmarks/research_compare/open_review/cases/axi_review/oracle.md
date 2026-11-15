# axi_review — independent source-derived oracle

Status: exploratory, seeded benchmark mutations; not upstream bug claims. Written from source and explicit requirements before compiler corroboration or follow-up outcomes. Paths below are relative to the worker workspace. Line numbers are aids; equivalent symbol/hierarchy references are acceptable.

The integration package uses AXI typedef macros with `AddrWidth=37`, `DataWidth=128`, `IdWidth=6`, `UserWidth=5`. It instantiates `i_buffer` with `Depth=5`, `FallThrough=1`, then `i_wire` with `Depth=0`. Review the instantiated positive-depth branch, not an unused default parameterization or the wrapper alone.

## Source findings and minimal corrections

1. `rtl/src/axi_fifo.sv:79`, `compare_axi_types.i_buffer.gen_axi_fifo.i_aw_fifo`: the push expression selects `slv_req_i.aw_valid_en`. The macro `AXI_TYPEDEF_REQ_T` in `rtl/include/axi/typedef.svh` defines `aw_valid`, not `aw_valid_en`, and integration passes its generated `link_req_t`. This is a real local member-resolution error in the selected implementation. Replace only `aw_valid_en` with `aw_valid`, retaining the conjunction with `slv_resp_o.aw_ready`. Adding a new request field, forcing valid constant, suppressing the diagnostic, or removing AW buffering does not preserve the stated interface and handshake contract.

2. `rtl/src/axi_fifo.sv:101`, `...i_w_fifo`: `.dtype(Depth)` assigns the value parameter `Depth` to `fifo_v3`'s type parameter `dtype` (declaration in `rtl/.bender/git/checkouts/common_cells-3e2fcccecd7aee7b/src/fifo_v3.sv`). `Depth` is an unsigned integer value, not a SystemVerilog type. This is a semantic type-parameter error, independent of the AW member error. Restore `.dtype(w_chan_t)`. The concrete `link_w_chan_t` contains 128 data bits, 16 strobes, `last`, and five user bits, for 150 bits; using a fixed 32-bit logic type would violate the payload contract even if it compiled.

3. `rtl/src/axi_fifo.sv:85`, `...i_ar_fifo`: `.DEPTH(Depth + 1)` means six AR entries for the configured five-entry stage, while AW, W, R and B use `.DEPTH(Depth)`. This expression is legal SystemVerilog and cannot be dismissed because type/member fixes or a compiler pass succeed. The explicit contract requires exactly Depth entries on all channels. Restore `.DEPTH(Depth)` for AR. Both 5 and 6 are legal FIFO depths; no argument about independent AXI channels overrides this integration's exact capacity requirement. This does not affect the Depth=0 bypass, which skips the entire FIFO branch.

4. `integration.sv`, `i_boundary_monitor`: `axi_boundary_monitor` is intentionally absent. Report it as an unavailable external monitor definition blocking complete top elaboration/monitor checks. The local source issues above are independently repairable without its implementation. Do not invent a stub, claim this supplied RTL slice implements it, treat its absence as evidence the AXI functional implementation is incorrect, or claim full sign-off after only the local fixes.

Useful local checks: Depth=0 assigns the entire request and response directly; positive-depth forwarding preserves the configured channel type parameters after the fixes. Neither compile acceptance nor these source checks prove arbitrary external monitor behavior or complete AXI correctness.

## Eight scoring criteria (one point each)

Accept ordinary prose, equivalent identifier references and technically equivalent minimal repairs. Per criterion: 1 = complete/correct; 0.5 = materially correct but missing a required location, explanation, or correction; 0 = absent or contradicted. Do not award a reason/repair criterion for a proposed change that violates the stated interface or configuration. Record the eight scores separately and sum /8; do not replace source review with diagnostic-string matching.

| ID | Full-credit evidence |
| --- | --- |
| A1 | Identifies nonexistent AW request member `aw_valid_en`, locating the AW FIFO push expression in `axi_fifo`/the buffered instance. |
| A2 | Explains macro-generated `link_req_t` has `aw_valid`; proposes the `aw_valid` replacement while preserving valid-and-ready push logic. |
| A3 | Identifies value `Depth` passed as W FIFO's `dtype`, locating `.dtype(Depth)` in `i_w_fifo`. |
| A4 | Explains value-versus-type mismatch and restores `w_chan_t` to preserve the complete W payload. Exact bit count is optional. |
| A5 | Identifies the legal-but-wrong AR capacity `Depth+1`, locating `i_ar_fifo`, and states six versus required five for this integration. |
| A6 | Explains why compiler acceptance does not satisfy the all-channel capacity contract and proposes `.DEPTH(Depth)` without changing other stage configuration or bypass. |
| A7 | Calibrates intentionally unavailable `axi_boundary_monitor` separately from repairable local faults; no invented stub or claim of full monitor/top verification. |
| A8 | Gives a coherent engineering disposition: local fragment does not meet the supplied contract; the concrete repairs are sufficient for the identified local findings, full integration sign-off remains conditional on the external boundary; no unsupported definite extra fault or upstream-bug claim. |

Additional concerns may be credited as cautious investigation suggestions when supported by source, without requiring them. Do not penalize a justified caveat as a false positive. A definite unsupported assertion that changes the disposition prevents A8 full credit. No finding-count target, diagnosis categories, or locations appear in the worker task.
