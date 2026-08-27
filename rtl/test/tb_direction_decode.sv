`timescale 1ns/1ps

import router_pkg::*;
`include "rtl/test/tb_pkt_helpers.svh"

module tb_direction_decode;

logic       valid_in;
packet_t    pkt_in;
logic       valid_out;
direction_e out_port;
packet_t    pkt_out;

direction_decode dut (
    .valid_in (valid_in),
    .pkt_in   (pkt_in),
    .valid_out(valid_out),
    .out_port (out_port),
    .pkt_out  (pkt_out)
);

int errors = 0;

task automatic check_port(input string label, input direction_e expected);
    if (out_port !== expected) begin
    $display("FAIL %s: out_port=%0d expected=%0d", label, out_port, expected);
    errors++;
    end
endtask

task automatic check_pkt(input string label, input packet_t expected);
    if (pkt_out !== expected) begin
    $display("FAIL %s: got header=%b payload=%h expected header=%b payload=%h",
                label, pkt_out[43:32], pkt_out[31:0], expected[43:32], expected[31:0]);
    errors++;
    end
endtask

initial begin
    // North -> East route: first hop North
    valid_in = 1'b1;
    pkt_in   = make_packet(NORTH, EAST, LOCAL, LOCAL, 32'hDEADBEEF);
    #10;
    check_port("north_first_hop", NORTH);
    check_pkt("north_first_hop", make_packet(EAST, LOCAL, LOCAL, LOCAL, 32'hDEADBEEF));

    // East -> South route
    pkt_in = make_packet(EAST, SOUTH, LOCAL, LOCAL, 32'h00000001);
    #10;
    check_port("east_first_hop", EAST);
    check_pkt("east_first_hop", make_packet(SOUTH, LOCAL, LOCAL, LOCAL, 32'h00000001));

    // South -> West route
    pkt_in = make_packet(SOUTH, WEST, LOCAL, LOCAL, 32'h00000002);
    #10;
    check_port("south_first_hop", SOUTH);
    check_pkt("south_first_hop", make_packet(WEST, LOCAL, LOCAL, LOCAL, 32'h00000002));

    // West -> North route
    pkt_in = make_packet(WEST, NORTH, LOCAL, LOCAL, 32'h00000003);
    #10;
    check_port("west_first_hop", WEST);
    check_pkt("west_first_hop", make_packet(NORTH, LOCAL, LOCAL, LOCAL, 32'h00000003));

    // Fully-nulled header -> LOCAL delivery, payload passes through unchanged
    pkt_in = make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'hCAFEF00D);
    #10;
    check_port("arrived", LOCAL);
    check_pkt("arrived", make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'hCAFEF00D));

    // Invalid input: valid_out must follow valid_in
    valid_in = 1'b0;
    pkt_in   = make_packet(NORTH, EAST, SOUTH, WEST, 32'h00000004);
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
