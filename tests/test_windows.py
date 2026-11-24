"""What Windows itself needs from the hub, tested where it can be: paths with backslashes, and
processes asked about without signals."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import procs  # noqa: E402
import state  # noqa: E402
from test_hub import HubCase, ev  # noqa: E402


class Paths(unittest.TestCase):
    def test_a_session_is_named_after_its_folder_however_the_path_is_written(self):
        for path, name in ((r"C:\work\api-server", "api-server"), (r"C:\work\api-server\\", "api-server"),
                           ("C:/work/web-app", "web-app"), ("/work/alpha/", "alpha")):
            self.assertEqual(state.leaf(path), name)


class Named(HubCase):
    def test_a_windows_session_gets_its_folders_name(self):
        hub = self.make()
        hub.on_event(ev("SessionStart", sid="w1", cwd=r"C:\Users\someone\work\api-server"))
        self.assertEqual(hub.snapshot()["sessions"][0]["name"], "api-server")


class TalkToggle(HubCase):
    def test_one_command_starts_talking_and_the_next_sends(self):
        # For a desktop's own shortcut (Wayland), which sees no key being let go.
        import threading
        from hub import serve
        from test_hub import FakeRecorder, FakeTranscriber
        hub = self.make()
        hub.recorder, hub.transcriber = FakeRecorder(), FakeTranscriber()
        hub.on_event(ev("SessionStart"))
        server = serve(hub, self.cfg.sock)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)

        def toggle():
            return subprocess.run(["curl", "-sf", "--unix-socket", self.cfg.sock, "-d", '{"action": "toggle"}', "http://hub/talk"],
                                  capture_output=True, text=True, timeout=5).returncode
        self.assertEqual(toggle(), 0)
        self.assertTrue(hub.recorder.recording)
        self.assertEqual(toggle(), 0)
        self.assertFalse(hub.recorder.recording)


class Processes(unittest.TestCase):
    def test_alive_and_ended(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        self.assertTrue(procs.alive(proc.pid))
        procs.end_tree(proc)
        proc.wait(5)
        self.assertFalse(procs.alive(proc.pid))


if __name__ == "__main__":
    unittest.main()
