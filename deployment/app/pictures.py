"""Original drawings for every item (no copyrighted photos).

picture(style, category) returns an inline SVG on a 100 x 100 canvas:
  * clothes and shoes are drawn from adjustable outlines (leg shape, length, sleeves, soles...),
    so items in the same family still look different (skinny vs flare jeans, mini vs maxi skirt);
  * accessories and bags have their own drawings;
  * aesthetics get a "mood badge": their own colours, initials and motif;
  * colours get a swatch and patterns a fabric sample, both with a visible border.
"""
from html import escape

INK = "#2b2622"
STROKE = f'fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'


def _svg(body: str) -> str:
    return f'<svg viewBox="0 0 100 100" aria-hidden="true">{body}</svg>'


def _path(d: str, extra: str = "") -> str:
    return f'<path d="{d}" {STROKE} {extra}/>'


def _poly(points, closed=True) -> str:
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points) + (" Z" if closed else "")
    return _path(d)


# ------------------------------------------------------------------ bottoms

def bottoms(waist_y=14, rise=24, knee=12, hem=12, length=88, gap=2, extras=()) -> str:
    """Trousers, jeans and shorts. knee/hem = width of each leg at the knee/hem."""
    crotch = waist_y + rise
    knee_y = crotch + (length - crotch) * 0.5
    left_c, right_c = 50 - gap - 10, 50 + gap + 10
    parts = []
    for c, s in ((left_c, -1), (right_c, 1)):
        pts = [(50 + s * 20, waist_y), (50 + s * 21, crotch - 4), (c + s * knee / 2, knee_y), (c + s * hem / 2, length),
               (c - s * hem / 2, length), (c - s * knee / 2, knee_y), (50 + s * gap * 0.3, crotch)]
        parts.append(_poly(pts, closed=False))
    parts.append(_path(f"M30 {waist_y} L70 {waist_y} M30 {waist_y + 5} L70 {waist_y + 5}"))
    if "fly" in extras:
        parts.append(_path(f"M50 {waist_y + 5} Q53 {crotch - 6} 50 {crotch - 2}"))
        parts.append(_path(f"M33 {waist_y + 6} Q38 {waist_y + 13} 43 {waist_y + 7} M67 {waist_y + 6} Q62 {waist_y + 13} 57 {waist_y + 7}"))
    if "cargo" in extras:
        y = knee_y - 8
        parts.append(_path(f"M{left_c - 9} {y} h8 v10 h-8 Z M{right_c + 1} {y} h8 v10 h-8 Z"))
    if "pleat" in extras:
        parts.append(_path(f"M41 {waist_y + 5} L40 {crotch + 10} M59 {waist_y + 5} L60 {crotch + 10}"))
    if "cuff" in extras:
        for c in (left_c, right_c):
            parts.append(_path(f"M{c - hem / 2} {length - 5} L{c + hem / 2} {length - 5}"))
    if "drawstring" in extras:
        parts.append(_path(f"M47 {waist_y + 5} q-2 6 -4 8 M53 {waist_y + 5} q2 6 4 8"))
    if "stripe" in extras:
        parts.append(_path(f"M29 {waist_y + 6} L{left_c - knee / 2 + 2} {knee_y} L{left_c - hem / 2 + 2} {length} "
                           f"M71 {waist_y + 6} L{right_c + knee / 2 - 2} {knee_y} L{right_c + hem / 2 - 2} {length}"))
    if "fray" in extras:
        for c in (left_c, right_c):
            x0 = c - hem / 2
            parts.append(_path(" ".join(f"M{x0 + i * hem / 4:.1f} {length} l1 3" for i in range(5))))
    if "button" in extras:
        parts.append(f'<circle cx="50" cy="{waist_y + 2.5}" r="1.6" fill="{INK}"/>')
    if "belt" in extras:
        parts.append(_path(f"M44 {waist_y} v5 h12 v-5"))
    return _svg("".join(parts))


# ------------------------------------------------------------------ skirts and dresses

def skirt(top=26, waist=30, hem_y=80, hem=56, extras=()) -> str:
    l, r = 50 - waist / 2, 50 + waist / 2
    hl, hr = 50 - hem / 2, 50 + hem / 2
    if "balloon" in extras:
        body = _path(f"M{l} {top} Q{hl - 8} {(top + hem_y) / 2} {hl + 6} {hem_y} Q50 {hem_y + 6} {hr - 6} {hem_y} "
                     f"Q{hr + 8} {(top + hem_y) / 2} {r} {top} Z")
    else:
        body = _poly([(l, top), (hl, hem_y), (hr, hem_y), (r, top)])
    parts = [body, _path(f"M{l} {top + 5} L{r} {top + 5}")]
    if "pleats" in extras:
        n = 7
        for i in range(1, n):
            x_top, x_hem = l + (r - l) * i / n, hl + (hr - hl) * i / n
            parts.append(_path(f"M{x_top:.1f} {top + 5} L{x_hem:.1f} {hem_y}"))
    if "denim" in extras:
        parts.append(_path(f"M50 {top + 5} L50 {hem_y} M{l + 4} {top + 9} Q{l + 8} {top + 15} {l + 12} {top + 9}", 'stroke-dasharray="2 2"'))
    return _svg("".join(parts))


def dress(kind: str) -> str:
    """Dresses: a bodice on top of a skirt shape."""
    shapes = {
        #                 bodice top, waist y, hem y, hem width, straps
        "slip dress": (18, 44, 86, 40, "thin"),
        "bodycon dress": (20, 46, 76, 30, "none"),
        "wrap dress": (18, 44, 82, 50, "v"),
        "babydoll dress": (20, 34, 70, 64, "thin"),
        "sundress": (20, 42, 78, 62, "thin"),
        "corset dress": (22, 46, 84, 46, "none"),
    }
    top_y, waist_y, hem_y, hem, straps = shapes.get(kind, (20, 44, 82, 50, "thin"))
    bw = 30 if kind == "babydoll dress" else 28
    parts = [_poly([(50 - bw / 2, top_y), (37, waist_y), (50 - hem / 2, hem_y), (50 + hem / 2, hem_y),
                    (63, waist_y), (50 + bw / 2, top_y)])]
    parts.append(_path(f"M{50 - bw / 2} {top_y} Q50 {top_y + 6} {50 + bw / 2} {top_y}"))
    if straps == "thin":
        parts.append(_path(f"M{50 - bw / 2 + 3} {top_y} L{50 - bw / 2 + 5} {top_y - 10} M{50 + bw / 2 - 3} {top_y} L{50 + bw / 2 - 5} {top_y - 10}"))
    if straps == "v":
        parts.append(_path(f"M{50 - bw / 2} {top_y} L50 {waist_y - 4} L{50 + bw / 2} {top_y} M50 {waist_y - 4} L{50 + hem / 2 - 6} {hem_y}"))
    parts.append(_path(f"M37 {waist_y} L63 {waist_y}"))
    if kind == "corset dress":
        parts.append(_path(" ".join(f"M46 {y} L54 {y + 4} M54 {y} L46 {y + 4}" for y in range(top_y + 6, waist_y - 4, 6))))
    if kind == "sundress":
        parts.append("".join(f'<circle cx="{x}" cy="{y}" r="2" fill="{INK}"/>' for x, y in ((40, 58), (56, 64), (46, 72), (62, 74))))
    if kind == "babydoll dress":
        parts.append(_path(f"M40 {waist_y} Q38 56 34 {hem_y} M60 {waist_y} Q62 56 66 {hem_y}"))
    return _svg("".join(parts))


# ------------------------------------------------------------------ tops

def top(sleeve="short", length=80, neck="crew", width=34, extras=()) -> str:
    l, r = 50 - width / 2, 50 + width / 2
    sh = 24  # shoulder line
    parts = []
    if neck in ("tube", "off"):
        y0 = 34 if neck == "tube" else 30
        parts.append(_poly([(l, y0), (l + 1, length), (r - 1, length), (r, y0)]))
        parts.append(_path(f"M{l} {y0} Q50 {y0 + 3} {r} {y0}"))
        if neck == "off":
            parts.append(_path(f"M{l} {y0} L{l - 12} {y0 + 6} L{l - 14} {y0 + 16} L{l} {y0 + 12} "
                               f"M{r} {y0} L{r + 12} {y0 + 6} L{r + 14} {y0 + 16} L{r} {y0 + 12}"))
        return _svg("".join(parts))
    if neck == "halter":
        parts.append(_poly([(44, 22), (l, 40), (l + 1, length), (r - 1, length), (r, 40), (56, 22)]))
        parts.append(_path("M44 22 Q50 14 56 22"))
        return _svg("".join(parts))
    drop = {"none": 0, "cap": 8, "short": 16, "long": 40}[sleeve]
    parts.append(_poly([(l, sh + 4), (l, length), (r, length), (r, sh + 4)], closed=False))
    parts.append(_path(f"M{l} {sh + 4} L{l + 8} {sh} L43 {sh - 2} M{r} {sh + 4} L{r - 8} {sh} L57 {sh - 2}"))
    if drop:
        parts.append(_poly([(l + 2, sh + 2), (l - drop * 0.45, sh + drop * 0.9), (l - drop * 0.45 + 7, sh + drop * 0.9 + 3), (l, sh + 14)], closed=False))
        parts.append(_poly([(r - 2, sh + 2), (r + drop * 0.45, sh + drop * 0.9), (r + drop * 0.45 - 7, sh + drop * 0.9 + 3), (r, sh + 14)], closed=False))
    else:
        parts.append(_path(f"M{l} {sh + 4} Q{l + 4} {sh + 14} {l} {sh + 18} M{r} {sh + 4} Q{r - 4} {sh + 14} {r} {sh + 18}"))
    if neck == "crew":
        parts.append(_path(f"M43 {sh - 2} Q50 {sh + 5} 57 {sh - 2}"))
    elif neck == "v":
        parts.append(_path(f"M43 {sh - 2} L50 {sh + 10} L57 {sh - 2}"))
    elif neck == "turtle":
        parts.append(_path(f"M43 {sh - 2} L43 {sh - 10} L57 {sh - 10} L57 {sh - 2} M43 {sh - 6} L57 {sh - 6}"))
    elif neck == "hood":
        parts.append(_path(f"M41 {sh - 1} Q38 {sh - 18} 50 {sh - 18} Q62 {sh - 18} 59 {sh - 1} M46 {sh} L46 {sh + 8} M54 {sh} L54 {sh + 8}"))
        parts.append(_path(f"M40 {length - 22} h20 l-3 10 h-14 Z"))
    elif neck == "sweetheart":
        parts.append(_path(f"M43 {sh - 2} Q46 {sh + 8} 50 {sh + 4} Q54 {sh + 8} 57 {sh - 2}"))
    if "rib" in extras:
        parts.append(_path(f"M{l} {length - 5} L{r} {length - 5}"))
    if "buttons" in extras:
        parts.append(_path(f"M50 {sh + 4} L50 {length}"))
        parts.append("".join(f'<circle cx="53" cy="{y}" r="1.4" fill="{INK}"/>' for y in range(sh + 10, int(length) - 4, 10)))
    if "graphic" in extras:
        cy = (sh + length) / 2
        parts.append(f'<circle cx="50" cy="{cy}" r="7" {STROKE}/>' + _path(f"M45 {cy + 2} l5 -6 l5 6"))
    if "mesh" in extras:
        parts.append("".join(f'<circle cx="{x}" cy="{y}" r=".9" fill="{INK}"/>'
                             for x in range(int(l) + 4, int(r) - 2, 6) for y in range(sh + 8, int(length) - 2, 6)))
    if "lacing" in extras:
        parts.append(_path(" ".join(f"M46 {y} L54 {y + 4} M54 {y} L46 {y + 4}" for y in range(sh + 8, int(length) - 6, 7))))
    if "knit" in extras:
        parts.append(_path(" ".join(f"M{x} {sh + 10} L{x} {length - 6}" for x in range(int(l) + 6, int(r) - 2, 6)), 'stroke-width="1" opacity=".5"'))
    return _svg("".join(parts))


# ------------------------------------------------------------------ outerwear

def jacket(length=78, extras=()) -> str:
    l, r, sh = 32, 68, 22
    parts = [_poly([(l, sh + 4), (l - 1, length), (r + 1, length), (r, sh + 4)], closed=False),
             _path(f"M{l} {sh + 4} L{l + 7} {sh} L43 {sh - 2} M{r} {sh + 4} L{r - 7} {sh} L57 {sh - 2}"),
             _poly([(l + 1, sh + 3), (l - 14, sh + 40), (l - 8, sh + 44), (l, sh + 18)], closed=False),
             _poly([(r - 1, sh + 3), (r + 14, sh + 40), (r + 8, sh + 44), (r, sh + 18)], closed=False)]
    if "lapels" in extras:
        parts.append(_path(f"M43 {sh - 2} L39 {sh + 8} L45 {sh + 10} L50 {sh + 26} L55 {sh + 10} L61 {sh + 8} L57 {sh - 2}"))
        parts.append(f'<circle cx="51" cy="{sh + 34}" r="1.6" fill="{INK}"/>')
    elif "zip_diagonal" not in extras:
        parts.append(_path(f"M50 {sh + 2} L50 {length}"))
    if "quilt" in extras:
        parts.append(_path(" ".join(f"M{l} {y} Q50 {y + 4} {r} {y}" for y in range(sh + 12, int(length), 10))))
        parts.append(_path(f"M43 {sh - 2} L43 {sh - 8} L57 {sh - 8} L57 {sh - 2}"))
    if "rib" in extras:
        parts.append(_path(f"M{l - 1} {length - 6} L{r + 1} {length - 6} M{l - 12} {sh + 37} l7 4 M{r + 12} {sh + 37} l-7 4"))
        parts.append(_path(f"M43 {sh - 2} Q50 {sh + 3} 57 {sh - 2}"))
    if "yoke" in extras:
        parts.append(_path(f"M{l} {sh + 12} L{r} {sh + 12}", 'stroke-dasharray="2 2"'))
        parts.append(_path(f"M37 {sh + 16} h9 v8 h-9 Z M54 {sh + 16} h9 v8 h-9 Z"))
        parts.append(_path(f"M43 {sh - 2} L45 {sh + 6} L50 {sh + 2} L55 {sh + 6} L57 {sh - 2}"))
    if "zip_diagonal" in extras:
        parts.append(_path(f"M44 {sh} L58 {length}"))
        parts.append(_path(f"M43 {sh - 2} L36 {sh + 8} L42 {sh + 12} M57 {sh - 2} L64 {sh + 8} L58 {sh + 12}"))
    if "hood" in extras:
        parts.append(_path(f"M41 {sh} Q38 {sh - 16} 50 {sh - 16} Q62 {sh - 16} 59 {sh}"))
        parts.append(_path(f"M{l} {sh + 22} L{r} {sh + 12}"))
    if "shirt" in extras:
        parts.append(_path(f"M43 {sh - 2} L45 {sh + 6} L50 {sh + 2} L55 {sh + 6} L57 {sh - 2}"))
        parts.append(_path(f"M37 {sh + 12} h8 v8 h-8 Z M55 {sh + 12} h8 v8 h-8 Z"))
        parts.append("".join(f'<circle cx="52" cy="{y}" r="1.3" fill="{INK}"/>' for y in range(sh + 10, int(length) - 4, 10)))
    if "fleece" in extras:
        parts.append("".join(f'<circle cx="{x}" cy="{y}" r="1" fill="{INK}" opacity=".45"/>'
                             for x in range(l + 4, r - 2, 7) for y in range(sh + 10, int(length) - 4, 8)))
        parts.append(_path(f"M43 {sh - 2} L43 {sh - 8} L57 {sh - 8} L57 {sh - 2}"))
    if "fur" in extras:
        parts.append(_path(" ".join(f"M{x} {length} q2 4 4 0" for x in range(l - 1, r, 4))))
        parts.append(_path(f"M41 {sh - 2} q-4 6 0 12 q-4 6 0 12 M59 {sh - 2} q4 6 0 12 q4 6 0 12"))
    if "belt" in extras:
        parts.append(_path(f"M{l} {sh + 30} L{r} {sh + 30} M{l} {sh + 34} L{r} {sh + 34} M56 {sh + 30} v4"))
        parts.append(_path(f"M43 {sh - 2} L38 {sh + 10} L46 {sh + 12} M57 {sh - 2} L62 {sh + 10} L54 {sh + 12}"))
    return _svg("".join(parts))


# ------------------------------------------------------------------ shoes (side view)

def shoe(shaft=0, heel=0, sole=4, toe="round", extras=()) -> str:
    """shaft = boot height above the ankle, heel = heel height, sole = sole thickness."""
    ground = 82
    if "straps_open" in extras:
        top_s = ground - sole
        return _svg(_path(f"M20 {top_s} L84 {top_s} L84 {ground} L20 {ground} Z")
                    + _path(f"M50 {top_s} Q58 {top_s - 16} 68 {top_s} M70 {top_s} Q76 {top_s - 12} 82 {top_s} "
                            f"M24 {top_s} Q22 {top_s - 16} 34 {top_s - 18} L50 {top_s - 8}"))
    top_y = ground - sole - heel - 18
    back_x, front_x = 24, (88 if toe == "point" else 82)
    ankle = top_y - shaft
    bx = back_x + (10 if "backless" in extras else 0)
    base = ground - sole
    upper = [(bx, base - heel), (bx, ankle if not "backless" in extras else base - heel), (back_x + 18, ankle), (back_x + 20, top_y + 2)]
    if toe == "point":
        upper += [(front_x - 10, base - 6), (front_x, base)]
    else:
        upper += [(front_x - 14, base - 14), (front_x, base - 4), (front_x, base)]
    parts = [_poly(upper, closed=False)]
    if heel:
        parts.append(_path(f"M{bx} {base - heel} L{bx + 6} {base - heel} L{bx + 8} {ground} L{bx + 4} {ground} Z"))
        parts.append(_path(f"M{bx + 6} {base - heel} Q{front_x - 30} {base - heel + 2} {front_x - 18} {base} L{front_x} {base}"))
    if sole >= 4:
        parts.append(_path(f"M{bx + (8 if heel else 0)} {ground} L{front_x} {ground} L{front_x} {base}"
                           + ("" if heel else f" M{bx} {base} L{bx} {ground}")))
    else:
        parts.append(_path(f"M{bx + (8 if heel else 0)} {ground} L{front_x} {ground}"))
    if "laces" in extras:
        n = max(2, int((top_y - ankle) / 6) + 2)
        parts.append(_path(" ".join(f"M{back_x + 19 + i * 3} {ankle + 4 + i * 5} l7 -2" for i in range(n))))
    if "strap" in extras:
        parts.append(_path(f"M{back_x + 14} {top_y + 6} L{back_x + 34} {top_y + 10}"))
        parts.append(f'<circle cx="{back_x + 32}" cy="{top_y + 10}" r="1.5" fill="{INK}"/>')
    if "bow" in extras:
        parts.append(_path(f"M{front_x - 22} {base - 14} l-4 -4 l0 8 Z M{front_x - 22} {base - 14} l4 -4 l0 8 Z"))
    if "penny" in extras:
        parts.append(_path(f"M{back_x + 30} {top_y + 8} L{front_x - 14} {top_y + 14} M{back_x + 40} {top_y + 10} l0 4 l6 0 l0 -3"))
    if "panels" in extras:
        parts.append(_path(f"M{back_x + 10} {base - 4} Q{back_x + 30} {top_y + 4} {front_x - 16} {base - 6} "
                           f"M{back_x + 4} {top_y + 8} L{back_x + 16} {base - 2}"))
    if "stitch" in extras:
        parts.append(_path(f"M{back_x + 4} {ankle + 8} Q{back_x + 12} {ankle + 22} {back_x + 4} {ankle + 34} "
                           f"M{back_x + 14} {ankle + 8} Q{back_x + 6} {ankle + 22} {back_x + 14} {ankle + 34}"))
    if "clog" in extras:
        parts.append(_path(" ".join(f"M{x} {base + 2} l0 {sole - 4}" for x in range(bx + 6, front_x, 8)), 'stroke-width="1" opacity=".5"'))
    return _svg("".join(parts))


# ------------------------------------------------------------------ bags

def bag(kind: str) -> str:
    shapes = {
        "tote bag": _poly([(26, 38), (74, 38), (70, 86), (30, 86)]) + _path("M36 38 Q36 16 44 16 Q50 16 50 38 M50 38 Q50 16 56 16 Q64 16 64 38"),
        "shoulder bag": _path("M26 50 L74 50 L72 82 Q50 88 28 82 Z M26 50 Q50 64 74 50") + _path("M30 50 Q50 6 70 50"),
        "crossbody bag": _path("M34 56 h32 v24 h-32 Z M34 62 h32") + _path("M36 56 L14 10 M64 56 L86 10"),
        "bucket bag": _path("M30 40 Q30 34 50 34 Q70 34 70 40 L66 84 Q50 90 34 84 Z M30 40 Q50 46 70 40") + _path("M38 38 Q50 14 62 38 M34 46 Q50 52 66 46"),
        "mini bag": _path("M40 52 h20 v20 h-20 Z M40 58 h20") + _path("M44 52 Q50 36 56 52"),
        "hobo bag": _path("M20 50 Q50 92 80 50 Q66 58 50 58 Q34 58 20 50 Z") + _path("M20 50 Q50 10 80 50"),
        "clutch bag": _path("M20 42 h60 v32 h-60 Z M20 42 L50 60 L80 42") + f'<circle cx="50" cy="60" r="2" fill="{INK}"/>',
        "baguette bag": _path("M18 52 Q18 44 26 44 h48 Q82 44 82 52 v14 Q82 72 74 72 h-48 Q18 72 18 66 Z M18 52 h64") + _path("M30 44 Q50 26 70 44"),
        "belt bag": _path("M24 50 Q50 40 76 50 L74 70 Q50 78 26 70 Z M28 58 Q50 52 72 58") + _path("M10 52 L24 54 M76 54 L90 52"),
        "backpack": _path("M30 34 Q30 18 50 18 Q70 18 70 34 L72 84 L28 84 Z M36 56 h28 v18 h-28 Z M44 18 v8 h12 v-8"),
    }
    return _svg(shapes.get(kind, shapes["tote bag"]))


# ------------------------------------------------------------------ accessories

ACCESSORIES = {
    "beanie": _path("M24 64 Q24 26 50 26 Q76 26 76 64 Z M22 64 h56 v12 h-56 Z M30 66 v10 M40 66 v10 M50 66 v10 M60 66 v10 M70 66 v10")
              + f'<circle cx="50" cy="22" r="5" {STROKE}/>',
    "baseball cap": _path("M22 62 Q22 32 50 32 Q78 32 78 62 Z M78 62 Q92 64 94 72 L58 72 M50 32 v-4 M36 36 Q42 50 40 62 M64 36 Q58 50 60 62"),
    "bucket hat": _path("M32 56 Q32 30 50 30 Q68 30 68 56 Z M32 56 L18 72 L82 72 L68 56 M32 52 h36"),
    "scarf": _path("M30 20 Q50 30 70 20 L70 34 Q50 44 30 34 Z M40 38 L36 84 L48 84 L50 40 M56 40 L58 76 L68 76 L64 36 "
                   "M36 84 l0 4 M40 84 l0 4 M44 84 l0 4 M58 76 l0 4 M62 76 l0 4 M66 76 l0 4"),
    "aviator sunglasses": _path("M12 40 L88 40 M16 40 Q16 66 30 66 Q44 66 44 44 M56 44 Q56 66 70 66 Q84 66 84 40 M44 44 Q50 38 56 44"),
    "oversized sunglasses": _path("M10 36 h80 M12 36 v20 Q12 66 26 66 h10 Q46 66 46 56 v-20 M54 36 v20 Q54 66 64 66 h10 Q88 66 88 56 v-20 M46 42 Q50 38 54 42"),
    "hoop earrings": f'<circle cx="34" cy="56" r="16" {STROKE}/><circle cx="68" cy="56" r="16" {STROKE}/>' + _path("M34 34 v6 M68 34 v6"),
    "layered necklace": _path("M24 18 Q50 52 76 18 M22 18 Q50 68 78 18 M20 18 Q50 84 80 18")
                        + f'<circle cx="50" cy="60" r="2.5" fill="{INK}"/><circle cx="50" cy="76" r="3.5" fill="{INK}"/>',
    "chunky necklace": _path("M22 20 Q50 70 78 20") + "".join(
        f'<circle cx="{50 + 28 * t:.1f}" cy="{20 + 45 * (1 - t * t):.1f}" r="5" {STROKE}/>' for t in (-0.9, -0.6, -0.3, 0, 0.3, 0.6, 0.9)),
    "claw clip": _path("M24 46 Q50 30 76 46 L72 54 Q50 42 28 54 Z M30 54 Q30 70 26 76 M40 50 Q40 70 36 78 M50 48 v30 M60 50 Q60 70 64 78 M70 54 Q70 70 74 76"),
    "scrunchie": _path("M50 24 q8 0 10 6 q8 -2 10 6 q6 4 2 10 q4 6 -2 10 q0 8 -8 8 q-4 6 -12 4 q-8 4 -12 -2 q-8 0 -8 -8 "
                       "q-6 -4 -2 -10 q-4 -6 2 -10 q2 -8 10 -6 q2 -6 10 -8 Z") + f'<circle cx="50" cy="50" r="9" {STROKE}/>',
    "headband": _path("M18 66 Q50 10 82 66 M24 64 Q50 20 76 64") + _path("M40 26 l-6 -8 l12 2 Z M60 26 l6 -8 l-12 2 Z"),
}

# ------------------------------------------------------------------ catalogue

DRAWN = {
    # jeans and denim
    "skinny jeans": lambda: bottoms(knee=9, hem=8, extras=("fly",)),
    "straight leg jeans": lambda: bottoms(knee=13, hem=13, extras=("fly",)),
    "wide leg jeans": lambda: bottoms(knee=20, hem=26, gap=1, extras=("fly",)),
    "baggy jeans": lambda: bottoms(rise=28, knee=20, hem=20, gap=1, extras=("fly", "cuff")),
    "bootcut jeans": lambda: bottoms(knee=11, hem=18, extras=("fly",)),
    "flare jeans": lambda: bottoms(knee=9, hem=26, extras=("fly",)),
    "mom jeans": lambda: bottoms(waist_y=10, rise=28, knee=15, hem=11, length=80, extras=("fly", "button")),
    "low rise jeans": lambda: bottoms(waist_y=24, rise=16, knee=13, hem=14, extras=("fly",)),
    "high waisted jeans": lambda: bottoms(waist_y=8, rise=30, knee=12, hem=12, extras=("fly", "button")),
    "barrel jeans": lambda: bottoms(knee=24, hem=10, length=84, extras=("fly",)),
    "boyfriend jeans": lambda: bottoms(knee=17, hem=14, length=80, extras=("fly", "cuff")),
    "cargo jeans": lambda: bottoms(knee=17, hem=16, extras=("fly", "cargo")),
    "jorts": lambda: bottoms(knee=17, hem=18, length=56, extras=("fly", "fray")),
    "denim skirt": lambda: skirt(hem_y=66, hem=44, extras=("denim",)),
    # trousers and shorts
    "cargo pants": lambda: bottoms(knee=16, hem=15, extras=("cargo", "belt")),
    "parachute pants": lambda: bottoms(knee=20, hem=12, extras=("drawstring", "cuff", "cargo")),
    "bell bottoms": lambda: bottoms(knee=10, hem=28, gap=3),
    "leggings": lambda: bottoms(waist_y=12, knee=8, hem=7, gap=1),
    "joggers": lambda: bottoms(knee=15, hem=9, extras=("drawstring", "cuff")),
    "sweatpants": lambda: bottoms(knee=17, hem=14, extras=("drawstring", "cuff")),
    "track pants": lambda: bottoms(knee=14, hem=13, extras=("stripe", "drawstring")),
    "pleated trousers": lambda: bottoms(knee=15, hem=14, extras=("pleat", "belt")),
    "capri pants": lambda: bottoms(knee=11, hem=11, length=70),
    "harem pants": lambda: bottoms(rise=40, knee=24, hem=9, gap=1, extras=("cuff",)),
    "palazzo pants": lambda: bottoms(knee=26, hem=32, gap=0, extras=("belt",)),
    "culottes": lambda: bottoms(knee=24, hem=28, length=68, gap=1),
    "bike shorts": lambda: bottoms(knee=10, hem=10, length=48, gap=1),
    "bermuda shorts": lambda: bottoms(knee=17, hem=18, length=60, extras=("belt", "cuff")),
    "leather pants": lambda: bottoms(knee=12, hem=12, extras=("fly", "button")),
    # skirts and dresses
    "mini skirt": lambda: skirt(hem_y=56, hem=46),
    "midi skirt": lambda: skirt(hem_y=76, hem=50),
    "maxi skirt": lambda: skirt(hem_y=90, hem=56),
    "pleated skirt": lambda: skirt(hem_y=74, hem=58, extras=("pleats",)),
    "tennis skirt": lambda: skirt(hem_y=56, hem=58, extras=("pleats",)),
    "balloon skirt": lambda: skirt(hem_y=70, hem=44, extras=("balloon",)),
    "slip dress": lambda: dress("slip dress"), "bodycon dress": lambda: dress("bodycon dress"),
    "wrap dress": lambda: dress("wrap dress"), "babydoll dress": lambda: dress("babydoll dress"),
    "sundress": lambda: dress("sundress"), "corset dress": lambda: dress("corset dress"),
    # tops and knitwear
    "crop top": lambda: top(sleeve="short", length=52),
    "corset top": lambda: top(sleeve="none", length=62, neck="sweetheart", width=30, extras=("lacing",)),
    "baby tee": lambda: top(sleeve="cap", length=62, width=30),
    "tube top": lambda: top(neck="tube", length=60, width=32),
    "halter top": lambda: top(neck="halter", length=66, width=32),
    "off the shoulder top": lambda: top(neck="off", length=70, width=34),
    "tank top": lambda: top(sleeve="none", length=78, width=30),
    "oversized t shirt": lambda: top(sleeve="short", length=86, width=46),
    "graphic tee": lambda: top(sleeve="short", length=80, extras=("graphic",)),
    "cardigan": lambda: top(sleeve="long", length=80, neck="v", extras=("buttons", "rib")),
    "sweater vest": lambda: top(sleeve="none", length=74, neck="v", extras=("rib", "knit")),
    "turtleneck": lambda: top(sleeve="long", length=80, neck="turtle", extras=("rib",)),
    "hoodie": lambda: top(sleeve="long", length=80, neck="hood", width=38, extras=("rib",)),
    "mesh top": lambda: top(sleeve="long", length=72, extras=("mesh",)),
    # outerwear
    "blazer": lambda: jacket(length=80, extras=("lapels",)),
    "bomber jacket": lambda: jacket(length=68, extras=("rib",)),
    "puffer jacket": lambda: jacket(length=74, extras=("quilt",)),
    "trench coat": lambda: jacket(length=94, extras=("belt",)),
    "leather jacket": lambda: jacket(length=70, extras=("zip_diagonal",)),
    "denim jacket": lambda: jacket(length=70, extras=("yoke",)),
    "windbreaker": lambda: jacket(length=74, extras=("hood",)),
    "shacket": lambda: jacket(length=80, extras=("shirt",)),
    "fleece jacket": lambda: jacket(length=72, extras=("fleece",)),
    "faux fur coat": lambda: jacket(length=86, extras=("fur",)),
    # shoes
    "ballet flats": lambda: shoe(sole=2, extras=("bow",)),
    "mary janes": lambda: shoe(sole=3, heel=4, extras=("strap",)),
    "loafers": lambda: shoe(sole=4, heel=2, extras=("penny",)),
    "chunky sneakers": lambda: shoe(sole=12, extras=("laces", "panels")),
    "white sneakers": lambda: shoe(sole=6, extras=("laces",)),
    "dad sneakers": lambda: shoe(sole=9, extras=("panels",)),
    "platform shoes": lambda: shoe(sole=14, heel=8),
    "combat boots": lambda: shoe(shaft=20, sole=7, extras=("laces",)),
    "knee high boots": lambda: shoe(shaft=44, heel=8, sole=3),
    "cowboy boots": lambda: shoe(shaft=26, heel=8, sole=3, toe="point", extras=("stitch",)),
    "kitten heels": lambda: shoe(heel=10, sole=2, toe="point"),
    "platform sandals": lambda: shoe(sole=12, extras=("straps_open",)),
    "clogs": lambda: shoe(sole=10, extras=("backless", "clog")),
    "mules": lambda: shoe(sole=3, heel=6, extras=("backless",)),
}

# Aesthetics: a mood badge with its own colours, initials and a small motif.
MOTIFS = {
    "stars": '<path d="M0 -6 L1.8 -1.8 L6 0 L1.8 1.8 L0 6 L-1.8 1.8 L-6 0 L-1.8 -1.8 Z"/>',
    "bow": '<path d="M0 0 L-7 -5 L-7 5 Z M0 0 L7 -5 L7 5 Z"/><circle r="1.6"/>',
    "pearl": '<circle r="3.2"/>', "leaf": '<path d="M-6 4 Q-6 -6 6 -6 Q6 4 -6 4 Z"/>',
    "mountain": '<path d="M-8 5 L-2 -5 L2 1 L4 -2 L8 5 Z"/>', "book": '<path d="M-7 -5 h6 v10 h-6 Z M1 -5 h6 v10 h-6 Z"/>',
    "flower": '<circle cx="0" cy="-3.5" r="2.5"/><circle cx="3.5" cy="0" r="2.5"/><circle cx="0" cy="3.5" r="2.5"/><circle cx="-3.5" cy="0" r="2.5"/>',
    "bolt": '<path d="M2 -7 L-4 1 L0 1 L-2 7 L4 -1 L0 -1 Z"/>', "drop": '<path d="M0 -6 Q5 1 0 6 Q-5 1 0 -6 Z"/>',
    "square": '<rect x="-4.5" y="-4.5" width="9" height="9"/>', "circle": '<circle r="4.5" fill="none" stroke-width="2"/>',
    "wave": '<path d="M-8 0 Q-4 -5 0 0 Q4 5 8 0" fill="none" stroke-width="2"/>',
}
AESTHETICS = {
    #                         background, ink, initials, motif
    "y2k fashion": ("#d9e4ff", "#3d3bd4", "Y2K", "stars"),
    "quiet luxury": ("#ebe4da", "#6b5b4b", "QL", "square"),
    "old money style": ("#dfe6dc", "#2f4a3a", "OM", "pearl"),
    "coquette": ("#fbe1e8", "#b23a62", "CQ", "bow"),
    "balletcore": ("#f6e6ea", "#8c5a69", "BC", "bow"),
    "gorpcore": ("#e3e8d3", "#4a5a2a", "GC", "mountain"),
    "cottagecore": ("#eef0d9", "#6b7a3a", "CC", "flower"),
    "dark academia": ("#e5ddd3", "#4a3426", "DA", "book"),
    "grunge": ("#dedede", "#2d2d2d", "GR", "bolt"),
    "boho style": ("#f3e2cf", "#9a5a2a", "BH", "leaf"),
    "streetwear": ("#ffe36e", "#1f1f1f", "SW", "bolt"),
    "preppy style": ("#dce6f3", "#1f3a64", "PR", "circle"),
    "athleisure": ("#dff1ec", "#1f6b5a", "AL", "wave"),
    "normcore": ("#e9e9e6", "#555550", "NC", "circle"),
    "clean girl aesthetic": ("#f4ece6", "#8a6a5a", "CG", "drop"),
    "mob wife aesthetic": ("#2a2420", "#e9cfa8", "MW", "pearl"),
    "capsule wardrobe": ("#ecebe7", "#3a3a38", "CW", "square"),
}

SWATCHES = {
    "baby blue": "#a9cbe6", "burgundy": "#6d1f2f", "butter yellow": "#f3e2a1", "cherry red": "#b3122e",
    "chocolate brown": "#4e3426", "lilac": "#c8b2dc", "olive green": "#6b6b35", "sage green": "#a7b59a",
}
FABRICS = {
    "leopard print": ("#d9a866", '<ellipse cx="6" cy="6" rx="3.2" ry="2.4" fill="none" stroke="#3a2516" stroke-width="1.6"/>'
                                 '<ellipse cx="15" cy="15" rx="2.6" ry="2" fill="#3a2516"/>'),
    "plaid": ("#8d2b2b", '<rect x="0" y="7" width="20" height="5" fill="#1f2a44" opacity=".7"/>'
                         '<rect x="7" y="0" width="5" height="20" fill="#1f2a44" opacity=".7"/>'
                         '<rect x="0" y="16" width="20" height="1" fill="#e9d38c"/>'),
    "gingham": ("#ffffff", '<rect width="10" height="20" fill="#e7a1ad" opacity=".55"/><rect width="20" height="10" fill="#e7a1ad" opacity=".55"/>'),
    "polka dot": ("#1f2433", '<circle cx="5" cy="5" r="2.4" fill="#f4f1ea"/><circle cx="15" cy="15" r="2.4" fill="#f4f1ea"/>'),
    "floral print": ("#f2e6ea", '<g fill="#c45f7a"><circle cx="10" cy="6" r="2.2"/><circle cx="14" cy="10" r="2.2"/>'
                                '<circle cx="10" cy="14" r="2.2"/><circle cx="6" cy="10" r="2.2"/></g><circle cx="10" cy="10" r="1.6" fill="#e9c46a"/>'),
    "tie dye": ("#f6c6d8", '<circle cx="10" cy="10" r="9" fill="none" stroke="#8fb8e8" stroke-width="3"/>'
                           '<circle cx="10" cy="10" r="4" fill="none" stroke="#f0d36b" stroke-width="2.5"/>'),
    "lace": ("#fbf8f3", '<circle cx="10" cy="10" r="6" fill="none" stroke="#b9ada0" stroke-width="1"/>'
                        '<circle cx="10" cy="10" r="2" fill="none" stroke="#b9ada0" stroke-width="1"/>'),
    "sequin": ("#c9c4cf", '<circle cx="5" cy="5" r="3.5" fill="#efeaf3"/><circle cx="15" cy="15" r="3.5" fill="#efeaf3"/>'
                          '<circle cx="15" cy="5" r="3.5" fill="#aaa3b3"/><circle cx="5" cy="15" r="3.5" fill="#aaa3b3"/>'),
    "velvet": ("#4b1730", '<rect width="20" height="20" fill="#6a2445" opacity=".5"/>'),
    "satin": ("#e8d7c3", '<path d="M0 14 Q10 4 20 14" stroke="#fff6ea" stroke-width="3" fill="none"/>'),
    "linen": ("#e6dccb", '<path d="M0 5 H20 M0 10 H20 M0 15 H20" stroke="#cfc2ac" stroke-width=".8"/>'
                         '<path d="M5 0 V20 M10 0 V20 M15 0 V20" stroke="#d9cdb8" stroke-width=".6"/>'),
}
BORDER = 'fill="none" stroke="rgba(43,38,34,.3)" stroke-width="1.5"'


def mood_badge(name: str) -> str:
    bg, ink, initials, motif = AESTHETICS[name]
    marks = "".join(f'<g transform="translate({x} {y}) scale({s})" fill="{ink}" stroke="{ink}">{MOTIFS[motif]}</g>'
                    for x, y, s in ((26, 28, .9), (76, 30, .7), (72, 76, 1.0), (28, 74, .6)))
    return _svg(f'<circle cx="50" cy="50" r="40" fill="{bg}"/><circle cx="50" cy="50" r="40" {BORDER}/>{marks}'
                f'<text x="50" y="58" text-anchor="middle" font-family="Poppins, sans-serif" font-weight="600" '
                f'font-size="{22 if len(initials) == 2 else 19}" letter-spacing="1" fill="{ink}">{escape(initials)}</text>')


def picture(style: str, category: str) -> str:
    name = style.lower()
    if name in SWATCHES:
        return _svg(f'<circle cx="50" cy="50" r="36" fill="{SWATCHES[name]}"/><circle cx="50" cy="50" r="36" {BORDER}/>')
    if name in FABRICS:
        bg, motif = FABRICS[name]
        pid = "p-" + name.replace(" ", "-")
        return _svg(f'<defs><pattern id="{pid}" width="20" height="20" patternUnits="userSpaceOnUse">'
                    f'<rect width="20" height="20" fill="{bg}"/>{motif}</pattern></defs>'
                    f'<rect x="14" y="14" width="72" height="72" rx="8" fill="url(#{pid})"/>'
                    f'<rect x="14" y="14" width="72" height="72" rx="8" {BORDER}/>')
    if name in AESTHETICS:
        return mood_badge(name)
    if name in DRAWN:
        return DRAWN[name]()
    if name in ACCESSORIES:
        return _svg(ACCESSORIES[name])
    if category == "Bags" or "bag" in name:
        return bag(name)
    return _svg(_path("M50 30 Q50 22 56 22 Q62 22 62 28 Q62 34 50 40 L14 66 L86 66 Z"))  # hanger, for items added later
