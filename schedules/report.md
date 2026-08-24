# Schedule comparison — 3x3, seed 0

Two schedules generated with `python3 -m routing generate-bf --grid 3 --seed 0`:

| | `schedule_none.sched` | `schedule_row.sched` |
|---|---|---|
| pack mode | `none` | `row` (V1) |
| rows (= packets per period) | 72 | 20 |
| alternatives | 72 | 72 |
| rows with choices | 0 | 17 |
| max injection clock | 31 | 11 |
| period (frame) | 33 cycles | 14 cycles |
| worst-case wait to any destination | <= 31 clocks | <= 11 clocks |
| per-destination repeat rate | every 33 cycles | every 14 cycles |
| aggregate throughput | 72/33 = 2.18 pkts/cycle | 20/14 = 1.43 pkts/cycle |
| all pairs complete | 1 period = 33 cycles (guaranteed) | 4 periods = 56 cycles (rotating choices) |
| collision safety | any choice, proven by Grid.run | any choice, proven by Grid.run |

## Semantics

- **`none` (max bandwidth):** every one of the 72 (src, dst) pairs gets its
  own (node, clock) row with a single destination. All 72 pairs inject every
  period — no choices, no ambiguity, guaranteed delivery of all pairs in one
  frame. Cost: long 33-cycle period; a specific destination may wait up to
  31 clocks for its turn.
- **`row` (low latency, packed):** destinations share rows as mutually
  exclusive alternatives (17 of 20 rows offer a choice). The node sends one
  packet per clock, so only 20 of the 72 pairs fire per period; rotate the
  per-row choices across periods to reach all 72 (4 periods = 56 cycles).
  Cost: lower sustained throughput per node; needs choice logic at the node
  or a fixed choice per period.

## Which to use

- Use **`none`** when every node must reach every destination every period,
  with zero runtime decision-making (e.g. a fixed, repeating hardcoded
  table, throughput-first traffic).
- Use **`row`** when time-to-first-send and short repeat latency matter
  more than guaranteed all-pairs throughput, and the node (or a small
  state machine) can pick one alternative per clock.

Generation time is negligible for both at 3x3. Both are deterministic for
`(n, seed)` and verified collision-free for *any* per-row choice.

## Experiment log — what we tested, so we don't re-run it

Every experiment below was run in this repo; all schedules were verified
with `python3 -m routing run <file>` (or `Grid.run`) — deliveries match
injections, zero collisions, and `Grid.run`'s stage-0 pre-pass proves
collision-freedom for *any* per-row choice. Timings are wall-clock
generation time. "Frame" is the accurate drain `max(clock + route_len) + 1`
unless noted; the old `generate` CLI reports the conservative
`max_clock + max_hops + 1`.

### E1 — Does the old BFS generator actually deliver all-to-all? (3x3, seeds 0–3)

Question: the old `generate` (BFS shortest path per pair, coin-flip order,
saved prefixes) reported frame 20–25. Is that a fair comparison — did it
really reach every node?

Setup: `python3 -m routing generate --grid 3 --seed {0,1,2,3}`; load each
schedule, count rows, count distinct (src, dst) delivered by the canonical
(first-alternative) execution, run through `Grid.run`.

Results:

| seed | rows | entries | canonical pairs delivered /72 | frame (accurate) |
|---|---|---|---|---|
| 0 | 43 | 84 | 38 | 24 |
| 1 | 32 | 78 | 30 | 19 |
| 2 | 41 | 89 | 37 | 23 |
| 3 | 40 | 85 | 35 | 22 |

Finding: the table contains all 72 full paths as *alternatives*, but a
period physically carries only `rows` packets (32–43), so 29–42 pairs are
shadowed behind other alternatives/prefixes in the same row. With a fixed
(canonical) choice only 30–38 distinct pairs deliver per period. BFS was
never complete all-to-all per period.

Decision: keep the brute-force generator.

### E2 — Path order: longest-first vs shortest-first (3x3, seeds 0–3)

Question: the original spec tried each pair's *longest* paths first; the
user saw "funny u-turns taking up all the space". Does flipping to
shortest-first help?

Setup: `generate_bruteforce(3, seed)` with the per-pair length loop
`sorted(..., reverse=True)` (longest-first) vs ascending (shortest-first),
seeds 0–3; counted detour routes (route length > Manhattan distance).

Results (seed 0; others similar): longest-first frame 42, detours 29/72
(58 extra hops); shortest-first frame 36, detours 13/72 (26 extra hops).
Longest-first frames across seeds: 40–42; shortest-first: 36–39.

Finding: longest-first committed 4-hop loops for adjacent pairs whose
direct 1-hop path would fit; shortest-first halved the detours and improved
the frame.

Decision: shortest-first is the default (current code).

### E3 — Global pair order: longest-distance-first vs shortest-distance-first (3x3, seed 0)

Question: with distance-descending order, node 9 (corner) was idle at
clock 0 despite 1-hop options. Would flipping the sweep order give short
pairs the early clocks?

Setup: scratch copy of the package in `/tmp/routing_test` with
`sorted(by_dist)` instead of `sorted(by_dist, reverse=True)`;
`PYTHONPATH=/tmp python3 -c "..."` seed 0.

Results: node 9 → 6 (`N`) did get clock 0 (72/72 ok), but the frame
worsened 36 → 40 (max_clock 31 → 35): the corner pairs' long paths get
squeezed into later offsets.

Finding: pair order decides who wins contested early wires; longest-
distance-first keeps the frame tightest. This is the same mechanism as E8.

Decision: rejected; kept longest-distance-first.

### E4 — Pack variants at 3x3: none / row / scan / lookback (seeds 0–3)

Question: can multiple destinations per row (alternatives) compress the
frame at the cost of per-period bandwidth?

Setup: `generate_bruteforce(3, seed, pack=mode)` for
mode ∈ {none, row, scan, lookback}, seeds 0–3. `row` = same-row conflict
skip in the global-offset sweep; `scan` = per-pair clock scan (no global
sweep); `lookback` = `row` sweep + join-earlier-rows fallback. Verified:
72 unique pairs, `Grid.run` ok, deterministic (`cmp` of two runs).

Results (rows / choices / max_clock / frame / time):

| seed | none | row | scan | lookback |
|---|---|---|---|---|
| 0 | 72/0/31/33 / 24.3 ms | 20/17/11/14 / 4.8 ms | 22/16/12/14 / 3.7 ms | 20/17/11/14 / 7.8 ms |
| 1 | 72/0/34/36 / 26.8 ms | 16/14/10/15 / 7.4 ms | 23/18/13/15 / 4.3 ms | 16/14/10/15 / 7.1 ms |
| 2 | 72/0/32/34 / 24.2 ms | 16/15/10/14 / 6.6 ms | 24/17/13/15 / 4.4 ms | 16/15/10/14 / 7.5 ms |
| 3 | 72/0/32/34 / 24.0 ms | 17/14/9/14 / 5.2 ms | 20/16/10/15 / 3.8 ms | 17/14/9/14 / 6.5 ms |

Findings:

- `row` ≡ `lookback` — byte-identical schedules every seed. The
  join-earlier-rows fallback never fires usefully: earlier rows carry more
  committed traffic to avoid, so a pair that fails at the current offset
  cannot fit into a busier earlier row either. V3 is redundant.
- `scan` packs slightly looser (20–24 rows vs 16–20) but is the fastest
  generator (3.7–4.4 ms) — it skips the sweep's repeated re-tries.
- `row` frame 14–15 vs `none` 33–36 — ~2.4× tighter.
- `none` is the slowest at 3x3 (24–27 ms): every pair scans many offsets
  before fitting.

Decision: adopt `row`. Keep `none` for the max-bandwidth guarantee. `scan`
only if generation speed ever matters; `lookback` is dead code (kept only
for comparison).

### E5 — Same variants at 4x4 (16 nodes, 240 pairs, max_hops 6, seeds 0–1)

Setup: identical matrix, `n=4`, timed.

Results (rows / max_clock / frame / time):

| mode | seed 0 | seed 1 | time |
|---|---|---|---|
| old-BFS | 170/48/55 | 155/43/50 | 0.23–0.25 s |
| none | 240/84/86 | 240/82/84 | 2.3 s |
| row | 40/23/27 | 41/21/26 | 0.40 s |
| scan | 46/23/25 | 53/24/28 | 0.17–0.19 s |
| lookback | 40/23/27 | 41/21/26 | 0.57–0.59 s |

Finding: packing gain grows with grid size — `row` frame 26–27 is ~2×
better than old-BFS (50–55) and ~3× better than `none` (84–86). `row` ≡
`lookback` again; `scan` fastest again but looser. `none` is by far the
slowest (2.3 s).

Decision: `row` confirmed.

### E6 — 5x5 scaling probe (25 nodes, 600 pairs, max_hops 8, seed 0, row)

Setup: timed `_all_paths(5)` separately from full generation.

Results: path enumeration <0.1 s (30,640 paths total); full `row`
generation 22.1 s; rows 72, max_clock 35, frame 41; run ok (72/72).

Finding: enumeration is cheap; the **sweep's conflict check is the
bottleneck** — every candidate path is intersected against all committed
entries, and pairs scan many offsets. This is why `none` is slowest and why
5x5 takes 22 s.

Decision: fine for 3x3/4x4. If >4x4 matters, replace the linear conflict
scan with a slot index `(cycle, router) → owner` (untried, est. ~1 s).

### E7 — Visualization iterations (visualize.py)

Sequence, each in response to review: injection-only frames → remaining-
route lines per packet → static mid-wire points → **animated per-wire
glides** in the flipbook (`animateMotion`, one wire per cycle, fade at
arrival) + SMIL full-journey viewport (glide a→b, vanish at dest, reappear
at source each period). Frame range fixed from conservative
`max_clock + max_hops + 1` to accurate drain `max(clock + len(route)) + 1`
— the old formula left empty tail frames (e.g. cycles 33–35 at 3x3 because
the last injections are 1-hop).

### E8 — Collision audit: why node 9 can't send at clock 0 (3x3 seed 0)

Question: "exhaustive" algorithm misses 9→8/9→6 at clock 0?

Setup: `slot_map` analysis of `schedule_none.sched` — who occupies
(cycle 1, router 8) and (cycle 1, router 6).

Results: 5→9 (`SE`, clock 0) occupies router 8 at cycle 1; 3→7 (`SWWS`,
clock 0) occupies router 6 at cycle 1. A second arrival would give that
router two valid inputs — a rule-1 collision. Transmitting while receiving
is legal (rule 2), so node 8's own clock-0 send does *not* block 9→8; the
5→9 packet does.

Finding: not a generator miss — the wires are genuinely busy; greedy pair
order (distance-descending) decides who gets them. Same mechanism as E3.

Decision: no code change.

### Untried (candidates, not yet run)

Slot-index conflict lookup (would cut the 5x5 sweep from 22 s to ~1 s);
grids > 5x5; seeds beyond 4; prefixes as an extra packing layer; choice-
rotation strategies for `row` coverage; seed sweeps for E3 at other grid
sizes.
