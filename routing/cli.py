"""Command line interface: ``python3 -m routing {generate,run}``."""

import argparse
import sys

from .generator import generate, generate_bruteforce
from .grid import Grid
from .schedule import dump, load
from .visualize import render_svg

__all__ = ["main"]


def _generate(args):
    schedule, stats = generate(args.grid, args.seed)
    text = dump(schedule)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(
        f"grid {args.grid}x{args.grid}, {stats['full_paths']} full paths, "
        f"{stats['saved_prefixes']} saved prefixes, "
        f"{stats['rows_with_choices']} rows with choices, "
        f"frame {stats['frame']} cycles (max clock {stats['max_clock']}), "
        f"seed {args.seed}",
        file=sys.stderr,
    )
    return 0


def _generate_bf(args):
    schedule, stats = generate_bruteforce(args.grid, args.seed)
    text = dump(schedule)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(
        f"grid {args.grid}x{args.grid}, {stats['full_paths']} full paths, "
        f"{stats['passes']} clock passes, "
        f"frame {stats['frame']} cycles (max clock {stats['max_clock']}), "
        f"seed {args.seed}",
        file=sys.stderr,
    )
    return 0


def _run(args):
    schedule = load(args.file)
    grid = Grid(schedule.grid)
    report = grid.run(schedule, verbose=args.verbose)
    if not report.ok:
        print(f"error: {report.message}", file=sys.stderr)
        return 1
    if args.verbose:
        for ev in report.events:
            print(ev)
    rows = len(schedule.rows())
    alts = len(schedule.entries)
    print(
        f"{rows} rows, {alts} alternatives; {report.deliveries}/{report.injections} "
        f"delivered, {report.collisions} collisions, max latency {report.max_latency}"
    )
    return 0


def _visualize(args):
    schedule = load(args.file)
    svg = render_svg(schedule, flip_ms=args.flip_ms)
    if args.out:
        with open(args.out, "w") as f:
            f.write(svg)
    else:
        sys.stdout.write(svg)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m routing",
        description="Edu4Chip router: generate/verify timing schedules.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="produce a collision-free all-pairs timing schedule")
    g.add_argument("--grid", type=int, default=3, help="NxN grid size (default 3)")
    g.add_argument("--seed", type=int, default=0, help="RNG seed (default 0)")
    g.add_argument("--out", default=None, help="write schedule to FILE instead of stdout")

    bf = sub.add_parser(
        "generate-bf",
        help="produce a collision-free all-pairs timing schedule (simulated brute force)",
    )
    bf.add_argument("--grid", type=int, default=3, help="NxN grid size (default 3)")
    bf.add_argument("--seed", type=int, default=0, help="RNG seed (default 0)")
    bf.add_argument("--out", default=None, help="write schedule to FILE instead of stdout")

    r = sub.add_parser("run", help="load a schedule and execute it on the clocked grid")
    r.add_argument("file", help="schedule file")
    r.add_argument("--verbose", action="store_true", help="print per-cycle events")

    v = sub.add_parser(
        "visualize",
        help="render a schedule as SVG (animated viewport + static flipbook)",
    )
    v.add_argument("file", help="schedule file")
    v.add_argument("--out", default=None, help="write SVG to FILE instead of stdout")
    v.add_argument(
        "--flip-ms",
        type=int,
        default=1200,
        help="animation period between cycles in ms (default 1200)",
    )

    args = parser.parse_args(argv)
    try:
        if args.cmd == "generate":
            return _generate(args)
        if args.cmd == "generate-bf":
            return _generate_bf(args)
        if args.cmd == "visualize":
            return _visualize(args)
        return _run(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
