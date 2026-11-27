"""Familiars to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. Now: the axolotl retouched (its tail clear of the right hand,
with a fin; its arms in one tone), beside the live one. Put a new figure's drawing here with its row in FIGURES to preview it beside
the live ones, keeping the rules the tests check (feet on row 42 of the 44, every motion through
`Frame.wave`, `Frame.cycle` or `Frame.beat` so each row repeats without a jump).

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402

from characters import ELL, LIMB, RE, K, has, ramp, tint, _round  # noqa: E402


def axolotl(F: ch.Frame, col: str):
    """Sweet, retouched: the tail along the floor and up, clear of the right hand, a fin round its
    end in the gills' color; the arms in one tone. The rest is the live one."""
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
    # the tail behind, along the floor and up at the right, a row clear of the right hand; a fin
    # round its rising end, in the gills' color
    pts = [(24, 35.6), (29.5, 36), (33.8, 34.6), (36, 31 + F.wave(3))]  # a slow swish; still while it talks
    rad, fin = (1.9, 1.6, 1.3, .9), (0, .4, .9, .9)  # the fin thin where the tail lies on the floor
    for i in (1, 2):
        c.part(LIMB(*pts[i], *pts[i + 1], rad[i] + fin[i], rad[i + 1] + fin[i + 1]), Gl, flat=3, cast=0)
    for i in range(3):
        c.part(LIMB(*pts[i], *pts[i + 1], rad[i], rad[i + 1]), C, flat=2, cast=0)
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
    # arms in the body's color, one tone down and flat: a raised one is an arm, not a white stick
    # across the cheek, and shaded, three pixels of arm were specks on the flank
    for sx, (x, y) in ((14, L), (26, R)):
        c.part(LIMB(sx, 28.5, x, y, 1.6, 1.4), C, flat=2)
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


# (name, color, drawing) of each figure being previewed
FIGURES: list = [("Axolotl, retouched", ch.COLORS[5], axolotl), ("Axolotl, today", ch.COLORS[5], ch.axolotl)]
OTHER = ("#FF8FA3", "#F9E27D", "#7FDBCA", "#B07CFF")  # more session colors to see each one in


def main(out: str) -> None:
    import characters_page
    base = len(ch.FAMILIARS)
    now = [(n, c, ch.sheet("familiars", i, c)) for i, (n, c) in enumerate(zip(characters_page.NAMES["familiars"], characters_page.colors(base)))]
    ch.FAMILIARS.extend(f for _, _, f in FIGURES)  # in this process only, to draw their sheets
    try:
        nxt = [(n, c, ch.sheet("familiars", base + i, c)) for i, (n, c, _) in enumerate(FIGURES)]
        more = [(n, c, ch.sheet("familiars", base + i, c)) for i, (n, _, _) in enumerate(FIGURES) for c in OTHER]
    finally:
        del ch.FAMILIARS[base:]
    characters_page.write(out, [
        ("next", "Proposed", "Figures being previewed, not in the overlay yet.", nxt, ch.N),
        ("colors", "In Other Colors", "The same figures as other sessions would have them.", more, ch.N),
        ("familiars", "Today", "The familiars as the overlay has them now, to compare.", now, ch.N),
    ], title="Sidetone Familiars, Proposed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "familiars-next")
