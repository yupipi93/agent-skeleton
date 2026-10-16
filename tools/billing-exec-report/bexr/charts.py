"""Inline SVG chart builders.

SVG rather than raster images for two reasons: it stays sharp when the HTML is
printed to PDF at any scale, and it keeps the document self-contained without
embedding megabytes of base64. Every builder returns a complete <svg> element
with a viewBox, so CSS controls the size.
"""
from __future__ import annotations

import datetime as dt
import math

INK = "#202124"
DIM = "#5f6368"
FAINT = "#5f6368"
GRID = "#e3e6ea"
TRACK = "#eef1f4"
PROJ = "#c8ccd1"


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _fmt(v: float, symbol: str, dp: int = 2) -> str:
    return f"{symbol}{v:,.{dp}f}"


def _open(w: float, h: float, cls: str = "") -> str:
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" '
            f'height="{h:.0f}" class="chart {cls}" role="img" '
            f'xmlns="http://www.w3.org/2000/svg">')


def _text(x, y, s, size=11, fill=INK, anchor="start", weight="400"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{_esc(s)}</text>')


# ------------------------------------------------------------------ markers

def marker(cx: float, cy: float, kind: str, color: str, r: float = 5.0) -> str:
    """The shape vocabulary the billing console uses in its legends."""
    if kind == "circle":
        return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'
    if kind == "square":
        return (f'<rect x="{cx - r}" y="{cy - r}" width="{2 * r}" '
                f'height="{2 * r}" fill="{color}"/>')
    if kind == "diamond":
        p = f"{cx},{cy - r * 1.25} {cx + r * 1.15},{cy} {cx},{cy + r * 1.25} {cx - r * 1.15},{cy}"
        return f'<polygon points="{p}" fill="{color}"/>'
    if kind == "tri-down":
        p = f"{cx - r * 1.15},{cy - r * .85} {cx + r * 1.15},{cy - r * .85} {cx},{cy + r * 1.05}"
        return f'<polygon points="{p}" fill="{color}"/>'
    if kind == "tri-up":
        p = f"{cx},{cy - r * 1.05} {cx + r * 1.15},{cy + r * .85} {cx - r * 1.15},{cy + r * .85}"
        return f'<polygon points="{p}" fill="{color}"/>'
    if kind == "pentagon":
        pts = [(cx + r * 1.15 * math.sin(math.radians(a)),
                cy - r * 1.15 * math.cos(math.radians(a)))
               for a in range(0, 360, 72)]
        return ('<polygon points="'
                + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                + f'" fill="{color}"/>')
    if kind == "cross":
        t = r * 0.42
        pts = [(cx - t, cy - r), (cx + t, cy - r), (cx + t, cy - t), (cx + r, cy - t),
               (cx + r, cy + t), (cx + t, cy + t), (cx + t, cy + r), (cx - t, cy + r),
               (cx - t, cy + t), (cx - r, cy + t), (cx - r, cy - t), (cx - t, cy - t)]
        return ('<polygon points="'
                + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                + f'" fill="{color}"/>')
    if kind == "asterisk":
        out = []
        for a in (0, 60, 120):
            dx, dy = r * math.cos(math.radians(a)), r * math.sin(math.radians(a))
            out.append(f'<line x1="{cx - dx:.1f}" y1="{cy - dy:.1f}" '
                       f'x2="{cx + dx:.1f}" y2="{cy + dy:.1f}" '
                       f'stroke="{color}" stroke-width="{r * 0.55:.1f}"/>')
        return "".join(out)
    if kind == "shield":
        p = (f"{cx - r * .9},{cy - r} {cx + r * .9},{cy - r} {cx + r * .9},{cy + r * .1} "
             f"{cx},{cy + r * 1.15} {cx - r * .9},{cy + r * .1}")
        return f'<polygon points="{p}" fill="{color}"/>'
    if kind == "star":
        pts = []
        for i in range(10):
            a = math.radians(-90 + i * 36)
            rr = r * 1.3 if i % 2 == 0 else r * 0.55
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        return ('<polygon points="'
                + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                + f'" fill="{color}"/>')
    return f'<circle cx="{cx}" cy="{cy}" r="{r * .62}" fill="{color}"/>'


# -------------------------------------------------------------------- donut

def _ring(cx, cy, ro, ri, a0, a1) -> str:
    """Annular sector path between two angles, degrees, 0 = 12 o'clock."""
    if a1 - a0 >= 359.999:
        return (f'M {cx - ro} {cy} A {ro} {ro} 0 1 1 {cx + ro} {cy} '
                f'A {ro} {ro} 0 1 1 {cx - ro} {cy} Z '
                f'M {cx - ri} {cy} A {ri} {ri} 0 1 0 {cx + ri} {cy} '
                f'A {ri} {ri} 0 1 0 {cx - ri} {cy} Z')
    r0, r1 = math.radians(a0 - 90), math.radians(a1 - 90)
    large = 1 if (a1 - a0) > 180 else 0
    x0o, y0o = cx + ro * math.cos(r0), cy + ro * math.sin(r0)
    x1o, y1o = cx + ro * math.cos(r1), cy + ro * math.sin(r1)
    x1i, y1i = cx + ri * math.cos(r1), cy + ri * math.sin(r1)
    x0i, y0i = cx + ri * math.cos(r0), cy + ri * math.sin(r0)
    return (f'M {x0o:.2f} {y0o:.2f} A {ro} {ro} 0 {large} 1 {x1o:.2f} {y1o:.2f} '
            f'L {x1i:.2f} {y1i:.2f} A {ri} {ri} 0 {large} 0 {x0i:.2f} {y0i:.2f} Z')


def donut(segments, total: float, symbol: str, center_label: str,
          w: float = 300, h: float = 300) -> str:
    """segments: [(name, value, color)] drawn clockwise from 12 o'clock."""
    cx, cy = w / 2, h / 2
    ro, ri = min(w, h) / 2 - 8, min(w, h) / 2 - 46
    out = [_open(w, h, "donut")]
    a = 0.0
    for name, value, color in segments:
        if value <= 0 or total <= 0:
            continue
        span = value / total * 360.0
        out.append(f'<path d="{_ring(cx, cy, ro, ri, a, a + span)}" '
                   f'fill="{color}"><title>{_esc(name)}: '
                   f'{_fmt(value, symbol)}</title></path>')
        a += span
    out.append(_text(cx, cy + 2, _fmt(total, symbol), 20, INK, "middle", "700"))
    out.append(_text(cx, cy + 20, center_label, 10, DIM, "middle"))
    out.append("</svg>")
    return "".join(out)


def legend(segments, total: float, symbol: str, w: float = 300) -> str:
    """Vertical legend with value and share, one row per segment."""
    row = 22.0
    h = row * len(segments) + 6
    out = [_open(w, h, "legend")]
    y = 12.0
    for name, value, color in segments:
        out.append(marker(7, y, "square", color, 5))
        out.append(_text(20, y + 4, name, 10.5, INK))
        out.append(_text(w - 54, y + 4, _fmt(value, symbol), 10.5, INK, "end"))
        share = (value / total * 100.0) if total else 0.0
        out.append(_text(w, y + 4, f"{share:.1f}%", 10.5, DIM, "end"))
        y += row
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------- split bar

def split_bar(segments, total: float, symbol: str, w: float = 620,
              h: float = 62) -> str:
    """One 100% stacked bar with in-bar labels where they fit."""
    out = [_open(w, h, "split")]
    bh = 30.0
    x = 0.0
    for name, value, color in segments:
        if value <= 0 or total <= 0:
            continue
        seg = value / total * w
        out.append(f'<rect x="{x:.2f}" y="0" width="{seg:.2f}" height="{bh}" '
                   f'fill="{color}"/>')
        pct = value / total * 100.0
        if seg > 58:
            label = f"{pct:.1f}%"
            pw = len(label) * 6.4 + 12
            out.append(f'<rect x="{x + seg / 2 - pw / 2:.1f}" y="{bh / 2 - 9:.1f}" '
                       f'width="{pw:.1f}" height="18" rx="2" fill="#ffffff"/>')
            out.append(_text(x + seg / 2, bh / 2 + 4, label, 11,
                             color, "middle", "700"))
        if seg > 92:
            out.append(_text(x + seg / 2, bh + 16, name, 9.5, DIM, "middle"))
            out.append(_text(x + seg / 2, bh + 28, _fmt(value, symbol), 9.5,
                             INK, "middle", "600"))
        x += seg
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------ horizontal bars

def hbars(items, symbol: str, w: float = 640, row: float = 26.0,
          label_w: float = 210, value_w: float = 128, dp: int = 2) -> str:
    """items: [(label, value, color, right_note)] sorted by the caller."""
    h = row * len(items) + 8
    bar_w = w - label_w - value_w
    mx = max((v for _, v, _, _ in items), default=0.0) or 1.0
    out = [_open(w, h, "hbars")]
    y = 6.0
    for label, value, color, note in items:
        cy = y + row / 2 - 3
        out.append(_text(0, cy + 4, label, 10.5, INK))
        bw = max(1.0, value / mx * bar_w)
        out.append(f'<rect x="{label_w}" y="{cy - 6}" width="{bar_w:.1f}" '
                   f'height="12" rx="2" fill="{TRACK}"/>')
        out.append(f'<rect x="{label_w}" y="{cy - 6}" width="{bw:.1f}" '
                   f'height="12" rx="2" fill="{color}"/>')
        out.append(_text(w - value_w + 74, cy + 4, _fmt(value, symbol, dp), 10.5,
                         INK, "end", "600"))
        if note:
            out.append(_text(w, cy + 4, note, 10, DIM, "end"))
        y += row
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------- daily trend

def daily_columns(days, values, symbol: str, baseline: float | None = None,
                  projected=None, w: float = 660, h: float = 220) -> str:
    """Column chart of daily cost.

    projected: optional [(date, value)] drawn in grey after the actual days, the
    way the console shades the remainder of the month.
    """
    projected = projected or []
    all_days = list(days) + [d for d, _ in projected]
    all_vals = list(values) + [v for _, v in projected]
    if not all_days:
        return ""
    pad_l, pad_r, pad_t, pad_b = 42.0, 6.0, 12.0, 30.0
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    vmax = max(all_vals) * 1.12 or 1.0
    step = plot_w / len(all_days)
    bw = min(step * 0.68, 26.0)

    def ty(v: float) -> float:
        return pad_t + plot_h - (v / vmax) * plot_h

    out = [_open(w, h, "daily")]
    ticks = _nice_ticks(vmax, 5)
    for t in ticks:
        y = ty(t)
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" '
                   f'y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(_text(pad_l - 6, y + 3.5, _fmt(t, symbol, 0), 9, FAINT, "end"))
    if baseline:
        y = ty(baseline)
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" '
                   f'y2="{y:.1f}" stroke="{INK}" stroke-width="1" '
                   f'stroke-dasharray="4 3" opacity="0.55"/>')
        out.append(_text(pad_l + 3, y - 4, f"baseline {_fmt(baseline, symbol)}",
                         8.5, DIM, "start"))

    n_actual = len(days)
    for i, (d, v) in enumerate(zip(all_days, all_vals)):
        x = pad_l + i * step + (step - bw) / 2
        y = ty(v)
        is_proj = i >= n_actual
        fill = PROJ if is_proj else ("#4285f4" if v <= (baseline or 0) * 1.35
                                     else "#f4511e")
        out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" '
                   f'height="{pad_t + plot_h - y:.2f}" fill="{fill}" rx="1.5">'
                   f'<title>{d:%d %b}: {_fmt(v, symbol)}'
                   f'{" (projected)" if is_proj else ""}</title></rect>')
        show = (len(all_days) <= 16 or i % 2 == 0 or i == len(all_days) - 1)
        if show:
            out.append(_text(x + bw / 2, h - 16, f"{d.day}", 8.5, FAINT, "middle"))
    out.append(_text(pad_l, h - 4, f"{all_days[0]:%b %Y}", 8.5, FAINT))
    if projected:
        out.append(_text(w - pad_r, h - 4, "grey: projected", 8.5, FAINT, "end"))
    out.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h:.1f}" '
               f'x2="{w - pad_r}" y2="{pad_t + plot_h:.1f}" '
               f'stroke="{FAINT}" stroke-width="1"/>')
    out.append("</svg>")
    return "".join(out)


def _nice_ticks(vmax: float, count: int) -> list[float]:
    raw = vmax / count
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        stepv = mag * mult
        if stepv >= raw:
            break
    out, v = [], stepv
    while v <= vmax:
        out.append(v)
        v += stepv
    return out


# ------------------------------------------------------------- budget chart

def budget_bars(rows, budget: float, thresholds, symbol: str,
                prev_budget: float | None = None, w: float = 660,
                h: float = 190) -> str:
    """rows: [(label, value, color, note)]. Budget drawn as a hard line."""
    pad_l, pad_r, pad_t = 176.0, 8.0, 52.0
    row_h, bar_h = 38.0, 22.0
    track_w = w - pad_l - pad_r
    vmax = max([v for _, v, _, _ in rows] + [budget]) * 1.16 or 1.0
    sx = lambda v: pad_l + (v / vmax) * track_w  # noqa: E731
    out = [_open(w, max(h, pad_t + row_h * len(rows) + 34), "budget")]

    reserved = [budget] + ([prev_budget] if prev_budget else [])
    for t in _nice_ticks(vmax, 6):
        x = sx(t)
        out.append(f'<line x1="{x:.1f}" y1="{pad_t - 6}" x2="{x:.1f}" '
                   f'y2="{pad_t + row_h * len(rows):.1f}" stroke="{GRID}"/>')
        # Skip a tick label that would sit on top of a budget marker label.
        if any(abs(sx(t) - sx(v)) < 34 for v in reserved):
            continue
        out.append(_text(x, pad_t - 11, _fmt(t, symbol, 0), 8.5, FAINT, "middle"))

    y = pad_t
    labels = []
    for label, value, color, note in rows:
        out.append(f'<rect x="{pad_l}" y="{y:.1f}" width="{track_w:.1f}" '
                   f'height="{bar_h}" fill="{TRACK}" rx="2"/>')
        out.append(f'<rect x="{pad_l}" y="{y:.1f}" width="{sx(value) - pad_l:.1f}" '
                   f'height="{bar_h}" fill="{color}" rx="2"/>')
        labels.append((label, value, y, note, color))
        y += row_h

    for t in thresholds:
        if t >= 1.0:
            continue
        x = sx(budget * t)
        if prev_budget and abs(x - sx(prev_budget)) < 4:
            continue
        out.append(f'<line x1="{x:.1f}" y1="{pad_t - 4}" x2="{x:.1f}" '
                   f'y2="{y:.1f}" stroke="{FAINT}" stroke-width="1" '
                   f'stroke-dasharray="2 3"/>')

    if prev_budget:
        xp = sx(prev_budget)
        out.append(f'<line x1="{xp:.1f}" y1="{pad_t - 20}" x2="{xp:.1f}" '
                   f'y2="{y:.1f}" stroke="#8a6d3b" stroke-width="1.5" '
                   f'stroke-dasharray="5 3"/>')
        out.append(_text(xp, pad_t - 25,
                         f"previous {_fmt(prev_budget, symbol, 0)}", 8.5,
                         "#8a6d3b", "middle", "700"))

    xb = sx(budget)
    out.append(f'<line x1="{xb:.1f}" y1="{pad_t - 34}" x2="{xb:.1f}" '
               f'y2="{y:.1f}" stroke="#d93025" stroke-width="2"/>')
    out.append(_text(xb, pad_t - 39, f"budget {_fmt(budget, symbol, 0)}", 9.5,
                     "#d93025", "middle", "700"))

    for label, value, ly, note, bar_color in labels:
        out.append(_text(0, ly + bar_h / 2 + 4, label, 10.5, INK, "start", "600"))
        wpx = len(note) * 5.6 + 10
        outside_x = sx(value) + 8
        # An outside label that would reach the budget marker goes inside instead,
        # so its plate can never interrupt that line.
        inside = ((sx(value) - pad_l) > track_w - 132
                  or outside_x + wpx > sx(budget) - 4)
        px = (pad_l + 5) if inside else (outside_x - 4)
        tx = (pad_l + 9) if inside else outside_x
        out.append(f'<rect x="{px:.1f}" y="{ly + 3:.1f}" width="{wpx:.1f}" '
                   f'height="{bar_h - 6:.1f}" rx="2" fill="#ffffff"/>')
        out.append(_text(tx, ly + bar_h / 2 + 4, note, 10, INK, "start", "600"))
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- sparkline

def inline_bar(value: float, mx: float, color: str, w: float = 52,
               h: float = 9) -> str:
    """Tiny bar for table cells."""
    frac = 0.0 if mx <= 0 else max(0.0, min(1.0, value / mx))
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" '
            f'class="inline-bar" xmlns="http://www.w3.org/2000/svg">'
            f'<rect x="0" y="1" width="{w}" height="{h - 2}" rx="1.5" '
            f'fill="{TRACK}"/>'
            f'<rect x="0" y="1" width="{max(1.0, frac * w):.1f}" '
            f'height="{h - 2}" rx="1.5" fill="{color}"/></svg>')
