package router_pkg;

    typedef enum logic [2:0] {
        PORT_N = 3'd0,
        PORT_E = 3'd1,
        PORT_S = 3'd2,
        PORT_W = 3'd3,
        PORT_L = 3'd4
    } port_e;

    typedef enum logic {
        EAST = 1'b0,
        WEST = 1'b1
    } x_dir_e;

    typedef enum logic {
        NORTH = 1'b0,
        SOUTH = 1'b1
    } y_dir_e;

    typedef struct packed {
        logic [31:0] payload;
        x_dir_e x_dir;
        logic [3:0] x_count;
        y_dir_e y_dir;
        logic [3:0] y_count;
    } packet;

endpackage
