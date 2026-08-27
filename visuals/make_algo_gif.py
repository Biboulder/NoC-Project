#!/usr/bin/env python3
"""Animate the offline scheduler's first (clock-0) pass as a looping GIF.

Replays ``generate_bruteforce(3, seed=0, pack=row|none)`` deterministically
and renders the pass-0 event trace: pairs are tried longest-distance-first,
each candidate path shortest-first; a collision flashes red on the exact
router/link and the path dies, a fit flashes and is committed to the mesh.
The first 10 pairs play in detail, the remaining 62 fast-forward, and an
outro shows the pass totals. Colors match the interactive schedule SVGs
(visualize.py); committed paths are colored by destination (packet hue
convention) with per-path dash phases so overlapping routes stay distinct.

pack row:  same-source rows hold mutually-exclusive alternatives.
pack none: strict disjointness — one entry per (node, clock) row; a source
           that already fired blocks itself until the next clock.

Usage:  python3 visuals/make_algo_gif.py [--pack row|none] [--out FILE]
"""

import argparse
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routing.generator import _all_paths, generate_bruteforce
from routing.grid import node_id, node_position, neighbor_of, slot_map
from routing.header import route_str
from routing.visualize import _DARK_PALETTE

# --------------------------------------------------------------------------
#  Trace: replay pass 0 (clock offset 0) with global-min collision reporting
# --------------------------------------------------------------------------

N, SEED = 3, 0
DETAIL_PAIRS = 10  # pairs played in detail; the rest fast-forward

# --- palette (house style, see routing/visualize.py) ---
BG = (13, 17, 23)          # #0d1117
PANEL = (22, 27, 34)       # #161b22
STROKE = (48, 54, 61)      # #30363d
WIRE = (33, 38, 45)        # #21262d
TXT = (201, 209, 217)      # #c9d1d9
TXT_BRIGHT = (230, 237, 243)  # #e6edf3
TXT_DIM = (139, 148, 158)  # #8b949e
CYAN = (77, 171, 247)      # #4dabf7  testing
RED = (255, 107, 107)      # #ff6b6b  collision / died
GOLD = (255, 224, 102)     # #ffe066  commit flash / accents
WHITE = (255, 255, 255)

# ImageDraw writes RGBA colors verbatim (no alpha compositing), so
# translucency must be pre-blended against the opaque background.
def blend(color, a, base=BG):
    return tuple(round(color[i] * a / 255 + base[i] * (255 - a) / 255)
                 for i in range(3))

# destination hues: packets are colored by destination (visualize.py rule)
HUE_RGB = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in _DARK_PALETTE]


def dest_hue(d):
    return HUE_RGB[(d - 1) % len(HUE_RGB)]


W, H = 960, 620
FPS = 12
DUR = 1000 // FPS

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = font("DejaVuSans-Bold.ttf", 16)
F_SUB = font("DejaVuSans.ttf", 11)
F_BODY = font("DejaVuSans.ttf", 14)
F_SMALL = font("DejaVuSans.ttf", 12)
F_CAPS = font("DejaVuSans-Bold.ttf", 11)
F_PAIR = font("DejaVuSans-Bold.ttf", 18)
F_VERDICT = font("DejaVuSans-Bold.ttf", 14)
F_NUM = font("DejaVuSans-Bold.ttf", 22)
F_HINT = font("DejaVuSans.ttf", 11)
F_TINY = font("DejaVuSans.ttf", 10)

_CAPTIONS = {
    "row": ("same-source clock-0 rows are alternatives —",
            "only one fires per cycle"),
    "none": ("pack none — strict disjointness · one entry per row",
             "same source blocks itself until the next clock"),
}
_EXTRA_HOW = {
    "row": "· same-row alternatives share slots — one fires",
    "none": "· same source blocks itself until the next clock",
}


def build(pack):
    """Replay generate_bruteforce pass 0; returns a context dict."""
    skip_row = pack == "row"
    rng = random.Random(SEED)
    by_pair = _all_paths(N)
    for lens in by_pair.values():
        for routes in lens.values():
            rng.shuffle(routes)

    labels = range(1, N * N + 1)
    by_dist = {}
    for s in labels:
        sx, sy = node_position(N, s)
        for d in labels:
            if d == s:
                continue
            dx, dy = node_position(N, d)
            by_dist.setdefault(abs(dx - sx) + abs(dy - sy), []).append((s, d))
    order = []
    for dist in sorted(by_dist, reverse=True):
        rng.shuffle(by_dist[dist])
        order.extend(by_dist[dist])

    committed = []       # (s, d, clock, route)
    committed_slots = []
    trace = []           # per pair: list of events

    def global_conflict(cand, s, o):
        best = None
        for ce, cslots in zip(committed, committed_slots):
            if skip_row and ce[0] == s and ce[2] == o:
                continue
            shared = cand.keys() & cslots.keys()
            if shared:
                k = min(shared)
                if best is None or k < best[0]:
                    best = (k, ce)
        return best

    offset = 0
    for s, d in order:
        events = []
        placed = False
        for L in sorted(by_pair[(s, d)]):
            for route in by_pair[(s, d)][L]:
                cand = slot_map(N, s, offset, route)
                hit = global_conflict(cand, s, offset)
                if hit is None:
                    committed.append((s, d, offset, route))
                    committed_slots.append(cand)
                    events.append({"kind": "commit", "route": route,
                                   "hops": len(route)})
                    placed = True
                    break
                key, foe = hit
                cycle, res = key
                fx, fy = res % N, res // N
                desc = f"router {node_id(N, fx, fy)}"
                res_pts = [(fx, fy), None]
                events.append({
                    "kind": "die", "route": route,
                    "hops": cycle,          # cycle == hop index at clock 0
                    "desc": desc, "res_pts": res_pts,
                    "foe": (foe[0], foe[1]),
                })
            if placed:
                break
        if not placed:
            events.append({"kind": "defer"})
        trace.append((s, d, events, placed))

    # Verify the replay against the real generator's clock-0 rows.
    real, stats = generate_bruteforce(N, SEED, pack=pack)
    real0 = sorted((e.node, e.dest, e.route) for e in real.entries
                   if e.clock == 0)
    mine0 = sorted((s, d, e["route"]) for (s, d, evs, p) in trace
                   for e in evs if e["kind"] == "commit")
    assert real0 == mine0, "replay diverged from generate_bruteforce"

    # Per-run lane assignment: each maximal straight run of a path keeps one
    # lane (no jump at straight-through routers); 90° turns join via a miter
    # cut. On any segment, runs to different destinations get distinct lanes;
    # same-destination runs may share.
    lane_vals = [(ln - 5.5) * 6 for ln in range(12)]  # ±3 .. ±33 px (9 dests max)
    seg_owner = {}   # segment -> {lane_px: dest}
    lanes = {}       # (s, d) -> list of px offsets, one per segment
    for s, d, _c, route in committed:
        x, y = node_position(N, s)
        pts = [(x, y)]
        for dirc in route:
            x, y = neighbor_of(N, x, y, dirc)
            pts.append((x, y))
        segs = list(zip(pts, pts[1:]))

        def vec(sg):
            return (sg[1][0] - sg[0][0], sg[1][1] - sg[0][1])

        runs = [[0]]
        for k in range(1, len(segs)):
            if vec(segs[k]) == vec(segs[k - 1]):
                runs[-1].append(k)
            else:
                runs.append([k])
        offs = [0] * len(segs)
        for run in runs:
            used = set()
            for k in run:
                seg = tuple(sorted(segs[k]))
                used |= {lp for lp, od in seg_owner.get(seg, {}).items()
                         if od != d}
            lane_px = next(lp for lp in lane_vals if lp not in used)
            for k in run:
                seg = tuple(sorted(segs[k]))
                seg_owner.setdefault(seg, {})[lane_px] = d
                offs[k] = lane_px
        lanes[(s, d)] = offs

    # Dash rhythm per path: extra texture on shared center-lane flows.
    rhythms = [(14, 10), (10, 14), (16, 8), (8, 16), (12, 12),
               (18, 6), (6, 18), (15, 9), (9, 15)]
    dash_rhythm = {(s, d): rhythms[(s * 7 + d * 13) % len(rhythms)]
                   for s, d, _c, _r in committed}
    return {"pack": pack, "order": order, "trace": trace, "stats": stats,
            "lanes": lanes, "rhythms": dash_rhythm}


# --------------------------------------------------------------------------
#  Geometry
# --------------------------------------------------------------------------

OX, OY = 56, 104          # mesh origin
CELL = 140
RAD = 26
PANEL_X = 510


def center(x, y):
    return (OX + x * CELL, OY + y * CELL)


def route_pts(route, s):
    """Router-center pixels along a route, source first."""
    x, y = node_position(N, s)
    pts = [center(x, y)]
    for d in route:
        x, y = neighbor_of(N, x, y, d)
        pts.append(center(x, y))
    return pts


def _perp(p, q):
    """Unit perpendicular to segment p->q, pointing toward the mesh interior
    (direction-invariant: depends only on the segment's position)."""
    x1, y1 = p
    x2, y2 = q
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (y2 - y1) / L, -(x2 - x1) / L
    midx = OX + (N - 1) / 2 * CELL
    midy = OY + (N - 1) / 2 * CELL
    if abs(ux) > abs(uy):  # vertical segment -> horizontal perp
        return (1.0, 0.0) if x1 <= midx else (-1.0, 0.0)
    return (0.0, 1.0) if y1 <= midy else (0.0, -1.0)


def offset_pts(pts, lanes):
    """Offset polyline: lanes applied per segment, miter cuts at 90° turns,
    collinear runs continuing on the same lane through routers."""
    n = len(pts)
    perps = [_perp(pts[k], pts[k + 1]) for k in range(n - 1)]
    verts = [(pts[0][0] + perps[0][0] * lanes[0],
              pts[0][1] + perps[0][1] * lanes[0])]
    for k in range(1, n - 1):
        vx, vy = pts[k]
        din = (pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
        dout = (pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
        if din == dout:
            mx = vx + perps[k][0] * lanes[k]
            my = vy + perps[k][1] * lanes[k]
        else:
            mx = vx + perps[k - 1][0] * lanes[k - 1] + perps[k][0] * lanes[k]
            my = vy + perps[k - 1][1] * lanes[k - 1] + perps[k][1] * lanes[k]
        verts.append((mx, my))
    verts.append((pts[-1][0] + perps[-1][0] * lanes[-1],
                  pts[-1][1] + perps[-1][1] * lanes[-1]))
    return verts


def dash_poly(draw, pts, color, width, dash=14, gap=10, phase=0, lanes=None):
    """Straight dashed polyline; ``lanes`` is one constant px offset per
    segment (perpendicular), so each segment is a straight parallel lane."""
    run = phase
    prev = pts[0]
    k = 0
    for p in pts[1:]:
        lane = lanes[k] if lanes else 0
        k += 1
        x1, y1 = prev
        x2, y2 = p
        L = math.hypot(x2 - x1, y2 - y1)
        if L == 0:
            continue
        ux, uy = _perp(prev, p)
        t = 0.0
        while t < L:
            c = (run + t) % (dash + gap)
            if c < dash:
                t2 = min(t + (dash - c), L)
                q1, q2 = t / L, t2 / L
                draw.line([(x1 + (x2 - x1) * q1 + ux * lane,
                            y1 + (y2 - y1) * q1 + uy * lane),
                           (x1 + (x2 - x1) * q2 + ux * lane,
                            y1 + (y2 - y1) * q2 + uy * lane)],
                          fill=color, width=width)
                t = t2
            else:
                t += (dash + gap) - c
        run += L
        prev = p


def arrowhead(draw, start, tip, color, size=11, half=5):
    """Triangle from ``start`` (lane end) into ``tip`` (router center)."""
    dx, dy = tip[0] - start[0], tip[1] - start[1]
    L = math.hypot(dx, dy)
    if L < 3:
        return
    ux, uy = dx / L, dy / L
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    px, py = -uy * half, ux * half
    draw.polygon([tip, (bx + px, by + py), (bx - px, by - py)], fill=color)


def draw_routers(draw):
    """Router circles + labels; drawn again on top of committed lanes so
    lanes vanish under the nodes at segment ends and corners read as hops."""
    for y in range(N):
        for x in range(N):
            cx, cy = center(x, y)
            draw.ellipse([cx - RAD, cy - RAD, cx + RAD, cy + RAD],
                         fill=(33, 38, 45), outline=STROKE, width=2)
            lbl = str(node_id(N, x, y))
            draw.text((cx, cy), lbl, font=F_BODY, fill=TXT, anchor="mm")


def draw_chrome(draw, ctx, pair_idx, counters, mode):
    """Static chrome: title bar, mesh, panel frames, legend, progress."""
    draw.rectangle([0, 0, W, H], fill=BG)
    # Title bar.
    draw.rectangle([0, 0, W, 52], fill=PANEL)
    draw.line([(0, 52), (W, 52)], fill=STROKE, width=1)
    draw.text((14, 11), "EDU4CHIP ROUTER — OFFLINE SCHEDULER",
              font=F_TITLE, fill=TXT_BRIGHT)
    draw.text((14, 33),
              f"greedy slot placement  ·  grid 3×3  ·  seed {SEED}  ·  "
              f"pack {ctx['pack']}",
              font=F_SUB, fill=TXT_DIM)
    draw.text((W - 14, 13), "CLOCK-0 PASS", font=F_TITLE, fill=GOLD,
              anchor="ra")
    draw.text((W - 14, 35), "paths tested · die · commit",
              font=F_SUB, fill=TXT_DIM, anchor="ra")

    # Mesh links.
    for y in range(N):
        for x in range(N):
            cx, cy = center(x, y)
            if x + 1 < N:
                nx, ny = center(x + 1, y)
                draw.line([(cx, cy), (nx, ny)], fill=WIRE, width=4)
            if y + 1 < N:
                nx, ny = center(x, y + 1)
                draw.line([(cx, cy), (nx, ny)], fill=WIRE, width=4)

    # Routers.
    draw_routers(draw)

    cap1, cap2 = _CAPTIONS[ctx["pack"]]
    cap_y = OY + 2 * CELL + RAD + 20
    draw.text((OX, cap_y), cap1, font=F_HINT, fill=TXT_DIM)
    draw.text((OX, cap_y + 14), cap2, font=F_HINT, fill=TXT_DIM)

    # Panel.
    draw.rectangle([PANEL_X, 74, W - 20, H - 96], fill=PANEL,
                   outline=STROKE, width=1)
    draw.text((PANEL_X + 16, 90), "PASS 1 · CLOCK 0", font=F_CAPS,
              fill=TXT_DIM)
    draw.text((PANEL_X + 16, 112), "PAIR", font=F_CAPS, fill=TXT_DIM)
    draw.text((PANEL_X + 16, 132),
              f"{pair_idx:>2}  →  {ctx['order'][pair_idx - 1][1]}",
              font=F_PAIR, fill=TXT_BRIGHT)

    # Counters.
    cw, ch, gap = 108, 46, 12
    cx0 = PANEL_X + 16
    for i, (key, col) in enumerate(zip(("committed", "died", "deferred"),
                                       (GOLD, RED, TXT_DIM))):
        bx = cx0 + i * (cw + gap)
        draw.rectangle([bx, 236, bx + cw, 236 + ch], fill=(17, 22, 29),
                       outline=STROKE, width=1)
        draw.text((bx + cw / 2, 236 + 13), str(counters[key]),
                  font=F_NUM, fill=col, anchor="mm")
        draw.text((bx + cw / 2, 236 + 38), key.upper(), font=F_SMALL,
                  fill=TXT_DIM, anchor="mm")

    # How it works.
    hy = 306
    draw.text((PANEL_X + 16, hy), "HOW IT WORKS", font=F_CAPS, fill=TXT_DIM)
    for i, line in enumerate([
            "· pairs tried longest-distance first",
            "· each pair tests paths shortest → longest",
            "· collision ⇒ path dies · fit ⇒ committed",
            _EXTRA_HOW[ctx["pack"]]]):
        draw.text((PANEL_X + 16, hy + 22 + i * 20), line, font=F_SMALL,
                  fill=TXT_DIM)

    # Legend + destination hues.
    ly = 396
    draw.text((PANEL_X + 16, ly), "LEGEND", font=F_CAPS, fill=TXT_DIM)
    for i, (col, label) in enumerate([
            (WHITE, "testing a path"),
            (RED, "collision · path dies"),
            (GOLD, "fit — flash, then committed")]):
        lx = PANEL_X + 16 + (i % 2) * 190
        lyr = ly + 24 + (i // 2) * 26
        draw.ellipse([lx, lyr, lx + 10, lyr + 10], fill=col)
        draw.text((lx + 18, lyr + 5), label, font=F_SMALL, fill=TXT,
                  anchor="lm")
    draw.text((PANEL_X + 16, 472), "DEST HUES", font=F_CAPS, fill=TXT_DIM)
    for d in range(1, N * N + 1):
        dx = PANEL_X + 16 + 76 + (d - 1) * 18
        draw.ellipse([dx, 474, dx + 11, 485], fill=dest_hue(d))
        draw.text((dx + 5, 492), str(d), font=F_TINY, fill=TXT_DIM,
                  anchor="ma")

    # Progress bar.
    n_pairs = len(ctx["order"])
    py = H - 52
    draw.text((14, py - 18), "CLOCK-0 PASS PROGRESS", font=F_CAPS,
              fill=TXT_DIM)
    draw.text((W - 14, py - 18), mode, font=F_CAPS, fill=TXT_DIM, anchor="ra")
    draw.rectangle([14, py, W - 14, py + 12], fill=PANEL, outline=STROKE,
                   width=1)
    fill_w = int((W - 30) * pair_idx / n_pairs)
    if fill_w > 0:
        draw.rectangle([16, py + 2, 16 + fill_w, py + 10], fill=GOLD)
    draw.text((W - 14, py + 6), f"{pair_idx:>2} / {n_pairs}",
              font=F_CAPS, fill=TXT, anchor="rm")


def commit_entry(ctx, s, d, pts):
    dash, gap = ctx["rhythms"][(s, d)]
    return {"s": s, "d": d, "pts": pts, "hue": dest_hue(d),
            "seg_lanes": ctx["lanes"][(s, d)], "dash": dash, "gap": gap}


def draw_committed(draw, committed, glow_idx=None, glow_age=0):
    """Committed paths: straight offset lanes with miter corners, drawn over
    the routers (the path hops through nodes — original look)."""
    for i, ent in enumerate(committed):
        pts, hue = ent["pts"], ent["hue"]
        seg_lanes = ent.get("seg_lanes") or [0] * (len(pts) - 1)
        vp = offset_pts(pts, seg_lanes)
        if glow_idx == i:
            a = max(60, 200 - glow_age * 35)
            draw.line(vp, fill=blend(WHITE, a), width=7)
            draw.line(vp, fill=hue, width=3)
        else:
            dash_poly(draw, vp, blend(hue, 200), width=3, phase=i * 7,
                      dash=ent.get("dash", 14), gap=ent.get("gap", 10))
        # short connector from the source router center onto the lane
        draw.line([pts[0], vp[0]], fill=blend(hue, 190), width=2)


def draw_marks(draw, committed):
    """Destination rings + arrowheads, drawn OVER the routers."""
    rings = {}
    for ent in committed:
        rings.setdefault(ent["d"], ent["hue"])
    for d, hue in rings.items():
        x, y = node_position(N, d)
        cx, cy = center(x, y)
        draw.ellipse([cx - RAD - 6, cy - RAD - 6, cx + RAD + 6, cy + RAD + 6],
                     outline=blend(hue, 190), width=2)
    for ent in committed:
        pts, hue = ent["pts"], ent["hue"]
        seg_lanes = ent.get("seg_lanes") or [0] * (len(pts) - 1)
        vp = offset_pts(pts, seg_lanes)
        # arrowhead: from the lane end into the destination router center
        start = vp[-1]
        if math.hypot(start[0] - pts[-1][0], start[1] - pts[-1][1]) < 6:
            p2, p1 = pts[-1], pts[-2]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            L = math.hypot(dx, dy) or 1.0
            start = (p2[0] - dx / L * 12, p2[1] - dy / L * 12)
        arrowhead(draw, start, pts[-1], blend(hue, 230), size=11)


def draw_source_ring(draw, s, age):
    x, y = node_position(N, s)
    cx, cy = center(x, y)
    a = max(60, 220 - age * 40)
    draw.ellipse([cx - RAD - 7, cy - RAD - 7, cx + RAD + 7, cy + RAD + 7],
                 outline=blend(CYAN, a), width=3)


def draw_test_path(draw, pts, head, color=WHITE, alpha=255):
    """Active path up to hop ``head``: white lane, cyan head dot.
    White is used (not cyan) so committed dest-2 paths (cyan) stay distinct.
    A dying path passes ``color=RED`` with decreasing ``alpha`` to fade out."""
    for i in range(1, head + 1):
        draw.line([pts[i - 1], pts[i]], fill=blend(color, max(50, alpha // 2)),
                  width=6)
        draw.line([pts[i - 1], pts[i]], fill=blend(color, alpha), width=2)
    hx, hy = pts[min(head, len(pts) - 1)]
    draw.ellipse([hx - 7, hy - 7, hx + 7, hy + 7], fill=blend(color, alpha))
    draw.ellipse([hx - 4, hy - 4, hx + 4, hy + 4], fill=CYAN)


def draw_collision(draw, res_pts, age):
    """Red pulse at the contested router or link."""
    if res_pts[1] is None:
        x, y = res_pts[0]
        cx, cy = center(x, y)
        r = 32 + age * 4
        a = max(80, 230 - age * 50)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=blend(RED, a),
                     width=5)
        draw.ellipse([cx - RAD - 3, cy - RAD - 3, cx + RAD + 3, cy + RAD + 3],
                     outline=blend(RED, a), width=2)
    else:
        p1 = center(*res_pts[0])
        p2 = center(*res_pts[1])
        a = max(80, 230 - age * 50)
        draw.line([p1, p2], fill=blend(RED, a), width=10)


def draw_verdict(draw, text, color):
    draw.rectangle([PANEL_X + 16, 196, W - 36, 222], fill=PANEL)
    draw.text((PANEL_X + 16, 209), text, font=F_VERDICT, fill=color,
              anchor="lm")


def make_frame(ctx, state):
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    draw_chrome(d, ctx, state["pair_idx"], state["counters"], state["mode"])
    draw_committed(d, state["committed"],
                   glow_idx=state.get("glow_idx"), glow_age=state.get("glow_age", 0))
    draw_marks(d, state["committed"])
    if state.get("src_ring"):
        draw_source_ring(d, state["src_ring"][0], state["src_ring"][1])
    if state.get("test_pts"):
        draw_test_path(d, state["test_pts"], state["head"],
                       color=state.get("test_color", WHITE),
                       alpha=state.get("test_alpha", 255))
    if state.get("collision"):
        draw_collision(d, state["collision"][0], state["collision"][1])
    if state.get("verdict"):
        draw_verdict(d, state["verdict"][0], state["verdict"][1])
    return img.convert("RGB")


def frames_for(ctx, events, committed, counters, pair_idx):
    """Yield frames for one pair's event list (detailed pacing)."""
    s, d = ctx["order"][pair_idx - 1]
    for ev in events:
        kind = ev["kind"]
        if kind == "commit":
            pts = route_pts(ev["route"], s)
            for head in range(1, ev["hops"] + 1):
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — testing", "committed": committed,
                    "src_ring": (s, 0), "test_pts": pts, "head": head,
                    "verdict": (f"trying  {route_str(ev['route'])}", TXT_BRIGHT)})
            committed.append(commit_entry(ctx, s, d, pts))
            counters["committed"] += 1
            for age in range(4):
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — committed", "committed": committed,
                    "glow_idx": len(committed) - 1, "glow_age": age,
                    "verdict": (f"{s} → {d} fits — committed", GOLD)})
            for _ in range(2):
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — committed", "committed": committed,
                    "verdict": (f"{s} → {d} fits — committed", GOLD)})
        elif kind == "die":
            pts = route_pts(ev["route"], s)
            hop = ev["hops"]
            if hop == 0:
                # blocked at the source itself: show the head dot, then flash
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — testing", "committed": committed,
                    "src_ring": (s, 0), "test_pts": pts, "head": 0,
                    "verdict": (f"trying  {route_str(ev['route'])}", TXT_BRIGHT)})
            else:
                for head in range(1, hop + 1):
                    yield make_frame(ctx, {
                        "pair_idx": pair_idx, "counters": counters,
                        "mode": "detail — testing",
                        "committed": committed,
                        "src_ring": (s, 0), "test_pts": pts, "head": head,
                        "verdict": (f"trying  {route_str(ev['route'])}", TXT_BRIGHT)})
            counters["died"] += 1
            for age in range(2):
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — collision", "committed": committed,
                    "src_ring": (s, 1) if hop > 0 else None,
                    "test_pts": pts, "head": hop,
                    "collision": (ev["res_pts"], age),
                    "verdict": (f"collides at {ev['desc']} · step {hop}",
                                RED)})
            for age in range(3):
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — died", "committed": committed,
                    "src_ring": (s, 2) if hop > 0 else None,
                    "test_pts": pts, "head": hop,
                    "test_color": RED, "test_alpha": 255 - age * 85,
                    "collision": (ev["res_pts"], age),
                    "verdict": (f"blocked by {ev['foe'][0]}→{ev['foe'][1]} — dies",
                                RED)})
        else:  # defer
            counters["deferred"] += 1
            for _ in range(4):
                yield make_frame(ctx, {
                    "pair_idx": pair_idx, "counters": counters,
                    "mode": "detail — deferred",
                    "committed": committed,
                    "verdict": ("all paths blocked — retries from clock 1",
                                TXT_DIM)})


def montage_frames(ctx, committed, counters, start_idx):
    """Fast-forward: 2 frames per remaining pair."""
    for k in range(start_idx, len(ctx["order"])):
        s, d, evs, placed = ctx["trace"][k]
        pair_idx = k + 1
        last = evs[-1]
        counters["died"] += sum(1 for e in evs if e["kind"] == "die")
        for f in range(2):
            st = {
                "pair_idx": pair_idx, "counters": counters,
                "mode": "fast-forward", "committed": committed,
            }
            if placed:
                st["verdict"] = (f"{s} → {d}  {route_str(last['route'])} — fits",
                                 GOLD)
            else:
                st["verdict"] = (f"{s} → {d} — blocked, retries clock 1+",
                                 TXT_DIM)
            if placed and f == 0:
                committed.append(
                    commit_entry(ctx, s, d, route_pts(last["route"], s)))
                counters["committed"] += 1
                st["glow_idx"] = len(committed) - 1
                st["glow_age"] = 0
            yield make_frame(ctx, st)
        if not placed:
            counters["deferred"] += 1


def outro_frames(ctx, committed, counters):
    stats = ctx["stats"]
    for _ in range(50):
        img = Image.new("RGBA", (W, H), BG)
        draw = ImageDraw.Draw(img)
        draw_chrome(draw, ctx, len(ctx["order"]), counters, "pass complete")
        draw_committed(draw, committed)
        draw_marks(draw, committed)
        # Summary block over the mesh.
        ox, oy = 40, 150
        draw.rectangle([ox - 16, oy - 26, ox + 430, oy + 150], fill=PANEL,
                       outline=STROKE, width=1)
        draw.text((ox, oy), "CLOCK-0 PASS COMPLETE", font=F_TITLE, fill=GOLD)
        draw.text((ox, oy + 30),
                  f"{counters['committed']} / {len(ctx['order'])} pairs "
                  "committed at clock 0", font=F_BODY, fill=TXT)
        draw.text((ox, oy + 54), f"{counters['deferred']} deferred · "
                  f"{counters['died']} paths died", font=F_BODY, fill=TXT_DIM)
        draw.text((ox, oy + 84), f"full schedule: {stats['passes']} passes · "
                  f"{stats['rows']} rows · {stats['alternatives']} alternatives",
                  font=F_SMALL, fill=TXT_DIM)
        draw.text((ox, oy + 104), f"frame = {stats['frame']} cycles · "
                  "loop plays again", font=F_SMALL, fill=TXT_DIM)
        draw.text((ox, oy + 128), f"regenerate: python3 -m routing generate-bf "
                  f"--grid 3 --seed 0 --pack {ctx['pack']}",
                  font=F_HINT, fill=TXT_DIM)
        yield img.convert("RGB")


def replay(ctx):
    """Replay the whole pass, returning (committed, counters) without frames."""
    committed = []
    counters = {"committed": 0, "died": 0, "deferred": 0}
    for pair_idx in range(1, len(ctx["order"]) + 1):
        s, d, evs, _placed = ctx["trace"][pair_idx - 1]
        for ev in evs:
            k = ev["kind"]
            if k == "commit":
                committed.append(
                    commit_entry(ctx, s, d, route_pts(ev["route"], s)))
                counters["committed"] += 1
            elif k == "die":
                counters["died"] += 1
            else:
                counters["deferred"] += 1
    return committed, counters


def compare(out):
    """Side-by-side screenshot: pack row vs pack none, final clock-0 state."""
    CW, CH = 1180, 700
    img = Image.new("RGBA", (CW, CH), BG)
    d = ImageDraw.Draw(img)
    # Title bar.
    d.rectangle([0, 0, CW, 60], fill=PANEL)
    d.line([(0, 60), (CW, 60)], fill=STROKE, width=1)
    d.text((16, 13), "OFFLINE SCHEDULER — PACKING COMPARISON",
           font=F_TITLE, fill=TXT_BRIGHT)
    d.text((16, 37), "clock-0 pass · grid 3×3 · seed 0 · committed paths "
           "colored by destination", font=F_SUB, fill=TXT_DIM)
    d.text((CW - 16, 13), "PACK ROW  vs  PACK NONE", font=F_TITLE, fill=GOLD,
           anchor="ra")

    pw, ph = 564, 600
    gap = 8
    x0 = 24
    y0 = 74
    crop_box = (26, 74, 366, 420)
    for i, pack in enumerate(("row", "none")):
        ctx = build(pack)
        committed, counters = replay(ctx)
        frame = make_frame(ctx, {
            "pair_idx": len(ctx["order"]), "counters": counters,
            "mode": "pass complete", "committed": committed,
        }).convert("RGB")
        mesh = frame.crop(crop_box)
        scale = 442 / mesh.width
        mesh = mesh.resize((442, round(mesh.height * scale)), Image.LANCZOS)

        px = x0 + i * (pw + gap)
        d.rectangle([px, y0, px + pw, y0 + ph], fill=PANEL, outline=STROKE,
                    width=1)
        d.text((px + 18, y0 + 14), f"PACK {pack.upper()}", font=F_TITLE,
               fill=GOLD)
        d.text((px + 18, y0 + 42),
               f"{counters['committed']} / {len(ctx['order'])} pairs fit at "
               "clock 0", font=F_BODY, fill=TXT_BRIGHT)
        mx = px + (pw - 442) // 2
        my = y0 + 68
        img.paste(mesh, (mx, my))
        # ring around node 7 (0,2) in both panels: source that fires twice (row)
        # vs blocks itself (none)
        n7 = (56 + 0 * CELL, 104 + 2 * CELL)  # full-frame center
        cx = mx + (n7[0] - crop_box[0]) * scale
        cy = my + (n7[1] - crop_box[1]) * scale
        r = (RAD + 8) * scale
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD + (255,),
                  width=3)
        d.text((cx, cy - r - 8), "node 7", font=F_SMALL, fill=GOLD,
               anchor="ma")

        notes = {
            "row": [
                "same-source rows hold alternatives:",
                "· 7→3, 7→2, 7→1 and 7→4 share the (node 7, clock 0) row",
                "· only one fires per cycle (rule 6)",
                f"· {ctx['stats']['rows']} rows · {ctx['stats']['passes']} "
                f"passes · frame {ctx['stats']['frame']} cycles",
            ],
            "none": [
                "strict disjointness — one entry per row:",
                "· 7 fired 7→3 at clock 0; 7→2 waits for clock 2",
                "· each source fires at most once per clock",
                f"· {ctx['stats']['rows']} rows · {ctx['stats']['passes']} "
                f"passes · frame {ctx['stats']['frame']} cycles",
            ],
        }[pack]
        ny = y0 + ph - 8 - len(notes) * 20
        for j, line in enumerate(notes):
            col = TXT if j == 0 else TXT_DIM
            d.text((px + 18, ny + j * 20), line, font=F_SMALL, fill=col)

    # Bottom bar.
    d.rectangle([0, CH - 40, CW, CH], fill=PANEL)
    d.line([(0, CH - 40), (CW, CH - 40)], fill=STROKE, width=1)
    d.text((16, CH - 26), "colors = destination · full run: python3 -m "
           "routing generate-bf --grid 3 --seed 0 --pack row|none",
           font=F_HINT, fill=TXT_DIM)
    img.convert("RGB").save(out)
    print(f"wrote {out}: {CW}x{CH} PNG, {os.path.getsize(out) / 1e6:.1f} MB")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", choices=("row", "none"), default="row")
    ap.add_argument("--out", default=None,
                    help="output GIF (default: schedule_algo.gif for row, "
                         "schedule_algo_none.gif for none)")
    ap.add_argument("--compare", action="store_true",
                    help="write a side-by-side packing comparison PNG instead")
    ap.add_argument("--fps", type=int, default=FPS)
    args = ap.parse_args()

    if args.compare:
        compare(args.out or os.path.join(here, "packing_compare.png"))
        return

    ctx = build(args.pack)
    out = args.out or os.path.join(
        here, "schedule_algo.gif" if args.pack == "row"
        else "schedule_algo_none.gif")

    committed = []
    counters = {"committed": 0, "died": 0, "deferred": 0}
    frames = []

    for pair_idx in range(1, DETAIL_PAIRS + 1):
        evs = ctx["trace"][pair_idx - 1][2]
        frames.extend(frames_for(ctx, evs, committed, counters, pair_idx))

    frames.extend(montage_frames(ctx, committed, counters, DETAIL_PAIRS))
    frames.extend(outro_frames(ctx, committed, counters))

    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=256)
              for f in frames]
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=1000 // args.fps, loop=0, optimize=True,
                   disposal=2)
    s = ctx["stats"]
    print(f"wrote {out}: {len(frames)} frames, "
          f"{len(frames) / args.fps:.1f}s @ {args.fps}fps, "
          f"{os.path.getsize(out) / 1e6:.1f} MB")
    print(f"pack {ctx['pack']}: {counters['committed']} committed at clock 0, "
          f"{counters['deferred']} deferred, {counters['died']} died; "
          f"stats {s['passes']} passes, rows {s['rows']}, frame {s['frame']}")


if __name__ == "__main__":
    main()
