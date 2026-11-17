"""Hub behaviour with a silent engine: speech order, labels, voices, session state, and the hooks.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests   (any Python 3.10+ works)
"""
import array
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import hub as hub_module  # noqa: E402
from hub import Config, Hub, serve  # noqa: E402
import sounds  # noqa: E402
import terminal  # noqa: E402
from tts import CommandEngine, NullEngine  # noqa: E402


def ev(event, sid="s1", cwd="/work/alpha", **extra):
    return {"hook_event_name": event, "session_id": sid, "cwd": cwd, **extra}


def tag(text):
    return f"<speak>{text}</speak>"


class HubCase(unittest.TestCase):
    def make(self, duration=0.0, **cfg):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.engine = NullEngine(duration)
        self.cfg = Config(run=self.tmp, state=self.tmp, engine="null",
                          mute_file=os.path.join(self.tmp, "voice-off"),
                          sessions_dir=os.path.join(self.tmp, "claude-sessions"), **cfg)
        self.hub = Hub(self.cfg, self.engine)
        self.addCleanup(self.hub.speech.close)
        self.written = []  # (terminal, bytes): what the hub wrote to sessions' terminals; no real one is touched
        self.hub.terminals.write = lambda tty, data: self.written.append((tty, data)) or True
        self.hub.terminals.sleep = lambda seconds: None
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

    def test_a_spoken_follow_up_does_not_silence_the_reply_before_it(self):
        hub = self.make(duration=0.2, label="never")
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A.")))
        time.sleep(0.05)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B, not heard yet.")))
        wake = "<task-notification>\n<summary>Stop hook feedback</summary>\n</task-notification>"
        hub.on_event(ev("UserPromptSubmit", sid="b", cwd="/w/b", prompt=wake))  # said by voice, not typed
        self.assertEqual(self.spoken(), ["A.", "B, not heard yet."])

    def test_our_own_short_answers_do_not_replace_what_a_session_said(self):
        hub = self.make(duration=0.2, label="never")
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A.")))
        time.sleep(0.05)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        with hub.lock:
            hub._say(hub.sessions.by_id["b"], "Sent.", "allowed", "follow-up")
        self.assertEqual(self.spoken(), ["A.", "Sent.", "B is done."])

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

    def test_voice_survives_a_restart_whatever_starts_first(self):
        first = self.make()
        first.on_event(ev("SessionStart", sid="a", cwd="/w/alpha"))
        first.on_event(ev("SessionStart", sid="b", cwd="/w/beta"))
        alpha, beta = self.session("a")["voice"], self.session("b")["voice"]
        state_dir = self.tmp
        second = self.make()
        second.sessions.__init__(self.cfg.voice_pool, {}, os.path.join(state_dir, "voices.json"))
        second.on_event(ev("SessionStart", sid="b2", cwd="/w/beta"))   # the other order this time
        second.on_event(ev("SessionStart", sid="a2", cwd="/w/alpha"))
        self.assertEqual((self.session("a2")["voice"], self.session("b2")["voice"]), (alpha, beta))

    def test_choosing_a_voice_switches_open_sessions_and_is_remembered(self):
        hub = self.make()
        hub.on_event(ev("SessionStart", sid="a", cwd="/w/alpha"))
        hub.sessions.set_voice("alpha", "am_puck")
        self.assertEqual(self.session("a")["voice"], "am_puck")
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/alpha"))
        hub.on_event(ev("SessionStart", sid="a2", cwd="/w/alpha"))
        self.assertEqual(self.session("a2")["voice"], "am_puck")
        self.assertIn("only one voice", hub.set_voice("alpha", "af_heart"))  # the silent test engine

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

    def test_the_layout_key_goes_round_the_layouts(self):
        hub = self.make()
        seen = []
        for _ in range(3):
            hub.on_overlay({"type": "hotkey", "name": "layout"})
            seen.append(hub.cfg.overlay["layout"])
        self.assertEqual(seen, ["island", "bar", "island"])
        self.assertIsNone(hub.set_layout("spiral"))  # not a layout: nothing changes
        self.assertEqual((hub.set_layout("bar"), hub.cfg.overlay["layout"]), ("bar", "bar"))

    def test_every_session_has_its_own_name_color(self):
        import state

        hub = self.make()
        for i in range(4):
            hub.on_event(ev("SessionStart", sid=f"s{i}", cwd=f"/w/project-{i}"))
        colors = [r["color"] for r in self.overlay.of("state")[-1]["sessions"]]
        self.assertEqual(len(set(colors)), 4)
        self.assertTrue(set(colors) <= set(state.COLORS))
        for i in range(4):
            hub.on_event(ev("SessionEnd", sid=f"s{i}", cwd=f"/w/project-{i}"))
        again = Hub(self.cfg, NullEngine())  # the same project gets the same color next time
        self.addCleanup(again.speech.close)
        again.on_event(ev("SessionStart", sid="x", cwd="/w/project-0"))
        self.assertEqual(again.snapshot()["sessions"][0]["color"], colors[0])

    def test_rows_carry_a_short_title_from_the_prompt(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", prompt="fix the flaky login test, then run the whole suite again and tell me\nmore"))
        row = self.overlay.of("state")[-1]["sessions"][0]
        self.assertEqual(row["title"], "Fix the flaky login test, then run the\u2026")

    def title(self):
        self.spoken()
        return self.overlay.of("state")[-1]["sessions"][0]["title"]

    def test_a_session_names_itself_in_its_speak_tag(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", prompt="look at the to-do list with me"))
        out = hub.on_display(ev("MessageDisplay", delta='<speak title="To-do list walkthrough">I ticked the first item.</speak>\nMore.\n'))
        self.assertEqual(out["hookSpecificOutput"]["displayContent"], "🔊 I ticked the first item.\nMore.\n")  # the title is not shown
        self.assertEqual(self.spoken(), ["I ticked the first item."])
        self.assertEqual(self.title(), "To-do list walkthrough")
        hub.on_display(ev("MessageDisplay", delta=tag("Second item done.")))  # a reply without one keeps it
        self.assertEqual(self.title(), "To-do list walkthrough")
        hub.on_display(ev("MessageDisplay", delta="<speak title='Talk key over video'>Fixed the release.</speak>"))
        self.assertEqual(self.title(), "Talk key over video")  # the work moved on, and so does the title

    def test_its_own_title_is_not_replaced_by_claude_codes_name(self):
        hub = self.make()
        os.makedirs(self.cfg.sessions_dir, exist_ok=True)
        hub.on_display(ev("MessageDisplay", delta='<speak title="Overlay key checks">Done.</speak>'))
        with open(os.path.join(self.cfg.sessions_dir, "1.json"), "w") as f:
            json.dump({"pid": os.getpid(), "sessionId": "s1", "status": "idle", "name": "look-at-the-list"}, f)
        hub.reconcile()
        self.assertEqual(self.title(), "Overlay key checks")

    def test_the_title_is_also_read_when_streaming_missed_the_line(self):
        hub = self.make()
        hub.on_event(ev("Stop", last_assistant_message='<speak title="Nightly export">The export ran.</speak>\nDetails.'))
        self.assertEqual(self.spoken(), ["The export ran."])
        self.assertEqual(self.title(), "Nightly export")

    def test_titles_can_be_left_to_the_hub(self):
        hub = self.make(titles="auto")
        hub.on_display(ev("MessageDisplay", delta='<speak title="Overlay key checks">All done here.</speak>'))
        self.assertEqual(self.title(), "All done here.")

    def test_no_spoken_label_while_the_overlay_shows_who_talks(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/alpha"))
        hub.on_event(ev("UserPromptSubmit", sid="b", cwd="/w/beta"))
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/alpha", delta=tag("Tests pass.")))
        self.assertEqual(self.spoken(), ["Tests pass."])
        self.engine.spoken.clear()
        self.overlay.ready = False  # the window is gone: the voice has to say who it is again
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/beta", delta=tag("Build is green.")))
        self.assertEqual(self.spoken(), ["beta. Build is green."])

    def test_the_voice_wave_goes_to_the_session_that_speaks(self):
        class FakeMeter:
            def start(self, on_levels):
                on_levels([0.1, 0.9, 0.4], 0.04)

            def stop(self):
                return 0.25

        hub = self.make()
        self.assertTrue(self.overlay_row(hub)["synth"])  # no meter: the overlay makes up a motion
        hub.speech.meter = FakeMeter()
        hub.on_display(ev("MessageDisplay", delta=tag("Tests pass.")))
        self.spoken()
        wave = self.overlay.of("wave")[-1]
        self.assertEqual((wave["name"], wave["levels"], wave["step"]), ("alpha", [0.1, 0.9, 0.4], 0.04))
        self.assertFalse(self.overlay.of("state")[-1]["sessions"][0]["synth"])
        log, deadline = "", time.time() + 3  # the log line is written just after the queue goes idle
        while "heard=" not in log and time.time() < deadline:
            time.sleep(0.02)
            if os.path.exists(os.path.join(self.tmp, "voice.log")):
                with open(os.path.join(self.tmp, "voice.log")) as f:
                    log = f.read()
        self.assertIn("heard=250ms", log)
        hub.say("Not from a session.")  # nothing to draw it on
        self.spoken()
        self.assertEqual(len(self.overlay.of("wave")), 1)

    def overlay_row(self, hub):
        hub.on_event(ev("SessionStart"))
        return self.overlay.of("state")[-1]["sessions"][0]

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

    def test_history_goes_along_newest_first(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", delta=tag("First.")))
        hub.on_display(ev("MessageDisplay", delta=tag("Second.")))
        self.spoken()
        hub.publish()
        history = self.overlay.of("state")[-1]["history"]
        self.assertEqual([(h["ago"], h["name"], h["text"]) for h in history],
                         [("now", "alpha", "Second."), ("now", "alpha", "First.")])

    def test_history_keeps_some_lines_of_every_session(self):
        hub = self.make(label="never")
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/web", delta=tag("Page built.")))
        for n in range(7):  # one session talks a lot
            hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/api-server", delta=tag(f"Step {n}.")))
            self.spoken()
        hub.publish()
        history = self.overlay.of("state")[-1]["history"]
        self.assertEqual([(h["name"], h["text"]) for h in history],
                         [("api-server", "Step 6."), ("api-server", "Step 5."), ("api-server", "Step 4."),
                          ("api-server", "Step 3."), ("web", "Page built.")])

    def test_a_dragged_position_is_saved_for_next_time(self):
        hub = self.make(config_path=os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "nested", "config.json"))
        with self.subTest("existing settings are kept"):
            os.makedirs(os.path.dirname(self.cfg.config_path))
            with open(self.cfg.config_path, "w") as f:
                json.dump({"label": "always", "overlay": {"opacity": 0.5}}, f)
            hub.on_overlay({"type": "moved", "monitor": 1, "corner": "bottom-left", "offset_x": 40, "offset_y": 12})
            with open(self.cfg.config_path) as f:
                saved = json.load(f)
            self.assertEqual(saved, {"label": "always", "overlay": {"opacity": 0.5, "monitor": 1, "corner": "bottom-left",
                                                                    "offset_x": 40, "offset_y": 12}})
            self.assertEqual(self.cfg.overlay["corner"], "bottom-left")

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


def question(text, *labels, multi=False):
    return {"question": text, "header": text[:10], "multiSelect": multi,
            "options": [{"label": label, "description": label} for label in labels]}


def ask_question(*questions, sid="s1"):
    return ev("PermissionRequest", sid=sid, tool_name="AskUserQuestion", tool_input={"questions": list(questions)})


class Questions(HubCase):
    def make(self, **kw):
        hub = super().make(**kw)
        hub.overlay = self.overlay = FakeOverlay()
        self.addCleanup(setattr, hub_module, "MIN_SHOWN", hub_module.MIN_SHOWN)
        hub_module.MIN_SHOWN = 0
        return hub

    def test_number_keys_answer_each_question_in_turn(self):
        hub = self.make()
        req = hub.request_permission(ask_question(question("Which drink?", "Tea", "Coffee", "Water"),
                                                  question("Which colour?", "Red", "Blue")))
        shown = self.overlay.of("request")[-1]
        self.assertEqual((shown["text"], shown["options"]), ("asks: Which drink?", ["Tea", "Coffee", "Water"]))
        self.assertIn("question 1 of 2", shown["keys"])
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["option1", "option2", "option3"])
        self.assertFalse(hub.decide("allow"))  # a question is not a yes/no
        self.assertFalse(hub.choose(4))  # there is no fourth option
        self.assertTrue(hub.choose(2))
        self.assertFalse(req.done.is_set())
        self.assertEqual(self.overlay.of("request")[-1]["text"], "asks: Which colour?")
        self.assertTrue(hub.choose(1))
        self.assertEqual((req.decision, req.answers), ("answer", {"Which drink?": "Coffee", "Which colour?": "Red"}))
        self.assertEqual(self.session()["state"], "working")
        self.assertEqual(self.spoken()[-1], "Answered: Red.")

    def test_an_open_question_is_shown_again_by_a_window_that_has_just_started(self):
        hub = self.make()
        hub.request_permission(ask_question(question("Which drink?", "Tea", "Coffee", "Water")))
        del self.overlay.sent[:]  # the window was restarted: the new one has been told nothing
        hub.on_overlay({"type": "ready"})
        shown = self.overlay.of("request")[-1]
        self.assertEqual((shown["text"], shown["options"]), ("asks: Which drink?", ["Tea", "Coffee", "Water"]))
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["option1", "option2", "option3"])
        self.assertTrue(hub.choose(2))

    def test_a_question_can_be_answered_in_your_own_words(self):
        hub = self.make(talk_feedback="none")
        req = hub.request_permission(ask_question(question("Which drink?", "Tea", "Coffee"),
                                                  question("Which colour?", "Red", "Blue")))
        hub.follow_up("Neither, water please", session="s1", delay=0)  # what push-to-talk heard
        time.sleep(0.1)
        self.assertEqual(req.answers, {"Which drink?": "Neither, water please"})
        self.assertFalse(req.done.is_set())
        self.assertEqual(self.overlay.of("request")[-1]["text"], "asks: Which colour?")
        hub.follow_up("Green", session="s1", delay=0)
        time.sleep(0.1)
        self.assertEqual((req.decision, req.answers), ("answer", {"Which drink?": "Neither, water please", "Which colour?": "Green"}))
        self.assertEqual(hub.followups.get("s1", []), [])  # the words were the answer, not a message for later
        self.assertEqual(self.session()["state"], "working")

    def test_a_question_answered_in_the_terminal_leaves_the_overlay(self):
        hub = self.make()
        asked = ask_question(question("Which drink?", "Tea", "Coffee"))
        req = hub.request_permission(asked)
        self.assertEqual(self.overlay.of("request")[-1]["text"], "asks: Which drink?")
        answered = {**asked["tool_input"], "answers": {"Which drink?": "Tea"}}  # as Claude Code reports the call that ran
        hub.on_event(ev("PostToolUse", tool_name="AskUserQuestion", tool_input=answered))
        self.assertTrue(req.done.is_set())
        self.assertIsNone(req.decision)
        self.assertEqual(self.overlay.of("request")[-1], {"type": "request"})
        self.assertEqual(self.session()["state"], "working")

    def test_a_waiting_question_is_read_out_with_its_options(self):
        hub = self.make()
        hub.request_permission(ask_question(question("Which drink?", "Tea", "Coffee")))
        self.assertEqual(self.spoken(), [])
        hub.on_event(ev("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.spoken(), ["Question: Which drink? One: Tea. Two: Coffee."])

    def test_questions_the_keys_cannot_answer_are_only_announced(self):
        hub = self.make()
        self.assertIsNone(hub.request_permission(ask_question(question("Pick any", "A", "B", multi=True))))
        self.assertIsNone(hub.request_permission(ask_question(question("Too many", "A", "B", "C", "D", "E"))))
        self.assertEqual(self.session()["note"], "has a question for you")


class CatchingUp(HubCase):
    def test_missed_replays_what_was_said_since_you_were_last_here(self):
        hub = self.make(label="never")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/api-server"))  # you were here
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/api-server", delta=tag("Tests pass.")))
        hub.on_event(ev("StopFailure", sid="b", cwd="/w/web", error="rate_limit"))
        self.spoken()
        self.engine.spoken.clear()
        self.assertEqual(hub.catch_up(), 2)
        self.assertEqual(self.spoken(), ["You missed 2 updates.", "api server. Tests pass.", "web. I hit an error: rate limit"])
        self.engine.spoken.clear()
        self.assertEqual(hub.catch_up(), 0)
        self.assertEqual(self.spoken(), ["Nothing new."])

    def test_repeat_says_the_last_line_again_in_the_same_voice(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", delta=tag("All done.")))
        self.spoken()
        self.assertTrue(hub.repeat())
        self.spoken()
        self.assertEqual(self.engine.spoken[-1], ("All done.", self.session()["voice"]))

    def two_sessions_spoke(self, **cfg):
        hub = self.make(label="never", **cfg)
        hub.overlay = self.overlay = FakeOverlay()
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/api-server", delta=tag("Tests pass.")))
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/web", delta=tag("Page built.")))
        self.spoken()
        self.engine.spoken.clear()
        return hub

    def test_repeat_is_about_the_session_in_focus(self):
        hub = self.two_sessions_spoke()
        self.assertTrue(hub.repeat())  # whoever spoke last has the focus
        self.assertEqual(self.spoken(), ["Page built."])
        hub.focus(-1)  # the wheel moves it to the other one
        self.assertTrue(hub.repeat())
        self.assertEqual(self.spoken()[-1], "Tests pass.")
        self.assertEqual(self.engine.spoken[-1][1], self.session("a")["voice"])

    def test_repeat_shows_at_the_session_like_the_first_time(self):
        hub = self.two_sessions_spoke()
        hub.focus(-1)
        self.overlay.sent.clear()
        hub.repeat()
        self.spoken()
        flash = self.overlay.of("flash")[-1]
        self.assertEqual((flash["name"], flash["text"], flash["state"]), ("api-server", "Tests pass.", "done"))
        self.assertTrue(any(row["speaking"] for m in self.overlay.of("state") for row in m["sessions"]
                            if row["name"] == "api-server"))

    def test_repeat_with_nothing_said_by_the_session_in_focus(self):
        hub = self.two_sessions_spoke()
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/docs"))
        hub.focus(1)
        self.assertEqual(self.hub._target().name, "docs")
        self.assertFalse(hub.repeat())
        self.assertEqual(self.spoken(), ["Nothing from docs yet."])

    def test_repeat_can_be_set_to_the_last_line_anyone_said(self):
        hub = self.two_sessions_spoke(repeat="last")
        hub.focus(-1)
        self.assertTrue(hub.repeat())
        self.assertEqual(self.spoken(), ["Page built."])

    def test_a_replayed_line_of_a_session_that_left_names_it(self):
        hub = self.two_sessions_spoke(repeat="last")
        hub.on_event(ev("SessionEnd", sid="b", cwd="/w/web"))
        self.assertTrue(hub.repeat())
        self.assertEqual(self.spoken(), ["web. Page built."])

    def test_progress_is_spoken_in_long_turns_but_not_often(self):
        hub = self.make(progress_after=0, progress_interval=60)
        hub.on_event(ev("UserPromptSubmit"))
        for task in "123":
            hub.on_event(ev("TaskCreated", task_id=task))
        hub.on_event(ev("TaskCompleted", task_id="1"))
        hub.on_event(ev("TaskCompleted", task_id="2"))  # within the interval: stays quiet
        hub.on_event(ev("TaskCompleted", task_id="3"))  # all done: the final line will say so
        self.assertEqual(self.spoken(), ["1 of 3 steps done"])

    def test_no_progress_talk_in_short_turns_or_short_lists(self):
        hub = self.make()  # default: only after 45 s of work
        hub.on_event(ev("UserPromptSubmit"))
        for task in "123":
            hub.on_event(ev("TaskCreated", task_id=task))
        hub.on_event(ev("TaskCompleted", task_id="1"))
        self.assertEqual(self.spoken(), [])


class FakeRecorder:
    recording = False

    def start(self):
        self.recording = True

    def stop(self, tail=0.0):
        self.recording = False
        return b"\0\0" * 1600


class FakeSounds:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)
        return True


class FakeTranscriber:
    text = "also add a test"
    seconds = 0.0

    def load(self):
        pass

    def unload(self):
        pass

    def transcribe(self, pcm):
        time.sleep(self.seconds)
        return self.text


def wait_for(condition, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


class PushToTalk(HubCase):
    def make(self, **kw):
        hub = super().make(followup_delay=0.05, talk_tail=0, label="never", **kw)
        hub.overlay = self.overlay = FakeOverlay()
        hub.recorder, hub.transcriber = FakeRecorder(), FakeTranscriber()
        self.addCleanup(setattr, hub_module, "TAP", hub_module.TAP)
        hub_module.TAP = 0  # every press in these tests counts as a hold
        hub.on_event(ev("SessionStart", sid="a", cwd="/w/a"))
        hub.on_event(ev("SessionStart", sid="b", cwd="/w/b"))
        return hub

    def talks(self):
        """What the overlay was told about push-to-talk: (step, session, words) in order."""
        return [(m.get("state"), m.get("name", ""), m.get("text", "")) for m in self.overlay.of("talk")]

    def test_hold_to_talk_reaches_the_session_that_spoke_last(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A is done.")))
        self.spoken()
        listener = hub.listen("a")
        self.assertTrue(hub.talk_start())
        self.assertTrue(hub.recorder.recording)
        self.assertIn(("listening", "a", ""), self.talks())
        hub.talk_end()
        self.assertTrue(listener.wake.wait(3), "the follow-up never reached the listener")
        self.assertIn(("ready", "a", "also add a test"), self.talks())
        self.assertEqual(hub.collect(listener), "also add a test")
        self.assertEqual(self.spoken(), ["A is done.", "Sent."])

    def test_a_line_cut_by_the_talk_key_is_said_again_unless_you_were_answering_it(self):
        hub = self.make(duration=0.3, focus_reach_back=0)  # the key is pressed 50 ms into a line here, and means that line
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A is talking.")))
        time.sleep(0.05)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B waits.")))
        hub.talk_target = "b"  # you turn to B while A is still talking
        hub.talk_start()
        time.sleep(0.05)
        hub.talk_end()
        self.assertEqual(self.spoken(), ["A is talking.", "A is talking.", "Queued.", "B waits."])
        self.engine.spoken.clear()
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A again.")))
        time.sleep(0.05)
        hub.talk_start()  # A spoke last, so this answers A: its line was cut on purpose
        time.sleep(0.05)
        hub.talk_end()
        self.assertTrue(wait_for(lambda: len(self.engine.spoken) > 1))
        self.assertEqual(self.spoken(), ["A again.", "Queued."])  # nobody is listening for A: it waits

    def test_a_sound_answers_at_once_instead_of_the_word(self):
        hub = self.make(duration=0.3)
        hub.sounds = FakeSounds()
        to_a = hub.listen("a")
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B talks for a while.")))
        time.sleep(0.05)
        self.assertTrue(hub.follow_up("to a", "a", delay=0))
        self.assertTrue(to_a.wake.wait(3))
        self.assertTrue(wait_for(lambda: hub.sounds.played == ["sent"]))
        self.assertFalse(hub.speech.wait_idle(0.05), "the sound should not have waited for B's line to end")
        self.assertTrue(hub.follow_up("to b", "b", delay=0))  # nobody is listening for B: it waits
        self.assertTrue(wait_for(lambda: hub.sounds.played == ["sent", "queued"]))
        hub.talk_start()
        hub.cancel()
        self.assertEqual(hub.sounds.played, ["sent", "queued", "failed"])
        self.assertEqual(set(self.spoken()), {"B talks for a while."})  # no "Sent." or "Queued." in words

    def test_feedback_can_be_the_word_or_nothing_and_is_quiet_when_the_voice_is_off(self):
        hub = self.make(talk_feedback="voice")
        hub.sounds = FakeSounds()
        hub.listen("a")
        hub.follow_up("one", "a", delay=0)
        self.assertTrue(wait_for(lambda: self.engine.spoken))
        self.assertEqual(self.spoken(), ["Sent."])
        hub.cfg.talk_feedback = "none"
        hub.follow_up("two", "a", delay=0)
        self.assertTrue(wait_for(lambda: len(hub.followups.get("a", [])) == 2))
        hub.cfg.talk_feedback = "sound"
        open(self.cfg.mute_file, "w").close()
        hub.follow_up("three", "a", delay=0)
        self.assertTrue(wait_for(lambda: len(hub.followups.get("a", [])) == 3))
        self.assertEqual((self.spoken(), hub.sounds.played), (["Sent."], []))

    def test_the_sounds_are_short_and_differ(self):
        made = {name: sounds.tone(notes, 0.3) for name, notes in sounds.TONES.items()}
        self.assertEqual(len(set(made.values())), 3)
        for name, pcm in made.items():
            samples = array.array("h", pcm)
            self.assertLess(len(samples) / sounds.RATE, 0.3, name)
            self.assertLess(max(abs(v) for v in samples), 32767 * 0.31, name)
            self.assertGreater(max(abs(v) for v in samples), 32767 * 0.1, name)
            self.assertEqual((abs(samples[0]) < 200, abs(samples[-1]) < 200), (True, True), name)  # no click
        self.assertFalse(sounds.Sounds().play("nothing"))

    def test_a_line_that_starts_while_you_talk_does_not_take_your_words(self):
        hub = self.make(duration=0.3)
        hub.transcriber.seconds = 0.15  # B's line is already being heard when the words come back
        hub.talk_target = "a"
        to_a, to_b = hub.listen("a"), hub.listen("b")
        hub.talk_start()
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        hub.talk_end()
        self.assertTrue(to_a.wake.wait(3), "the follow-up never reached the session it was said to")
        self.assertEqual(hub.collect(to_a), "also add a test")
        self.assertFalse(to_b.wake.is_set())
        self.assertEqual(self.spoken(), ["B is done.", "Sent."])
        self.assertEqual(self.in_focus(), "a")
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B once more.")))
        self.spoken()
        self.assertEqual(self.in_focus(), "b")  # with the talk over, whoever speaks takes the focus again

    def test_time_spent_talking_does_not_make_a_waiting_line_too_old(self):
        hub = self.make(duration=0.0, max_age=0.2)
        hub.talk_start()
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        time.sleep(0.4)
        hub.cancel()
        self.assertEqual(self.spoken(), ["B is done."])

    def test_speech_goes_quiet_while_recording(self):
        hub = self.make(duration=0.3)
        hub.talk_start()
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        time.sleep(0.15)
        self.assertEqual(self.engine.spoken, [])
        hub.cancel()
        self.assertFalse(hub.recorder.recording)
        self.assertEqual(self.spoken(), ["B is done."])
        self.assertEqual(hub.followups, {})

    def test_cancel_takes_a_follow_up_back(self):
        hub = self.make()
        self.assertTrue(hub.follow_up("delete everything", "a", delay=0.2))
        hub.cancel()
        time.sleep(0.35)
        self.assertEqual(hub.followups, {})
        self.assertIn(("failed", "a", "Cancelled"), self.talks())

    def test_cancel_while_the_words_are_being_worked_out_drops_them(self):
        hub = self.make()
        hub.transcriber.seconds = 0.3
        hub.talk_target = "a"
        listener = hub.listen("a")
        hub.talk_start()
        hub.talk_end()
        self.assertIn("cancel", self.overlay.of("keys")[-1]["live"])  # the key stays claimed after letting go
        hub.cancel()
        self.assertEqual(self.talks()[-1], ("failed", "a", "Cancelled"))
        time.sleep(0.6)
        self.assertFalse(listener.wake.is_set())
        self.assertEqual(hub.followups, {})
        self.assertNotIn("sent", [step for step, _, _ in self.talks()])
        hub.talk_start()  # and the next thing said goes out as usual
        hub.talk_end()
        self.assertTrue(listener.wake.wait(3))
        self.assertEqual(hub.collect(listener), "also add a test")

    def test_words_that_wait_are_marked_on_the_light_until_the_session_has_them(self):
        hub = self.make(unsend_seconds=0)
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))  # "a" is in the middle of a reply
        hub.listen("a")
        hub.follow_up("also add a test", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        row = lambda: next(r for r in self.overlay.of("state")[-1]["sessions"] if r["name"] == "a")
        self.assertTrue(wait_for(lambda: row()["waiting"] == 1))
        self.assertIn("1 message waiting", row()["meta"])
        hub.follow_up("and run it", "a", delay=0)
        self.assertTrue(wait_for(lambda: row()["waiting"] == 2))
        self.assertIn("2 messages waiting", row()["meta"])
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Done.")))
        self.assertEqual(row()["waiting"], 2, "the reply ended, but its new listener has not asked yet")
        self.assertEqual(hub.collect(hub.listen("a")), "also add a test and run it")
        self.assertEqual(row()["waiting"], 0)
        self.assertNotIn("waiting", row()["meta"])
        self.assertEqual(self.talks()[-1], ("sent", "a", "also add a test and run it"))

    def test_words_handed_over_at_once_are_never_marked_as_waiting(self):
        hub = self.make()
        hub.listen("a")  # idle and listening
        hub.follow_up("run the tests", "a", delay=0)
        self.assertTrue(wait_for(lambda: ("sent", "a", "run the tests") in self.talks()))
        self.assertEqual([r["waiting"] for m in self.overlay.of("state") for r in m["sessions"] if "waiting" in r and r["waiting"]], [])

    def test_cancel_right_after_sending_takes_waiting_words_back(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))  # "a" is in the middle of a reply
        hub.followups["a"] = ["said earlier"]
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub.followups.get("a") == ["said earlier", "also add a test"]))
        self.assertIn("cancel", self.overlay.of("keys")[-1]["live"])
        hub.cancel()
        self.assertEqual(hub.followups, {"a": ["said earlier"]})
        self.assertEqual(self.talks()[-1], ("failed", "a", "Taken back"))
        hub.cancel()  # a second press has nothing left to take back
        self.assertEqual(hub.followups, {"a": ["said earlier"]})

    def test_cancel_after_the_session_got_the_words_tells_it_to_ignore_them(self):
        hub = self.make()
        hub.talk_target = "a"
        listener = hub.listen("a")
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(listener.wake.wait(3))
        self.assertEqual(hub.collect(listener), "also add a test")
        again = hub.listen("a")
        hub.cancel()
        self.assertTrue(again.wake.wait(3), "the session was not told")
        self.assertEqual(hub.collect(again), hub_module.TAKE_BACK)
        self.assertEqual(self.talks()[-1][:2], ("failed", "a"))

    def test_words_can_only_be_taken_back_for_a_few_seconds(self):
        hub = self.make(unsend_seconds=0.2)
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub.followups.get("a") == ["also add a test"]))
        self.assertTrue(wait_for(lambda: "cancel" not in self.overlay.of("keys")[-1]["live"]),
                        "the cancel key was not given back")
        hub.cancel()
        self.assertEqual(hub.followups, {"a": ["also add a test"]})

    def test_speaking_again_ends_the_time_to_take_words_back(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub.followups.get("a") == ["also add a test"]))
        hub.talk_start()
        hub.cancel()  # throws away the new recording, not what went out before
        hub.cancel()
        self.assertEqual(hub.followups, {"a": ["also add a test"]})

    def test_a_quick_tap_can_be_set_to_pick_the_next_session(self):
        hub = self.make(talk_tap="next")
        hub_module.TAP = 30
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertEqual(hub.talk_target, "b")
        self.assertIn(("focus", "b", ""), self.talks())
        self.assertFalse(wait_for(lambda: hub.followups, 0.2))

    def test_a_quick_tap_does_nothing_by_itself(self):
        hub = self.make()
        hub_module.TAP = 30
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertEqual(hub.talk_target, "a")
        self.assertFalse(wait_for(lambda: hub.followups, 0.2))

    def test_the_arrow_keys_move_the_focus_and_are_only_claimed_with_several_sessions(self):
        hub = self.make()  # two sessions, a and b
        hub.publish()
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["focus_next", "focus_prev"])
        hub.talk_target = "a"
        hub.on_overlay({"type": "hotkey", "name": "focus_next"})
        self.assertEqual(hub.talk_target, "b")
        hub.on_overlay({"type": "hotkey", "name": "focus_next"})  # the last one: it stops there
        self.assertEqual(hub.talk_target, "b")
        hub.on_overlay({"type": "hotkey", "name": "focus_prev"})
        self.assertEqual(hub.talk_target, "a")
        hub.on_event(ev("SessionEnd", sid="b", cwd="/w/b"))
        hub.publish()
        self.assertEqual(self.overlay.of("keys")[-1]["live"], [])

    def test_what_is_on_screen_follows_the_focus(self):
        hub = self.make()
        hub.talk_target = "a"
        hub.talk_start()
        self.assertEqual(self.talks()[-1], ("listening", "a", ""))
        hub.focus(1)  # the wheel, while the talk key is still held
        self.assertEqual(self.talks()[-1], ("listening", "b", ""))
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub.followups.get("b") == ["also add a test"]))
        self.assertIn(("sent", "b", "also add a test"), self.talks())

    def test_moving_the_focus_after_letting_go_does_not_take_the_words_along(self):
        hub = self.make()
        hub.transcriber.seconds = 0.15  # the words are still being worked out when the focus moves
        hub.talk_target = "a"
        to_a, to_b = hub.listen("a"), hub.listen("b")
        hub.talk_start()
        hub.talk_end()
        hub.focus(1)  # on to the next session, right after letting go
        self.assertTrue(to_a.wake.wait(3), "the follow-up never reached the session it was said to")
        self.assertEqual(hub.collect(to_a), "also add a test")
        self.assertFalse(to_b.wake.is_set())
        self.assertIn(("sent", "a", "also add a test"), self.talks())
        self.assertEqual(self.in_focus(), "b")  # the focus stays where you put it

    def test_moving_the_focus_in_the_tail_of_the_recording_does_not_take_the_words_along(self):
        hub = self.make()
        hub.cfg.talk_tail = 0.3  # the recorder goes on for a moment after the key is up
        in_tail, stop = threading.Event(), hub.recorder.stop

        def slow_stop(tail=0.0):
            in_tail.set()
            time.sleep(tail)
            return stop()

        hub.recorder.stop = slow_stop
        hub.talk_target = "a"
        to_a, to_b = hub.listen("a"), hub.listen("b")
        hub.talk_start()
        ending = threading.Thread(target=hub.talk_end)
        ending.start()
        self.assertTrue(in_tail.wait(3))
        hub.focus(1)  # while the last word is still being recorded
        ending.join(3)
        self.assertTrue(to_a.wake.wait(3), "the follow-up never reached the session it was said to")
        self.assertEqual(hub.collect(to_a), "also add a test")
        self.assertFalse(to_b.wake.is_set())
        self.assertNotIn(("listening", "b", ""), self.talks())
        self.assertEqual(self.in_focus(), "b")

    def test_words_for_a_session_that_ended_meanwhile_go_to_nobody(self):
        hub = self.make()
        hub.transcriber.seconds = 0.15
        hub.talk_target = "a"
        to_b = hub.listen("b")
        hub.talk_start()
        hub.talk_end()
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a"))
        self.assertTrue(wait_for(lambda: self.talks()[-1][0] == "failed"))
        self.assertFalse(to_b.wake.is_set())
        self.assertEqual(hub.followups, {})

    def test_the_microphone_is_shown_while_listening(self):
        hub = self.make()
        hub._mic_heard(bytes(1600))
        self.assertEqual(self.overlay.of("mic")[-1], {"type": "mic", "levels": [0.0], "step": 0.05})

    def test_what_was_said_to_a_busy_session_survives_a_hub_restart(self):
        hub = self.make()
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()  # nobody is listening for "a": it is in the middle of a reply
        self.assertTrue(wait_for(lambda: hub.followups.get("a") == ["also add a test"]))
        self.assertIn(("queued", "a", "also add a test"), self.talks())
        again = Hub(self.cfg, NullEngine())  # the hub is restarted before that reply ends
        self.addCleanup(again.speech.close)
        listener = again.listen("a")
        self.assertTrue(listener.wake.is_set())
        self.assertEqual(again.collect(listener), "also add a test")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "followups.json")))  # delivered: nothing left on disk

    def test_silence_sends_nothing(self):
        hub = self.make()
        hub.transcriber.text = ""
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: ("failed", "b", "Didn't catch that") in self.talks()))  # b: the newest session
        self.assertEqual(hub.followups, {})

    def test_follow_up_waits_for_a_session_with_no_listener_yet(self):
        hub = self.make()
        hub.follow_up("run the tests", "b", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("b")))
        listener = hub.listen("b")  # armed when the session next stops
        self.assertTrue(listener.wake.is_set())
        self.assertEqual(hub.collect(listener), "run the tests")

    def test_words_for_a_busy_session_wait_and_go_out_when_it_is_interrupted(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a"))
        listener = hub.listen("a")  # the listener a session has from the moment a prompt is sent
        hub.follow_up("stop, do the other thing", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        hub.reconcile()
        self.assertFalse(listener.wake.is_set())  # in the middle of its reply: not now
        self.assertIn("queued", [t[0] for t in self.talks()])
        hub.on_event(ev("PostToolUse", sid="a", cwd="/w/a", tool_name="Bash", is_interrupt=True))  # Esc; no Stop follows
        hub.reconcile()
        self.assertTrue(listener.wake.is_set())
        self.assertEqual(hub.collect(listener), "stop, do the other thing")

    def test_words_for_an_interrupted_session_are_sent_at_once(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a"))
        listener = hub.listen("a")
        hub.on_event(ev("PostToolUse", sid="a", cwd="/w/a", tool_name="Bash", is_interrupt=True))
        hub.follow_up("are you there", "a", delay=0)
        self.assertTrue(wait_for(listener.wake.is_set))
        self.assertEqual(hub.collect(listener), "are you there")

    def test_a_listener_that_starts_in_the_middle_of_a_reply_waits_for_its_end(self):
        hub = self.make()
        hub.follow_up("one more thing", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a"))  # you typed something else meanwhile
        listener = hub.listen("a")
        self.assertFalse(listener.wake.is_set())
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Done.")))
        hub.reconcile()
        self.assertTrue(listener.wake.is_set())

    def test_a_newer_listener_replaces_the_older_one(self):
        hub = self.make()
        old, new = hub.listen("a"), hub.listen("a")
        self.assertTrue(old.wake.is_set())
        self.assertIsNone(hub.collect(old))
        self.assertFalse(new.wake.is_set())

    def test_a_follow_up_is_sent_without_a_second_tap(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", permission_mode="bypassPermissions"))
        hub.on_event(ev("Stop", sid="a", cwd="/w/a"))  # its turn is over: it can be spoken to at once
        hub.talk_target = "a"
        listener = hub.listen("a")
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(listener.wake.wait(2))
        self.assertEqual(hub.collect(listener), "also add a test")
        self.assertIn(("sent", "a", "also add a test"), self.talks())  # a receipt to glance at

    def test_with_confirming_on_an_unattended_session_needs_a_tap(self):
        hub = self.make(followup_confirm="auto")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", permission_mode="bypassPermissions"))
        hub.on_event(ev("Stop", sid="a", cwd="/w/a"))  # its turn is over: it can be spoken to at once
        hub.talk_target = "a"
        listener = hub.listen("a")
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub._pending is not None))
        self.assertIn("tap Ctrl+Alt+Space to send", self.overlay.of("talk")[-1]["hint"])
        time.sleep(0.2)  # well past followup_delay: it must still be waiting
        self.assertFalse(listener.wake.is_set())
        hub_module.TAP = 30  # the next press is a tap
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(listener.wake.wait(2))
        self.assertEqual(hub.collect(listener), "also add a test")

    def test_unconfirmed_follow_up_is_dropped_not_sent(self):
        hub = self.make(followup_confirm=True)
        self.addCleanup(setattr, hub_module, "CONFIRM_WINDOW", hub_module.CONFIRM_WINDOW)
        hub_module.CONFIRM_WINDOW = 0.1
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: "Not sent" in [text for _, _, text in self.talks()]))
        self.assertEqual(hub.followups, {})

    def test_typed_follow_up_and_prompting_session_send_without_a_tap(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", permission_mode="default"))
        self.assertFalse(hub._needs_confirmation(hub.sessions.by_id["a"]))
        hub.on_event(ev("UserPromptSubmit", sid="b", cwd="/w/b", permission_mode="auto"))
        hub.follow_up("typed in a shell", "b", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("b")))

    def test_list_marks_who_a_follow_up_goes_to(self):
        hub = self.make()
        hub.talk_target = "b"
        hub.publish()
        self.assertEqual(self.in_focus(), "b")

    def in_focus(self):
        marked = [r["name"] for r in self.overlay.of("state")[-1]["sessions"] if r["target"]]
        self.assertEqual(len(marked), 1)
        return marked[0]

    def test_the_wheel_moves_the_focus_and_whoever_speaks_takes_it(self):
        hub = self.make()
        hub.talk_target = "a"
        hub.on_overlay({"type": "hotkey", "name": "focus_next"})
        self.assertEqual(self.in_focus(), "b")
        hub.on_overlay({"type": "hotkey", "name": "focus_next"})  # already on the last one: it stays there
        self.assertEqual(self.in_focus(), "b")
        hub.on_overlay({"type": "hotkey", "name": "focus_prev"})
        self.assertEqual(self.in_focus(), "a")
        hub.on_overlay({"type": "hotkey", "name": "focus_prev"})  # and it stays on the first one
        self.assertEqual(self.in_focus(), "a")
        hub.on_overlay({"type": "hotkey", "name": "focus_next"})
        self.assertEqual(self.in_focus(), "b")
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("Done here.")))
        self.assertTrue(hub.speech.wait_idle(5))
        self.assertEqual(self.in_focus(), "a")  # it spoke last, so a follow-up answers it

    def test_a_session_that_starts_speaking_as_the_key_goes_down_does_not_get_the_words(self):
        hub = self.make(duration=0.3)
        hub.talk_target = "a"  # you are about to speak to A
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        self.assertTrue(wait_for(lambda: hub.talk_target == "b"))  # B began to speak and took the focus
        hub.talk_start()  # your finger was already on its way
        self.assertEqual(self.talks()[-1][:2], ("listening", "a"))
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub.followups.get("a") or ("sent", "a", "also add a test") in self.talks()))
        self.assertFalse(hub.followups.get("b"))

    def test_after_a_moment_the_talk_key_goes_to_the_session_that_spoke(self):
        hub = self.make(focus_reach_back=0.05)
        hub.talk_target = "a"
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B is done.")))
        self.assertTrue(hub.speech.wait_idle(5))
        time.sleep(0.1)  # long enough to have heard who is speaking
        hub.talk_start()
        self.assertEqual(self.talks()[-1][:2], ("listening", "b"))

    def test_overlay_claims_keys_only_while_they_can_act(self):
        hub = self.make()
        hub.publish()
        arrows = ["focus_next", "focus_prev"]  # there are two sessions to move between
        self.assertEqual(self.overlay.of("keys")[-1]["live"], arrows)
        hub.request_permission(ask(sid="a", cwd="/w/a"))
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "deny"] + arrows)
        hub.talk_start()
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "cancel", "deny"] + arrows)


class SpokenLanguages(unittest.TestCase):
    def test_which_languages_a_model_listens_for(self):
        import stt

        self.assertEqual(stt.Transcriber("small.en", "it").languages, ["en"])  # an English-only model
        self.assertEqual(stt.Transcriber("small", "it").languages, ["it"])
        self.assertEqual(stt.Transcriber("small", "en, IT").languages, ["en", "it"])
        self.assertEqual(stt.Transcriber("small", ["en", "it"]).languages, ["en", "it"])
        self.assertEqual(stt.Transcriber("small", "auto").languages, [])  # any language

    def test_a_recording_is_taken_as_the_likeliest_of_your_languages(self):
        import stt

        class Model:
            asked = None

            def detect_language(self, audio):
                return "cy", 0.5, [("cy", 0.5), ("it", 0.3), ("en", 0.1)]  # a short clip mistaken for Welsh

            def transcribe(self, audio, language, **options):
                Model.asked = language
                return [types.SimpleNamespace(text=" Ciao Claude. ")], types.SimpleNamespace(language=language)

        listener = stt.Transcriber("small", "en,it")
        listener._model = Model()
        self.assertEqual(listener.transcribe(bytes(3200)), "Ciao Claude.")
        self.assertEqual((Model.asked, listener.heard), ("it", "it"))


class Loudness(unittest.TestCase):
    def test_loudness_is_relative_to_the_loudest_moment_lately(self):
        import array
        import math
        from tts import Meter

        def tone(amplitude):
            return array.array("h", [int(amplitude * 32767 * math.sin(i / 3)) for i in range(320)]).tobytes()

        meter = Meter()
        self.assertEqual(meter.level(bytes(640)), 0.0)  # silence
        self.assertEqual(meter.level(tone(0.3)), 1.0)  # the loudest so far
        self.assertTrue(0.3 < meter.level(tone(0.1)) < 0.6)
        self.assertEqual(meter.level(tone(0.3)), 1.0)
        self.assertEqual(meter.level(tone(0.0005)), 0.0)  # hiss does not count as sound


class ClaudeCodesOwnRecords(HubCase):
    """Claude Code's session files tell the hub what no hook reports."""

    def record(self, sid, status, pid=None, seconds_ago=10, **more):
        os.makedirs(self.cfg.sessions_dir, exist_ok=True)
        pid = pid or os.getpid()
        with open(os.path.join(self.cfg.sessions_dir, f"{pid}.json"), "w") as f:
            json.dump({"pid": pid, "sessionId": sid, "status": status,
                       "statusUpdatedAt": (time.time() - seconds_ago) * 1000, **more}, f)

    def quiet_for(self, seconds, sid="s1"):
        self.hub.sessions.by_id[sid].updated -= seconds

    def test_esc_leaves_no_event_but_the_session_shows_idle(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit"))
        req = hub.request_permission(ask())
        self.record("s1", "idle")
        hub.reconcile()
        self.assertEqual(self.session()["state"], "needs_you")  # too soon after its last event to judge
        self.quiet_for(10)
        hub.reconcile()
        self.assertEqual((self.session()["state"], self.session()["note"]), ("idle", "interrupted"))
        self.assertTrue(req.done.is_set())

    def test_a_busy_session_is_left_alone(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit"))
        self.record("s1", "busy")
        self.quiet_for(600)
        hub.reconcile()
        self.assertEqual(self.session()["state"], "working")

    def test_a_closed_terminal_removes_the_session(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit"))
        self.record("s1", "busy")
        hub.reconcile()
        os.remove(os.path.join(self.cfg.sessions_dir, f"{os.getpid()}.json"))
        self.quiet_for(10)
        hub.reconcile()
        self.assertEqual(hub.snapshot()["sessions"], [])

    def test_claude_codes_name_for_a_session_becomes_its_title(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", prompt="what is this project about?"))
        self.assertEqual(self.session()["title"], "What is this project about?")
        self.record("s1", "busy", name="eyes-free-claude-speaks")
        hub.reconcile()
        self.assertEqual(self.session()["title"], "Eyes free claude speaks")
        hub.on_event(ev("UserPromptSubmit", prompt="something else"))  # a later prompt does not replace the name
        self.assertEqual(self.session()["title"], "Eyes free claude speaks")

    def test_a_placeholder_name_is_not_a_title(self):
        hub = self.make()  # at start Claude Code calls a session after its folder plus two letters
        hub.on_event(ev("UserPromptSubmit", prompt="what is this project about?"))
        self.record("s1", "busy", name="proj-3f", nameSource="derived")
        hub.reconcile()
        self.assertEqual(self.session()["title"], "What is this project about?")
        self.record("s1", "busy", name="project-tour", nameSource="auto")
        hub.reconcile()
        self.assertEqual(self.session()["title"], "Project tour")

    def test_the_first_reply_names_a_session_claude_code_has_not_named(self):
        hub = self.make()
        wake = "<task-notification>\n<summary>Stop hook feedback</summary>\n</task-notification>"
        hub.on_event(ev("UserPromptSubmit", prompt=wake))  # how a spoken follow-up reaches Claude
        self.assertEqual(self.session()["title"], "")  # markup is no one's words, so wait for the reply
        hub.on_display(ev("MessageDisplay", delta=tag("I added the phone idea to the list.") + "\n"))
        self.assertEqual(self.session()["title"], "I added the phone idea to the list.")
        hub.on_event(ev("Stop", last_assistant_message=tag("I added the phone idea to the list.")))
        hub.on_event(ev("UserPromptSubmit", prompt="now something else entirely"))
        hub.on_display(ev("MessageDisplay", delta=tag("Done with the other thing.") + "\n"))
        self.assertEqual(self.session()["title"], "I added the phone idea to the list.")  # it stays
        self.record("s1", "busy", name="phone-ideas", nameSource="auto")
        hub.reconcile()
        self.assertEqual(self.session()["title"], "Phone ideas")  # Claude Code's own name still wins

    def test_a_reply_that_only_reached_the_stop_event_names_the_session_too(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", prompt="<task-notification>"))
        hub.on_event(ev("Stop", last_assistant_message=tag("The tests pass.")))
        self.assertEqual(self.session()["title"], "The tests pass.")

    def test_a_dead_process_counts_as_gone_and_sessions_without_a_file_are_kept(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit"))
        hub.on_event(ev("UserPromptSubmit", sid="demo", cwd="/w/demo"))  # never had a file
        self.record("s1", "busy")
        hub.reconcile()
        dead = subprocess.Popen(["true"])
        dead.wait()
        os.remove(os.path.join(self.cfg.sessions_dir, f"{os.getpid()}.json"))
        self.record("s1", "busy", pid=dead.pid)
        self.quiet_for(10)
        self.quiet_for(10, "demo")
        hub.reconcile()
        self.assertEqual([s["id"] for s in hub.snapshot()["sessions"]], ["demo"])


class AcrossARestart(HubCase):
    """A restarted hub knows its sessions again: who is who must not depend on who reports first."""

    def restart(self):
        self.hub = Hub(self.cfg, NullEngine())
        self.addCleanup(self.hub.speech.close)
        return self.hub

    def record(self, sid, status, pid):
        os.makedirs(self.cfg.sessions_dir, exist_ok=True)
        with open(os.path.join(self.cfg.sessions_dir, f"{pid}.json"), "w") as f:
            json.dump({"pid": pid, "sessionId": sid, "status": status,
                       "statusUpdatedAt": (time.time() - 90) * 1000}, f)

    def who(self):
        return [(s["id"], s["name"], s["color"], s["voice"]) for s in self.hub.snapshot()["sessions"]]

    def three(self):
        hub = self.make()
        for sid in "abc":
            hub.on_event(ev("SessionStart", sid=sid))
        return hub

    def test_a_color_that_is_no_longer_handed_out_is_replaced(self):
        import state

        hub = self.three()
        hub.on_display(ev("MessageDisplay", sid="b", delta=tag("Page built.")))
        self.spoken()
        hub.publish()
        before = self.who()
        path = hub._sessions_file()
        with open(path) as f:
            kept = json.load(f)
        for entry in kept["sessions"] + kept["history"]:  # as written by a hub with another list of colors
            if entry.get("session", entry.get("id")) == "b":
                entry["color"] = "#F27FFF"
        with open(path, "w") as f:
            json.dump(kept, f)
        again = self.restart()
        for sid in "cba":
            again.on_event(ev("SessionStart", sid=sid))
        after = self.who()
        self.assertEqual([(i, n, v) for i, n, c, v in after], [(i, n, v) for i, n, c, v in before])
        colors = [c for _, _, c, _ in after]
        self.assertEqual((colors[0], colors[2]), (before[0][2], before[2][2]))  # the others keep theirs
        self.assertIn(colors[1], state.COLORS)
        self.assertEqual(len(set(colors)), 3)
        self.assertEqual([h["color"] for h in again.history], [colors[1]])  # and its old lines follow

    def test_what_was_said_can_still_be_repeated_after_a_restart(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", sid="a", delta=tag("Tests pass.")))
        hub.on_display(ev("MessageDisplay", sid="b", delta=tag("Page built.")))
        self.spoken()
        hub.publish()
        again = self.restart()
        again.on_event(ev("SessionStart", sid="a"))
        again.on_event(ev("SessionStart", sid="b"))
        again.talk_target = "a"
        self.assertTrue(again.repeat())
        self.assertTrue(again.speech.wait_idle(5))
        self.assertEqual([e["text"] for e in again.history], ["Tests pass.", "Page built."])

    def test_sessions_of_one_project_do_not_swap_names_colors_and_voices(self):
        self.three()
        before = self.who()
        self.assertEqual([name for _, name, _, _ in before], ["alpha", "alpha 2", "alpha 3"])
        hub = self.restart()
        self.assertEqual(self.who(), [])  # no session files here: nobody is known to be alive
        for sid in "cab":  # they report in another order than they started in
            hub.on_event(ev("PreToolUse", sid=sid, tool_name="Read", tool_input={}))
        self.assertEqual(self.who(), before)

    def test_a_new_session_does_not_take_what_belongs_to_one_that_is_not_back_yet(self):
        self.three()
        before = self.who()
        hub = self.restart()
        hub.on_event(ev("SessionStart", sid="new"))
        new = self.who()[0]
        self.assertEqual(new[1], "alpha 4")
        self.assertNotIn(new[2], [color for _, _, color, _ in before])
        self.assertNotIn(new[3], [voice for _, _, _, voice in before])
        for sid in "cba":
            hub.listen(sid)
        self.assertEqual(self.who(), before + [new])  # and it stays last in the bar

    def test_a_second_restart_before_everyone_is_back_forgets_nobody(self):
        self.three()
        before = self.who()
        self.restart().on_event(ev("PreToolUse", sid="b", tool_name="Read", tool_input={}))
        hub = self.restart()
        for sid in "cba":
            hub.listen(sid)
        self.assertEqual(self.who(), before)

    def test_sessions_claude_code_still_lists_are_back_at_once(self):
        hub = self.three()
        hub.on_event(ev("UserPromptSubmit", sid="a", prompt="tidy the readme"))
        hub.on_event(ev("Stop", sid="a", last_assistant_message=tag("Readme tidied.")))
        hub.on_event(ev("UserPromptSubmit", sid="b", prompt="run the tests"))
        self.spoken()  # "a" spoke last and has the focus, until it is moved by hand
        hub.talk_target = "b"
        self.record("a", "idle", os.getpid())
        self.record("b", "busy", os.getppid())
        # A third process that is surely running (the next process id only was by chance: the
        # test failed once nothing happened to have it). Removed below: that session has ended.
        self.record("c", "idle", 1)
        hub.reconcile()
        hub.publish()
        before = self.who()
        os.unlink(os.path.join(self.cfg.sessions_dir, "1.json"))
        hub = self.restart()
        self.assertEqual(self.who(), before[:2])  # "c" had a session file and has none now: it ended
        a, b = self.session("a"), self.session("b")
        self.assertEqual((a["state"], a["note"], a["title"]), ("done", "Readme tidied.", "Readme tidied."))
        self.assertEqual((b["state"], b["activity"], b["title"]), ("working", "Thinking", "Run the tests"))
        self.assertGreater(b["turn_seconds"], 80)  # the turn's clock did not start again
        self.assertEqual(hub.talk_target, "b")
        hub.on_event(ev("SessionStart", sid="c2"))
        self.assertEqual(self.session("c2")["name"], "alpha 3")  # the name of the one that ended is free

    def test_an_ended_session_is_not_brought_back(self):
        hub = self.three()
        hub.on_event(ev("SessionEnd", sid="b"))
        self.restart()
        for sid in "ac":
            self.hub.listen(sid)
        self.assertEqual([sid for sid, _, _, _ in self.who()], ["a", "c"])
        self.assertNotIn("b", self.hub.sessions.kept)

    def test_what_is_kept_is_private_and_goes_stale(self):
        self.three()
        path = os.path.join(self.tmp, "sessions.json")
        self.assertEqual(os.stat(path).st_mode & 0o077, 0)
        old = time.time() - 7 * 3600
        os.utime(path, (old, old))
        self.assertEqual(self.restart().sessions.kept, {})


class OtherVoices(unittest.TestCase):
    def test_a_system_voice_speaks_and_can_be_cut_short(self):
        said = os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "said")
        engine = CommandEngine(lambda text: ["sh", "-c", 'echo "$0" > "$1"; sleep 5', text, said])
        engine.arm()
        threading.Timer(0.3, engine.stop).start()
        started = time.monotonic()
        engine.speak(["alpha.", "Tests pass."], "ignored")
        self.assertLess(time.monotonic() - started, 3)
        with open(said) as f:
            self.assertEqual(f.read().strip(), "alpha. Tests pass.")


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

    def test_permission_hook_hands_claude_the_chosen_option(self):
        hub_module.MIN_SHOWN, old = 0, hub_module.MIN_SHOWN
        self.addCleanup(setattr, hub_module, "MIN_SHOWN", old)
        env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp}
        proc = subprocess.Popen([os.path.join(ROOT, "hooks", "permission.sh")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True, env=env)
        proc.stdin.write(json.dumps(ask_question(question("Which drink?", "Tea", "Coffee"))))
        proc.stdin.close()
        proc.stdin = None
        self.assertTrue(wait_for(lambda: self.hub.requests))
        self.assertTrue(self.hub.choose(2))
        decision = json.loads(proc.communicate(timeout=5)[0])["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "allow")
        self.assertEqual(decision["updatedInput"]["answers"], {"Which drink?": "Coffee"})
        self.assertEqual(len(decision["updatedInput"]["questions"]), 1)
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
        proc.stdout.close()
        for _ in range(60):
            if not self.hub.requests:
                break
            time.sleep(0.05)
        self.assertEqual(self.hub.requests, [])
        self.assertEqual((self.session()["state"], self.session()["note"]), ("idle", "interrupted"))

    def start_listener_hook(self):
        env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp}
        proc = subprocess.Popen([os.path.join(ROOT, "hooks", "listen.sh")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        proc.stdin.write(json.dumps(ev("Stop")))
        proc.stdin.close()
        proc.stdin = None
        self.assertTrue(wait_for(lambda: "s1" in self.hub.listeners), "the hub never saw the listener")
        return proc

    def test_listener_hook_wakes_claude_with_the_follow_up(self):
        self.hub.on_event(ev("SessionStart"))
        proc = self.start_listener_hook()
        self.hub.follow_up("run the tests again", "s1", delay=0)
        out, err = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 2)  # exit 2 is what wakes an idle session
        self.assertIn('"run the tests again"', err)
        self.assertEqual(out, "")
        self.assertEqual(os.listdir(self.tmp).count("listen"), 0)
        self.assertFalse([f for f in os.listdir(self.tmp) if f.startswith("listen.")])
        self.spoken()

    def test_listener_hook_exits_quietly_when_the_session_ends(self):
        self.hub.on_event(ev("SessionStart"))
        proc = self.start_listener_hook()
        self.hub.on_event(ev("SessionEnd"))
        out, err = proc.communicate(timeout=5)
        self.assertEqual((proc.returncode, out, err), (0, "", ""))

    def test_report_and_notify(self):
        self.hook("report.sh", ev("PreToolUse", tool_name="Read", tool_input={"file_path": "/x/notes.md"}))
        self.assertEqual(self.session()["activity"], "Reading notes.md")
        self.hook("notify.sh", ev("Notification", notification_type="permission_prompt"))
        self.assertEqual(self.spoken(), ["I need your input"])


class OwnTerminals(HubCase):
    """Each session's terminal is marked, so the terminals can be told apart like the lights."""

    def make(self, **kw):
        hub = super().make(**kw)
        self.ttys = {}  # pid -> the terminal that process is said to run in
        real = terminal.tty_of
        terminal.tty_of = lambda pid: self.ttys.get(pid, "")
        self.addCleanup(setattr, terminal, "tty_of", real)
        return hub

    def open(self, sid, pid, tty, cwd="/work/alpha"):
        """A session in its own terminal, known to Claude Code and to the hub."""
        os.makedirs(self.cfg.sessions_dir, exist_ok=True)
        with open(os.path.join(self.cfg.sessions_dir, f"{pid}.json"), "w") as f:
            json.dump({"pid": pid, "sessionId": sid, "status": "idle", "statusUpdatedAt": time.time() * 1000}, f)
        self.ttys[pid] = tty
        self.hub.on_event(ev("SessionStart", sid=sid, cwd=cwd))
        self.hub.reconcile()
        self.hub.publish()

    def tint(self, sid, amount):
        color = self.hub.sessions.by_id[sid].color
        return f"\x1b]11;{terminal.mix('#181818', color, amount)}\x1b\\".encode()

    def last(self, tty):
        return [data for t, data in self.written if t == tty][-1]

    def test_the_session_in_focus_tints_its_terminal_and_the_others_stay_plain(self):
        self.make()
        me, other = os.getpid(), os.getppid()
        self.open("a", me, "/dev/pts/91")
        self.assertEqual(self.written, [("/dev/pts/91", terminal.RESET)])  # alone: nothing to tell apart
        self.open("b", other, "/dev/pts/92")
        self.assertEqual(self.hub._target().id, "b")
        self.assertEqual(self.last("/dev/pts/92"), self.tint("b", 0.08))
        self.assertEqual(self.last("/dev/pts/91"), terminal.RESET)
        count = len(self.written)
        self.hub.publish()
        self.assertEqual(len(self.written), count, "nothing changed, so nothing is written")

    def test_moving_the_focus_moves_the_tint_and_lights_the_new_terminal_up(self):
        hub = self.make()
        self.open("a", os.getpid(), "/dev/pts/91")
        self.open("b", os.getppid(), "/dev/pts/92")
        del self.written[:]
        hub.focus(-1)
        for thread in threading.enumerate():
            if thread.name == "terminal-pulse":
                thread.join(5)
        to_a = [data for tty, data in self.written if tty == "/dev/pts/91"]
        self.assertEqual(to_a[0], self.tint("a", 0.08))  # at once
        self.assertEqual(to_a[1], self.tint("a", 0.15))  # then a little brighter
        self.assertEqual(to_a[-1], self.tint("a", 0.08))  # and back to its resting tint
        self.assertEqual(len(to_a), terminal.PULSE_STEPS + 2)
        self.assertEqual([data for tty, data in self.written if tty == "/dev/pts/92"], [terminal.RESET])

    def test_a_session_that_ends_gets_its_terminal_back(self):
        hub = self.make()
        self.open("a", os.getpid(), "/dev/pts/91")
        self.open("b", os.getppid(), "/dev/pts/92")
        hub.on_event(ev("SessionEnd", sid="b"))
        self.assertEqual(self.last("/dev/pts/92"), terminal.RESET)
        self.assertEqual(self.last("/dev/pts/91"), terminal.RESET)  # one session left: no tint

    def test_every_terminal_can_wear_its_color_and_it_can_be_turned_off(self):
        hub = self.make(config_path=os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "config.json"))
        self.open("a", os.getpid(), "/dev/pts/91")
        self.open("b", os.getppid(), "/dev/pts/92")
        hub.set_terminal(tint="all")
        self.assertEqual(self.last("/dev/pts/91"), self.tint("a", 0.04))
        self.assertEqual(self.last("/dev/pts/92"), self.tint("b", 0.08))
        hub.set_terminal(tint="off", pulse=False)
        self.assertEqual(self.last("/dev/pts/91"), terminal.RESET)
        self.assertEqual(self.last("/dev/pts/92"), terminal.RESET)
        with open(self.cfg.config_path) as f:
            self.assertEqual(json.load(f)["terminal"], {"tint": "off", "pulse": False})
        count = len(self.written)
        hub.focus(-1)
        self.assertEqual(len(self.written), count, "all off: no terminal is written to")
        self.assertEqual(hub.find_terminal("alpha"), "alpha")  # asked for by name: shown all the same
        self.assertIsNone(hub.find_terminal("nobody"))

    def test_the_title_names_the_session_and_cannot_carry_control_characters(self):
        hub = self.make(terminal={**terminal.DEFAULTS, "title": True})
        self.open("a", os.getpid(), "/dev/pts/91")
        self.assertEqual(self.last("/dev/pts/91"), terminal.RESET + b"\x1b]2;alpha\x1b\\")
        hub.sessions.by_id["a"].title = "fix\x1b]11;#ff0000\x07 the\nlogin"
        hub.publish()
        self.assertEqual(self.last("/dev/pts/91"), "\x1b]2;alpha \u00b7 fix ]11;#ff0000  the login\x1b\\".encode())

    def test_going_to_a_terminal_in_the_editor_gives_its_session_the_focus(self):
        hub = self.make()
        self.open("a", os.getpid(), "/dev/pts/91")
        self.open("b", os.getppid(), "/dev/pts/92")
        self.ttys[7001], self.ttys[7002], self.ttys[7003] = "/dev/pts/91", "/dev/pts/92", "/dev/pts/93"  # their shells
        del self.written[:]
        self.assertEqual(hub.terminal_in_front(7001), "alpha")
        self.assertEqual(hub._target().id, "a")
        self.assertCountEqual(self.written, [("/dev/pts/92", terminal.RESET), ("/dev/pts/91", self.tint("a", 0.08))])  # no flash
        self.assertIsNone(hub.terminal_in_front(7001), "it has the focus already")
        self.assertIsNone(hub.terminal_in_front(7003), "a terminal with no session in it")
        self.assertEqual(hub._target().id, "a")
        self.assertIsNone(hub.terminal_in_front(424242), "a process that is not there")

    def test_coming_back_to_the_window_does_not_take_the_focus_from_who_spoke(self):
        hub = self.make()
        self.open("a", os.getpid(), "/dev/pts/91")
        self.open("b", os.getppid(), "/dev/pts/92")
        self.ttys[7001], self.ttys[7002] = "/dev/pts/91", "/dev/pts/92"
        hub.terminal_in_front(7001)
        hub.on_event(ev("Stop", sid="b", last_assistant_message=tag("Done here.")))
        self.spoken()
        self.assertEqual(hub._target().id, "b")  # whoever speaks gets the focus
        self.assertIsNone(hub.terminal_in_front(7001, switched=False))  # the same terminal as before: only the window came back
        self.assertEqual(hub._target().id, "b")
        hub.terminal_in_front(7002, switched=False)
        self.assertEqual(hub.terminal_in_front(7001, switched=False), "alpha")  # another window's terminal: that is a change
        hub.set_terminal(follow=False)
        self.assertIsNone(hub.terminal_in_front(7002))
        self.assertEqual(hub._target().id, "a")

    def test_a_session_with_no_terminal_is_left_alone(self):
        self.make()
        self.open("a", os.getpid(), "")
        self.open("b", os.getppid(), "")
        self.assertEqual(self.written, [])

    def test_the_hub_stopping_gives_the_terminals_back(self):
        hub = self.make()
        self.open("a", os.getpid(), "/dev/pts/91")
        self.open("b", os.getppid(), "/dev/pts/92")
        del self.written[:]
        hub.terminals.close()
        self.assertEqual(self.written, [("/dev/pts/92", terminal.RESET)])
        hub.publish()
        hub.focus(-1)
        self.assertEqual(len(self.written), 1, "nothing is written after that")


class ARealTerminal(unittest.TestCase):
    def test_a_process_is_found_in_its_terminal_and_what_is_written_arrives_whole(self):
        import pty
        ours, theirs = pty.openpty()
        self.addCleanup(os.close, ours)
        proc = subprocess.Popen(["sleep", "30"], stdin=theirs)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        tty = os.ttyname(theirs)
        os.close(theirs)
        self.assertEqual(terminal.tty_of(proc.pid), tty)
        self.assertEqual(terminal.tty_of(os.getpid()) if not os.isatty(0) and not os.isatty(1) and not os.isatty(2) else "", "")
        self.assertTrue(terminal.write(tty, terminal.RESET))
        self.assertEqual(os.read(ours, 100), terminal.RESET)
        self.assertFalse(terminal.write("/dev/pts/no-such-terminal", terminal.RESET))

    def test_the_editor_extension_packs_into_a_file_vs_code_installs(self):
        import importlib.util
        import zipfile
        spec = importlib.util.spec_from_file_location("pack", os.path.join(ROOT, "vscode", "pack.py"))
        pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pack)
        out = os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "x.vsix")
        self.assertEqual(pack.pack(out), "claude-speaks.claude-speaks")
        with zipfile.ZipFile(out) as z:
            self.assertEqual(sorted(z.namelist()), ["[Content_Types].xml", "extension.vsixmanifest",
                                                    "extension/extension.js", "extension/package.json"])
            package = json.loads(z.read("extension/package.json"))
            self.assertIn(f'Version="{package["version"]}"', z.read("extension.vsixmanifest").decode())
        self.assertEqual((package["main"], package["extensionKind"]), ("./extension.js", ["workspace"]))

    def test_colors_mix(self):
        self.assertEqual(terminal.mix("#000000", "#ffffff", 0.5), "rgb:80/80/80")
        self.assertEqual(terminal.mix("#181818", "#C6A0F6", 0), "rgb:18/18/18")
        self.assertEqual(terminal.mix("#181818", "#C6A0F6", 1), "rgb:c6/a0/f6")
        self.assertEqual(terminal.mix("#181818", "purple", 0.5), "")


class HubProcess(unittest.TestCase):
    """The hub as a real process, so it can die the way it would in real life."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp,
                    "XDG_CONFIG_HOME": self.tmp, "CLAUDE_SPEAKS_TTS": "null", "CLAUDE_SPEAKS_OVERLAY": "off",
                    "CLAUDE_SPEAKS_TERMINAL": "off",
                    "CS_RETRY": "0.2"}
        self.sock = os.path.join(self.tmp, "hub.sock")

    def start_hub(self):
        proc = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "hub", "hub.py")], env=self.env)
        self.addCleanup(proc.kill)
        self.assertTrue(wait_for(lambda: self.call("/health") is not None, 10), "the hub did not start")
        return proc

    def call(self, path, body=None):
        cmd = ["curl", "-sf", "-m", "2", "--unix-socket", self.sock, f"http://hub{path}"]
        if body is not None:
            cmd += ["--data-binary", json.dumps(body)]
        done = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(done.stdout or "null") if done.returncode == 0 else None

    def names(self):
        state = self.call("/state")
        return [s["name"] for s in state["sessions"]] if state else []

    def test_an_idle_session_is_reachable_again_after_the_hub_restarts(self):
        first = self.start_hub()
        hook = subprocess.Popen([os.path.join(ROOT, "hooks", "listen.sh")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        self.addCleanup(hook.kill)
        hook.stdin.write(json.dumps(ev("Stop")))
        hook.stdin.close()
        hook.stdin = None
        self.assertTrue(wait_for(lambda: self.names() == ["alpha"], 5), "the hub never saw the listener")
        first.kill()  # no goodbye: the socket file is left behind, like after a crash
        first.wait(5)
        self.start_hub()
        self.assertTrue(wait_for(lambda: self.names() == ["alpha"], 5), "the listener did not come back")
        self.assertEqual(self.call("/follow-up", {"text": "run the tests", "session": "alpha", "delay": 0}), {"queued": True})
        out, err = hook.communicate(timeout=5)
        self.assertEqual(hook.returncode, 2)
        self.assertIn('"run the tests"', err)

    def test_a_listener_started_just_before_the_hub_waits_for_it(self):
        """The first session starts the hub and its listener in the same moment."""
        hook = subprocess.Popen([os.path.join(ROOT, "hooks", "listen.sh")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        self.addCleanup(hook.kill)
        hook.stdin.write(json.dumps(ev("SessionStart")))
        hook.stdin.close()
        hook.stdin = None
        time.sleep(0.5)
        self.assertIsNone(hook.poll(), "the listener gave up before the hub was there")
        self.start_hub()
        self.assertTrue(wait_for(lambda: self.names() == ["alpha"], 5), "the hub never saw the listener")
        self.assertEqual(self.call("/follow-up", {"text": "run the tests", "session": "alpha", "delay": 0}), {"queued": True})
        out, err = hook.communicate(timeout=5)
        self.assertEqual(hook.returncode, 2)
        self.assertIn('"run the tests"', err)

    def test_a_listener_gives_up_where_there_is_no_hub(self):
        done = subprocess.run([os.path.join(ROOT, "hooks", "listen.sh")], input=json.dumps(ev("SessionStart")),
                              capture_output=True, text=True, env={**self.env, "CS_WAIT": "1"}, timeout=10)
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    @unittest.skipUnless(__import__("shutil").which("node"), "needs node to run the editor extension")
    def test_the_editor_extension_tells_the_hub_which_terminal_you_went_to(self):
        """The real extension code, with a stand-in for the editor, against a real hub."""
        import pty
        import shutil
        sessions = os.path.join(self.tmp, ".claude", "sessions")
        os.makedirs(sessions)
        pids = {}
        for sid in ("a", "b"):  # two sessions, each a process in a terminal of its own
            ours, theirs = pty.openpty()
            proc = subprocess.Popen(["sleep", "30"], stdin=theirs)
            os.close(theirs)
            self.addCleanup(os.close, ours)
            self.addCleanup(proc.wait)
            self.addCleanup(proc.kill)
            pids[sid] = proc.pid
            with open(os.path.join(sessions, f"{proc.pid}.json"), "w") as f:
                json.dump({"pid": proc.pid, "sessionId": sid, "status": "idle", "statusUpdatedAt": time.time() * 1000}, f)
        self.start_hub()
        self.call("/event", ev("SessionStart", sid="a", cwd="/work/alpha"))
        self.call("/event", ev("SessionStart", sid="b", cwd="/work/beta"))
        self.assertEqual(self.call("/target", {})["target"], "beta")
        ext = os.path.join(self.tmp, "ext")
        os.makedirs(os.path.join(ext, "node_modules", "vscode"))
        shutil.copy(os.path.join(ROOT, "vscode", "extension.js"), ext)
        with open(os.path.join(ext, "node_modules", "vscode", "index.js"), "w") as f:
            f.write("""
                const went = [];
                exports.went = went;
                exports.window = {
                  state: { focused: true },
                  activeTerminal: { processId: Promise.resolve(Number(process.env.SHELL_PID)) },
                  onDidChangeActiveTerminal: (f) => { went.push(f); return { dispose() {} }; },
                  onDidChangeWindowState: (f) => ({ dispose() {} }),
                };""")
        go = "const x = require('./extension.js'); x.activate({ subscriptions: [] }); require('vscode').went[0]();"
        # Told within two seconds of the hub starting, or the hub has not looked for the terminals yet.
        self.assertTrue(wait_for(lambda: subprocess.run(
            ["node", "-e", go], cwd=ext, env={**self.env, "SHELL_PID": str(pids["a"])}, timeout=10).returncode == 0
            and self.call("/target", {})["target"] == "alpha", 8), "the hub did not move the focus")


    def test_a_listener_keeps_working_when_its_script_is_edited_under_it(self):
        """Bash reads a script from its file as it goes. A listener waits for hours, and when the
        file changed meanwhile it read on in the middle of the new text: a syntax error, the
        session woken with that error, and the words it had been given lost."""
        import shutil
        hooks = os.path.join(self.tmp, "hooks")
        shutil.copytree(os.path.join(ROOT, "hooks"), hooks)
        self.env["CS_ROOT"] = ROOT
        self.start_hub()
        script = os.path.join(hooks, "listen.sh")
        hook = subprocess.Popen([script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=self.env)
        self.addCleanup(hook.kill)
        hook.stdin.write(json.dumps(ev("Stop")))
        hook.stdin.close()
        hook.stdin = None
        self.assertTrue(wait_for(lambda: self.names() == ["alpha"], 5), "the hub never saw the listener")
        with open(script, "r+") as f:  # the same file, with everything moved down a little
            text = f.read()
            f.seek(0)
            f.write(text.replace("\n", "\n# a comment someone added while it was running\n", 1))
        self.assertEqual(self.call("/follow-up", {"text": "run the tests", "session": "alpha", "delay": 0}), {"queued": True})
        out, err = hook.communicate(timeout=5)
        self.assertEqual((hook.returncode, err.count("\n")), (2, 2), err)
        self.assertIn('"run the tests"', err)


if __name__ == "__main__":
    unittest.main()
