"""Familiars to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. The author, 2026-11-26: "I feel like the turtle is the one that I
like the least. And the mushroom person, like the head seems very detached from the body", then
"any other familiars who would be cool, dragons and stuff?", then "do a preview. Don't delete the
turtle yet. Revamp it. We can maybe do more than 5". Of the first preview: "improve but don't stray
from the main idea" ("mushroom a bit off, dragon not crazy, especially the wings, the chest not that
good"). Redrawn 2026-11-26 after a review: the toadstool's gills, the shellback's shell round its
head and a green face, the dragon's bat wings, horns and muzzle, a flat plank chest with straps
over lid and box, the axolotl's paws out to the side. Every motion goes through `Frame.wave` or
`Frame.cycle`, so that each row repeats without a jump; feet stay on row 42 of the 44.

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
    """Grumpy, now one piece: a stout stem that flares up into the cap's gills, the face on the stem."""
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
        if ch.LOOK != 1:  # in turn, with frames in between
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
            if br > 0:
                c.dot(ex - 5, ey - 1, K, 2, 1)
                c.dot(ex - 3, ey, K)
                c.dot(ex + 3, ey - 1, K, 2, 1)
                c.dot(ex + 2, ey, K)
        if s == "listen":  # a small, curious mouth
            c.dot(ex - 1, ey + 5, K, 2, 1)
        else:
            F.mouth(ex, ey + 5, V if s == "speaking" else .4 if s == "needs" else .5 if s == "done" else 0)


def shellback(F: Frame, col: str):
    """Shy, on all fours, seen from the front and a little above: a big domed shell in the session's
    color, its plates parted by dark seams, a light rim; a round green face pokes out under it.
    It pulls everything in when its session fails."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, D, Rm = ramp(col), ramp(tint(col, -.3)), ramp(tint(col, .3))
    W, Wa = ramp("#a9c47f"), ramp("#7f9f57")  # the face, and the legs a tone darker
    hy, tilt, eye, mouth, lift, wave_, wig, hide = 0.0, 0.0, "open", 0.0, (0, 0), None, 0.0, 0
    sy = 0.0  # the shell's breath: its top a little up or down
    if s == "idle":
        hy, sy = F.wave(4) * .45, F.wave(4, 1) * .4
    if s == "working":  # nibbling, or reading: the head bobs down, the front feet tap in turn
        k = math.floor(T * 6) % 2
        hy, lift = .4 + k, (1, 0) if k else (0, 1)
        if ch.LOOK != 1:  # with frames in between
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
    Ln = ramp(tint("#7f9f57", -.62))  # a dark line round the legs and the face, where they lie on the shell
    line = True
    if ch.LOOK != 1:  # LOOK 2: the line in the legs' own outline tone, as the engine draws round them, not a near-black
        Ln = Wa
    for i, x in enumerate((10, 30)):
        sd = -1 if i == 0 else 1
        if i == 1 and wave_ is not None:
            fx, fy = 33.5 + wave_ * .6, 25 - wave_
            if line:
                c.part(LIMB(29, 31, fx, fy, 3.2, 2.9), Ln, flat=1, cast=0)
            c.part(LIMB(29, 31, fx, fy, 2.3, 2), Wa)
            c.part(ELL(fx + .2, fy - .5, 2.3, 2.1), Wa)
            continue
        up = lift[i]
        if line:
            c.part(LIMB(x - sd * .3, 31.5, x + sd * .3, 35 - up, 3.4), Ln, flat=1, cast=0)
        c.part(LIMB(x - sd * .3, 31.5, x + sd * .3, 35 - up, 2.5), Wa)
        c.part(ELL(x + sd * .6, 36.6 - up, 3.3, 1.7), Wa, k=-1)
    # the head: a neck when it stretches, then the round face (its middle on whole pixels)
    hc = _round(30 + hy)
    if hc < 28:
        if line:
            c.part(LIMB(20, 33, 20, hc + 3, 3.1), Ln, flat=1, cast=0)
        c.part(LIMB(20, 33, 20, hc + 3, 2.2), Wa, k=-1)
    if line:
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


def dragon(F: Frame, col: str):
    """Proud: a whelp in the session's color, horns that curve back, a muzzle, wings that spread, a little fire."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    dead = s == "failed"
    C = ramp(tint(col, -.25) if dead else col)
    # the wings' membrane a little darker than the body, so arms in front of them stand out
    B, H, M, Bn = ramp(tint(col, .45)), ramp("#f3e2b8"), ramp(tint(col, -.14)), ramp(tint(col, -.45))
    wing, la, ra, mouth, eye, hy = .25, 0, 0, 0.0, "open", 0.0
    if s == "idle":
        wing = .25 + F.wave(4) * .3  # two pixels up and down, slowly
    if s == "speaking":
        mouth, wing = V, .25 + V * .45 + F.wave(.5) * .12 * V
    if s == "needs":  # quick little flaps, kept low on the right, clear of the mark
        wing, ra, mouth, eye = .32 + abs(F.wave(.5)) * .18 * F.lively, 10 + F.wave(1, 1) * 1.2 * F.lively, .5, "wide"
    if s == "working":
        k = math.floor(T * 6) % 2
        la, ra = (3, 0) if k else (0, 3)
        wing = .2 + k * .06
        if ch.LOOK != 1:  # in turn, with frames in between
            la, ra, wing = 3 * F.beat(2 / 3), 3 * F.beat(2 / 3, .5), .23
    if s == "done":  # wings spread wide and flapping
        wing, la, ra, mouth, eye = .85 + F.wave(.5) * .12, 9, 9, .6, "happy"
    if dead:
        wing, eye, hy = -.35 + F.wave(2) * .04, "x", 1
    if s == "listen":
        wing, ra, eye = .5 + F.wave(1) * .06, 6, "wide"
    # wings behind: a bright membrane in the session's color between darker bones
    for sd in (-1, 1):  # a bat's wing: an arm up to the wrist, three fingers down from it, membrane between
        sx, w = 20 + sd * 5, wing
        wx, wy = sx + sd * (6 + w * 2), 15 - w * 6
        tips = [(wx + sd * (4 + w), wy + 3.5 - w * 2), (wx + sd * 4, wy + 9.5 - w), (wx + sd * 1, wy + 13.5 - w * .5)]

        def mid(a, b, pull=1.6):  # the membrane's edge curves in between two finger tips
            return ((a[0] + b[0]) / 2 - sd * pull, (a[1] + b[1]) / 2)
        c.part(POLY([(sx, 23.5), (wx, wy), tips[0], mid(tips[0], tips[1]), tips[1], mid(tips[1], tips[2]), tips[2],
                     (sx + sd * 3, 29), (sx, 29)]), M)
        c.part(LIMB(sx, 23.5, wx, wy, .65), Bn, flat=2, cast=0)
        for tip in tips:
            c.part(LIMB(wx, wy, tip[0] - sd * .4, tip[1] - .2, .5), Bn, flat=2, cast=0)
    # the tail, curling out to the right, a spade at its tip
    c.part(LIMB(25, 34, 31, 35, 2.4, 1.6), C, k=-1)
    c.part(LIMB(31, 35, 33.5, 31.5, 1.6, 1), C, k=-1)
    c.part(POLY([(32.5, 31.8), (35.5, 28.8), (35, 32.6)]), M, flat=3)
    c.part(ELL(15.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(24.5, 36.6, 3, 1.8), C, k=-1)
    c.part(ELL(20, 30.5, 8, 6.8), C)
    c.part(ELL(20, 32, 4.8, 4.6), B, cast=0)
    for y in (30, 32.5, 35):
        c.dot(17, y, B[2], 6, 1)
    # the head: horns sweeping out and back, a small crest, the skull, then a longer muzzle
    for sd in (-1, 1):
        c.part(POLY([(20 + sd * 3, 10 + hy), (20 + sd * 5, 6.5 + hy), (20 + sd * 8, 4.5 + hy), (20 + sd * 11, 4.8 + hy),
                     (20 + sd * 8.5, 6.6 + hy), (20 + sd * 6.8, 10.5 + hy)]), H)
    c.part(POLY([(18.6, 9.5 + hy), (20, 6.5 + hy), (21.4, 9.5 + hy)]), M, flat=3)
    c.part(ELL(20, 15 + hy, 8.4, 6.6), C)
    for sd in (-1, 1):  # small fins at the cheeks
        c.part(POLY([(20 + sd * 7.5, 14 + hy), (20 + sd * 11, 12 - (2 if s in ("listen", "needs") else 0) + hy), (20 + sd * 8.5, 17.5 + hy)]), M, flat=3)
    c.part(ELL(20, 20.3 + hy, 4.6, 4), C)  # the muzzle, standing out below the skull
    c.part(LIMB(13, 27, 10.5 - la * .2, 31 - la, 1.8), C)
    c.part(LIMB(27, 27, 29.5 + (.5 if ra > 5 else 0), 31 - ra, 1.8), C)
    E = _round(13 + hy)
    F.eyes([15, 23], E, eye, 3)
    for x in (18, 22):  # nostrils: small slits on top of the muzzle
        c.dot(x, E + 5, C[1])
    if dead:  # it sneezed: soot on its face, smoke out of both nostrils
        c.dot(16, E + 6, "#3a3440", 3, 1, .8)
        c.dot(22, E + 7, "#3a3440", 3, 1, .8)
        c.dot(19, E + 8, C[0], 3, 1)
        def puff(x, y, r, a):  # a round little cloud, 1 to 4 pixels across
            X, Y = _round(x), _round(y)
            for dx, dy, w, h in {1: ((0, 0, 1, 1),), 2: ((0, 0, 2, 2),), 3: ((-1, 0, 3, 1), (0, -1, 1, 3)),
                                 4: ((-1, 0, 4, 2), (0, -1, 2, 4))}[r]:
                c.dot(X + dx, Y + dy, "#c8cfdb", w, h, a)
        for x, ph in ((18, 0), (22, .5)):  # puffing out of the nostrils, swelling as they rise past the head
            for i in range(3):
                k = F.cycle(2, ph + i / 3)
                sd = 1 if x > 20 else -1
                puff(x + sd * (1 + k * 11), E + 4 - k * 14, 1 + min(3, int(k * 4)), min(1, k * 4) * (.9 - k * .6))
        return
    my = E + 8
    if mouth > .08:
        F.mouth(20, my, mouth)
    else:
        c.dot(18, my, C[0], 4, 1)
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
        op = 1 + (math.floor(T * 4) % 2) * 2 if ch.LOOK == 1 else 1 + 1.6 * F.beat(.5)
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


def axolotl(F: Frame, col: str):
    """Sweet: frilly gills that flutter with the voice, a wide smile, cheeks that blush."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    C, B, Gl = ramp(col), ramp(tint(col, .4)), ramp(tint(col, -.2))
    spread, droop, eye, blush, tl, hy = .3, 0.0, "open", .45, 0.0, 0.0
    L, R = (11.5, 32), (28.5, 32)  # where the hands are
    if s == "idle":
        spread = .3 + F.wave(2) * .06
    if s == "speaking":
        spread, hy = .2 + V * .8 + F.wave(1 / 3) * .05 * V, -V * 1.2
    if s == "needs":  # it waves one hand high and out to the side, the gills up
        spread, eye, hy = .9 + F.wave(.5) * .06 * F.lively, "wide", -.5
        R = (33.5 + F.wave(1) * 1.2 * F.lively, 22 - F.wave(1, 1) * 1.2 * F.lively)  # up high, not pointing
    if s == "working":
        k = math.floor(T * 6) % 2
        spread = .35 + k * .1
        L, R = ((11.5, 29), (28.5, 32)) if k else ((11.5, 32), (28.5, 29))
        if ch.LOOK != 1:  # in turn, with frames in between
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
    # tail behind, to one side
    c.part(LIMB(24, 33, 33, 30 + F.wave(3), 2.6, 1.2), C, k=-1)  # a slow swish; still while it talks
    c.part(ELL(15, 36.6, 2.8, 1.6), C, k=-1)
    c.part(ELL(25, 36.6, 2.8, 1.6), C, k=-1)
    c.part(ELL(20, 31.5, 7, 5.5), C)
    c.part(ELL(20, 32.5, 4, 3.6), B, cast=0)
    # gills: three frills each side, fanning up with `spread`, hanging when it fails
    for sd in (-1, 1):
        for i, base in enumerate((-.55, 0, .55)):
            a = base * (.6 + spread * .7) + (.9 if droop else -.25 * spread) - sd * tl
            x0, y0 = rot(20 + sd * 8.5, 18.5 + i * 2 - 2 + hy)
            ln = 5 + spread * 1.5 - droop
            x1, y1 = x0 + sd * math.cos(a) * ln, y0 + math.sin(a) * ln
            c.part(LIMB(x0, y0, x1, y1, 1.4, 1.1), Gl)
            c.dot(x1 - .5, y1 - .5, Gl[5], 1, 1, .9)
    hx, hc = rot(20, 20 + hy)
    c.part(RE(hx, hc, 10, 7.2, tl), C)
    # arms in the belly's lighter tone, so that a raised one stands out from the head
    for sx, (x, y) in ((14, L), (26, R)):
        c.part(LIMB(sx, 28.5, x, y, 1.6, 1.4), B, k=-1)
        if y < 27:  # a raised hand: a little paw at its end
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
