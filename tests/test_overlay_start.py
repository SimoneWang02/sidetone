"""When the hub starts the overlay's window, and when it holds off."""
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import overlay  # noqa: E402


class StartingTheWindow(unittest.TestCase):
    def window(self, clock):
        """An overlay whose program is `cat` (it stays until its input ends) and whose clock is ours."""
        for patch in (mock.patch.object(overlay, "command", lambda script, log=None: ["cat"]),
                      mock.patch.object(overlay, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))):
            patch.start()
            self.addCleanup(patch.stop)
        window = overlay.Overlay("/nowhere/overlay.ps1", {})
        self.addCleanup(window.stop)
        return window

    def test_it_starts_at_once_on_a_machine_that_has_just_booted(self):
        # The clock counts from the boot. The first session of the day starts the hub seconds
        # after it, and the window used to wait until the machine had been up for half a minute.
        clock = [5.0]
        window = self.window(clock)
        window.send({"type": "state", "sessions": []})
        self.assertIsNotNone(window.proc)

    def test_one_that_went_away_is_not_started_again_right_away(self):
        clock = [5.0]
        window = self.window(clock)
        window.send({"type": "state", "sessions": []})
        window.stop()  # as if it had crashed
        clock[0] += overlay.RETRY_AFTER - 1
        window.send({"type": "state", "sessions": []})
        self.assertIsNone(window.proc)
        clock[0] += 2
        window.send({"type": "state", "sessions": []})
        self.assertIsNotNone(window.proc)

    def test_asked_to_restart_it_does_not_wait(self):
        clock = [5.0]
        window = self.window(clock)
        window.send({"type": "state", "sessions": []})
        first = window.proc
        window.restart()
        self.assertIsNotNone(window.proc)
        self.assertIsNot(window.proc, first)



class ReadingTheWindow(unittest.TestCase):
    def test_a_message_the_hub_cannot_act_on_does_not_end_the_reading(self):
        # Before, one error ended the reader for the rest of the hub's life, and every hotkey with it.
        got, logged = [], []

        def on_message(msg):
            if msg["type"] == "talk_end":
                raise OSError("recorder gone")
            got.append(msg["type"])
        window = overlay.Overlay("overlay.ps1", {}, on_message=on_message, log=logged.append)
        proc = types.SimpleNamespace(stdout=iter(['{"type": "talk_end"}\n', '{"type": "allow"}\n']))
        window._read(proc)
        self.assertEqual(got, ["allow"])
        self.assertTrue(any("talk_end failed" in line and "recorder gone" in line for line in logged), logged)



if __name__ == "__main__":
    unittest.main()
