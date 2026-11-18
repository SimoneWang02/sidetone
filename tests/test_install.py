"""install.sh and uninstall.sh in a throwaway home: the hooks, and the offer of the VS Code extension.

Nothing here reaches the real VS Code, the real settings or the running hub: `code` is a
stand-in that writes down what it was asked, every real `code` is taken off the PATH, and
the home, settings and run folders are made for the test.
"""
import json
import os
import pty
import select
import subprocess
import tempfile
import time
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSION = "claude-speaks.claude-speaks"
CODE = """#!/bin/sh
echo "$*" >> "$CODE_LOG"
case $1 in
  --list-extensions) echo someone.else; [ ! -f "$CODE_LOG.installed" ] || echo claude-speaks.claude-speaks ;;
  --install-extension) [ -z "${CODE_FAILS:-}" ] || exit 1; cp "$2" "$CODE_LOG.vsix" && : > "$CODE_LOG.installed" ;;
  --uninstall-extension) rm -f "$CODE_LOG.installed" ;;
esac
"""


class Installing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.settings = os.path.join(self.tmp, ".claude", "settings.json")
        self.bin = os.path.join(self.tmp, "stand-ins")
        os.makedirs(self.bin)
        self.log = os.path.join(self.tmp, "code.log")
        without_code = [d for d in os.environ["PATH"].split(os.pathsep)
                        if d and not os.path.exists(os.path.join(d, "code"))]
        self.env = {**os.environ, "HOME": self.tmp, "PATH": os.pathsep.join([self.bin, *without_code]),
                    "XDG_CONFIG_HOME": os.path.join(self.tmp, "cfg"), "XDG_RUNTIME_DIR": os.path.join(self.tmp, "xdg"),
                    "CS_RUN": os.path.join(self.tmp, "run"), "CS_STATE": self.tmp,
                    "KOKORO_DIR": os.path.join(self.tmp, "kokoro"), "CODE_LOG": self.log}
        self.env.pop("CODE_FAILS", None)

    def stand_in(self, name, text="#!/bin/sh\nexit 0\n"):
        path = os.path.join(self.bin, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)

    def vs_code(self, installed=False):
        self.stand_in("code", CODE)
        if installed:
            open(self.log + ".installed", "w").close()

    def run_it(self, script, *args):
        return subprocess.run([os.path.join(ROOT, script), *args], env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=60)

    def at_a_terminal(self, *args, typed=""):
        """A whole install as a person at a terminal would run it, minus the downloads: `uv`
        and the Python it would have set up are stand-ins. Returns what the terminal showed."""
        self.stand_in("uv")
        self.stand_in(os.path.join("..", "kokoro", "venv", "bin", "python"))
        ours, theirs = pty.openpty()
        process = subprocess.Popen([os.path.join(ROOT, "install.sh"), "--no-models", "--languages", "en", *args],
                                   env=self.env, stdin=theirs, stdout=theirs, stderr=theirs, close_fds=True)
        os.close(theirs)
        os.write(ours, typed.encode())
        shown, until = b"", time.monotonic() + 60
        while time.monotonic() < until:
            if not select.select([ours], [], [], 0.2)[0]:
                if process.poll() is not None:
                    break
                continue
            try:
                piece = os.read(ours, 4096)
            except OSError:  # the other end is closed: the script is done
                break
            if not piece:
                break
            shown += piece
        os.close(ours)
        self.assertEqual(process.wait(timeout=10), 0, shown.decode(errors="replace"))
        return shown.decode(errors="replace")

    def asked_of_code(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [line.split()[0] for line in f.read().splitlines()]

    def hooks(self):
        with open(self.settings) as f:
            return json.load(f).get("hooks", {})

    # The hooks

    def test_every_hook_of_the_snippet_is_registered_and_taken_out_again(self):
        with open(os.path.join(ROOT, "hooks", "settings-snippet.json")) as f:
            snippet = json.load(f)["hooks"]
        wanted = {event: [hook["command"].replace("$HOME/personal/claude-speaks", ROOT)
                          for group in groups for hook in group["hooks"]] for event, groups in snippet.items()}
        for script in ("stop.sh", "listen.sh", "permission.sh", "report.sh --start"):
            self.assertTrue(any(c.endswith("/hooks/" + script) for cs in wanted.values() for c in cs), script)
        own = {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/bin/true"}]}],
               "SubagentStop": [{"hooks": [{"type": "command", "command": "/usr/bin/true"}]}]}
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as f:
            json.dump({"model": "opus", "hooks": own}, f)

        done = self.run_it("install.sh", "--hooks-only")
        self.assertEqual(done.returncode, 0, done.stderr)
        registered = {event: [hook["command"] for group in groups for hook in group["hooks"]]
                      for event, groups in self.hooks().items()}
        for event, commands in wanted.items():
            self.assertEqual([c for c in registered[event] if c.startswith(ROOT)], commands, event)
            for command in commands:  # and each one is a script that is there and can be run
                self.assertTrue(os.access(command.split()[0], os.X_OK), command)
        for event in ("PreToolUse", "PostToolUse"):
            self.assertIn(os.path.join(ROOT, "hooks", "stop.sh"), registered[event])
        self.assertIn("/usr/bin/true", registered["PreToolUse"])

        again = self.run_it("install.sh", "--hooks-only")  # a second run adds nothing twice
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual({event: [hook["command"] for group in groups for hook in group["hooks"]]
                          for event, groups in self.hooks().items()}, registered)

        gone = self.run_it("uninstall.sh")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        with open(self.settings) as f:
            self.assertEqual(json.load(f), {"model": "opus", "hooks": own})

    def test_with_only_our_hooks_nothing_of_them_is_left(self):
        self.assertEqual(self.run_it("install.sh", "--hooks-only").returncode, 0)
        with open(os.path.join(ROOT, "hooks", "settings-snippet.json")) as f:
            self.assertEqual(sorted(self.hooks()), sorted(json.load(f)["hooks"]))
        self.assertEqual(self.run_it("uninstall.sh").returncode, 0)
        with open(self.settings) as f:
            self.assertEqual(json.load(f), {})
        for name in ("claude-speaks", "cs"):
            self.assertFalse(os.path.lexists(os.path.join(self.tmp, ".local", "bin", name)))

    # The VS Code extension

    def test_the_option_installs_the_extension(self):
        self.vs_code()
        done = self.run_it("install.sh", "--hooks-only", "--vscode")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.asked_of_code(), ["--install-extension"])
        with zipfile.ZipFile(self.log + ".vsix") as packed:  # what VS Code was handed is the extension
            self.assertIn("extension/extension.js", packed.namelist())
            self.assertEqual(json.loads(packed.read("extension/package.json"))["name"], "claude-speaks")

    def test_with_nobody_to_ask_vs_code_is_left_alone(self):
        self.vs_code()
        done = self.run_it("install.sh", "--hooks-only")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.asked_of_code(), [])
        self.assertNotIn("extension", done.stdout)

    def test_a_whole_install_with_nobody_to_ask_leaves_vs_code_alone_too(self):
        self.vs_code()
        self.stand_in("uv")
        self.stand_in(os.path.join("..", "kokoro", "venv", "bin", "python"))
        done = self.run_it("install.sh", "--no-models", "--languages", "en")  # from a script: no terminal
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Python environment", done.stdout)
        self.assertEqual(self.asked_of_code(), [])

    def test_the_option_without_vs_code_only_says_so(self):
        done = self.run_it("install.sh", "--hooks-only", "--vscode")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("no 'code' command", done.stdout)
        self.assertIn("Done.", done.stdout)

    def test_an_extension_that_will_not_install_does_not_stop_the_install(self):
        self.vs_code()
        self.env["CODE_FAILS"] = "1"
        done = self.run_it("install.sh", "--hooks-only", "--vscode")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("could not be installed", done.stdout)
        self.assertIn("Stop", self.hooks())
        self.assertIn("Done.", done.stdout)

    def test_a_person_at_a_terminal_is_asked_and_enter_means_yes(self):
        self.vs_code()
        shown = self.at_a_terminal(typed="\n")
        self.assertIn("Install the extension?", shown)
        self.assertIn("which terminal you are in", shown)  # one line on what it is for
        self.assertEqual(self.asked_of_code(), ["--list-extensions", "--install-extension"])
        self.assertIn("Done.", shown)

    def test_a_no_at_the_terminal_installs_nothing(self):
        self.vs_code()
        shown = self.at_a_terminal(typed="n\n")
        self.assertIn("Install the extension?", shown)
        self.assertIn("claude-speaks vscode install", shown)  # how to get it later
        self.assertEqual(self.asked_of_code(), ["--list-extensions"])

    def test_an_answer_given_ahead_is_not_asked_for(self):
        self.vs_code()
        self.assertNotIn("Install the extension?", self.at_a_terminal("--no-vscode"))
        self.assertEqual(self.asked_of_code(), [])
        self.assertNotIn("Install the extension?", self.at_a_terminal("--vscode"))
        self.assertEqual(self.asked_of_code(), ["--install-extension"])

    def test_an_extension_already_there_is_brought_up_to_date_without_asking(self):
        self.vs_code(installed=True)
        shown = self.at_a_terminal()
        self.assertNotIn("Install the extension?", shown)
        self.assertEqual(self.asked_of_code(), ["--list-extensions", "--install-extension"])

    def test_without_vs_code_nothing_is_asked(self):
        shown = self.at_a_terminal()
        self.assertNotIn("extension", shown)
        self.assertIn("Done.", shown)

    def test_uninstalling_takes_the_extension_out_again(self):
        self.vs_code()
        self.assertEqual(self.run_it("install.sh", "--hooks-only", "--vscode").returncode, 0)
        self.assertTrue(os.path.exists(self.log + ".installed"))
        gone = self.run_it("uninstall.sh")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertIn("VS Code extension removed", gone.stdout)
        self.assertFalse(os.path.exists(self.log + ".installed"))
        self.assertEqual(self.asked_of_code()[1:], ["--list-extensions", "--uninstall-extension"])

    def test_uninstalling_can_leave_the_extension(self):
        self.vs_code(installed=True)
        self.assertEqual(self.run_it("install.sh", "--hooks-only").returncode, 0)
        gone = self.run_it("uninstall.sh", "--keep-vscode")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual(self.asked_of_code(), [])
        self.assertEqual(self.hooks(), {})

    def test_uninstalling_does_not_remove_an_extension_that_is_not_there(self):
        self.vs_code()
        self.assertEqual(self.run_it("install.sh", "--hooks-only").returncode, 0)
        gone = self.run_it("uninstall.sh")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual(self.asked_of_code(), ["--list-extensions"])
        self.assertNotIn("extension", gone.stdout)

    def test_an_unknown_option_to_uninstall_changes_nothing(self):
        self.assertEqual(self.run_it("install.sh", "--hooks-only").returncode, 0)
        gone = self.run_it("uninstall.sh", "--everything")
        self.assertEqual(gone.returncode, 2)
        self.assertIn("Stop", self.hooks())


if __name__ == "__main__":
    unittest.main()
