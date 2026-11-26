"""Familiars to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. The author, 2026-11-26: "I feel like the turtle is the one that I
like the least. And the mushroom person, like the head seems very detached from the body", then
"any other familiars who would be cool, dragons and stuff?", then "do a preview. Don't delete the
turtle yet. Revamp it. We can maybe do more than 5".

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402
from characters import BOX, DOME, ELL, GOLD, K, LIMB, POLY, RE, SHAPE, TAU, WH, EM, Frame, _clamp, _round, ramp, tint  # noqa: E402,F401


def toadstool(F: Frame, col: str):
    """Grumpy, now one piece: a stout stem that runs up into the cap, the face on the stem."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, W, G = ramp(col), ramp("#ead9b6"), ramp("#d8c49c")
    cy, ct, ra, la, br, lean = 0.0, 0.0, 0, 0, 1, 0.0
    if s == "speaking":
        cy = -V * 1.6
    if s == "needs":
        cy, ct, ra, br = -1 + (math.sin(A * TAU) * .6 if A < 5 else 0), 3, 9, 0
    if s == "done":
        ra, la, br = 9, 9, -1
    if s == "failed":
        cy, ct, lean = 3, -2, -1
    if s == "working":
        k = math.floor(T * 6) % 2
        ra, la = (3, 0) if k else (0, 3)
    if s == "listen":
        cy, ct, ra, br = -1, 2.5, 10, 0
    if s == "idle":
        cy = math.sin(T * TAU / 4) * .4
    c.part(ELL(15.5, 36.8, 2.8, 1.6), W, k=-1)
    c.part(ELL(24.5, 36.8, 2.8, 1.6), W, k=-1)
    X, y = 20 + ct * .4 + lean, 20 + cy
    # the stem: wide at the foot, narrowing up into the cap, so the cap sits on it
    c.part(SHAPE(lambda p, q: ((p - 20) / 8, (q - 30) / 8) if q > y and abs(p - (20 + (X - 20) * (34 - q) / 14)) <= 5.2 + (q - y) * .19 and q < 37 else None,
                 (10, y, 30, 37)), W)
    c.part(LIMB(13.5, 29, 10.5 - la * .2, 33 - la, 1.8), W, k=-1)
    c.part(LIMB(26.5, 29, 29.5 + (.5 if ra > 5 else 0), 33 - ra, 1.8), W, k=-1)

    def cap(p, q):
        u, v, cut = (p - X) / 13.5, (q - y) / 12, y + 2 + ct * (p - X) * .05
        return (u, v) if u * u + v * v <= 1 and q < cut else None
    c.part(SHAPE(cap, (X - 14, y - 12, X + 14, y + 3)), C)
    for a, b, w, h in ((-6.5, -5.5, 2.5, 2.2), (1, -8.5, 3, 2.4), (7.5, -4, 2.3, 2), (-1, -2.5, 1.7, 1.3), (-10.5, -1.5, 1.3, 1.1)):
        c.part(ELL(X + a, y + b, w, h), ramp("#fff3df"), cast=0)
    c.dot(X - 6, y + 2.5, G[1], 12, 1)  # the gills' shadow, just under the rim
    ey = 26 - (1 if s in ("needs", "done", "listen") else 0) + (1 if s == "failed" else 0)
    ex = _round(20 + (X - 20) * .5)
    if s == "failed":
        F.eyes([ex - 4, ex + 3], ey, "shut")
        c.dot(ex - 2, ey + 6, K)
        c.dot(ex - 1, ey + 5, K, 4, 1)
        c.dot(ex + 3, ey + 6, K)
        F.smoke(20, 7)
    else:
        if s == "done":
            F.eyes([ex - 4, ex + 3], ey, "happy")
        else:
            F.eyes([ex - 4, ex + 2], ey, "wide" if s in ("needs", "listen") else "open", 2)
            if br > 0:
                c.dot(ex - 5, ey - 1, K, 2, 1)
                c.dot(ex - 3, ey, K)
                c.dot(ex + 3, ey - 1, K, 2, 1)
                c.dot(ex + 2, ey, K)
        F.mouth(ex, ey + 5, V if s == "speaking" else .4 if s == "needs" else .5 if s == "done" else 0)


def shellback(F: Frame, col: str):
    """Shy, now facing you: sitting up, the shell on its back, a big face; it hides in the shell."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, W, D, Y = ramp(col), ramp("#d9cf9a"), ramp(tint(col, -.35)), ramp("#f0dc92")
    hy, la, ra, jaw, tilt, hide = 0.0, 0, 0, 0.0, 0.0, 0.0
    if s == "speaking":
        jaw, hy = V, -V
    if s == "needs":
        hy, ra, jaw = -2.5, 10 + (math.sin(A * TAU) * 1.5 if A < 5 else 0), .4
    if s == "working":
        k = math.floor(T * 6) % 2
        la, ra = (3, 0) if k else (0, 3)
        hy = 1
    if s == "done":
        la, ra, hy, jaw = 9, 9, -1.5, .5
    if s == "failed":
        hide = _clamp(A / .4) if A < 5 else 1
    if s == "listen":
        hy, tilt, ra = -1.5, 1.5, 6
    if s == "idle":
        hy = math.sin(T * TAU / 4) * .4
    hy += hide * 9
    # the shell behind: a dome showing round the body, its rim in the session's color
    c.part(ELL(20, 27, 12.5, 10.5), C, k=-1)
    for x, y in ((10.5, 23), (29.5, 23), (9.5, 30), (30.5, 30)):
        c.part(ELL(x, y, 2.4, 2.6), D, cast=0)
    c.part(ELL(14.5, 36.6, 3, 1.8), W, k=-1)
    c.part(ELL(25.5, 36.6, 3, 1.8), W, k=-1)
    # the head, then the belly plate over its neck
    hx = 20 + tilt
    if hide < 1:
        c.part(ELL(hx, 16 + hy, 8, 7), W)
    c.part(ELL(20, 29.5, 8, 7.5), Y)
    for y in (27, 31):
        c.dot(14, y, Y[2], 13, 1)
    c.dot(20, 23.5, Y[2], 1, 12)
    c.part(LIMB(12.5, 27, 9.5 - la * .2, 31 - la, 2), W, k=-1)
    c.part(LIMB(27.5, 27, 30.5 + (.5 if ra > 5 else 0), 31 - ra, 2), W, k=-1)
    if hide >= 1:  # only its eyes, peeking over the plate
        c.part(DOME(20, 24, 7, 3, 23.5), W)
        if math.floor(T * 2) % 5:
            c.dot(16, 22, K, 2, 1)
            c.dot(23, 22, K, 2, 1)
        F.smoke(20, 14)
        return
    X, E = _round(hx), _round(15 + hy)
    if s == "done":
        F.eyes([X - 5, X + 3], E - 1, "happy")
    else:
        F.eyes([X - 5, X + 3], E - 1, "wide" if s in ("needs", "listen") else "open", 3)
    c.dot(X - 7, E + 3, ramp("#ff9aa8")[3], 2, 1, .7)
    c.dot(X + 5, E + 3, ramp("#ff9aa8")[3], 2, 1, .7)
    if jaw > .15:
        c.dot(X - 1, E + 3, K, 3, 3 if jaw > .5 else 2)
        if jaw > .5:
            c.dot(X - 1, E + 5, EM, 3, 1)
    else:
        c.dot(X - 2, E + 3, K)
        c.dot(X - 1, E + 4, K, 3, 1)
        c.dot(X + 2, E + 3, K)


def dragon(F: Frame, col: str):
    """Proud: a whelp in the session's color, horns, wings that spread, a little fire."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, B, H, Wg = ramp(col), ramp(tint(col, .45)), ramp("#f3e2b8"), ramp(tint(col, -.25))
    wing, la, ra, mouth, flap, eye = .25, 0, 0, 0.0, 0.0, "open"
    if s == "speaking":
        mouth, wing = V, .3 + V * .3
    if s == "needs":
        wing, ra, mouth, eye = 1, 10, .5, "wide"
        flap = math.sin(A * TAU * 2) * 1.5 if A < 5 else 0
    if s == "working":
        k = math.floor(T * 6) % 2
        la, ra = (3, 0) if k else (0, 3)
    if s == "done":
        wing, la, ra, mouth, eye = 1, 9, 9, .6, "happy"
    if s == "failed":
        wing, eye = 0, "x"
    if s == "listen":
        wing, ra, eye = .6, 6, "wide"
    if s == "idle":
        wing = .25 + math.sin(T * TAU / 4) * .08
    # wings behind, from the shoulders out and up
    for sd in (-1, 1):
        sx, tip = 20 + sd * 5, wing * 7 + flap
        c.part(POLY([(sx, 25), (sx + sd * (8 + wing * 3), 17 - tip), (sx + sd * (10 + wing * 2), 24 - tip * .4),
                     (sx + sd * (7.5 + wing * 1.5), 23.5 - tip * .2), (sx + sd * (8 + wing), 28), (sx + sd * 1, 30)]), Wg, k=-1)
    # the tail, curling out to the right
    c.part(LIMB(25, 34, 31, 35, 2.4, 1.6), C, k=-1)
    c.part(LIMB(31, 35, 33.5, 31.5, 1.6, 1), C, k=-1)
    c.part(POLY([(32.5, 31.5), (35.5, 29), (34.8, 32.6)]), Wg, flat=3)
    c.part(ELL(15.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(24.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(20, 30.5, 8, 6.8), C)
    c.part(ELL(20, 32, 4.8, 4.6), B, cast=0)
    for y in (30, 32.5, 35):
        c.dot(17, y, B[2], 6, 1)
    # the head: horns, then the face with a snout
    for sd in (-1, 1):
        c.part(POLY([(20 + sd * 3.5, 12), (20 + sd * 7.5, 5.5), (20 + sd * 6.5, 12.5)]), H)
    c.part(ELL(20, 17, 8.6, 7.2), C)
    for sd in (-1, 1):  # small fins at the cheeks
        c.part(POLY([(20 + sd * 8, 15.5), (20 + sd * 11.5, 13 - (2 if s in ("listen", "needs") else 0)), (20 + sd * 8.5, 18.5)]), Wg, flat=3)
    c.part(ELL(20, 20.5, 4.6, 2.8), B, cast=0)
    c.part(LIMB(13, 27, 10.5 - la * .2, 31 - la, 1.8), C, k=-1)
    c.part(LIMB(27, 27, 29.5 + (.5 if ra > 5 else 0), 31 - ra, 1.8), C, k=-1)
    F.eyes([15, 23], 14, eye, 3)
    c.dot(18, 20, C[0])
    c.dot(21, 20, C[0])
    if s == "failed":  # it sneezed: soot on the snout, smoke out of the nose
        c.dot(16, 21, "#3a3440", 3, 1)
        c.dot(22, 22, "#3a3440", 2, 1)
        F.smoke(20, 10)
        return
    if mouth > .08:
        F.mouth(20, 22, mouth)
    else:
        c.dot(18, 22, C[0], 4, 1)
    fire = ramp("#ffb347")
    if s == "speaking" and V > .5 or s == "done" and A < 3:
        n = 3 if s == "speaking" else 5
        for i in range(n):
            k = (T * 1.6 + i / n) % 1
            c.dot(20 + math.sin(i * 2.1 + k * 4) * (2 + k * 5), 21 - k * 14, "#fff0a0" if k < .3 else fire[3] if k < .65 else fire[1], 1, 1, 1 - k * .8)
    if s == "working":  # smoke rings while it thinks
        k = (T * .5) % 1
        c.dot(24 + k * 6, 16 - k * 10, "#c9cfdb", 2, 1, 1 - k)
        c.dot(24 + k * 6, 18 - k * 10, "#c9cfdb", 2, 1, 1 - k)
        c.dot(23 + k * 6, 17 - k * 10, "#c9cfdb", 1, 1, 1 - k)
        c.dot(26 + k * 6, 17 - k * 10, "#c9cfdb", 1, 1, 1 - k)


def mimic(F: Frame, col: str):
    """Sneaky: a treasure chest whose lid is its mouth; the bands and lock in the session's color."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    Wd, Bd, Lk = ramp("#a8703c"), ramp(col), ramp(tint(col, .3))
    op, eye, gold, tongue = 1.0, "open", False, 0
    if s == "idle":
        op = .5 + .5 * math.sin(T * TAU / 4)
    if s == "speaking":
        op = 1 + V * 7
        tongue = 1 if V > .5 else 0
    if s == "needs":
        op, eye, gold = 5 + (math.sin(A * TAU) if A < 5 else 0), "wide", True
    if s == "working":
        op = 1 + (math.floor(T * 8) % 2) * 2
    if s == "done":
        op, eye, gold, tongue = 6, "happy", True, 1
    if s == "failed":
        op, eye = 0, "shut"
    if s == "listen":
        op, eye = 3, "wide"
    top = 26  # the base's top edge
    c.part(ELL(12, 37, 2.6, 1.6), Wd, k=-1)
    c.part(ELL(28, 37, 2.6, 1.6), Wd, k=-1)
    c.part(BOX(20, 31.5, 11.5, 5.5), Wd)
    for x in (11.5, 28.5):
        c.part(BOX(x, 31.5, 1.3, 5.5), Bd, flat=3, cast=0)
    if op > .5:  # inside: dark, teeth, maybe gold
        c.dot(9, top - op, "#1a0f14", 23, _round(op) + 1)
        for x in range(10, 31, 3):
            c.dot(x, top - 1, WH, 2, 1)
            c.dot(x + 1, top - op, WH, 1, 1)
        if gold:
            for i in range(4):
                k = (T * 1.5 + i * .25) % 1
                c.dot(12 + i * 5, top - op * .6 + (k > .5), GOLD if k < .7 else "#fff3a8")
        if tongue:
            c.dot(17, top - 1, ramp("#ff7a95")[3], 6, 2)
            c.dot(18, top + 1, ramp("#ff7a95")[2], 4, 1)
    ly = top - op  # the lid, raised with the voice
    c.part(DOME(20, ly, 12, 7, ly + .01), Wd)
    c.part(BOX(20, ly - 1, 12, 1.3), Wd, k=-1)
    for x in (11.5, 28.5):
        c.part(SHAPE(lambda p, q, x=x: ((p - x) / 2, (q - ly) / 7) if abs(p - x) <= 1.3 and q < ly and ((p - 20) / 12) ** 2 + ((q - ly) / 7) ** 2 <= 1 else None,
                     (x - 1.5, ly - 7, x + 1.5, ly)), Bd, flat=3, cast=0)
    c.part(BOX(20, ly + .5, 2.2, 2.2), Lk, flat=4)
    c.dot(20, ly, K, 1, 2)
    F.eyes([14, 24], _round(ly - 5), eye, 3)
    if s == "failed":
        F.smoke(20, 22)
    if s == "done" and A < 2.5:
        for i in range(4):
            k = (A * 1.2 + i * .23) % 1
            c.dot(20 + (i - 1.5) * 6 * k, top - 2 - math.sin(k * math.pi) * 12, GOLD, 2, 2, 1 - k * .5)


def axolotl(F: Frame, col: str):
    """Sweet: frilly gills that flutter with the voice, a wide smile, cheeks that blush."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, B, Gl = ramp(col), ramp(tint(col, .4)), ramp(tint(col, -.2))
    spread, droop, la, ra, eye, blush = .3, 0.0, 0, 0, "open", .45
    if s == "idle":
        spread = .3 + math.sin(T * TAU / 2) * .06
    if s == "speaking":
        spread = .2 + V * .8 + math.sin(T * TAU * 3) * .05 * V
    if s == "needs":
        spread, ra, eye = .9, 10 + (math.sin(A * TAU) * 1.5 if A < 5 else 0), "wide"
    if s == "working":
        spread = .35 + (math.floor(T * 6) % 2) * .1
        k = math.floor(T * 6) % 2
        la, ra = (3, 0) if k else (0, 3)
    if s == "done":
        spread, la, ra, eye, blush = .8, 9, 9, "happy", 1
    if s == "failed":
        droop, eye, blush = 1, "shut", 0
    if s == "listen":
        spread, eye = .7, "wide"
    # tail behind, to one side
    c.part(LIMB(24, 33, 33, 30 + math.sin(T * TAU / 2), 2.6, 1.2), C, k=-1)
    c.part(ELL(15, 36.6, 2.8, 1.6), C, k=-1)
    c.part(ELL(25, 36.6, 2.8, 1.6), C, k=-1)
    c.part(ELL(20, 31.5, 7, 5.5), C)
    c.part(ELL(20, 32.5, 4, 3.6), B, cast=0)
    # gills: three frills each side, fanning up with `spread`, hanging when it fails
    for sd in (-1, 1):
        for i, base in enumerate((-.55, 0, .55)):
            a = base * (.6 + spread * .7) + (.9 if droop else -.25 * spread)
            x0, y0 = 20 + sd * 8.5, 18.5 + i * 2 - 2
            L = 5 + spread * 1.5 - droop
            x1, y1 = x0 + sd * math.cos(a) * L, y0 + math.sin(a) * L
            c.part(LIMB(x0, y0, x1, y1, 1.4, 1.1), Gl)
            c.dot(x1 - .5, y1 - .5, Gl[5], 1, 1, .9)
    c.part(ELL(20, 20, 10, 7.2), C)
    c.part(LIMB(14, 28.5, 11.5 - la * .2, 32 - la, 1.6), C, k=-1)
    c.part(LIMB(26, 28.5, 28.5 + (.5 if ra > 5 else 0), 32 - ra, 1.6), C, k=-1)
    F.eyes([13, 25], 17, eye, 2)
    for x in (11, 27):
        c.dot(x, 22, "#ff6f91", 2, 1, blush)
    if s == "failed":
        c.dot(17, 24, K)
        c.dot(18, 23, K, 4, 1)
        c.dot(22, 24, K)
        F.smoke(20, 9)
    elif s == "speaking" and V > .08 or s == "needs":
        F.mouth(20, 22, V if s == "speaking" else .4)
    else:
        c.dot(16, 22, K)
        c.dot(17, 23, K, 6, 1)
        c.dot(23, 22, K)


FIGURES = [("Toadstool, joined", "#FF8FA3", toadstool), ("Shellback, facing you", "#7FDBCA", shellback),
           ("Dragon whelp, proud", "#FFA24D", dragon), ("Mimic, sneaky", "#B07CFF", mimic), ("Axolotl, sweet", "#8AB4FF", axolotl)]


def main(out: str) -> None:
    import characters_page
    base = len(ch.FAMILIARS)
    ch.FAMILIARS.extend(f for _, _, f in FIGURES)  # in this process only, to draw their sheets
    now = [(n, c, ch.sheet("familiars", i, c)) for i, (n, c) in enumerate(zip(characters_page.NAMES["familiars"], ch.COLORS[:5]))]
    nxt = [(n, c, ch.sheet("familiars", base + i, c)) for i, (n, c, _) in enumerate(FIGURES)]
    characters_page.write(out, [
        ("next", "Proposed", "Two revamped (the toadstool in one piece, the shellback facing you) and three new: a dragon whelp, a mimic and an axolotl. Preview only: not in the overlay yet.", nxt, ch.N),
        ("familiars", "Today", "The five familiars as the overlay has them now, to compare.", now, ch.N),
    ], title="Sidetone Familiars, Proposed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "familiars-next")
