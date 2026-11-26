"""A familiar to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. The mimic stays here, held for a rework. Every motion goes through
`Frame.wave` or `Frame.cycle`, so that each row repeats without a jump; feet stay on row 42 of the
44.

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402
from characters import GOLD, K, SHAPE, WH, Frame, _round, ramp  # noqa: E402


# The mimic's wood, the same whatever the session's color (which goes on its metal): a warm brown
# (hue about 28), built in OKLCH from the outline (lifted to show on the glass) to the highlight.
WOOD = [ch.from_oklch(L, C, h) for L, C, h in ((.36, .07, 42), (.42, .08, 45), (.49, .09, 50), (.56, .1, 54), (.65, .1, 60), (.74, .09, 68))]
INSIDE = [ch.from_oklch(L, C, h) for L, C, h in ((.17, .03, 350), (.19, .04, 355), (.24, .05, 10), (.3, .06, 15), (.36, .06, 20), (.42, .06, 25))]
TONGUE = ramp("#ff7a95")
IVORY, IVORY2 = ch._rgb("#f4ecd6"), ch._rgb("#c8b994")  # the fangs, lit and in shadow
GLOW = ch._rgb("#ffe27a")  # its glints and squints, glowing in the dark under the lid
EYE = ch._rgb("#fff6dc")  # its eyes, open
# Fangs: where each sits along a jaw, irregular and the same in every frame; each a base of two
# pixels on the jaw and a tip of one, on the side given (0 left, 1 right).
UPPER = ((7, 1), (12, 0), (26, 1), (30, 0))
LOWER = ((9, 0), (14, 1), (28, 0))
X0, X1 = 5, 34  # the chest's first and last columns: 30 pixels and an outline, 32 wide
LID, RIM = 12, 25  # the lid's top row, the box's top row; the lid shut fills the rows between
STRAPS = (11, 26)  # the straps' first columns, three pixels wide, over lid and box


def mimic(F: Frame, col: str):
    """Sneaky: a treasure chest, innocent, shut but for a crack, with eyes glinting in the dark
    under its lid; the lid is its mouth, fanged. Planks of wood in three tones, lit from the top
    left; the metal (straps, the lid's trim, the corner brackets, the lock) in the session's color.
    The lid swings back on its hinge as it opens, so its front shows shorter, and its top stays
    where it is, clear of the mark's corner; dark side walls join it to the box."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    dead = s == "failed"
    Wd, In, Bd = WOOD, INSIDE, ramp(ch.tint(col, -.25) if dead else col)
    gap, eye, look, tongue, gold, lick = 1, "glint", 0, 0, False, None
    lift = [0] * 40  # how far up each column of the lid is, over the gap (a lid knocked askew)
    if s == "idle":  # nearly shut; a shifty glance left and right once a row, then a quick lick
        k = F.cycle(4)
        look = -2 if .3 <= k < .42 else -1 if .42 <= k < .46 else 2 if .5 <= k < .62 else 1 if .62 <= k < .66 else 0
        if .74 <= k < .9:  # the tip of the tongue out of the crack, run along the box's rim
            lick = min(4, math.floor((k - .74) / .16 * 5))
        if .94 <= k < .98:
            eye = "shut"
    if s == "working":  # chomping: shut, opening, wide, closing, each held two frames, even
        q = math.floor(T * 6) % 4
        gap, eye = (0, 2, 5, 3)[q], "squint"
    if s == "speaking":  # the lid opens with the voice; silent, it still breathes
        gap = max(1, min(6, _round(1.2 + V * 5 + .5 * F.wave(1))))
        eye, tongue = "open" if gap >= 3 else "glint", V > .5
    if s == "needs":  # lid up, gold glinting inside, eyes wide; the lid rattles for five seconds
        gap, eye, gold = 5 + _round(F.wave(.5) * F.lively * 1.2), "wide", True
    if s == "done":  # a grin, the tongue out, coins hopping out of it and falling back in
        gap, eye, tongue = 5, "happy", True
    if dead:  # the lid knocked askew, down on the right, up on the left
        gap, eye = 0, "x"
        lift = [max(0, _round(6.5 * (30 - x) / 25 + .3 * F.wave(2))) for x in range(40)]
    if s == "listen":  # the lid ajar, eyes glancing up to the right, at the sign
        gap, eye, look = 4 + (F.wave(1) > .6), "up", 1
    Hl = RIM - LID - gap  # the lid's front, shorter as it swings back
    W = Hl - 2  # its wood; two rows of trim under it
    px: dict = {}

    def put(x, y, R, z):
        px[(x, y)] = (R, z)
    # the box: three planks, lit at the top left, in shadow on the right, their seams dark
    for y in range(RIM, 38):
        for x in range(X0, X1 + 1):
            z = 2 if x >= 31 or y == 37 else 4 if x <= 6 or y in (RIM + 1, 30, 34) and x < 24 else 3
            put(x, y, Wd, 1 if y in (29, 33) and X0 < x < X1 else z)
    for x, y, n in ((7, 27, 3), (16, 28, 2), (23, 31, 3), (7, 31, 2), (16, 35, 3), (22, 36, 2), (31, 27, 2), (32, 35, 2)):
        for i in range(n):  # grain, a few short dashes
            put(x + i, y, Wd, 1 if x + i >= 31 else 2)
    for x in range(X0, X1 + 1):  # the box's rim
        put(x, RIM, Bd, 4 if x <= 9 else 2 if x >= 31 else 3)
    # the lid, column by column (each lifted by its own amount when knocked askew)
    for x in range(X0, X1 + 1):
        for r in range(Hl):
            inset = (4, 2, 1)[r] if r < 3 else 0
            if not X0 + inset <= x <= X1 - inset:
                continue
            y = LID + r - lift[x]
            if r >= W:  # the trim, lit along its top
                put(x, y, Bd, (4 if x <= 9 else 3 if x < 31 else 2) if r == W else (2 if x < 31 else 1))
            else:  # the lid's planks: its curved top lit, its right in shadow, one seam
                z = 5 if r == 0 and 10 <= x <= 16 else 4 if r == 0 or (r == 1 and x < 22) or x <= X0 + inset else 3
                if x >= 31 - (r == 0) * 2:
                    z = 2 if r else 3
                if W >= 5 and r == _round(W * .6):
                    z = 1
                put(x, y, Wd, z)
        if gap + lift[x]:  # the gap under it: dark, with the box's side walls
            for y in range(LID + Hl - lift[x], RIM):
                if x <= X0 + 1:
                    put(x, y, Wd, 1)
                elif x >= X1 - 1:
                    put(x, y, Wd, 2)
                else:
                    put(x, y, In, 2 if y == LID + Hl - lift[x] else 3)
    for k in (0, 1):  # the corner brackets, top of the lid and foot of the box
        for r in range(5):
            for d in range(4 - max(0, r - 1)):
                x = X0 + d if not k else X1 - d
                y = LID + r - lift[x]
                if (x, y) in px and px[(x, y)][0] is Wd:
                    put(x, y, Bd, (5 if d == 0 else 4) if not k else (2 if d == 0 else 3))
        for x, y in [(i, 37) for i in range(5)] + [(i, 36) for i in range(4)] + [(0, 35), (1, 35), (0, 34)]:
            put(X0 + x if not k else X1 - x, y, Bd, (4 if x == 0 else 3) if not k else (2 if x == 0 else 3))
    for sx in STRAPS:  # the straps, over lid and box: lit on the left, bending inwards over the lid's top
        for y in range(LID - 7, 38):
            for i in range(3):
                x = sx + i
                r = y - LID + lift[x]  # the lid's row here
                X = x + ((1 if sx < 20 else -1) if 0 <= r < 2 else 0)
                if (y >= RIM or 0 <= r < Hl) and (X, y) in px and px[(X, y)][0] is not In:
                    put(X, y, Bd, (5 - i if r < 2 else 4 - i) if y < RIM else 4 - i)
            if y >= RIM + 1:  # its shadow on the wood
                put(sx + 3, y, Wd, 1 if (sx + 3, y) in px and px[(sx + 3, y)][1] == 1 else 2)
    for x in range(18, 23):  # the lock, on the box's front
        for y in range(RIM + 1, 32):
            put(x, y, Bd, 4 if x == 18 or y == RIM + 1 else 2 if x == 22 or y == 31 else 3)
    groups: dict = {}
    for (x, y), (R, z) in px.items():
        groups.setdefault((id(R), z), (R, z, set()))[2].add((x, y))
    for R, z, S in groups.values():
        xs, ys = [p[0] for p in S], [p[1] for p in S]
        c.part(SHAPE(lambda p, q, S=S: (0, 0) if (math.floor(p), math.floor(q)) in S else None,
                     (min(xs), min(ys), max(xs) + 1, max(ys) + 1)), R, flat=z, cast=0)
    # the metal's shine, the rivets, the keyhole
    for x, y in ((X0 + 1, LID + 3 - lift[X0 + 1]), (STRAPS[0] + 1, LID - lift[STRAPS[0] + 1]), (18, RIM + 1), (X0 + 1, 36)):
        c.dot(x, y, WH)
    c.dot(6, RIM - lift[6], WH, 2, 1)
    for x in (STRAPS[0] + 1, STRAPS[1] + 1):
        c.dot(x, 27, Bd[5])
        c.dot(x, 35, Bd[5])
    c.dot(20, 28, K)
    c.dot(20, 29, K)
    # inside: gold, fangs, eyes, tongue
    lip = RIM - gap  # the first row of the gap (straight lid)
    if gold and gap >= 3:  # a heap of coins at the back, one glinting at a time
        for x in (13, 20, 23, 28):
            c.dot(x, RIM - 1, GOLD, 2, 1)
            c.dot(x + 1, RIM - 1, ch._rgb("#c98a14"))
        c.dot(21, RIM - 2, GOLD, 2, 1)
        k = math.floor(F.cycle(1) * 4)
        c.dot((13, 21, 28, 23)[k], RIM - 1 - (k == 1), WH)
    if gap >= 2:  # the upper fangs first, then the lower ones, as the lid rises
        for x, side in UPPER:
            c.dot(x, lip, IVORY)
            c.dot(x + 1, lip, IVORY2)
            if gap >= 3:
                c.dot(x + side, lip + 1, IVORY)
        for x, side in LOWER if gap >= 3 else ():
            c.dot(x, RIM - 1, IVORY)
            c.dot(x + 1, RIM - 1, IVORY2)
            if gap >= 4:
                c.dot(x + side, RIM - 2, IVORY)
    if tongue and gap >= 3:
        c.dot(17, RIM - 1, TONGUE[2], 6, 1)
        c.dot(18, RIM - 2, TONGUE[3], 4, 1)
        c.dot(19, RIM - 2, TONGUE[4], 1, 1)
        if s == "done":  # out over the rim
            c.dot(19, RIM, TONGUE[3], 3, 1)
            c.dot(20, RIM + 1, TONGUE[2], 1, 1)
    if lick is not None:  # the tip of the tongue, along the rim from right to left
        x = (23, 21, 19, 17, 16)[lick]
        c.dot(x, RIM, TONGUE[3], 3, 1)
        c.dot(x + 1, RIM, TONGUE[4])
        c.dot(x + 1, RIM + 1, TONGUE[2])
    ex = (15 + look, 23 + look)
    ey = lip + (gap >= 4) + (gap >= 6)  # open eyes: clear of the upper fangs' bases
    if eye == "glint":  # two glints in the crack, all there is to see of it
        for x in ex:
            c.dot(x, lip, WH)
            c.dot(x + 1, lip, GLOW)
    elif eye == "squint" and gap >= 2:
        for x in ex:
            c.dot(x, lip + (gap >= 3), GLOW, 2, 1)
    elif eye == "open":  # two by two, glowing, in the middle of the dark
        for x in ex:
            c.dot(x, ey, GLOW, 2, 2)
            c.dot(x, ey, WH)
    elif eye in ("wide", "up"):  # three by three, a pupil in each (up to the right: at the sign)
        for x in ex:
            c.dot(x - (x < 20), ey, EYE, 3, 3)
            c.dot(x - (x < 20) + 1 + (eye == "up"), ey + 1 - (eye == "up"), K)
    elif eye == "happy":  # glowing arcs, a grin under them
        for x in ex:
            c.dot(x - 1, ey + 1, GLOW)
            c.dot(x, ey, GLOW, 2, 1)
            c.dot(x + 2, ey + 1, GLOW)
    elif eye == "x":
        for x in (10, 16):
            y = LID + Hl - lift[x] + 1
            for a, b in ((-1, 0), (1, 0), (0, 1), (-1, 2), (1, 2)):
                c.dot(x + a, y + b, ch._rgb("#d9cfe6"))
        y0 = LID + Hl - lift[6]  # smoke out of the open end of the seam, drifting up and out
        for i in range(3):
            k = F.cycle(2, i / 3)
            c.dot(6 - k * 4 + math.sin(k * 5 + i), y0 - k * 11, "#c4cad6", 2 if k < .4 else 1, 2 if k < .4 else 1, (1 - k) * min(1, k * 8))
    if s == "done":  # coins hop out of the mouth and fall back in, one after another, spinning
        for i in range(3):
            k = F.cycle(1, i / 3)
            sd = (-1, 1, 0)[i]
            x = 19 + sd * (1 + 7 * k)
            y = lip + 1 - math.sin(k * math.pi) * (13 if sd else 16)
            w = (3, 2, 1, 2)[math.floor(k * 12) % 4]  # spinning: face on, edge on
            c.dot(x + (3 - w) / 2, y, GOLD, w, 3)
            c.dot(x + (3 - w) / 2, y, "#fff3a8")
            c.dot(x + (3 - w) / 2 + w - 1, y + 2, ch._rgb("#b87a10"))



FIGURES = [("Mimic, sneaky", "#B07CFF", mimic)]


def main(out: str) -> None:
    import characters_page
    base = len(ch.FAMILIARS)
    now = [(n, c, ch.sheet("familiars", i, c)) for i, (n, c) in enumerate(zip(characters_page.NAMES["familiars"], characters_page.colors(base)))]
    ch.FAMILIARS.extend(f for _, _, f in FIGURES)  # in this process only, to draw their sheets
    try:
        nxt = [(n, c, ch.sheet("familiars", base + i, c)) for i, (n, c, _) in enumerate(FIGURES)]
    finally:
        del ch.FAMILIARS[base:]
    characters_page.write(out, [
        ("next", "Proposed", "The mimic, held for a rework. Preview only: not in the overlay.", nxt, ch.N),
        ("familiars", "Today", "The seven familiars as the overlay has them now, to compare.", now, ch.N),
    ], title="Sidetone Familiars, Proposed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "familiars-next")
