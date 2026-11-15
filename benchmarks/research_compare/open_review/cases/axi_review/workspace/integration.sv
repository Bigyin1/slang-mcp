// Review-fixture integration. External boundary monitor is supplied by the system owner.
`include "axi/typedef.svh"

package compare_axi_types_pkg;
  localparam int unsigned AddrWidth = 37;
  localparam int unsigned DataWidth = 128;
  localparam int unsigned IdWidth = 6;
  localparam int unsigned UserWidth = 5;
  typedef logic [AddrWidth-1:0] addr_t;
  typedef logic [DataWidth-1:0] data_t;
  typedef logic [IdWidth-1:0] id_t;
  typedef logic [UserWidth-1:0] user_t;
  typedef logic [DataWidth/8-1:0] strb_t;
  `AXI_TYPEDEF_ALL(link, addr_t, id_t, data_t, strb_t, user_t)
endpackage

module compare_axi_types (
  input logic clk_i,
  input logic rst_ni,
  input logic test_i,
  input compare_axi_types_pkg::link_req_t req_i,
  output compare_axi_types_pkg::link_resp_t resp_o,
  output compare_axi_types_pkg::link_req_t req_o,
  input compare_axi_types_pkg::link_resp_t resp_i
);
  import compare_axi_types_pkg::*;
  link_req_t buffered_req;
  link_resp_t buffered_resp;

  axi_fifo #(
    .Depth(5), .FallThrough(1'b1),
    .aw_chan_t(link_aw_chan_t), .w_chan_t(link_w_chan_t),
    .b_chan_t(link_b_chan_t), .ar_chan_t(link_ar_chan_t),
    .r_chan_t(link_r_chan_t), .axi_req_t(link_req_t), .axi_resp_t(link_resp_t)
  ) i_buffer (
    .clk_i, .rst_ni, .test_i,
    .slv_req_i(req_i), .slv_resp_o(resp_o),
    .mst_req_o(buffered_req), .mst_resp_i(buffered_resp)
  );

  axi_fifo #(
    .Depth(0),
    .aw_chan_t(link_aw_chan_t), .w_chan_t(link_w_chan_t),
    .b_chan_t(link_b_chan_t), .ar_chan_t(link_ar_chan_t),
    .r_chan_t(link_r_chan_t), .axi_req_t(link_req_t), .axi_resp_t(link_resp_t)
  ) i_wire (
    .clk_i, .rst_ni, .test_i,
    .slv_req_i(buffered_req), .slv_resp_o(buffered_resp),
    .mst_req_o(req_o), .mst_resp_i(resp_i)
  );
  axi_boundary_monitor i_boundary_monitor (.clk_i, .rst_ni);
endmodule
