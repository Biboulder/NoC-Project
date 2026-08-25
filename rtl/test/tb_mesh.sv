import router_pkg::*;

// Testbench for a SIDE=3 mesh built from `mesh #(.SIDE(3))`.
//
// Node index = row*SIDE + col:
//   0=(0,0) 1=(0,1) 2=(0,2)
//   3=(1,0) 4=(1,1) 5=(1,2)
//   6=(2,0) 7=(2,1) 8=(2,2)
//
// Stimulus is driven on @(negedge clk), not @(posedge clk): changing
// valid_in_l/pkt_in_l in the same time step as the posedge that
// router.sv's own always_ff also triggers on is a genuine simulator
// race (which value the flop samples is scheduler-dependent -- Icarus
// and Verilator resolved it differently). Driving on the falling edge
// gives a full half-period of settling margin before the next rising
// edge samples it.
//
// Latency model: each router hop costs one clock cycle (input register
// stage + combinational decode/crossbar). A packet needing N real
// direction hops before a LOCAL decode (explicit or via automatic
// zero-padding) is observable on the destination's local output port
// N clock cycles after the deassert-negedge that ends the injection
// pulse (0 hops = check immediately after that negedge, no extra wait).
module tb_mesh;

    localparam int SIDE = 3;
    localparam int NNODES = SIDE * SIDE;

    logic clk = 0;
    logic rst_n;

    logic [NNODES-1:0]                   valid_in_l;
    logic [NNODES-1:0][PACKET_WIDTH-1:0] pkt_in_l;
    logic [NNODES-1:0]                   valid_out_l;
    logic [NNODES-1:0][PACKET_WIDTH-1:0] pkt_out_l;

    mesh #(.SIDE(SIDE)) dut (
        .clk(clk), .rst_n(rst_n),
        .valid_in_l(valid_in_l), .pkt_in_l(pkt_in_l),
        .valid_out_l(valid_out_l), .pkt_out_l(pkt_out_l)
    );

    always #5 clk = ~clk;

    int fail_count = 0;

    function automatic packet_t make_packet(
        direction_e d1, direction_e d2, direction_e d3, direction_e d4,
        logic [31:0] payload
    );
        logic [11:0] header;
        header = {d1, d2, d3, d4};
        return {header, payload};
    endfunction

    // Expected packet content after `hops` router traversals: the
    // header is left-shifted by 3 bits per hop with zero-fill, which
    // is equivalent to (header << 3*hops) truncated to 12 bits.
    function automatic packet_t expect_pkt(
        direction_e d1, direction_e d2, direction_e d3, direction_e d4,
        logic [31:0] payload, int hops
    );
        logic [11:0] header, shifted;
        header  = {d1, d2, d3, d4};
        shifted = (header << (3 * hops)) & 12'hFFF;
        return {shifted, payload};
    endfunction

    task automatic check(
        string name, int port,
        logic actual_valid, packet_t actual_pkt,
        logic exp_valid, packet_t exp_pkt
    );
        if (actual_valid !== exp_valid || (exp_valid && actual_pkt !== exp_pkt)) begin
            $display("FAIL %s [node%0d]: valid=%0d pkt=%h (expected valid=%0d pkt=%h)",
                      name, port, actual_valid, actual_pkt, exp_valid, exp_pkt);
            fail_count++;
        end
    endtask

    // Pulses valid_in_l[src]/pkt_in_l[src] for one clock period, timed
    // on negedges to avoid racing router.sv's posedge-triggered flops,
    // then waits (hops) further cycles before checking the dst output.
    task automatic inject_and_check(
        string name, int src, int dst, packet_t pkt, int hops,
        logic exp_valid, packet_t exp_pkt
    );
        @(negedge clk);
        valid_in_l[src] = 1'b1;
        pkt_in_l[src]   = pkt;
        @(negedge clk);
        valid_in_l[src] = 1'b0;
        pkt_in_l[src]   = '0;
        repeat (hops) @(negedge clk);
        check(name, dst, valid_out_l[dst], pkt_out_l[dst], exp_valid, exp_pkt);
    endtask

    initial begin
        rst_n = 0;
        valid_in_l = '0;
        pkt_in_l   = '0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        @(negedge clk);

        // 1. local_loopback: inject and deliver at the same node, 0 hops.
        inject_and_check(
            "local_loopback", 4, 4,
            make_packet(LOCAL, LOCAL, LOCAL, LOCAL, 32'h11112222), 0,
            1'b1, expect_pkt(LOCAL, LOCAL, LOCAL, LOCAL, 32'h11112222, 1)
        );

        // 2. one_hop_east: node0 -> node1, 1 hop.
        inject_and_check(
            "one_hop_east", 0, 1,
            make_packet(EAST, LOCAL, LOCAL, LOCAL, 32'hAAAA0001), 1,
            1'b1, expect_pkt(EAST, LOCAL, LOCAL, LOCAL, 32'hAAAA0001, 2)
        );

        // 3. one_hop_south: node0 -> node3, 1 hop.
        inject_and_check(
            "one_hop_south", 0, 3,
            make_packet(SOUTH, LOCAL, LOCAL, LOCAL, 32'hBBBB0002), 1,
            1'b1, expect_pkt(SOUTH, LOCAL, LOCAL, LOCAL, 32'hBBBB0002, 2)
        );

        // 4. two_hop_diag: node0 -E-> node1 -S-> node4, 2 hops.
        inject_and_check(
            "two_hop_diag", 0, 4,
            make_packet(EAST, SOUTH, LOCAL, LOCAL, 32'hCCCC0003), 2,
            1'b1, expect_pkt(EAST, SOUTH, LOCAL, LOCAL, 32'hCCCC0003, 3)
        );

        // 5. max_hops_corner_to_corner: node0 -E-> node1 -E-> node2
        //    -S-> node5 -S-> node8, 4 real hops, all fields used, no
        //    explicit LOCAL field. Delivery relies on the automatic
        //    zero-padded header decoding as LOCAL at node8.
        inject_and_check(
            "max_hops_corner_to_corner", 0, 8,
            make_packet(EAST, EAST, SOUTH, SOUTH, 32'hDEAD0004), 4,
            1'b1, expect_pkt(EAST, EAST, SOUTH, SOUTH, 32'hDEAD0004, 5)
        );

        // 6. simultaneous_independent_paths: two packets injected on
        //    the same cycle, on independent (non-conflicting) paths:
        //    node0 -E-> node1 -E-> node2 (top row)
        //    node8 -W-> node7 -W-> node6 (bottom row)
        @(negedge clk);
        valid_in_l[0] = 1'b1;
        pkt_in_l[0]   = make_packet(EAST, EAST, LOCAL, LOCAL, 32'hAAAA1111);
        valid_in_l[8] = 1'b1;
        pkt_in_l[8]   = make_packet(WEST, WEST, LOCAL, LOCAL, 32'hBBBB2222);
        @(negedge clk);
        valid_in_l[0] = 1'b0; pkt_in_l[0] = '0;
        valid_in_l[8] = 1'b0; pkt_in_l[8] = '0;
        repeat (2) @(negedge clk);
        check("simultaneous_independent_paths", 2,
              valid_out_l[2], pkt_out_l[2],
              1'b1, expect_pkt(EAST, EAST, LOCAL, LOCAL, 32'hAAAA1111, 3));
        check("simultaneous_independent_paths", 6,
              valid_out_l[6], pkt_out_l[6],
              1'b1, expect_pkt(WEST, WEST, LOCAL, LOCAL, 32'hBBBB2222, 3));

        if (fail_count == 0) begin
            $display("PASS: tb_mesh, all checks passed");
            $finish;
        end else begin
            $display("FAIL: tb_mesh, %0d check(s) failed", fail_count);
            $fatal(1);
        end
    end

endmodule