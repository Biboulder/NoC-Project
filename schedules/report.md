# Schedule comparison — 3x3, seed 0 (link-constrained generator)

> **Link-direction rule (added after E8, regenerated all numbers):** a link is
> a single bidirectional resource — at most one packet may traverse any link
> per cycle, in either direction. Two packets crossing the same link in
> opposite directions in the same cycle are a collision (the "link driven
> from both ends" rule). `Grid.run`'s slot model previously covered routers
> only, so link conflicts were missed; `slot_map` now records links as
> resources too, and the generator places against them. `row` and `lookback`
> are no longer byte-identical (the join-earlier-rows fallback fires under
> the tighter constraint), though their stats match.

Two schedules generated with `python3 -m routing generate-bf --grid 3 --seed 0`:

| | `schedule_none.sched` | `schedule_row.sched` |
|---|---|---|
| pack mode | `none` | `row` (V1) |
| rows (= packets per period) | 72 | 19 |
| alternatives | 72 | 72 |
| rows with choices | 0 | 14 |
| max injection clock | 35 | 12 |
| period (frame) | 37 cycles | 16 cycles |
| worst-case wait to any destination | <= 35 clocks | <= 12 clocks |
| per-destination repeat rate | every 37 cycles | every 16 cycles |
| aggregate throughput | 72/37 = 1.95 pkts/cycle | 19/16 = 1.19 pkts/cycle |
| all pairs complete | 1 period = 37 cycles (guaranteed) | 4 periods = 64 cycles (rotating choices) |
| collision safety | any choice, proven by Grid.run | any choice, proven by Grid.run |

## Semantics

- **`none` (max bandwidth):** every one of the 72 (src, dst) pairs gets its
  own (node, clock) row with a single destination. All 72 pairs inject every
  period — no choices, no ambiguity, guaranteed delivery of all pairs in one
  frame. Cost: long 37-cycle period; a specific destination may wait up to
  35 clocks for its turn.
- **`row` (low latency, packed):** destinations share rows as mutually
  exclusive alternatives (14 of 19 rows offer a choice). The node sends one
  packet per clock, so only 19 of the 72 pairs fire per period; rotate the
  per-row choices across periods to reach all 72 (4 periods = 64 cycles).
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
collision-freedom (routers *and* links) for *any* per-row choice. The
clocked execution then spot-checks a **seeded-random** per-row choice
(`Grid.run(..., seed=)`, CLI `run --seed N`, default 0) — each row picks
one of its alternatives uniformly at random, never just the first. Timings
are wall-clock generation time. "Frame" is the accurate drain
`max(clock + route_len) + 1` unless noted; the old `generate` CLI reports
the conservative `max_clock + max_hops + 1`.

### E1 — Does the old BFS generator actually deliver all-to-all? (3x3, seeds 0–3)

Question: the old `generate` (BFS shortest path per pair, coin-flip order,
saved prefixes) reported frame 20–25. Is that a fair comparison — did it
really reach every node?

Setup: `python3 -m routing generate --grid 3 --seed {0,1,2,3}`; load each
schedule, count rows, count distinct (src, dst) delivered by the executed
(seeded-random, seed 0) choice, run through `Grid.run`.

Results:

| seed | rows | entries | pairs delivered /72 (seed 0) | frame (accurate) |
|---|---|---|---|---|
| 0 | 44 | 85 | 35 | 25 |
| 1 | 42 | 85 | 37 | 24 |
| 2 | 47 | 93 | 38 | 27 |
| 3 | 65 | 108 | 46 | 30 |

Finding: the table contains all 72 full paths as *alternatives*, but a
period physically carries only `rows` packets (42–65), so 23–36 pairs are
shadowed behind other alternatives/prefixes in the same row. With any
per-row choice only 35–46 distinct pairs deliver per period. BFS was
never complete all-to-all per period.

Decision: keep the brute-force generator.

### E2 — Path order: longest-first vs shortest-first (3x3, seeds 0–3)

Question: the original spec tried each pair's *longest* paths first; the
user saw "funny u-turns taking up all the space". Does flipping to
shortest-first help?

Setup: `generate_bruteforce(3, seed)` with the per-pair length loop
`sorted(..., reverse=True)` (longest-first) vs ascending (shortest-first),
seeds 0–3; counted detour routes (route length > Manhattan distance).

Results (all seeds): shortest-first frame 15–16, detours 8–12/72
(16–24 extra hops); longest-first identical — frame 15–16, detours 8–12/72.

Finding: under the link-direction constraint the conflict graph is dense
enough at 3x3 that path ordering no longer changes the result; the earlier
longest-first penalty (4-hop loops for adjacent pairs) is gone.

Decision: keep shortest-first as the default (no regression, and the
pre-constraint rationale still favors it at larger grids).

### E3 — Global pair order: longest-distance-first vs shortest-distance-first (3x3, seeds 0–3)

Question: with distance-descending order, corner pairs could lose early
clocks to shorter pairs. Does flipping the sweep order help?

Setup: scratch copy of the package in `/tmp/rt_link` with
`sorted(by_dist)` instead of `sorted(by_dist, reverse=True)`;
`PYTHONPATH=/tmp python3 -c "..."` seeds 0–3.

Results: identical frames and max clocks for both orders across all seeds
(frame 15–16, max_clock 11–12).

Finding: same mechanism as E2 — the link constraint dominates pair-order
effects at 3x3.

Decision: keep longest-distance-first (tie at 3x3; no reason to change).

### E4 — Pack variants at 3x3: none / row / scan / lookback (seeds 0–3)

Question: can multiple destinations per row (alternatives) compress the
frame at the cost of per-period bandwidth?

Setup: `generate_bruteforce(3, seed, pack=mode)` for
mode ∈ {none, row, scan, lookback}, seeds 0–3. `row` = same-row conflict
skip in the global-offset sweep; `scan` = per-pair clock scan (no global
sweep); `lookback` = `row` sweep + join-earlier-rows fallback. Verified:
72 unique pairs, `Grid.run` ok (router + link slots), deterministic
(`cmp` of two runs).

Results (rows / choices / max_clock / frame / time):

| seed | none | row | scan | lookback |
|---|---|---|---|---|
| 0 | 72/0/35/37 / 80.1 ms | 19/14/12/16 / 50.0 ms | 24/15/12/16 / 48.2 ms | 19/14/12/16 / 51.6 ms |
| 1 | 72/0/35/37 / 83.8 ms | 20/14/11/15 / 48.7 ms | 24/16/11/15 / 47.2 ms | 20/14/11/15 / 51.4 ms |
| 2 | 72/0/36/38 / 81.3 ms | 18/15/11/15 / 48.7 ms | 26/16/14/16 / 48.3 ms | 18/15/11/15 / 52.4 ms |
| 3 | 72/0/32/34 / 77.9 ms | 18/15/11/15 / 46.0 ms | 25/20/13/16 / 46.5 ms | 18/15/11/15 / 49.3 ms |

Findings:

- `row` and `lookback` produce the same stats (identical rows/choices/
  clocks/frame) every seed, but are **no longer byte-identical**: the
  join-earlier-rows fallback does fire usefully under the link constraint.
  `lookback` remains redundant in practice.
- `scan` packs slightly looser (24–26 rows vs 18–20) but is the fastest
  generator (46–48 ms) — it skips the sweep's repeated re-tries.
- `row` frame 15–16 vs `none` 34–38 — ~2.3× tighter.
- `none` is the slowest at 3x3 (78–84 ms): every pair scans many offsets
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
| none | 240/82/84 | 240/84/86 | 3.5–3.6 s |
| row | 36/20/25 | 43/23/29 | 0.50–0.71 s |
| scan | 48/22/27 | 50/25/29 | 0.30–0.36 s |
| lookback | 36/20/25 | 43/23/29 | 0.71–1.10 s |

Finding: packing gain grows with grid size — `row` frame 25–29 is ~2×
better than old-BFS (50–55) and ~3× better than `none` (84–86). `row` and
`lookback` share stats again (different bytes); `scan` fastest but looser.
`none` is by far the slowest (3.5 s+).

Decision: `row` confirmed.

### E6 — 5x5 scaling probe (25 nodes, 600 pairs, max_hops 8, seed 0, row)

Setup: timed `_all_paths(5)` separately from full generation.

Results: path enumeration <0.1 s; full `row` generation 39.7 s; rows 64,
max_clock 38, frame 46; run ok (64/64 delivered — the canonical choice
fires 64 of 600 pairs per period; all 600 paths are present as
alternatives across rows).

Finding: enumeration is cheap; the **sweep's conflict check is the
bottleneck** — every candidate path is intersected against all committed
entries (now router *and* link slots), and pairs scan many offsets. The
link constraint made the sweep costlier than before (22 s → 40 s at 5x5).

Decision: fine for 3x3/4x4. If >4x4 matters, replace the linear conflict
scan with a slot index `(cycle, resource) → owner` (untried, est. ~1 s).

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

Setup: `slot_map` analysis of the *old* `schedule_none.sched` — who
occupies (cycle 1, router 8) and (cycle 1, router 6).

Results: 5→9 (`SE`, clock 0) occupied router 8 at cycle 1; 3→7 (`SWWS`,
clock 0) occupied router 6 at cycle 1. A second arrival would give that
router two valid inputs — a rule-1 collision. Transmitting while receiving
is legal (rule 2).

Finding: not a generator miss — the wires were genuinely busy. **Superseded
by the link-direction rule:** the audit modeled routers only; with links as
single-user resources the generator additionally forbids opposite-direction
crossings, and the specific clock-0 assignments cited here no longer apply
to the regenerated schedules. The slot-index conflict lookup (Untried)
remains the fix if the sweep ever becomes the bottleneck.

Decision: no code change beyond the link-direction rule.

### Untried (candidates, not yet run)

Slot-index conflict lookup (would cut the 5x5 sweep from ~40 s to ~1 s);
grids > 5x5; seeds beyond 4; prefixes as an extra packing layer; choice-
rotation strategies for `row` coverage; seed sweeps for E3 at other grid
sizes.
