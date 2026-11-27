"""Familiars to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. Now: the dragon redrawn (a neck, a belly of plates, darker wings
clear of the head, haunches, clawed feet, a longer tail), beside the live one. Put a new figure's
drawing here with its row in FIGURES to preview it beside the live ones, keeping the rules the
tests check (feet on row 42 of the 44, every motion through `Frame.wave`, `Frame.cycle` or
`Frame.beat` so each row repeats without a jump).

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402

from characters import ELL, LIMB, POLY, K, WH, ramp, tint, _round  # noqa: E402

CREAM = "#f3e2b8"  # horns, belly plates and claws


def dragon(F: ch.Frame, col: str):
    """Proud, redrawn: the head on a neck, a belly of cream plates, wings well darker than the body
    and clear of the head, haunches and clawed feet, a tail with a spade. It acts as the live one."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    dead = s == "failed"
    base = tint(col, -.25) if dead else col
    C, H, M = ramp(base), ramp(CREAM), ramp(tint(base, -.3))
    C = C[:5] + [C[4]]  # no brightest tone: on a body this small it was specks, not a shine
    wing, la, ra, mouth, eye, hy, chin, puff = .25, 0, 0, 0.0, "open", 0.0, 0, 0.0
    if s == "idle":  # proud: chin up, eyes half shut, chest out
        wing, eye, chin, puff = .25 + F.wave(4) * .3, "smug", 1, 1.0
    if s == "speaking":
        mouth, wing = V, .25 + V * .45 + F.wave(.5) * .12 * V
    if s == "needs":  # quick little flaps, kept low on the right, clear of the mark
        wing, ra, mouth, eye = .32 + abs(F.wave(.5)) * .18 * F.lively, 10 + F.wave(1, 1) * 1.2 * F.lively, .5, "wide"
    if s == "working":
        la, ra, wing = 3 * F.beat(2 / 3), 3 * F.beat(2 / 3, .5), .23
    if s == "done":  # wings spread wide, flapping once a second
        wing, la, ra, mouth, eye = .85 + F.wave(1) * .14, 9, 9, .6, "happy"
    if dead:
        wing, eye, hy = -.35 + F.wave(2) * .04, "x", 1
    if s == "listen":
        wing, ra, eye = .5 + F.wave(1) * .06, 6, "wide"
    # wings behind, from the shoulders: an arm up to the wrist, two fingers down from it, the
    # membrane scalloped between them; the wrist stays two pixels clear of the head
    for sd in (-1, 1):
        ax, ay, w = 20 + sd * 6, 25, wing
        wx, wy = ax + sd * (5 + 3.5 * w), 20 - 9 * w
        t1, t2, root = (wx + sd * (3 + .5 * w), wy + 5 - 2 * w), (wx + sd * .5, wy + 9.5 - 1.5 * w), (ax - sd, 28.5)
        e1 = ((t1[0] + t2[0]) / 2 - sd * 1.6, (t1[1] + t2[1]) / 2 - .5)
        e2 = ((t2[0] + root[0]) / 2, (t2[1] + root[1]) / 2 - 1.6)
        c.part(POLY([(ax, ay), (wx, wy), t1, e1, t2, e2, root]), M, flat=2, cast=0)
        c.part(LIMB(ax, ay, wx, wy, .7), M, flat=4, cast=0)
        for tip in (t1, t2):
            c.part(LIMB(wx, wy, tip[0] - sd * .4, tip[1] - .3, .5), M, flat=4, cast=0)
    # the tail, out to the right and up, a spade at its tip
    pts = [(25, 35.6), (30.5, 36.3), (34.8, 35), (37, 32)]
    for i in range(3):
        c.part(LIMB(*pts[i], *pts[i + 1], 2.3 - i / 3, 2.3 - (i + 1) / 3), C, flat=2, cast=0)
    c.part(POLY([(37, 26.6), (40, 31.2), (37, 30.2), (34, 31.2)]), M, flat=2, cast=0)
    # sitting: haunches, the body, a neck in shadow under the chin, the belly's plates, clawed feet
    for sd in (-1, 1):
        c.part(ELL(20 + sd * 6.8, 34.4, 4, 3.6), C, k=-1)
    c.part(ELL(20, 29.6 - puff * .4, 7.2 + puff * .4, 8.2), C)  # the chest out when proud
    c.part(ELL(20, 23.4, 5.2, 2.4), C, flat=2, cast=0)
    by, bw, bh = 30.6 - puff * .4, 4.4 + puff * .4, 5.2
    c.part(ELL(20, by, bw, bh), H, flat=3, cast=0)
    for y in (28, 31, 34):
        hw = bw * math.sqrt(max(0, 1 - ((y + .5 - by) / bh) ** 2))
        x0, x1 = math.ceil(20 - hw - .5), math.floor(20 + hw - .5)
        c.dot(x0, y, H[2], x1 - x0 + 1, 1)
    for fx in (15.2, 24.8):
        c.part(ELL(fx, 36.7, 2.9, 1.7), C)
        for d in (-2, 0, 2):
            c.dot(fx + d, 37, H[4])
    # the head: short horns curving back to a point, a small crest, the skull, then the snout
    for sd in (-1, 1):
        c.part(POLY([(20 + sd * 3, 10.2 + hy), (20 + sd * 4.6, 7.4 + hy), (20 + sd * 6.6, 5.6 + hy), (20 + sd * 8.6, 5.2 + hy),
                     (20 + sd * 7, 7 + hy), (20 + sd * 6.4, 10.4 + hy)]), H)
    c.part(POLY([(18.6, 9.5 + hy), (20, 6.5 + hy), (21.4, 9.5 + hy)]), M, flat=2)
    c.part(ELL(20, 15 + hy, 9, 6.8), C)
    c.part(ELL(20, 19.6 + hy - chin, 5.4, 3.7), C, flat=4, cast=0)
    # the arms in one tone: shaded, three pixels of arm were specks on the flank
    c.part(LIMB(13.5, 27, 11.5 - la * .2, 31 - la, 1.7), C, flat=4)
    c.part(LIMB(26.5, 27, 28.5 + (.5 if ra > 5 else 0), 31 - ra, 1.7), C, flat=4)
    E = _round(13 + hy)
    if eye == "smug":  # half shut: a lid across the top of each eye, the pupil under it
        for i, x in enumerate((15, 23)):
            c.dot(x - (1 if i == 0 else 0), E + 1, K, 3, 1)
            c.dot(x, E + 2, K, 2, 1)
            c.dot(x + (1 if i == 0 else 0), E + 2, WH)
    else:
        F.eyes([15, 23], E, eye, 3)
    ny = E + 5 - chin
    for x in (18, 22):  # nostrils: small slits on top of the snout
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
    if s == "speaking":  # a puff of fire once a second out of the side of its mouth, cooling to smoke
        k, g = F.cycle(1), .55 + .45 * V
        for j in range(3):
            q = k - j * .1
            if not 0 <= q < 1 or (V < .1 and q < .35):
                continue
            x, y, r = 26 + q * 9, my - q * 10, (1.4 + 2.6 * math.sin(q * math.pi)) * g
            if q < .7:
                c.part(ELL(x, y, r, r * .85), ramp("#f04a2a"), k=1, cast=0)
                c.part(ELL(x - .3, y + .2, r * .6, r * .55), ramp("#ffd84a"), flat=4, cast=0)
                if r > 2:  # a white-hot heart, so it shows on an orange dragon too
                    c.dot(x - .5, y, "#fff6d0")
            else:
                c.dot(x, y, "#b8bec9", 2 if r > 1.5 else 1, 2 if r > 1.5 else 1, (1 - q) / .3)
    if s == "done" and A < 3:
        for i in range(5):
            k = (A * 1.6 + i / 5) % 1
            c.dot(20 + math.sin(i * 2.1 + k * 4) * (2 + k * 5), my - 1 - k * 14, "#fff0a0" if k < .3 else "#ffb347" if k < .65 else "#e2593c", 1, 1, 1 - k * .8)
    if s == "working":  # smoke rings while it thinks
        k = F.cycle(2)
        for dx, dy, w in ((0, -1, 2), (0, 1, 2), (-1, 0, 1), (2, 0, 1)):
            c.dot(28 + k * 5 + dx, 16 + hy - k * 10 + dy, "#c9cfdb", w, 1, 1 - k)  # rising beside the head


# (name, color, drawing) of each figure being previewed
FIGURES: list = [("Dragon, redrawn", ch.COLORS[6], dragon), ("Dragon, today", ch.COLORS[6], ch.dragon)]
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
