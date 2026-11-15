# idma_review — independent source-derived oracle

Status: exploratory, seeded benchmark mutations; not upstream bug claims. Written from source and explicit requirements before compiler corroboration or follow-up outcomes. Paths below are relative to the worker workspace. Line numbers are aids; equivalent symbol/hierarchy references are acceptable.

The integration package defines a packed lane of 13 bits (payload 8, tag 4, poison 1) and a packed array of three lanes, `beat_t` (39 bits). `i_dataflow` generates three lane FIFOs with `BufferDepth=5`, `byte_t=lane_t`; `i_packet_fifo` uses `Depth=5`, `FallThrough=1`, `data_t=beat_t`. Packet clear and flush are separate top inputs connected to `cc_stream_fifo` and then `cc_fifo`.

## Source findings and minimal corrections

1. `rtl/src/backend/idma_dataflow_element.sv:47`, `compare_idma_state.i_dataflow.gen_fifo_buffer[i].i_passthrough_stream_fifo`: named connection `.ready_out(ready_o[i])` does not match the declared `ready_o` output in `cc_passthrough_stream_fifo` (under `rtl/.bender/git/checkouts/common_cells-b5ef1d9e9e7e3ce8/src/`). This causes a local module-interface compile error for generated lane instances. Restore `.ready_o(ready_o[i])`; do not rename the library's interface or change aggregate top `ready_o`. Each lane's output-ready notification must reach `lane_ready`, whose reduction AND drives top readiness. Repeated generated diagnostics are one root cause, not separate issues.

2. `rtl/.bender/git/checkouts/common_cells-b5ef1d9e9e7e3ce8/src/cc_stream_fifo.sv:54`, `compare_idma_state.i_packet_fifo.fifo_i`: `.data_t(DataWidth)` passes unsigned integer value parameter `DataWidth` to `cc_fifo`'s type parameter `data_t`. That value is not a SystemVerilog type. Restore `.data_t(data_t)` to propagate the caller's complete `beat_t` type into storage. `DataWidth` remains the wrapper's default 32 here, whereas the supplied `data_t` is a 39-bit beat. Replacing the type argument with `logic [DataWidth-1:0]` would compile but truncate payload relative to the contract. This error is independent of the lane named-port error.

3. `rtl/.bender/git/checkouts/common_cells-b5ef1d9e9e7e3ce8/src/cc_fifo.sv:126`, `...i_packet_fifo.fifo_i`: the `FFLARNC` for payload `mem_q` takes `clr_or_flush` as its synchronous clear. The earlier assignment defines `clr_or_flush = clr_i || flush_i`; pointer and occupancy flops should use it, but payload storage must clear on `clr_i` only. In `include/common_cells/registers.svh`, `FFLARNC` gives synchronous clear priority over load. Thus with reset inactive, clear low, flush high and no push/pop, the mutated memory register is set to all zero payload rather than holding its prior bits. This violates the explicit storage preservation requirement even if the queued data becomes invalid. Minimal repair: change only the payload macro's clear argument from `clr_or_flush` to `clr_i`, retaining `clr_or_flush` for read/write pointers and occupancy. The memory macro remains enabled by `!gate_clock`, preserving ordinary writes; clear remains independent of load. This is legal, synthesizable SystemVerilog and cannot be settled by compiler success alone.

4. `integration.sv`, `i_boundary_monitor`: `idma_boundary_monitor` is intentionally absent. Report it as unavailable external monitor definition preventing complete top elaboration/monitor checks. The local source issues above are independently repairable. Do not invent a stub, count the boundary absence as a seeded functional defect, or claim full integration sign-off after local repairs.

The oracle does not assert unseen simulation outcomes, complete DMA behavior, or physical/netlist connectivity. The flush reasoning follows directly from the clear expression and macro priority, with a concrete no-transfer counterexample. Reset clearing storage and explicit clear clearing storage remain allowed. The task deliberately distinguishes memory contents from whether contents are currently valid in the queue.

## Eight scoring criteria (one point each)

Accept ordinary prose, equivalent identifier references and technically equivalent minimal repairs. Per criterion: 1 = complete/correct; 0.5 = materially correct but missing a required location, explanation, or correction; 0 = absent or contradicted. Do not award a reason/repair criterion for a proposed change that violates the stated interface or configuration. Record the eight scores separately and sum /8; do not replace source review with diagnostic-string matching.

| ID | Full-credit evidence |
| --- | --- |
| I1 | Identifies nonexistent named port `ready_out`, locating the generated `cc_passthrough_stream_fifo` instance in `idma_dataflow_element`. |
| I2 | Explains the callee declares `ready_o` and restores `.ready_o(ready_o[i])`, preserving lane readiness wiring; repeated lane diagnostics are one root cause. |
| I3 | Identifies `DataWidth` value passed as `cc_fifo.data_t`, locating `.data_t(DataWidth)` in `cc_stream_fifo`/the packet FIFO instance. |
| I4 | Explains value-versus-type mismatch and proposes `.data_t(data_t)` to preserve the full caller beat type; no reduction to fixed 32-bit payload. Exact bit count is optional. |
| I5 | Identifies payload clear on flush, locating `mem_q`'s `FFLARNC` clear argument `clr_or_flush` in `cc_fifo`. |
| I6 | Explains clear priority/flush counterexample and repairs only payload clear to `clr_i`, retaining pointer/count flush behavior; explicitly recognizes this as a contract violation beyond compiler diagnostics. |
| I7 | Calibrates intentionally unavailable `idma_boundary_monitor` separately from repairable local faults; no invented stub or claim of full monitor/top verification. |
| I8 | Gives a coherent engineering disposition: local fragment does not meet the supplied contract; concrete repairs address identified local findings, full integration sign-off remains conditional on the external boundary; no unsupported definite extra fault or upstream-bug claim. |

Additional concerns may be credited as cautious investigation suggestions when supported by source, without requiring them. Do not penalize a justified caveat as a false positive. A definite unsupported assertion that changes the disposition prevents I8 full credit. No finding-count target, diagnosis categories, or locations appear in the worker task.
