"""Characters beside the bubble: the drawing, the sheet the overlay reads, and what the hub sends.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests
"""
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import base  # noqa: E402
import characters  # noqa: E402
from hub import Config, Hub  # noqa: E402
from state import COLORS  # noqa: E402
from tts import NullEngine  # noqa: E402

MOMENTS = ("idle", "working", "speaking", "needs", "done", "failed", "listen")


def opaque(cell) -> int:
    return sum(1 for i in range(3, len(cell), 4) if cell[i] > 128)


def unpng(data: bytes):
    """Width, height and RGBA of a PNG this module wrote (8-bit RGBA, no filters)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    pos, idat = 8, b""
    while pos < len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            idat += data[pos + 8:pos + 8 + size]
        pos += 12 + size
    raw = zlib.decompress(idat)
    rgba = b"".join(raw[y * (width * 4 + 1) + 1:(y + 1) * (width * 4 + 1)] for y in range(height))
    return width, height, rgba


def cell_of(sheet: bytes, row: str, column: int) -> bytes:
    width, _, rgba = unpng(sheet)
    r = characters.LAYOUT["rows"][row][0]
    n = characters.N
    return b"".join(rgba[((r * n + y) * width + column * n) * 4:((r * n + y) * width + (column + 1) * n) * 4] for y in range(n))


class Drawing(unittest.TestCase):
    styles = characters.STYLES
    def test_every_figure_draws_every_moment(self):
        for style in self.styles:
            for kind in range(characters.kinds(style)):
                for moment in MOMENTS:
                    cell = characters.frame(style, kind, COLORS[kind], moment, 0.5, 0.5, 0.6)
                    self.assertEqual(len(cell), characters.cell(style) ** 2 * 4)
                    self.assertGreater(opaque(cell), 150, (style, kind, moment))

    def test_the_same_moment_is_drawn_the_same_every_time(self):
        a = characters.frame("operators", 2, COLORS[2], "needs", 1.0, 1.0, 0)
        b = characters.frame("operators", 2, COLORS[2], "needs", 1.0, 1.0, 0)
        self.assertEqual(a, b)

    def test_a_louder_voice_opens_the_mouth_wider(self):
        quiet = characters.frame("familiars", 1, COLORS[1], "speaking", 0.5, 0.5, 0.0)
        loud = characters.frame("familiars", 1, COLORS[1], "speaking", 0.5, 0.5, 0.95)
        self.assertNotEqual(quiet, loud)

    def test_each_session_keeps_its_figure_by_its_color(self):
        self.assertEqual(characters.kinds("familiars"), 10)
        self.assertEqual(characters.kinds("operators"), 5)
        self.assertEqual([characters.kind_of(c, 10) for c in COLORS[:11]], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0])
        self.assertEqual([characters.kind_of(c, 5) for c in COLORS[:6]], [0, 1, 2, 3, 4, 0])
        self.assertEqual(characters.kind_of("#8ab4ff", 10), 0)  # the color as the config may write it
        own = characters.kind_of("#123456", 10)
        self.assertEqual(characters.kind_of("#123456", 10), own)
        self.assertIn(own, range(10))
        # by color, the pick the hub has always made: the first five colors keep their five figures
        for style in ("familiars", "operators"):
            self.assertEqual([characters.pick(style, c, "any-session") for c in COLORS[:5]], [0, 1, 2, 3, 4])
        self.assertEqual(characters.pick("familiars", COLORS[6], "s"), 6)

    def test_at_random_a_session_keeps_one_figure_for_its_life(self):
        # overlay.character_pick "random"
        ids = [f"5f0c{i:04x}-1a2b-4c3d-8e9f-{i * 7919:012x}" for i in range(140)]
        for style, count in (("familiars", 10), ("operators", 5)):
            got = [characters.pick(style, COLORS[0], sid, "random") for sid in ids]
            self.assertEqual(got, [characters.pick(style, COLORS[0], sid, "random") for sid in ids])  # the same every time
            self.assertEqual(got, [characters.pick(style, COLORS[3], sid, "random") for sid in ids])  # whatever its color
            self.assertEqual(set(got), set(range(count)))  # every figure comes up
            self.assertLess(max(got.count(k) for k in range(count)), len(ids) / count * 1.8)  # none much more than the others
        self.assertEqual(characters.pick("familiars", COLORS[2], "", "random"), 2)  # no id yet: by its color

    def test_nothing_is_cut_off_at_the_top_or_the_sides(self):
        # Nothing is cut: leaves and hair stay inside the cell.
        for style in self.styles:
            n = characters.cell(style)
            edges = [(x, 0) for x in range(n)] + [(0, y) for y in range(n)] + [(n - 1, y) for y in range(n)]
            for kind in range(characters.kinds(style)):
                for name, count in characters.ROWS:
                    s, t0, a0, v = characters._moment(name)
                    for i in (0, count // 3, 2 * count // 3):
                        cell = characters.frame(style, kind, COLORS[kind], s, t0 + i / characters.FPS, a0 + i / characters.FPS, v)
                        self.assertFalse(any(cell[(y * n + x) * 4 + 3] > 40 for x, y in edges), (style, kind, name, i))

    def test_the_sketch_is_one_operator_in_the_session_color(self):
        # The sketch: one figure for all, the scarf in the session's color.
        def colored(cell, color):
            r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            return sum(1 for i in range(0, len(cell), 4) if cell[i + 3] > 200 and abs(cell[i] - r) + abs(cell[i + 1] - g) + abs(cell[i + 2] - b) < 30)
        blue = characters.frame("sketch", 0, COLORS[0], "idle", 0, 0, 0)
        orange = characters.frame("sketch", 1, COLORS[1], "idle", 0, 0, 0)
        self.assertGreater(colored(blue, COLORS[0]), 300)
        self.assertEqual(colored(blue, COLORS[1]), 0)
        self.assertGreater(colored(orange, COLORS[1]), 300)

    def test_the_sketch_has_smooth_edges(self):
        cell = characters.frame("sketch", 0, COLORS[0], "speaking", 0.5, 0.5, 0.6)
        between = sum(1 for i in range(3, len(cell), 4) if 20 < cell[i] < 235)
        self.assertGreater(between, 300)  # lines fade at their edges, not whole pixels

    def test_every_row_repeats_without_a_jump(self):
        # The overlay repeats each row (needs you and done go on into their _hold row): a motion
        # that does not go round a whole number of times in it jumps where it starts again. The
        # frame one step past a row's end must be the frame shown next, drawn as the sheet draws
        # it (the operators' hair following the head a moment late).
        def changed(a, b):
            return sum(1 for i in range(0, len(a), 4) if sum(abs(a[i + j] - b[i + j]) for j in range(4)) > 24)
        for style in [s for s in self.styles if s != "sketch"]:
            for kind in range(characters.kinds(style)):
                for name, count in characters.ROWS:
                    nxt = name + "_hold" if name in ("needs", "done") else name
                    if style == "familiars":  # nothing carried from frame to frame: just the two frames
                        s, t0, a0, v = characters._moment(name)
                        end = characters.frame(style, kind, COLORS[kind], s, t0 + count / characters.FPS, a0 + count / characters.FPS, v)
                    else:
                        end = list(characters.row_frames(style, kind, COLORS[kind], name, extra=1))[-1]
                    start = next(characters.row_frames(style, kind, COLORS[kind], nxt))
                    self.assertEqual(changed(end, start), 0, (style, kind, name))

    def test_feet_stay_on_the_ground(self):
        # No jumping: the window is cut at the edge the figure stands on. Every figure stands on
        # the same row: two above the cell's bottom (the overlay puts those below the edge), four
        # in the sketch's cells of twice the size.
        for style in self.styles:
            n = characters.cell(style)
            floor = n - 2 * n // characters.N
            for kind in range(characters.kinds(style)):
                for name, count in characters.ROWS:
                    s, t0, a0, v = characters._moment(name)
                    for i in range(0, count, 4):
                        cell = characters.frame(style, kind, COLORS[kind], s, t0 + i / characters.FPS, a0 + i / characters.FPS, v)
                        low = next(y for y in range(n - 1, -1, -1) if any(a > 128 for a in cell[y * n * 4 + 3:(y + 1) * n * 4:4]))
                        self.assertEqual(low, floor, (style, kind, name, i))

    def test_no_blink_on_the_idle_rows_first_frame(self):
        # The list shows a row's first frame when nothing moves: shut eyes there look asleep. The
        # eyes' white shine is all there at frame 0, as in a frame with no blink in it.
        def shine(cell):
            return sum(1 for i in range(0, len(cell), 4) if cell[i + 3] > 200 and bytes(cell[i:i + 3]) == bytes(characters.WH))
        for kind in range(characters.kinds("familiars")):
            first, later = (characters.frame("familiars", kind, COLORS[kind], "idle", t, t, 0) for t in (0, 1.0))
            self.assertGreaterEqual(shine(first), shine(later), kind)

    def test_needs_you_settles(self):
        # The big motions of needs you play in its first five seconds; held, only the mark bobs.
        def figure(cell):  # the cell without the mark's corner
            n = characters.N
            return bytes(cell[(y * n + x) * 4 + 3] > 128 for y in range(n) for x in range(n) if not (x >= 31 and y < 20))
        for style in self.styles:
            if style == "sketch":
                continue
            for kind in range(characters.kinds(style)):
                held = [characters.frame(style, kind, COLORS[kind], "needs", 6 + i / 4, 6 + i / 4, 0) for i in range(4)]
                moved = max(sum(a != b for a, b in zip(figure(held[0]), figure(h))) for h in held[1:])
                self.assertLess(moved, 40, (style, kind))

    def test_the_shellback_is_not_green_on_green(self):
        # On a green session color its face and legs are tan, so they do not merge with the shell.
        self.assertTrue(characters._greenish("#0CC006"))
        self.assertTrue(characters._greenish("#B9F27C"))
        self.assertFalse(characters._greenish("#7FDBCA"))  # the teal it gets first keeps its green face
        self.assertFalse(characters._greenish("#8AB4FF"))
        skin = characters.ramp(characters.SHELL_SKIN[True][0])[3]
        tan = characters.frame("familiars", 3, "#0CC006", "idle", 0, 0, 0)
        self.assertTrue(any(bytes(tan[i:i + 3]) == bytes(skin) for i in range(0, len(tan), 4)))

    def test_shadows_of_skin_do_not_turn_red(self):
        r, g, b = characters.ramp("#f2c9a4")[1]
        self.assertGreater(g / r, 0.55)  # a warm brown, not a red


class Sheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = characters.sheet("familiars", 3, COLORS[3])

    def test_it_is_a_png_with_a_row_for_each_moment(self):
        width, height, rgba = unpng(self.sheet)
        self.assertEqual((width, height), (characters.WIDTH, characters.HEIGHT))
        self.assertEqual(len(rgba), width * height * 4)
        self.assertEqual(sorted(characters.LAYOUT["rows"]), sorted(name for name, _ in characters.ROWS))

    def test_every_frame_of_every_row_is_drawn(self):
        for name, count in characters.ROWS:
            for column in range(count):
                self.assertGreater(opaque(cell_of(self.sheet, name, column)), 150, (name, column))

    def test_needs_you_holds_up_its_mark_and_done_settles(self):
        def gold(cell):  # the mark's yellow, in the top right corner
            return sum(1 for y in range(characters.OFF, characters.OFF + 14) for x in range(30, 40)
                       if cell[(y * 40 + x) * 4 + 3] > 200 and cell[(y * 40 + x) * 4] > 220 and cell[(y * 40 + x) * 4 + 2] < 120)
        self.assertGreater(gold(cell_of(self.sheet, "needs", 0)), 6)
        self.assertGreater(gold(cell_of(self.sheet, "needs_hold", 0)), 6)
        self.assertEqual(gold(cell_of(self.sheet, "done_hold", 0)), 0)

    def test_the_sheet_is_the_same_each_time_it_is_drawn(self):
        self.assertEqual(characters.sheet("familiars", 3, COLORS[3]), self.sheet)


class SketchSheet(unittest.TestCase):
    def test_its_cells_are_twice_as_large_and_every_frame_is_drawn(self):
        data = characters.sheet("sketch", 2, COLORS[2])
        width, height, rgba = unpng(data)
        n = characters.cell("sketch")
        self.assertEqual(n, 2 * characters.N)
        self.assertEqual((width, height), (characters.WIDTH * 2, characters.HEIGHT * 2))  # the overlay reads the cell from the height
        for name, count in characters.ROWS:
            r = characters.LAYOUT["rows"][name][0]
            for column in range(count):
                cell = b"".join(rgba[((r * n + y) * width + column * n) * 4:((r * n + y) * width + (column + 1) * n) * 4] for y in range(n))
                self.assertGreater(opaque(cell), 1000, (name, column))


class Sheets(unittest.TestCase):
    def test_a_sheet_is_drawn_once_in_the_background_then_named(self):
        folder = tempfile.mkdtemp(prefix="cs-sprites-")
        ready = threading.Event()
        sheets = characters.Sheets(folder, windows=lambda p: "C:\\x\\" + os.path.basename(p), done=ready.set)
        self.assertEqual(sheets.path("familiars", COLORS[0]), "")  # being drawn
        self.assertTrue(ready.wait(30))
        path = sheets.path("familiars", COLORS[0])
        self.assertTrue(path.startswith("C:\\x\\familiars-0-8ab4ff-") and path.endswith(".png"), path)
        self.assertEqual(len(os.listdir(folder)), 1)  # nothing left half written
        self.assertEqual(sheets.path("none", COLORS[0]), "")
        self.assertEqual(sheets.path("familiars", ""), "")

    def test_each_look_has_its_own_sheet(self):
        folder = tempfile.mkdtemp(prefix="cs-sprites-")
        sheets = characters.Sheets(folder)
        names = {sheets.name("familiars", 0, COLORS[0], look) for look in (1, 2, 3)}
        self.assertEqual(len(names), 3)
        self.assertIn("-look3-", sheets.name("familiars", 0, COLORS[0], 3))
        was = characters.LOOK
        drawn = {characters.sheet("familiars", 1, COLORS[1], look) for look in (1, 2, 3)}
        self.assertEqual(len(drawn), 3)
        self.assertEqual(characters.LOOK, was)
        sheets._busy = True  # nothing drawn: only what is asked for
        sheets.path("sketch", COLORS[0], 3)  # the sketch has one look: its first
        sheets.path("familiars", COLORS[0], 3)
        self.assertEqual([key[3] for key in sheets._wanted[:2]], [1, 3])

    def test_each_strength_has_its_own_sheet(self):
        sheets = characters.Sheets(tempfile.mkdtemp(prefix="cs-sprites-"))
        sheets._busy = True  # nothing drawn: only what is asked for
        for strength in (None, 60, 60.2, 400, "strong"):  # the setting as config.json may hold it
            sheets.path("familiars", COLORS[0], strength=strength)
            sheets.path("sketch", COLORS[0], strength=strength)  # lines in the session's own color: one sheet
        self.assertEqual([key[3:] for key in sheets._wanted], [(3, 25), (1, 100), (3, 60), (3, 100)])
        self.assertEqual(len({sheets.name(*key) for key in sheets._wanted}), 4)

    def test_the_kind_given_names_the_sheet(self):
        # the hub hands the figure it picked (by color, or at random by the session's id)
        sheets = characters.Sheets(tempfile.mkdtemp(prefix="cs-sprites-"))
        sheets._busy = True  # nothing drawn: only what is asked for
        sheets.path("familiars", COLORS[0], kind=6)
        sheets.path("familiars", COLORS[0])
        sheets.path("operators", COLORS[0], kind=6)  # past the operators' five: wrapped round
        self.assertEqual([key[:3] for key in sheets._wanted], [("familiars", 6, COLORS[0]), ("familiars", 0, COLORS[0]),
                                                               ("operators", 1, COLORS[0])])

    def test_a_sheet_already_on_disk_is_not_drawn_again(self):
        folder = tempfile.mkdtemp(prefix="cs-sprites-")
        first = characters.Sheets(folder)
        name = first.name("operators", characters.kind_of(COLORS[1], 5), COLORS[1])
        with open(name, "wb") as f:
            f.write(b"drawn before")
        again = characters.Sheets(folder, done=lambda: self.fail("drawn again"))
        self.assertEqual(again.path("operators", COLORS[1]), name)


class Look2:
    """The same checks with the engine's second look (characters.LOOK = 2), put back afterwards:
    the look is chosen by one constant, and every look must keep every rule."""
    look = 2

    @classmethod
    def setUpClass(cls):
        cls.was = characters.LOOK
        characters.LOOK = cls.look
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        characters.LOOK = cls.was
        super().tearDownClass()


class DrawingLook2(Look2, unittest.TestCase):
    styles = ("familiars", "operators")  # the sketch is drawn apart from the engine and its looks
    test_every_figure_draws_every_moment = Drawing.test_every_figure_draws_every_moment
    test_nothing_is_cut_off_at_the_top_or_the_sides = Drawing.test_nothing_is_cut_off_at_the_top_or_the_sides
    test_every_row_repeats_without_a_jump = Drawing.test_every_row_repeats_without_a_jump
    test_feet_stay_on_the_ground = Drawing.test_feet_stay_on_the_ground
    test_shadows_of_skin_do_not_turn_red = Drawing.test_shadows_of_skin_do_not_turn_red
    test_a_louder_voice_opens_the_mouth_wider = Drawing.test_a_louder_voice_opens_the_mouth_wider


class SheetLook2(Look2, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sheet = characters.sheet("familiars", 3, COLORS[3])

    test_needs_you_holds_up_its_mark_and_done_settles = Sheet.test_needs_you_holds_up_its_mark_and_done_settles


class Look3(Look2):
    """LOOK 3, the two mixed (2026-11-26): Classic's tones and motion, Refined's eyes and signs."""
    look = 3


class DrawingLook3(Look3, DrawingLook2):
    pass


class SheetLook3(Look3, SheetLook2):
    pass


class Look3Mix(Look3, unittest.TestCase):
    def test_the_tones_are_classic_with_an_outline_that_shows(self):
        # The comparison of 2026-11-26: Classic's shading has the volume and punch; its outline
        # was 1.0 to 1.25:1 against the glass for most colors.
        glass = characters.luminance(characters.GLASS)
        for color in COLORS + characters.SKIN + ["#3a3f58", "#fff3df"]:
            R = characters.ramp(color)
            characters.LOOK = 1
            classic = characters.ramp(color)
            characters.LOOK = 3
            self.assertEqual(R[3:], classic[3:], color)  # the color and its lights as Classic's
            for t in R[:3]:  # the shadows a little over the color's own strength, not HSL's full strength
                self.assertLess(characters.oklch(t)[1], characters.oklch(color)[1] * 1.2 + .03, color)
            L = [characters.oklch(t)[0] for t in R]
            self.assertLessEqual(L[0], L[1], color)  # the outline no lighter than any shadow
            if color in COLORS[:8]:  # the colors handed out first: the darkest shadow leaves room
                self.assertGreater((characters.luminance(R[0]) + .05) / (glass + .05), 1.5, color)
        # pale colors' shadows not at full strength: no lime under a pale green, no royal blue
        for color, tone in (("#DAF0B8", 1), ("#8AB4FF", 1)):
            self.assertLess(characters.oklch(characters.ramp(color)[tone])[1], .2, color)

    def test_a_figure_wears_its_color_calmer(self):
        # The author, three times on 2026-11-26: a figure filled with its session's color is "too
        # saturated". Measured before: a pink's shadows at a chroma of .28, a green's lighter and
        # stronger than its body.
        for color in COLORS:
            R = [characters.oklch(t) for t in characters.ramp(characters.calm(color))]
            self.assertLess(max(C for _, C, _ in R), .19, color)
            self.assertLess(R[2][0], R[3][0], color)  # a shadow darker than the body
            hue = (characters.oklch(characters.calm(color))[2] - characters.oklch(color)[2] + 180) % 360 - 180
            self.assertLess(abs(hue), 4, color)  # still its session's color
        self.assertEqual(characters.calm("#7FDBCA"), "#7fdbca")  # a soft color stays as it is
        self.assertLess(characters.oklch(characters.calm("#B9F27C"))[0], .85)  # a light green: leaf, not lime
        self.assertGreater(characters.oklch(characters.calm("#F9E27D"))[0], .9)  # a yellow stays light
        soft, own = (characters.sheet("familiars", 6, COLORS[7], strength=k) for k in (0, 100))
        self.assertNotEqual(soft, own)
        self.assertEqual(characters.STRENGTH, 25)
        characters.STRENGTH = 100
        try:
            self.assertEqual(characters.calm("#ED44EC"), "#ED44EC")  # the color itself
        finally:
            characters.STRENGTH = 25

    def test_it_moves_as_classic_while_working(self):
        # Held poses, not the eased cycles of LOOK 2: the figure's own pixels where Classic's are.
        def solid(cell):
            return bytes(cell[i] > 200 for i in range(3, len(cell), 4))
        for style, kinds in (("familiars", range(1, 7)), ("operators", range(5))):
            for kind in kinds:
                for i in range(0, 24, 3):
                    t = i / characters.FPS
                    mix = characters.frame(style, kind, COLORS[kind], "working", t, t, 0)
                    characters.LOOK = 1
                    classic = characters.frame(style, kind, COLORS[kind], "working", t, t, 0)
                    characters.LOOK = 3
                    self.assertEqual(solid(mix), solid(classic), (style, kind, i))

    def test_the_lantern_glows_about_as_much_as_classic(self):
        # The author found the refined lantern dull; done is where its glow is widest.
        def glow(look):
            characters.LOOK = look
            cell = characters.frame("familiars", 0, COLORS[0], "done", 5.0, 5.0, 0)
            characters.LOOK = 3
            return sum(cell[i] for i in range(3, len(cell), 4) if 0 < cell[i] < 200)
        self.assertGreater(glow(3), glow(1) * .8)
        self.assertGreater(glow(3), glow(2) * 2)


class Look2Ramps(Look2, unittest.TestCase):
    def test_the_outline_shows_on_the_glass_and_the_tones_stay_apart(self):
        # The review, 2026-11-26: the outline tone was 1.00 to 1.25 against the glass for 16 of
        # the 20 colors, shadows went to full saturation, pale colors lost their top tones.
        glass = characters.luminance(characters.GLASS)
        for color in COLORS + characters.SKIN + ["#3a3f58", "#3a1a22", "#fff3df"]:
            R = characters.ramp(color)
            L = [characters.oklch(t)[0] for t in R]
            for a, b in zip(L, L[1:]):
                self.assertGreater(b - a, .03, (color, L))  # six tones, each its own
            if color in COLORS:
                self.assertGreater((characters.luminance(R[0]) + .05) / (glass + .05), 1.5, color)
                self.assertLess(max(R[5]) / 255 + min(R[5]) / 255, 1.92, color)  # highlights under white
                for t in R[:3]:  # shadows not at full saturation
                    self.assertLess((max(t) - min(t)) / 255, .75, (color, t))


class PreviewsBothLooks(unittest.TestCase):
    """The previews in docs/dev/looks/familiars_next.py keep the rules too, in every look."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "docs", "dev", "looks"))
        import familiars_next
        # A hub of an earlier test may still be drawing a sheet, and a sheet sets LOOK back as it
        # ends: in the middle of this test, that drew a row's end and its start in two looks.
        for thread in threading.enumerate():
            if thread.name == "characters":
                thread.join()
        cls.was, cls.base = characters.LOOK, len(characters.FAMILIARS)
        characters.FAMILIARS.extend(f for _, _, f in familiars_next.FIGURES)
        cls.colors = [c for _, c, _ in familiars_next.FIGURES]

    @classmethod
    def tearDownClass(cls):
        del characters.FAMILIARS[cls.base:]
        characters.LOOK = cls.was

    def test_feet_edges_and_rows(self):
        n = characters.N
        edges = [(x, 0) for x in range(n)] + [(0, y) for y in range(n)] + [(n - 1, y) for y in range(n)]
        for look in (1, 2, 3):
            characters.LOOK = look
            for i, color in enumerate(self.colors):
                kind = self.base + i
                for name, count in characters.ROWS:
                    s, t0, a0, v = characters._moment(name)
                    for f in range(0, count, 3):
                        cell = characters.frame("familiars", kind, color, s, t0 + f / characters.FPS, a0 + f / characters.FPS, v)
                        low = next(y for y in range(n - 1, -1, -1) if any(a > 128 for a in cell[y * n * 4 + 3:(y + 1) * n * 4:4]))
                        self.assertEqual(low, n - 2, (look, kind, name, f))
                        self.assertFalse(any(cell[(y * n + x) * 4 + 3] > 40 for x, y in edges), (look, kind, name, f))
                    nxt = name + "_hold" if name in ("needs", "done") else name
                    end = characters.frame("familiars", kind, color, s, t0 + count / characters.FPS, a0 + count / characters.FPS, v)
                    start = next(characters.row_frames("familiars", kind, color, nxt))
                    jump = sum(1 for j in range(0, len(end), 4) if sum(abs(end[j + k] - start[j + k]) for k in range(4)) > 24)
                    self.assertEqual(jump, 0, (look, kind, name))


class HubRows(unittest.TestCase):
    def make(self, character):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        overlay = {"character": character}
        cfg = Config(run=self.tmp, state=self.tmp, engine="null", usage_shown=False,
                     mute_file=os.path.join(self.tmp, "voice-off"), sessions_dir=os.path.join(self.tmp, "claude-sessions"))
        cfg.overlay.update(overlay)
        hub = Hub(cfg, NullEngine(0.0))
        self.addCleanup(hub.speech.close)
        sent = []
        hub.overlay = type("Window", (), {"send": lambda self, m: sent.append(m), "reconfigure": lambda self: None})()
        hub.terminals.write = lambda tty, data: True
        hub.on_event({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/tmp/project-a"})
        return hub, sent

    def rows(self, sent):
        states = [m for m in sent if m.get("type") == "state"]
        return states[-1]

    def test_with_no_character_the_rows_name_no_sheet(self):
        hub, sent = self.make("none")
        hub.publish()
        state = self.rows(sent)
        self.assertEqual([r["sprite"] for r in state["sessions"]], [""])
        self.assertEqual(state["sprite_layout"], characters.LAYOUT)

    def test_at_random_the_figure_follows_the_session_id(self):
        hub, sent = self.make("familiars")
        hub.sheets._busy = True  # nothing drawn: only what is asked for
        hub.publish()
        hub.cfg.overlay["character_pick"] = "random"
        hub.publish()
        by_color, by_id = characters.kind_of(hub.sessions.by_id["s1"].color, 7), characters.pick("familiars", "", "s1", "random")
        self.assertEqual([key[1] for key in hub.sheets._wanted], list(dict.fromkeys([by_color, by_id])))

    def test_the_figure_is_drawn_at_the_strength_set(self):
        hub, sent = self.make("familiars")
        hub.sheets._busy = True  # nothing drawn: only what is asked for
        hub.publish()
        hub.cfg.overlay["character_strength"] = 70
        hub.publish()
        self.assertEqual([key[4] for key in hub.sheets._wanted], [25, 70])

    def test_a_character_reaches_the_overlay_once_drawn(self):
        hub, sent = self.make("familiars")
        hub.publish()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not self.rows(sent)["sessions"][0]["sprite"]:
            time.sleep(0.05)
        path = self.rows(sent)["sessions"][0]["sprite"]
        self.assertTrue(path.endswith(".png") and os.path.isfile(path), path)
        self.assertIn(os.path.join(self.tmp, "characters"), path)


def _ev(event, **extra):
    return {"hook_event_name": event, "session_id": "s1", "cwd": "/tmp/project-a", **extra}


class Companions(unittest.TestCase):
    """A session's subagents as small companions (`overlay.character_agents`), from the events
    as a real session sent them (docs/dev/facts.md, "What the hooks say about subagents")."""
    rows = HubRows.rows

    def make(self, on=True, character="familiars"):
        hub, sent = HubRows.make(self, character)
        hub.sheets._busy = True  # no sheet is drawn: only the rows matter here
        hub.cfg.overlay["character_agents"] = on
        return hub, sent

    def start(self, hub, aid, task):
        hub.on_event(_ev("PreToolUse", tool_name="Agent", tool_input={"description": task, "subagent_type": "general-purpose"}))
        hub.on_event(_ev("SubagentStart", agent_id=aid, agent_type="general-purpose"))
        hub.on_event(_ev("PostToolUse", tool_name="Agent", tool_input={"description": task},
                         tool_response={"isAsync": True, "status": "async_launched", "agentId": aid, "description": task}))

    def shown(self, hub, sent):
        hub.publish()
        row = self.rows(sent)["sessions"][0]
        return row["agents"], row["agents_more"]

    def test_off_for_a_new_install_and_with_no_character(self):
        import overlay
        self.assertIs(overlay.DEFAULTS["character_agents"], False)
        for on, character in ((False, "familiars"), (True, "none")):
            hub, sent = self.make(on, character)
            self.start(hub, "a1", "Alpha task")
            self.assertEqual(self.shown(hub, sent), ([], 0))

    def test_one_for_each_that_runs_and_a_cheer_when_it_finishes(self):
        hub, sent = self.make()
        for aid, task in (("a1", "Alpha task"), ("a2", "Beta task"), ("a3", "Gamma task")):
            self.start(hub, aid, task)
        self.assertEqual(self.shown(hub, sent), ([["a1", "Alpha task", "working"], ["a2", "Beta task", "working"],
                                                  ["a3", "Gamma task", "working"]], 0))
        # What one of them does is the session's too, and its turn ends while they run on.
        hub.on_event(_ev("PreToolUse", tool_name="Bash", tool_input={"command": "sleep 4"}, agent_id="a3", agent_type="general-purpose"))
        hub.on_event(_ev("Stop", last_assistant_message="Launched.", background_tasks=[
            {"id": aid, "type": "subagent", "status": "running", "description": "x"} for aid in ("a1", "a2", "a3")]))
        # Claude Code's own agent after each turn: no start, no type.
        hub.on_event(_ev("SubagentStop", agent_id="a9", agent_type="", last_assistant_message="is it done yet?"))
        self.assertEqual(len(self.shown(hub, sent)[0]), 3)
        hub.on_event(_ev("SubagentStop", agent_id="a3", agent_type="general-purpose", last_assistant_message="gamma"))
        self.assertEqual([a[2] for a in self.shown(hub, sent)[0]], ["working", "working", "done"])
        hub.sessions.by_id["s1"].agents["a3"].done -= base.AGENT_CHEER  # it has cheered
        self.assertEqual([a[0] for a in self.shown(hub, sent)[0]], ["a1", "a2"])

    def test_three_stand_there_and_the_rest_are_counted(self):
        hub, sent = self.make()
        for n in range(5):
            self.start(hub, f"a{n}", f"Task {n}")
        agents, more = self.shown(hub, sent)
        self.assertEqual(([a[0] for a in agents], more), (["a0", "a1", "a2"], 2))
        hub.on_event(_ev("SubagentStop", agent_id="a0", agent_type="general-purpose"))
        hub.sessions.by_id["s1"].agents["a0"].done -= base.AGENT_CHEER
        agents, more = self.shown(hub, sent)
        self.assertEqual(([a[0] for a in agents], more), (["a1", "a2", "a3"], 1))  # the next one steps up

    def test_one_that_was_stopped_goes_when_the_turn_ends(self):
        # Stopped by Claude or by hand it sends no SubagentStop: the next Stop lists what runs.
        hub, sent = self.make()
        self.start(hub, "a1", "Step walker")
        self.start(hub, "a2", "Quick look")
        hub.on_event(_ev("Stop", last_assistant_message="x", background_tasks=[
            {"id": "a2", "type": "subagent", "status": "running", "description": "Quick look", "agent_type": "general-purpose"},
            {"id": "b1", "type": "shell", "status": "running", "description": "Sleep"}]))
        self.assertEqual(self.shown(hub, sent), ([["a2", "Quick look", "working"]], 0))
        hub.on_event(_ev("Stop", last_assistant_message="x"))  # an older Claude Code names none: nothing is taken away
        self.assertEqual(len(self.shown(hub, sent)[0]), 1)

    def test_one_that_comes_back_keeps_its_task_and_stands_last(self):
        hub, sent = self.make()
        self.start(hub, "a1", "Quick look")
        hub.on_event(_ev("SubagentStop", agent_id="a1", agent_type="general-purpose"))
        hub.sessions.by_id["s1"].agents["a1"].done -= base.AGENT_CHEER
        self.start(hub, "a2", "Step walker")
        hub.on_event(_ev("SubagentStart", agent_id="a1", agent_type="general-purpose"))  # sent a message, or woke itself
        self.assertEqual(self.shown(hub, sent), ([["a2", "Step walker", "working"], ["a1", "Quick look", "working"]], 0))

    def test_one_that_comes_back_while_it_cheers_keeps_its_place(self):
        hub, sent = self.make()  # the session is told of its end 0.05 s after, and may send it a message at once
        self.start(hub, "a1", "Quick look")
        self.start(hub, "a2", "Step walker")
        hub.on_event(_ev("SubagentStop", agent_id="a1", agent_type="general-purpose"))
        hub.on_event(_ev("SubagentStart", agent_id="a1", agent_type="general-purpose"))
        self.assertEqual([a[0] + ":" + a[2] for a in self.shown(hub, sent)[0]], ["a1:working", "a2:working"])

    def test_one_that_was_stopped_and_comes_back_keeps_its_task(self):
        hub, sent = self.make()
        self.start(hub, "a1", "Alpha task")
        self.start(hub, "a2", "Beta task")
        hub.on_event(_ev("Stop", last_assistant_message="x", background_tasks=[{"id": "a1", "type": "subagent", "status": "running"}]))
        hub.on_event(_ev("SubagentStart", agent_id="a2", agent_type="general-purpose"))
        self.assertEqual(self.shown(hub, sent)[0], [["a1", "Alpha task", "working"], ["a2", "Beta task", "working"]])

    def test_a_stop_and_a_start_that_crossed_are_put_right_when_the_turn_ends(self):
        # It stopped waiting on a command of its own, which ended at that moment: the hooks report
        # on their own, and its start came first. It runs, and the next Stop says so.
        hub, sent = self.make()
        self.start(hub, "a1", "Self waker")
        hub.on_event(_ev("SubagentStart", agent_id="a1", agent_type="general-purpose"))
        hub.on_event(_ev("SubagentStop", agent_id="a1", agent_type="general-purpose"))
        hub.on_event(_ev("Stop", last_assistant_message="x", background_tasks=[{"id": "a1", "type": "subagent", "status": "running"}]))
        hub.sessions.by_id["s1"].agents["a1"].since -= 60
        self.assertEqual(self.shown(hub, sent)[0], [["a1", "Self waker", "working"]])

    def test_one_whose_request_failed_goes_without_a_cheer(self):
        hub, sent = self.make()  # at the usage limit there may be no clean turn for hours
        self.start(hub, "a1", "Alpha task")
        hub.on_event(_ev("StopFailure", agent_id="a1", agent_type="general-purpose", error="rate_limit"))
        self.assertEqual(self.shown(hub, sent), ([], 0))
        self.assertEqual(hub.snapshot()["sessions"][0]["agents"], [])

    def test_events_in_any_order_name_it_once_and_leave_no_task_behind(self):
        import itertools
        events = [_ev("PreToolUse", tool_name="Agent", tool_input={"description": "Alpha task"}),
                  _ev("SubagentStart", agent_id="a1", agent_type="general-purpose"),
                  _ev("PostToolUse", tool_name="Agent", tool_response={"status": "async_launched", "agentId": "a1", "description": "Alpha task"})]
        for order in itertools.permutations(events):
            hub, sent = self.make()
            for event in order:
                hub.on_event(event)
            self.assertEqual(self.shown(hub, sent), ([["a1", "Alpha task", "working"]], 0))
            self.assertEqual(hub.snapshot()["sessions"][0]["agents"], ["Alpha task"])
            # The next one, whose own task has not arrived yet, is not given this one's for good.
            hub.on_event(_ev("SubagentStart", agent_id="a2", agent_type="general-purpose"))
            hub.on_event(_ev("PostToolUse", tool_name="Agent", tool_response={"status": "async_launched", "agentId": "a2", "description": "Beta task"}))
            self.assertEqual([a[1] for a in self.shown(hub, sent)[0]], ["Alpha task", "Beta task"])

    def test_one_that_outlived_a_clear_is_taken_in_at_the_next_stop(self):
        hub, sent = self.make()  # it reports under the new session, which has not seen it start
        hub.on_event(_ev("SubagentStop", agent_id="a1", agent_type="general-purpose"))
        self.assertEqual(self.shown(hub, sent), ([], 0))
        hub.on_event(_ev("Stop", last_assistant_message="x", background_tasks=[
            {"id": "a2", "type": "subagent", "status": "running", "description": "Outlives clear"}]))
        self.assertEqual(self.shown(hub, sent), ([["a2", "Outlives clear", "working"]], 0))


if __name__ == "__main__":
    unittest.main()
