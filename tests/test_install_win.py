"""The Windows install's merging of hooks (hub/install_win.py), which runs anywhere."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import install_win  # noqa: E402

EXE = r"C:\Users\someone\AppData\Local\sidetone\sidetone-hook.exe"


class TheHooks(unittest.TestCase):
    def test_every_bash_hook_has_its_word_and_keeps_its_options(self):
        with open(install_win.SNIPPET) as f:
            snippet = json.load(f)["hooks"]
        made = install_win.windows_hooks(EXE)
        self.assertEqual(set(made), set(snippet))
        for event in snippet:
            for old_group, new_group in zip(snippet[event], made[event]):
                self.assertEqual(old_group.get("matcher"), new_group.get("matcher"))
                for old, new in zip(old_group["hooks"], new_group["hooks"]):
                    self.assertEqual(new["command"], EXE)
                    self.assertEqual(len(new["args"]), 1)
                    self.assertIn(new["args"][0], install_win.SCRIPTS.values())
                    for option in ("async", "asyncRewake", "timeout"):
                        self.assertEqual(old.get(option), new.get(option), (event, option))
        self.assertEqual(made["MessageDisplay"][0]["hooks"][0]["args"], ["display"])
        self.assertEqual(made["SessionStart"][0]["hooks"][0]["args"], ["report-start"])

    def test_others_hooks_and_settings_are_kept_and_a_second_install_does_not_double(self):
        theirs = {"type": "command", "command": "C:\\tools\\lint.exe"}
        current = {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [theirs]}]}}
        once = install_win.merged(current, EXE)
        twice = install_win.merged(once, EXE)
        self.assertEqual(once, twice)
        self.assertEqual(twice["model"], "opus")
        self.assertIn({"matcher": "Bash", "hooks": [theirs]}, twice["hooks"]["PreToolUse"])

    def test_uninstall_leaves_only_theirs(self):
        theirs = {"type": "command", "command": "C:\\tools\\lint.exe"}
        current = install_win.merged({"hooks": {"Stop": [{"hooks": [theirs]}]}}, EXE)
        gone = install_win.merged(current, EXE, add=False)
        self.assertEqual(gone, {"hooks": {"Stop": [{"hooks": [theirs]}]}})
        self.assertEqual(install_win.merged(install_win.merged({}, EXE), EXE, add=False), {})


if __name__ == "__main__":
    unittest.main()
