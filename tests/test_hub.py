"""Hub behaviour with a silent engine: speech order, labels, voices, session state, and the hooks.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests   (any Python 3.10+ works)
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
from hub import Config, Hub, serve  # noqa: E402
from tts import NullEngine  # noqa: E402


def ev(event, sid="s1", cwd="/work/alpha", **extra):
    return {"hook_event_name": event, "session_id": sid, "cwd": cwd, **extra}


def tag(text):
    return f"<speak>{text}</speak>"


class HubCase(unittest.TestCase):
    def make(self, duration=0.0, **cfg):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.engine = NullEngine(duration)
        self.cfg = Config(run=self.tmp, state=self.tmp, engine="null",
                          mute_file=os.path.join(self.tmp, "voice-off"), **cfg)
        self.hub = Hub(self.cfg, self.engine)
        self.addCleanup(self.hub.speech.close)
        return self.hub

    def spoken(self):
        self.assertTrue(self.hub.speech.wait_idle(5), "speech queue did not drain")
        return [text for text, _ in self.engine.spoken]

    def session(self, sid="s1"):
        return next(s for s in self.hub.snapshot()["sessions"] if s["id"] == sid)


class Display(HubCase):
    def test_own_line_tag_is_spoken_and_rewritten(self):
        hub = self.make()
        out = hub.on_display(ev("MessageDisplay", delta=f"{tag('All done.')}\nDetails follow.\n"))
        self.assertEqual(out["hookSpecificOutput"]["displayContent"], "🔊 All done.\nDetails follow.\n")
        self.assertEqual(self.spoken(), ["All done."])

    def test_inline_mention_is_ignored(self):
        hub = self.make()
        self.assertIsNone(hub.on_display(ev("MessageDisplay", delta=f"Use the {tag('x')} tag on its own line.\n")))
        self.assertEqual(self.spoken(), [])

    def test_stop_does_not_repeat_the_streamed_line(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", delta=tag("All done.") + "\n"))
        hub.on_event(ev("Stop", last_assistant_message=f"{tag('All done.')}\n\nBody"))
        self.assertEqual(self.spoken(), ["All done."])

    def test_stop_speaks_when_streaming_missed_it(self):
        hub = self.make()
        hub.on_event(ev("Stop", last_assistant_message=f"Intro\n{tag('Finished.')}\nBody"))
        self.assertEqual(self.spoken(), ["Finished."])

    def test_stop_skips_a_line_the_hook_spoke_without_the_hub(self):
        hub = self.make()
        os.makedirs(os.path.join(self.tmp, ".state"))
        with open(os.path.join(self.tmp, ".state", "s1.spoken"), "w") as f:
            f.write("Finished.")
        hub.on_event(ev("Stop", last_assistant_message=tag("Finished.")))
        self.assertEqual(self.spoken(), [])


class Queue(HubCase):
    def test_needs_you_jumps_ahead_of_done(self):
        hub = self.make(duration=0.2, label="never")
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A is done.")))
        time.sleep(0.05)  # A is now being spoken
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        hub.on_event(ev("Notification", sid="c", cwd="/w/c", notification_type="permission_prompt"))
        self.assertEqual(self.spoken(), ["A is done.", "I need your input", "B is done."])

    def test_newer_line_replaces_the_queued_one(self):
        hub = self.make(duration=0.2, label="never")
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A.")))
        time.sleep(0.05)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("Old.")))
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("New.")))
        self.assertEqual(self.spoken(), ["A.", "New."])

    def test_line_that_waited_too_long_is_dropped(self):
        hub = self.make(duration=0.3, label="never", max_age=0.1)
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A.")))
        time.sleep(0.05)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("Late.")))
        self.assertEqual(self.spoken(), ["A."])

    def test_new_prompt_silences_that_session(self):
        hub = self.make(duration=2.0, label="never")
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("Long line.")))
        time.sleep(0.05)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B.")))
        hub.on_event(ev("UserPromptSubmit", sid="b", cwd="/w/b"))  # B was only queued: dropped
        started = time.monotonic()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a"))  # A is cut short mid-line
        self.assertEqual(self.spoken(), ["Long line."])
        self.assertLess(time.monotonic() - started, 1.0)

    def test_muted_keeps_state_but_says_nothing(self):
        hub = self.make()
        open(self.cfg.mute_file, "w").close()
        hub.on_event(ev("Stop", last_assistant_message=tag("Quiet.")))
        self.assertEqual(self.spoken(), [])
        self.assertEqual(self.session()["state"], "done")
        self.assertEqual(self.session()["last_speech"], "Quiet.")


class LabelsAndVoices(HubCase):
    def test_no_label_for_a_single_session(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", delta=tag("Hello.")))
        self.assertEqual(self.spoken(), ["Hello."])

    def test_label_when_several_sessions_are_active(self):
        hub = self.make()
        hub.on_event(ev("SessionStart", sid="b", cwd="/work/web_app"))
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/work/api-server", delta=tag("Tests pass.")))
        self.assertEqual(self.spoken(), ["api server. Tests pass."])

    def test_same_project_same_voice_and_live_sessions_differ(self):
        first = self.make()
        first.on_event(ev("SessionStart", sid="a", cwd="/work/alpha"))
        first.on_event(ev("SessionStart", sid="b", cwd="/work/alpha"))  # same folder, second session
        a, b = self.session("a"), self.session("b")
        self.assertEqual((a["name"], b["name"]), ("alpha", "alpha 2"))
        self.assertNotEqual(a["voice"], b["voice"])
        second = self.make()
        second.on_event(ev("SessionStart", sid="z", cwd="/elsewhere/alpha"))
        self.assertEqual(self.session("z")["voice"], a["voice"])

    def test_pinned_voice_from_config(self):
        hub = self.make(voices={"alpha": "bm_george"})
        hub.on_event(ev("SessionStart"))
        self.assertEqual(self.session()["voice"], "bm_george")


class State(HubCase):
    def test_a_turn_from_prompt_to_stop(self):
        hub = self.make()
        hub.on_event(ev("SessionStart"))
        self.assertEqual(self.session()["state"], "idle")
        hub.on_event(ev("UserPromptSubmit"))
        self.assertEqual((self.session()["state"], self.session()["activity"]), ("working", "Thinking"))
        hub.on_event(ev("PreToolUse", tool_name="Bash", tool_input={"command": "npm test", "description": "Run tests"}))
        self.assertEqual(self.session()["activity"], "Run tests")
        hub.on_event(ev("PreToolUse", tool_name="Edit", tool_input={"file_path": "/work/alpha/src/app.py"}))
        self.assertEqual(self.session()["activity"], "Editing app.py")
        hub.on_event(ev("TaskCreated", task_id="1"))
        hub.on_event(ev("TaskCreated", task_id="2"))
        hub.on_event(ev("TaskCompleted", task_id="1"))
        self.assertEqual((self.session()["tasks_done"], self.session()["tasks_total"]), (1, 2))
        hub.on_event(ev("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.session()["state"], "needs_you")
        hub.on_event(ev("Notification", notification_type="idle_prompt"))  # not worth a word
        hub.on_event(ev("PostToolUse", tool_name="Bash"))
        self.assertEqual(self.session()["state"], "working")
        hub.on_event(ev("Stop", last_assistant_message="no tag here"))
        self.assertEqual(self.session()["state"], "done")
        self.assertEqual(self.spoken(), ["I need your input"])

    def test_api_error_is_spoken(self):
        hub = self.make()
        hub.on_event(ev("StopFailure", error="rate_limit"))
        self.assertEqual(self.session()["state"], "failed")
        self.assertEqual(self.spoken(), ["I hit an error: rate limit"])

    def test_session_end_forgets_the_session(self):
        hub = self.make()
        hub.on_event(ev("SessionStart"))
        hub.on_event(ev("SessionEnd", reason="other"))
        self.assertEqual(self.hub.snapshot()["sessions"], [])


class ThroughTheHooks(HubCase):
    """The real hook scripts talking to a hub over its socket."""

    def setUp(self):
        hub = self.make()
        self.server = serve(hub, self.cfg.sock)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def hook(self, script, payload, *args):
        env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp}
        return subprocess.run([os.path.join(ROOT, "hooks", script), *args], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=10)

    def test_socket_is_private(self):
        self.assertEqual(os.stat(self.cfg.sock).st_mode & 0o077, 0)

    def test_display_then_stop(self):
        delta = f"{tag('Pushed and done.')}\nMore text.\n"
        shown = self.hook("display.sh", ev("MessageDisplay", delta=delta))
        self.assertEqual(json.loads(shown.stdout)["hookSpecificOutput"]["displayContent"],
                         "🔊 Pushed and done.\nMore text.\n")
        self.assertEqual(self.hook("speak.sh", ev("Stop", last_assistant_message=delta)).returncode, 0)
        self.assertEqual(self.spoken(), ["Pushed and done."])
        self.assertEqual(self.session()["state"], "done")

    def test_display_without_tag_prints_nothing(self):
        self.assertEqual(self.hook("display.sh", ev("MessageDisplay", delta="plain text\n")).stdout, "")

    def test_report_and_notify(self):
        self.hook("report.sh", ev("PreToolUse", tool_name="Read", tool_input={"file_path": "/x/notes.md"}))
        self.assertEqual(self.session()["activity"], "Reading notes.md")
        self.hook("notify.sh", ev("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.spoken(), ["I need your input"])


if __name__ == "__main__":
    unittest.main()
