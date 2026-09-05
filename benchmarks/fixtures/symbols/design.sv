package data_pkg;
 typedef logic [11:0] word_t;
 parameter int LIMIT=7;
 function automatic int twice(input int x); return 2*x; endfunction
endpackage
module leaf; logic flag; endmodule
module top(input logic clk, input data_pkg::word_t value, output wire ready);
 wire link;
 logic stored;
 leaf left(); leaf right();
 function automatic int increment(input int x); return x+1; endfunction
 task automatic clear(output logic x); x=0; endtask
 if (1) begin: inner
   localparam int COUNT=3;
   logic nested;
 end
 assign ready=stored;
endmodule
