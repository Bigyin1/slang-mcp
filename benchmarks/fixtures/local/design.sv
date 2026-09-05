module top(input logic clk, rst_n, load, enable, a, b, mask, input logic [3:0] data, output logic [3:0] count_q, output logic fire);
 // count_q holds its value when enable is low and load is low.
 always_ff @(posedge clk or negedge rst_n)
   if (!rst_n) count_q <= 0;
   else if (load) count_q <= data;
   else if (enable) count_q <= count_q + 1'b1;
 assign fire=(a || b) && !mask;
endmodule
