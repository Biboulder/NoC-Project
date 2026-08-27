`timescale 1ns/1ps
`include "rtl/test/schedule_data.svh"

// Schedule-driven test bench for the SIDE=3 mesh (tb_schedule).
//
// The bench drives a 3x3 mesh purely from the embedded schedule table
// (tb_schedule_pkg, generated from a .sched file by
// `python3 -m routing export-sv`). No scheduling logic exists in the RTL;
// the schedule, buffered here, decides which node injects which packet at
// which clock. Two phases:
//
//   Phase 1 (single_pass): every alternative of the schedule fires exactly
//   once, across consecutive periods; rows whose alternatives are all
//   exhausted stay silent in later periods (safe: the schedule is
//   collision-free for any subset of choices).
//
//   Phase 2 (random): 100 periods; each row picks a uniform-random
//   alternative per period ($urandom_range), seeded via +seed= (default 1).
//
// Collision detection is by data correctness: every injection must be
// delivered exactly once, at the right node, with the payload intact and
// the header fully nulled. Any anomaly (stray id, duplicate, wrong
// recipient, non-nulled header, missing delivery) plus link contention
// (a link driven from both ends) counts as a collision and fails the
// phase. The RTL crossbar never flags collisions itself -- the scoreboard
// and the hierarchical contention monitor are the detectors.
//
// Timing follows tb_mesh.sv: stimulus is driven on @(negedge clk) to avoid
// races with router.sv's posedge flops; a packet with H real direction
// hops is observable on the destination LOCAL output H negedges after the
// deassert-negedge that ends the injection pulse. Cycle c injection =
// valid driven at the negedge starting cycle c, deasserted at the negedge
// ending it.
module tb_schedule;

    import router_pkg::*;
    import tb_schedule_pkg::*;

    localparam int SIDE = SCHED_GRID;
    localparam int NNODES = SIDE * SIDE;
    localparam int RANDOM_PERIODS = 100;
    localparam int MAX_INJ = RANDOM_PERIODS * SCHED_ROWS;  // scoreboard capacity (per phase)
    localparam int MAX_HOPS = 4;                   // grid <= 3: diameter 4

    logic clk = 0;
    logic rst_n;

    logic [NNODES-1:0]                   valid_in_l;
    logic [NNODES-1:0][PACKET_WIDTH-1:0] pkt_in_l;
    logic [NNODES-1:0]                   valid_out_l;
    logic [NNODES-1:0][PACKET_WIDTH-1:0] pkt_out_l;

    logic [NNODES-1:0] inject_active;             // pulse in flight (deassert next cycle)

    mesh #(.SIDE(SIDE)) dut (
        .clk(clk), .rst_n(rst_n),
        .valid_in_l(valid_in_l), .pkt_in_l(pkt_in_l),
        .valid_out_l(valid_out_l), .pkt_out_l(pkt_out_l)
    );

    always #5 clk = ~clk;

    // ---- phase-scoped counters (zeroed by finish_phase) ----
    longint cycle_count;                          // negedge ticks since phase start
    int packets_sent;                             // incremented in inject()
    int packets_delivered;                        // incremented on each verified delivery
    int collisions;                               // delivery anomalies + contentions
    int errors;

    // ---- cumulative totals (across phases, for the final verdict) ----
    longint total_cycles;
    int total_sent, total_delivered, total_errors, total_collisions;
    int phase_idx;                                // 0 = single_pass, 1 = random
    int ph_sent[2], ph_del[2];
    longint ph_cycles[2];

    // ---- scoreboard (id-indexed; id = payload at injection) ----
    int inj_dst[MAX_INJ];
    int inj_hops[MAX_INJ];
    logic inj_done[MAX_INJ];
    int inj_count;

    // ---- single-pass tracking ----
    int fired[SCHED_ALTS];

    int seed = 1;
    logic [31:0] lcg_state;   // iverilog lacks $srandom: own seeded LCG

    // Uniform choice in [0, maxv] from the LCG (Numerical Recipes constants).
    function automatic int rand_choice(input int maxv);
        lcg_state = lcg_state * 32'd1664525 + 32'd1013904223;
        rand_choice = int'(lcg_state % (maxv + 1));
    endfunction

    // Drive one injection: valid/pkt asserted on the LOCAL port of src,
    // scoreboard recorded. Deassert happens on the next cycle in
    // drive_cycle() via inject_active.
    task automatic inject(int row, int alt);
        int src, id;
        src = SCHED_ROW_NODE(row);
        id  = inj_count;
        valid_in_l[src] = 1'b1;
        pkt_in_l[src]   = {SCHED_ALT_D1(alt), SCHED_ALT_D2(alt), SCHED_ALT_D3(alt),
                           SCHED_ALT_D4(alt), id[31:0]};
        inject_active[src] = 1'b1;
        inj_dst [id] = SCHED_ALT_DST(alt);
        inj_hops[id] = SCHED_ALT_HOPS(alt);
        inj_done[id] = 1'b0;
        inj_count++;
        packets_sent++;
    endtask

    // Data-correctness check on every LOCAL output that is valid this cycle.
    task automatic sample();
        int id;
        packet_t pkt;
        for (int node = 0; node < NNODES; node++) begin
            if (valid_out_l[node]) begin
                pkt = pkt_out_l[node];
                id = pkt[31:0];
                if (id >= inj_count) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] stray packet id %0d at node %0d (no such injection)",
                             $time, id, node);
                end else if (inj_done[id]) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] duplicate delivery of id %0d at node %0d",
                             $time, id, node);
                end else if (inj_dst[id] != node) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] id %0d destined node %0d delivered at node %0d",
                             $time, id, inj_dst[id], node);
                end else if (pkt[43:32] != 12'h000) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] id %0d at node %0d has non-nulled header %h",
                             $time, id, node, pkt[43:32]);
                end else begin
                    inj_done[id] = 1'b1;
                    packets_delivered++;
                end
            end
        end
    endtask

    // Hierarchical link-contention monitor: a link driven from both ends in
    // the same cycle is a collision. North/south pairs share the (r,c)<->(r+1,c)
    // link; east/west pairs share the (r,c)<->(r,c+1) link.
    task automatic check_contentions();
        for (int r = 0; r < SIDE - 1; r++) begin
            for (int c = 0; c < SIDE; c++) begin
                if (dut.out_s_valid[r][c] && dut.out_n_valid[r + 1][c]) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] link contention (N/S) between nodes (%0d,%0d) and (%0d,%0d)",
                             $time, r, c, r + 1, c);
                end
            end
            for (int c = 0; c < SIDE - 1; c++) begin
                if (dut.out_e_valid[r][c] && dut.out_w_valid[r][c + 1]) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] link contention (E/W) between nodes (%0d,%0d) and (%0d,%0d)",
                             $time, r, c, r, c + 1);
                end
            end
        end
    endtask

    // One negedge: deassert the injection pulsed last cycle (after the
    // posedge that sampled it), then sample deliveries and contentions,
    // then count the cycle. This is the only place that advances time in
    // the phase loop, so ordering is deterministic.
    task automatic drive_cycle();
        @(negedge clk);
        for (int i = 0; i < NNODES; i++) begin
            if (inject_active[i]) begin
                valid_in_l[i] = 1'b0;
                pkt_in_l[i]   = '0;
                inject_active[i] = 1'b0;
            end
        end
        sample();
        check_contentions();
        cycle_count++;
    endtask

    // Report the phase, accumulate totals, reset per-phase state.
    task automatic finish_phase(string label);
        int undelivered;
        undelivered = 0;
        for (int id = 0; id < inj_count; id++) begin
            if (!inj_done[id]) undelivered++;
        end
        if (undelivered > 0) begin
            collisions += undelivered;
            errors++;
            $display("COLLISION %0s: %0d packet(s) never delivered", label, undelivered);
        end
        ph_sent[phase_idx] = packets_sent;
        ph_del[phase_idx]  = packets_delivered;
        ph_cycles[phase_idx] = cycle_count;
        total_sent += packets_sent;
        total_delivered += packets_delivered;
        total_cycles += cycle_count;
        total_errors += errors;
        total_collisions += collisions;
        $display("%0s: sent %0d, delivered %0d, collisions %0d, throughput %0.3f pkts/cycle",
                 label, packets_sent, packets_delivered, collisions,
                 (packets_delivered * 1.0) / cycle_count);
        for (int id = 0; id < inj_count; id++) inj_done[id] = 1'b0;
        inj_count = 0;
        packets_sent = 0;
        packets_delivered = 0;
        collisions = 0;
        errors = 0;
        cycle_count = 0;
        phase_idx++;
    endtask

    initial begin
        int p, c, r, a, alt, target, fired_any, last_cycle, last_period;

        // Reset: three negedges deasserted, release, one settling negedge.
        rst_n = 0;
        valid_in_l = '0;
        pkt_in_l = '0;
        inject_active = '0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        @(negedge clk);
        cycle_count = 0;

        // ============ Phase 1: single pass, every alternative exactly once ============
        // Periods advance until every alternative has fired; a row injects its
        // first still-unfired alternative at p*SCHED_FRAME + SCHED_ROW_CLOCK[r].
        // Rows are processed clock-major so injections land in cycle order.
        // (iverilog has no break/continue: flag + while loops.)
        p = 0;
        fired_any = 1;
        while (fired_any) begin
            fired_any = 0;
            for (c = 0; c <= SCHED_MAX_CLOCK; c++) begin
                for (r = 0; r < SCHED_ROWS; r++) begin
                    if (SCHED_ROW_CLOCK(r) == c) begin
                        // first still-unfired alternative of this row
                        a = SCHED_ROW_ALT0(r);
                        while (a < SCHED_ROW_ALT0(r) + SCHED_ROW_NALT(r) && fired[a]) a++;
                        if (a < SCHED_ROW_ALT0(r) + SCHED_ROW_NALT(r)) begin
                            target = p * SCHED_FRAME + c;
                            while (cycle_count < target) drive_cycle();
                            inject(r, a);
                            fired[a] = 1;
                            fired_any = 1;
                            last_period = p;
                        end
                    end
                end
            end
            p++;
        end
        // Drain: last injection cycle + deassert cycle + max hops + 5-cycle margin.
        last_cycle = last_period * SCHED_FRAME + SCHED_MAX_CLOCK;
        while (cycle_count <= last_cycle + 1 + MAX_HOPS + 5) drive_cycle();
        finish_phase("single_pass");

        // ============ Phase 2: random traffic, choices within the schedule ============
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        lcg_state = seed;
        for (p = 0; p < RANDOM_PERIODS; p++) begin
            for (c = 0; c <= SCHED_MAX_CLOCK; c++) begin
                for (r = 0; r < SCHED_ROWS; r++) begin
                    if (SCHED_ROW_CLOCK(r) == c) begin
                        alt = rand_choice(SCHED_ROW_NALT(r) - 1);
                        target = p * SCHED_FRAME + c;
                        while (cycle_count < target) drive_cycle();
                        inject(r, SCHED_ROW_ALT0(r) + alt);
                    end
                end
            end
        end
        last_cycle = (RANDOM_PERIODS - 1) * SCHED_FRAME + SCHED_MAX_CLOCK;
        while (cycle_count <= last_cycle + 1 + MAX_HOPS + 5) drive_cycle();
        finish_phase("random");

        // ============ Final verdict ============
        if (total_errors == 0) begin
            $display("PASS: tb_schedule — collision-free (single pass sent %0d/delivered %0d, random sent %0d/delivered %0d, %0d collisions), overall throughput %0.3f pkts/cycle",
                     ph_sent[0], ph_del[0], ph_sent[1], ph_del[1], total_collisions,
                     (total_delivered * 1.0) / total_cycles);
            $finish;
        end else begin
            $display("FAIL: tb_schedule, %0d error(s), %0d collision(s)",
                     total_errors, total_collisions);
            $fatal(1);
        end
    end

endmodule
