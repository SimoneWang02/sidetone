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

    def test_rows_carry_a_short_title_from_the_prompt(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", prompt="fix the flaky login test, then run the whole suite again and tell me\nmore"))
        row = self.overlay.of("state")[-1]["sessions"][0]
        self.assertEqual(row["title"], "Fix the flaky login test, then run the\u2026")

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
        self.assertEqual((shown["text"], shown["detail"]), ("asks: Which drink?", "1  Tea   2  Coffee   3  Water"))
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
        self.assertEqual(self.engine.spoken[-1], ("alpha. All done.", self.session()["voice"]))

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


class FakeTranscriber:
    text = "also add a test"

    def load(self):
        pass

    def unload(self):
        pass

    def transcribe(self, pcm):
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

    def banners(self):
        return [m.get("text") for m in self.overlay.of("banner")]

    def test_hold_to_talk_reaches_the_session_that_spoke_last(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A is done.")))
        self.spoken()
        listener = hub.listen("a")
        self.assertTrue(hub.talk_start())
        self.assertTrue(hub.recorder.recording)
        self.assertIn("listening \u2192 a", self.banners())
        hub.talk_end()
        self.assertTrue(listener.wake.wait(3), "the follow-up never reached the listener")
        self.assertIn("\u2192 a: \u201calso add a test\u201d", self.banners())
        self.assertEqual(hub.collect(listener), "also add a test")
        self.assertEqual(self.spoken(), ["A is done.", "Sent."])

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
        self.assertIn("cancelled", self.banners())

    def test_a_quick_tap_picks_the_next_session(self):
        hub = self.make()
        hub_module.TAP = 30
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertEqual(hub.talk_target, "b")
        self.assertIn("talking to b", self.banners())
        self.assertFalse(wait_for(lambda: hub.followups, 0.2))

    def test_silence_sends_nothing(self):
        hub = self.make()
        hub.transcriber.text = ""
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: "did not catch that" in self.banners()))
        self.assertEqual(hub.followups, {})

    def test_follow_up_waits_for_a_session_with_no_listener_yet(self):
        hub = self.make()
        hub.follow_up("run the tests", "b", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("b")))
        listener = hub.listen("b")  # armed when the session next stops
        self.assertTrue(listener.wake.is_set())
        self.assertEqual(hub.collect(listener), "run the tests")

    def test_a_newer_listener_replaces_the_older_one(self):
        hub = self.make()
        old, new = hub.listen("a"), hub.listen("a")
        self.assertTrue(old.wake.is_set())
        self.assertIsNone(hub.collect(old))
        self.assertFalse(new.wake.is_set())

    def test_unattended_session_needs_a_confirming_tap(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", permission_mode="bypassPermissions"))
        hub.talk_target = "a"
        listener = hub.listen("a")
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(wait_for(lambda: hub._pending is not None))
        self.assertIn("tap Ctrl+Alt+Space to send", self.overlay.of("banner")[-1]["hint"])
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
        self.assertTrue(wait_for(lambda: "not sent" in self.banners()))
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

    def test_overlay_claims_keys_only_while_they_can_act(self):
        hub = self.make()
        hub.publish()
        self.assertEqual(self.overlay.of("keys")[-1]["live"], [])
        hub.request_permission(ask(sid="a", cwd="/w/a"))
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "deny"])
        hub.talk_start()
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "cancel", "deny"])


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


class HubProcess(unittest.TestCase):
    """The hub as a real process, so it can die the way it would in real life."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.env = {**os.environ, "CS_RUN": self.tmp, "CS_STATE": self.tmp, "HOME": self.tmp,
                    "XDG_CONFIG_HOME": self.tmp, "CLAUDE_SPEAKS_TTS": "null", "CLAUDE_SPEAKS_OVERLAY": "off",
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


if __name__ == "__main__":
    unittest.main()
