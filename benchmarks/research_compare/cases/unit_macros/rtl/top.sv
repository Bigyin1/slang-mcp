`include "settings.svh"
`undef LANES
`define LANES 3

module unit_macros_top #(
  parameter int unsigned W = `WORD_W,
  parameter int unsigned N = `LANES
) (
  input logic [W*N-1:0] data_i,
  input unit_word_t unit_i,
  output logic [W+1:0] data_o
);
  if (W > $bits(unit_word_t)) begin : g_wide
    channel #(.W(W+2)) u_channel (
      .unit_i(unit_i),
      .payload_i(data_i[W+1:0]),
      .payload_o(data_o)
    );
  end else begin : g_small
    assign data_o = '0;
  end
endmodule
