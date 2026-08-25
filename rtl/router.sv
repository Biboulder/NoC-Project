import router_pkg::*;

module router (
    input logic clk,
    input logic rst_n,

    input logic valid_in_n, valid_in_s, valid_in_e, valid_in_w, valid_in_l,
    input packet_t pkt_in_n, pkt_in_s, pkt_in_e, pkt_in_w, pkt_in_l,

    output logic valid_out_n, valid_out_s, valid_out_e, valid_out_w, valid_out_l,
    output packet_t pkt_out_n, pkt_out_s, pkt_out_e, pkt_out_w, pkt_out_l
    );

    // buffer
    logic buf_valid[5];  // 0=N, 1=S, 2=E, 3=W, 4=L
    packet_t buf_pkt[5];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < 5; i++) begin
                buf_valid[i] <= 1'b0;
                buf_pkt[i] <= '0;
            end
        end else begin
            buf_valid[0] <= valid_in_n; buf_pkt[0] <= pkt_in_n;
            buf_valid[1] <= valid_in_s; buf_pkt[1] <= pkt_in_s;
            buf_valid[2] <= valid_in_e; buf_pkt[2] <= pkt_in_e;
            buf_valid[3] <= valid_in_w; buf_pkt[3] <= pkt_in_w;
            buf_valid[4] <= valid_in_l; buf_pkt[4] <= pkt_in_l;
        end
    end

    // decode
    logic dec_valid[5];
    direction_e dec_port[5];
    packet_t dec_pkt[5];

    generate
        for (genvar gi = 0; gi < 5; gi++) begin : decode_gen
            direction_decode u_decode (
                .valid_in (buf_valid[gi]),
                .pkt_in   (buf_pkt[gi]),
                .valid_out(dec_valid[gi]),
                .out_port (dec_port[gi]),
                .pkt_out  (dec_pkt[gi])
            );
        end
    endgenerate

    // crossbar
    always_comb begin
        valid_out_n = 1'b0; pkt_out_n = '0;
        valid_out_s = 1'b0; pkt_out_s = '0;
        valid_out_e = 1'b0; pkt_out_e = '0;
        valid_out_w = 1'b0; pkt_out_w = '0;
        valid_out_l = 1'b0; pkt_out_l = '0;

        for (int i = 0; i < 5; i++) begin
            if (dec_valid[i]) begin
                case (dec_port[i])
                    NORTH: begin valid_out_n = 1'b1; pkt_out_n = dec_pkt[i]; end
                    SOUTH: begin valid_out_s = 1'b1; pkt_out_s = dec_pkt[i]; end
                    EAST:  begin valid_out_e = 1'b1; pkt_out_e = dec_pkt[i]; end
                    WEST:  begin valid_out_w = 1'b1; pkt_out_w = dec_pkt[i]; end
                    LOCAL: begin valid_out_l = 1'b1; pkt_out_l = dec_pkt[i]; end
                endcase
            end
        end
    end

endmodule