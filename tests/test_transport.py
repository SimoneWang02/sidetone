"""The hub's door on a local port, as on Windows (no Unix sockets for Python there): only a
request with the token from hub.addr is let in, never one a web page sends, and the hooks find
it. Run here with SIDETONE_TRANSPORT=tcp."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_hub import ev, tag, wait_for  # noqa: E402


class ALocalPort(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp, "XDG_CONFIG_HOME": self.tmp,
                    "SIDETONE_TTS": "null", "SIDETONE_OVERLAY": "off", "SIDETONE_TERMINAL": "off", "SIDETONE_TRANSPORT": "tcp"}
        self.hub = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "hub", "hub.py")], env=self.env)
        self.addCleanup(self.hub.wait, 5)
        self.addCleanup(self.hub.terminate)
        self.addr = os.path.join(self.tmp, "hub.addr")
        self.assertTrue(wait_for(lambda: os.path.exists(self.addr), 10), "no hub.addr")
        with open(self.addr) as f:
            port, self.token = f.read().split()
        self.url = f"http://127.0.0.1:{port}"

    def ask(self, path, body=None, headers=None):
        request = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=3) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_no_unix_socket_and_the_file_is_the_owners(self):
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "hub.sock")))
        self.assertEqual(os.stat(self.addr).st_mode & 0o077, 0)

    def test_only_the_token_lets_a_request_in(self):
        self.assertEqual(self.ask("/health")[0], 403)
        self.assertEqual(self.ask("/health", headers={"X-Sidetone-Token": "guess"})[0], 403)
        self.assertEqual(self.ask("/health", headers={"X-Sidetone-Token": self.token})[0], 200)

    def test_a_web_page_is_refused_even_with_the_token(self):
        # A page cannot read the token, but if it ever had it: browsers send Origin, and a page
        # that renamed itself to 127.0.0.1 still sends its own Host.
        self.assertEqual(self.ask("/health", headers={"X-Sidetone-Token": self.token, "Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.ask("/health", headers={"X-Sidetone-Token": self.token, "Host": "evil.example"})[0], 403)

    def test_the_hooks_reach_it(self):
        hook = lambda name, payload: subprocess.run([os.path.join(ROOT, "hooks", name)], input=json.dumps(payload),  # noqa: E731
                                                    text=True, capture_output=True, env=self.env, timeout=10)
        hook("report.sh", ev("SessionStart", sid="a", cwd="/work/alpha"))
        shown = hook("display.sh", ev("MessageDisplay", sid="a", cwd="/work/alpha", delta=tag("All done.") + "\n"))
        self.assertIn("All done.", shown.stdout)
        state = self.ask("/state", headers={"X-Sidetone-Token": self.token})[1]
        self.assertEqual([s["name"] for s in state["sessions"]], ["alpha"])
        status = subprocess.run([os.path.join(ROOT, "bin", "sidetone"), "status"], text=True, capture_output=True, env=self.env, timeout=10)
        self.assertIn("alpha", status.stdout)


if __name__ == "__main__":
    unittest.main()
