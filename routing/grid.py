"""NxN clocked grid: execute a schedule and verify deliveries/collisions.

Timing model (mirrors NSEW_packet.md "Router buffering"): output lags input
by 1 cycle; each hop takes one cycle; a packet injected at cycle c with a
route of ``h`` hops is delivered at cycle ``c + h + 1``.

Node labels are 1-based row-major (routing.md table convention); internals
are 0-based (x, y). Conversion happens only here and at the file boundary.
"""

from dataclasses import dataclass, field
import random

from .header import Direction, encode, max_hops_for, route_str
from .router import OPPOSITE, Router

__all__ = [
    "Grid",
    "Report",
    "node_id",
    "node_position",
    "neighbor_of",
    "slot_map",
    "choose_alternatives",
]


def choose_alternatives(schedule, seed=0):
    """One alternative per row, seeded-random (deterministic for seed).

    Each (node, clock) row executes exactly one of its alternatives
    (rule 6); this picks one uniformly at random. The stage-0 pre-pass in
    Grid.run proves *any* such choice is collision-free (routers and
    links), so the drawn choice is a valid spot-check. ``visualize`` uses
    the same helper so the drawing matches the sim.
    """
    rng = random.Random(seed)
    return {
        key: alts[rng.randrange(len(alts))]
        for key, alts in schedule.rows().items()
    }


def node_position(n, label):
    """1-based row-major label -> 0-based (x, y)."""
    label -= 1
    return (label % n, label // n)


def node_id(n, x, y):
    """0-based (x, y) -> 1-based row-major label."""
    return y * n + x + 1


def neighbor_of(n, x, y, port):
    """Position reached from (x, y) via ``port``, or None when off-grid."""
    if port is Direction.NORTH:
        return (x, y - 1) if y > 0 else None
    if port is Direction.SOUTH:
        return (x, y + 1) if y < n - 1 else None
    if port is Direction.EAST:
        return (x + 1, y) if x < n - 1 else None
    if port is Direction.WEST:
        return (x - 1, y) if x > 0 else None
    return None  # LOCAL has no link


def slot_map(n, node, clock, route):
    """Occupied slots for one alternative: (cycle, kind, resource) -> hop index.

    Hop index 0 is the LOCAL injection at the source router; hop h is the
    router reached after h hops, at cycle clock + h. Two resource kinds:

    - kind 0 (router): router h is occupied at cycle clock + h; no router
      may receive more than one packet per cycle.
    - kind 1 (link): hop h traverses the link between routers h-1 and h
      during cycle clock + h. Links are direction-agnostic: a link may
      carry at most one packet per cycle, either way -- two packets
      crossing the same link in opposite directions in the same cycle is
      a collision (the link is a single bidirectional resource).

    Keys are 3-tuples so mixed router/link keys compare cleanly with min().
    Routes are validated in-grid by the parser, so hops never leave the grid.
    """
    x, y = node_position(n, node)
    slots = {(clock, 0, y * n + x): 0}
    for h, d in enumerate(route, start=1):
        nb = neighbor_of(n, x, y, d)
        assert nb is not None, "route must be validated in-grid"
        link = tuple(sorted([(x, y), nb]))
        slots[(clock + h, 1, link)] = h
        x, y = nb
        slots[(clock + h, 0, y * n + x)] = h
    return slots


@dataclass
class Report:
    ok: bool
    message: str = ""
    injections: int = 0
    deliveries: int = 0
    collisions: int = 0
    max_latency: int = 0
    events: list = field(default_factory=list)


def _describe(e):
    return f"node {e.node} clock {e.clock} dest {e.dest} route {route_str(e.route)}"


class Grid:
    def __init__(self, n):
        self.n = n
        self.max_hops = max_hops_for(n)
        self.routers = [Router(x, y, self.max_hops) for y in range(n) for x in range(n)]

    def router_at(self, x, y):
        return self.routers[y * self.n + x]

    def run(self, schedule, verbose=False, seed=0):
        n = self.n
        events = []

        def fail(msg):
            return Report(ok=False, message=msg, events=events)

        # --- Stage 0: choice-safety pre-pass ------------------------------
        # Alternatives in the same row (same node, same clock) are mutually
        # exclusive — the node executes exactly one (rule 6), so they may
        # share slots. Every pair from different rows is co-executable and
        # must be slot-disjoint (routers *and* links); that proves *any*
        # per-row choice is collision-free.
        entries = schedule.entries
        slot_maps = [slot_map(n, e.node, e.clock, e.route) for e in entries]
        for i in range(len(entries)):
            e1 = entries[i]
            for j in range(i + 1, len(entries)):
                e2 = entries[j]
                if e1.node == e2.node and e1.clock == e2.clock:
                    continue
                shared = slot_maps[i].keys() & slot_maps[j].keys()
                if shared:
                    cycle, kind, res = min(shared)
                    if kind == 0:  # router
                        x, y = res % n, res // n
                        what = f"router ({x}, {y})"
                    else:  # link
                        (x1, y1), (x2, y2) = res
                        what = f"link ({x1},{y1})-({x2},{y2})"
                    return fail(
                        f"collision: {_describe(e1)} and {_describe(e2)} "
                        f"both use slot ({cycle}, {what})"
                    )

        # --- Stage 1: clocked execution, seeded-random choice -------------
        # Each row picks one of its alternatives uniformly at random (seeded,
        # deterministic for (schedule, seed)): the executed choice spot-checks
        # a non-trivial selection, which the stage-0 pre-pass already proved
        # safe for any choice.
        choice = choose_alternatives(schedule, seed)

        injections = 0
        deliveries = 0
        max_latency = 0
        pending = set()  # (src, dst, injected_cycle)

        # Run through the last possible delivery (clock + hops + 1); this
        # covers one period plus the flush tail, and also multi-period
        # schedules (clocks shifted by k * period).
        last_slot = max((e.clock + len(e.route) for e in schedule.entries), default=0)
        for c in range(last_slot + 2):
            # 1. Outputs: each router emits (or delivers) its buffered packet.
            driven = {}  # (x, y) -> list[(in_port, pkt)]
            for r in self.routers:
                if r.buffer is None:
                    continue
                _valid, header, src, dst, inj = r.buffer
                out_port, new_header = r.decode()
                if out_port is Direction.LOCAL:
                    if (r.x, r.y) != node_position(n, dst):
                        return fail(
                            f"wrong destination: packet src {src} dst {dst} "
                            f"delivered at ({r.x}, {r.y}) cycle {c}"
                        )
                    lat = c - inj
                    max_latency = max(max_latency, lat)
                    deliveries += 1
                    pending.discard((src, dst, inj))
                    events.append(
                        f"cycle {c}: deliver src {src} dst {dst} "
                        f"at ({r.x}, {r.y}) latency {lat}"
                    )
                else:
                    nb = neighbor_of(n, r.x, r.y, out_port)
                    if nb is None:
                        return fail(
                            f"routed off-grid: packet src {src} dst {dst} "
                            f"port {out_port.to_char()} at ({r.x}, {r.y}) cycle {c}"
                        )
                    nx, ny = nb
                    driven.setdefault((nx, ny), []).append(
                        (OPPOSITE[out_port], (True, new_header, src, dst, inj))
                    )
                    events.append(
                        f"cycle {c}: hop src {src} dst {dst} ({r.x},{r.y}) "
                        f"-{out_port.to_char()}-> ({nx},{ny})"
                    )
                r.buffer = None  # consumed; latch replaces it below

            # 2. Inputs: link arrivals driven in phase 1 + LOCAL injections.
            for r in self.routers:
                r.clear_inputs()
            for (x, y), lst in driven.items():
                r = self.router_at(x, y)
                for port, pkt in lst:
                    r.set_input(port, pkt)
            for (node, clock), e in choice.items():
                if clock != c:
                    continue
                x, y = node_position(n, node)
                pkt = (True, encode(e.route, self.max_hops), node, e.dest, c)
                self.router_at(x, y).set_input(Direction.LOCAL, pkt)
                injections += 1
                pending.add((node, e.dest, c))
                events.append(
                    f"cycle {c}: inject node {node} -> dest {e.dest} "
                    f"route {route_str(e.route)}"
                )

            # 3. Collision check (rule 1): no router receives 2+ packets.
            for r in self.routers:
                valid = r.valid_inputs()
                if len(valid) >= 2:
                    sources = ", ".join(f"{p[2]}->{p[3]}" for p in valid)
                    return fail(
                        f"collision: {len(valid)} packets arrive at router "
                        f"({r.x}, {r.y}) cycle {c} from {sources}"
                    )

            # 4. Latch.
            for r in self.routers:
                r.latch()

        if pending:
            listed = ", ".join(
                f"{s}->{d}@clock {ic}" for (s, d, ic) in sorted(pending)
            )
            return fail(f"undelivered: {len(pending)} packets never delivered: {listed}")

        return Report(
            ok=True,
            injections=injections,
            deliveries=deliveries,
            collisions=0,
            max_latency=max_latency,
            events=events,
        )
