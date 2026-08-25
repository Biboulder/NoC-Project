import router_pkg::*;

module mesh #(
    parameter int SIDE = 3
) (
    input logic clk,
    input logic rst_n,

    input logic [SIDE*SIDE-1:0] valid_in_l,
    input logic [SIDE*SIDE-1:0][PACKET_WIDTH-1:0] pkt_in_l,
    output logic [SIDE*SIDE-1:0] valid_out_l,
    output logic [SIDE*SIDE-1:0][PACKET_WIDTH-1:0] pkt_out_l
);

    logic out_n_valid [SIDE][SIDE], out_s_valid [SIDE][SIDE];
    logic out_e_valid [SIDE][SIDE], out_w_valid [SIDE][SIDE];
    packet_t out_n_pkt [SIDE][SIDE], out_s_pkt [SIDE][SIDE];
    packet_t out_e_pkt [SIDE][SIDE], out_w_pkt [SIDE][SIDE];

    generate
        for (genvar r = 0; r < SIDE; r++) begin : row_gen
            for (genvar c = 0; c < SIDE; c++) begin : col_gen

                localparam int IDX = r * SIDE + c;

                logic in_n_valid, in_s_valid, in_w_valid, in_e_valid;
                packet_t in_n_pkt, in_s_pkt, in_w_pkt, in_e_pkt;

                if (r == 0) begin : north_boundary
                    assign in_n_valid = 1'b0;
                    assign in_n_pkt = '0;
                end else begin : north_interior
                    assign in_n_valid = out_s_valid[r-1][c];
                    assign in_n_pkt = out_s_pkt[r-1][c];
                end

                if (r == SIDE-1) begin : south_boundary
                    assign in_s_valid = 1'b0;
                    assign in_s_pkt = '0;
                end else begin : south_interior
                    assign in_s_valid = out_n_valid[r+1][c];
                    assign in_s_pkt = out_n_pkt[r+1][c];
                end

                if (c == 0) begin : west_boundary
                    assign in_w_valid = 1'b0;
                    assign in_w_pkt = '0;
                end else begin : west_interior
                    assign in_w_valid = out_e_valid[r][c-1];
                    assign in_w_pkt = out_e_pkt[r][c-1];
                end

                if (c == SIDE-1) begin : east_boundary
                    assign in_e_valid = 1'b0;
                    assign in_e_pkt = '0;
                end else begin : east_interior
                    assign in_e_valid = out_w_valid[r][c+1];
                    assign in_e_pkt = out_w_pkt[r][c+1];
                end

                router u_router (
                    .clk(clk), .rst_n(rst_n),

                    .valid_in_n(in_n_valid), .pkt_in_n(in_n_pkt),
                    .valid_in_s(in_s_valid), .pkt_in_s(in_s_pkt),
                    .valid_in_w(in_w_valid), .pkt_in_w(in_w_pkt),
                    .valid_in_e(in_e_valid), .pkt_in_e(in_e_pkt),

                    .valid_in_l(valid_in_l[IDX]),
                    .pkt_in_l(pkt_in_l[IDX]),

                    .valid_out_n(out_n_valid[r][c]), .pkt_out_n(out_n_pkt[r][c]),
                    .valid_out_s(out_s_valid[r][c]), .pkt_out_s(out_s_pkt[r][c]),
                    .valid_out_w(out_w_valid[r][c]), .pkt_out_w(out_w_pkt[r][c]),
                    .valid_out_e(out_e_valid[r][c]), .pkt_out_e(out_e_pkt[r][c]),

                    .valid_out_l(valid_out_l[IDX]),
                    .pkt_out_l(pkt_out_l[IDX])
                );

            end
        end
    endgenerate

endmodule