package widths;
 typedef logic [8:0] payload_t;
 typedef enum logic [1:0] {IDLE=0, RUN=2, DONE=3} state_t;
endpackage
module unit #(parameter int WIDTH=5)(input logic [WIDTH-1:0] data);
 localparam int DOUBLE=2*WIDTH;
 logic [DOUBLE-1:0] wide;
endmodule
module top;
 parameter int BASE=7;
 widths::payload_t payload;
 widths::state_t state;
 logic [BASE+2:0] bus;
 unit #(.WIDTH(BASE+3)) u_unit(.data(bus));
endmodule
