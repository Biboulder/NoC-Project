"""NxN clocked grid: execute a schedule and verify deliveries/collisions.

Timing model (mirrors NSEW_packet.md "Router buffering"): output lags input
by 1 cycle; each hop takes one cycle; a packet injected at cycle c with a
route of ``h`` hops is delivered at cycle ``c + h + 1``.

Node labels are 1-based row-major (routing.md table convention); internals
are 0-based (x, y). Conversion happens only here and at the file boundary.
"""

from dataclasses import dataclass, field

from .header import Direction, encode, max_hops_for, route_str
from .router import OPPOSITE, Router

__all__ = [
    "Grid",
    "Report",
    "node_id",
    "node_position",
    "neighbor_of",
    "slot_map",
]


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
    """Occupied slots for one alternative: (cycle, router_index) -> hop index.

    Hop index 0 is the LOCAL injection at the source router; hop h is the
    router reached after h hops, at cycle clock + h. Routes are validated
    in-grid by the parser, so hops never leave the grid.
    """
    x, y = node_position(n, node)
    slots = {(clock, y * n + x): 0}
    for h, d in enumerate(route, start=1):
        nb = neighbor_of(n, x, y, d)
        assert nb is not None, "route must be validated in-grid"
        x, y = nb
        slots[(clock + h, y * n + x)] = h
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

    def run(self, schedule, verbose=False):
        n = self.n
        events = []

        def fail(msg):
            return Report(ok=False, message=msg, events=events)

        # --- Stage 0: choice-safety pre-pass ------------------------------
        # Alternatives in the same row (same node, same clock) are mutually
        # exclusive — the node executes exactly one (rule 6) — so they may
        # share slots. Every pair from different rows is co-executable and
        # must be slot-disjoint; that proves *any* per-row choice is
        # collision-free.
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
                    cycle, idx = min(shared)
                    x, y = idx % n, idx // n
                    return fail(
                        f"collision: {_describe(e1)} and {_describe(e2)} "
                        f"both use slot ({cycle}, ({x}, {y}))"
                    )

        # --- Stage 1: clocked execution, canonical choice -----------------
        # Canonical choice = first alternative of each row (entry order).
        choice = {key: alts[0] for key, alts in schedule.rows().items()}

        injections = 0
        deliveries = 0
        max_latency = 0
        pending = set()  # (src, dst, injected_cycle)

        for c in range(schedule.max_clock + self.max_hops + 2):
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
