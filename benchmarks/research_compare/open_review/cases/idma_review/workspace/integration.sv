// Review-fixture integration. External boundary monitor is supplied by the system owner.
package compare_idma_state_pkg;
  typedef struct packed {
    logic [7:0] payload;
    logic [3:0] tag;
    logic poison;
  } lane_t;
  typedef lane_t [2:0] beat_t;
endpackage

module compare_idma_state (
  input logic clk_i,
  input logic rst_ni,
  input logic clear_packet_i,
  input logic flush_packet_i,
  input compare_idma_state_pkg::beat_t data_i,
  input logic valid_i,
  output logic ready_o,
  output compare_idma_state_pkg::beat_t data_o,
  output logic valid_o,
  input logic ready_i,
  output logic [2:0] packet_usage_o
);
  import compare_idma_state_pkg::*;
  beat_t lane_data;
  logic [2:0] lane_valid, lane_ready;
  logic packet_ready;

  assign ready_o = &lane_ready;

  idma_dataflow_element #(
    .BufferDepth(5), .StrbWidth(3), .strb_t(logic [2:0]), .byte_t(lane_t)
  ) i_dataflow (
    .clk_i, .rst_ni, .data_i,
    .valid_i({3{valid_i}}), .ready_o(lane_ready),
    .data_o(lane_data), .valid_o(lane_valid), .ready_i({3{packet_ready}})
  );

  cc_stream_fifo #(
    .Depth(5), .FallThrough(1'b1), .data_t(beat_t)
  ) i_packet_fifo (
    .clk_i, .rst_ni, .clr_i(clear_packet_i), .flush_i(flush_packet_i),
    .usage_o(packet_usage_o), .data_i(lane_data), .valid_i(&lane_valid),
    .ready_o(packet_ready), .data_o, .valid_o, .ready_i
  );
  idma_boundary_monitor i_boundary_monitor (.clk_i, .rst_ni);
endmodule
