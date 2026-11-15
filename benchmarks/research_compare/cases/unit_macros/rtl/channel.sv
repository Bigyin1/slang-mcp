`include "settings.svh"
`undef WORD_W
`define WORD_W 13

module channel #(
  parameter int unsigned W = `WORD_W
) (
  input unit_word_t unit_i,
  input logic [W-1:0] payload_i,
  output logic [W-1:0] payload_o
);
  assign payload_o = payload_i ^ {{(W-$bits(unit_word_t)){1'b0}}, unit_i};
endmodule
