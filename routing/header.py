"""Header primitive for the Edu4Chip router (spec-level simulator).

Direction encodings match NSEW_packet.md exactly. The header is an integer of
``max_hops`` 3-bit fields, MSB-first: the first direction occupies the top 3
bits, and a shift left by 3 (zero-filling the tail) moves to the next field.
A zero field (LOCAL) means "deliver here". There is no payload anywhere.
"""

from enum import IntEnum

__all__ = [
    "Direction",
    "max_hops_for",
    "encode",
    "first_field",
    "shift",
    "route_str",
]


class Direction(IntEnum):
    """Wire direction encodings per NSEW_packet.md."""

    NORTH = 0b001
    SOUTH = 0b010
    EAST = 0b011
    WEST = 0b100
    LOCAL = 0b000

    @classmethod
    def from_char(cls, c):
        """N/S/E/W -> Direction; anything else raises ValueError."""
        for d, ch in _ROUTE_CHARS.items():
            if ch == c:
                return d
        raise ValueError(f"invalid direction character {c!r}")

    def to_char(self):
        try:
            return _ROUTE_CHARS[self]
        except KeyError:
            raise ValueError(f"{self.name} has no route character") from None


_ROUTE_CHARS = {
    Direction.NORTH: "N",
    Direction.SOUTH: "S",
    Direction.EAST: "E",
    Direction.WEST: "W",
}


def max_hops_for(n):
    """Manhattan diameter of an n x n grid: the longest shortest route."""
    if n < 1:
        raise ValueError(f"grid size must be >= 1, got {n}")
    return 2 * n - 2


def encode(route, max_hops):
    """Pack ``route`` into an MSB-first ``max_hops``-field header (int).

    Field i of the route sits in the top ``3*(max_hops - i)`` bits; unused
    trailing fields are zero (LOCAL). The sender never codes LOCAL.
    """
    if max_hops < 0:
        raise ValueError(f"max_hops must be >= 0, got {max_hops}")
    if len(route) > max_hops:
        raise ValueError(f"route length {len(route)} exceeds max_hops {max_hops}")
    h = 0
    for i, d in enumerate(route):
        if d == Direction.LOCAL:
            raise ValueError("sender never codes LOCAL")
        h |= int(d) << (3 * (max_hops - 1 - i))
    return h


def first_field(h, max_hops):
    """The top 3-bit field of the header as a Direction."""
    return Direction((h >> (3 * (max_hops - 1))) & 0b111)


def shift(h, max_hops):
    """Advance one field: shift left 3, zeros in at the tail, width kept."""
    mask = (1 << (3 * max_hops)) - 1
    return (h << 3) & mask


def route_str(route):
    """Directions -> route abbreviation, e.g. (NORTH, EAST) -> "NE"."""
    return "".join(d.to_char() for d in route)
