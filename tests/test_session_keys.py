"""The new-session key and the end key (Ctrl+Alt+Plus, Ctrl+Alt+Minus): what the hub asks of the
editor, when the keys are claimed, and the session that starts getting the focus.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests
"""
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import hub as hub_module  # noqa: E402
from test_hub import FakeOverlay, HubCase, ev  # noqa: E402


class SessionKeys(HubCase):
    def make(self, **kw):
        hub = super().make(label="never", **kw)
        hub.overlay = self.overlay = FakeOverlay()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.on_event(ev("SessionStart", sid="a", cwd="/w/a"))
        hub.on_event(ev("SessionStart", sid="b", cwd="/w/b"))
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        hub.talk_target = "a"
        return hub

    def live(self):
        keys = self.overlay.of("keys")
        return keys[-1]["live"] if keys else []

    def test_the_keys_are_claimed_only_with_an_editor_that_can_do_it(self):
        hub = self.make()
        hub.publish()
        self.assertNotIn("new_session", self.live())
        self.assertNotIn("end_session", self.live())
        hub.editor_waits([4001], shows=True, clears=True)  # an extension from before 0.5.0
        hub.publish()
        self.assertNotIn("new_session", self.live())
        editor = hub.editor_waits([4001], shows=True, clears=True, opens=True)
        hub.publish()
        self.assertIn("new_session", self.live())
        self.assertIn("end_session", self.live())
        hub.editor_done(editor)
        hub.talk_target = "b"  # its terminal is in no editor: nothing to end there
        hub.editor_waits([4001], opens=True)
        hub.publish()
        self.assertIn("new_session", self.live())
        self.assertNotIn("end_session", self.live())

    def test_a_new_session_opens_beside_the_one_in_focus_and_gets_the_focus(self):
        hub = self.make()
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertTrue(editor.wake.is_set())
        self.assertEqual(editor.open, [{"cwd": "/w/a", "beside": 4001}])
        self.assertEqual(hub.editor_done(editor), [])  # nothing typed into a terminal of ours
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/a", source="startup"))
        self.assertEqual(hub._target().id, "c")
        hub.talk_target = "a"
        hub.on_event(ev("SessionStart", sid="d", cwd="/w/a", source="startup"))  # opened by hand: no focus
        self.assertEqual(hub._target().id, "a")

    def test_with_no_session_a_new_one_opens_in_the_editors_own_folder(self):
        hub = self.make()
        for sid in list(hub.sessions.by_id):
            hub.on_event(ev("SessionEnd", sid=sid))
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertEqual(editor.open, [{"cwd": "", "beside": None}])

    def test_the_end_key_asks_then_ends_and_closes_the_terminal_once_ended(self):
        hub = self.make()
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertFalse(editor.wake.is_set(), "one press only asks")
        asked = self.overlay.of("banner")[-1]
        self.assertEqual((asked["icon"], asked["text"], asked["hint"]), ("end", "End a?", "Ctrl+Alt+Minus to confirm"))
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1], {"type": "banner"})
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "exit"}])
        self.assertEqual(editor.close, [], "the terminal stays until the session has ended")
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [4001])
        # A session that ends by itself does not have its terminal closed.
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_event(ev("SessionEnd", sid="b", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [])

    def test_a_late_second_press_only_asks_again(self):
        hub = self.make()
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub._end_armed = ("a", time.monotonic() - 4)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertFalse(editor.wake.is_set())

    def test_a_close_asked_between_two_requests_goes_to_the_next(self):
        hub = self.make()
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.editor_done(editor)
        hub.on_event(ev("SessionEnd", sid="a"))  # no editor waiting at this moment
        editor = hub.editor_waits([4001], opens=True)
        self.assertEqual(editor.close, [4001])
        self.assertTrue(editor.wake.is_set())


if __name__ == "__main__":
    unittest.main()
