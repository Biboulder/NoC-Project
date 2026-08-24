package router_pkg;

  typedef enum logic [2:0] {
    LOCAL = 3'b000,
    NORTH = 3'b001,
    SOUTH = 3'b010,
    EAST = 3'b011,
    WEST = 3'b100
  } direction_e;

  localparam int HEADER = 12;
  localparam int PAYLOAD = 32;
  localparam int PACKET_WIDTH = HEADER + PAYLOAD;

  typedef logic [PACKET_WIDTH-1:0] packet_t;

endpackage