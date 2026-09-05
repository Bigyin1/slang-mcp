`include "width.svh"
module top;
 logic [`BUS_WIDTH-1:0] bus;
`ifdef FEATURE
 logic feature_enabled;
`else
 logic feature_disabled;
`endif
`ifdef FAST
 localparam int LATENCY=1;
`else
 localparam int LATENCY=3;
`endif
endmodule
