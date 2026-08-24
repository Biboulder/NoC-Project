"""Offline schedule generator: BFS all-pairs routes + greedy slot placement.

The routing.md coin flip is realized as the seeded shuffle of (src, dst) pair
order: the order decides who wins a contested slot. Committed alternatives are
immutable — a later path that collides "dies", its hops up to the collision
stay valid and are saved as an extra alternative in that row (packing), and
the full pair retries at the next clock.
"""

import random

from .grid import neighbor_of, node_id, node_position, slot_map
from .header import Direction, max_hops_for
from .schedule import Entry, Schedule

__all__ = ["generate", "generate_bruteforce"]

_SCAN = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)


def _shortest_routes(n):
    """BFS from every node -> {(src, dst): route} (deterministic)."""
    routes = {}
    labels = range(1, n * n + 1)
    for s in labels:
        sx, sy = node_position(n, s)
        prev = {(sx, sy): None}  # pos -> (prev_pos, direction)
        queue = [(sx, sy)]
        head = 0
        while head < len(queue):
            x, y = queue[head]
            head += 1
            for d in _SCAN:
                nb = neighbor_of(n, x, y, d)
                if nb is not None and nb not in prev:
                    prev[nb] = ((x, y), d)
                    queue.append(nb)
        for d in labels:
            if d == s:
                continue
            dx, dy = node_position(n, d)
            route = []
            pos = (dx, dy)
            while prev[pos] is not None:
                ppos, dirc = prev[pos]
                route.append(dirc)
                pos = ppos
            route.reverse()
            routes[(s, d)] = tuple(route)
    return routes


def generate(n, seed):
    """Collision-free all-pairs schedule; deterministic for (n, seed).

    Returns (Schedule, stats). Every (src, dst) pair gets a full-path
    alternative; dying paths leave saved-prefix alternatives behind (packing).
    """
    if n < 2:
        raise ValueError(f"grid must be >= 2, got {n}")

    rng = random.Random(seed)
    labels = list(range(1, n * n + 1))
    pairs = [(s, d) for s in labels for d in labels if s != d]
    rng.shuffle(pairs)  # the coin flip

    routes = _shortest_routes(n)
    committed = []  # list[Entry]
    committed_slots = []  # parallel list of slot maps
    committed_rows = {}  # (node, clock) -> list[Entry] in commit order
    saved_prefixes = 0

    def add(entry, slots):
        """Commit an alternative; exact (dest, route) duplicates within a row
        are skipped — the delivery option already exists there."""
        row = committed_rows.get((entry.node, entry.clock))
        if row is not None and entry in row:
            return False
        committed.append(entry)
        committed_slots.append(slots)
        committed_rows.setdefault((entry.node, entry.clock), []).append(entry)
        return True

    for s, d in pairs:
        route = routes[(s, d)]
        c = 0
        while True:
            cand = slot_map(n, s, c, route)
            # Earliest conflicting slot over all committed alternatives from
            # different rows (same node+clock rows are mutually exclusive).
            first_shared = None
            for ce, cslots in zip(committed, committed_slots):
                if ce.node == s and ce.clock == c:
                    continue
                shared = cand.keys() & cslots.keys()
                if shared:
                    fs = min(shared)
                    if first_shared is None or fs < first_shared:
                        first_shared = fs
            if first_shared is None:
                # Pair done whether the alternative is new or was already
                # saved by an earlier dying path (dedup returns False).
                add(Entry(s, c, d, route), cand)
                break
            hstar = cand[first_shared]  # hop index of the collision (0 = injection)
            if hstar >= 2:
                # The path dies here, but hops 1..hstar-1 stay valid: save
                # them as an extra alternative (dest = router at the last
                # valid hop). All prefix slots precede first_shared, so they
                # are conflict-free with every committed alternative.
                prefix = route[: hstar - 1]
                x, y = node_position(n, s)
                for dirc in prefix:
                    x, y = neighbor_of(n, x, y, dirc)
                dest = node_id(n, x, y)
                if add(Entry(s, c, dest, prefix), slot_map(n, s, c, prefix)):
                    saved_prefixes += 1
            c += 1  # retry the full pair at the next clock

    rows = {}
    for e in committed:
        rows.setdefault((e.node, e.clock), []).append(e)
    max_clock = max((e.clock for e in committed), default=0)
    stats = {
        "full_paths": len(pairs),
        "saved_prefixes": saved_prefixes,
        "rows": len(rows),
        "alternatives": len(committed),
        "rows_with_choices": sum(1 for alts in rows.values() if len(alts) >= 2),
        "max_clock": max_clock,
        "frame": max_clock + max_hops_for(n) + 1,
    }
    return Schedule(n, committed), stats


def _all_paths(n):
    """DFS every node -> {(src, dst): {length: [route, ...]}} (deterministic).

    All simple paths (no repeated nodes) of up to ``max_hops`` hops, grouped
    by length so generate_bruteforce can ascend shortest-first. The scan
    order (and hence the path order within each length group) is fixed;
    randomness is applied later by generate_bruteforce's seeded shuffles.
    """
    max_hops = max_hops_for(n)
    by_pair = {}
    labels = range(1, n * n + 1)
    for s in labels:
        sx, sy = node_position(n, s)
        visited = {(sx, sy)}
        route = []

        def dfs(x, y):
            if len(route) >= max_hops:
                return
            for d in _SCAN:
                nb = neighbor_of(n, x, y, d)
                if nb is None or nb in visited:
                    continue
                visited.add(nb)
                route.append(d)
                dlabel = node_id(n, nb[0], nb[1])
                by_pair.setdefault((s, dlabel), {}).setdefault(
                    len(route), []
                ).append(tuple(route))
                dfs(nb[0], nb[1])
                route.pop()
                visited.discard(nb)

        dfs(sx, sy)
    return by_pair


def generate_bruteforce(n, seed):
    """Simulated brute-force schedule; deterministic for (n, seed).

    Enumerate all simple paths per (src, dst) pair, then sweep the
    uncommitted pairs longest-distance-first at a global clock offset: each
    pair tries its own paths from shortest to longest and commits the first
    that is slot-disjoint from every committed entry; when a pass commits
    nothing new the offset increments by 1 and all remaining pairs are
    re-swept at the new offset (committed entries keep their clocks).
    Committing a pair deletes its alternative paths (deletion by omission).
    Every (node, clock) row ends with exactly one entry — no alternatives.

    Returns (Schedule, stats). Termination is guaranteed: once the offset
    exceeds every committed slot cycle, the first remaining pair's slots all
    lie beyond them, so each pass commits at least one pair.
    """
    if n < 2:
        raise ValueError(f"grid must be >= 2, got {n}")

    rng = random.Random(seed)
    by_pair = _all_paths(n)
    for lens in by_pair.values():
        for routes in lens.values():
            rng.shuffle(routes)

    # Pair order: Manhattan distance descending (corner pairs first), ties
    # seeded-shuffled.
    labels = range(1, n * n + 1)
    by_dist = {}
    for s in labels:
        sx, sy = node_position(n, s)
        for d in labels:
            if d == s:
                continue
            dx, dy = node_position(n, d)
            by_dist.setdefault(abs(dx - sx) + abs(dy - sy), []).append((s, d))
    order = []
    for dist in sorted(by_dist, reverse=True):
        rng.shuffle(by_dist[dist])
        order.extend(by_dist[dist])

    committed = []  # list[Entry]
    committed_slots = []  # parallel list of slot maps
    remaining = order
    offset = 0
    passes = 0
    while remaining:
        passes += 1
        still = []
        for s, d in remaining:
            placed = False
            for L in sorted(by_pair[(s, d)]):
                for route in by_pair[(s, d)][L]:
                    cand = slot_map(n, s, offset, route)
                    if not any(
                        cand.keys() & cslots.keys() for cslots in committed_slots
                    ):
                        committed.append(Entry(s, offset, d, route))
                        committed_slots.append(cand)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                still.append((s, d))
        remaining = still
        offset += 1

    assert len(committed) == n * n * (n * n - 1)
    max_clock = max((e.clock for e in committed), default=0)
    stats = {
        "full_paths": n * n * (n * n - 1),
        "passes": passes,
        "max_clock": max_clock,
        "frame": max_clock + max_hops_for(n) + 1,
    }
    return Schedule(n, committed), stats
