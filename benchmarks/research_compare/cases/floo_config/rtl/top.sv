// Benchmark integration fixture; upstream modules are supplied unmodified.
module floo_config_top;
  typedef struct packed {
    logic [12:0] payload;
    logic [7:0] tag;
    logic [1:0] flags;
  } flit_t;

  floo_fifo #(.NumChannels(3), .NumVirtChannels(4), .NumPhysChannels(1),
              .FifoDepth(5), .flit_t(flit_t)) u_virtual (
    .clk_i(1'b0), .rst_ni(1'b1), .test_enable_i(1'b0),
    .valid_i('0), .ready_o(), .data_i('0), .valid_o(), .ready_i('0), .data_o()
  );
  floo_fifo #(.NumChannels(2), .NumVirtChannels(3), .NumPhysChannels(3),
              .FifoDepth(2), .flit_t(flit_t)) u_physical (
    .clk_i(1'b0), .rst_ni(1'b1), .test_enable_i(1'b0),
    .valid_i('0), .ready_o(), .data_i('0), .valid_o(), .ready_i('0), .data_o()
  );
  floo_fifo #(.NumChannels(2), .NumVirtChannels(4), .NumPhysChannels(1),
              .FifoDepth(0), .flit_t(flit_t)) u_bypass (
    .clk_i(1'b0), .rst_ni(1'b1), .test_enable_i(1'b0),
    .valid_i('0), .ready_o(), .data_i('0), .valid_o(), .ready_i('0), .data_o()
  );
endmodule
