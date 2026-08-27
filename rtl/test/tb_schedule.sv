`timescale 1ns/1ps
`include "rtl/test/schedule_data.svh"

// Schedule-driven test bench for the SIDE=3 mesh.
//
// The bench drives the mesh purely from the generated schedule table
// (tb_schedule_pkg, from `python3 -m routing export-sv`); the RTL has no
// scheduling logic. Two phases:
//
//   Phase 1 (single_pass): every alternative of the schedule fires exactly
//   once. Safe because the schedule is collision-free for any subset of
//   per-row choices.
//
//   Phase 2 (random): 100 periods; each row picks a uniform-random
//   alternative per period (+seed= seeds the LCG, default 1).
//
// Delivery-only check: every injection must arrive at its destination node at
// the expected cycle, and the payload id must identify that injection
// (stray/duplicate ids fail). Stimulus is driven on @(negedge clk) to avoid
// races with router.sv's posedge flops; an injection at iteration c with h
// hops is delivered at iteration c + h.
module tb_schedule;

    import router_pkg::*;
    import tb_schedule_pkg::*;

    localparam int SIDE = SCHED_GRID;
    localparam int NNODES = SIDE * SIDE;
    localparam int RANDOM_PERIODS = 100;
    localparam int MAX_INJ = RANDOM_PERIODS * SCHED_ROWS;  // scoreboard capacity (per phase)

    logic clk = 0;
    logic rst_n;

    logic [NNODES-1:0]                   valid_in_l;
    logic [NNODES-1:0][PACKET_WIDTH-1:0] pkt_in_l;
    logic [NNODES-1:0]                   valid_out_l;
    logic [NNODES-1:0][PACKET_WIDTH-1:0] pkt_out_l;

    logic [NNODES-1:0] inject_active;             // injection pulse in flight (cleared next cycle)

    mesh #(.SIDE(SIDE)) dut (
        .clk(clk), .rst_n(rst_n),
        .valid_in_l(valid_in_l), .pkt_in_l(pkt_in_l),
        .valid_out_l(valid_out_l), .pkt_out_l(pkt_out_l)
    );

    always #5 clk = ~clk;

    // ---- scoreboard (id = payload; ids are sequential at injection) ----
    int   expect_node[MAX_INJ];  // destination RTL index (0-based)
    int   expect_cyc [MAX_INJ];  // iteration at which delivery is observed
    logic done       [MAX_INJ];
    int inj_count;

    // ---- per-phase counters ----
    int packets_sent, packets_delivered, collisions, errors;
    // ---- cumulative totals (for the final verdict) ----
    longint total_cycles;
    int total_sent, total_delivered, total_errors, total_collisions;

    int seed = 1;
    logic [31:0] lcg_state;   // iverilog lacks $srandom: own seeded LCG

    // Uniform choice in [0, maxv] from the LCG (Numerical Recipes constants).
    function automatic int rand_choice(input int maxv);
        lcg_state = lcg_state * 32'd1664525 + 32'd1013904223;
        rand_choice = int'(lcg_state % (maxv + 1));
    endfunction

    // Assert a one-cycle injection pulse for row r's alternative alt at
    // iteration inj_cyc; record the expected destination node and arrival
    // iteration in the scoreboard.
    task automatic inject(int r, int alt, int inj_cyc);
        int src, id;
        src = SCHED_ROW_NODE(r);
        id  = inj_count;
        valid_in_l[src] = 1'b1;
        pkt_in_l[src]   = {SCHED_ALT_D1(alt), SCHED_ALT_D2(alt), SCHED_ALT_D3(alt),
                           SCHED_ALT_D4(alt), id[31:0]};
        inject_active[src] = 1'b1;
        expect_node[id] = SCHED_ALT_DST(alt);
        expect_cyc [id] = inj_cyc + SCHED_ALT_HOPS(alt);
        done       [id] = 1'b0;
        inj_count++;
        packets_sent++;
    endtask

    // Delivery-only check on every LOCAL output valid this iteration.
    task automatic sample(int cyc);
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
                end else if (done[id]) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] duplicate delivery of id %0d at node %0d",
                             $time, id, node);
                end else if (expect_node[id] != node) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] id %0d destined node %0d delivered at node %0d",
                             $time, id, expect_node[id], node);
                end else if (cyc != expect_cyc[id]) begin
                    collisions++; errors++;
                    $display("COLLISION [%0t] id %0d expected at cycle %0d delivered at cycle %0d",
                             $time, id, expect_cyc[id], cyc);
                end else begin
                    done[id] = 1'b1;
                    packets_delivered++;
                end
            end
        end
    endtask

    // Advance one iteration: clear the pulse injected last iteration (the
    // posedge just passed has already sampled it), then check arrivals.
    task automatic cycle(int cyc);
        @(negedge clk);
        for (int i = 0; i < NNODES; i++) begin
            if (inject_active[i]) begin
                valid_in_l[i] = 1'b0;
                pkt_in_l[i]   = '0;
                inject_active[i] = 1'b0;
            end
        end
        sample(cyc);
    endtask

    // Report the phase, accumulate totals, reset per-phase state.
    task automatic finish_phase(string label, longint cycles);
        int undelivered;
        undelivered = 0;
        for (int id = 0; id < inj_count; id++) begin
            if (!done[id]) undelivered++;
        end
        if (undelivered > 0) begin
            collisions += undelivered;
            errors++;
            $display("COLLISION %0s: %0d packet(s) never delivered", label, undelivered);
        end
        total_sent += packets_sent;
        total_delivered += packets_delivered;
        total_cycles += cycles;
        total_errors += errors;
        total_collisions += collisions;
        $display("%0s: sent %0d, delivered %0d, collisions %0d, throughput %0.3f pkts/cycle",
                 label, packets_sent, packets_delivered, collisions,
                 (packets_delivered * 1.0) / cycles);
        for (int id = 0; id < inj_count; id++) done[id] = 1'b0;
        inj_count = 0;
        packets_sent = 0;
        packets_delivered = 0;
        collisions = 0;
        errors = 0;
    endtask

    initial begin
        int r, a, cyc, alt;
        int next_alt[SCHED_ROWS];  // next still-unfired alternative per row (phase 1)

        // Reset: three negedges deasserted, release, one settling negedge.
        rst_n = 0;
        valid_in_l = '0;
        pkt_in_l = '0;
        inject_active = '0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        @(negedge clk);

        // ============ Phase 1: single pass, every alternative exactly once ============
        // Row r fires its next still-unfired alternative at its scheduled
        // clock in every period; a row fires at most one per period, so
        // SCHED_MAX_ALTS periods cover every alternative.
        for (r = 0; r < SCHED_ROWS; r++) next_alt[r] = SCHED_ROW_ALT0(r);
        for (cyc = 0; cyc < SCHED_MAX_ALTS * SCHED_FRAME; cyc++) begin
            for (r = 0; r < SCHED_ROWS; r++) begin
                if (SCHED_ROW_CLOCK(r) == cyc % SCHED_FRAME &&
                    next_alt[r] < SCHED_ROW_ALT0(r) + SCHED_ROW_NALT(r)) begin
                    inject(r, next_alt[r], cyc);
                    next_alt[r]++;
                end
            end
            cycle(cyc);
        end
        finish_phase("single_pass", SCHED_MAX_ALTS * SCHED_FRAME);

        // ============ Phase 2: random traffic, choices within the schedule ============
        // Every row fires one uniform-random alternative every period.
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        lcg_state = seed;
        for (cyc = 0; cyc < RANDOM_PERIODS * SCHED_FRAME; cyc++) begin
            for (r = 0; r < SCHED_ROWS; r++) begin
                if (SCHED_ROW_CLOCK(r) == cyc % SCHED_FRAME) begin
                    alt = rand_choice(SCHED_ROW_NALT(r) - 1);
                    inject(r, SCHED_ROW_ALT0(r) + alt, cyc);
                end
            end
            cycle(cyc);
        end
        finish_phase("random", RANDOM_PERIODS * SCHED_FRAME);

        // ============ Final verdict ============
        if (total_errors == 0) begin
            $display("PASS: tb_schedule — collision-free (sent %0d, delivered %0d, %0d collisions), overall throughput %0.3f pkts/cycle",
                     total_sent, total_delivered, total_collisions,
                     (total_delivered * 1.0) / total_cycles);
            $finish;
        end else begin
            $display("FAIL: tb_schedule, %0d error(s), %0d collision(s)",
                     total_errors, total_collisions);
            $fatal(1);
        end
    end

endmodule
