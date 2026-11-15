module broken_fragment_top #(
  parameter int unsigned W = 12
) (
  input logic clk_i,
  input logic rst_ni,
  input logic [W-1:0] data_i,
  output logic [3:0] narrow_o,
  output logic invalid_member_o,
  output logic [W-1:0] external_o
);
  typedef struct packed {
    logic [W-1:0] payload;
    logic valid;
  } sample_t;

  sample_t sample;
  logic [3:0] narrow_q;

  assign sample.payload = data_i;
  assign sample.valid = 1'b1;
  assign invalid_member_o = sample.missing;
  assign narrow_o = narrow_q;

  always_ff @(posedge clk_i) begin
    if (!rst_ni)
      narrow_q <= '0;
    else
      narrow_q <= data_i;
  end

  external_stage #(.W(W)) u_external (
    .clk_i(clk_i),
    .data_i(data_i),
    .data_o(external_o)
  );
endmodule
