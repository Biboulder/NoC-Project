import router_pkg::*;

module direction_decode (
    input  logic valid_in,
    input  packet_t pkt_in,
    output logic valid_out,
    output port_e out_port,
    output packet_t pkt_out
);

    // Unpack struct fields outside the always_comb block: iverilog cannot
    // track constant selects (struct members) in always_* sensitivity lists
    // and would emit "sorry: constant selects ..." warnings otherwise.
    wire logic [3:0] x_count = pkt_in.x_count;
    wire logic [3:0] y_count = pkt_in.y_count;
    wire x_dir_e x_dir = pkt_in.x_dir;
    wire y_dir_e y_dir = pkt_in.y_dir;

    always_comb begin
        pkt_out = pkt_in;
        out_port = PORT_L;
        valid_out = valid_in;

        if (x_count != 4'd0) begin
        if (x_dir == EAST) begin
            out_port = PORT_E;
        end else begin
            out_port = PORT_W;
        end
        pkt_out.x_count = x_count - 4'd1;
        end
        else if (y_count != 4'd0) begin
        if (y_dir == NORTH) begin
            out_port = PORT_N;
        end else begin
            out_port = PORT_S;
        end
        pkt_out.y_count = y_count - 4'd1;
        end
        else begin
        out_port = PORT_L;
        end
    end

endmodule
