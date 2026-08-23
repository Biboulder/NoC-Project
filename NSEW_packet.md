To send a packet through a grid of routers consisting of N,S,E,W,L outputs, we would need 3 bits for each direction.

This means, if the grid is 3x3, then the maximum distance (manhattan distance), would be 4, which means 12 bits are needed for the header.

By creating an enum: {NORTH 001, SOUTH 010, EAST 011, WEST 100, LOCAL 000}, where local means the routers output.

If the routers read the first 3 bits to determine destination, and after reading the header, the router sends the whole header shifted 3 bits left, the consumed 3 bits are deleted and zeros are shifted in at the tail.

LOCAL (000) is never coded into the header by the sender. A North->East route only needs 6 real header bits (2 fields); the header is zero-padded at injection to the provisioned width of 12 bits (4 fields, the 3x3 max manhattan distance). Since zero is never a real direction, the first zero-filled field a router reads is LOCAL, which terminates the routing, assuming correct routing.

"visualize in ascii |header for 2 routes (North, East)| + |payload|"

"visualize the shift for each router"

"visualize the nulled header"

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
