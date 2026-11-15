    fifo_v3 #(
        .dtype(aw_chan_t),
        .DEPTH(Depth),
        .FALL_THROUGH(FallThrough)
    ) i_aw_fifo (
        .clk_i,
        .rst_ni,
        .flush_i   (1'b0),
        .testmode_i(test_i),
        .full_o    (aw_fifo_full),
        .empty_o   (aw_fifo_empty),
        .usage_o   (),
        .data_i    (slv_req_i.aw),
        .push_i    (slv_req_i.aw_valid && slv_resp_o.aw_ready),
        .data_o    (mst_req_o.aw),
        .pop_i     (mst_req_o.aw_valid && mst_resp_i.aw_ready)
    );
