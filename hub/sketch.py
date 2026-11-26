"""The Sketch character: one operator with a headset in rough pencil, the same for every session
but for the scarf and the headset, which are the session's color.

The author, 2026-11-26, of the Character setting: "a select would be better, because it's
missing the hand-drawn operators". Ported from the "Sketch" (`operator`) of
`docs/dev/looks/characters.html`, which drew it on a canvas 100 units wide; here the same lines
are drawn with smooth edges (the coverage of each pixel, not whole pixels), into a cell twice as
large as the pixel styles' so that the overlay shows it at its own size on the edge, never
doubled. The lines shake a little three times a second, as an animatic redrawn on each frame does.

Changes from the preview, so that rows repeat without a jump and nothing leaves its cell: the
head's sway while speaking and the arm while working go once a second (the rows are whole
seconds long), it does not jump when done, and when it fails it sinks 7 units, not 9, with its feet kept on the ground.
"""
from __future__ import annotations

import math

import numpy as np

CELL = 88  # pixels; twice the pixel styles' cell (characters.N), shown at this size on the edge
Z = 0.8  # pixels for each of the preview's units
TOP = 4.8  # where its unit 0 is: the feet (unit 99) end two of the pixel styles' rows above the bottom, as theirs do
SS = 4  # samples a side for each pixel of a filled shape
TAU = math.tau
PENCIL = (236, 228, 212)
HEAD = (43, 47, 58)
MOUTH = (14, 11, 16)


def _rgb(color: str) -> tuple[int, int, int]:
    h = color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rand(seed: float):
    """The preview's: a Park-Miller generator, so that the same frame shakes the same way."""
    s = math.floor(seed * 7919) % 2147483646 + 1

    def next_():
        nonlocal s
        s = s * 16807 % 2147483647
        return s / 2147483647
    return next_


class Paper:
    """One cell: RGB premultiplied by its alpha, painted over in turn."""

    def __init__(self):
        self.rgb = np.zeros((CELL, CELL, 3))
        self.a = np.zeros((CELL, CELL))

    def _over(self, x0, y0, cover, color, alpha):
        h, w = cover.shape
        k = cover * alpha
        self.rgb[y0:y0 + h, x0:x0 + w] = np.asarray(color, float) * k[..., None] + self.rgb[y0:y0 + h, x0:x0 + w] * (1 - k[..., None])
        self.a[y0:y0 + h, x0:x0 + w] = k + self.a[y0:y0 + h, x0:x0 + w] * (1 - k)

    @staticmethod
    def _box(xs, ys, pad):
        x0, x1 = max(0, math.floor(min(xs) - pad)), min(CELL, math.ceil(max(xs) + pad) + 1)
        y0, y1 = max(0, math.floor(min(ys) - pad)), min(CELL, math.ceil(max(ys) + pad) + 1)
        return x0, y0, x1, y1

    def stroke(self, pts, width, color, alpha=1.0):
        """A line through the points, with round ends and joins, `width` pixels wide."""
        r = width / 2
        x0, y0, x1, y1 = self._box([p[0] for p in pts], [p[1] for p in pts], r + 1)
        if x1 <= x0 or y1 <= y0:
            return
        X, Y = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        a = np.array(pts[:-1], float)[:, None, None, :] if len(pts) > 1 else np.array(pts, float)[:, None, None, :]
        b = np.array(pts[1:], float)[:, None, None, :] if len(pts) > 1 else a
        d = b - a
        px, py = X[None] - a[..., 0], Y[None] - a[..., 1]
        dd = d[..., 0] ** 2 + d[..., 1] ** 2
        t = np.clip((px * d[..., 0] + py * d[..., 1]) / np.where(dd > 0, dd, 1), 0, 1)
        dist = np.sqrt((px - t * d[..., 0]) ** 2 + (py - t * d[..., 1]) ** 2).min(axis=0)
        self._over(x0, y0, np.clip(r - dist + .5, 0, 1) * min(1, width), color, alpha)

    def fill(self, pts, color, alpha=1.0):
        """The inside of a closed outline (even-odd), its edges as smooth as SS by SS samples make them."""
        x0, y0, x1, y1 = self._box([p[0] for p in pts], [p[1] for p in pts], 1)
        if x1 <= x0 or y1 <= y0:
            return
        X, Y = np.meshgrid(x0 + (np.arange((x1 - x0) * SS) + .5) / SS, y0 + (np.arange((y1 - y0) * SS) + .5) / SS)
        inside = np.zeros(X.shape, bool)
        for (xi, yi), (xj, yj) in zip(pts, pts[-1:] + pts[:-1]):
            if yi == yj:
                continue
            crosses = (yi > Y) != (yj > Y)
            inside ^= crosses & (X < (xj - xi) * (Y - yi) / (yj - yi) + xi)
        cover = inside.reshape(y1 - y0, SS, x1 - x0, SS).mean(axis=(1, 3))
        self._over(x0, y0, cover, color, alpha)

    def pixels(self) -> bytearray:
        a = self.a
        rgb = np.where(a[..., None] > 0, self.rgb / np.where(a > 0, a, 1)[..., None], 0)
        out = np.dstack([np.clip(np.rint(rgb), 0, 255), np.clip(np.rint(a * 255), 0, 255)]).astype(np.uint8)
        return bytearray(out.tobytes())


def _ellipse(x, y, rx, ry, a=0.0, b=TAU, n=40):
    return [(x + math.cos(a + (b - a) * k / n) * rx, y + math.sin(a + (b - a) * k / n) * ry) for k in range(n + 1)]


def _round_rect(x, y, w, h, r):
    out = []
    for cx, cy, a in ((x + w - r, y + r, -TAU / 4), (x + w - r, y + h - r, 0), (x + r, y + h - r, TAU / 4), (x + r, y + r, TAU / 2)):
        out += [(cx + math.cos(a + TAU / 4 * k / 6) * r, cy + math.sin(a + TAU / 4 * k / 6) * r) for k in range(7)]
    return out


def _quad(p0, c, p1, n=12):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1])
            for t in (k / n for k in range(1, n + 1))]


def frame(kind: int, color: str, s: str, T: float, A: float, V: float) -> bytearray:
    """One cell, as RGBA: s the moment, T the time, A the time since the moment began, V how loud."""
    q = _rand(math.floor(T * 6 + 1e-9) % 3 + kind * 5 + 2)
    c = _rgb(color)
    paper = Paper()

    tilt, hx, hy, m, arm, lid, brow, dy = 0.0, 50.0, 42.0, 0.0, 0.0, 0, 0, 0.0
    if s == "speaking":
        m, tilt, arm = V, math.sin(T * TAU) * .06, V * .5
    if s == "needs":
        arm, brow, tilt, m = 1.5 + (math.sin(A * TAU) * .22 if A < 5 else 0), 1, -.1, .25
    if s == "done":
        arm, lid, m = 1.1, 2, .2  # no jump (the author, 2026-11-26: "when they're done, they're jumping")
    if s == "failed":
        tilt, dy, brow = .38, 7.0, -1
    if s == "working":
        hy, lid, arm = 45.0, 1, .3 + math.sin(T * TAU) * .12
    if s == "listen":
        tilt, arm, brow = .2, 2.0, 1

    cos, sin = math.cos(tilt), math.sin(tilt)

    def body(p, lift=True):  # the preview's units to this cell's pixels
        return (p[0] * Z, (p[1] + (dy if lift else 0)) * Z + TOP)

    def head(p):  # turned with the head, about its middle
        x, y = p[0] - hx, p[1] - hy
        return body((hx + x * cos - y * sin, hy + x * sin + y * cos))

    def line(pts, width=2.6, col=PENCIL, at=body):
        shaken = []
        for x, y in pts:
            X = x + (q() - .5) * 1.3
            shaken.append(at((X, y + (q() - .5) * 1.3)))
        paper.stroke(shaken, width * Z, col)

    def arc(cx, cy, rx, ry, a, b, width, col=PENCIL, at=body):
        line([(cx + math.cos(a + (b - a) * k / 18) * rx, cy + math.sin(a + (b - a) * k / 18) * ry) for k in range(19)], width, col, at)

    # The scarf, in the session's color, and its end hanging down.
    scarf = [(28, 66)] + _quad((28, 66), (50, 58), (74, 66)) + [(72, 76)] + _quad((72, 76), (50, 69), (30, 76))
    paper.fill([body(p) for p in scarf], c, .92)
    # its end stops above the feet's line when the body sinks (failed): nothing below where it stands
    paper.fill([body(p) for p in ((34, 72), (28, 95 - dy), (40, 96 - dy), (43, 74))], c, .92)
    # Legs: from the body, which jumps and sinks, to feet that stay on the ground unless it jumps.
    for top, foot in (((30, 74 + dy), (22, 99 + min(dy, 0))), ((70, 74 + dy), (78, 99 + min(dy, 0)))):
        line([top, foot], at=lambda p: body(p, lift=False))
    ax, ay = 70, 80
    line([(ax, ay), (ax + 16 + arm * 3, ay + 6 - arm * 16), (ax + 12 + (-8 if arm > 1.9 else arm * 4), ay - 8 - arm * 22)], 3.2)

    # The head, turned: its shape, hair, the headset in the session's color.
    paper.fill([head(p) for p in _ellipse(hx, hy, 24, 23)], HEAD)
    arc(hx, hy, 24, 23, .2, TAU + .35, 2.8, at=head)
    line([(38, 22), (34, 10), (44, 19), (49, 7), (54, 19), (64, 11), (61, 22)], 2.6, at=head)
    arc(hx, hy - 2, 28, 27, math.pi * 1.08, math.pi * 1.92, 4, c, at=head)
    paper.fill([head(p) for p in _round_rect(18, 36, 10, 18, 4)], c)
    paper.fill([head(p) for p in _round_rect(72, 36, 10, 18, 4)], c)
    line([(24, 53), (28, 62), (40, 62)], 2.4, c, at=head)
    paper.fill([head(p) for p in _ellipse(41, 61.5, 3.2, 3.2, n=16)], c)
    for k in (-1, 1):
        ex = hx + k * 9.5
        if s == "failed":
            line([(ex - 4, hy - 1), (ex + 4, hy + 2)], 2.6, at=head)
        elif lid == 2:
            arc(ex, hy + 1, 4.5, 4, math.pi, TAU, 2.8, at=head)
        elif lid == 1:
            line([(ex - 4, hy), (ex + 4, hy + .5)], 2.8, at=head)
        else:
            jx = (q() - .5) * .6
            paper.fill([head(p) for p in _ellipse(ex + jx, hy - 1, 2.7, 4.6 if s in ("needs", "listen") else 3.7, n=20)], PENCIL)
        tip = 2 * k if brow < 0 else 0
        line([(ex - 5, hy - 9 - brow * 2 + tip), (ex + 5, hy - 9 - brow * 2 - tip)], 2.2, at=head)
    if m > .08:
        paper.fill([head(p) for p in _ellipse(hx + 1, hy + 12, 5, 1.5 + m * 6, n=24)], MOUTH)
        arc(hx + 1, hy + 12, 5, 1.5 + m * 6, 0, TAU, 2, at=head)
    else:
        line([(hx - 5, hy + 12), (hx + 1, hy + (10 if s == "failed" else 13)), (hx + 6, hy + 12)], 2.4, at=head)
    # Pencil shading on the cheek, not turned with the head, as in the preview.
    for k in range(6):
        paper.stroke([body((56 + k * 3, 52 + k * .5)), body((52 + k * 3, 60))], 1.2 * Z, PENCIL, .4)
    return paper.pixels()
