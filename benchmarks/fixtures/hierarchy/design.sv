module worker; endmodule
module spare; endmodule
module branch; worker u_leaf(); endmodule
module top;
 parameter int N=4;
 worker u_direct();
 branch u_branch();
 worker u_array[2:0]();
 for (genvar i=0;i<N;i++) begin: lanes
   worker u_worker();
 end
 if (N>2) begin: enabled
   branch u_selected();
 end else begin: disabled
   spare u_selected();
 end
endmodule
