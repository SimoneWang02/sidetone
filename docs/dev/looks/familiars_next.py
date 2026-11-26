"""Familiars to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. Now a cat and a dog. Put a new figure's drawing here with its row
in FIGURES to preview it beside the live ones, keeping the rules the tests check (feet on row 42
of the 44, every motion through `Frame.wave`, `Frame.cycle` or `Frame.beat` so each row repeats
without a jump).

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402
from characters import ELL, LIMB, POLY, RE, K, WH, Frame, _clamp, _hex, _round, from_oklch, oklch, ramp, tint  # noqa: E402


CAT_PINK = "#f39ab0"  # ear insides and nose
DOG_NOSE = "#2a1c22"
DOG_TONGUE = ramp("#ec4d6c")
BONE = ramp("#efe4c8")


def cat(F: Frame, col: str):
    """Curious: a cat sitting up, ears that turn to every sound, a tail whose tip never stops."""
    s, T, A, V, c = F.s, F.T, F.A, F.V, F.c
    dead = s == "failed"
    base = tint(col, -.25) if dead else col
    L0, C0, h0 = oklch(col)
    pinkish = C0 > .08 and abs((h0 + 180) % 360 - 180) < 35  # pink ears and nose would vanish on it
    C, B = ramp(base), ramp(tint(base, .35))
    P = ramp(tint(base, -.35)) if pinkish else ramp(CAT_PINK)
    tl, hy, eye, pose, paw, ball, meow = 0.0, 0.0, "open", "low", None, None, False
    ear = [0.0, 0.0]  # each ear tip's lift
    back = [0.0, 0.0]  # each ear turned out and down (1: flat to the side)
    spread = 0.0  # both ear tips further out
    look = 0  # the eyes a pixel left and down, at the ball
    tip = F.wave(2)  # the tail tip's sway
    if s == "idle":
        k = F.cycle(4)
        back[1] = .4 if .3 <= k < .36 else 0
        tip = F.wave(2) * 1.5
        if .62 <= k < .75:
            eye = "shut"  # a slow blink
        if .84 <= k:  # a glance aside, the head cocked the other way from listening
            tl = .1 * math.sin((k - .84) / .16 * math.pi)
    if s == "working":
        b = F.beat(1)
        paw = (10.5 - 3 * b, 27 + 4.5 * b)
        ball = (6.2 - 1.2 * F.beat(1, .15), 34.9)
        look = 1
    if s == "speaking":
        hy, spread = -V * 1.2, V * 1.5
        ear = [V * .6, V * .6]
    if s == "needs":
        pose, eye, m = "up", "wide", F.lively
        meow = F.cycle(1) < .4
        if m:  # beckoning beside the left ear, the paw curling down twice a second, the head bobbing
            curl = F.beat(.5)
            paw = (16.5 - 8 * m, 36.6 - (23.6 - 3.5 * curl) * m)
            hy = -1.5 * curl * m
        tip = F.wave(.5) * 1.5 * m
    if s == "done":  # a stretch up, then sitting pleased, the tail round its paws
        pose, eye = "front", "happy"
        ear = [1, 1]
        tip = F.wave(1)
        if A < 1.5:
            c.tall = 1 + .08 * math.sin(A / 1.5 * math.pi)
    if dead:  # dazed: ears half back, the tail limp on the floor
        pose, eye, hy = "limp", "x", 1
        back = [.5, .5]
    if s == "listen":
        eye, tl = "wide", -.2
        ear = [1.5, 1.5]
        back[1] = .3  # the right ear swung out, towards the sound
        tip = F.wave(2) * .5

    def rot(x, y):  # the head tilts about the neck
        dx, dy = x - 20, y - 25
        return 20 + dx * math.cos(tl) - dy * math.sin(tl), 25 + dx * math.sin(tl) + dy * math.cos(tl)

    def tail(pts, r0, r1, z=2):  # one flat tone: shaded bands where it meets the haunch were noise
        for i in range(len(pts) - 1):
            a, b = r0 + (r1 - r0) * i / (len(pts) - 1), r0 + (r1 - r0) * (i + 1) / (len(pts) - 1)
            c.part(LIMB(*pts[i], *pts[i + 1], a, b), C, flat=z, cast=0)
    # the tail: wrapped round the right on the floor with its end curling up, held up in a hook,
    # limp along the floor, or (done) round the front paws, drawn after them
    tail({"low": [(25, 35.5), (30, 36.4), (33.5, 34.5), (35, 31), (34 + tip, 27.5)],
          "up": [(25, 33), (30.5, 31.5), (34, 27.5), (35, 23), (36 + tip * .6, 19.5), (38 + tip, 18.5)],
          "limp": [(25, 35.5), (30, 36.4), (34, 36.7), (37.5, 36.7)],
          "front": [(25, 35.5), (30, 36.8)]}[pose], 1.8, 1.1)
    # the haunches, the body, the chest
    c.part(ELL(13.5, 34.5, 4, 3.6), C, k=-1)
    c.part(ELL(26.5, 34.5, 4, 3.6), C, flat=2, cast=0)
    c.part(ELL(20, 30.5, 7.2, 7.2), C)
    c.part(ELL(20, 29.5, 3.6, 5), B, flat=4, cast=0)
    if paw:  # the left front paw, raised
        c.part(LIMB(15.5, 28.5, *paw, 1.7, 1.5), C)
        c.part(ELL(paw[0], paw[1], 1.9, 1.7), B, flat=4)
    else:
        c.part(ELL(16.5, 36.6, 2.2, 1.6), B)
    c.part(ELL(23.5, 36.6, 2.2, 1.6), B)
    if pose == "front":
        tail([(30, 36.6), (24, 37), (16, 37), (10.5, 36.4), (8, 34.2), (8.6 + tip * .8, 31.6)], 1.5, 1, z=3)
    if ball:
        Y = ramp(_hex(from_oklch(.74, .15, h0 + 180)))  # the session's opposite hue: apart from paw and fur
        c.part(ELL(*ball, 3.2, 3.2), Y)
        k = F.cycle(1)  # its strands roll round as it moves
        for i in range(2):
            c.dot(ball[0] - 2 + _round((k + i / 2) % 1 * 4), ball[1] - 1, Y[1], 1, 3)
    # ears behind the head: tall points, pink inside; turned back out to the sides
    for i, sd in enumerate((-1, 1)):
        e, f = ear[i], back[i]
        tipx, tipy = (20 + sd * (7.5 + spread + f * 5.5), 5.5 - e + f * 7.5)
        o = [rot(20 + sd * 2.5, 13 + hy), rot(tipx, tipy + hy), rot(20 + sd * 9.5, 17 + hy)]
        c.part(POLY(o), C)
        inner = [rot(20 + sd * 4, 13.5 + hy), rot(tipx - sd * .8, tipy + 2.5 + hy), rot(20 + sd * 8, 15.5 + hy)]
        c.part(POLY(inner), P, flat=3, cast=0)
    hx, hc = rot(20, 18 + hy)
    c.part(RE(hx, hc, 9.8, 7.2, tl), C)
    mx, my = rot(20, 21.5 + hy)
    c.part(RE(mx, my, 3.8, 2.3, tl), B, flat=4, cast=0)

    def at(x, y):
        X, Y = rot(x, y + hy)
        return _round(X), _round(Y)
    (e1x, e1y), (e2x, e2y) = at(15 - look, 15.5 + look), at(23 - look, 15.5 + look)
    if e1y == e2y:
        F.eyes([e1x, e2x], e1y, eye, 3)
    else:
        F.eyes([e1x], e1y, eye, 3)
        F.eyes([e2x], e2y, eye, 3)
    for x, y, h in ((17, 11, 2), (19, 10.5, 3), (20, 10.5, 3), (22, 11, 2)):  # tabby stripes
        fx, fy = at(x, y)
        c.dot(fx, fy, C[2], 1, h)
    nx, ny = at(19, 20)
    c.dot(nx, ny, P[3], 2, 1)
    for sd in (-1, 1):  # a whisker a side, slanting out of the cheek's outline, in the fur's light
        for j in range(2):
            wx, wy = at(20 + sd * (10 + j) - (sd < 0), 21 - j)
            c.dot(wx, wy, C[5])
    if s == "speaking" and V > .08 or meow:
        F.mouth(nx + 1, ny + 2, V if s == "speaking" else .45)
    elif dead:
        c.dot(nx - 1, ny + 2, K, 4, 1)
        F.smoke(20, 10)
    else:
        for dx, dy in ((-1, 1), (0, 2), (1, 2), (2, 1)):
            c.dot(nx + dx, ny + dy, K)


def dog(F: Frame, col: str):
    """Devoted: a puppy sitting at your feet, eyes on you, floppy ears, a stub of a tail that wags."""
    s, V, c = F.s, F.V, F.c
    dead = s == "failed"
    base = tint(col, -.3) if dead else col
    C, B = ramp(base), ramp(tint(base, .45))
    eye, tl, hy, wag, perk, mouth, tongue, chew = "open", 0.0, 0.0, 0.0, (0.0, 0.0), 0.0, 0, None
    sit, beg = 0.0, None  # how far it sits up; where its begging paws are
    if s == "idle":  # a slow wag, a breath, one ear twitching once a row
        wag = F.wave(2) * .6
        hy = F.wave(4) * .3
        perk = (.5 if .8 <= F.cycle(4) < .87 else 0.0, 0.0)
    if s == "working":  # a bone across its mouth, chewed
        chew = F.beat(2 / 3)
        hy = .5 + chew * .6
        wag = F.wave(1) * .5
    if s == "speaking":  # quiet, it is the idle dog; the voice lifts its head and swings its tail
        mouth, hy, wag = V, -V, F.wave(1 / 3) * V
    if s == "needs":  # sits up and begs, both paws up at its chest, barking
        bark = F.beat(.5) * F.lively
        eye, sit, mouth, hy = "wide", 1.5, .3 + .4 * bark, -1.5 * bark
        beg = 28.5 - 1.2 * F.wave(.5) * F.lively
        wag = F.wave(1 / 3) * F.lively
    if s == "done":  # two seconds of joy, ears flapping, then a calm wag
        e = _clamp(3 - F.A)
        eye, mouth, tongue = "happy", .5, 1
        wag = F.wave(.5) * e + F.wave(1) * .6 * (1 - e)
        perk = (e * (.35 + .25 * F.wave(.5)),) * 2
    if dead:  # sorry: head hung low, muzzle down, ears hanging long, the tail tucked away
        eye, hy, perk = "shut", 3.0, (-.5, -.5)
    if s == "listen":  # the head tilted, one ear up
        eye, tl, perk = "wide", .2, (.4, 0.0)
        wag = F.wave(1) * .4
    hy -= sit

    def rot(x, y):  # the head tilts about the neck
        dx, dy = x - 20, y - 26
        return 20 + dx * math.cos(tl) - dy * math.sin(tl), 26 + dx * math.sin(tl) + dy * math.cos(tl) + hy

    # the tail, a stub behind the left haunch (the cat's long one curls up on the right)
    if not dead:
        c.part(LIMB(14, 32, 8 + wag * 2.2, 26.5 - abs(wag) * .6, 1.7, 1.3), C, k=-1)
    # back feet poking out at the sides, haunches, the body, the chest
    c.part(ELL(11.5, 36.6, 3, 1.6), C, k=-1)
    c.part(ELL(28.5, 36.6, 3, 1.6), C, k=-1)
    c.part(ELL(13.5, 33.5, 4, 3.8), C, k=-1)
    c.part(ELL(26.5, 33.5, 4, 3.8), C, k=-1)
    c.part(ELL(20, 30.5 - sit / 2, 7, 6.5 + sit / 2), C)
    if beg is None:
        c.part(ELL(20, 28.5, 3.4, 3), B, flat=4, cast=0)
    else:  # sitting up shows the belly, lower than the bib: the paws hang clear of it
        c.part(ELL(20, 32.3, 4.2, 3.8), B, flat=4, cast=0)
    # front legs, flat, each casting a dark line on the body beside it
    for x, z in ((16.5, 4), (23.5, 3)):
        if beg is None:
            c.part(LIMB(x, 28, x, 35.5, 1.7), C, flat=z)
            c.part(ELL(x, 36.6, 2.5, 1.6), B, flat=z + 1)
        else:  # held up at the chest, the paws hanging
            px = x + (-2 if x < 20 else 2)
            c.part(LIMB(px, 23, px, beg - sit, 1.7), C, flat=z)
            c.part(ELL(px, beg - sit + .3, 2.3, 1.8), B, flat=5)
    # the head, round, then the muzzle (pointing down when sorry: shorter, lower)
    hx, hc = rot(20, 17.2)
    c.part(ELL(hx, hc, 9, 7.4), C)
    mx, my = rot(20, 22.6 if dead else 22)
    c.part(ELL(mx, my, 5, 2.7 if dead else 3.3), B, k=1)
    # ears: hung from the sides under a round crown; perk swings their tips out and up
    for i, sd in enumerate((-1, 1)):
        p = perk[i]
        bx, by = rot(20 + sd * 8, 14.3)
        ex, ey = rot(20 + sd * (10.5 + (4 * p if p > 0 else -2 * p)), 24 - p * 9)
        c.part(LIMB(bx, by, ex, ey, 2.2, 2.9), C, flat=2)

    def at(x, y):
        X, Y = rot(x, y)
        return _round(X), _round(Y)
    (e1x, e1y), (e2x, e2y) = at(15, 15), at(23, 15)
    if e1y == e2y:
        F.eyes([e1x, e2x], e1y, eye, 3)
    else:
        F.eyes([e1x], e1y, eye, 3)
        F.eyes([e2x], e2y, eye, 3)
    nx, ny = at(19, 20 if dead else 19)
    c.dot(nx, ny, DOG_NOSE, 3, 2)
    c.dot(nx, ny, WH)
    ax, ay = at(20, 22)
    if mouth > .08:
        F.mouth(ax, ay, mouth)
    elif not dead:
        c.dot(ax, ay - 1, C[0])
        c.dot(ax - 2, ay, C[0], 2, 1)
        c.dot(ax + 1, ay, C[0], 2, 1)
    if tongue:  # hanging out, rimmed in its own dark tone so it shows on a pink dog
        T = DOG_TONGUE
        c.dot(ax - 2, ay + 3, T[0], 1, 2)
        c.dot(ax + 1, ay + 3, T[0], 1, 2)
        c.dot(ax - 1, ay + 5, T[0], 2, 1)
        c.dot(ax - 1, ay + 3, T[3], 2, 2)
        c.dot(ax - 1, ay + 3, T[4])
    if chew is not None:  # the bone, rimmed in the dog's dark tone: it tips as it is chewed
        y0, y1 = ay + .5 - (chew - .5), ay + .5 + (chew - .5)
        for R, w, z in ((C, 1, 0), (BONE, 0, None)):
            c.part(LIMB(15, y0, 25, y1, 1.1 + w), R, flat=z, k=1)
            for x, y in ((13.8, y0), (26.2, y1)):
                for d in (-1.3, 1.3):
                    c.part(ELL(x, y + d, 1.5 + w, 1.4 + w), R, flat=z, k=1)
    if dead:
        F.smoke(20, 13)


# (name, color, drawing) of each figure being previewed
FIGURES: list = [("Cat, curious", "#8AB4FF", cat), ("Dog, devoted", "#FFA24D", dog)]
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
