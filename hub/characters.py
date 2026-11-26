"""Characters beside the speech bubble: small pixel-art figures that act what a session is doing.

The author, 2026-11-25, after many tries (plushies, an aquarium, twelve sketches, six looks):
"all three of them are pretty good. So we can just put them as selection by the user", and of the
previews, "these previews look good. You can build them." Two of the three are drawn here, as
pixel art: Familiars (seven creatures with seven tempers since 2026-11-26, when the axolotl and the
dragon joined and the shellback and the toadstool were redrawn; the author: "We can maybe do more
than 5", and of the preview, "you can put them") and Operators (five people on the line, each with
their own headset and something of their own). The previews they were drawn from are
`docs/dev/looks/characters.html`; this is the same drawing, ported from its JavaScript.

The hub draws every frame of a session's character once, into a sheet of 40 by 40 pixel cells,
one row for each moment (idle, working, speaking at four loudnesses, needs you, done, failed,
listening), and keeps it as a PNG where the overlay can read it. The overlay only picks the cell:
by the moment, the time since it began, and, while the session speaks, how loud the voice is.
A session's character follows its color, so the same project keeps the same figure, or, with
overlay.character_pick at random, its id (`pick`).
"""
from __future__ import annotations

import colorsys
import hashlib
import math
import os
import struct
import threading
import zlib
from typing import Callable

N = 44  # a cell is N by N pixels
# Which look the engine draws: 1 is the look the author has seen in the overlay; 2 is a pass on what
# every figure shares (2026-11-26, after a pixel-art review: "charming at 2x and falls apart at
# 35 px, and most of the damage comes from the engine"): ramps built in OKLCH with an outline that
# shows on the dark glass, light from the top left, a selective outline, stepless glows, sparks in
# place of the done beams, bigger wide eyes, eyes looking down while working, a sound glyph while
# listening, a breath while speaking, working motions with in-betweens. Shown side by side in
# docs/dev/looks/look2.py; 1 stays until the author has seen it. 3 is the two mixed (2026-11-26, after
# a comparison of the two; the author: "I kinda prefer the default", "mostly the shading"): Classic's
# tones and shading with an outline lifted to show on the glass, Refined's eyes, sparks, sound sign
# and lantern, a glow without rings as strong as Classic's; shown in docs/dev/looks/look3.py.
# The Mix (3) is the one look since 2026-11-26, and the setting that chose between them is gone
# (the author: "There shouldn't be two choices. Make it only one. I guess mix is better."); 1 and
# 2 stay only for the comparison pages until their branches are folded away.
LOOK = 3
# What each look draws differently from Classic, by name; `has` asks the look being drawn.
PARTS = {
    1: frozenset(),
    2: frozenset({
        "ramp2",      # tones built in OKLCH (_ramp2)
        "flat",       # light from the top left, mostly flat across a part (_tone)
        "selective",  # the outline a tone lighter on the lit top and left
        "glow",       # glows without rings, in a strong tone of their color
        "sparks",     # sparks rising when done, in place of the grey beams
        "glyph",      # a sound sign ")" while listening, shared by every figure
        "wide",       # wide eyes a pixel wider and taller, with a catchlight
        "ink",        # x, shut and happy eyes in a tone that shows on the face
        "down",       # open eyes looking down while working
        "beat",       # working motions with frames in between, hops eased
        "breath",     # a breath while speaking
        "lantern2",   # the lantern's flame under its eyes (_lantern2)
    }),
    3: frozenset({
        "ramp3",      # Classic's tones with the outline lifted to show on the glass (_ramp3)
        "glow", "glow3",  # glows without rings, as strong as Classic's
        "sparks", "sparks3",  # the sparks, two pixels tall so they last at 35 px
        # not "wide": the author, 2026-11-26, of the needs-you and listening eyes in the Mix, "I
        # probably prefer the classic ... not consistent with the rest"
        "glyph", "ink", "lantern2",
    }),
}


def has(part: str) -> bool:
    """Whether the look being drawn (`LOOK`) has this part of what tells the looks apart."""
    return part in PARTS[LOOK]
# The figures are drawn on a 40 by 40 grid standing on row 38, and that grid sits this far down in
# the cell: room above for leaves raised high, hair, a jump (the author, 2026-11-26: "the
# animation seems cut when jumping and then falling down"; the sprout's leaves were cut flat).
OFF = 4
FLOOR = 38  # the row the figures stand on, in the drawing's own rows
# Frames a second, for every moment: 12 since 2026-11-26 (8 before; the author: "could we put
# more FPS?"), as smooth as hand-made pixel art usually moves; the sheets are half as long again.
FPS = 12
TAU = math.tau
STYLES = ("familiars", "operators", "sketch")  # sketch: the pencil operator, in hub/sketch.py
# The sheet: each row a moment and how many frames it has. Speaking has a row for each of four
# loudnesses; needs you and done have a first part that plays once, then a part that repeats.
SECONDS = [("idle", 4), ("working", 2), ("speaking0", 1), ("speaking1", 1), ("speaking2", 1), ("speaking3", 1),
           ("needs", 5), ("needs_hold", 1), ("done", 4), ("done_hold", 1), ("failed", 2), ("listen", 2)]
ROWS = [(name, seconds * FPS) for name, seconds in SECONDS]
LOUD = [0.0, 0.3, 0.6, 0.95]  # the loudness each speaking row is drawn at
LAYOUT = {"cell": N, "fps": FPS, "rows": {name: [i, count] for i, (name, count) in enumerate(ROWS)}}
WIDTH = max(count for _, count in ROWS) * N
HEIGHT = len(ROWS) * N
# The session colors the hub hands out (state.COLORS); one at the same place in this list as in
# that one gets the same figure every time.
from state import COLORS  # noqa: E402

import sketch  # noqa: E402

# A new drawing makes new sheets.
_SOURCE = hashlib.sha1(b"".join(open(f, "rb").read() for f in (__file__, sketch.__file__))).hexdigest()[:8]


def cell(style: str) -> int:
    """How many pixels a side a style's cells are: the pencil lines are drawn at twice the size,
    with smooth edges, and shown at their own size (the overlay finds it from the sheet's height)."""
    return sketch.CELL if style == "sketch" else N


def kinds(style: str) -> int:
    """How many figures a style has: seven familiars, five operators; the sketch is one operator,
    and its kind only varies the pencil's wobble."""
    return len(FAMILIARS) if style == "familiars" else 5


def kind_of(color: str, count: int) -> int:
    """Which of `count` figures a session of this color gets: by the color's place in the hub's
    list, so the first sessions get the figures in order, or by the color itself."""
    color = color.upper()
    if color in COLORS:
        return COLORS.index(color) % count
    return zlib.crc32(color.encode()) % count


# How a session's figure is chosen (overlay.character_pick): by its color, so the same project
# keeps the same figure, or at random, which here means by the session's id: it looks random, and
# a session keeps its figure for its whole life with nothing stored. The author, 2026-11-26:
# "maybe someone want the companion to be random".
PICKS = ("color", "random")


def pick(style: str, color: str, session: str = "", how: str = "color") -> int:
    """Which figure of the style a session gets."""
    count = kinds(style)
    if how == "random" and session:
        return zlib.crc32(session.encode()) % count
    return kind_of(color, count)


# ---- colors -----------------------------------------------------------------------------------

def _rgb(color) -> tuple[float, float, float]:
    if isinstance(color, tuple):
        return color
    h = color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)


def tint(color: str, k: float) -> str:
    """Darker towards black (k < 0) or lighter towards white (k > 0)."""
    return _hex(tuple(v * (1 + k) if k < 0 else v + (255 - v) * k for v in _rgb(color)))


def _toward(h: float, t: float, k: float) -> float:
    d = ((t - h + 540) % 360) - 180
    return (h + d * k + 360) % 360


_ramps: dict = {}


def ramp(color: str) -> list[tuple[int, int, int]]:
    """Six tones of a color, from the outline to the highlight. Shadows turn a little towards
    violet and lights towards yellow, as pixel artists do; warm light colors (skin) turn less, so
    that a cheek in shadow does not go red."""
    key = (LOOK, color)
    if key not in _ramps:
        _ramps[key] = _ramp2(color) if has("ramp2") else _ramp3(color) if has("ramp3") else _ramp1(color)
    return _ramps[key]


def _ramp1(color: str) -> list[tuple[int, int, int]]:
    """Classic's six tones."""
    r, g, b = (v / 255 for v in _rgb(color))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    h, s, l = hh * 360, ss, ll
    warm = 8 < h < 62
    out = []
    for d, k in ((-.47, .34), (-.31, .26), (-.16, .14), (0, 0), (.12, -.1), (.24, -.2)):
        hue = _toward(h, 262, k * .28 if warm else k) if k >= 0 else _toward(h, 52, -k)
        sat = s * (1 - (1.5 if warm and l > .45 else .35) * -d if d < 0 else 1.06)
        lit = max(.07, min(.97, l + d * (1.05 if l > .6 else .95)))
        # as a browser reads hsl(): the hue to a degree, the rest to a percent
        hue, sat, lit = round(hue), round(max(0, min(1, sat)) * 100) / 100, round(max(0, min(1, lit)) * 100) / 100
        rr, gg, bb = colorsys.hls_to_rgb(hue / 360, lit, sat)
        out.append((round(rr * 255), round(gg * 255), round(bb * 255)))
    return out


# LOOK 2's ramps are built in OKLCH, where equal steps of lightness look about equal, so a pale
# color keeps four lights apart and a dark one four shadows.

def _lin(v: float) -> float:
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def _gam(v: float) -> float:
    return v * 12.92 if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055


def oklch(color) -> tuple[float, float, float]:
    r, g, b = (_lin(v / 255) for v in _rgb(color))
    l_ = (.4122214708 * r + .5363325363 * g + .0514459929 * b) ** (1 / 3)
    m_ = (.2119034982 * r + .6806995451 * g + .1073969566 * b) ** (1 / 3)
    s_ = (.0883024619 * r + .2817188376 * g + .6299787005 * b) ** (1 / 3)
    L = .2104542553 * l_ + .7936177850 * m_ - .0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + .4505937099 * s_
    bb = .0259040371 * l_ + .7827717662 * m_ - .8086757660 * s_
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def _oklch_lin(L: float, C: float, h: float) -> tuple[float, float, float]:
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_, m_, s_ = L + .3963377774 * a + .2158037573 * b, L - .1055613458 * a - .0638541728 * b, L - .0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s,
            -.0041960863 * l - .7034186147 * m + 1.7076147010 * s)


def from_oklch(L: float, C: float, h: float) -> tuple[int, int, int]:
    """The color, its chroma lowered until it fits in sRGB (its lightness and hue kept)."""
    lo, hi = 0.0, C
    if any(not -1e-4 <= v <= 1.0001 for v in _oklch_lin(L, C, h)):
        for _ in range(24):
            mid = (lo + hi) / 2
            if all(-1e-4 <= v <= 1.0001 for v in _oklch_lin(L, mid, h)):
                lo = mid
            else:
                hi = mid
        C = lo
    return tuple(round(_clamp(_gam(_clamp(v)), 0, 1) * 255) for v in _oklch_lin(L, C, h))


def luminance(color) -> float:
    r, g, b = (_lin(v / 255) for v in _rgb(color))
    return .2126 * r + .7152 * g + .0722 * b


GLASS = (0x1e, 0x1f, 0x2b)  # the overlay's dark glass, which the figures stand on


def _ramp2(color: str) -> list[tuple[int, int, int]]:
    """LOOK 2: the outline light enough to show on the dark glass (about 1.6:1 against it), yet
    darker than every other tone; shadows at about 0.7 of the color's chroma, turning towards
    violet (skin less, so it stays brown); lights turning towards yellow and kept under white;
    the color itself in the middle, a pale one a little lower so its lights stay apart."""
    Lc, Cc, h = oklch(color)
    warm = 25 < h < 100 and Cc < .13  # skin, sand, wood: warm and soft, their shadows brown, not red
    # Shadows turn towards violet, at most 30 degrees; a yellow's turn towards orange instead
    # (through green it would go olive and sickly).
    cool = 30 if 75 < h < 125 else 285
    L3 = Lc if Lc <= .86 else .86 + (Lc - .86) * .3
    d = _clamp((.955 - L3) * .42, .042, .095)
    L0 = max(L3 * .5, min(.385, L3 - .2))
    out = []
    for i, (L, c, k) in enumerate(((L0, 1.15, .3), (L3 - (L3 - L0) * .7, 1.25, .22), (L3 - (L3 - L0) * .4, 1.15, .12),
                                   (L3, 1, 0), (L3 + d, .86, -.12), (L3 + 2 * d, .62, -.24))):
        if i == 3 and L3 == Lc:
            out.append(_rgb(color))
            continue
        # a pale color's shadows a little richer than it, a strong color's at about 0.7 of it
        cc = min(Cc * (c if not warm else (.75, .8, .9)[i]), (.09, .12, .14)[i]) if i < 3 else Cc * c
        turn = ((((cool if k >= 0 else 95) - h) + 540) % 360) - 180
        turn = _clamp(turn * abs(k), -100 * abs(k), 100 * abs(k)) * (.25 if warm and k > 0 else 1)
        out.append(from_oklch(L, cc, (h + turn) % 360))
    return out


def _ramp3(color: str) -> list[tuple[int, int, int]]:
    """LOOK 3: Classic's tones, their volume and punch, with two changes. The outline, as Classic's
    where that shows on the glass, lifted elsewhere to about 1.6:1 against it, as far as the
    darkest shadow lets it (four dark session colors of the twenty, and dark clothes, stay near
    Classic's). And a pale color's shadows (lightness above .75) kept from going to full
    strength: a pale green's to lime, a pale blue's to royal blue."""
    out = _ramp1(color)
    hl = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(color)))[1]
    Cc = oklch(color)[1]
    tones = [list(oklch(t)) for t in out[:3]]
    moved = set()
    for i, t in enumerate(tones):
        if hl > .75 and t[1] > Cc * 1.35 + .02:
            t[1] = Cc * 1.35 + .02
            moved.add(i)
    # the outline: lifted to about 1.6:1 against the glass, but kept under the darkest shadow (a dark
    # color's stays about as dark as Classic's: lifting its shadows too flattened it, and an arm
    # ran into the body); as strong as the color, up to a dark's .12, in the shadow's hue
    L0 = min(.385, tones[1][0] - .04)
    if L0 > tones[0][0] + .02:
        tones[0] = [L0, min(Cc, .12, tones[1][1] + .04), tones[1][2]]
        moved.add(0)
    for i in moved:
        out[i] = from_oklch(*tones[i])
    return out


K, WH, GOLD, EM = _rgb("#1a1222"), _rgb("#fffdf2"), _rgb("#ffd23c"), _rgb("#e2596f")


def _round(x: float) -> int:  # as JavaScript rounds: halves up
    return math.floor(x + .5)


def _clamp(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def _ease(k: float) -> float:
    return 1 - (1 - _clamp(k)) ** 3


# ---- shapes: each a test for a pixel's middle, giving a rough surface direction, and its bounds --

def ELL(x, y, a, b):
    def f(p, q):
        u, v = (p - x) / a, (q - y) / b
        return (u, v) if u * u + v * v <= 1 else None
    return f, (x - a, y - b, x + a, y + b)


def RE(x, y, a, b, t):
    c, s = math.cos(t), math.sin(t)

    def f(p, q):
        X, Y = p - x, q - y
        u, v = (X * c + Y * s) / a, (-X * s + Y * c) / b
        return (u * c - v * s, u * s + v * c) if u * u + v * v <= 1 else None
    r = max(a, b)
    return f, (x - r, y - r, x + r, y + r)


def BOX(x, y, a, b):
    def f(p, q):
        return ((p - x) / a * .7, (q - y) / b * .7) if abs(p - x) <= a and abs(q - y) <= b else None
    return f, (x - a, y - b, x + a, y + b)


def DOME(x, y, a, b, cut):
    def f(p, q):
        u, v = (p - x) / a, (q - y) / b
        return (u, v) if u * u + v * v <= 1 and q < cut else None
    return f, (x - a, y - b, x + a, y + b)


def RING(x, y, a, b, w):
    def f(p, q):
        u, v, U, V2 = (p - x) / a, (q - y) / b, (p - x) / (a - w), (q - y) / (b - w)
        return (u * .8, v * .8) if u * u + v * v <= 1 and U * U + V2 * V2 > 1 else None
    return f, (x - a, y - b, x + a, y + b)


def LIMB(x0, y0, x1, y1, r, r2=None):
    r2 = r if r2 is None else r2
    dx, dy = x1 - x0, y1 - y0
    ll = dx * dx + dy * dy or 1

    def f(p, q):
        t = _clamp(((p - x0) * dx + (q - y0) * dy) / ll)
        X, Y, R = x0 + dx * t, y0 + dy * t, r + (r2 - r) * t
        u, v = (p - X) / R, (q - Y) / R
        return (u, v) if u * u + v * v <= 1 else None
    m = max(r, r2)
    return f, (min(x0, x1) - m, min(y0, y1) - m, max(x0, x1) + m, max(y0, y1) + m)


def POLY(P):
    mx = sum(a for a, _ in P) / len(P)
    my = sum(b for _, b in P) / len(P)
    w = max(abs(a - mx) for a, _ in P) or 1
    h = max(abs(b - my) for _, b in P) or 1

    def f(p, q):
        c, j = False, len(P) - 1
        for i in range(len(P)):
            if (P[i][1] > q) != (P[j][1] > q) and p < (P[j][0] - P[i][0]) * (q - P[i][1]) / (P[j][1] - P[i][1]) + P[i][0]:
                c = not c
            j = i
        return ((p - mx) / w * .7, (q - my) / h * .7) if c else None
    return f, (min(a for a, _ in P), min(b for _, b in P), max(a for a, _ in P), max(b for _, b in P))


def FLAME(x, y, a, b, ph, t):
    def f(p, q):
        v = (q - y) / b
        if abs(v) > 1:
            return None
        up = v < 0
        w = a * (1 + v) ** .8 if up else a * math.sqrt(1 - v * v)
        X = x + (math.sin(v * 3.4 + t * TAU + ph) * 1.7 * -v if up else 0)  # once a second: every row repeats
        return ((p - X) / (w or 1) * .8, v * .8) if abs(p - X) <= w else None
    return f, (x - a - 2, y - b, x + a + 2, y + b)


def SHAPE(f, box):
    return f, box


# ---- the painter ------------------------------------------------------------------------------

def _tone(u) -> int:
    nz = math.sqrt(max(0, 1 - u[0] * u[0] - u[1] * u[1]))
    if has("flat"):
        # A light from the top left, mostly flat across the part: its lit side and its shadow
        # side, with no dark ring round every edge (the review: "every part a lit ball").
        lit = -u[0] * .7 - u[1] * .6 + nz * .12
        return 5 if lit > .72 else 4 if lit > .4 else 3 if lit > -.15 else 2
    lit = -u[0] * .5 - u[1] * .66 + nz * .55
    return 5 if lit > .93 else 4 if lit > .62 else 3 if lit > .16 else 2 if lit > -.32 else 1


class Canvas:
    """One frame: parts in flat bands of tone, a contact shadow where a part lies on another, an
    outline in the darkest tone of the part it surrounds, then single pixels and soft glows."""

    def __init__(self, off: int = OFF):
        self.off = off  # how far down the cell the drawing sits
        self.g = [[None] * N for _ in range(N)]  # [ramp, tone, shaded]
        self.dots: list = []
        self.under: list = []
        # LOOK 2: how much taller than drawn everything is, about the line it stands on (a breath
        # while it speaks: the head rises a fraction of a pixel, the feet stay)
        self.tall = 1.0

    def _y(self, y: float) -> float:  # where a point drawn at y lands, as the figure breathes
        return y if self.tall == 1.0 else FLOOR + (y - FLOOR) * self.tall

    def part(self, shape, R, k=0, flat=None, cast=1):
        f, (x0, y0, x1, y1) = shape
        inn = []
        if self.tall != 1.0:
            y0, y1 = self._y(y0) - 1, self._y(y1) + 1
        for y in range(max(0, math.floor(y0) + self.off - 1), min(N, math.ceil(y1) + self.off + 2)):
            for x in range(max(0, math.floor(x0) - 1), min(N, math.ceil(x1) + 2)):
                q = y + .5 - self.off
                u = f(x + .5, q if self.tall == 1.0 else FLOOR + (q - FLOOR) / self.tall)
                if u:
                    inn.append((x, y, u))
        if cast:
            mine = {(x, y) for x, y, _ in inn}
            for x, y, _ in inn:
                for dx, dy in ((0, 1), (1, 1)):
                    X, Y = x + dx, y + dy
                    if X < N and Y < N and (X, Y) not in mine and self.g[Y][X]:
                        self.g[Y][X][2] = 1
        for x, y, u in inn:
            z = flat if flat is not None else _tone(u)
            self.g[y][x] = [R, int(_clamp(z + k, 1, 5)), 0]

    def dot(self, x, y, c, w=1, h=1, a=1.0):
        self.dots.append((_round(x), _round(self._y(y)) + self.off, _rgb(c), w, h, a))

    def glow(self, x, y, r, c, a):
        self.under.append((x, self._y(y) + self.off, r, _rgb(c), a))

    def pixels(self) -> bytearray:
        """The frame as RGBA, row by row."""
        px = [[0.0, 0.0, 0.0, 0.0] for _ in range(N * N)]

        def over(i, c, a):
            p = px[i]
            out = a + p[3] * (1 - a)
            if out <= 0:
                return
            for j in range(3):
                p[j] = (c[j] * a + p[j] * p[3] * (1 - a)) / out
            p[3] = out
        # how strong a glow is at d, from its middle (0) to its edge (1): LOOK 1 in three rings; LOOK 2
        # stepless, fading fast; LOOK 3 stepless, fading slower, about as strong as LOOK 1's rings
        if has("glow3"):
            def fall(d):
                return 1 - d * d
        elif has("glow"):
            def fall(d):
                return (1 - d * d) ** 2
        else:
            def fall(d):
                return 1 if d < .45 else .6 if d < .72 else .3
        for cx, cy, r, c, a in self.under:
            if has("glow"):  # stepless, and in a strong tone of its color, not a grey film
                L, C, h = oklch(c)
                c = from_oklch(_clamp(L, .6, .9 if has("glow3") else .82), max(C, .13), h)
            for Y in range(max(0, math.floor(cy - r)), min(N, math.ceil(cy + r) + 1)):
                for X in range(max(0, math.floor(cx - r)), min(N, math.ceil(cx + r) + 1)):
                    d = math.hypot(X + .5 - cx, Y + .5 - cy) / r
                    if d < 1:
                        over(Y * N + X, c, a * fall(d))
        selective = has("selective")
        for Y in range(N):
            for X in range(N):
                p = self.g[Y][X]
                if p:
                    over(Y * N + X, p[0][int(_clamp(p[1] - p[2], 1, 5))], 1)
                    continue
                for a, b in ((0, 1), (1, 0), (-1, 0), (0, -1)):
                    if 0 <= Y + b < N and 0 <= X + a < N and self.g[Y + b][X + a]:
                        # LOOK 2: a selective outline, a tone lighter on the lit top and left
                        lit = selective and (a, b) in ((0, 1), (1, 0))
                        over(Y * N + X, self.g[Y + b][X + a][0][1 if lit else 0], 1)
                        break
        for X, Y, c, w, h, a in self.dots:
            for y in range(max(0, Y), min(N, Y + h)):
                for x in range(max(0, X), min(N, X + w)):
                    over(y * N + x, c, a)
        out = bytearray(N * N * 4)
        for i, p in enumerate(px):
            out[i * 4:i * 4 + 4] = bytes((round(p[0]), round(p[1]), round(p[2]), round(p[3] * 255)))
        return out


# ---- what every figure shares: the level-up, the stars, the mark, the smoke, eyes and mouths ----

# How many seconds each moment's row lasts before it repeats; the others repeat each second
# (speaking's four rows, and needs you and done, whose start leads into a row of one second).
LOOP = {"idle": 4, "working": 2, "failed": 2, "listen": 2}


class Frame:
    """The moment being drawn: s (idle, working, speaking, needs, done, failed, listen), T the time
    in seconds, A the time since the moment began, V how loud the voice is (0 to 1).

    Anything that moves with time goes through `wave` or `cycle`, which round its period so that it
    goes round a whole number of times in the row: the rows repeat in the overlay, and a motion
    that does not fit them jumps where they start again."""

    def __init__(self, s: str, T: float, A: float, V: float, off: int = OFF):
        self.s, self.T, self.A, self.V = s, T, A, V
        self.L = LOOP.get(s, 1)
        # Needs you settles: the body's big motions (a swing, a wave, a hop) play in its first
        # five seconds, fading out in the last, then only the mark keeps bobbing.
        self.lively = _clamp(5 - A) if s == "needs" else 1.0
        self.c = Canvas(off)
        if has("breath") and s == "speaking":
            # a breath once a second, the head about half a pixel up and down, so that speaking
            # in silence is not a still picture after the breathing idle (the review)
            self.c.tall = 1 + .5 / 30 * self.wave(1)

    def beat(self, period: float, ph: float = 0.0) -> float:
        """LOOK 2: from 0 to 1 and back once in `period`, smoothly (a tap, a step, a chatter): drawn
        at 12 frames a second it has frames in between, where LOOK 1 jumped from one pose to the other."""
        return (1 - math.cos(TAU * self.cycle(period, ph))) / 2

    def turns(self, period: float) -> int:
        """How many times a motion of about this period goes round in the row: none (it holds
        still) when the row is far too short for it, so a slow drift does not race in a short row."""
        if period > 2 * self.L:
            return 0
        return max(1, round(self.L / period))

    def wave(self, period: float, ph: float = 0.0) -> float:
        """A sine that goes round about once in `period` seconds (exactly, a whole number of times a row)."""
        return math.sin(TAU * self.T * self.turns(period) / self.L + ph)

    def cycle(self, period: float, ph: float = 0.0) -> float:
        """From 0 up to 1 about once in `period` seconds, for things that rise and fade."""
        return (self.T * self.turns(period) / self.L + ph) % 1

    def common(self, color: str, top: int):
        R, c, A = ramp(color), self.c, self.A
        if self.s == "done":
            if A < 1.1 and has("sparks"):
                # sparks rising past it, bright single pixels with a short tail, in place of the
                # grey beams of LOOK 1 (the review: "translucent rectangles over the figure")
                for i in range(9):
                    k = _clamp(A / 1.1 * 1.2 - i * .02)
                    if k >= .9:
                        continue
                    y = FLOOR - 3 - ((k * 44 + i * 11) % 34)
                    x = 7 + ((i * 13) % 27)
                    # bright the whole way, white, then gold, then the color's own light: no grey;
                    # LOOK 3: a head of two pixels, so that a spark still shows at 35 px
                    head = 2 if has("sparks3") else 1
                    c.dot(x, y, WH if k < .35 else "#fff3a8" if k < .65 else GOLD, 1, head)
                    c.dot(x, y + head, GOLD if k < .65 else R[4], 1, 2 if k < .4 else 1)
            elif A < 1.1:
                k = A / 1.1
                H = _round(34 * (1 - (1 - k) ** 2))
                for i in range(4):
                    c.dot(12 + i * 4, FLOOR - H, R[4], 4, H, (1 - k) * (.18, .3, .3, .18)[i])
                for i in range(7):  # above the line it stands on
                    y = FLOOR - 2 - ((k * 46 + i * 9) % 36)
                    c.dot(10 + ((i * 11) % 21), y, WH if i % 2 else R[5], 1, 2, 1 - k)
            if A > .5:
                for i in range(4):
                    q = (math.floor(A * 6) + i) % 5  # 6 a second: an even two frames each
                    X, Y = ((4, 10), (35, 12), (6, 25), (34, 27))[i]
                    if A < 4 and q < 3:
                        if q == 1:
                            c.dot(X - 1, Y, GOLD, 3, 1)
                            c.dot(X, Y - 1, GOLD, 1, 3)
                        c.dot(X, Y, "#fff6b8")
        if self.s == "needs":
            b = _round(abs(math.sin(A * TAU / 2)) * 2)  # a hop a second, on after the first five
            y = top - b
            c.dot(34, y, "#3a2000", 4, 11)
            c.dot(33, y + 1, "#3a2000", 6, 9)
            c.dot(34, y + 1, GOLD, 4, 5)
            c.dot(35, y + 6, GOLD, 2, 1)
            c.dot(35, y + 8, GOLD, 2, 2)
            c.dot(34, y + 1, "#fff3a8", 1, 3)
        if self.s == "listen" and has("glyph"):
            # LOOK 2: sound coming in, where the "!" is when it needs you: three thin arcs ")",
            # the nearest always there, the others coming on in turn
            y, on = top + 1, self.cycle(1)
            c.dot(32, y + 5, "#8fd0ff", 1, 2)
            for k, pts in enumerate((((34, 3), (35, 4), (35, 5), (35, 6), (34, 7)),
                                     ((36, 1), (37, 2), (38, 3), (38, 4), (38, 5), (38, 6), (38, 7), (37, 8), (36, 9)))):
                a = (1 if on < .8 else .4) if k == 0 else (1 if .25 <= on < .8 else .4)
                for X, Y in pts:
                    c.dot(X, y + Y, "#8fd0ff", 1, 1, a)

    def smoke(self, x, y, rise=13):
        rise = min(rise, y + self.c.off - 1)  # it fades out below the cell's top
        for i in range(3):
            k = self.cycle(2, i / 3)
            self.c.dot(x + math.sin(k * 6 + i) * 2, y - k * rise, "#aab2c2", 2 if k < .5 else 1, 2 if k < .5 else 1, 1 - k)

    def ink(self, x, y):
        """LOOK 2: a line on the face that shows: near-black on a light face, a light tone of the
        face's own color on a dark one (a failed, greyed figure)."""
        X, Y = _round(x), _round(self.c._y(y)) + self.c.off
        p = self.c.g[Y][X] if 0 <= X < N and 0 <= Y < N else None
        if not p:
            return K
        tone = p[0][int(_clamp(p[1] - p[2], 1, 5))]
        return K if luminance(tone) > .16 else p[0][5]

    def eyes(self, xs, y, kind, h=3):
        if has("wide"):
            return self._eyes2(xs, y, kind, h)
        c = self.c
        for i, x in enumerate(xs):
            # once in the idle row's four seconds, away from its first frame (the list holds that
            # one still: shut eyes there look asleep); never while it talks, listens or works
            blink = kind == "open" and self.s == "idle" and 2 <= self.T % 4 < 2.15
            if kind == "x":
                for a, b in ((-1, 0), (1, 0), (0, 1), (-1, 2), (1, 2)):
                    c.dot(x + a, y + b, K)
            elif kind == "happy":
                c.dot(x - 1, y + 2, K)
                c.dot(x, y + 1, K, 2, 1)
                c.dot(x + 2, y + 2, K)
            elif kind == "shut" or blink:
                c.dot(x - (0 if i else 1), y + 2, K, 3, 1)
            else:
                H, Y = (h + 1, y - 1) if kind == "wide" else (h, y)
                c.dot(x, Y, K, 2, H)
                c.dot(x, Y, WH)

    def _eyes2(self, xs, y, kind, h=3):
        """LOOK 2's eyes: wide ones a pixel wider and taller than open (3 by 3 at least) with a
        catchlight, so needing you reads at 35 pixels; while it works, open eyes look down (a lid
        across their top, the shine low); x and shut in a tone that shows on the face."""
        c = self.c
        blink = kind == "open" and self.s == "idle" and 2 <= self.T % 4 < 2.15
        if kind in ("open", "wide") and self.s == "working" and has("down"):
            kind = "down"
        for i, x in enumerate(xs):
            out = -1 if (len(xs) > 1 and i == 0) or (len(xs) == 1 and x < 20) else 0  # which side grows
            if kind == "x":
                ink = self.ink(x, y + 1)
                for a, b in ((-1, 0), (1, 0), (0, 1), (-1, 2), (1, 2)):
                    c.dot(x + a, y + b, ink)
            elif kind == "happy":
                ink = self.ink(x, y + 2)
                c.dot(x - 1, y + 2, ink)
                c.dot(x, y + 1, ink, 2, 1)
                c.dot(x + 2, y + 2, ink)
            elif kind == "shut" or blink:
                c.dot(x - (0 if i else 1), y + 2, self.ink(x, y + 2), 3, 1)
            elif kind == "down":
                H = max(2, h - 1)
                c.dot(x + out, y + h - H - 1, self.ink(x, y), 3, 1)  # the lid
                c.dot(x, y + h - H, K, 2, H)
                c.dot(x + 1, y + h - 1, WH)
            elif kind == "wide":
                H = max(3, h + 1)
                c.dot(x + out, y - 1, K, 3, H)
                c.dot(x + out, y - 1, WH)
                if H > 3:
                    c.dot(x + out + 1, y, WH)  # a catchlight of two pixels, a diagonal
            else:
                c.dot(x, y, K, 2, h)
                c.dot(x, y, WH)

    def mouth(self, x, y, v):
        c = self.c
        if v < .08:
            c.dot(x - 1, y, K, 2, 1)
            return
        h = 4 if v > .62 else 3 if v > .36 else 2 if v > .18 else 1
        w = 4 if v > .36 else 3
        c.dot(x - w // 2, y, K, w, h)
        if h > 2:
            c.dot(x - 1, y + h - 1, EM, 2, 1)


# ---- the familiars: seven creatures, seven tempers ----------------------------------------------

def lantern(F: Frame, col: str):
    if has("lantern2"):
        return _lantern2(F, col)
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, W, H = ramp(col), ramp("#c9a45c"), ramp("#ffd27a")
    # it swings on its ring: slowly, or hard once a second while it starts needing you
    sw = math.sin(A * TAU) * 2.6 * F.lively if s == "needs" else F.wave(4) * .5
    f = .35 + .1 * F.wave(.5)
    if s == "speaking":
        f = .2 + V * .95
    if s == "listen":
        f = .25 + .05 * F.wave(1)
    if s == "done":
        f = .95 + .05 * F.wave(1, TAU / 4)  # it glows on, breathing a little
    if s == "working":
        f = .45 + .15 * F.wave(1)
    dead = s == "failed"
    tx, y = 20 + sw, (1 if dead else 0)
    if not dead:
        c.glow(tx, 24, 8 + f * 9, "#ffdf9a", .1 + f * .16)
    c.part(RING(20 + sw * .4, 9 + y, 4.6, 4.2, 1.2), W)
    c.part(LIMB(14, 37, 14, 36, 1.5), W)
    c.part(LIMB(26, 37, 26, 36, 1.5), W)
    c.part(ELL(tx, 24 + y, 9.2, 10), C, k=-2 if dead else -1)
    if not dead:
        c.part(FLAME(tx, 26.5, 2.6 + f * 2.4, 3.5 + f * 5.5, 0, T), H, k=1, cast=0)
        c.part(FLAME(tx, 28.5, 1.4 + f * 1.2, 2 + f * 2.6, 1, T), ramp("#fff2c2"), k=1, cast=0)
    c.part(POLY([(14 + sw * .7, 13.5 + y), (17 + sw * .6, 10.5 + y), (23 + sw * .6, 10.5 + y), (26 + sw * .7, 13.5 + y),
                 (28.5 + sw * .8, 16.5 + y), (11.5 + sw * .8, 16.5 + y)]), W)
    c.part(BOX(tx, 34 + y, 8.6, 1.6), W)
    ex = _round(tx)
    if dead:
        c.dot(ex - 5, 22, C[0], 3, 1)
        c.dot(ex + 3, 22, C[0], 3, 1)
        F.smoke(20, 8)
    elif s == "done":
        F.eyes([ex - 5, ex + 3], 20, "happy")
    elif s in ("listen", "working"):
        for x in (ex - 5, ex + 3):
            c.dot(x, 22, WH, 3, 1)
    else:
        for x in (ex - 5, ex + 4):
            c.dot(x, 19 if s == "needs" else 20, WH, 2, 5 if s == "needs" else 4)
    if s == "speaking" and V > .2:
        for i in range(5):
            a, r = (i + T) * TAU / 5, 13 + V * 4  # one place round a second: as it started
            c.dot(tx + math.cos(a) * r, 24 + math.sin(a) * r * .75, "#ffe6a0", 1, 1, .9)


def _lantern2(F: Frame, col: str):
    """LOOK 2's lantern: its white bar eyes, kept at the author's word, and the flame standing on the lantern's floor, growing up to just under the eyes, never over
    them, so the face stays while it speaks."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, W, H = ramp(col), ramp("#c9a45c"), ramp("#ffd27a")
    sw = math.sin(A * TAU) * 2.6 * F.lively if s == "needs" else F.wave(4) * .5
    f = .35 + .1 * F.wave(.5)
    if s == "speaking":
        f = .2 + V * .95
    if s == "listen":
        f = .25 + .05 * F.wave(1)
    if s == "done":
        f = .95 + .05 * F.wave(1, TAU / 4)
    if s == "working":
        f = .45 + .15 * F.wave(1)
    dead = s == "failed"
    tx, y = 20 + sw, (1 if dead else 0)
    if not dead:
        if has("glow3"):  # LOOK 3: about as strong outside the lantern as LOOK 1's glow, round the flame
            c.glow(tx, 25, 8 + f * 10, "#ffc861", .12 + f * .18)
        else:
            c.glow(tx, 27, 8 + f * 8, "#ffc861", .12 + f * .14)
    c.part(RING(20 + sw * .4, 9 + y, 4.6, 4.2, 1.2), W)
    c.part(LIMB(14, 37, 14, 36, 1.5), W)
    c.part(LIMB(26, 37, 26, 36, 1.5), W)
    c.part(ELL(tx, 24 + y, 9.2, 10), C, k=-1)
    if not dead:  # the flame's foot on the floor, its tip at most up to row 23, under the eyes
        b = 2.6 + f * 2.4
        c.part(FLAME(tx, 33.5 - b, 2.4 + f * 2.6, b, 0, T), H, k=1, cast=0)
        b2 = 1.5 + f * 1.5
        c.part(FLAME(tx, 33.5 - b2, 1.3 + f * 1.3, b2, 1, T), ramp("#fff2c2"), k=1, cast=0)
    c.part(POLY([(14 + sw * .7, 13.5 + y), (17 + sw * .6, 10.5 + y), (23 + sw * .6, 10.5 + y), (26 + sw * .7, 13.5 + y),
                 (28.5 + sw * .8, 16.5 + y), (11.5 + sw * .8, 16.5 + y)]), W)
    c.part(BOX(tx, 34 + y, 8.6, 1.6), W)
    ex = _round(tx)
    if dead:
        F.eyes([ex - 5, ex + 3], 19, "shut")
        F.smoke(20, 8)
    elif s == "done":
        F.eyes([ex - 5, ex + 3], 19, "happy")
    elif s in ("listen", "working"):  # white bars, as it always had (the author, 2026-11-26: "I actually like the white eyes only")
        for x in (ex - 5, ex + 3):
            c.dot(x, 22, WH, 3, 1)
    else:
        for x in (ex - 5, ex + 4):
            c.dot(x, 19 if s == "needs" else 20, WH, 2, 5 if s == "needs" else 4)
    if s == "speaking" and V > .2:
        for i in range(5):
            a, r = (i + T) * TAU / 5, 13 + V * 4
            c.dot(tx + math.cos(a) * r, 24 + math.sin(a) * r * .75, "#ffe6a0", 1, 1, .9)


def ember(F: Frame, col: str):
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C = ramp(col)
    dead = s == "failed"
    H = ramp("#6a6470" if dead else "#ffd55e")
    Q = ramp("#57505c") if dead else C
    h, la, ra = 1.0, 0.0, 0.0
    if s == "speaking":
        h, la, ra = .94 + V * .2, V * 4, V * 4
    if s == "needs":
        # it bounces in place, feet down: the flame stretches up once a second and the arm waves
        h, ra = 1.04 + abs(math.sin(A * TAU / 2)) * .14 * F.lively, 9 + F.wave(1) * 1.5 * F.lively
    if s == "working":
        if not has("beat"):
            k = math.floor(T * 6) % 4
            la, ra = (5, 0) if k < 2 else (0, 5)
        else:  # the arms pump in turn, with frames in between
            la, ra = 3 * F.beat(2 / 3), 3 * F.beat(2 / 3, .5)
    if s == "done":
        # no jump: the author, 2026-11-26, "when they're done, they're jumping"
        la = ra = 9
    if dead:
        h = .62
    if s == "idle":
        h = 1 + F.wave(2) * .03
    if not dead:
        c.glow(20, 27, 15, col, .16 + (V * .12 if s == "speaking" else 0))
    c.part(ELL(15, 36.4, 2.8, 1.8), Q, k=-1)
    c.part(ELL(25, 36.4, 2.8, 1.8), Q, k=-1)
    b = 14 * h
    y = 36 - b * .92
    by = -max(0.0, b - 14) * .6  # the shoulders ride up a little as it stretches
    c.part(FLAME(20, y, 9.6, b, 0, 0 if dead else T), Q)
    c.part(FLAME(20, y + 3.2, 6.4, b * .66, .8, 0 if dead else T), H, cast=0)
    c.part(LIMB(11.5, 29 + by, 8, 31 - la + by, 1.9, 1.7), Q)
    c.part(LIMB(28.5, 29 + by, 32, 31 - ra + by, 1.9, 1.7), Q)
    ey = _round(y + 1)
    if dead:
        F.eyes([15, 24], ey, "x")
        F.smoke(20, 20)
    else:
        F.eyes([14, 24], ey, "happy" if s == "done" else "wide" if s in ("needs", "listen") else "open", 4)
        F.mouth(20, ey + 6, V if s == "speaking" else .7 if s in ("needs", "done") else 0 if s == "listen" else .12)
        for i in range(5 if s == "speaking" and V > .08 else 6 if s == "done" else 2):
            k = F.cycle(1, i * .37)
            c.dot(13 + ((i * 7) % 15) + math.sin(k * 5 + i) * 2, 24 - k * 22, "#fff0a0" if k < .4 else C[4], 1, 1, 1 - k)


def sprout(F: Frame, col: str):
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, L = ramp(col), ramp("#8c8a4c" if s == "failed" else "#79c95f")
    a, sq, by, up, bl, wv = .32 + F.wave(4) * .06, 1.0, 0, 0, 0.0, 0.0
    if s == "speaking":
        a, sq = .15 + V * .75 + F.wave(.5) * .06 * V, 1 - V * .04  # the leaves flutter with the voice
    if s == "needs":
        a, up, wv = 1.25, 3, F.wave(1) * 1.5 * F.lively  # it hops on the spot, feet down, and waves
        if not has("beat"):
            by = -_round(abs(math.sin(A * TAU / 2)) * 2 * F.lively)
        else:  # off the ground by fractions of a pixel, and squashed a little where it lands
            hop = abs(math.sin(A * TAU / 2))
            by, sq = -hop * 2.2 * F.lively, 1 - .09 * max(0.0, 1 - hop * 3) * F.lively
    if s == "failed":
        a, sq = -.75 + F.wave(2) * .05, .9 + F.wave(2, 1) * .015  # a slow sigh
    if s == "done":
        bl, a = _ease((A - .3) / .5), .5 + F.wave(1) * .05  # in flower, the leaves breathing
    if s == "working":
        a = .3 + .25 * F.wave(.67) if not has("beat") else .3 + .14 * F.wave(.67)  # LOOK 2: a smaller flutter
    if s == "listen":
        a, up = .95 + F.wave(1) * .08, 1
    y = 28.5 + by + (1 - sq) * 8
    c.part(ELL(15.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(24.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(20, y, 9.8, 8.8 * sq), C)
    sy = y - 8 * sq
    tx = 20 + (3 if s == "failed" else F.wave(4) * .6)
    c.part(LIMB(20, sy + 1, tx, sy - 4 - up, 1.1), L)
    c.part(RE(tx - 6.2 * math.cos(a), sy - 5 - up - 6 * math.sin(a), 6.4, 2.9, a), L)
    c.part(RE(tx + 6.2 * math.cos(a), sy - 5 - up - 6 * math.sin(a) - .5, 6.4, 2.9, -a), L)
    if bl > 0:
        P = ramp("#ffb3d1")
        for i in range(6):
            q = i * TAU / 6 + .3
            c.part(ELL(tx + math.cos(q) * 4 * bl, sy - 6 + math.sin(q) * 4 * bl, 2.6 * bl, 2.6 * bl), P)
        c.part(ELL(tx, sy - 6, 2.2 * bl, 2.2 * bl), ramp("#ffd95a"))
    tap = (3 if s == "working" and math.floor(T * 6) % 2 else 0) if not has("beat") else 3 * F.beat(2 / 3) if s == "working" else 0
    c.part(LIMB(11.5, 30 + by, 10, 33 + by - tap, 1.8), C, k=-1)
    c.part(LIMB(28.5, 30 + by, 30 + wv, 33 + by - (8 if s == "needs" else 9 if s == "listen" else 0), 1.8), C, k=-1)
    ey = _round(y - 3)
    if s == "failed":
        F.eyes([14, 23], ey, "shut")
    elif s == "done":
        F.eyes([14, 23], ey, "happy")
    elif s == "needs":
        F.eyes([14, 24], ey, "wide")
    elif s == "working" and has("down"):
        F.eyes([14, 24], ey, "down")
    else:
        for x in (14, 23):
            c.dot(x, ey + 1, K, 3, 2)
            c.dot(x, ey + 1, C[2], 3, 1)
            c.dot(x, ey + 2, WH)
    F.mouth(20, ey + 6, V if s == "speaking" else .4 if s == "needs" else .5 if s == "done" else 0)
    if s == "failed":
        c.dot(17, ey + 6, K)
        c.dot(18, ey + 5, K, 3, 1)
        c.dot(21, ey + 6, K)
    if s == "idle":  # z z: each rises and fades in two seconds
        for i in range(2):
            k = F.cycle(2, i * .5)
            c.dot(29 + k * 4, 20 - k * 9, "#dfe7f5", 3 if i else 2, 1, min(1, k * 5, (1 - k) * 1.6))


def shellback(F: Frame, col: str):
    """Shy, on all fours, seen from the front and a little above: a big domed shell in the session's
    color, its plates parted by dark seams, a light rim; a round face pokes out under it. It pulls
    everything in when its session fails. (Redrawn 2026-11-26; the author: "I feel like the turtle
    is the one that I like the least", then "Revamp it".)"""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, D, Rm = ramp(col), ramp(tint(col, -.3)), ramp(tint(col, .3))
    # the face, and the legs a tone darker: green, or tan on a green shell, where green would merge
    # with it (a session hue within about 40 degrees of green)
    skin, legs = SHELL_SKIN[_greenish(col)]
    W, Wa = ramp(skin), ramp(legs)
    hy, tilt, eye, mouth, lift, wave_, wig, hide = 0.0, 0.0, "open", 0.0, (0, 0), None, 0.0, 0
    sy = 0.0  # the shell's breath: its top a little up or down
    if s == "idle":
        hy, sy = F.wave(4) * .45, F.wave(4, 1) * .4
    if s == "working":  # nibbling, or reading: the head bobs down, the front feet tap in turn
        k = math.floor(T * 6) % 2
        hy, lift = .4 + k, (1, 0) if k else (0, 1)
        if has("beat"):  # with frames in between
            hy, lift = .4 + F.beat(2 / 3), (F.beat(2 / 3), F.beat(2 / 3, .5))
    if s == "speaking":  # it nods with the voice
        hy, mouth = -V * 1.2 + F.wave(.5) * .7 * V, V
    if s == "needs":  # the head stretches up and out on its neck, a front foot waves
        hy, eye, mouth = -6 + math.sin(A * TAU) * .8 * F.lively, "wide", .4
        wave_ = F.wave(1, 1) * 1.4 * F.lively
    if s == "done":  # head up, happy, a little shell wiggle
        hy, eye, mouth, wig = -2 + F.wave(1, 1) * .4, "happy", .5, F.wave(1) * .6
    if s == "failed":  # all the way in, the whole row (it repeats: no coming out again)
        hide = 1
    if s == "listen":  # the head raised and tilted, attentive
        hy, tilt, eye = -2.5 + F.wave(1) * .4, .16 + F.wave(1, 1) * .05, "wide"
    sx, top = 20 + wig, 27 + hide * 6  # the shell's middle, and the line of its rim
    # the back legs, behind the shell at its sides, a little higher than the front ones
    if not hide:
        for x in (6, 34):
            c.part(ELL(x, 32.6, 2.6, 2.1), Wa, k=-1)
    # the rim: a light band under the dome, thick at the front and thin at the sides
    c.part(ELL(sx, top + 1, 15.6, 4), Rm, flat=3)
    for x in (-12.5, -7, 7, 12.5):  # the rim's own little plates
        c.part(BOX(sx + x, top + 2.5, .4, 1.4 if abs(x) < 10 else .6), Rm, flat=1, cast=0)
    # the dome, dark, then its plates over it: the gaps between them are the seams
    a, b = 15.2, 16.5 - sy
    c.part(DOME(sx, top + 1, a, b, top + 1.5), D, flat=1)
    seeds = [(0, -9.5), (-10.5, -6.5), (10.5, -6.5), (-6.5, -.5), (6.5, -.5), (0, -19)]

    def plates(p, q):
        u, v = (p - sx) / a, (q - top - 1) / b
        if u * u + v * v > .9 or q > top + 1:
            return None
        X, Y = p - sx, q - top - 1
        d = sorted(math.hypot(X - x, (Y - y) * 1.15) for x, y in seeds)
        if d[1] - d[0] < 1.5:
            return None
        return (u * .8, (v + .5) * .75)
    c.part(SHAPE(plates, (sx - a, top + 1 - b, sx + a, top + 1)), C, cast=0)
    if hide:  # dark openings where the head and the legs went in, eyes peeking out of the front one
        Hd = ramp(tint(col, -.75))
        c.part(ELL(20, top + 3, 5.6, 2.3), Hd, flat=2, cast=0)
        for x in (9, 31):
            c.part(ELL(x, top + 3.3, 2.6, 1.5), Hd, flat=2, cast=0)
        if math.floor(T * 2) % 4 != 3:  # it blinks once in the row
            for x in (17, 22):
                c.dot(x, top + 2.5, WH, 2, 2)
            c.dot(18, top + 3.5, K)
            c.dot(22, top + 3.5, K)
        else:
            c.dot(17, top + 3.5, Hd[3], 2, 1)
            c.dot(22, top + 3.5, Hd[3], 2, 1)
        F.smoke(sx, top + 1 - b - 2)
        return
    # the front legs, stubby, on the line it stands on; the right one waves while it needs you
    Ln = ramp(tint(legs, -.62))  # a dark line round the legs and the face, where they lie on the shell
    if has("selective"):  # LOOK 2: the line in the legs' own outline tone, as the engine draws round them, not a near-black
        Ln = Wa
    for i, x in enumerate((10, 30)):
        sd = -1 if i == 0 else 1
        if i == 1 and wave_ is not None:
            fx, fy = 33.5 + wave_ * .6, 25 - wave_
            c.part(LIMB(29, 31, fx, fy, 3.2, 2.9), Ln, flat=1, cast=0)
            c.part(LIMB(29, 31, fx, fy, 2.3, 2), Wa)
            c.part(ELL(fx + .2, fy - .5, 2.3, 2.1), Wa)
            continue
        up = lift[i]
        c.part(LIMB(x - sd * .3, 31.5, x + sd * .3, 35 - up, 3.4), Ln, flat=1, cast=0)
        c.part(LIMB(x - sd * .3, 31.5, x + sd * .3, 35 - up, 2.5), Wa)
        c.part(ELL(x + sd * .6, 36.6 - up, 3.3, 1.7), Wa, k=-1)
    # the head: a neck when it stretches, then the round face (its middle on whole pixels)
    hc = _round(30 + hy)
    if hc < 28:
        c.part(LIMB(20, 33, 20, hc + 3, 3.1), Ln, flat=1, cast=0)
        c.part(LIMB(20, 33, 20, hc + 3, 2.2), Wa, k=-1)
    c.part(RE(20, hc, 8.3, 7.1, tilt) if tilt else ELL(20, hc, 8.3, 7.1), Ln, flat=1, cast=0)
    c.part(RE(20, hc, 7.4, 6.2, tilt) if tilt else ELL(20, hc, 7.4, 6.2), W)
    E = hc - 2
    dy = 1 if tilt else 0  # tilted: the far eye a pixel higher
    if eye == "happy":
        F.eyes([16, 22], E - 1, "happy")
    else:
        look = 1 if s == "working" else 0  # eyes down at what it reads
        F.eyes([16], E + look, eye, 3)
        F.eyes([22], E + look - dy, eye, 3)
    c.dot(14, E + 3, ramp("#ff9aa8")[3], 2, 1, .75)
    c.dot(24, E + 3 - dy, ramp("#ff9aa8")[3], 2, 1, .75)
    if mouth > .08:
        F.mouth(20, E + 4, mouth)
    else:  # a small shy smile
        c.dot(18, E + 4, K)
        c.dot(19, E + 5, K, 2, 1)
        c.dot(21, E + 4, K)


# The shellback's face and legs: green, or tan on a green shell (2026-11-26, a review: on the
# green session colors its face merged with the shell).
SHELL_SKIN = {False: ("#a9c47f", "#7f9f57"), True: ("#c9a67a", "#9a7a54")}


def _greenish(color: str) -> bool:
    """A color whose hue is within about 40 degrees of green (120), and not a grey."""
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(color)))
    return s > .15 and abs((h * 360 - 120 + 180) % 360 - 180) <= 40


def toadstool(F: Frame, col: str):
    """Grumpy, in one piece: a stout stem that flares up into the cap's gills, the face on the stem.
    (Redrawn 2026-11-26; the author: "the mushroom person, like the head seems very detached from
    the body".) A frown and brows while it idles and works."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, W, G, Ar = ramp(col), ramp("#ead9b6"), ramp("#b89470"), ramp("#cfae80")
    cy, ct, ra, la, br, lean, look = 0.0, 0.0, 0.0, 0.0, 1, 0.0, 0
    lh = None  # where the left hand is cupped, while it listens
    if s == "speaking":  # the cap bounces with the voice, up to three pixels
        cy = -V * 3 + F.wave(.5) * .4 * V
    if s == "needs":  # it waves high, the cap tipped towards the mark
        cy, ct, ra, br = -1 + math.sin(A * TAU) * .7 * F.lively, 3, 9 + F.wave(1, 1) * 1.5 * F.lively, 0
    if s == "done":
        ra, la, br, cy = 9 + F.wave(1) * .7, 9 - F.wave(1) * .7, -1, -.5 + F.wave(1, 1) * .4
    if s == "failed":
        cy, ct, lean = 3 + F.wave(2) * .3, -2, -1
    if s == "working":
        k = math.floor(T * 6) % 2
        ra, la = (3, 0) if k else (0, 3)
        if has("beat"):  # in turn, with frames in between
            ra, la = 3 * F.beat(2 / 3), 3 * F.beat(2 / 3, .5)
    if s == "listen":  # a hand cupped to the side of its face, the cap tipped to that side, eyes to it
        cy, ct, br, look, lean = -.5 + F.wave(1) * .4, -3, 0, -1, -.6
        lh = (11 + F.wave(1, 1) * .4, 24.5)
    if s == "idle":
        cy = F.wave(4) * .4
    c.part(ELL(15.5, 36.8, 2.8, 1.6), W, k=-1)
    c.part(ELL(24.5, 36.8, 2.8, 1.6), W, k=-1)
    X, y = 20 + ct * .4 + lean, 19.5 + cy

    # the stem: wide at the foot, narrowing up, then flaring out into the gills under the cap
    def stem(p, q):
        if not y < q < 37:
            return None
        mid = 20 + (X - 20) * (34 - q) / 14
        d = q - y
        w = 5.2 + d * .17 + 2.4 * max(0, 1 - d / 5) ** 2
        return ((p - mid) / 8, (q - 30) / 8) if abs(p - mid) <= w else None
    c.part(SHAPE(stem, (8, y, 32, 37)), W)
    # arms a tone apart from the stem
    if lh:
        c.part(LIMB(26.5, 29, 29, 33, 1.8), Ar)
        c.part(LIMB(13.5, 29, lh[0] + .5, lh[1] + 1, 1.8), Ar)
        c.part(ELL(lh[0], lh[1] - .5, 2.4, 2.8), Ar)  # the hand cupped behind where an ear would be
        hx, hy2 = _round(lh[0]), _round(lh[1] - .5)
        c.dot(hx + 1, hy2 - 1, Ar[1], 1, 3)  # the hollow of the hand, open to the side
        for j in range(2):  # sound coming in, arc by arc
            k = F.cycle(1, j / 2)
            r = 2 + (1 - k) * 4
            for q in (-1, 0, 1):
                c.dot(hx - 2 - r + abs(q) * .8, hy2 + q * 1.6, "#7fd4f5", 1, 1, min(1, (1 - k) * 2) * .9)
    else:
        c.part(LIMB(13.5, 29, 10.5 - la * .2, 33 - la, 1.8), Ar)
        c.part(LIMB(26.5, 29, 29.5 + (.5 if ra > 5 else 0), 33 - ra, 1.8), Ar)
    # the gills: an underside a little wider than the stem, with darker lines from the rim to the stem
    c.part(ELL(X, y + 1.3, 9.6, 3.3), G, flat=2)
    for sd in (-1, 1):
        for x0, x1 in ((7.6, 5.6), (3.4, 2.6)):
            for k in range(3):
                c.dot(X + sd * (x0 + (x1 - x0) * k / 2), y + 1.6 + k, G[0])

    def cap(p, q):
        # tipped, its rim rises on one side and sinks on the other, never below the gills
        u, v, cut = (p - X) / 13.5, (q - y) / 12, y + 1 + _clamp(ct * (p - X) * .05, -2, .5)
        return (u, v) if u * u + v * v <= 1 and q < cut else None
    c.part(SHAPE(cap, (X - 14, y - 12, X + 14, y + 3)), C)
    for a, b, w, h in ((-6.5, -5.5, 2.5, 2.2), (1, -8.5, 3, 2.4), (7.5, -4, 2.3, 2), (-1, -2.5, 1.7, 1.3), (-10.5, -1.5, 1.3, 1.1)):
        c.part(ELL(X + a, y + b, w, h), ramp("#fff3df"), cast=0)
    ey = 26 - (1 if s in ("needs", "done") else 0) + (1 if s == "failed" else 0)
    ex = _round(20 + (X - 20) * .5)
    if s == "failed":
        F.eyes([ex - 4, ex + 3], ey, "shut")
        c.dot(ex - 2, ey + 6, K)
        c.dot(ex - 1, ey + 5, K, 4, 1)
        c.dot(ex + 3, ey + 6, K)
        F.smoke(X, y - 10)
    else:
        if s == "done":
            F.eyes([ex - 4, ex + 3], ey, "happy")
        else:
            F.eyes([ex - 4 + look, ex + 2 + look], ey, "wide" if s == "needs" else "open", 2)
            if br > 0:  # brows down at the middle: grumpy
                c.dot(ex - 5, ey - 1, K, 2, 1)
                c.dot(ex - 3, ey, K)
                c.dot(ex + 3, ey - 1, K, 2, 1)
                c.dot(ex + 2, ey, K)
        if s == "listen":  # a small, curious mouth
            c.dot(ex - 1, ey + 5, K, 2, 1)
        else:
            F.mouth(ex, ey + 5, V if s == "speaking" else .4 if s == "needs" else .5 if s == "done" else 0)
            if s in ("idle", "working"):  # the corners of its frown, as it always had (the review: it lost them)
                c.dot(ex - 2, ey + 6, K)
                c.dot(ex + 1, ey + 6, K)


def axolotl(F: Frame, col: str):
    """Sweet: frilly gills that flutter with the voice, a wide smile, cheeks that blush."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, B, Gl = ramp(col), ramp(tint(col, .3)), ramp(tint(col, -.2))
    spread, droop, eye, blush, tl, hy = .3, 0.0, "open", .45, 0.0, 0.0
    L, R = (11.5, 32), (28.5, 32)  # where the hands are
    if s == "idle":
        spread = .3 + F.wave(2) * .06
    if s == "speaking":
        spread, hy = .2 + V * .8 + F.wave(1 / 3) * .05 * V, -V * 1.2
    if s == "needs":  # it waves one hand high and out to the side, the gills up
        spread, eye, hy = .9 + F.wave(.5) * .06 * F.lively, "wide", -.5
        R = (35 + F.wave(1) * 1.2 * F.lively, 22.5 - F.wave(1, 1) * 1.2 * F.lively)  # up high and out, clear of the cheek
    if s == "working":
        k = math.floor(T * 6) % 2
        spread = .35 + k * .1
        L, R = ((11.5, 29), (28.5, 32)) if k else ((11.5, 32), (28.5, 29))
        if has("beat"):  # in turn, with frames in between
            spread, L, R = .4, (11.5, 32 - 3 * F.beat(2 / 3)), (28.5, 32 - 3 * F.beat(2 / 3, .5))
    if s == "done":  # both hands up and out, cheeks pink, the gills fanning
        spread, eye, blush, hy = .85 + abs(F.wave(1)) * .1, "happy", 1, -.5
        L, R = (5.5 - F.wave(1) * .6, 24 - abs(F.wave(1)) * .8), (34.5 + F.wave(1) * .6, 24 - abs(F.wave(1)) * .8)
    if s == "failed":
        droop, eye, blush, hy = 1, "shut", 0, 1 + F.wave(2) * .3
    if s == "listen":  # the head tilted towards you, the gills perked up and quivering
        spread, eye, tl = 1.05 + F.wave(.5) * .05, "wide", .16
        R = (30, 29.5)

    def rot(x, y):  # the head tilts about the neck
        dx, dy = x - 20, y - 27
        return 20 + dx * math.cos(tl) - dy * math.sin(tl), 27 + dx * math.sin(tl) + dy * math.cos(tl)
    hx, hc = rot(20, 20 + hy)
    head = RE(hx, hc, 10, 7.2, tl)
    # tail behind, to one side
    c.part(LIMB(24, 33, 33, 30 + F.wave(3), 2.6, 1.2), C, k=-1)  # a slow swish; still while it talks
    c.part(ELL(15, 36.6, 2.8, 1.6), C, k=-1)
    c.part(ELL(25, 36.6, 2.8, 1.6), C, k=-1)
    c.part(ELL(20, 31.5, 7, 5.5), C)
    c.part(ELL(20, 32.5, 4, 3.6), B, flat=3, cast=0)  # the belly, flat and a little lighter
    # gills: three fronds each side, fanning up with `spread`, hanging when it fails: a thin spine
    # with single pixels of fringe on alternate sides, its tip the lightest
    fringe = []
    for sd in (-1, 1):
        for i, base in enumerate((-.55, 0, .55)):
            a = base * (.6 + spread * .7) + (.9 if droop else -.25 * spread) - sd * tl
            x0, y0 = rot(20 + sd * 8.5, 18.5 + i * 2 - 2 + hy)
            ln = 5 + spread * 1.5 - droop
            dx, dy = sd * math.cos(a), math.sin(a)
            c.part(LIMB(x0, y0, x0 + dx * ln, y0 + dy * ln, .95, .75), Gl)
            for j, t in enumerate((.5, .75)):
                side = (1 if j % 2 else -1) * (1 if i != 1 else -1)
                fringe.append((x0 + dx * ln * t - dy * side * 1.7, y0 + dy * ln * t + dx * side * 1.7, Gl[4]))
            fringe.append((x0 + dx * (ln + 1), y0 + dy * (ln + 1), Gl[5]))
    c.part(head, C)
    for x, y, tone in fringe:  # where the head does not cover them
        if not head[0](_round(x) + .5, _round(y) + .5):
            c.dot(x, y, tone)
    # arms in the body's color, a tone down: a raised one is an arm, not a white stick across the cheek
    for sx, (x, y) in ((14, L), (26, R)):
        c.part(LIMB(sx, 28.5, x, y, 1.6, 1.4), C, k=-1)
        if y < 27:  # a raised hand: a little paw at its end, in the belly's lighter tone
            c.part(ELL(x, y - .3, 1.9, 1.9), B)

    def at(x, y):
        X, Y = rot(x, y + hy)
        return _round(X), _round(Y)
    (e1x, e1y), (e2x, e2y) = at(13, 17), at(25, 17)
    if e1y == e2y:
        F.eyes([e1x, e2x], e1y, eye, 2)
    else:  # tilted: each eye at its own height
        F.eyes([e1x], e1y, eye, 2)
        F.eyes([e2x], e2y, eye, 2)
    for x in (11, 27):
        bx, by = at(x, 22)
        c.dot(bx, by, "#ff6f91", 2, 1, blush)
    mx, my = at(20, 22)
    if s == "failed":
        c.dot(mx - 3, my + 2, K)
        c.dot(mx - 2, my + 1, K, 4, 1)
        c.dot(mx + 2, my + 2, K)
        F.smoke(20, 12)
    elif s == "speaking" and V > .08 or s == "needs":
        F.mouth(mx, my, V if s == "speaking" else .4)
    else:
        c.dot(mx - 4, my, K)
        c.dot(mx - 3, my + 1, K, 6, 1)
        c.dot(mx + 3, my, K)


def dragon(F: Frame, col: str):
    """Proud: a whelp in the session's color, short horns curving back, a muzzle, bat wings that
    spread, a little fire. Idle, it holds its chin up, its eyes half shut and its chest out, and
    snorts a little smoke. (The author, 2026-11-26: "dragon not crazy, especially the wings".)"""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    dead = s == "failed"
    C = ramp(tint(col, -.25) if dead else col)
    # the wings' membrane a little darker than the body, so arms in front of them stand out; its
    # bones a tone darker again
    B, H, M = ramp(tint(tint(col, -.25) if dead else col, .45)), ramp("#f3e2b8"), ramp(tint(col, -.14))
    wing, la, ra, mouth, eye, hy, chin, puff = .25, 0, 0, 0.0, "open", 0.0, 0, 0.0
    if s == "idle":  # proud: chin up, eyes half shut, chest out
        wing, eye, chin, puff = .25 + F.wave(4) * .3, "smug", 1, 1.0
    if s == "speaking":
        mouth, wing = V, .25 + V * .45 + F.wave(.5) * .12 * V
    if s == "needs":  # quick little flaps, kept low on the right, clear of the mark
        wing, ra, mouth, eye = .32 + abs(F.wave(.5)) * .18 * F.lively, 10 + F.wave(1, 1) * 1.2 * F.lively, .5, "wide"
    if s == "working":
        k = math.floor(T * 6) % 2
        la, ra = (3, 0) if k else (0, 3)
        wing = .2 + k * .06
        if has("beat"):  # in turn, with frames in between
            la, ra, wing = 3 * F.beat(2 / 3), 3 * F.beat(2 / 3, .5), .23
    if s == "done":  # wings spread wide, flapping once a second
        wing, la, ra, mouth, eye = .85 + F.wave(1) * .14, 9, 9, .6, "happy"
    if dead:
        wing, eye, hy = -.35 + F.wave(2) * .04, "x", 1
    if s == "listen":
        wing, ra, eye = .5 + F.wave(1) * .06, 6, "wide"
    # wings behind: a bat's wing, an arm up to the wrist, two fingers down from it, membrane between
    for sd in (-1, 1):
        sx, w = 20 + sd * 5, wing
        wx, wy = sx + sd * (6 + w * 2), 15 - w * 6
        tips = [(wx + sd * (4 + w), wy + 4.5 - w * 2), (wx + sd * 2, wy + 12.5 - w * .75)]
        edge = ((tips[0][0] + tips[1][0]) / 2 - sd * 1.8, (tips[0][1] + tips[1][1]) / 2)  # curving in between the tips
        c.part(POLY([(sx, 23.5), (wx, wy), tips[0], edge, tips[1], (sx + sd * 3, 29), (sx, 29)]), M)
        c.part(LIMB(sx, 23.5, wx, wy, .65), M, flat=2, cast=0)
        for tip in tips:
            c.part(LIMB(wx, wy, tip[0] - sd * .4, tip[1] - .2, .5), M, flat=2, cast=0)
    # the tail, curling out to the right, a spade at its tip
    c.part(LIMB(25, 34, 31, 35, 2.4, 1.6), C, k=-1)
    c.part(LIMB(31, 35, 33.5, 31.5, 1.6, 1), C, k=-1)
    c.part(POLY([(32.5, 31.8), (35.5, 28.8), (35, 32.6)]), M, flat=3)
    c.part(ELL(15.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(24.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(20, 30.5 - puff * .5, 8 + puff * .4, 6.8 + puff * .5), C)  # the chest a pixel out when proud
    c.part(ELL(20, 32 - puff * .5, 4.8 + puff * .4, 4.6 + puff * .5), B, flat=3, cast=0)  # a flat, lighter belly
    # the head: short horns curving back to a point, a small crest, the skull, then the muzzle
    for sd in (-1, 1):
        c.part(POLY([(20 + sd * 3, 10.2 + hy), (20 + sd * 4.6, 7.4 + hy), (20 + sd * 6.6, 5.6 + hy), (20 + sd * 8.6, 5.2 + hy),
                     (20 + sd * 7, 7 + hy), (20 + sd * 6.4, 10.4 + hy)]), H)
    c.part(POLY([(18.6, 9.5 + hy), (20, 6.5 + hy), (21.4, 9.5 + hy)]), M, flat=3)
    c.part(ELL(20, 15 + hy, 8.4, 6.6), C)
    c.part(ELL(20, 20.3 + hy - chin, 4.6, 4), C)  # the muzzle, standing out below the skull
    c.part(LIMB(13, 27, 10.5 - la * .2, 31 - la, 1.8), C)
    c.part(LIMB(27, 27, 29.5 + (.5 if ra > 5 else 0), 31 - ra, 1.8), C)
    E = _round(13 + hy)
    if eye == "smug":  # half shut: a lid across the top of each eye, the pupil under it
        for i, x in enumerate((15, 23)):
            c.dot(x - (1 if i == 0 else 0), E + 1, K, 3, 1)
            c.dot(x, E + 2, K, 2, 1)
            c.dot(x + (1 if i == 0 else 0), E + 2, WH)
    else:
        F.eyes([15, 23], E, eye, 3)
    ny = E + 5 - chin
    for x in (18, 22):  # nostrils: small slits on top of the muzzle
        c.dot(x, ny, C[1])
    if dead:  # it sneezed: soot on its face, smoke out of both nostrils, drifting out past its cheeks
        c.dot(16, E + 6, "#3a3440", 3, 1, .8)
        c.dot(22, E + 7, "#3a3440", 3, 1, .8)
        c.dot(19, E + 8, C[0], 3, 1)
        for x in (18, 22):
            sd = 1 if x > 20 else -1
            for i in range(3):
                k = F.cycle(2, i / 3 + (.5 if sd > 0 else 0))
                r = 1 if k < .3 else 2
                c.dot(x + sd * (1 + k * 12) - (r - 1) / 2, ny - 1 - k * 6, "#d4dae4", r, r, min(1, k * 6) * (1 - k * .6))
        return
    my = E + 8 - chin
    if mouth > .08:
        F.mouth(20, my, mouth)
    else:
        c.dot(18, my, C[0], 4, 1)
    if s == "idle":  # a snort once in the row: two wisps out of the nostrils, down and out
        k = F.cycle(4)
        if .6 <= k < .8:
            q = (k - .6) / .2
            for x in (18, 22):
                c.dot(x + (1 if x > 20 else -1) * _round(1 + q * 3), ny + 1 + _round(q * 1.5), "#e4e8f0", 1, 1, 1 - q * .7)
    if s == "speaking" and V > .7:  # a puff of fire out of the side of its mouth
        k = F.cycle(.5)
        for j, (dx, dy, r) in enumerate(((5.5, -1, 2.3), (9.5, -4, 3.1), (13.5, -7.5, 3.6))):
            q = r * (.75 + .25 * math.sin((k + j / 3) * TAU))
            c.part(ELL(20 + dx + k, my + dy - k, q, q * .85), ramp("#f04a2a"), k=1, cast=0)
            c.part(ELL(20 + dx + k - .3, my + dy - k + .2, q * .6, q * .55), ramp("#ffd84a"), flat=4, cast=0)
    if s == "done" and A < 3:
        for i in range(5):
            k = (A * 1.6 + i / 5) % 1
            c.dot(20 + math.sin(i * 2.1 + k * 4) * (2 + k * 5), my - 1 - k * 14, "#fff0a0" if k < .3 else "#ffb347" if k < .65 else "#e2593c", 1, 1, 1 - k * .8)
    if s == "working":  # smoke rings while it thinks
        k = F.cycle(2)
        for dx, dy, w in ((0, -1, 2), (0, 1, 2), (-1, 0, 1), (2, 0, 1)):
            c.dot(28 + k * 5 + dx, 16 + hy - k * 10 + dy, "#c9cfdb", w, 1, 1 - k)  # rising beside the head


FAMILIARS = [lantern, ember, sprout, shellback, toadstool, axolotl, dragon]

# ---- the operators: one job, five people --------------------------------------------------------

LAG = .68 ** (8 / FPS)  # how much of the hair's lag behind the head is left after a frame
HAIR = ["#4a3f78", "#7a3e2a", "#3b4257", "#3a2a2a", "#a03a5e"]
SKIN = ["#f2c9a4", "#c58a5e", "#f5d6b6", "#8f5d3e", "#e7b48e"]


def operator(F: Frame, col: str, i: int, lag: list):
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, H, KS, B, P2 = ramp(col), ramp(HAIR[i]), ramp(SKIN[i]), ramp(tint(col, -.48)), ramp("#3a3f58")
    hx, hy, by, L1, R1, eye, m, slip = 0.0, 0.0, 0, (11, 33.5), (29, 33.5), "open", 0.0, 0
    if s == "idle":
        hy = F.wave(4) * .5
    if s == "speaking":
        m, hy = V, -_round(V * 1.4) + F.wave(.5) * .5 * V  # a nod with the voice, none in silence
        R1, L1 = (30 + V * 1.5, 30 - V * 5), (11, 33 - V * 2)
    if s == "working":
        k = math.floor(T * 6) % 4  # typing, two frames a key
        L1, R1, eye, hy = (14, 33 - (2 if k < 2 else 0)), (26, 33 - (0 if k < 2 else 2)), "down", 1
        if has("beat"):  # the hands in turn, with frames in between
            L1, R1 = (14, 33 - 2 * F.beat(2 / 3)), (26, 33 - 2 * F.beat(2 / 3, .5))
    if s == "needs":
        k = math.sin(A * TAU) * F.lively  # waving, once a second, then the hand held up
        R1, eye, m, hy = (32.5 + k * 2, 17), "wide", .45, (-1 if A < .3 else 0)
    if s == "done":
        # no jump: the author, 2026-11-26, "when they're done, they're jumping"
        L1, R1, eye, m = (7.5, 20 + F.wave(1) * .6), (32.5, 20 + F.wave(1) * .6), "happy", .5  # cheering, gently
    if s == "failed":
        hy, hx, eye, slip, L1, R1 = 2.5, -.5, "sad", 1, (12, 35), (28, 35)
    if s == "listen":
        R1, hx, eye = (30.5, 18.5), 1, "shut"
    cx, cy = 20 + hx, 16.5 + hy + by

    def Y(v):
        return v + by
    lag[0] = cy if lag[0] is None else lag[0] + (cy - lag[0]) * (1 - LAG)  # the hair lands a moment after the head
    if len(lag) > 1:  # only following the head, for row_frames: nothing to draw
        return
    hc = cy + round(_clamp(lag[0] - cy, -1.6, 1.6), 6)  # rounded: a rounding error must not move a pixel
    sw = F.wave(2.7, i) * .6 + ((V - .3) * 1.6 if s == "speaking" else 0) + (math.sin(A * TAU) * 1.4 * F.lively if s == "needs" else 0)
    head = (cx - 13, cy - 14, cx + 13, cy + 12)
    if i == 1:
        def bob(p, q):
            u, v = (p - cx) / 11.6, (q - hc - 1.5) / 11
            return (u, v) if u * u + v * v <= 1 and q < hc + 8.5 + (sw * .6 if p > cx else -sw * .6) else None
        c.part(SHAPE(bob, head), H, k=-1)
    if i == 3:
        for a in range(9):
            q = math.pi * (1.02 + a * .12)
            c.part(ELL(cx + math.cos(q) * 8.6, hc - 1 + math.sin(q) * 8.2, 3.9, 3.9), H)
    if i == 4:
        c.part(ELL(cx + 1, hc - 10.5, 3.6, 3.2), H)
        c.part(LIMB(cx + 3.5, hc - 11, cx + 6 + sw * .5, hc - 13.5, .9), ramp(tint(col, -.1)))
    c.part(LIMB(17, Y(34), 16.5, 36.8, 2.1), P2)
    c.part(LIMB(23, Y(34), 23.5, 36.8, 2.1), P2)
    c.part(ELL(20, Y(31), 7, 5.8), B)
    c.part(BOX((cx + 20) / 2, Y(25), 3, 2.6), KS, k=-1)
    c.part(ELL(cx, cy, 9.4, 8.7), KS)

    def hair(p, q):
        u, v = (p - cx) / 9.9, (q - cy) / 9.3
        if u * u + v * v > 1:
            return None
        X = p - cx
        fr = [-3.6 + (1.8 if math.floor(p) % 3 == 0 else 0), -1.4 - X * .1 if X < -1 else -4.2 + X * .12, -4.6,
              -4.4 + math.sin(p * 1.9) * .9, -1.6 + X * .12 if X > 1 else -4.4][i]
        side = abs(X) > 8.1 - (1.2 if i == 1 else 0)
        return (u * .75, v * .8) if q < hc + fr or (side and q < hc + [1, 9, 0, 1.5, 3][i] + (((sw if p > cx else -sw) * .5) if i == 1 else 0)) else None
    c.part(SHAPE(hair, head), H)
    if i == 0:
        for a in ((-6, -6.5, -8.5, -12.5, -2, -8.5), (-1.5, -8.5, .5, -13.5, 3, -8.2), (3.5, -8, 8, -11.5, 6.8, -5.5)):
            c.part(POLY([(cx + a[0], hc + a[1]), (cx + a[2] + sw * .4, hc + a[3]), (cx + a[4], hc + a[5])]), H, flat=3)
    if i == 2:
        c.part(DOME(cx, cy - 3, 9.9, 7.6, cy - 3.4), ramp(tint(col, -.3)))
        c.part(SHAPE(lambda p, q: ((p - cx) / 14, q - cy + 3.5) if cy - 4.6 < q < cy - 2.4 and cx - 13.5 < p < cx + 3 else None,
                     (cx - 14, cy - 5, cx + 3, cy - 2)), ramp(tint(col, -.1)), flat=3)
        c.part(ELL(cx, cy - 10, 1.2, 1), C, flat=4)

    def band(right=True):
        def f(p, q):
            u, v, a, b = (p - cx) / 11.3, (q - cy) / 11, (p - cx) / 9.8, (q - cy) / 9.5
            return (u * .8, v * .8) if u * u + v * v <= 1 and a * a + b * b > 1 and q < cy - 1.5 and (right or p < cx + 3) else None
        c.part(SHAPE(f, (cx - 12, cy - 12, cx + 12, cy)), C)

    def cup(sd, a, b, ring=False):
        x, y = cx + sd * 10.2, cy + 1.2 + (slip * 2.5 if sd < 0 else -slip)
        c.part(ELL(x, y, a, b), C)
        c.part(ELL(x + sd * .4, y, a * .45, b * .5), ramp("#2c2f40") if ring else B, cast=0)

    def ear(sd):
        c.part(ELL(cx + sd * 9.1, cy + 1.5, 1.6, 2.2), KS, k=-1)
    if i == 0:
        band()
        cup(-1, 2.6, 4)
        cup(1, 2.6, 4)
        for sd in (-1, 1):
            c.part(POLY([(cx + sd * 3.5, cy - 8.2), (cx + sd * 7.8, cy - 12.2 + (sw * .4 if sd > 0 else 0)), (cx + sd * 8.6, cy - 6)]), C, flat=3)
    if i == 1:
        band()
        cup(-1, 3.3, 4.8, True)
        cup(1, 3.3, 4.8, True)
    if i == 2:
        band(False)
        cup(-1, 2.6, 4)
        ear(1)
    if i == 3:
        ear(-1)
        ear(1)
        c.part(ELL(cx - 9.4, cy + 2.2, 1.3, 1.3), C, flat=4)
        c.part(ELL(cx + 9.4, cy + 2.2, 1.3, 1.3), C, flat=4)
    if i == 4:
        band()
        cup(-1, 2.6, 4)
        cup(1, 2.6, 4)
        c.part(LIMB(cx + 11, cy - 2, cx + 12.5 + sw * .6, cy - 9, .7), ramp("#9aa3b8"))
    fl = F.wave(2.1) * .7 + sw * .6
    if i == 0:
        c.part(ELL(20 + hx * .3, Y(26.2), 7.6, 2.4), ramp(tint(col, -.3)))
        for d in (-1.6, 1.6):
            c.part(LIMB(20 + d, Y(27.5), 20 + d * 1.15 + sw * .5, Y(31.5), .6), ramp("#eceaf2"), cast=0)
    if i == 1:
        c.part(BOX((cx + 20) / 2, Y(26.2), 3.2, 1.1), KS, k=-1)
    if i == 2:
        c.part(POLY([(14.4, Y(25.2)), (25.6, Y(25.2)), (20.4 + fl * 1.4, Y(30.6))]), ramp(tint(col, .42)))
    if i == 3:
        c.part(POLY([(16, Y(25.4)), (24, Y(25.4)), (20, Y(28.6))]), KS, k=-1)
    if i == 4:
        c.part(BOX(20 + hx * .4, Y(26.4), 6.2, 1.9), C)
        c.part(LIMB(15.5, Y(27.5), 13.8 + fl, Y(32.5), 1.7, 1.4), C)

    def arm(sx, ax, ay):
        ex = (sx + ax) / 2 + (-1.6 if sx < 20 else 1.6)
        ey = (Y(29) + ay) / 2 + (1.5 if ay < 24 else .6)
        c.part(LIMB(sx, Y(29), ex, ey, 2.2, 2), B)
        c.part(LIMB(ex, ey, ax, ay, 2, 1.8), B)
        c.part(ELL(ax, ay - .4, 2.1, 2.1), KS)
    arm(14.4, L1[0], L1[1] + by)
    arm(25.6, R1[0], R1[1] + by)
    X, E = _round(cx), _round(cy)
    xs = [X - 5, X + 3]
    if eye == "sad":
        for q, x2 in enumerate(xs):
            c.dot(x2, E + 1, K, 2, 2)
            c.dot(x2 + (1 if q else 0), E - 2, H[0])
            c.dot(x2 + (0 if q else 1), E - 2, H[0])
            c.dot(x2 + (-1 if q else 2), E - 3, H[0])
    elif eye == "down":  # open, looking down at the work: a heavy lid over the eye, its shine low
        for x2 in xs:
            c.dot(x2 - 1, E, K, 4, 1)
            c.dot(x2, E + 1, K, 2, 2)
            c.dot(x2 + 1, E + 2, WH)
    elif eye == "shut":
        for x2 in xs:
            c.dot(x2 - 1, E + 1, K, 3, 1)
    else:
        F.eyes(xs, E - 1, eye, 4)
    if eye in ("open", "wide", "down"):
        for q, x2 in enumerate(xs):
            c.dot(x2 - (0 if q else 1), E - (5 if eye == "wide" else 4), H[1], 3, 1)
    if i == 4 and eye != "happy":
        for x2 in xs:
            a, b = x2 - 1, E - 2
            for q, r, ww, hh in ((0, 0, 4, 1), (0, 5, 4, 1), (-1, 1, 1, 4), (4, 1, 1, 4)):
                c.dot(a + q, b + r, "#f4e3a0", ww, hh)
        c.dot(X - 2, E, "#f4e3a0", 3, 1)
    if i == 3:
        def beard(p, q):
            u, v = (p - cx) / 7.2, (q - cy - 4.2) / 4.8
            return (u * .7, v * .6) if u * u + v * v <= 1 and q > cy + 3.4 else None
        c.part(SHAPE(beard, (cx - 8, cy + 3, cx + 8, cy + 10)), H, cast=0)
    if i == 1:
        for a, b in ((-6, 3), (-4, 4), (4, 3), (6, 4)):
            c.dot(X + a, E + b, KS[2])
        pdx = _round(20 + F.wave(2.9) * 1.3 + sw * .4)
        c.dot(17, Y(28), GOLD)
        c.dot(23, Y(28), GOLD)
        c.dot(18, Y(29), GOLD, 5, 1, .8)
        c.dot(pdx, Y(30), GOLD, 1, 2)
        c.dot(pdx, Y(30), "#fff6c0")
    if i == 3:
        sx = _round(cx - 9.4)
        for k in range(7):
            c.dot(sx + _round(F.wave(3, k * .5) * (k / 7) * 1.6) + (1 if k > 3 else 0), _round(cy + 3.4 + k * 1.25), C[3])
    if i == 4:
        c.dot(_round(cx + 12.5 + sw * .6), _round(cy - 10), "#ff6a5e" if math.floor(T * 2) % 2 else "#ffd0c8")
    if i == 0 and s == "speaking" and V > .3:
        for a, b in ((-6, -10), (6, -10)):
            c.dot(X + a, E + b, C[5])
    if eye == "sad":
        c.dot(X - 2, E + 6, K)
        c.dot(X - 1, E + 5, K, 3, 1)
        c.dot(X + 2, E + 6, K)
    else:
        F.mouth(X, E + 5, m)
    c.dot(X, E + 3, KS[1])
    if i in (0, 2, 4):
        for a, b in ((-10, 5), (-10, 6), (-9, 7), (-8, 7), (-7, 7)):
            c.dot(X + a, E + b + slip * 2, "#1e2030")
        c.dot(X - 6, E + 6 + slip * 2, C[5 if s == "speaking" and V > .2 else 2], 2, 2)
    if i != 3:
        c.dot(X + (-11 if i == 2 else 11), E, "#7fe0ff" if s == "listen" else "#ff6a5e" if s == "failed" else C[5])
    if s == "speaking":
        for k in range(3):
            if V > .12 + k * .24:
                r = 3 + k * 2.2
                for q in range(-2, 3):
                    a = math.pi + q * .3
                    c.dot(X - 9 + math.cos(a) * r, E + 7 + math.sin(a) * r, C[4], 1, 1, 1 - k * .25)
    if s == "listen" and not has("glyph"):  # LOOKs 2 and 3 have the shared sound glyph instead
        for k in range(3):
            if F.cycle(2, k / 3) < .53:  # the rings go out one after another
                r = 3.5 + k * 2
                for q in range(-2, 3):
                    c.dot(cx + 13 + math.cos(q * .32) * r * .6, E + 1 + math.sin(q * .32) * r, "#7fd4f5", 1, 1, .95 - k * .25)
    if s == "failed":
        k = F.cycle(2)
        c.dot(X + 8, E - 5 + k * 7, "#9fd8ff", 1, 2, 1 - k * .6)
        c.dot(X + 9, E - 3 + k * 7, "#9fd8ff", 1, 1, 1 - k * .6)


# ---- the sheet ----------------------------------------------------------------------------------

def frame(style: str, kind: int, color: str, s: str, T: float, A: float, V: float, lag: list | None = None) -> bytearray:
    """One cell, as RGBA."""
    if style == "sketch":
        return sketch.frame(kind, color, s, T, A, V)
    # the operators are drawn one row higher, to stand on the same row as the familiars (42 of 44)
    F = Frame(s, T, A, V, OFF - 1 if style == "operators" else OFF)
    if style == "operators":
        operator(F, color, kind, lag if lag is not None else [None])
        if lag is not None and len(lag) > 1:
            return bytearray()
        F.common(color, 2)
    else:
        FAMILIARS[kind](F, color)
        F.common(color, 1)
    return F.c.pixels()


def _moment(name: str) -> tuple[str, float, float, float]:
    """What a row draws: the moment, the time its first frame is at, the time since the moment
    began at that frame, and the loudness."""
    if name.startswith("speaking"):
        return "speaking", 0.0, 0.0, LOUD[int(name[-1])]
    if name == "needs_hold":
        return "needs", 6.0, 6.0, 0.0
    if name == "done_hold":
        return "done", 5.0, 5.0, 0.0
    return name, 0.0, 0.0, 0.0


def row_frames(style: str, kind: int, color: str, name: str, extra: int = 0):
    """The cells of one row of the sheet, in order (`extra` more past its end, for checks)."""
    count = dict(ROWS)[name]
    s, t0, a0, v = _moment(name)
    lag: list = [None]
    if style == "operators":
        # The hair follows the head a moment late (each frame a part of the way). Run the row once
        # from 0: where that ends is what the lag owes to the row itself, and a start of that over
        # (1 - LAG ** count) ends where it began, so the row repeats exactly.
        lag = [0.0, "follow only"]
        for i in range(count):
            frame(style, kind, color, s, t0 + i / FPS, a0 + i / FPS, v, lag)
        lag = [lag[0] / (1 - LAG ** count)]
    for i in range(count + extra):
        yield frame(style, kind, color, s, t0 + i / FPS, a0 + i / FPS, v, lag)


def sheet(style: str, kind: int, color: str, look: int | None = None) -> bytes:
    """Every cell of one figure in one color, as a PNG; `look` draws it in that look (1 classic,
    2 refined, 3 the two mixed) instead of the module's `LOOK`. Sheets are drawn one at a time (`Sheets`)."""
    global LOOK
    if look is None:
        return _sheet(style, kind, color)
    was, LOOK = LOOK, look
    try:
        return _sheet(style, kind, color)
    finally:
        LOOK = was


def _sheet(style: str, kind: int, color: str) -> bytes:
    n = cell(style)
    width, height = max(count for _, count in ROWS) * n, len(ROWS) * n
    rgba = bytearray(width * height * 4)
    for row, (name, count) in enumerate(ROWS):
        for i, drawn in enumerate(row_frames(style, kind, color, name)):
            for y in range(n):
                start = ((row * n + y) * width + i * n) * 4
                rgba[start:start + n * 4] = drawn[y * n * 4:(y + 1) * n * 4]
    return png(width, height, rgba)


def png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(rgba[y * width * 4:(y + 1) * width * 4]) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


class Sheets:
    """Draws sheets in the background, one at a time, into `folder`, and says where each is.
    `windows` turns a path here into the path the overlay reads; `done` is called when a sheet
    is ready (the hub sends the overlay its rows again)."""

    def __init__(self, folder: str, windows: Callable[[str], str] = lambda path: path,
                 done: Callable[[], None] = lambda: None, log: Callable[[str], None] = lambda line: None):
        self.folder, self.windows, self.done, self.log = folder, windows, done, log
        self._lock = threading.Lock()
        self._wanted: list[tuple[str, int, str]] = []
        self._ready: dict[tuple[str, int, str], str] = {}
        self._busy = False

    def name(self, style: str, kind: int, color: str, look: int | None = None) -> str:
        look = LOOK if look is None else look
        return os.path.join(self.folder, f"{style}-{kind}-{color.lstrip('#').lower()}-{f'look{look}-' if look != 1 else ''}{_SOURCE}.png")

    def path(self, style: str, color: str, look: int | None = None, kind: int | None = None) -> str:
        """The overlay's path to this session's sheet, or "" while it is being drawn. `look`:
        1 classic, 2 refined, 3 the two mixed; `LOOK` when not given. `kind`: which figure (`pick`);
        the color's when not given."""
        if style not in STYLES or not color:
            return ""
        look = LOOK if look is None else look
        kind = kind_of(color, kinds(style)) if kind is None else kind % kinds(style)
        key = (style, kind, color, look if look in PARTS and style != "sketch" else 1)
        with self._lock:
            if key in self._ready:
                return self._ready[key]
            path = self.name(*key)
            if os.path.isfile(path):
                self._ready[key] = self.windows(path)
                return self._ready[key]
            if key not in self._wanted:
                self._wanted.append(key)
            if not self._busy:
                self._busy = True
                threading.Thread(target=self._draw, name="characters", daemon=True).start()
        return ""

    def _draw(self) -> None:
        while True:
            with self._lock:
                if not self._wanted:
                    self._busy = False
                    return
                key = self._wanted[0]
            path = self.name(*key)
            try:
                os.makedirs(self.folder, exist_ok=True)
                data = sheet(*key)
                with open(path + ".part", "wb") as f:
                    f.write(data)
                os.replace(path + ".part", path)
                ready = self.windows(path)
            except Exception as e:  # noqa: BLE001  a sheet that cannot be drawn leaves the bubble as it was
                self.log(f"character {key} not drawn: {e}")
                ready = ""
            with self._lock:
                self._wanted.remove(key)
                if ready:
                    self._ready[key] = ready
            if ready:
                self.done()
