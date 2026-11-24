"""`sidetone status` says when what is running is older than the code on disk."""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import overlay  # noqa: E402
import stale  # noqa: E402
from hub import serve  # noqa: E402
from test_hub import HubCase  # noqa: E402


class WhatChanged(unittest.TestCase):
    def test_edited_added_and_removed_files_are_named(self):
        folder = tempfile.mkdtemp(prefix="cs-test-")
        for name in ("a.py", "b.py", "gone.py", "notes.txt"):
            with open(os.path.join(folder, name), "w") as f:
                f.write("x")
        then = stale.prints(folder)
        self.assertEqual(sorted(then), ["a.py", "b.py", "gone.py"])
        self.assertEqual(stale.changed(then, folder), [])
        os.utime(os.path.join(folder, "a.py"), (1, 1))  # only touched: the same text
        with open(os.path.join(folder, "b.py"), "w") as f:
            f.write("y")
        os.unlink(os.path.join(folder, "gone.py"))
        with open(os.path.join(folder, "new.py"), "w") as f:
            f.write("x")
        self.assertEqual(stale.changed(then, folder), ["b.py", "gone.py", "new.py"])

    def test_the_overlay_knows_when_its_source_changed(self):
        folder = tempfile.mkdtemp(prefix="cs-test-")
        for name in ("Overlay.cs", "overlay.ps1"):
            with open(os.path.join(folder, name), "w") as f:
                f.write("x")
        for patch in (mock.patch.object(overlay, "MAC", False), mock.patch.object(overlay, "wsl", lambda: True)):
            patch.start()  # the Windows overlay's files, wherever this runs
            self.addCleanup(patch.stop)
        window = overlay.Overlay(os.path.join(folder, "overlay.ps1"), {})
        self.assertFalse(window.outdated())  # not started: nothing is running
        window.proc, window._source = object(), stale.prints(folder, overlay.SOURCES)
        self.assertFalse(window.outdated())
        with open(os.path.join(folder, "Overlay.cs"), "w") as f:
            f.write("y")
        self.assertTrue(window.outdated())


class TheStatusCommand(HubCase):
    def status(self):
        hub = self.make()
        server = serve(hub, self.cfg.sock)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp}
        return subprocess.run([os.path.join(ROOT, "bin", "sidetone"), "status"], capture_output=True,
                              text=True, env=env, timeout=10).stdout

    def test_it_is_quiet_when_nothing_changed(self):
        with mock.patch.object(stale, "LOADED", stale.prints()):  # as if started this instant: another session may be editing
            self.assertNotIn("note:", self.status())

    def test_it_names_the_files_a_restart_would_bring_in(self):
        with mock.patch.object(stale, "LOADED", {**stale.LOADED, "hub.py": "older", "tts.py": "older"}):
            said = self.status()
        self.assertIn("note: the hub is running older code than is on disk (hub.py, tts.py)", said)
        self.assertIn("sidetone hub restart", said)
        self.assertNotIn("overlay", said)

    def test_it_says_when_the_overlay_is_behind(self):
        hub = self.make()
        hub.overlay = mock.Mock(outdated=lambda: True)
        self.assertEqual(hub.snapshot()["outdated"], {"hub": [], "overlay": True})


if __name__ == "__main__":
    unittest.main()
