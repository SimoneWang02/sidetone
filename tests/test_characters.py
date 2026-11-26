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
    def test_every_figure_draws_every_moment(self):
        for style in characters.STYLES:
            for kind in range(5):
                for moment in MOMENTS:
                    cell = characters.frame(style, kind, COLORS[kind], moment, 0.5, 0.5, 0.6)
                    self.assertEqual(len(cell), characters.N * characters.N * 4)
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
        self.assertEqual([characters.kind_of(c) for c in COLORS[:6]], [0, 1, 2, 3, 4, 0])
        self.assertEqual(characters.kind_of("#8ab4ff"), 0)  # the color as the config may write it
        own = characters.kind_of("#123456")
        self.assertEqual(characters.kind_of("#123456"), own)
        self.assertIn(own, range(5))

    def test_nothing_is_cut_off_at_the_top_or_the_sides(self):
        # The author, 2026-11-26: "the animation seems cut"; leaves and hair ran past the cell.
        n = characters.N
        edges = [(x, 0) for x in range(n)] + [(0, y) for y in range(n)] + [(n - 1, y) for y in range(n)]
        for style in characters.STYLES:
            for kind in range(5):
                for name, count in characters.ROWS:
                    s, t0, a0, v = characters._moment(name)
                    for i in (0, count // 3, 2 * count // 3):
                        cell = characters.frame(style, kind, COLORS[kind], s, t0 + i / characters.FPS, a0 + i / characters.FPS, v)
                        self.assertFalse(any(cell[(y * n + x) * 4 + 3] > 40 for x, y in edges), (style, kind, name, i))

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

    def test_a_sheet_already_on_disk_is_not_drawn_again(self):
        folder = tempfile.mkdtemp(prefix="cs-sprites-")
        first = characters.Sheets(folder)
        name = first.name("operators", characters.kind_of(COLORS[1]), COLORS[1])
        with open(name, "wb") as f:
            f.write(b"drawn before")
        again = characters.Sheets(folder, done=lambda: self.fail("drawn again"))
        self.assertEqual(again.path("operators", COLORS[1]), name)


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

    def test_a_character_reaches_the_overlay_once_drawn(self):
        hub, sent = self.make("familiars")
        hub.publish()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not self.rows(sent)["sessions"][0]["sprite"]:
            time.sleep(0.05)
        path = self.rows(sent)["sessions"][0]["sprite"]
        self.assertTrue(path.endswith(".png") and os.path.isfile(path), path)
        self.assertIn(os.path.join(self.tmp, "characters"), path)


if __name__ == "__main__":
    unittest.main()
