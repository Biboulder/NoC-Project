"""SVG visualization of a schedule: an animated viewport plus a static
flipbook, one grid per clock cycle.

Each packet (canonical choice per row, matching Grid.run) is a colored point
that moves from source to destination along the wires — one wire per clock
cycle. When it reaches the destination it vanishes, and it reappears at its
source when the schedule period repeats. The wire the packet is currently
traversing is highlighted, so the occupied wires are visible at a glance.

The animated viewport glides every point continuously along its route (SMIL
animateMotion); the static flipbook snapshots the traffic at every cycle —
each point sits mid-wire on the link it is traversing, so scanning frames
shows it moving along the route, with the traversed wire lit. Colors are
per destination. One period covers cycles 0..last occupied slot
(injections plus the drain tail) and repeats; the animation flip period is
parameterized.
"""

from .grid import neighbor_of, node_position

__all__ = ["render_svg"]

_PALETTE = [
    "#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e",
    "#17becf", "#e377c2", "#7f7f7f", "#bcbd22", "#8c564b",
    "#393b79", "#c49c94",
]


def _center(n, cell, title_h, margin, x, y):
    return (margin + x * cell, title_h + margin + y * cell)


def _grid_circles(n, cell, margin, radius, title_h):
    """Router circles + labels, shared by every frame and the viewport."""
    parts = []
    for y in range(n):
        for x in range(n):
            cx, cy = _center(n, cell, title_h, margin, x, y)
            label = y * n + x + 1
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" '
                f'fill="#f0f0f0" stroke="#555555" stroke-width="1.5"/>'
            )
            parts.append(
                f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="{radius}" '
                f'text-anchor="middle" dominant-baseline="central">{label}</text>'
            )
    return "".join(parts)


def _packet_pts(n, cell, margin, title_h, e):
    """Pixel centers of every router along an entry's route (source first)."""
    x, y = node_position(n, e.node)
    ppts = [_center(n, cell, title_h, margin, x, y)]
    for d in e.route:
        x, y = neighbor_of(n, x, y, d)
        ppts.append(_center(n, cell, title_h, margin, x, y))
    return ppts


def _frame(schedule, c, cell, margin, radius, title_h, cap_h, fw, fh, glide_ms):
    """One cycle snapshot in frame-local coordinates (0,0)-(fw,fh).

    Traffic is animated in place: a packet with hop k at this cycle
    (k = c - clock, 0 = injection) glides along the wire (k-1 -> k) it is
    traversing, looping — fading out as it arrives at the router and
    reappearing at the wire's start, so every frame shows the flow. The
    wire is lit while traversed; the packet starts at the source (k = 0,
    static) and is gone the cycle after k = h (delivered). Wires are never
    shared in a collision-free schedule, so no offsetting is needed.
    """
    n = schedule.grid
    rows = schedule.rows()
    parts = [
        f'<rect x="0" y="0" width="{fw}" height="{fh}" fill="#fdfdfd" '
        f'stroke="#cccccc" stroke-width="1"/>',
        f'<text x="{margin}" y="16" font-size="12" font-weight="bold">cycle {c}</text>',
    ]
    parts.append(_grid_circles(n, cell, margin, radius, title_h))

    wires = []
    points = []  # static (k = 0: just injected)
    movers = []  # (start, end, color): glide along the lit wire
    in_flight = 0
    for (node, clock), alts in rows.items():
        e = alts[0]  # canonical choice, same as Grid.run
        h = len(e.route)
        k = c - e.clock
        if not 0 <= k <= h:
            continue
        in_flight += 1
        color = _PALETTE[(e.dest - 1) % len(_PALETTE)]
        ppts = _packet_pts(n, cell, margin, title_h, e)
        if k == 0:
            points.append((*ppts[0], color))
        else:
            a, b = ppts[k - 1], ppts[k]
            wires.append((a, b, color))
            movers.append((a, b, color))

    for p1, p2, color in wires:
        parts.append(
            f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
            f'stroke="{color}" stroke-width="3" opacity="0.55"/>'
        )
    for px, py, color in points:
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{max(3, radius // 2)}" '
            f'fill="{color}" stroke="#ffffff" stroke-width="1"/>'
        )

    dur = glide_ms / 1000.0
    for a, b, color in movers:
        path = f"M {a[0]:.1f},{a[1]:.1f} L {b[0]:.1f},{b[1]:.1f}"
        parts.append(
            f'<circle r="{max(3, radius // 2)}" fill="{color}" stroke="#ffffff" stroke-width="1">'
            f'<animateMotion dur="{dur:.3f}s" repeatCount="indefinite" calcMode="linear" '
            f'path="{path}"/>'
            f'<animate attributeName="opacity" values="0;1;1;0" '
            f'keyTimes="0;0.02;0.98;1" dur="{dur:.3f}s" repeatCount="indefinite"/>'
            f'</circle>'
        )

    n_inj = sum(1 for (node, clock), alts in rows.items() if clock == c)
    caption = f"{in_flight} in flight" + (f", {n_inj} injected" if n_inj else "")
    parts.append(
        f'<text x="{margin}" y="{fh - 5}" font-size="10" fill="#333333">'
        f"c{c}: {caption}</text>"
    )
    return "".join(parts)


def render_svg(schedule, flip_ms=1200):
    n = schedule.grid
    # Cycles 0..last occupied slot: injections plus the real drain tail
    # (a max_hops-length route from max_clock would be a conservative
    # over-estimate that leaves empty frames at the end).
    frames = max((e.clock + len(e.route) for e in schedule.entries), default=0) + 1
    if flip_ms <= 0:
        raise ValueError(f"flip_ms must be > 0, got {flip_ms}")

    cell = min(90, max(40, 240 // n))
    margin = 26
    radius = max(9, cell // 5)
    gap = 30
    title_h = 24
    cap_h = 15
    cols = min(4, frames)
    fw = n * cell + 2 * margin
    fh = n * cell + 2 * margin + title_h + cap_h
    grid_rows = (frames + cols - 1) // cols
    flip_width = cols * fw + (cols - 1) * gap
    flip_height = grid_rows * fh + (grid_rows - 1) * gap

    top = 46
    static_y = top + fh + 34
    width = max(fw, flip_width)
    height = static_y + flip_height

    rows = schedule.rows()

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="monospace">',
        f'<text x="12" y="18" font-size="14" font-weight="bold">grid {n}x{n}, '
        f"{frames} cycles per period (repeats), {len(schedule.entries)} alternatives"
        f"</text>",
        f'<text x="12" y="38" font-size="11" fill="#666666">animated (flip {flip_ms} ms):</text>',
    ]

    # --- Animated viewport: one point per packet gliding source -> dest,
    # --- one wire per clock cycle; it vanishes at the destination and
    # --- reappears at its source when the period repeats. A faint dashed
    # --- track shows each packet's full route. ---
    cycle = flip_ms / 1000.0
    total = frames * cycle
    eps = 1e-3
    parts.append(f'<g transform="translate(0,{top})">')
    parts.append(
        f'<rect x="0" y="0" width="{fw}" height="{fh}" fill="#fdfdfd" '
        f'stroke="#cccccc" stroke-width="1"/>'
    )
    parts.append(_grid_circles(n, cell, margin, radius, title_h))
    for (node, clock), alts in rows.items():
        e = alts[0]  # canonical choice, same as Grid.run
        h = len(e.route)
        color = _PALETTE[(e.dest - 1) % len(_PALETTE)]
        ppts = _packet_pts(n, cell, margin, title_h, e)
        track = " ".join(f"{px:.1f},{py:.1f}" for px, py in ppts)
        path = "M " + " L ".join(f"{px:.1f},{py:.1f}" for px, py in ppts)
        t0 = clock / frames          # injection: appears at the source
        t_arr = (clock + h) / frames  # arrives at the destination
        t_gone = (clock + h + 1) / frames  # delivered: vanishes

        parts.append(
            f'<polyline points="{track}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" opacity="0.15" stroke-dasharray="3,3"/>'
        )
        # Motion: fraction 0 (source) until t0, glide 0 -> 1 over
        # [t0, t_arr] (one wire per cycle), hold at the destination.
        if t0 > 0:
            kp = "0;0;1;1"
            kt_m = f"0;{t0:.4f};{t_arr:.4f};1"
        else:
            kp = "0;1;1"
            kt_m = f"0;{t_arr:.4f};1"
        # Opacity: invisible outside [t0, t_gone], with a tiny ramp so the
        # keyTimes stay strictly increasing.
        kt_o = [0.0]
        vals = [1.0 if t0 <= 0 else 0.0]
        if t0 > 0:
            kt_o.append(t0)
            vals.append(0.0)
        kt_o.append(min(t0 + eps, t_gone))
        vals.append(1.0)
        kt_o.append(max(t_gone - eps, t0))
        vals.append(1.0)
        kt_o.append(t_gone)
        vals.append(0.0)
        kt_o.append(1.0)
        vals.append(0.0)
        kt_str = ";".join(f"{t:.4f}" for t in kt_o)
        val_str = ";".join(f"{v:g}" for v in vals)
        parts.append(
            f'<circle r="{max(3, radius // 2)}" fill="{color}" stroke="#ffffff" stroke-width="1">'
            f'<animateMotion dur="{total:.3f}s" repeatCount="indefinite" calcMode="linear" '
            f'path="{path}" keyPoints="{kp}" keyTimes="{kt_m}"/>'
            f'<animate attributeName="opacity" values="{val_str}" '
            f'keyTimes="{kt_str}" dur="{total:.3f}s" repeatCount="indefinite"/>'
            f'</circle>'
        )
    parts.append("</g>")

    # --- Static flipbook: every cycle snapshot visible at once. ---
    parts.append(
        f'<text x="12" y="{static_y - 6}" font-size="11" fill="#666666">static flipbook:</text>'
    )
    parts.append(f'<g transform="translate(0,{static_y})">')
    for c in range(frames):
        fx = (c % cols) * (fw + gap)
        fy = (c // cols) * (fh + gap)
        parts.append(
            f'<g transform="translate({fx},{fy})">{_frame(schedule, c, cell, margin, radius, title_h, cap_h, fw, fh, flip_ms)}</g>'
        )
    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
