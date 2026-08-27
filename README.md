# Edu4Chip_Router

## Running tests

Test benches run inside a Docker container with Icarus Verilog (`-g2012`):

```bash
./run_tb.sh direction_decode            # runs rtl/test/tb_direction_decode.sv
./run_tb.sh direction_decode --rebuild  # force a Docker image rebuild
```

Works on Linux and macOS with [Docker Desktop](https://www.docker.com/products/docker-desktop/);
the image is multi-arch, so both Intel and Apple Silicon are supported.
`run_tb.sh` needs bash (3.2+, bundled with macOS).

The `edu4chip-iverilog` image (see `Dockerfile`) is built automatically on
first use. All RTL in `rtl/` is compiled together with
`rtl/test/tb_<module>.sv`; package files (`*_pkg.sv`) are compiled first,
since iverilog requires definitions before imports. The repo is mounted
read-write, so test benches can write wave files (e.g. `$dumpfile`) into
`rtl/test/`.

## Workflow: generate a schedule, export it, run the bench, visualize

The Python tooling (`python3 -m routing`) generates collision-free
time-division schedules. The RTL contains no scheduling logic — the bench
drives injection purely from a schedule table exported as SystemVerilog.

### 1. Generate a schedule

Grids 2 and 3 are supported (`router_pkg` HEADER=12 holds four 3-bit
direction fields, so a 3x3 mesh — max route 4 hops — is the largest; the
exporter refuses anything bigger). Generation is deterministic for
`(grid, seed)`:

```bash
python3 -m routing generate-bf --grid 3 --seed 0 --pack row \
    --out schedules/schedule_row.sched
```

- `--pack row` packs several destinations into shared (node, clock) rows as
  mutually exclusive alternatives: low latency, ~19 of 72 pairs fire per
  period, all pairs covered in 4 periods (the checked-in default).
- `--pack none` gives each pair its own row: max bandwidth, all 72 pairs
  fire every period, at the cost of a longer period.
- Schedule file format: see `routing.md`.

Validate the schedule — the checker proves collision-freedom (routers and
links) for *any* per-row choice, then executes a **seeded-random** choice
among each row's alternatives and must deliver everything:

```bash
python3 -m routing run schedules/schedule_row.sched            # choice seed 0
python3 -m routing run schedules/schedule_row.sched --seed 7   # a different choice
```

### 2. Export the schedule as a SystemVerilog include

```bash
python3 -m routing export-sv schedules/schedule_row.sched -o rtl/test/schedule_data.svh
```

This writes `rtl/test/schedule_data.svh`, a `tb_schedule_pkg` package
(grid, frame, rows, alternatives, routes) that `rtl/test/tb_schedule.sv`
includes. Regenerate it whenever the schedule changes.

### 3. Run the schedule-driven test bench

```bash
./run_tb.sh schedule            # Docker (compiles all of rtl/ + the bench)
```

or locally with Icarus Verilog:

```bash
iverilog -g2012 -o /tmp/sim.out rtl/router_pkg.sv rtl/mesh.sv rtl/router.sv \
    rtl/direction_decode.sv rtl/test/tb_schedule.sv
vvp /tmp/sim.out                # +seed=N seeds the random phase (default 1)
```

The bench runs two phases: a single pass firing every schedule alternative
exactly once (72 packets for the 3x3 row schedule), and 100 periods of
seeded-random traffic following the schedule (100 x rows packets). It
checks deliveries only — stray, duplicate, wrong-recipient, wrong-cycle, or
missing deliveries — and prints
per-phase and overall throughput. A clean run ends with
`PASS: tb_schedule — collision-free …`.

### 4. Visualize a schedule

```bash
python3 -m routing visualize schedules/schedule_row.sched --out /tmp/sched.svg
python3 -m routing visualize schedules/schedule_row.sched --flip-ms 800
python3 -m routing visualize schedules/schedule_row.sched --seed 3
```

Writes a self-contained, browser-interactive dark SVG — open the file in a
browser (JavaScript animates it; static image viewers show only the
initial frame). Packets are animated live in three explicit states:
**injected** (at the source, pulsing ring — has not left), **in flight**
(gliding along a lit wire), **delivered** (flash at the destination); a HUD
counts the three disjoint states each cycle, alongside play/pause, speed
(0.5x/1x/2x), and a cycle scrubber (`‹`/`›` + slider) controls. Packed
rows have several alternatives — `--seed` picks the *initial* per-row
choice (default 0, matching `run --seed N` for the first frame only);
choices then re-roll randomly at every period boundary and via the
`re-roll` button. `--flip-ms` sets the milliseconds per cycle. Below the
main viewport (centered over the flipbook) a **static flipbook** shows
every cycle as its own dark grid — packets glide along lit wires (one
hop per cycle, axis-aligned on the mesh), captions count in-flight /
injected packets per cycle, row-packed rows show a random path per
period (re-rolled at every period boundary and on `re-roll`), and the
flipbook follows the play/pause and speed controls. The flipbook sits in
a draggable, resizable window — drag its title bar to move it, drag the
bottom-right corner to resize; frames re-stack to the window width (more
columns when wider) and the canvas grows to fit — handy for composing
screenshot layouts.
