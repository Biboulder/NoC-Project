"""Stateless router: a 1-cycle pipeline register with no routing state.

A packet on the wire is a 5-tuple ``(valid, header, src, dst, injected_cycle)``
where src/dst/injected_cycle are verification bookkeeping, not wire data.
The router holds at most one packet in its buffer (latched from the previous
cycle's single valid input) and emits at most one output per cycle.
"""

from .header import Direction, first_field, shift

__all__ = ["Router", "OPPOSITE"]

# Input port naming: a packet arriving from the east is received on the WEST
# input port of this router (the link connects the two).
OPPOSITE = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}


class Router:
    def __init__(self, x, y, max_hops):
        self.x = x
        self.y = y
        self.max_hops = max_hops
        self.buffer = None  # (valid, header, src, dst, injected_cycle) | None
        self.inputs = {}  # Direction -> packet | None, cleared each cycle

    def set_input(self, port, pkt):
        self.inputs[port] = pkt

    def clear_inputs(self):
        self.inputs.clear()

    def valid_inputs(self):
        return [p for p in self.inputs.values() if p is not None]

    def decode(self):
        """(out_port, shifted_header) for the buffered packet.

        LOCAL out_port means the packet is delivered at this router; the grid
        checks the delivery position and handles neighbor/off-grid mapping.
        """
        _valid, header, _src, _dst, _inj = self.buffer
        out = first_field(header, self.max_hops)
        return out, shift(header, self.max_hops)

    def latch(self):
        """Latches the sole valid input into the buffer (or idles).

        The grid fails the run before latching when 2+ valid inputs arrive,
        so latch only ever sees 0 or 1; defensively, 2+ latches nothing.
        """
        valid = self.valid_inputs()
        self.buffer = valid[0] if len(valid) == 1 else None
