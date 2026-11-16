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
import hub as hub_module  # noqa: E402
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


class FakeOverlay:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)

    def of(self, kind):
        return [m for m in self.sent if m["type"] == kind]


class OverlayFeed(HubCase):
    def make(self, **kw):
        hub = super().make(**kw)
        hub.overlay = self.overlay = FakeOverlay()
        return hub

    def test_rows_show_activity_tasks_and_how_the_turn_ended(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit"))
        hub.on_event(ev("TaskCreated", task_id="1"))
        hub.on_event(ev("PreToolUse", tool_name="Bash", tool_input={"description": "Run tests"}))
        row = self.overlay.of("state")[-1]["sessions"][0]
        self.assertEqual((row["name"], row["state"], row["text"], row["meta"]),
                         ("alpha", "working", "Run tests", "0/1 \u00b7 <1m"))
        hub.on_event(ev("Stop", last_assistant_message=tag("All done.")))
        self.spoken()
        row = self.overlay.of("state")[-1]["sessions"][0]
        self.assertEqual((row["state"], row["text"], row["speaking"]), ("done", "All done.", False))

    def test_unchanged_state_is_not_sent_again(self):
        hub = self.make()
        hub.on_event(ev("SessionStart"))
        hub.on_event(ev("SessionStart"))
        hub.publish()
        self.assertEqual(len(self.overlay.of("state")), 1)

    def test_flash_and_speaking_mark_follow_the_voice(self):
        hub = self.make(duration=0.2)
        hub.on_display(ev("MessageDisplay", delta=tag("Tests pass.")))
        time.sleep(0.05)
        flash = self.overlay.of("flash")[-1]
        self.assertEqual((flash["state"], flash["name"], flash["text"]), ("done", "alpha", "Tests pass."))
        self.assertTrue(self.overlay.of("state")[-1]["sessions"][0]["speaking"])
        self.spoken()
        self.assertFalse(self.overlay.of("state")[-1]["sessions"][0]["speaking"])

    def test_muted_voice_still_flashes(self):
        hub = self.make()
        open(self.cfg.mute_file, "w").close()
        hub.on_event(ev("Notification", notification_type="permission_prompt"))
        flash = self.overlay.of("flash")[-1]
        self.assertEqual((flash["state"], flash["text"]), ("needs_you", "I need your input"))

    def test_turn_without_a_spoken_line_flashes_done(self):
        hub = self.make()
        hub.on_event(ev("Stop", last_assistant_message="no tag"))
        self.assertEqual(self.overlay.of("flash")[-1]["text"], "done")

    def test_demo_runs_to_the_end(self):
        import demo
        hub = self.make(label="never")
        demo.run(hub, speed=200)
        spoken = self.spoken()
        self.assertIn("All forty two tests pass.", spoken)
        self.assertIn("I hit an error: rate limit", spoken)
        self.assertEqual(self.hub.snapshot()["sessions"], [])


def ask(sid="s1", description="Run tests", command="npm test", **extra):
    return ev("PermissionRequest", sid=sid, tool_name="Bash",
              tool_input={"command": command, "description": description}, **extra)


class Permissions(HubCase):
    def make(self, **kw):
        hub = super().make(**kw)
        hub.overlay = self.overlay = FakeOverlay()
        self.addCleanup(setattr, hub_module, "MIN_SHOWN", hub_module.MIN_SHOWN)
        hub_module.MIN_SHOWN = 0
        return hub

    def test_request_shows_and_allow_answers_it(self):
        hub = self.make()
        req = hub.request_permission(ask())
        self.assertEqual((self.session()["state"], self.session()["note"]), ("needs_you", "wants to: Run tests"))
        shown = self.overlay.of("request")[-1]
        self.assertEqual((shown["name"], shown["text"], shown["detail"]), ("alpha", "wants to: Run tests", "npm test"))
        self.assertIn("Ctrl+Alt+Y allow", shown["keys"])
        self.assertTrue(hub.decide("allow"))
        self.assertEqual(req.decision, "allow")
        self.assertTrue(req.done.is_set())
        self.assertEqual(self.session()["state"], "working")
        self.assertEqual(self.overlay.of("request")[-1], {"type": "request"})  # cleared
        self.assertEqual(self.spoken(), ["Allowed."])

    def test_a_request_just_shown_cannot_be_answered_yet(self):
        hub = self.make()
        hub_module.MIN_SHOWN = 30
        req = hub.request_permission(ask())
        self.assertFalse(hub.decide("allow"))
        self.assertIsNone(req.decision)

    def test_nothing_waiting_means_nothing_answered(self):
        self.assertFalse(self.make().decide("allow"))

    def test_voice_waits_for_claude_codes_notification_and_names_the_request(self):
        hub = self.make()
        hub.request_permission(ask())
        self.assertEqual(self.spoken(), [])  # you may be answering in the terminal right now
        hub.on_event(ev("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.spoken(), ["Permission needed: Run tests"])

    def test_oldest_request_first_and_deny(self):
        hub = self.make(label="never")
        first = hub.request_permission(ask(sid="a", cwd="/w/a", description="Push"))
        second = hub.request_permission(ask(sid="b", cwd="/w/b", description="Delete logs"))
        self.assertIn("1 more waiting", self.overlay.of("request")[-1]["keys"])
        self.assertTrue(hub.decide("deny"))
        self.assertEqual((first.decision, second.decision), ("deny", None))
        self.assertEqual(self.overlay.of("request")[-1]["text"], "wants to: Delete logs")
        self.assertTrue(hub.decide("allow"))
        self.assertEqual(second.decision, "allow")
        self.assertEqual(self.spoken(), ["Denied.", "Allowed."])

    def test_the_tool_running_means_it_was_answered_in_the_terminal(self):
        hub = self.make()
        req = hub.request_permission(ask())
        hub.on_event(ev("PostToolUse", tool_name="Bash", tool_input={"command": "ls", "description": "List"}))
        self.assertFalse(req.done.is_set())  # a different call
        hub.on_event(ev("PostToolUse", tool_name="Bash", tool_input={"command": "npm test", "description": "Run tests"}))
        self.assertTrue(req.done.is_set())
        self.assertIsNone(req.decision)
        self.assertEqual(self.session()["state"], "working")

    def test_questions_are_not_offered_to_the_hotkeys(self):
        hub = self.make()
        self.assertIsNone(hub.request_permission(ev("PermissionRequest", tool_name="AskUserQuestion", tool_input={})))
        self.assertEqual(self.session()["note"], "has a question for you")
        self.assertEqual(hub.requests, [])


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

    def start_permission_hook(self):
        env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp}
        proc = subprocess.Popen([os.path.join(ROOT, "hooks", "permission.sh")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True, env=env)
        proc.stdin.write(json.dumps(ask()))
        proc.stdin.close()
        proc.stdin = None  # so communicate() only reads
        for _ in range(100):
            if self.hub.requests:
                return proc
            time.sleep(0.05)
        self.fail("the hub never saw the request")

    def test_permission_hook_prints_the_hotkey_decision(self):
        hub_module.MIN_SHOWN, old = 0, hub_module.MIN_SHOWN
        self.addCleanup(setattr, hub_module, "MIN_SHOWN", old)
        proc = self.start_permission_hook()
        self.assertTrue(self.hub.decide("deny"))
        decision = json.loads(proc.communicate(timeout=5)[0])["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("overlay", decision["message"])
        self.spoken()

    def test_permission_hook_prints_nothing_when_answered_in_the_terminal(self):
        self.cfg.permission_grace = 0.3  # no notification arrives: the prompt was answered at once
        proc = self.start_permission_hook()
        self.assertEqual(proc.communicate(timeout=5)[0], "")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.hub.requests, [])
        self.assertEqual(self.session()["state"], "working")

    def test_killed_permission_hook_means_the_turn_was_interrupted(self):
        proc = self.start_permission_hook()
        proc.terminate()  # what Claude Code does when you press Esc on the prompt
        proc.wait(5)
        for _ in range(60):
            if not self.hub.requests:
                break
            time.sleep(0.05)
        self.assertEqual(self.hub.requests, [])
        self.assertEqual((self.session()["state"], self.session()["note"]), ("idle", "interrupted"))

    def test_report_and_notify(self):
        self.hook("report.sh", ev("PreToolUse", tool_name="Read", tool_input={"file_path": "/x/notes.md"}))
        self.assertEqual(self.session()["activity"], "Reading notes.md")
        self.hook("notify.sh", ev("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.spoken(), ["I need your input"])


if __name__ == "__main__":
    unittest.main()
