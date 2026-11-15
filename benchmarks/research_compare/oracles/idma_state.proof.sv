module idma_state_proof;
  import compare_idma_state_pkg::*;
  compare_idma_state dut (
    .clk_i(1'b0), .rst_ni(1'b0), .clear_packet_i(1'b0), .flush_packet_i(1'b0),
    .data_i('0), .valid_i(1'b0), .ready_o(),
    .data_o(), .valid_o(), .ready_i(1'b0), .packet_usage_o()
  );
  initial begin
    assert ($bits(lane_t) == 13) else $fatal;
    assert ($bits(dut.i_dataflow.data_i) == 39) else $fatal;
    assert ($bits(dut.i_dataflow.gen_fifo_buffer[0].i_passthrough_stream_fifo.data_q) == 65) else $fatal;
    assert ($bits(dut.i_dataflow.gen_fifo_buffer[0].i_passthrough_stream_fifo.read_ptr_q) == 4) else $fatal;
    assert ($bits(dut.i_dataflow.gen_fifo_buffer[0].i_passthrough_stream_fifo.write_ptr_q) == 4) else $fatal;
    assert ($bits(dut.i_dataflow.gen_fifo_buffer[1].i_passthrough_stream_fifo.data_q) == 65) else $fatal;
    assert ($bits(dut.i_dataflow.gen_fifo_buffer[2].i_passthrough_stream_fifo.data_q) == 65) else $fatal;
    assert ($bits(dut.i_packet_fifo.fifo_i.mem_q) == 195) else $fatal;
    assert ($bits(dut.i_packet_fifo.fifo_i.status_cnt_q) == 3) else $fatal;
    assert ($bits(dut.i_packet_fifo.fifo_i.usage_o) == 3) else $fatal;
    assert (dut.i_packet_fifo.fifo_i.DataWidth == 32) else $fatal;
    assert (dut.i_packet_fifo.fifo_i.Depth == 5) else $fatal;
    assert (dut.i_packet_fifo.fifo_i.PtrWidth == 3) else $fatal;
    $display("PASS IDMA packed storage, generated lanes, pointer/count widths and defaults");
    $finish;
  end
endmodule
