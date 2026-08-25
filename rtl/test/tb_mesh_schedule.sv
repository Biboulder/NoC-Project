import router_pkg::*;

// Integration test: drives the real `mesh` RTL according to the
// canonical (first-alternative) entries decoded from
// schedules/schedule_row.sched (3x3 grid, pack=row, frame=14 cycles,
// 20 injections), and checks that every scheduled (src, dst) packet
// actually arrives at the right node on the right cycle with no
// collisions.
//
// Node label -> local port index: schedule node K (1-based, row-major)
// = RTL index K-1 (node_id(n,x,y) = y*n + x + 1 in routing/grid.py,
// same row-major convention as this mesh's valid_in_l[row*3+col]).
//
// Latency model (matches tb_mesh.sv): a packet asserted during cycle
// `clk` (negedge-aligned pulse, one cycle wide) needing `hops` router
// traversals is observable at its destination's local output at cycle
// index (clk + 1 + hops).
//
// Local ports use packed arrays to match this repo's mesh.sv, which
// declares valid_in_l/pkt_in_l/valid_out_l/pkt_out_l as packed vectors
// (not unpacked array ports).
module tb_mesh_schedule;

    localparam int SIDE = 3;
    localparam int NNODES = SIDE * SIDE;
    localparam int NUM_ENTRIES = 20;
    localparam int NCYCLES = 20;  // frame=14 + margin to drain last arrivals

    logic clk = 0;
    logic rst_n;

    logic [NNODES-1:0]                   valid_in_l;
    packet_t [NNODES-1:0]                pkt_in_l;
    logic [NNODES-1:0]                   valid_out_l;
    packet_t [NNODES-1:0]                pkt_out_l;

    mesh #(.SIDE(SIDE)) dut (
        .clk(clk), .rst_n(rst_n),
        .valid_in_l(valid_in_l), .pkt_in_l(pkt_in_l),
        .valid_out_l(valid_out_l), .pkt_out_l(pkt_out_l)
    );

    always #5 clk = ~clk;

    function automatic packet_t make_packet(
        direction_e d1, direction_e d2, direction_e d3, direction_e d4,
        logic [31:0] payload
    );
        logic [11:0] header;
        header = {d1, d2, d3, d4};
        return {header, payload};
    endfunction

    function automatic packet_t expect_pkt(
        direction_e d1, direction_e d2, direction_e d3, direction_e d4,
        logic [31:0] payload, int hops
    );
        logic [11:0] header, shifted;
        header  = {d1, d2, d3, d4};
        shifted = (header << (3 * hops)) & 12'hFFF;
        return {shifted, payload};
    endfunction

    // Entry fields, decoded from schedules/schedule_row.sched (canonical
    // first alternative per row). src/dst are RTL indices (node label - 1).
    int src   [NUM_ENTRIES];
    int clk_c [NUM_ENTRIES];
    int dst   [NUM_ENTRIES];
    int hops  [NUM_ENTRIES];

    packet_t inject_pkt [NUM_ENTRIES];
    packet_t expect_pkt_arr [NUM_ENTRIES];
    int      arrive_cyc [NUM_ENTRIES];
    bit      matched     [NUM_ENTRIES];

    int fail_count = 0;

    task automatic def_entry(
        int idx, int s, int c, int d, int h,
        direction_e d1, direction_e d2, direction_e d3, direction_e d4
    );
        logic [31:0] payload;
        src[idx]   = s;
        clk_c[idx] = c;
        dst[idx]   = d;
        hops[idx]  = h;
        // Payload encodes (src_label, dst_label, clock) for traceability.
        payload = {8'((s+1) & 8'hFF), 8'((d+1) & 8'hFF), 8'(c & 8'hFF), 8'h00};
        inject_pkt[idx]     = make_packet(d1, d2, d3, d4, payload);
        expect_pkt_arr[idx] = expect_pkt(d1, d2, d3, d4, payload, h);
        arrive_cyc[idx]     = c + 1 + h;
        matched[idx]        = 1'b0;
    endtask

    initial begin
        // node1 (idx0)
        def_entry(0,  0, 0, 8, 4, EAST,  EAST,  SOUTH, SOUTH); // dest9 EESS
        def_entry(1,  0, 5, 7, 3, SOUTH, SOUTH, EAST,  LOCAL); // dest8 SSE
        // node2 (idx1)
        def_entry(2,  1, 0, 6, 3, WEST,  SOUTH, SOUTH, LOCAL); // dest7 WSS
        def_entry(3,  1, 5, 8, 3, EAST,  SOUTH, SOUTH, LOCAL); // dest9 ESS
        // node3 (idx2)
        def_entry(4,  2, 0, 6, 4, SOUTH, WEST,  WEST,  SOUTH); // dest7 SWWS
        def_entry(5,  2, 10, 1, 1, WEST, LOCAL, LOCAL, LOCAL); // dest2 W
        // node4 (idx3)
        def_entry(6,  3, 0, 8, 3, SOUTH, EAST,  EAST,  LOCAL); // dest9 SEE
        def_entry(7,  3, 5, 2, 3, EAST,  NORTH, EAST,  LOCAL); // dest3 ENE
        // node5 (idx4)
        def_entry(8,  4, 5, 0, 2, NORTH, WEST,  LOCAL, LOCAL); // dest1 NW
        def_entry(9,  4, 11, 8, 2, EAST, SOUTH, LOCAL, LOCAL); // dest9 ES
        // node6 (idx5)
        def_entry(10, 5, 0, 0, 3, NORTH, WEST,  WEST,  LOCAL); // dest1 NWW
        def_entry(11, 5, 5, 6, 3, SOUTH, WEST,  WEST,  LOCAL); // dest7 SWW
        def_entry(12, 5, 9, 4, 1, WEST, LOCAL, LOCAL, LOCAL);  // dest5 W
        // node7 (idx6)
        def_entry(13, 6, 0, 2, 4, NORTH, NORTH, EAST,  EAST);  // dest3 NNEE
        def_entry(14, 6, 5, 5, 3, EAST,  EAST,  NORTH, LOCAL); // dest6 EEN
        // node8 (idx7)
        def_entry(15, 7, 0, 2, 3, NORTH, EAST,  NORTH, LOCAL); // dest3 NEN
        def_entry(16, 7, 5, 0, 3, WEST,  NORTH, NORTH, LOCAL); // dest1 WNN
        def_entry(17, 7, 9, 8, 1, EAST, LOCAL, LOCAL, LOCAL);  // dest9 E
        // node9 (idx8)
        def_entry(18, 8, 0, 6, 2, WEST,  WEST,  LOCAL, LOCAL); // dest7 WW
        def_entry(19, 8, 5, 0, 4, NORTH, WEST,  NORTH, WEST);  // dest1 NWNW

        rst_n = 0;
        valid_in_l = '0;
        pkt_in_l   = '0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        @(negedge clk);

        for (int cyc = 0; cyc < NCYCLES; cyc++) begin
            @(negedge clk);

            // 1. Sample outputs first: these reflect whatever was
            //    registered at the posedge just before this negedge,
            //    i.e. arrivals for this exact cycle index.
            for (int nd = 0; nd < NNODES; nd++) begin
                if (valid_out_l[nd]) begin
                    bit found;
                    found = 1'b0;
                    for (int e = 0; e < NUM_ENTRIES; e++) begin
                        if (!matched[e] && dst[e] == nd && arrive_cyc[e] == cyc) begin
                            if (pkt_out_l[nd] === expect_pkt_arr[e]) begin
                                matched[e] = 1'b1;
                                found = 1'b1;
                            end
                        end
                    end
                    if (!found) begin
                        $display("FAIL unexpected arrival at node%0d cyc=%0d pkt=%h (no matching scheduled entry)",
                                  nd, cyc, pkt_out_l[nd]);
                        fail_count++;
                    end
                end
            end

            // 2. Clear all local inputs, then assert this cycle's
            //    scheduled injections (one-cycle pulse per entry).
            valid_in_l = '0;
            pkt_in_l   = '0;
            for (int e = 0; e < NUM_ENTRIES; e++) begin
                if (clk_c[e] == cyc) begin
                    valid_in_l[src[e]] = 1'b1;
                    pkt_in_l[src[e]]   = inject_pkt[e];
                end
            end
        end

        for (int e = 0; e < NUM_ENTRIES; e++) begin
            if (!matched[e]) begin
                $display("FAIL missed delivery: src=node%0d clk=%0d dst=node%0d hops=%0d expected_arrival_cyc=%0d",
                          src[e]+1, clk_c[e], dst[e]+1, hops[e], arrive_cyc[e]);
                fail_count++;
            end
        end

        if (fail_count == 0) begin
            $display("PASS: tb_mesh_schedule, all %0d scheduled deliveries confirmed, no collisions", NUM_ENTRIES);
            $finish;
        end else begin
            $display("FAIL: tb_mesh_schedule, %0d issue(s) found", fail_count);
            $fatal(1);
        end
    end

endmodule