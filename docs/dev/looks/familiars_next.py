"""Familiars to come, as a preview: drawn with the overlay's own pixel engine (hub/characters.py),
but not yet among its figures. Empty: the dragon redrawn, the last previewed here, moved
into the overlay. Put a new figure's drawing here with its row in FIGURES to preview it beside
the live ones, keeping the rules the tests check (feet on row 42 of the 44, every motion through
`Frame.wave`, `Frame.cycle` or `Frame.beat` so each row repeats without a jump).

Run: ~/.local/share/kokoro/venv/bin/python -I docs/dev/looks/familiars_next.py OUT_DIR
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import characters as ch  # noqa: E402


FIGURES: list = []  # (name, color, drawing) of each figure being previewed
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
