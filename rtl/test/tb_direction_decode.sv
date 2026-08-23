`timescale 1ns/1ps

import router_pkg::*;

module tb_direction_decode;

    logic    valid_in;
    packet_t pkt_in;
    logic    valid_out;
    port_e   out_port;
    packet_t pkt_out;

    direction_decode dut (
        .valid_in (valid_in),
        .pkt_in   (pkt_in),
        .valid_out(valid_out),
        .out_port (out_port),
        .pkt_out  (pkt_out)
    );

    int errors = 0;

    // Drive pkt_in field-by-field: iverilog 12 rejects named-member
    // assignment patterns like '{payload: ..., x_dir: ...}.
    task automatic drive(input logic [31:0] payload,
                         input x_dir_e xd, input logic [3:0] xc,
                         input y_dir_e yd, input logic [3:0] yc);
        pkt_in.payload = payload;
        pkt_in.x_dir   = xd;
        pkt_in.x_count = xc;
        pkt_in.y_dir   = yd;
        pkt_in.y_count = yc;
    endtask

    task automatic check_port(input string label, input port_e expected);
        if (out_port !== expected) begin
            $display("FAIL %s: out_port=%0d expected=%0d", label, out_port, expected);
            errors++;
        end
    endtask

    task automatic check_pkt(input string label,
                             input logic [31:0] payload,
                             input x_dir_e xd, input logic [3:0] xc,
                             input y_dir_e yd, input logic [3:0] yc);
        if (pkt_out.payload !== payload || pkt_out.x_dir !== xd ||
            pkt_out.x_count !== xc || pkt_out.y_dir !== yd ||
            pkt_out.y_count !== yc) begin
            $display("FAIL %s: got %h/%0d/%0d/%0d/%0d expected %h/%0d/%0d/%0d/%0d",
                     label, pkt_out.payload, pkt_out.x_dir, pkt_out.x_count,
                     pkt_out.y_dir, pkt_out.y_count, payload, xd, xc, yd, yc);
            errors++;
        end
    endtask

    initial begin
        // East hop: x_count decrements, output port E
        valid_in = 1'b1;
        drive(32'hDEADBEEF, EAST, 4'd1, NORTH, 4'd0);
        #10;
        check_port("east", PORT_E);
        check_pkt("east", 32'hDEADBEEF, EAST, 4'd0, NORTH, 4'd0);

        // West hop
        drive(32'h00000001, WEST, 4'd2, SOUTH, 4'd0);
        #10;
        check_port("west", PORT_W);
        check_pkt("west", 32'h00000001, WEST, 4'd1, SOUTH, 4'd0);

        // North hop once x is exhausted
        drive(32'h00000002, EAST, 4'd0, NORTH, 4'd3);
        #10;
        check_port("north", PORT_N);
        check_pkt("north", 32'h00000002, EAST, 4'd0, NORTH, 4'd2);

        // Local delivery when both counts are zero
        drive(32'h00000003, WEST, 4'd0, SOUTH, 4'd0);
        #10;
        check_port("local", PORT_L);
        check_pkt("local", 32'h00000003, WEST, 4'd0, SOUTH, 4'd0);

        // Invalid input: valid_out must follow valid_in
        valid_in = 1'b0;
        drive(32'h00000004, EAST, 4'd5, NORTH, 4'd5);
        #10;
        if (valid_out !== 1'b0) begin
            $display("FAIL valid_in passthrough: valid_out=%0d", valid_out);
            errors++;
        end

        if (errors > 0) begin
            $display("FAIL: tb_direction_decode, %0d check(s) failed", errors);
            $fatal;
        end
        $display("PASS: tb_direction_decode");
        $finish;
    end

endmodule
