"""A familiar to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. The author, 2026-11-26: "I feel like the turtle is the one that I
like the least. And the mushroom person, like the head seems very detached from the body", then
"any other familiars who would be cool, dragons and stuff?", then "do a preview. Don't delete the
turtle yet. Revamp it. We can maybe do more than 5". Of the previews: "improve but don't stray from
the main idea", then "you can put them": the shellback and the toadstool redrawn, the axolotl and
the dragon moved into hub/characters.py the same day. The mimic stays here, held for a rework.
Every motion goes through `Frame.wave` or `Frame.cycle`, so that each row repeats without a jump;
feet stay on row 42 of the 44.

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402
from characters import BOX, ELL, GOLD, K, LIMB, POLY, SHAPE, TAU, WH, Frame, _round, ramp  # noqa: E402


def mimic(F: Frame, col: str):
    """Sneaky: a treasure chest whose lid is its mouth; the straps and the lock in the session's color."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    Wd, Bd, In = ramp("#a8703c"), ramp(col), ramp("#3a1a22")
    op, eye, gold, tongue, tilt, look = 1.0, "open", False, 0, 0.0, 0
    if s == "idle":
        op = .5 + .5 * F.wave(4)
    if s == "speaking":
        op = 1 + V * 6.5 + F.wave(.5) * .5 * V
        tongue = 1 if V > .5 else 0
    if s == "needs":
        op, eye, gold = 5 + math.sin(A * TAU) * .8 * F.lively, "wide", True
    if s == "working":  # an even chatter, four times a second
        op = 1 + (math.floor(T * 4) % 2) * 2 if not ch.has("beat") else 1 + 1.6 * F.beat(.5)
    if s == "done":
        op, eye, gold, tongue = 6 + F.wave(1) * .5, "happy", True, 1
    if s == "failed":  # the lid knocked askew, down on one side
        op, eye, tilt = 2.2 + F.wave(2) * .15, "x", -.22
    if s == "listen":  # lid up a crack, eyes to one side
        op, eye, look = 2.5 + F.wave(1) * .4, "wide", 1
    top, x0, x1 = 24, 8.5, 31.5  # the box's top edge and its sides
    ly = top - op  # the lid's bottom edge in its middle, raised with the voice
    ct, st = math.cos(tilt), math.sin(tilt)

    def world(dx, dy):  # a point of the lid (from its bottom middle) where it is drawn
        return 20 + dx * ct - dy * st, ly + dx * st + dy * ct

    def local(p, q):
        X, Y = p - 20, q - ly
        return X * ct + Y * st, -X * st + Y * ct

    def lid(test, box):
        def f(p, q):
            u, v = local(p, q)
            return test(u, v)
        return SHAPE(f, box)
    yl, yr = world(-11.5, 0)[1], world(11.5, 0)[1]
    c.part(ELL(12.5, 36.6, 2.6, 1.6), Wd, k=-1)
    c.part(ELL(27.5, 36.6, 2.6, 1.6), Wd, k=-1)
    # the box: flat planks, straps over it, the lock on its front
    c.part(BOX(20, 30.25, 11.5, 6.25), Wd, flat=3)
    for y in (top + 4.5, top + 8.5):
        c.dot(9, y, Wd[2], 23, 1)
    c.dot(9, top + 12, Wd[2], 23, 1)
    for x in (12.5, 27.5):  # flat, lit on their left; the same on the lid
        c.part(BOX(x, 30.25, 1.5, 6.25), Bd, flat=3, cast=0)
        c.part(BOX(x - 1, 30.25, .5, 6.25), Bd, flat=4, cast=0)
    if op > .4:  # inside: dark, its side walls holding the lid to the box, teeth, maybe gold
        c.part(POLY([(x0, top + .5), (x1, top + .5), (x1, yr), (x0, yl)]), In, flat=2, cast=0)
        for x in (x0 + .6, x1 - .6):  # the side walls, in the wood's shadow
            c.part(LIMB(x, top, x, yl if x < 20 else yr, .8), Wd, flat=1, cast=0)
        for x in range(10, 31, 3):
            c.dot(x, top - 1, WH, 2, 1)
        if gold:
            for i in range(4):
                k = F.cycle(1, i * .25)
                c.dot(12 + i * 5, top - op * .55 + (k > .5), GOLD if k < .7 else "#fff3a8", 2, 1)
        if tongue:
            c.dot(17, top - 1, ramp("#ff7a95")[3], 6, 2)
            c.dot(18, top + 1, ramp("#ff7a95")[2], 4, 1)
    c.part(BOX(20, top + 3.6, 2.3, 2.3), Bd, flat=3)  # the lock, on the front of the box
    c.dot(18, top + 2, Bd[5], 2, 1)
    c.dot(20, top + 3, K, 1, 2)
    # the lid: a rounded top, its rim, the straps running over it; upper teeth under its edge
    c.part(lid(lambda u, v: (u / 12, v / 9.5) if (u / 12) ** 2 + (v / 9.5) ** 2 <= 1 and v < 0 else None, (7, ly - 11, 33, ly + 3)), Wd)
    c.part(lid(lambda u, v: (u / 12 * .7, (v + 1) / 1.3 * .7) if abs(u) <= 11.8 and abs(v + 1) <= 1.2 else None, (7, ly - 4, 33, ly + 3)), Wd, k=-1)
    for x in (-7.5, 7.5):  # one strap over lid and box: the same tone, lit on the left
        for lo, hi, z in ((-1.5, 1.5, 3), (-1.5, -.5, 4)):
            c.part(lid(lambda u, v, x=x, lo=lo, hi=hi: (0, 0) if lo <= u - x <= hi and v < 0 and (u / 12) ** 2 + (v / 9.5) ** 2 <= 1
                       else None, (7, ly - 11, 33, ly + 3)), Bd, flat=z, cast=0)
    if op > .4:
        for x in range(-8, 10, 3):
            X, Y = world(x + .5, .5)
            c.dot(X, Y, WH)
    ex = [world(-5 + look, -5), world(3 + look, -5)]  # clear of the straps
    for X, Y in ex:
        F.eyes([_round(X)], _round(Y), eye, 3)
    if s == "failed":
        F.smoke(20, ly - 9)
    if s == "done" and A < 2.5:
        for i in range(4):
            k = (A * 1.2 + i * .23) % 1
            c.dot(20 + (i - 1.5) * 6 * k, top - 2 - math.sin(k * math.pi) * 12, GOLD, 2, 2, 1 - k * .5)



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
