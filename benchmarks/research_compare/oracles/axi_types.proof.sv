module axi_types_proof;
  import compare_axi_types_pkg::*;
  compare_axi_types dut (
    .clk_i(1'b0), .rst_ni(1'b0), .test_i(1'b0),
    .req_i('0), .resp_o(), .req_o(), .resp_i('0)
  );
  initial begin
    assert ($bits(link_aw_chan_t) == 83) else $fatal;
    assert ($bits(link_w_chan_t) == 150) else $fatal;
    assert ($bits(link_b_chan_t) == 13) else $fatal;
    assert ($bits(link_ar_chan_t) == 77) else $fatal;
    assert ($bits(link_r_chan_t) == 142) else $fatal;
    assert ($bits(link_req_t) == 315) else $fatal;
    assert ($bits(link_resp_t) == 160) else $fatal;
    assert ($bits(dut.i_buffer.gen_axi_fifo.i_aw_fifo.data_i) == 83) else $fatal;
    assert ($bits(dut.i_buffer.gen_axi_fifo.i_w_fifo.data_i) == 150) else $fatal;
    assert ($bits(dut.i_buffer.gen_axi_fifo.i_b_fifo.data_i) == 13) else $fatal;
    assert ($bits(dut.i_buffer.gen_axi_fifo.i_ar_fifo.data_i) == 77) else $fatal;
    assert ($bits(dut.i_buffer.gen_axi_fifo.i_r_fifo.data_i) == 142) else $fatal;
    assert (dut.i_buffer.gen_axi_fifo.i_aw_fifo.DEPTH == 5) else $fatal;
    assert (dut.i_buffer.gen_axi_fifo.i_aw_fifo.FALL_THROUGH == 1) else $fatal;
    assert (dut.i_buffer.gen_axi_fifo.i_aw_fifo.DATA_WIDTH == 32) else $fatal;
    assert (dut.i_wire.Depth == 0) else $fatal;
    assert (dut.i_wire.FallThrough == 0) else $fatal;
    $display("PASS AXI widths, formal widths, and concrete/default parameters");
    $finish;
  end
endmodule
