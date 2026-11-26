"""The engine's second look beside its first: every familiar (the five in the overlay, then the five
previews of familiars_next.py) and the operators, drawn with `characters.LOOK = 1` and then `2`.

LOOK 2 is a pass on what every figure shares, after a pixel-art review (2026-11-26: "charming at
2x and falls apart at 35 px, and most of the damage comes from the engine"). The page also shows
the two sizes the overlay scales to by a fraction (35 px in the list, 66 in the bubble) either as
today, nearest neighbour, which drops rows of pixels so that eyes shimmer, or smoothed; and the
whole-pixel sizes (44, 88) that need neither.

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/look2.py OUT_DIR
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, HERE)
import characters as ch  # noqa: E402
import characters_page  # noqa: E402
import familiars_next  # noqa: E402

TITLE = "Sidetone Look 2"
INTRO = ("The engine's first look (as the overlay has it) and its second, frame for frame. The second: tones built in "
         "OKLCH with an outline that shows on the dark glass, light from the top left with three or four tones a part, a "
         "selective outline, a stepless glow, bright sparks in place of the grey Done beams, Wide eyes a size bigger, "
         "eyes looking down while Working, a small sound sign while Listening, a breath while Speaking, and Working "
         "motions with frames in between. Pick In the List or Inside to see the sizes the overlay scales to by a "
         "fraction, then Nearest (today) or Smooth.")
CHANGES = [
    ("Tones", "Built in OKLCH: the outline about 1.6:1 against the glass (was 1.0 to 1.25 for 16 of the 20 colors), shadows at about 0.7 of the color's strength, lights kept under white, a pale color's top tones kept apart."),
    ("Light", "From the top left, mostly flat across a part, a shadow side on the right and below; no dark ring round every limb."),
    ("Outline", "One rule, the engine's: a tone lighter on the top and left, the darkest below and right. The previews' near-black inner lines follow it."),
    ("Glow, Done", "The glow fades without rings, in a strong tone of its color; the grey beams over the figure are gone, bright sparks rise instead."),
    ("Eyes", "Wide is a pixel wider and taller than open, with a catchlight; x and shut take a tone that shows on the face; the lantern has dark eyes and its flame stays under them."),
    ("Moments", "Listening shows a small sound sign where the ! is; Working looks down, on every figure."),
    ("Motion", "A half-pixel breath in every Speaking row; Working moves in four or more frames, not a two-pose flip; hops ease and land with a squash."),
]
SIZES = [("In the List", 35), ("List, Whole Pixels", 44), ("Inside", 66), ("On the Edge", 88), ("Up Close", 176)]
NAMES = characters_page.NAMES["familiars"] + [n for n, _, _ in familiars_next.FIGURES]


def page(out: str, groups, title: str = TITLE, intro: str = INTRO, changes=CHANGES) -> str:
    """The page of tests/characters_page.py with an introduction, a list of changes and a choice of
    scaling at the fractional sizes (look3.py makes its page with this one too)."""
    path = characters_page.write(out, groups, title=title)
    html = open(path).read()

    def swap(old: str, new: str) -> None:
        nonlocal html
        assert old in html, old  # tests/characters_page.py's page changed: update this one
        html = html.replace(old, new)
    swap(characters_page.PAGE.split("<header>")[1].split("</header>")[0].replace("<h1>Sidetone Characters</h1>", f"<h1>{title}</h1>"),
         f"<h1>{title}</h1><p>{intro}</p>")
    swap('<div class="group"><button type="button" id="replay">',
         '<div class="group" id="scaling" role="group" aria-label="Fractional sizes"><span>35 and 66 px</span></div>\n'
         '  <div class="group"><button type="button" id="replay">')
    swap('const SIZES=[["In the List",35],["Inside",66],["On the Edge",88],["Up Close",176]];',
         "const SIZES=" + str([[n, z] for n, z in SIZES]).replace("'", '"') + ";")
    swap('SIZES.forEach(([n,z])=>button(el("sizes"),n,z===size,()=>{size=z;build()}));',
         'SIZES.forEach(([n,z])=>button(el("sizes"),n,z===size,()=>{size=z;build()}));\n'
         'let smooth=false;[["Nearest (Today)",false],["Smooth",true]].forEach(([n,v])=>button(el("scaling"),n,v===smooth,()=>{smooth=v;build()}));')
    # nearest neighbour at whole multiples of the cell; at a fraction, as the toggle says
    swap("g.imageSmoothingEnabled=c.smooth;", "g.imageSmoothingEnabled=c.smooth||(smooth&&(c.cv.width%c.cell)!==0);")
    swap('<p class="note">Sizes are the overlay\'s:',
         '<ul class="changes">' + "".join(f"<li><b>{a}.</b> {b}</li>" for a, b in changes) + '</ul>\n<p class="note">Sizes are the overlay\'s:')
    swap("Up Close is twice the edge.", "Up Close is twice the edge. List, Whole Pixels is the list at the drawing's own size (44), as a proposal: no fraction, nothing to smooth.")
    swap(".note{", ".changes{margin:0;padding-left:20px;color:var(--soft);max-width:80ch;display:grid;gap:4px}.changes b{color:var(--fg)}\n.note{")
    with open(path, "w") as f:
        f.write(html)
    return path


def main(out: str) -> None:
    base = len(ch.FAMILIARS)
    ch.FAMILIARS.extend(f for _, _, f in familiars_next.FIGURES)  # in this process only
    colors = list(ch.COLORS[:5]) + [c for _, c, _ in familiars_next.FIGURES]
    was = ch.LOOK
    drawn = {}
    try:
        for look in (1, 2):
            ch.LOOK = look
            drawn["familiars", look] = [(NAMES[k], colors[k], ch.sheet("familiars", k, colors[k])) for k in range(base + len(familiars_next.FIGURES))]
            drawn["operators", look] = [(characters_page.NAMES["operators"][k], ch.COLORS[k], ch.sheet("operators", k, ch.COLORS[k])) for k in range(5)]
    finally:
        ch.LOOK = was
        del ch.FAMILIARS[base:]

    def pairs(style):
        return [(f"{name}, {when}", color, data) for (name, color, a), (_, _, b) in zip(drawn[style, 1], drawn[style, 2])
                for when, data in (("Before", a), ("After", b))]
    groups = [
        ("compare", "Familiars, Side by Side", "Each familiar before (Look 1, the overlay today) and after (Look 2): the five in the overlay, then the five previews.", pairs("familiars"), ch.N),
        ("before", "Before", "Look 1: the familiars as the overlay draws them now, and the five previews.", drawn["familiars", 1], ch.N),
        ("after", "After", "Look 2: the same familiars with the engine's second look.", drawn["familiars", 2], ch.N),
        ("operators", "Operators, Side by Side", "The five operators, before and after: they share the engine, so they change with it.", pairs("operators"), ch.N),
    ]
    print(page(out, groups))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "look2")
