import router_pkg::*;

module direction_decode (
    input  logic valid_in,
    input  packet_t pkt_in,
    output logic valid_out,
    output port_e out_port,
    output packet_t pkt_out
);

    always_comb begin
        pkt_out = pkt_in;
        out_port = PORT_L;
        valid_out = valid_in;

        if (pkt_in.x_count != 0) begin
        out_port = (pkt_in.x_dir == EAST) ? PORT_E : PORT_W;
        pkt_out.x_count = pkt_in.x_count - 1;
        end
        else if (pkt_in.y_count != 0) begin
        out_port = (pkt_in.y_dir == NORTH) ? PORT_N : PORT_S;
        pkt_out.y_count = pkt_in.y_count - 1;
        end
        else begin
        out_port = PORT_L;
        end
    end

endmodule