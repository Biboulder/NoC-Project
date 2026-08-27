"""Schedule file format (routing.md table) + parser/validator.

One row per (node, clock)::

    <clock> <dest1,dest2,...> <route1,route2,...>

The dests/routes are parallel comma-separated lists of alternatives; the node
executes exactly one of them per clock (rule 6), so alternatives in a row are
mutually exclusive. Multiple rows for the same (node, clock) are an error.
"""

from dataclasses import dataclass

from .grid import neighbor_of, node_id, node_position
from .header import Direction, max_hops_for, route_str

__all__ = ["Schedule", "Entry", "parse", "load", "dump"]


@dataclass(frozen=True)
class Entry:
    node: int  # 1-based source label
    clock: int  # injection cycle
    dest: int  # 1-based destination label (may be an intermediate router)
    route: tuple  # tuple[Direction, ...] hop sequence


@dataclass
class Schedule:
    grid: int
    entries: list  # list[Entry]
    frame: int = 0  # explicit period (0 = derive): repeats every `frame` cycles

    @property
    def max_clock(self):
        return max((e.clock for e in self.entries), default=0)

    @property
    def period(self):
        """Repeating period: explicit ``frame``, else last occupied cycle + 1.

        The period covers injections plus the flush tail — the network is
        empty exactly at the period boundary, so looping is collision-free.
        """
        if self.frame:
            return self.frame
        return max((e.clock + len(e.route) for e in self.entries), default=0) + 1

    def count(self):
        return len(self.entries)

    def rows(self):
        """(node, clock) -> list of alternative entries, first-appearance order."""
        rows = {}
        for e in self.entries:
            rows.setdefault((e.node, e.clock), []).append(e)
        return rows


def parse(text):
    """Parse schedule text; ValueError with line number on any violation."""
    lines = text.splitlines()
    n = None
    frame = 0
    current = None
    seen_nodes = set()
    seen_rows = set()
    entries = []

    for lineno, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        if n is None:
            tok = line.split()
            if len(tok) != 2 or tok[0] != "grid":
                raise ValueError(f"line {lineno}: expected 'grid N' as first directive, got {line!r}")
            try:
                n = int(tok[1])
            except ValueError:
                raise ValueError(f"line {lineno}: invalid grid size {tok[1]!r}") from None
            if n < 2:
                raise ValueError(f"line {lineno}: grid size must be >= 2, got {n}")
            continue

        if line.startswith("node ") and line.endswith(":"):
            label_s = line[5:-1].strip()
            try:
                label = int(label_s)
            except ValueError:
                raise ValueError(f"line {lineno}: invalid node label {label_s!r}") from None
            if not 1 <= label <= n * n:
                raise ValueError(f"line {lineno}: node label {label} out of range 1..{n * n}")
            if label in seen_nodes:
                raise ValueError(f"line {lineno}: duplicate node section for node {label}")
            seen_nodes.add(label)
            current = label
            continue

        tok = line.split()
        if tok[0] == "grid":
            raise ValueError(f"line {lineno}: 'grid' directive must be the first line")
        if tok[0] == "frame":
            if current is not None:
                raise ValueError(f"line {lineno}: 'frame' must come before any 'node' section")
            if len(tok) != 2:
                raise ValueError(f"line {lineno}: expected 'frame N', got {line!r}")
            try:
                frame = int(tok[1])
            except ValueError:
                raise ValueError(f"line {lineno}: invalid frame {tok[1]!r}") from None
            if frame < 1:
                raise ValueError(f"line {lineno}: frame must be >= 1, got {frame}")
            continue
        if len(tok) != 3:
            raise ValueError(
                f"line {lineno}: expected '<clock> <dest1,dest2,...> <route1,route2,...>', got {line!r}"
            )
        if current is None:
            raise ValueError(f"line {lineno}: entry before any 'node' section")

        try:
            clock = int(tok[0])
        except ValueError:
            raise ValueError(f"line {lineno}: invalid clock {tok[0]!r}") from None
        if clock < 0:
            raise ValueError(f"line {lineno}: clock must be >= 0, got {clock}")

        dest_s = tok[1].split(",")
        route_s = tok[2].split(",")
        if not dest_s:
            raise ValueError(f"line {lineno}: row has no alternatives")
        if len(dest_s) != len(route_s):
            raise ValueError(
                f"line {lineno}: {len(dest_s)} dests but {len(route_s)} routes"
            )

        key = (current, clock)
        if key in seen_rows:
            raise ValueError(
                f"line {lineno}: duplicate row for node {current} clock {clock} "
                "(one choice set per node per clock)"
            )
        seen_rows.add(key)

        for i, (ds, rs) in enumerate(zip(dest_s, route_s)):
            try:
                dest = int(ds)
            except ValueError:
                raise ValueError(f"line {lineno}: invalid dest {ds!r}") from None
            if not 1 <= dest <= n * n:
                raise ValueError(f"line {lineno}: dest {dest} out of range 1..{n * n}")
            if not rs:
                raise ValueError(f"line {lineno}: alternative {i + 1} has an empty route")
            try:
                route = tuple(Direction.from_char(ch) for ch in rs)
            except ValueError as e:
                raise ValueError(f"line {lineno}: {e}") from None

            # Static validation (catches off-grid and wrong-dest routes here).
            if dest == current:
                raise ValueError(f"line {lineno}: source node {current} equals dest {dest}")
            if len(route) > max_hops_for(n):
                raise ValueError(
                    f"line {lineno}: route {rs!r} length {len(route)} exceeds "
                    f"max hops {max_hops_for(n)}"
                )
            x, y = node_position(n, current)
            for h, d in enumerate(route, 1):
                nb = neighbor_of(n, x, y, d)
                if nb is None:
                    raise ValueError(
                        f"line {lineno}: route {rs!r} leaves the grid at hop {h} (node {current})"
                    )
                x, y = nb
            if (x, y) != node_position(n, dest):
                raise ValueError(
                    f"line {lineno}: route {rs!r} from node {current} ends at "
                    f"node {node_id(n, x, y)}, not dest {dest}"
                )

            entries.append(Entry(current, clock, dest, route))

    if n is None:
        raise ValueError("empty schedule: missing 'grid N' directive")
    drain = max((e.clock + len(e.route) for e in entries), default=0) + 1
    if frame and frame < drain:
        raise ValueError(
            f"line: frame {frame} is shorter than the schedule's drain tail "
            f"(last packet occupies cycle {drain - 1})"
        )
    return Schedule(n, entries, frame)


def load(path):
    with open(path) as f:
        return parse(f.read())


def dump(schedule):
    """Render a Schedule back to file format (round-trips parse)."""
    out = [f"grid {schedule.grid}"]
    if schedule.frame:
        out.append(f"frame {schedule.frame}")
    by_node = {}
    for (node, clock), alts in schedule.rows().items():
        by_node.setdefault(node, []).append((clock, alts))
    for node in sorted(by_node):
        out.append(f"node {node}:")
        for clock, alts in sorted(by_node[node]):
            dests = ",".join(str(e.dest) for e in alts)
            routes = ",".join(route_str(e.route) for e in alts)
            out.append(f"  {clock} {dests} {routes}")
    return "\n".join(out) + "\n"
