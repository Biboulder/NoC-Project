Some rules need to be agreed upon to make a router. These are the following:

1. A router may only send and receive one packet each clock. If two packets are received from e.g. North and East (2 or more enable pins), then there is a collision.
2. A router buffers data for 1 clock cycle. The buffer is a pipeline stage, not state: it lets the router send the previous cycle's packet while accepting a new one, and bounds each hop's combinational path.
3. Routers have no routing state; they just forward according to the packet information.
4. Packets can only hop 4 times.
5. We arrange in a 3x3 grid.
6. Outside of the network/grid, we assume that each node, which can inject data into the network, follows a time-divided schedule. This means each node can send only one packet per clock.


Schedule table is the following format, and it is unique for each input node. This is why source is not specified.

`dest nodes` lists the destinations the node may send to at that clock; the node sends one packet to exactly one of them (rule 1). Each `routes` entry is the matching hop sequence for that destination, abbreviated: N = NORTH, NW = NORTH,WEST, SSE = SOUTH,SOUTH,EAST, etc. Routes never exceed 4 hops (rule 4) and are encoded verbatim as header fields (NSEW_packet.md).

| Clock (c) | Destination nodes | Routes |
|:---:|---|---|
| 0 | 1, 2, 4 | `N`, `NW`, `SSE` |
| 1 | 3, 5, 4 | `S`, `EES`, `SSE` |
| ... | ... | ... |
| n | 1, 2, 4 | `E`, `E`, `NE` |


Naive schedule table is to let each node communicate once over a 4 cycle period (since each packet can have a max of 4 jumps). This means each node can talk to another node every 9 * 4 = 36 cycles.


Current idea is to run BFS from all nodes to all nodes. When a collision happens, flip a coin and pick one; let the other route die and let it try again in a later iteration. Iterate until all nodes have a path. This pass is the offline generator of the hardcoded schedule table (NSEW_packet.md); collisions are resolved at design time, so the router never arbitrates.

