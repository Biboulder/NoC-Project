"""Offline schedule generator: brute-force all-pairs paths + greedy slot placement.

The routing.md coin flip is realized as the seeded shuffle of (src, dst) pair
order: the order decides who wins a contested slot. Committed alternatives are
immutable — a later path that collides "dies" and retries at the next clock.
"""

import random

from .grid import neighbor_of, node_id, node_position, slot_map
from .header import Direction, max_hops_for
from .schedule import Entry, Schedule

__all__ = ["generate_bruteforce"]

_SCAN = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)


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


def generate_bruteforce(n, seed, pack="none"):
    """Simulated brute-force schedule; deterministic for (n, seed).

    Enumerate all simple paths per (src, dst) pair; pairs are swept
    longest-distance-first (ties seeded-shuffled), each trying its own paths
    from shortest to longest. Committing a pair deletes its alternative
    paths (deletion by omission). ``pack`` selects how many destinations may
    share a (node, clock) row:

    - "none": strict slot-disjointness — every row holds exactly one entry
      and all pairs fire every period.
    - "row" (V1): a pair may join an existing (source, clock) row as an
      alternative — alternatives are mutually exclusive (one packet per node
      per clock, rule 6) so they may share slots; the candidate is checked
      only against entries of *other* rows.

    Returns (Schedule, stats). Termination is guaranteed: once the offset
    exceeds every committed slot cycle, the first remaining pair's slots all
    lie beyond them, so each pass commits at least one pair.
    """
    if n < 2:
        raise ValueError(f"grid must be >= 2, got {n}")
    if pack not in ("none", "row"):
        raise ValueError(
            f"pack must be one of none/row, got {pack!r}"
        )

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

    def conflict(cand, s, o, skip_row):
        """Candidate slots vs every committed entry; with ``skip_row`` the
        (source, clock) row's own entries are mutually-exclusive
        alternatives and may share slots, so they are skipped."""
        for ce, cslots in zip(committed, committed_slots):
            if skip_row and ce.node == s and ce.clock == o:
                continue
            if cand.keys() & cslots.keys():
                return True
        return False

    def try_place(s, d, o, skip_row):
        """Commit pair (s, d) at clock ``o`` if any path fits; True if so."""
        for L in sorted(by_pair[(s, d)]):
            for route in by_pair[(s, d)][L]:
                cand = slot_map(n, s, o, route)
                if not conflict(cand, s, o, skip_row):
                    committed.append(Entry(s, o, d, route))
                    committed_slots.append(cand)
                    return True
        return False

    # sweep: none | row
    skip_row = pack == "row"
    remaining = order
    offset = 0
    passes = 0
    while remaining:
        passes += 1
        still = []
        for s, d in remaining:
            if try_place(s, d, offset, skip_row):
                continue
            still.append((s, d))
        remaining = still
        offset += 1

    assert len(committed) == n * n * (n * n - 1)
    rows = {}
    for e in committed:
        rows.setdefault((e.node, e.clock), []).append(e)
    max_clock = max((e.clock for e in committed), default=0)
    stats = {
        "full_paths": n * n * (n * n - 1),
        "passes": passes,
        "rows": len(rows),
        "alternatives": len(committed),
        "rows_with_choices": sum(1 for alts in rows.values() if len(alts) >= 2),
        "max_clock": max_clock,
        # accurate drain tail: last cycle any packet occupies a router
        "frame": max((e.clock + len(e.route) for e in committed), default=0) + 1,
    }
    return Schedule(n, committed, stats["frame"]), stats
