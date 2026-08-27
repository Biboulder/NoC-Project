"""SVG visualization of a schedule: a self-contained, browser-interactive
dark-themed SVG with embedded JavaScript.

Each (node, clock) row carries one or more alternative routes (mutually
exclusive — rule 6: one packet per node per clock). The initial per-row
choice is seeded (``--seed``, matching ``Grid.run``/``choose_alternatives``
so the first frame equals what the sim executes); the embedded JavaScript
re-rolls every row's choice randomly at each period boundary and via a
``re-roll`` button — packed rows show a random alternative that refreshes
every period.

Packets are animated live by JS: injected (at the source, k = 0 — pulsing
white ring, has not left), in flight (gliding wire to wire on a lit wire),
delivered (flash at the destination, k = hops). A HUD counts the three
disjoint states each cycle, plus play/pause, speed (0.5x/1x/2x), and a
cycle scrubber. ``seed`` fixes only the initial frame; later re-rolls use
Math.random (deliberately non-reproducible).
"""

import json

from .grid import choose_alternatives, neighbor_of, node_position

__all__ = ["render_svg"]

_DARK_PALETTE = [
    "#ff6b6b", "#4dabf7", "#51cf66", "#b197fc", "#ffa94d", "#22b8cf",
    "#f783ac", "#ced4da", "#ffe066", "#ff922b", "#748ffc", "#63e6be",
]

_TITLE_H = 24
_MARGIN = 26
_TOP = 46     # title bar height
_HUD = 64     # HUD bar height
_LEGEND = 34  # legend strip height


def _center(n, cell, title_h, margin, x, y):
    return (margin + x * cell, title_h + margin + y * cell)


def _packet_pts(n, cell, margin, title_h, e):
    """Pixel centers of every router along an entry's route (source first)."""
    x, y = node_position(n, e.node)
    ppts = [_center(n, cell, title_h, margin, x, y)]
    for d in e.route:
        x, y = neighbor_of(n, x, y, d)
        ppts.append(_center(n, cell, title_h, margin, x, y))
    return ppts


def _baseline_wires(n, cell, margin, title_h):
    """Faint lines for every mesh link (static chrome; JS never rebuilds)."""
    parts = []
    for y in range(n):
        for x in range(n):
            cx, cy = _center(n, cell, title_h, margin, x, y)
            if x + 1 < n:
                nx, ny = _center(n, cell, title_h, margin, x + 1, y)
                parts.append(
                    f'<line class="wire-baseline" x1="{cx:.1f}" y1="{cy:.1f}" '
                    f'x2="{nx:.1f}" y2="{ny:.1f}"/>'
                )
            if y + 1 < n:
                nx, ny = _center(n, cell, title_h, margin, x, y + 1)
                parts.append(
                    f'<line class="wire-baseline" x1="{cx:.1f}" y1="{cy:.1f}" '
                    f'x2="{nx:.1f}" y2="{ny:.1f}"/>'
                )
    return "".join(parts)


def _routers(n, cell, margin, radius, title_h):
    """Router circles + labels (static chrome)."""
    parts = []
    for y in range(n):
        for x in range(n):
            cx, cy = _center(n, cell, title_h, margin, x, y)
            label = y * n + x + 1
            parts.append(
                f'<circle class="router" cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}"/>'
            )
            parts.append(
                f'<text class="router-label" x="{cx:.1f}" y="{cy:.1f}" '
                f'font-size="{radius}" text-anchor="middle" '
                f'dominant-baseline="central">{label}</text>'
            )
    return "".join(parts)


def _flipbook(n, cell, radius, fw, fh, cols, gap, frames):
    """Per-cycle frame chrome (static); JS fills each `.flip-traffic` group.

    Frame coordinates are frame-local (same `_center` math as the viewport),
    so `_baseline_wires`/`_routers` emit directly inside each frame. The
    `.flip-traffic` groups appear in document order == cycle order.
    """
    parts = []
    for c in range(frames):
        fx = (c % cols) * (fw + gap)
        fy = (c // cols) * (fh + gap)
        parts.append(
            f'<g data-frame="{c}" transform="translate({fx},{fy})">'
            f'<rect class="frame" x="0" y="0" width="{fw}" height="{fh}" rx="8"/>'
            f'<g class="frame-wires">{_baseline_wires(n, cell, _MARGIN, _TITLE_H)}</g>'
            f'<g class="frame-routers">{_routers(n, cell, _MARGIN, radius, _TITLE_H)}</g>'
            f'<text class="frame-label" x="26" y="16">cycle {c}</text>'
            f'<text class="frame-caption" x="26" y="{fh - 8}">c{c}</text>'
            '<g class="flip-traffic"/>'
            "</g>"
        )
    return "".join(parts)


def _legend(n, parts):
    """Destination-hue swatches + note (static chrome)."""
    for d in range(1, min(12, n * n) + 1):
        x = 16 + (d - 1) * 34
        color = _DARK_PALETTE[(d - 1) % len(_DARK_PALETTE)]
        parts.append(f'<circle cx="{x}" cy="12" r="5" fill="{color}"/>')
        parts.append(
            f'<text x="{x}" y="27" font-size="10" fill="#8b949e" '
            f'text-anchor="middle">{d}</text>'
        )
    note_x = 16 + min(12, n * n) * 34 + 8
    parts.append(
        f'<text x="{note_x}" y="18" font-size="11" fill="#8b949e">'
        f'destination hue (repeats mod {len(_DARK_PALETTE)})</text>'
    )


_CSS = """
svg { background: #0d1117; }
.viewport { fill: #161b22; stroke: #30363d; }
.wire-baseline { stroke: #21262d; stroke-width: 1; }
.router { fill: #21262d; stroke: #30363d; }
.router-label { fill: #c9d1d9; pointer-events: none; }
.wire-active { opacity: 0.85; stroke-width: 3; filter: url(#glow); }
.packet { transition: transform var(--dur) linear; }
.pkt { fill: #4dabf7; }
.pkt.injected {
  stroke: #ffffff; stroke-width: 1.5;
  animation: pulse var(--dur) ease-out infinite;
  transform-box: fill-box; transform-origin: center;
}
.pkt.inflight { filter: url(#glow); }
.pkt.delivered { animation: flash var(--dur) ease-in-out infinite; }
@keyframes pulse { from { transform: scale(1); opacity: 0.9; } to { transform: scale(1.6); opacity: 0; } }
@keyframes flash { 0% { opacity: 0; } 50% { opacity: 1; } 100% { opacity: 0; } }
.frame { fill: #161b22; stroke: #30363d; }
.frame-label { fill: #e6edf3; font-size: 12px; font-weight: bold; }
.frame-caption { fill: #8b949e; font-size: 10px; }
.flip-wire { opacity: 0.85; stroke-width: 3; }
.fpkt { animation: flipglide var(--dur) linear infinite, flipfade var(--dur) linear infinite; }
.fpkt.static { animation: none; }
@keyframes flipglide { from { transform: translate(var(--fx), var(--fy)); } to { transform: translate(var(--tx), var(--ty)); } }
@keyframes flipfade { 0% { opacity: 0; } 2% { opacity: 1; } 98% { opacity: 1; } 100% { opacity: 0; } }
svg.paused .pkt, svg.paused .fpkt { animation-play-state: paused !important; }
.fwindow { fill: #161b22; stroke: #30363d; }
.fwindow-header { fill: #21262d; stroke: #30363d; cursor: move; }
.fwindow-title { fill: #c9d1d9; font-size: 11px; pointer-events: none; user-select: none; }
.fwindow-resize { cursor: nwse-resize; }
.fwindow-resize rect { fill: #21262d; stroke: #30363d; }
.fwindow-resize:hover rect { fill: #30363d; }
.hud-status { fill: #c9d1d9; font-size: 13px; }
.chip { fill: #21262d; }
.chip-text { fill: #c9d1d9; font-size: 12px; pointer-events: none; }
.btn { fill: #21262d; cursor: pointer; }
.btn:hover { fill: #30363d; }
.btn-text { fill: #e6edf3; font-size: 12px; pointer-events: none; }
input[type='range'].slider { accent-color: #4dabf7; margin: 0; padding: 0; background: transparent; }
"""

_JS = r"""
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var data = JSON.parse(document.getElementById('sched-data').textContent);
  var root = document.querySelector('svg');
  var rows = data.rows;
  var frames = data.frames;
  var flipMs = data.flip_ms;

  var cycle = 0;
  var speed = 1;
  var playing = true;
  var timer = null;
  var choice = rows.map(function (r) {
    return Math.min(r.choice0, r.alts.length - 1);
  });
  /* Per-row previous state: a position change is a one-hop glide only when
     the route is unchanged and the cycle advanced exactly one step. */
  var prevChoice = choice.slice();
  var prevK = new Array(rows.length);
  var prevVisible = new Array(rows.length);
  for (var vi = 0; vi < rows.length; vi++) { prevVisible[vi] = false; }

  function el(name, attrs, text) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) {
        e.setAttribute(k, attrs[k]);
      }
    }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }

  /* One group per row: position + glide transition; the pkt circle inside
     carries the injected/inflight/delivered state styling. */
  var packets = [];
  var wires = [];
  var wiresG = document.getElementById('wires-live');
  var packetsG = document.getElementById('packets');
  rows.forEach(function (row, i) {
    var g = el('g', {'class': 'packet'});
    g.appendChild(el('circle', {r: 5, 'class': 'pkt'}));
    packets.push(g);
    wires.push(el('line', {'class': 'wire'}));
    wiresG.appendChild(wires[i]);
    packetsG.appendChild(g);
  });

  /* Flipbook: one .flip-traffic group per cycle, document order == c order. */
  var flipGroups = Array.prototype.slice.call(document.querySelectorAll('.flip-traffic'));

  /* HUD chrome. */
  var hud = document.getElementById('hud');
  var status = el('text', {x: 16, y: 22, 'class': 'hud-status'});
  hud.appendChild(status);

  var chipDefs = [
    ['#ffe066', 'injected'],
    ['#4dabf7', 'in flight'],
    ['#51cf66', 'delivered'],
  ];
  var chips = [];
  chipDefs.forEach(function (c, i) {
    var g = el('g', {transform: 'translate(' + (16 + i * 96) + ',42)'});
    g.appendChild(el('rect', {width: 90, height: 20, rx: 8, 'class': 'chip'}));
    g.appendChild(el('circle', {cx: 12, cy: 10, r: 4, fill: c[0]}));
    chips.push(el('text', {x: 22, y: 15, 'class': 'chip-text'}));
    g.appendChild(chips[i]);
    hud.appendChild(g);
  });

  function button(x, w, label, role, onClick) {
    var g = el('g', {transform: 'translate(' + x + ',38)'});
    var r = el('rect', {
      width: w, height: 26, rx: 8, 'class': 'btn', 'data-role': role,
    });
    var t = el('text', {
      x: w / 2, y: 17, 'class': 'btn-text', 'text-anchor': 'middle',
    }, label);
    g.appendChild(r);
    g.appendChild(t);
    hud.appendChild(g);
    r.addEventListener('click', onClick);
    return {g: g, rect: r, text: t};
  }

  var slider = document.createElementNS('http://www.w3.org/1999/xhtml', 'input');
  slider.type = 'range';
  slider.min = 0;
  slider.max = frames - 1;
  slider.value = 0;
  slider.className = 'slider';
  slider.style.width = '80px';
  slider.style.margin = '0';
  slider.style.padding = '0';
  var fo = el('foreignObject', {x: 455, y: 40, width: 80, height: 22});
  fo.appendChild(slider);
  hud.appendChild(fo);

  function setDur() {
    root.style.setProperty('--dur', (flipMs / speed) + 'ms');
  }

  function kFor(row) {
    return ((cycle - row.clock) % frames + frames) % frames;
  }

  /* Per-row alternative for the current flipbook period: one random path
     per row, consistent across the period's frames; re-rolled on every
     rebuild (init, manual re-roll, and each period rollover). */
  var flipChoice = rows.map(function () { return 0; });

  /* Rebuild every frame's snapshot from the current period's flipChoice.
     Row-packed schedules show a random path per period, re-rolled every
     period; single-alternative rows (--pack none) keep their fixed path.
     k = c - clock (one period, no modulo — the original _frame rule). */
  function buildFlipbook() {
    for (var i = 0; i < rows.length; i++) {
      flipChoice[i] = Math.floor(Math.random() * rows[i].alts.length);
    }
    for (var c = 0; c < frames; c++) {
      var g = flipGroups[c];
      while (g.firstChild) { g.removeChild(g.firstChild); }
      var inflight = 0, injected = 0;
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var alt = row.alts[flipChoice[i]];
        var k = c - row.clock;
        var h = alt.hops;
        if (k < 0 || k > h) { continue; }
        var pts = alt.pts;
        var color = alt.color;
        if (k === 0) {
          injected++;
          g.appendChild(el('circle', {
            'class': 'fpkt static', cx: pts[0][0], cy: pts[0][1],
            r: 5, fill: color,
          }));
        } else {
          inflight++;
          g.appendChild(el('line', {
            'class': 'flip-wire',
            x1: pts[k - 1][0], y1: pts[k - 1][1],
            x2: pts[k][0], y2: pts[k][1],
            stroke: color,
          }));
          var pkt = el('circle', {'class': 'fpkt', cx: 0, cy: 0, r: 5, fill: color});
          pkt.style.setProperty('--fx', pts[k - 1][0] + 'px');
          pkt.style.setProperty('--fy', pts[k - 1][1] + 'px');
          pkt.style.setProperty('--tx', pts[k][0] + 'px');
          pkt.style.setProperty('--ty', pts[k][1] + 'px');
          g.appendChild(pkt);
        }
      }
      g.parentNode.querySelector('.frame-caption').textContent =
        'c' + c + ': ' + inflight + ' in flight' +
        (injected ? ', ' + injected + ' injected' : '');
    }
  }

  function syncPaused() {
    root.classList.toggle('paused', !playing);
  }

  /* Flipbook window: drag the title bar to move, drag the bottom-right
     corner to resize. Frames re-stack to the window width (more columns
     when wider); content scales to fit; the canvas grows/shrinks so the
     window is never cut off. */
  var svgRoot = document.querySelector('svg');
  var canvasW0 = parseFloat(svgRoot.getAttribute('width'));
  var canvasH0 = parseFloat(svgRoot.getAttribute('height'));
  var win = document.getElementById('flipbook-window');
  var winFrame = document.getElementById('fwindow-frame');
  var winHeader = document.getElementById('fwindow-header');
  var winContent = document.getElementById('flipbook-content');
  var winResize = document.getElementById('fwindow-resize');
  var flipbook = document.getElementById('flipbook');
  var fwPx = parseFloat(flipbook.getAttribute('data-fw'));
  var fhPx = parseFloat(flipbook.getAttribute('data-fh'));
  var gapPx = parseFloat(flipbook.getAttribute('data-gap'));
  var frameGroups = Array.prototype.slice.call(
    document.querySelectorAll('#flipbook > [data-frame]'));
  var winT = (win.getAttribute('transform') || '').match(/translate\(([-\d.]+),([-\d.]+)\)/);
  var winX = winT ? parseFloat(winT[1]) : 0;
  var winY = winT ? parseFloat(winT[2]) : 0;
  var winW = parseFloat(winFrame.getAttribute('width'));
  var winH = parseFloat(winFrame.getAttribute('height'));

  function layoutWindow() {
    /* Re-stack frames to the window width. */
    var cols = Math.max(1, Math.min(frames,
      Math.floor((winW + gapPx) / (fwPx + gapPx))));
    var gridW = cols * fwPx + (cols - 1) * gapPx;
    var rows = Math.ceil(frames / cols);
    var gridH = rows * fhPx + (rows - 1) * gapPx;
    frameGroups.forEach(function (g, c) {
      g.setAttribute('transform',
        'translate(' + (c % cols) * (fwPx + gapPx) + ',' +
        Math.floor(c / cols) * (fhPx + gapPx) + ')');
    });
    /* Scale to fit (contain), centered. */
    var s = Math.min(winW / gridW, (winH - 24) / gridH);
    if (s < 0.02) { s = 0.02; }
    var cx = (winW - gridW * s) / 2;
    var cy = 24 + (winH - 24 - gridH * s) / 2;
    winContent.setAttribute('transform',
      'translate(' + cx + ',' + cy + ') scale(' + s + ')');
    winFrame.setAttribute('width', winW);
    winFrame.setAttribute('height', winH);
    winHeader.setAttribute('width', winW);
    winResize.setAttribute('transform',
      'translate(' + (winW - 18) + ',' + (winH - 18) + ')');
    updateCanvas();
  }

  function updateCanvas() {
    var w = Math.max(canvasW0, winX + winW + 16);
    var h = Math.max(canvasH0, winY + winH + 16);
    svgRoot.setAttribute('width', w);
    svgRoot.setAttribute('height', h);
  }

  function windowDrag(el, onMove) {
    el.addEventListener('pointerdown', function (ev) {
      ev.preventDefault();
      var sx = ev.clientX, sy = ev.clientY;
      function move(e) {
        onMove(e.clientX - sx, e.clientY - sy);
        sx = e.clientX; sy = e.clientY;
      }
      function up() {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
      }
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
    });
  }

  windowDrag(winHeader, function (dx, dy) {
    winX += dx; winY += dy;
    win.setAttribute('transform', 'translate(' + winX + ',' + winY + ')');
    updateCanvas();
  });

  windowDrag(winResize, function (dx, dy) {
    winW = Math.max(160, winW + dx);
    winH = Math.max(64, winH + dy);
    layoutWindow();
  });

  function stopTimer() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  function startTimer() {
    stopTimer();
    setDur();
    if (playing) { timer = setInterval(step, flipMs / speed); }
  }

  function pause() {
    if (playing) {
      playing = false;
      playBtn.text.textContent = '\u25B6';
      stopTimer();
      syncPaused();
    }
  }

  function togglePlay() {
    playing = !playing;
    playBtn.text.textContent = playing ? '\u23F8' : '\u25B6';
    startTimer();
    syncPaused();
  }

  function reroll() {
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].alts.length > 1) {
        choice[i] = Math.floor(Math.random() * rows[i].alts.length);
      }
    }
    render();
    buildFlipbook();
  }

  function step() {
    cycle = (cycle + 1) % frames;
    if (cycle === 0) { reroll(); } else { render(); }
  }

  var SPEEDS = [0.5, 1, 2];
  var speedIdx = 1;
  var playBtn = button(341, 30, '\u23F8', 'play', togglePlay);
  var speedBtn = button(377, 40, '1\u00D7', 'speed', function () {
    speedIdx = (speedIdx + 1) % SPEEDS.length;
    speed = SPEEDS[speedIdx];
    speedBtn.text.textContent = (speed < 1 ? speed.toFixed(1) : String(speed)) + '\u00D7';
    startTimer();
  });
  button(423, 26, '\u2039', 'prev', function () {
    pause(); cycle = (cycle - 1 + frames) % frames; render();
  });
  button(541, 26, '\u203A', 'next', function () {
    pause(); cycle = (cycle + 1) % frames; render();
  });
  button(573, 56, 're-roll', 'reroll', reroll);

  slider.addEventListener('input', function () {
    pause();
    cycle = parseInt(slider.value, 10);
    render();
  });

  function render() {
    var injected = 0, inflight = 0, delivered = 0;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var alt = row.alts[choice[i]];
      var k = kFor(row);
      var h = alt.hops;
      var p = packets[i];
      var w = wires[i];
      if (k < 0 || k > h) {
        p.style.display = 'none';
        w.style.display = 'none';
        prevChoice[i] = choice[i];
        prevK[i] = k;
        prevVisible[i] = false;
        continue;
      }
      var pt = alt.pts[k];
      p.style.display = '';
      var glide = prevVisible[i] && choice[i] === prevChoice[i] &&
        k === prevK[i] + 1;
      if (glide) {
        /* Restore the stylesheet transition, then move: one-hop glide
           along the same route's wire (axis-aligned on a mesh). */
        p.style.transition = '';
        p.style.transform = 'translate(' + pt[0] + 'px,' + pt[1] + 'px)';
      } else {
        /* Snap: re-roll, scrub, back-step, or reappear — apply the new
           position with transition disabled so no diagonal interpolation;
           keep it disabled until the next glide. */
        p.style.transition = 'none';
        p.style.transform = 'translate(' + pt[0] + 'px,' + pt[1] + 'px)';
        void p.getBoundingClientRect();
      }
      var core = p.firstChild;
      core.setAttribute('fill', alt.color);
      if (k === 0) {
        injected++;
        core.setAttribute('class', 'pkt injected');
        w.style.display = 'none';
      } else if (k === h) {
        delivered++;
        core.setAttribute('class', 'pkt delivered');
        w.style.display = 'none';
      } else {
        inflight++;
        core.setAttribute('class', 'pkt inflight');
        w.style.display = '';
        w.setAttribute('x1', alt.pts[k - 1][0]);
        w.setAttribute('y1', alt.pts[k - 1][1]);
        w.setAttribute('x2', pt[0]);
        w.setAttribute('y2', pt[1]);
        w.setAttribute('stroke', alt.color);
        w.setAttribute('class', 'wire wire-active');
      }
      prevChoice[i] = choice[i];
      prevK[i] = k;
      prevVisible[i] = true;
    }
    status.textContent = 'cycle ' + cycle + ' \u2014 ' + injected + ' injected \u00B7 ' +
      inflight + ' in flight \u00B7 ' + delivered + ' delivered';
    chips[0].textContent = injected + ' injected';
    chips[1].textContent = inflight + ' in flight';
    chips[2].textContent = delivered + ' delivered';
    slider.value = cycle;
  }

  function init() {
    setDur();
    render();
    buildFlipbook();
    startTimer();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.__viz = {
    state: function () {
      return {
        cycle: cycle, playing: playing, speed: speed,
        frames: frames, choice: choice.slice(),
        flipChoice: flipChoice.slice(),
      };
    }
  };
})();
"""


def render_svg(schedule, flip_ms=1200, seed=0):
    if flip_ms <= 0:
        raise ValueError(f"flip_ms must be > 0, got {flip_ms}")
    n = schedule.grid
    frames = schedule.period
    choice = choose_alternatives(schedule, seed)  # initial per-row choice, same as Grid.run

    cell = min(90, max(40, 240 // n))
    radius = max(9, cell // 5)
    fw = n * cell + 2 * _MARGIN
    fh = n * cell + 2 * _MARGIN + _TITLE_H
    cols = min(4, frames)
    gap = 30
    grid_rows = (frames + cols - 1) // cols
    flip_width = cols * fw + (cols - 1) * gap
    flip_height = grid_rows * fh + (grid_rows - 1) * gap
    width = max(flip_width, 640)
    x_offset = (width - fw) // 2
    height = _TOP + fh + _HUD + _LEGEND + 24 + flip_height

    rows_data = []
    for (node, clock), alts in schedule.rows().items():
        try:
            choice0 = alts.index(choice[(node, clock)])
        except (KeyError, ValueError):
            choice0 = 0  # helper changed shape; fall back to first alternative
        alt_data = []
        for e in alts:
            ppts = _packet_pts(n, cell, _MARGIN, _TITLE_H, e)
            alt_data.append({
                "dest": e.dest,
                "hops": len(e.route),
                "color": _DARK_PALETTE[(e.dest - 1) % len(_DARK_PALETTE)],
                "pts": [[round(px, 1), round(py, 1)] for px, py in ppts],
            })
        rows_data.append({
            "node": node,
            "clock": clock,
            "choice0": choice0,
            "alts": alt_data,
        })

    data = {
        "grid": n,
        "frames": frames,
        "seed": seed,
        "flip_ms": flip_ms,
        "rows": rows_data,
    }

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="'
        f'{width}" height="{height}" '
        'font-family="system-ui, -apple-system, \'Segoe UI\', Roboto, sans-serif" '
        'style="background:#0d1117">',
        "<defs>",
        '  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">',
        '    <feGaussianBlur stdDeviation="3" result="blur"/>',
        '    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>',
        "  </filter>",
        "</defs>",
        "<style>",
        _CSS,
        "</style>",
        # Title bar.
        '<text x="12" y="18" font-size="14" font-weight="bold" fill="#e6edf3">'
        f"grid {n}x{n}, {frames} cycles per period, {len(schedule.entries)} alternatives, "
        f"{len(schedule.rows())} rows per period (choice seed {seed})</text>",
        '<text x="12" y="38" font-size="11" fill="#8b949e">'
        f"JS-driven \u00B7 {flip_ms} ms per cycle \u00B7 per-row choices re-roll each period "
        "\u00B7 open in a browser</text>",
        # Viewport (static chrome; JS animates inside wires-live / packets).
        f'<g transform="translate({x_offset},{_TOP})">',
        f'<rect class="viewport" x="0" y="0" width="{fw}" height="{fh}" rx="12"/>',
        f'<g id="wires-baseline">{_baseline_wires(n, cell, _MARGIN, _TITLE_H)}</g>',
        f'<g id="routers">{_routers(n, cell, _MARGIN, radius, _TITLE_H)}</g>',
        '<g id="wires-live"/>',
        '<g id="packets"/>',
        "</g>",
        # HUD bar: JS builds chips + controls.
        f'<g id="hud" transform="translate({x_offset},{_TOP + fh})"/>',
        # Legend strip.
        f'<g id="legend" transform="translate({x_offset},{_TOP + fh + _HUD})">',
    ]
    _legend(n, parts)
    parts.extend(
        [
            "</g>",
            # Static flipbook: one dark grid per cycle, animated by JS, inside
            # a draggable/resizable window (drag title bar to move, drag the
            # bottom-right corner to resize; content scales to fit — for
            # composing screenshot layouts).
            f'<g id="flipbook-window" transform="translate(0,{_TOP + fh + _HUD + _LEGEND})">',
            f'<rect id="fwindow-frame" class="fwindow" x="0" y="0" '
            f'width="{flip_width}" height="{24 + flip_height}" rx="8"/>',
            f'<rect id="fwindow-header" class="fwindow-header" x="0" y="0" '
            f'width="{flip_width}" height="24" rx="8"/>',
            f'<text id="fwindow-title" class="fwindow-title" x="12" y="16">'
            "static flipbook (every cycle snapshot, animated) \u00B7 drag title "
            "bar to move, drag corner to resize</text>",
            f'<g id="flipbook-content" transform="translate(0,24)">',
            f'<g id="flipbook" data-fw="{fw}" data-fh="{fh}" data-gap="{gap}">'
            f'{_flipbook(n, cell, radius, fw, fh, cols, gap, frames)}</g>',
            "</g>",
            f'<g id="fwindow-resize" class="fwindow-resize" '
            f'transform="translate({flip_width - 18},{24 + flip_height - 18})">',
            '<rect x="0" y="0" width="18" height="18" rx="3"/>',
            '<path d="M15 12 L12 15 M15 8 L8 15 M15 4 L4 15" '
            'stroke="#8b949e" stroke-width="1.5" fill="none"/>',
            "</g>",
            "</g>",
            '<script id="sched-data" type="application/json">',
            json.dumps(data, separators=(",", ":")),
            "</script>",
            "<script>",
            "<![CDATA[",
            _JS,
            "]]>",
            "</script>",
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"
