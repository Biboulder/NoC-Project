To send a packet through a grid of routers consisting of N,S,E,W,L outputs, we would need 3 bits for each direction.

This means, if the grid is 3x3, then the maximum distance (manhattan distance), would be 4, which means 12 bits are needed for the header.

By creating an enum: {NORTH 001, SOUTH 010, EAST 011, WEST 100, LOCAL 000}, where local means the routers output.

If the routers read the first 3 bits to determine destination, and after reading the header, the router sends the whole header shifted 3 bits left, the consumed 3 bits are deleted and zeros are shifted in at the tail.

LOCAL (000) is never coded into the header by the sender. A North->East route only needs 6 real header bits (2 fields); the header is zero-padded at injection to the provisioned width of 12 bits (4 fields, the 3x3 max manhattan distance). Since zero is never a real direction, the first zero-filled field a router reads is LOCAL, which terminates the routing, assuming correct routing.

## Wire format

Each router-to-router link carries a separate valid bit alongside the
packet:

```
router A              router B
        valid ────────►
        packet[43:0] ─►   header[11:0] | payload[31:0]
```

The 44-bit packet is a fixed 12-bit header (grid-provisioned) followed by a
full 32-bit payload word: `packet[43:32]` is the header (`header[11:0]`,
MSB-first — bit 43 is the first direction field), `packet[31:0]` is the
payload. The valid bit is NOT part of the packet; it tells the receiver
whether the data lines carry a real packet:

```
  valid │ packet[43:0]
  ──────┼─────────────────────────────────────────────
    1   │ 001 011 000 000 │ payload   ← real packet; the header is decoded,
        │                              even when it is fully nulled (LOCAL
        │                              delivery in progress)
    0   │ 000 000 000 000 │ 00000000  ← idle link; data lines are don't-care
        │                              (driven to 0), nothing is decoded
```

Without the valid bit, an idle link driving all zeros would be
indistinguishable from a packet whose header has been fully nulled — i.e.
a LOCAL-terminated packet — causing spurious deliveries.

## Router buffering (send and receive simultaneously)

Each router registers its input: at every rising clock edge it latches the
incoming (valid, packet) pair into an input buffer. The output is
combinational logic over that buffered input — the router drives its output
from the *previous* clock cycle's input:

```
                  ┌─────────────────────────────────────┐
                  │               ROUTER                │
 valid_in ───────►│  ┌────────────┐  ┌───────────────┐  │──────► valid_out
 pkt_in[43:0] ───►│  │ input      │  │ decode +      │  │──────► pkt_out[43:0]
                  │  │ buffer     ├─►│ shift (comb.) │  │
                  │  │ (register) │  │               │  │
                  │  └────────────┘  └───────────────┘  │
                  └─────────────────────────────────────┘
```

Consequence: during any cycle the router transmits the packet it received
the previous cycle while simultaneously accepting a new one — it never
stalls on its own output. Per-hop latency is 1 clock cycle; throughput is
1 packet per cycle.

```
clock cycle               N        N+1      N+2      N+3
--------------------------------------------------------------
input (valid, packet)     pkt A    pkt B    pkt C    pkt D
                          v edge   v edge   v edge   v edge
--------------------------------------------------------------
input buffer                -      pkt A    pkt B    pkt C
output (valid, packet)      -      A'       B'       C'
```

A' is pkt A after decode + shift: the header is read (header[11:9] selects
the output port), shifted left 3, and the result driven on the output — all
from the buffered copy, so the input stays free to accept pkt B in the same
cycle.

## Scheduler

A hardcoded, repeating schedule table guarantees that no two packets ever
target the same link in the same slot — collisions and arbitration are
avoided by construction. The table is generated offline from the routing
rules (routing.md): BFS from every node with coin-flip collision
resolution; the router itself performs no runtime arbitration.

## ASCII visualization

### Header: North, East + payload (no explicit LOCAL)

A North->East route codes in 6 real header bits; the sender pads to the
provisioned 12-bit slot with zeros. The (null) fields read as LOCAL:

```
+----------------+----------------+----------------+----------------+------------------+
| hop 1 (NORTH)  |  hop 2 (EAST)  |     (null)     |     (null)     |     payload      |
|      001       |      011       |      000       |      000       |     32 bits      |
+----------------+----------------+----------------+----------------+------------------+
```

### Shift for each router

Every router reads the first 3 bits (next direction), routes accordingly,
then shifts the whole header left by 3 bits, shifting zeros in at the tail:

```
+----------------+----------------+----------------+----------------+------------------+
|      001       |      011       |      000       |      000       |     payload      |
+----------------+----------------+----------------+----------------+------------------+
  |
  v  router 1: reads 001 = NORTH, routes N, shifts header left 3 (0s in)

+----------------+----------------+----------------+----------------+------------------+
|      011       |      000       |      000       |      000       |     payload      |
+----------------+----------------+----------------+----------------+------------------+
  |
  v  router 2: reads 011 = EAST, routes E, shifts header left 3 (0s in)

+----------------+----------------+----------------+----------------+------------------+
|      000       |      000       |      000       |      000       |     payload      |
+----------------+----------------+----------------+----------------+------------------+
  |
  v  router 3: reads 000 = LOCAL (nothing coded), terminates, delivers payload
```

### Nulled header

At the destination all direction slots are zero; the header carries no
further routing information and the payload is delivered to the local
output:

```
+----------------+----------------+----------------+----------------+------------------+
|     hop 1      |     hop 2      |     hop 3      |     hop 4      |     payload      |
|      000       |      000       |      000       |      000       |    delivered     |
+----------------+----------------+----------------+----------------+------------------+
```
