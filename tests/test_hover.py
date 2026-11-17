"""Whether the mouse alone brings the overlay's details out is a setting."""
import json
import os
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import overlay  # noqa: E402
from hub import serve  # noqa: E402
from test_hub import FakeOverlay, HubCase  # noqa: E402


class Hover(HubCase):
    def test_the_mouse_opens_the_details_unless_told_otherwise(self):
        self.assertEqual(overlay.DEFAULTS["hover"], "always")

    def test_the_command_changes_it_and_it_is_remembered(self):
        config = os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "config.json")
        hub = self.make(config_path=config)
        hub.overlay = FakeOverlay()
        server = serve(hub, self.cfg.sock)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp}
        run = lambda *args: subprocess.run([os.path.join(ROOT, "bin", "claude-speaks"), "overlay", *args],  # noqa: E731
                                           capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(run("hover", "keys").stdout.strip(), "hover: keys")
        self.assertEqual(hub.cfg.overlay["hover"], "keys")
        with open(config) as f:
            self.assertEqual(json.load(f)["overlay"]["hover"], "keys")
        wrong = run("hover", "sometimes")
        self.assertEqual(wrong.returncode, 2)
        self.assertEqual(hub.cfg.overlay["hover"], "keys")
