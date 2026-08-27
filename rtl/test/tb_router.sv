`timescale 1ns/1ps

import router_pkg::*;
`include "rtl/test/tb_pkt_helpers.svh"

module tb_router;

logic clk = 0;
logic rst_n;

logic valid_in_n, valid_in_s, valid_in_e, valid_in_w, valid_in_l;
packet_t pkt_in_n, pkt_in_s, pkt_in_e, pkt_in_w, pkt_in_l;

logic valid_out_n, valid_out_s, valid_out_e, valid_out_w, valid_out_l;
packet_t pkt_out_n, pkt_out_s, pkt_out_e, pkt_out_w, pkt_out_l;

router dut (.*);

always #5 clk = ~clk;   // 10ns period

int errors = 0;

task automatic clear_inputs();
    valid_in_n = 0; valid_in_s = 0; valid_in_e = 0; valid_in_w = 0; valid_in_l = 0;
    pkt_in_n = '0; pkt_in_s = '0; pkt_in_e = '0; pkt_in_w = '0; pkt_in_l = '0;
endtask

task automatic check_one(input string label, input string port_name,
                            input logic act_valid, input packet_t act_pkt,
                            input logic exp_valid, input packet_t exp_pkt);
    if (act_valid !== exp_valid || (exp_valid && act_pkt !== exp_pkt)) begin
    $display("FAIL %s [%s]: valid=%0d pkt=%h (expected valid=%0d pkt=%h)",
                label, port_name, act_valid, act_pkt, exp_valid, exp_pkt);
    errors++;
    end
endtask

task automatic check_all(input string label,
    input logic ev_n, input packet_t ep_n,
    input logic ev_s, input packet_t ep_s,
    input logic ev_e, input packet_t ep_e,
    input logic ev_w, input packet_t ep_w,
    input logic ev_l, input packet_t ep_l);
    check_one(label, "N", valid_out_n, pkt_out_n, ev_n, ep_n);
    check_one(label, "S", valid_out_s, pkt_out_s, ev_s, ep_s);
    check_one(label, "E", valid_out_e, pkt_out_e, ev_e, ep_e);
    check_one(label, "W", valid_out_w, pkt_out_w, ev_w, ep_w);
    check_one(label, "L", valid_out_l, pkt_out_l, ev_l, ep_l);
endtask

initial begin
    // ---- Reset ----
    rst_n = 0;
    clear_inputs();
    repeat (2) @(negedge clk);
    rst_n = 1;
    @(posedge clk); #1;
    check_all("after_reset", 0,'0, 0,'0, 0,'0, 0,'0, 0,'0);

    // ---- Test 1: inject at Local, header NORTH,EAST -> exits North, shifted ----
    @(negedge clk);
    valid_in_l = 1;
    pkt_in_l   = make_packet(NORTH, EAST, LOCAL, LOCAL, 32'hDEADBEEF);
    @(posedge clk); #1;
    check_all("local_to_north",
    1, make_packet(EAST, LOCAL, LOCAL, LOCAL, 32'hDEADBEEF),
    0, '0, 0, '0, 0, '0, 0, '0);

    // ---- Test 2: inject at West, header EAST -> exits East (pass-through) ----
    @(negedge clk);
    clear_inputs();
    valid_in_w = 1;
    pkt_in_w   = make_packet(EAST, LOCAL, LOCAL, LOCAL, 32'hCAFEF00D);
    @(posedge clk); #1;
    check_all("west_to_east",
    0, '0, 0, '0,
    1, make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'hCAFEF00D),
    0, '0, 0, '0);

    // ---- Test 3: inject at North, fully-nulled header -> arrival at Local ----
    @(negedge clk);
    clear_inputs();
    valid_in_n = 1;
    pkt_in_n   = make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'h11112222);
    @(posedge clk); #1;
    check_all("arrived_at_local",
    0, '0, 0, '0, 0, '0, 0, '0,
    1, make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'h11112222));

    // ---- Test 4: simultaneous packets on N and E, different targets (no contention) ----
    @(negedge clk);
    clear_inputs();
    valid_in_n = 1; pkt_in_n = make_packet(SOUTH, LOCAL, LOCAL, LOCAL, 32'hAAAA0001);
    valid_in_e = 1; pkt_in_e = make_packet(WEST,  LOCAL, LOCAL, LOCAL, 32'hAAAA0002);
    @(posedge clk); #1;
    check_all("simultaneous_two_packets",
    0, '0,
    1, make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'hAAAA0001),
    0, '0,
    1, make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'hAAAA0002),
    0, '0);

    @(negedge clk);
    clear_inputs();

    if (errors > 0) begin
    $display("FAIL: tb_router, %0d check(s) failed", errors);
    $fatal;
    end
    $display("PASS: tb_router");
    $finish;
end

endmodule
