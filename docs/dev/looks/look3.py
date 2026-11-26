"""The engine's third look, the two mixed, beside the other two: every familiar (the five in the
overlay, then the five previews of familiars_next.py) as Classic, Mix and Refined, and the operators
as Classic and Mix.

LOOK 3 (2026-11-26) after a comparison of Classic and Refined, which found Classic's shading
better (pillow tones, deep shadows, near-white lights: volume and punch) and Refined flat and chalky.
The author: "I kinda prefer the default", "mostly the shading"; the refined working eyes "weird".

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/look3.py OUT_DIR
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import look2  # noqa: E402  (puts hub/ and tests/ on the path)
import characters as ch  # noqa: E402
import characters_page  # noqa: E402
import familiars_next  # noqa: E402

TITLE = "Sidetone Character Looks"
INTRO = ("Classic (as the overlay has it), Mix and Refined, frame for frame. The Mix keeps Classic's tones, shading and "
         "motion, lifts the outline so the edges show on the dark glass, and takes Refined's eyes, sparks, sound sign and "
         "lantern. Pick In the List or Inside to see the sizes the overlay scales to by a fraction, then Nearest (today) or Smooth.")
CHANGES = [
    ("From Classic", "The six tones of every color and the pillow shading, one outline tone all round, the held working "
                     "poses and hops, the working eyes (the sprout's sleepy ones too)."),
    ("Outline", "Classic's darkest tone lifted to about 1.6:1 against the glass, in its shadow's hue, kept under the "
                "darkest shadow: the first eight session colors all reach it; four dark ones and dark clothes stay near Classic."),
    ("Pale colors", "Their shadows kept from full strength: no lime under the pale green, no royal blue under the blue."),
    ("Glow", "Refined's, without rings, but fading slower: about as strong as Classic's. The lantern glows round its flame again."),
    ("From Refined", "The sparks when done (two pixels tall, to last at 35 px), the sound sign while listening, wide eyes "
                     "with a catchlight, x and shut eyes in a tone that shows, the lantern's flame under its white eyes."),
]
NAMES = [n.split(",")[0] for n in characters_page.NAMES["familiars"]] + [n.split(",")[0] for n, _, _ in familiars_next.FIGURES]
OPERATORS = characters_page.NAMES["operators"]
LOOKS = [(1, "Classic"), (3, "Mix"), (2, "Refined")]


def main(out: str) -> None:
    base = len(ch.FAMILIARS)
    ch.FAMILIARS.extend(f for _, _, f in familiars_next.FIGURES)  # in this process only
    colors = list(ch.COLORS[:5]) + [c for _, c, _ in familiars_next.FIGURES]
    fam, ops = {}, {}
    try:
        for look, _ in LOOKS:
            fam[look] = [ch.sheet("familiars", k, colors[k], look) for k in range(len(NAMES))]
            if look != 2:
                ops[look] = [ch.sheet("operators", k, ch.COLORS[k], look) for k in range(5)]
    finally:
        del ch.FAMILIARS[base:]
    side = [(f"{NAMES[k]} · {name}", colors[k], fam[look][k]) for k in range(len(NAMES)) for look, name in LOOKS]
    mix = [(NAMES[k], colors[k], fam[3][k]) for k in range(len(NAMES))]
    opside = [(f"{OPERATORS[k]} · {name}", ch.COLORS[k], ops[look][k]) for k in range(5) for look, name in LOOKS if look != 2]
    groups = [
        ("compare", "Side by Side", "Each familiar as Classic, Mix and Refined: the five in the overlay, then the five previews.", side, ch.N),
        ("mix", "Mix", "The Mix alone: the five familiars in the overlay, then the five previews.", mix, ch.N),
        ("operators", "Operators, Side by Side", "The five operators as Classic and Mix: they share the engine, so they change with it.", opside, ch.N),
    ]
    print(look2.page(out, groups, title=TITLE, intro=INTRO, changes=CHANGES))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "look3")
