import router_pkg::*;

module direction_decode (
    input  logic valid_in,
    input  packet_t pkt_in,
    output logic valid_out,
    output direction_e out_port,
    output packet_t pkt_out
);

    logic [11:0] header, header_shifted;

    assign header = pkt_in[43:32];
    assign out_port = direction_e'(header[11:9]);
    assign header_shifted = {header[8:0], 3'b000};   // consume field, zero-fill tail

    always_comb begin
        valid_out = valid_in;
        pkt_out = {header_shifted, pkt_in[31:0]};
    end

endmodule
