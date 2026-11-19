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
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import hub as hub_module  # noqa: E402
import base  # noqa: E402  (what the hub's parts share; the waits these tests shorten are read from it)
from hub import Config, Hub, serve  # noqa: E402
import sounds  # noqa: E402
import terminal  # noqa: E402
from tts import CommandEngine, NullEngine, voice_lang  # noqa: E402
from state import split_display  # noqa: E402


def ev(event, sid="s1", cwd="/work/alpha", **extra):
    return {"hook_event_name": event, "session_id": sid, "cwd": cwd, **extra}


def tag(text):
    return f"<speak>{text}</speak>"


class HubCase(unittest.TestCase):
    def make(self, duration=0.0, **cfg):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.engine = NullEngine(duration)
        cfg.setdefault("usage_shown", False)  # or a hub with an overlay would ask the real Claude Code for the plan's usage
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


class ReplyLanguage(HubCase):
    """A line in another language than English is said by a voice of that language."""
    VOICES = {"af_heart", "am_michael", "if_sara", "im_nicola", "ef_dora", "em_alex", "em_santa"}

    def make(self, **cfg):
        hub = super().make(**cfg)
        self.engine.voices = set(self.VOICES)
        return hub

    def test_the_tag_reads_title_and_language_in_any_order(self):
        self.assertEqual(split_display('<speak lang="it" title="Tasto muto">Ho finito.</speak>'),
                         ("Ho finito.", "\U0001f50a Ho finito.", "Tasto muto", "it"))
        self.assertEqual(split_display("<speak title='T'>Done.</speak>")[2:], ("T", ""))
        self.assertEqual(split_display('<speak lang="pt-BR">Feito.</speak>')[3], "pt")

    def test_an_italian_line_gets_an_italian_voice_of_the_same_kind(self):
        hub = self.make()
        hub.on_display(ev("MessageDisplay", delta='<speak lang="it">Ho aggiunto il tasto.</speak>'))
        self.spoken()
        own = self.session()["voice"]
        said = self.engine.spoken[-1][1]
        self.assertTrue(said.startswith("i" + own[1]), (own, said))  # if_sara for a female voice
        hub.on_display(ev("MessageDisplay", delta=tag("Done.")))
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][1], own)  # English again: its own voice

    def test_the_stop_event_reads_the_language_too(self):
        hub = self.make()
        hub.on_event(ev("Stop", last_assistant_message='<speak lang="es">Listo.</speak>\nmore'))
        self.spoken()
        self.assertTrue(self.engine.spoken[-1][1].startswith("e"))

    def test_english_only_or_unknown_language_keeps_the_own_voice(self):
        hub = self.make(reply_language="english")
        hub.on_display(ev("MessageDisplay", delta='<speak lang="it">Ciao.</speak>'))
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][1], self.session()["voice"])
        hub.cfg.reply_language = "spoken"
        hub.on_display(ev("MessageDisplay", delta='<speak lang="de">Hallo.</speak>'))  # no German voice
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][1], self.session()["voice"])

    def test_a_better_voice_for_the_language_comes_first(self):
        hub = self.make()
        self.engine.has = lambda v: v in self.VOICES or v == "piper:it_IT-paola-medium"
        hub.on_display(ev("MessageDisplay", delta='<speak lang="it">Fatto.</speak>'))
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][1], "piper:it_IT-paola-medium")  # Paola, when installed
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/work/beta", delta='<speak lang="it">Anche io.</speak>'))
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][1], "if_sara")  # another session: the next of the three
        hub.cfg.language_voices = {"it": "im_nicola"}
        hub.on_display(ev("MessageDisplay", delta='<speak lang="it">Fatto di nuovo.</speak>'))
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][1], "im_nicola")  # one chosen in config.json wins

    def test_the_voice_says_how_to_pronounce(self):
        self.assertEqual([voice_lang(v) for v in ("if_sara", "af_heart", "bm_george", "pm_alex", "mine")],
                         ["it", "en-us", "en-gb", "pt-br", "en-us"])


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

    def test_rows_say_how_full_a_sessions_context_is(self):
        hub = self.make()
        record = os.path.join(self.tmp, "record.jsonl")
        with open(record, "w") as f:
            json.dump({"type": "assistant", "isSidechain": False, "message": {"usage": {
                "input_tokens": 2, "cache_creation_input_tokens": 150000, "cache_read_input_tokens": 469998, "output_tokens": 14}}}, f)
        hub.on_event(ev("UserPromptSubmit"))
        row = lambda: self.overlay.of("state")[-1]["sessions"][0]
        self.assertIsNone(row()["context"])  # nothing to go on yet
        hub.on_event(ev("Stop", transcript_path=record, last_assistant_message=tag("Done.")))
        self.assertEqual(row()["context"], 62.0)  # for the arc around its light
        self.assertNotIn("context", row()["meta"], "the arc says it; the words were too long beside the running time")
        hub.on_event(ev("Stop", transcript_path=os.path.join(self.tmp, "gone.jsonl"), last_assistant_message=tag("Done.")))
        self.assertEqual(row()["context"], 62.0, "a record that cannot be read leaves the last figure")

    def test_the_history_says_how_a_line_ended_and_whether_it_was_missed(self):
        hub = self.make()
        hub.cfg.history_missed = True
        hub.on_event(ev("UserPromptSubmit"))
        hub.on_event(ev("Stop", last_assistant_message=tag("All done.")))
        self.spoken()
        hub.publish()
        line = lambda: self.overlay.of("state")[-1]["history"][0]
        self.assertEqual((line()["text"], line()["kind"], line()["missed"]), ("All done.", "done", False))
        # A line that never reached the voice (replaced by a newer one, too old, cut off) and is not waiting to be said.
        hub.history.append({"time": time.time(), "session": "s1", "name": "alpha", "color": "", "spoken_name": "alpha",
                            "voice": "af_heart", "text": "Half way.", "kind": "progress", "heard": False})
        hub.publish()
        self.assertEqual((line()["text"], line()["kind"], line()["missed"]), ("Half way.", "progress", True))
        hub.history[-1]["shown"] = True  # the voice was off and it was shown instead
        hub.on_event(ev("UserPromptSubmit"))
        self.assertFalse(line()["missed"])
        # Off by default: no dot, even on a line that was not heard.
        hub.history[-1]["shown"] = False
        hub.cfg.history_missed = False
        hub.on_event(ev("UserPromptSubmit"))
        self.assertFalse(line()["missed"])

    def test_figures_go_under_the_rows_with_their_names_and_only_the_time_stays_in_the_row(self):
        hub = self.make()
        record = os.path.join(self.tmp, "record.jsonl")
        with open(record, "w") as f:
            json.dump({"type": "assistant", "isSidechain": False, "message": {"id": "a", "usage": {
                "input_tokens": 2, "cache_creation_input_tokens": 149998, "cache_read_input_tokens": 470000, "output_tokens": 4000}}}, f)
        row = lambda: self.overlay.of("state")[-1]["sessions"][0]
        hub.on_event(ev("UserPromptSubmit"))
        self.assertEqual(row()["details"], [["Context", "", None, ""], ["Last reply", "", None, ""], ["This turn", "<1m", None, ""],
                                            ["Tasks", "", None, ""]], "what is not known keeps its place")
        hub.on_event(ev("TaskCreated", task_id="1"))
        hub.on_event(ev("TaskCreated", task_id="2"))
        hub.on_event(ev("TaskCompleted", task_id="1"))
        hub.on_event(ev("PostToolUse", transcript_path=record))
        self.assertEqual(row()["meta"], "<1m")
        self.assertEqual(row()["details"], [["Context", "62%", 0.62, ""], ["This reply", "154k", None, ""], ["This turn", "<1m", None, ""],
                                            ["Tasks", "1/2", 0.5, ""]])
        hub.on_event(ev("Stop", transcript_path=record, last_assistant_message=tag("Done.")))
        self.assertEqual(row()["meta"], "")
        self.assertEqual([d[:2] for d in row()["details"]], [["Context", "62%"], ["Last reply", "154k"], ["Last turn", "<1m"], ["Tasks", "1/2"]])
        hub.cfg.overlay["context_warn"] = 60
        hub.cfg.row_metrics, hub.cfg.detail_metrics = ["tasks", "tokens"], ["waiting", "context"]  # a choice of one's own
        hub.publish()
        self.assertEqual((row()["meta"], row()["details"]), ("1/2   154k", [["Waiting", "", None, ""], ["Context", "62%", 0.62, "warn"]]))
        hub.cfg.detail_metrics = []
        hub.publish()
        self.assertEqual(row()["details"], [])

    def test_a_row_says_what_the_turn_used_once_it_has_ended(self):
        hub = self.make()
        hub.cfg.row_metrics = ["time", "tokens"]  # in the row, where it was at first
        record = os.path.join(self.tmp, "record.jsonl")
        reply = lambda id, out, new, again: json.dumps({"type": "assistant", "isSidechain": False, "message": {"id": id, "usage": {
            "input_tokens": 2, "cache_creation_input_tokens": new - 2, "cache_read_input_tokens": again, "output_tokens": out}}})
        with open(record, "w") as f:
            f.write(reply("old", 9000, 9000, 9000) + "\n")  # an earlier turn: not counted
        row = lambda: self.overlay.of("state")[-1]["sessions"][0]
        hub.on_event(ev("UserPromptSubmit", transcript_path=record))
        with open(record, "a") as f:
            f.write(reply("a", 500, 3000, 100000) + "\n" + reply("a", 500, 3000, 100000) + "\n" + reply("b", 700, 800, 103000) + "\n")
        hub.on_event(ev("PostToolUse", transcript_path=record))
        self.assertEqual(row()["meta"], "<1m", "not while it works")
        hub.on_event(ev("Stop", transcript_path=record, last_assistant_message=tag("Done.")))
        self.assertEqual(row()["meta"], "5.0k")  # 1,200 written and 3,800 read for the first time
        with open(record, "a") as f:
            f.write(reply("c", 1000, 2000, 104000) + "\n")  # the last reply reaches the record late
        self.assertTrue(wait_for(lambda: row()["meta"] == "8.0k"))
        said = lambda: self.overlay.of("state")[-1]["history"][0]
        self.assertEqual((said()["text"], said()["tokens"]), ("Done.", "8.0k"), "the line it ended on keeps the figure")
        self.assertEqual(said()["kind"], "done")  # for the mark in front of it
        hub.cfg.turn_tokens_label = "tokens"
        hub.publish()
        self.assertEqual(row()["meta"], "8.0k tokens")
        hub.on_event(ev("UserPromptSubmit", transcript_path=record))
        self.assertEqual(row()["meta"], "<1m")
        hub.cfg.turn_tokens = "all"
        hub.on_event(ev("Stop", transcript_path=record, last_assistant_message=tag("Done.")))
        self.assertEqual(row()["meta"], "", "nothing was written in this turn")
        hub.cfg.turn_tokens = "off"
        hub.on_event(ev("UserPromptSubmit", transcript_path=record))
        hub.on_event(ev("Stop", transcript_path=record, last_assistant_message=tag("Done.")))
        self.assertEqual(row()["meta"], "")

    def test_where_the_context_shows_is_a_setting(self):
        hub = self.make()
        record = os.path.join(self.tmp, "record.jsonl")
        with open(record, "w") as f:
            json.dump({"type": "assistant", "isSidechain": False, "message": {"usage": {
                "input_tokens": 2, "cache_creation_input_tokens": 150000, "cache_read_input_tokens": 469998, "output_tokens": 14}}}, f)
        hub.on_event(ev("Stop", transcript_path=record, last_assistant_message=tag("Done.")))
        row = lambda: self.overlay.of("state")[-1]["sessions"][0]
        for wanted, arc, words in (("arc", True, False), ("text", False, True), ("both", True, True), ("off", False, False),
                                   (True, True, False), (False, False, False)):
            hub.cfg.context_shown = wanted
            hub.on_event(ev("UserPromptSubmit"))
            self.assertEqual(row()["context"], 62.0 if arc else None, wanted)
            self.assertEqual("context 62%" in row()["meta"], words, wanted)

    def test_rows_show_activity_tasks_and_how_the_turn_ended(self):
        hub = self.make()
        hub.on_event(ev("UserPromptSubmit"))
        hub.on_event(ev("TaskCreated", task_id="1"))
        hub.on_event(ev("PreToolUse", tool_name="Bash", tool_input={"description": "Run tests"}))
        row = self.overlay.of("state")[-1]["sessions"][0]
        self.assertEqual((row["name"], row["state"], row["text"], row["meta"], row["details"][3]),
                         ("alpha", "working", "Run tests", "<1m", ["Tasks", "0/1", 0.0, ""]))
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

    def test_name_colors_side_by_side_are_far_apart(self):
        import state

        near = state.color_distance("#FFB86B", "#F9E27D")  # the orange and the yellow the author could not tell apart
        self.assertLess(near, state.TOO_CLOSE)
        self.assertGreater(state.color_distance("#FF8FA3", "#7FDBCA"), 70)  # pink and teal: nobody mixes those up
        hub = self.make()
        for i in range(5):  # also sessions of one project, which is where it was seen
            hub.on_event(ev("SessionStart", sid=f"s{i}", cwd="/w/claude-speaks"))
        colors = [r["color"] for r in self.overlay.of("state")[-1]["sessions"]]
        apart = min(state.color_distance(a, b) for i, a in enumerate(colors) for b in colors[:i])
        self.assertGreaterEqual(apart, state.TOO_CLOSE, colors)

    def test_twenty_sessions_have_twenty_colors_and_the_first_ones_the_soft_ones(self):
        import state

        hub = self.make()
        for i in range(21):
            hub.on_event(ev("SessionStart", sid=f"s{i}", cwd="/w/claude-speaks"))
        colors = [r["color"] for r in self.overlay.of("state")[-1]["sessions"]]
        self.assertTrue(set(colors[:5]) <= set(state.COLORS[:state.SOFT]), colors[:5])
        self.assertEqual(len(set(colors[:20])), 20)
        apart = min(state.color_distance(a, b) for i, a in enumerate(colors[:20]) for b in colors[:i])
        self.assertGreater(apart, 25, colors)  # 25: the orange and the yellow that could not be told apart
        self.assertIn(colors[20], state.COLORS)  # one more session than colors: it shares one

    def test_the_name_colors_can_be_your_own(self):
        hub = self.make(colors=["#ff0000", "#00FF00", "not a color", "#0000FF"])
        for i in range(3):
            hub.on_event(ev("SessionStart", sid=f"s{i}", cwd=f"/w/project-{i}"))
        colors = [r["color"] for r in self.overlay.of("state")[-1]["sessions"]]
        self.assertEqual(sorted(colors), ["#0000FF", "#00FF00", "#FF0000"])
        import state
        self.assertEqual(state.usable_colors(["#123456"]), state.COLORS)  # one color tells nobody apart

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
        # A line a session has said with the command is its own: drawn at its light like any other.
        hub.say("Here is the list.", session="s1")
        self.assertEqual(self.spoken()[-1], "Here is the list.")
        self.assertEqual([w["name"] for w in self.overlay.of("wave")], ["alpha", "alpha"])
        self.assertEqual((hub.history[-1]["text"], hub.history[-1]["kind"], hub.history[-1]["session"]), ("Here is the list.", "progress", "s1"))
        hub.say("From a session the hub does not know.", session="nobody")
        self.spoken()
        self.assertEqual(len(self.overlay.of("wave")), 2)

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
                         [("", "alpha", "Second."), ("", "alpha", "First.")])  # how long ago is a setting, off
        hub.cfg.history_time = True
        hub.on_event(ev("UserPromptSubmit"))
        self.assertEqual([h["ago"] for h in self.overlay.of("state")[-1]["history"]], ["now", "now"])

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
        self.addCleanup(setattr, base, "MIN_SHOWN", base.MIN_SHOWN)
        base.MIN_SHOWN = 0
        return hub

    def test_request_shows_and_allow_answers_it(self):
        hub = self.make()
        req = hub.request_permission(ask())
        self.assertEqual((self.session()["state"], self.session()["note"]), ("needs_you", "wants to: Run tests"))
        shown = self.overlay.of("request")[-1]
        self.assertEqual((shown["name"], shown["text"], shown["detail"]), ("alpha", "wants to: Run tests", "npm test"))
        self.assertIn("Ctrl+Alt+Y allow", shown["keys"])
        self.assertEqual((shown["hints"], shown["more"]), ([["Ctrl+Alt+Y", "allow", ""], ["Ctrl+Alt+N", "deny", ""]], 0))  # for key caps
        self.assertTrue(hub.decide("allow"))
        self.assertEqual(req.decision, "allow")
        self.assertTrue(req.done.is_set())
        self.assertEqual(self.session()["state"], "working")
        self.assertEqual(self.overlay.of("request")[-1], {"type": "request"})  # cleared
        self.assertEqual(self.spoken(), ["Allowed."])

    def test_a_request_just_shown_cannot_be_answered_yet(self):
        hub = self.make()
        base.MIN_SHOWN = 30
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
        self.addCleanup(setattr, base, "MIN_SHOWN", base.MIN_SHOWN)
        base.MIN_SHOWN = 0
        return hub

    def test_number_keys_answer_each_question_in_turn(self):
        hub = self.make()
        req = hub.request_permission(ask_question(question("Which drink?", "Tea", "Coffee", "Water"),
                                                  question("Which colour?", "Red", "Blue")))
        shown = self.overlay.of("request")[-1]
        self.assertEqual((shown["text"], shown["options"]), ("asks: Which drink?", ["Tea", "Coffee", "Water"]))
        self.assertEqual(shown["place"], "1 of 2")
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["option1", "option2", "option3"])
        self.assertFalse(hub.decide("allow"))  # a question is not a yes/no
        self.assertFalse(hub.choose(4))  # there is no fourth option
        self.assertTrue(hub.choose(2))
        self.assertFalse(req.done.is_set())
        self.assertEqual(self.overlay.of("request")[-1]["text"], "asks: Which colour?")
        self.assertEqual(self.overlay.of("request")[-1]["place"], "2 of 2")
        self.assertEqual(self.spoken()[-1][:39], "Next. Question 2 of 2: Which colour? On")
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

    def test_an_answer_given_with_the_keys_is_met_with_a_sound_not_read_back(self):
        hub = self.make()
        hub.sounds = FakeSounds()
        hub.request_permission(ask_question(question("Which drink?", "Tea", "Coffee"), question("Which colour?", "Red", "Blue")))
        self.assertTrue(hub.choose(2))
        self.assertTrue(hub.choose(1))
        said = self.spoken()
        self.assertEqual(hub.sounds.played, ["sent"])  # once, when the last answer went in
        # The next question may have begun to be read out ("... One: Red."); no answer is said back.
        self.assertFalse([line for line in said if "Coffee" in line or "Answered" in line], said)

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

    def test_several_choices_are_ticked_with_the_number_keys_and_handed_in_with_the_allow_key(self):
        hub = self.make()
        req = hub.request_permission(ask_question(question("Which fruits?", "Apple", "Banana", "Cherry", multi=True),
                                                  question("Which drink?", "Tea", "Coffee")))
        shown = lambda: self.overlay.of("request")[-1]
        self.assertEqual((shown()["question"], shown()["options"], shown()["ticked"]),
                         ("Which fruits?", ["Apple", "Banana", "Cherry"], [False, False, False]))
        self.assertIn("Ctrl+Alt+Y confirms", shown()["keys"])
        self.assertEqual(shown()["hints"], [["Ctrl+Alt+1", "tick", "3"], ["Ctrl+Alt+Y", "confirms", ""]])
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "option1", "option2", "option3"])
        self.assertFalse(hub.decide("allow"), "nothing is ticked yet")
        self.assertTrue(hub.choose(3))
        self.assertTrue(hub.choose(1))
        self.assertTrue(hub.choose(2))
        self.assertTrue(hub.choose(2))  # ticked by mistake: off again
        self.assertEqual(shown()["ticked"], [True, False, True])
        self.assertEqual(req.answers, {})
        self.assertFalse(hub.decide("deny"))  # a question is not refused with a key
        self.assertTrue(hub.decide("allow"))
        self.assertEqual(req.answers, {"Which fruits?": "Apple, Cherry"})  # in the order they were offered
        self.assertEqual(shown()["options"], ["Tea", "Coffee"])
        self.assertNotIn("ticked", shown())  # the next one has a single answer: numbers, no boxes
        self.assertNotIn("allow", self.overlay.of("keys")[-1]["live"])
        self.assertTrue(hub.choose(2))
        self.assertEqual((req.decision, req.answers), ("answer", {"Which fruits?": "Apple, Cherry", "Which drink?": "Coffee"}))
        self.assertEqual(self.spoken()[-1], "Answered: Coffee.")  # what each key said was cut by the next

    def test_a_question_with_several_choices_can_be_answered_in_your_own_words(self):
        hub = self.make(talk_feedback="none")
        req = hub.request_permission(ask_question(question("Which fruits?", "Apple", "Banana", multi=True)))
        self.assertTrue(hub.choose(1))
        hub.follow_up("Apples, and mango, which is not on your list", session="s1", delay=0)
        time.sleep(0.1)
        self.assertEqual((req.decision, req.answers), ("answer", {"Which fruits?": "Apples, and mango, which is not on your list"}))

    def test_questions_the_keys_cannot_answer_are_only_announced(self):
        hub = self.make()
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

    def test_repeat_and_catch_up_stay_quiet_while_muted(self):
        hub = self.two_sessions_spoke()
        open(self.cfg.mute_file, "a").close()
        self.assertTrue(hub.repeat())
        self.assertEqual(hub.catch_up(), 0)
        self.assertEqual(self.spoken(), [])  # not "Page built." again, nor "Nothing new."
        self.assertEqual(self.overlay.of("flash")[-1]["text"], "Page built.")  # shown at its light instead

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
        self.addCleanup(setattr, base, "TAP", base.TAP)
        base.TAP = 0  # every press in these tests counts as a hold
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
        self.assertEqual(len(set(made.values())), len(sounds.TONES))
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
        self.assertNotIn("waiting", row()["meta"], "the number on the light says it; the words are a setting")
        hub.cfg.waiting_words = True
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
        # The sign for words that went out leaves the bubble to a session that is speaking.
        self.assertEqual([m.get("quiet", False) for m in self.overlay.of("talk") if m.get("state") in ("ready", "sent")], [False, True])
        hub.cfg.overlay["sent_first"] = True  # as it was: the sign's words first
        hub.follow_up("and again", "a", delay=0)
        self.assertTrue(wait_for(lambda: ("sent", "a", "and again") in self.talks()))
        self.assertNotIn("quiet", self.overlay.of("talk")[-1])
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

    def got_the_words(self, **cfg):
        """Session "a" was idle and has just been handed what was said to it."""
        hub = self.make(**cfg)
        hub.talk_target = "a"
        listener = hub.listen("a")
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(listener.wake.wait(3))
        self.assertEqual(hub.collect(listener), "also add a test")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="<task-notification>also add a test"))
        return hub

    def test_cancel_after_the_session_got_the_words_stops_its_turn(self):
        hub = self.got_the_words()
        again = hub.listen("a")
        hub.cancel()
        flag = os.path.join(self.tmp, "stop", "a")
        self.assertTrue(os.path.exists(flag), "nothing was left for its hook")
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Taken back: stopping it"))
        self.assertFalse(again.wake.is_set(), "it must not be woken with a message about it")
        row = lambda: next(r for r in self.overlay.of("state")[-1]["sessions"] if r["name"] == "a")
        self.assertEqual(row()["text"], "Stopping at its next step")
        os.unlink(flag)  # hooks/stop.sh, at its next tool call
        hub.reconcile()
        self.assertEqual((row()["state"], row()["text"]), ("idle", "stopped"))
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Stopped"))

    def test_a_stopped_turn_that_ends_by_itself_is_not_spoken_and_the_next_one_runs(self):
        hub = self.got_the_words()
        hub.cancel()
        flag = os.path.join(self.tmp, "stop", "a")
        self.assertTrue(os.path.exists(flag))
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Here is the answer to what you took back.")))
        self.assertNotIn("Here is the answer to what you took back.", " ".join(self.spoken()))
        self.assertFalse(os.path.exists(flag), "the next turn would be stopped at its first step")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go on"))
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Going on.")))
        self.assertIn("Going on.", self.spoken()[-1])

    def test_new_words_or_a_typed_prompt_call_the_stop_off(self):
        hub = self.got_the_words()
        hub.cancel()
        flag = os.path.join(self.tmp, "stop", "a")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="do this instead"))
        self.assertFalse(os.path.exists(flag))
        self.assertTrue(hub.speech.wait_idle(5))  # while the hub's own answer to the first press is said, the key would cut that
        hub.cancel()  # nothing just sent, nothing spoken: the key stops the session in focus
        self.assertTrue(os.path.exists(flag))
        hub.follow_up("and this", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        self.assertTrue(os.path.exists(flag), "words that wait for the turn to end do not call it off")
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Stopped there.")))
        self.assertEqual(hub.collect(hub.listen("a")), "and this")
        self.assertFalse(os.path.exists(flag))

    def test_the_cancel_key_ends_the_turn_of_the_session_in_focus(self):
        hub = self.make()
        hub.talk_target = "a"
        hub.publish()
        self.assertNotIn("cancel", self.overlay.of("keys")[-1]["live"])  # idle: nothing for the key to do
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        self.assertIn("cancel", self.overlay.of("keys")[-1]["live"])
        hub.cancel()
        flag = os.path.join(self.tmp, "stop", "a")
        self.assertTrue(os.path.exists(flag))
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Stopping at its next step"))
        self.assertNotIn("cancel", self.overlay.of("keys")[-1]["live"])  # asked already
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "stop", "b")), "only the session in focus")

    def test_the_cancel_key_stops_at_once_where_an_editor_can_type_escape(self):
        hub = self.make()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        editor = hub.editor_waits([4002, 4001, 9])  # one window of the editor, with both terminals and a plain shell
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        hub.talk_target = "a"
        hub.cancel()
        self.assertTrue(editor.wake.is_set())
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "escape"}])
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Stopping"))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "stop", "a")), "the hook stays as the way that always works")
        hub.on_event(ev("PostToolUse", sid="a", cwd="/w/a", tool_name="Bash", is_interrupt=True))  # what Escape does
        hub.reconcile()
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "stop", "a")), "its next turn would be stopped too")
        row = next(r for r in self.overlay.of("state")[-1]["sessions"] if r["name"] == "a")
        self.assertEqual((row["state"], row["text"]), ("idle", "stopped"))
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Stopped"))

    def test_a_key_brings_the_terminal_of_the_session_in_focus_to_the_front(self):
        hub = self.make()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        hub.talk_target = "a"
        hub.publish()
        self.assertNotIn("jump", self.overlay.of("keys")[-1]["live"])  # no editor: the key is left to other programs
        self.assertIsNone(hub.show_terminal())
        old = hub.editor_waits([4001, 4002])  # an extension from before this: it only types Escape
        self.assertNotIn("jump", self.overlay.of("keys")[-1]["live"])
        self.assertIsNone(hub.show_terminal())
        hub.editor_done(old)
        editor = hub.editor_waits([4002, 4001, 9], shows=True)
        self.assertIn("jump", self.overlay.of("keys")[-1]["live"])
        hub.on_overlay({"type": "hotkey", "name": "jump"})
        self.assertTrue(editor.wake.is_set())
        self.assertEqual((editor.show, hub.editor_done(editor)), ([4001], []))  # shown, and nothing typed
        # Between two requests of the editor the key still works: the next request is handed it.
        self.assertEqual(hub.show_terminal("b"), "b")
        again = hub.editor_waits([4002, 4001], shows=True)
        self.assertTrue(again.wake.is_set())
        self.assertEqual(again.show, [4002])
        hub.editor_done(again)
        self.assertIsNone(hub.show_terminal("nobody"))
        # An editor that has been gone for a while cannot be asked.
        hub._shown_by.clear()
        self.assertIsNone(hub.show_terminal())

    def test_the_terminal_can_follow_the_focus_moved_by_hand(self):
        hub = self.make()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        hub.talk_target = "a"
        editor = hub.editor_waits([4001, 4002], shows=True)
        hub.focus(1)
        self.assertFalse(editor.wake.is_set(), "off by default: terminals side by side are all in sight")
        hub.focus(-1)
        hub.set_terminal(jump=True)
        hub.focus(1)
        self.assertTrue(editor.wake.is_set())
        self.assertEqual(editor.show, [4002])
        hub.focus(-1)  # before the editor has answered: only the newest one is shown
        self.assertEqual(editor.show, [4001])
        hub.editor_done(editor)
        self.assertEqual(hub.sessions.by_id[hub.talk_target].name, "a")
        # The editor reports what it was asked to show; a report from a show the focus has
        # since moved past does not pull the focus back.
        hub._shown_at["/dev/pts/42"] = time.monotonic()
        self.assertIsNone(hub.terminal_in_front(4002))
        self.assertEqual(hub.sessions.by_id[hub.talk_target].name, "a")

    def test_escape_is_asked_for_once_and_only_of_a_session_in_a_turn(self):
        hub = self.got_the_words()  # "a" has the words and has begun on them
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41"}.get(pid)
        hub.sessions.by_id["a"].tty = "/dev/pts/41"
        hub.cancel()  # taken back: no editor is waiting, so the hook has to do it
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Taken back: stopping it"))
        editor = hub.editor_waits([4001])  # the editor asks a moment later
        hub.reconcile()
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "escape"}])
        again = hub.editor_waits([4001])
        hub.reconcile()
        self.assertEqual(hub.editor_done(again), [], "a second Escape would open the session's rewind list")
        hub.cfg.stop_at_once = False
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Stopped.")))
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        off = hub.editor_waits([4001])
        self.assertTrue(hub.speech.wait_idle(5))
        hub.talk_target = "a"
        hub.cancel()
        self.assertEqual(hub.editor_done(off), [], "switched off: only the hook")
        self.assertEqual(self.talks()[-1], ("stopped", "a", "Stopping at its next step"))

    def said(self, hub, words, sid):
        """Words heard for a session, and what the hub does with them done."""
        hub.follow_up(words, sid, delay=0)
        self.assertTrue(wait_for(lambda: hub._pending is None, 3))
        with hub.lock:  # and it is through with them
            pass

    def test_clear_the_chat_is_typed_by_the_editor_and_not_handed_to_the_session(self):
        hub = self.make()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        listener = hub.listen("a")
        # No editor that can type it: said so on the light, and the session is not bothered with it.
        old = hub.editor_waits([4001, 4002], shows=True)  # an extension from before this
        self.said(hub, "Hey Cloud, clear the chat.", "a")
        self.assertEqual(self.talks()[-1], ("failed", "a", "Not cleared: no editor to type it"))
        self.assertEqual((old.wake.is_set(), listener.wake.is_set(), hub.followups), (False, False, {}))
        hub.editor_done(old)
        editor = hub.editor_waits([4002, 4001, 9], shows=True, clears=True)
        self.said(hub, "Hey Cloud, clear the chat.", "a")
        self.assertTrue(editor.wake.is_set())
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "clear"}])
        self.assertEqual(self.talks()[-1], ("sent", "a", "Hey Cloud, clear the chat."))
        self.assertEqual((listener.wake.is_set(), hub.followups), (False, {}), "the session never gets the words")
        # Between two requests of the editor: the next request is handed it.
        self.said(hub, "clear the context please", "b")
        again = hub.editor_waits([4002, 4001], clears=True)
        self.assertEqual(hub.editor_done(again), [{"pid": 4002, "key": "clear"}])
        # Words that only hold the order are the session's.
        hub.editor_done(hub.editor_waits([4001], clears=True))
        self.said(hub, "clear the chat history file from the repo", "a")
        self.assertTrue(listener.wake.is_set())
        # Switched off, the order itself is too.
        hub.cfg.clear_by_voice = False
        waiting = hub.editor_waits([4001, 4002], clears=True)
        self.said(hub, "clear the chat", "b")
        self.assertEqual((waiting.wake.is_set(), hub.followups.get("b")), (False, ["clear the chat"]))

    def test_a_cleared_chat_is_confirmed_when_claude_code_ends_it(self):
        """No sound when the order goes to the editor; the end of the conversation with the
        reason "clear" says it worked, and only then the sound of "sent" plays."""
        hub = self.make()
        hub.sounds = FakeSounds()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        editor = hub.editor_waits([4001, 4002], clears=True)
        self.said(hub, "clear the chat", "a")
        hub.editor_done(editor)
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a", reason="clear"))
        self.assertEqual(hub.sounds.played, ["sent"])  # one sound, once it is done
        self.assertNotIn("a", hub._clearing)
        # Not seen done in time: said so, with the sound for "not done".
        self.addCleanup(setattr, hub_module.base, "CLEAR_CONFIRM", hub_module.base.CLEAR_CONFIRM)
        hub_module.base.CLEAR_CONFIRM = 0.2
        editor = hub.editor_waits([4002], clears=True)
        self.said(hub, "clear the chat", "b")
        self.assertTrue(wait_for(lambda: hub.sounds.played == ["sent", "failed"], 3))
        self.assertEqual(self.talks()[-1], ("failed", "b", "Not cleared: the chat is still there"))
        # In words, for those who chose spoken feedback.
        hub.cfg.talk_feedback = "voice"
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/c"))
        hub.sessions.by_id["c"].tty = "/dev/pts/41"
        hub.editor_done(editor)
        self.said(hub, "clear the chat", "c")
        hub.on_event(ev("SessionEnd", sid="c", cwd="/w/c", reason="clear"))
        self.assertTrue(hub.speech.wait_idle(5))
        self.assertEqual(self.spoken()[-1], "Chat cleared.")  # "Clearing." goes with the session if not yet said

    def test_a_cleared_chat_takes_its_lines_out_of_the_history(self):
        """/clear ends the conversation and the next one in that terminal has the same name,
        so its old lines would show under it: they go with the chat. Another end keeps them."""
        hub = self.make()
        for sid in ("a", "b"):
            hub.on_event(ev("SessionStart", sid=sid, cwd=f"/w/{sid}"))
            hub.history.append({"time": time.time(), "session": sid, "name": sid, "text": f"line of {sid}"})
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a", reason="clear"))
        hub.on_event(ev("SessionEnd", sid="b", cwd="/w/b", reason="other"))
        self.assertEqual([e["text"] for e in hub.history], ["line of b"])
        self.assertEqual(hub.history.maxlen, 100)

    def test_clear_the_chat_is_only_typed_for_a_session_at_its_prompt(self):
        """It is typed with an Enter, which would answer a dialog that is open in the terminal:
        said during a turn, it waits for the session to be back at its prompt."""
        hub = self.make()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41"}.get(pid)
        hub.sessions.by_id["a"].tty = "/dev/pts/41"
        editor = hub.editor_waits([4001], clears=True)
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        self.said(hub, "clear the chat", "a")
        self.assertEqual(self.talks()[-1], ("queued", "a", "clear the chat"))
        hub.reconcile()
        self.assertEqual((editor.wake.is_set(), hub.followups), (False, {}))
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Done.")))
        self.assertTrue(hub.speech.wait_idle(5))
        # The hooks have it at its prompt, Claude Code's own file does not (a dialog no hook told of).
        os.makedirs(hub.cfg.sessions_dir, exist_ok=True)
        status = os.path.join(hub.cfg.sessions_dir, f"{os.getpid()}.json")
        def file_says(what):
            with open(status, "w") as f:
                json.dump({"pid": os.getpid(), "sessionId": "a", "status": what, "statusUpdatedAt": time.time() * 1000}, f)
        file_says("busy")
        hub.reconcile()
        self.assertFalse(editor.wake.is_set())
        file_says("idle")
        hub.reconcile()
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "clear"}])
        self.assertEqual(hub._clear_after, {})
        # A prompt typed meanwhile, or words said after it, are for that conversation: no clear.
        for then in ("typed", "said"):
            editor = hub.editor_waits([4001], clears=True)
            hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
            self.said(hub, "clear the chat", "a")
            if then == "typed":
                hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="and this too"))
            else:
                self.said(hub, "and also the readme", "a")
            self.assertEqual(hub._clear_after, {}, then)
            hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Done.")))
            hub.reconcile()
            self.assertFalse(editor.wake.is_set(), then)
            hub.editor_done(editor)
        # A turn that runs past the wait: given up, and said so.
        self.addCleanup(setattr, hub_module.base, "CLEAR_WAIT", hub_module.base.CLEAR_WAIT)
        hub_module.base.CLEAR_WAIT = 0
        hub.followups.clear()
        editor = hub.editor_waits([4001], clears=True)
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        self.said(hub, "clear the chat", "a")
        hub.reconcile()
        self.assertEqual(self.talks()[-1], ("failed", "a", "Not cleared: its turn ran too long"))
        self.assertFalse(editor.wake.is_set())

    def test_a_clear_typed_after_its_turn_leaves_a_recording_on_screen(self):
        """The turn a clear waited for can end while you hold the talk key for another session;
        the overlay shows one push-to-talk step, so "sent" would take the listening sign away
        (the author, 2026-11-19: "I don't see the registering icon anymore")."""
        hub = self.make()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41"}.get(pid)
        hub.sessions.by_id["a"].tty = "/dev/pts/41"
        editor = hub.editor_waits([4001], clears=True)
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        self.said(hub, "clear the chat", "a")
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Done.")))
        self.assertTrue(hub.speech.wait_idle(5))
        with hub.lock:
            hub._talking = time.monotonic()  # the key is held, for session b
            hub._talk("listening", hub.sessions.by_id["b"])
        hub.reconcile()
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "clear"}], "it is still typed")
        self.assertEqual(self.talks()[-1][:2], ("listening", "b"))
        hub._talking = None

    def test_which_words_clear_a_conversation(self):
        words = hub_module.Config(run="r", state="s").clear_words
        for said in ("Hey, Cloud, clear the chat.", "Clear chat", "Okay Claude, can you clear the context?", "/clear",
                     "Slash clear.", "Run /clear", "clear this conversation now", "Clear your context for me", "I'll clear the chat.", "clear the shot"):
            self.assertTrue(hub_module.base.asks_to_clear(said, words), said)
        for said in ("Clear the chat history file from the repo", "clear", "Don't clear the chat", "clear the cache",
                     "is it possible to say clear the chat", "", "the"):
            self.assertFalse(hub_module.base.asks_to_clear(said, words), said)
        self.assertTrue(hub_module.base.asks_to_clear("Pulisci la chat", ["pulisci la chat"]))

    USAGE = ("Current session: 26% used \u00b7 resets Nov 18, 2:39am (America/New_York)\n"
             "Current week (all models): 38% used \u00b7 resets Nov 23, 7:59am (America/New_York)\n")

    def test_a_spoken_question_about_the_usage_is_answered_aloud_and_reaches_no_session(self):
        hub = self.make(talk_feedback="none")
        asked = []
        hub.usage_ask = lambda program, timeout: asked.append(program) or (self.USAGE, "")
        listener = hub.listen("a")
        hub.follow_up("what's my usage", "a", delay=0)
        self.assertTrue(wait_for(lambda: any("26 percent of the five hours" in line for line in self.spoken())), self.spoken())
        self.assertEqual(len(asked), 1)
        self.assertFalse(listener.wake.is_set(), "the session was given the question")
        self.assertEqual(hub.followups, {})
        shown = [m for m in self.overlay.of("talk") if m.get("state") == "aside"]
        self.assertEqual((shown[-1]["name"], shown[-1]["hint"]), ("a", "Reading your usage\u2026"))
        self.assertEqual(self.overlay.of("talk")[-1], {"type": "talk"})  # and taken off the screen again
        hub.follow_up("add a usage meter to the overlay", "a", delay=0)  # about usage, but work for the session
        self.assertTrue(listener.wake.wait(3))
        self.assertEqual(hub.collect(listener), "add a usage meter to the overlay")
        self.assertEqual(len(asked), 1)

    def test_the_plans_usage_goes_to_the_overlay_and_is_read_again_only_when_it_is_old(self):
        hub = self.make(usage_shown=True, usage_warn=30)
        asked = []
        hub.usage_ask = lambda program, timeout: asked.append(program) or (self.USAGE, "")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a"))
        hub.reconcile()
        self.assertTrue(wait_for(lambda: self.overlay.of("state")[-1]["usage"] == [["5 hours", 26, ""], ["Week", 38, "warn"]]))
        hub.reconcile()
        hub.reconcile()
        self.assertEqual(len(asked), 1, "read a moment ago")
        hub.usage_ask = lambda program, timeout: ("", "no answer")  # a reading that fails leaves the last figures
        hub._plan_asked = float("-inf")
        hub.reconcile()
        self.assertTrue(wait_for(lambda: not hub._plan_busy))
        hub.publish()
        self.assertEqual(self.overlay.of("state")[-1]["usage"][0], ["5 hours", 26, ""])
        hub.cfg.usage_shown = False
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message=tag("Done.")))
        self.assertEqual(self.overlay.of("state")[-1]["usage"], [])

    def test_the_week_of_one_model_can_be_a_bar_of_its_own(self):
        hub = self.make(usage_shown=True)
        fable = self.USAGE + "Current week (Fable): 89% used \u00b7 resets Nov 23, 7:59am (America/New_York)\n"
        hub.usage_ask = lambda program, timeout: (fable, "")
        hub.usage(quiet=True)
        self.assertEqual(hub._plan_bars(), [["5 hours", 26, ""], ["Week", 38, ""]])  # not unless asked for
        hub.cfg.usage_models = "all"
        self.assertEqual(hub._plan_bars(), [["5 hours", 26, ""], ["Week", 38, ""], ["Fable", 89, "warn"]])
        hub.cfg.usage_models, hub.cfg.usage_warn = "near", 95  # only once it is near its end
        self.assertEqual(hub._plan_bars(), [["5 hours", 26, ""], ["Week", 38, ""]])
        hub.cfg.usage_warn = 80
        self.assertEqual(hub._plan_bars()[-1], ["Fable", 89, "warn"])

    def test_usage_that_cannot_be_read_says_so_and_can_be_switched_off(self):
        hub = self.make(talk_feedback="none")
        hub.usage_ask = lambda program, timeout: ("", "no answer in 20s")
        hub.follow_up("how much usage do I have left", "a", delay=0)
        self.assertTrue(wait_for(lambda: "I could not read the usage." in self.spoken()), self.spoken())
        hub.cfg.usage_by_voice = False
        listener = hub.listen("a")
        hub.follow_up("what's my usage", "a", delay=0)
        self.assertTrue(listener.wake.wait(3), "switched off: the words are the session's")

    def test_the_cancel_key_cuts_a_line_before_it_stops_anyone(self):
        hub = self.make(duration=2.0)
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        hub.on_event(ev("Stop", sid="b", cwd="/w/b", last_assistant_message=tag("A long line from the other session.")))
        self.assertTrue(wait_for(lambda: hub.speech.current is not None and hub.talk_target == "b"))
        hub.talk_target = "a"  # the one that speaks took the focus; it is moved back by hand
        hub.cancel()
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "stop", "a")), "that press was for the voice")
        self.assertTrue(wait_for(lambda: hub.speech.current is None))
        hub.cancel()
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "stop", "a")))

    def test_the_cancel_key_can_be_kept_from_stopping_sessions(self):
        hub = self.make(cancel_stops="sent")
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="go"))
        hub.talk_target = "a"
        hub.cancel()
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "stop", "a")))

    def test_a_hub_that_starts_forgets_what_the_last_one_wanted_stopped(self):
        hub = self.got_the_words()
        hub.cancel()
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "stop", "a")))
        again = Hub(self.cfg, NullEngine())
        self.addCleanup(again.speech.close)
        self.assertEqual(os.listdir(os.path.join(self.tmp, "stop")), [])

    def test_cancel_after_the_session_got_the_words_tells_it_to_ignore_them(self):
        hub = self.make(cancel_stops="never")
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
        hub = self.make(unsend_seconds=0.2, cancel_stops="sent")  # or the key would stay, to stop the session
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
        base.TAP = 30
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertEqual(hub.talk_target, "b")
        self.assertIn(("focus", "b", ""), self.talks())
        self.assertFalse(wait_for(lambda: hub.followups, 0.2))

    def test_a_quick_tap_does_nothing_by_itself(self):
        hub = self.make()
        base.TAP = 30
        hub.talk_target = "a"
        hub.talk_start()
        hub.talk_end()
        self.assertEqual(hub.talk_target, "a")
        self.assertFalse(wait_for(lambda: hub.followups, 0.2))

    def test_a_quick_tap_does_not_leave_the_listening_sign_up(self):
        hub = self.make()
        base.TAP = 30
        hub.talk_target = "a"
        hub.talk_start()
        self.assertEqual(self.talks()[-1][0], "listening")
        hub.talk_end()
        self.assertIsNone(self.talks()[-1][0])  # taken away: it stayed as if the key were still held
        self.assertIsNone(hub._talk_shown)  # and a move of the focus does not bring it back

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
        base.TAP = 30  # the next press is a tap
        hub.talk_start()
        hub.talk_end()
        self.assertTrue(listener.wake.wait(2))
        self.assertEqual(hub.collect(listener), "also add a test")

    def test_unconfirmed_follow_up_is_dropped_not_sent(self):
        hub = self.make(followup_confirm=True)
        self.addCleanup(setattr, base, "CONFIRM_WINDOW", base.CONFIRM_WINDOW)
        base.CONFIRM_WINDOW = 0.1
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

    def test_a_prompt_typed_to_a_session_gives_it_the_focus(self):
        hub = self.make()
        hub.talk_target = "a"
        hub.on_event(ev("UserPromptSubmit", sid="b", cwd="/w/b", prompt="run the tests"))
        self.assertEqual(self.in_focus(), "b")  # you are there: what you say next is for it
        # A spoken follow-up reaches its session as a prompt too, wrapped in markup: not typed.
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="<task-notification>and the docs</task-notification>"))
        self.assertEqual(self.in_focus(), "b")
        # While you hold the talk key the words have their session, whatever is typed elsewhere.
        hub.talk_start()
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="something typed"))
        self.assertEqual(self.in_focus(), "b")
        hub.cancel()

    def test_typed_prompts_can_be_kept_from_moving_the_focus(self):
        hub = self.make(focus_on_prompt=False)
        hub.talk_target = "a"
        hub.on_event(ev("UserPromptSubmit", sid="b", cwd="/w/b", prompt="run the tests"))
        self.assertEqual(self.in_focus(), "a")

    def test_overlay_claims_keys_only_while_they_can_act(self):
        hub = self.make()
        hub.publish()
        arrows = ["focus_next", "focus_prev"]  # there are two sessions to move between
        self.assertEqual(self.overlay.of("keys")[-1]["live"], arrows)
        hub.request_permission(ask(sid="a", cwd="/w/a"))
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "deny"] + arrows)
        hub.talk_start()
        self.assertEqual(self.overlay.of("keys")[-1]["live"], ["allow", "cancel", "deny"] + arrows)


class SideQuestions(HubCase):
    """Spoken words that open with "by the way" are answered at once by a copy of a busy session."""

    def make(self, answer="It is in the hub folder.", why="", **kw):
        hub = super().make(label="never", **kw)
        hub.overlay = self.overlay = FakeOverlay()
        hub.sounds = FakeSounds()
        self.asked, self.go = [], threading.Event()  # what the copy was asked; set `go` to let it answer
        self.go.set()

        def run(aside, cwd, question):
            self.asked.append((aside.session, cwd, question))
            self.go.wait(5)
            return answer, why
        hub.aside_run = run
        hub.on_event(ev("SessionStart", sid="a", cwd="/w/a"))
        hub.on_event(ev("SessionStart", sid="b", cwd="/w/b"))
        hub.on_event(ev("UserPromptSubmit", sid="a", cwd="/w/a", prompt="build it"))  # A is in the middle of a turn
        return hub

    def talks(self):
        return [(m.get("state"), m.get("name", ""), m.get("text", "")) for m in self.overlay.of("talk")]

    def test_the_opening_words_make_a_side_question(self):
        q = hub_module.aside_question
        self.assertEqual(q("By the way, where is the socket?", ["by the way", "btw"]), "where is the socket?")
        self.assertEqual(q("by  the way where is it", ["by the way"]), "where is it")
        self.assertEqual(q("BTW: is it done?", ["by the way", "btw"]), "is it done?")
        self.assertEqual(q("A proposito, a che punto sei?", ["by the way", "a proposito"]), "a che punto sei?")
        self.assertEqual(q("By the wayside inn we stopped", ["by the way"]), "")
        self.assertEqual(q("Run the tests, by the way", ["by the way"]), "")  # only as the opening
        self.assertEqual(q("By the way.", ["by the way"]), "")  # nothing asked
        self.assertEqual(q("By the way, what now?", []), "")
        self.assertEqual(q("Oh, by the way, what time is it right now?", ["by the way", "btw"]), "what time is it right now?")
        self.assertEqual(q("Alright, so, btw is it done?", ["by the way", "btw"]), "is it done?")
        self.assertEqual(q("Oh no, by the way is blocked", ["by the way"]), "")  # "no" is not such a word

    def test_the_copy_is_told_the_time(self):
        asked = hub_module.base.aside_prompt("what time is it?")
        self.assertIn(time.strftime("%A, %d %B %Y"), asked)
        self.assertTrue(asked.endswith("The question: what time is it?"))

    def test_an_answer_is_cleaned_for_the_voice(self):
        clean = hub_module.spoken_answer
        self.assertEqual(clean('<speak title="Side">It is `done`.</speak>\n'), "It is done.")
        self.assertEqual(clean("**Yes.**\nTwo  tests\tfail.\n"), "Yes. Two tests fail.")
        self.assertEqual(clean("One. " + "word " * 200, limit=40), "One.")
        self.assertEqual(clean("  \n"), "")

    def test_a_busy_session_answers_on_the_side_and_never_gets_the_words(self):
        hub = self.make()
        listener = hub.listen("a")
        self.go.clear()
        hub.follow_up("By the way, where is the socket?", "a", delay=0)
        self.assertTrue(wait_for(lambda: self.asked))
        self.assertEqual(self.asked, [("a", "/w/a", "where is the socket?")])
        self.assertEqual(self.talks()[-1], ("aside", "a", "By the way, where is the socket?"))
        self.assertIn("cancel", self.overlay.of("keys")[-1]["live"])  # it can be taken back while the copy thinks
        self.go.set()
        self.assertTrue(wait_for(lambda: self.engine.spoken))
        self.assertEqual(self.spoken(), ["It is in the hub folder."])
        self.assertEqual(self.engine.spoken[0][1], next(s["voice"] for s in hub.snapshot()["sessions"] if s["id"] == "a"))
        self.assertEqual(self.talks()[-1][0], None)  # the sign is gone once the answer is there
        self.assertEqual(hub.sounds.played, ["sent"])
        self.assertFalse(hub.followups.get("a"))
        self.assertFalse(listener.wake.is_set())
        self.assertEqual(self.session("a")["state"], "working")
        self.assertEqual(hub.history[-1]["text"], "It is in the hub folder.")  # the repeat key has it

    def test_an_idle_session_gets_the_words_as_usual(self):
        hub = self.make()
        listener = hub.listen("b")
        hub.follow_up("By the way, run the tests too", "b", delay=0)
        self.assertTrue(listener.wake.wait(3))
        self.assertEqual(hub.collect(listener), "By the way, run the tests too")
        self.assertEqual(self.asked, [])

    def test_always_asks_on_the_side_and_off_never_does(self):
        hub = self.make(aside="always")
        hub.follow_up("By the way, what is left?", "b", delay=0)
        self.assertTrue(wait_for(lambda: self.asked))
        self.assertFalse(hub.followups.get("b"))
        hub = self.make(aside="off")
        hub.follow_up("By the way, what is left?", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        self.assertEqual(self.asked, [])

    def test_other_words_for_a_busy_session_still_wait(self):
        hub = self.make()
        hub.follow_up("and add a test", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        self.assertEqual(self.asked, [])

    def test_the_answer_does_not_replace_the_sessions_own_waiting_line(self):
        hub = self.make(duration=0.3)
        hub.on_display(ev("MessageDisplay", sid="b", cwd="/w/b", delta=tag("B talks for a while.")))
        time.sleep(0.05)
        hub.on_event(ev("Notification", sid="a", cwd="/w/a", notification_type="permission_prompt"))  # A's own line waits
        hub.follow_up("By the way, where is the socket?", "a", delay=0)
        self.assertTrue(wait_for(lambda: len(self.engine.spoken) >= 3))
        self.assertEqual(sorted(self.spoken()), sorted(["B talks for a while.", "I need your input", "It is in the hub folder."]))

    def test_with_no_answer_the_words_go_to_the_session(self):
        hub = self.make(answer="", why="no answer in 60s")
        hub.follow_up("By the way, where is the socket?", "a", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        self.assertEqual(hub.followups["a"], ["By the way, where is the socket?"])
        self.assertEqual(self.talks()[-1][0], "queued")
        self.assertEqual(self.spoken(), [])
        self.assertTrue(wait_for(lambda: hub.sounds.played == ["sent", "queued"]))

    def test_the_cancel_key_drops_the_question_and_leaves_the_session_working(self):
        hub = self.make()
        self.go.clear()
        hub.follow_up("By the way, where is the socket?", "a", delay=0)
        self.assertTrue(wait_for(lambda: self.asked))
        hub.cancel()
        self.assertEqual(self.talks()[-1], ("failed", "a", "Cancelled"))
        self.assertEqual(hub._stopping, {})  # the key did not go on to stop A's turn
        self.go.set()
        self.assertTrue(wait_for(lambda: not hub._asides))
        self.assertEqual(self.spoken(), [])
        self.assertFalse(hub.followups.get("a"))
        self.assertEqual(self.session("a")["state"], "working")

    def test_a_session_that_ends_takes_its_side_question_with_it(self):
        hub = self.make()
        self.go.clear()
        hub.follow_up("By the way, where is the socket?", "a", delay=0)
        self.assertTrue(wait_for(lambda: self.asked))
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a"))
        self.go.set()
        self.assertTrue(wait_for(lambda: not hub._asides))
        self.assertEqual(self.spoken(), [])

    def test_the_copy_is_a_real_process_that_leaves_the_session_alone(self):
        tmp = tempfile.mkdtemp(prefix="cs-aside-")
        program, seen = os.path.join(tmp, "claude"), os.path.join(tmp, "seen.json")
        with open(program, "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, os, sys\n"
                    f"json.dump({{'args': sys.argv[1:], 'cwd': os.getcwd(), 'inside': os.environ.get('CLAUDECODE'),\n"
                    f"           'kept': os.environ.get('CLAUDE_CONFIG_DIR'),\n"
                    f"           'saving': os.environ.get('DISABLE_PROMPT_CACHING')}}, open({seen!r}, 'w'))\n"
                    "print('<speak title=\"Side\">It listens on a socket.</speak>')\n")
        os.chmod(program, 0o755)
        hub = self.make(aside_claude=program, aside_model="haiku")
        del hub.aside_run  # the real one
        hub.on_event(ev("UserPromptSubmit", sid="c0ffee-12", cwd=tmp, prompt="build it"))
        with unittest.mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "x", "CLAUDE_CONFIG_DIR": "/cfg"}):
            hub.follow_up("By the way, how does it listen?", "c0ffee-12", delay=0)
            self.assertTrue(wait_for(lambda: self.engine.spoken))
        self.assertEqual(self.spoken(), ["It listens on a socket."])
        with open(seen) as f:
            seen = json.load(f)
        args = seen["args"]
        self.assertEqual(args[:5], ["-p", "--resume", "c0ffee-12", "--fork-session", "--no-session-persistence"])
        self.assertEqual(json.loads(args[args.index("--settings") + 1]), {"disableAllHooks": True})
        self.assertEqual((args[args.index("--tools") + 1], args[args.index("--model") + 1]), ("", "haiku"))
        self.assertEqual(args[-2], "--")  # or the words would be read as more names of tools
        self.assertTrue(args[-1].endswith("The question: how does it listen?"))
        self.assertEqual((seen["cwd"], seen["inside"], seen["kept"]), (os.path.realpath(tmp), None, "/cfg"))
        self.assertEqual(seen["saving"], "1")  # the copy does not pay to save a conversation it reads once

    def test_on_the_sessions_own_model_the_copy_keeps_the_tools_and_may_use_none_that_acts(self):
        tmp = tempfile.mkdtemp(prefix="cs-aside-")
        program, seen = os.path.join(tmp, "claude"), os.path.join(tmp, "seen.json")
        with open(program, "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, os, sys\n"
                    f"json.dump({{'args': sys.argv[1:], 'saving': os.environ.get('DISABLE_PROMPT_CACHING')}}, open({seen!r}, 'w'))\n"
                    "print('It listens on a socket.')\n")
        os.chmod(program, 0o755)
        record = os.path.join(tmp, "projects", "-w-c")
        os.makedirs(record)
        with open(os.path.join(record, "c0ffee-12.jsonl"), "w") as f:
            for model, effort, side in (("claude-old-1", "low", False), ("claude-new-2", "high", False), ("claude-side-3", "max", True)):
                f.write(json.dumps({"type": "assistant", "effort": effort, "isSidechain": side, "message": {"model": model}}) + "\n")
                f.write(json.dumps({"type": "user", "message": {"content": "an \"assistant\" is mentioned"}}) + "\n")
        hub = self.make(aside_claude=program, projects_dir=os.path.join(tmp, "projects"))
        self.assertEqual(hub.cfg.aside_model, "session")
        del hub.aside_run  # the real one
        hub.on_event(ev("UserPromptSubmit", sid="c0ffee-12", cwd=tmp, prompt="build it"))
        hub.follow_up("By the way, how does it listen?", "c0ffee-12", delay=0)
        self.assertTrue(wait_for(lambda: self.engine.spoken))
        self.assertEqual(self.spoken(), ["It listens on a socket."])
        with open(seen) as f:
            seen = json.load(f)
        args = seen["args"]
        self.assertEqual((args[args.index("--model") + 1], args[args.index("--effort") + 1]), ("claude-new-2", "high"))
        self.assertEqual(args[args.index("--permission-mode") + 1], "default")
        settings = json.loads(args[args.index("--settings") + 1])
        self.assertTrue(settings["disableAllHooks"])
        self.assertTrue({"Bash", "Edit", "Write", "Read", "mcp__*"} <= set(settings["permissions"]["ask"]))
        for changes_the_start in ("--tools", "--disallowedTools", "--strict-mcp-config"):
            self.assertNotIn(changes_the_start, args)  # or what the session has saved is not reused
        self.assertIsNone(seen["saving"])
        self.assertEqual(args[-2], "--")

    def test_a_session_with_no_record_is_asked_on_claude_codes_own_choice_of_model(self):
        self.assertEqual(hub_module.session_model(tempfile.mkdtemp(prefix="cs-aside-"), "c0ffee-12"), ("", ""))

    def test_a_copy_that_fails_or_takes_too_long_gives_the_words_to_the_session(self):
        tmp = tempfile.mkdtemp(prefix="cs-aside-")
        program = os.path.join(tmp, "claude")
        with open(program, "w") as f:
            f.write("#!/bin/sh\necho 'No conversation found' >&2\nexit 1\n")
        os.chmod(program, 0o755)
        hub = self.make(aside_claude=program)
        del hub.aside_run
        hub.follow_up("By the way, how does it listen?", "a", delay=0)  # its folder /w/a does not exist either
        self.assertTrue(wait_for(lambda: hub.followups.get("a")))
        hub.on_event(ev("UserPromptSubmit", sid="slow", cwd=tmp, prompt="build it"))
        with open(program, "w") as f:
            f.write("#!/bin/sh\nsleep 30\n")
        hub.cfg.aside_timeout = 0.2
        started = time.monotonic()
        hub.follow_up("By the way, are you there?", "slow", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("slow")))
        self.assertLess(time.monotonic() - started, 3)


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

    def a_session_that_runs(self, *commands):
        """A stand-in for a session's process: for each line it is sent, it starts the next of
        `commands` the way Claude Code starts a Bash tool's command, in a shell of its own."""
        code = ("import subprocess, sys\n"
                "for command in sys.argv[1:]:\n"
                "    sys.stdin.readline()\n"
                "    subprocess.Popen(['/bin/sh', '-c', 'true /home/x/.claude/shell-snapshots/snap.sh"
                " && : eval ' + repr(command) + ' ; sleep 30; true'])\n"  # named, not run
                "    print('started', flush=True)\n"
                "sys.stdin.readline()\n")
        proc = subprocess.Popen([sys.executable, "-c", code, *commands], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: subprocess.run(["pkill", "-P", str(proc.pid)]) and None)
        self.addCleanup(proc.kill)

        def start():
            proc.stdin.write("go\n")
            proc.stdin.flush()
            proc.stdout.readline()
        return proc, start

    def test_a_command_allowed_in_the_terminal_is_seen_starting(self):
        """No hook reports a yes typed in the terminal, and the session showed "needs you"
        until the command was done. The command starting is what tells."""
        hub = self.make()
        proc, start = self.a_session_that_runs("npm test")
        self.record("s1", "busy", pid=proc.pid)
        hub.on_event(ev("UserPromptSubmit"))
        req = hub.request_permission(ask())
        hub.on_event(ev("Notification", notification_type="permission_prompt"))  # still open after six seconds
        hub.reconcile()
        self.assertEqual(self.session()["state"], "needs_you")
        self.assertFalse(req.done.is_set())
        start()
        hub.reconcile()
        self.assertTrue(req.done.is_set())
        self.assertIsNone(req.decision)  # the hook prints nothing: the terminal has answered
        self.assertEqual(self.session()["state"], "working")

    def test_another_command_of_the_session_does_not_answer_the_question(self):
        hub = self.make()
        proc, start = self.a_session_that_runs("ls -la src", "git status", "npm test")
        self.record("s1", "busy", pid=proc.pid)
        hub.on_event(ev("UserPromptSubmit"))
        start()  # one that was running before it asked
        req = hub.request_permission(ask())
        hub.reconcile()
        start()  # and one that a helper of the session starts meanwhile
        hub.reconcile()
        self.assertFalse(req.done.is_set())
        self.assertEqual(self.session()["state"], "needs_you")
        start()
        hub.reconcile()
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

    def test_colors_too_near_each_other_are_set_apart_at_a_restart(self):
        import state

        hub = self.make()
        for sid in "abcd":
            hub.on_event(ev("SessionStart", sid=sid))
        hub.publish()
        path = hub._sessions_file()
        with open(path) as f:
            kept = json.load(f)
        # As the author had them: pink, the old orange, yellow, teal.
        for entry, color in zip(kept["sessions"], ["#FF8FA3", "#FFB86B", "#F9E27D", "#7FDBCA"]):
            entry["color"] = color
        with open(path, "w") as f:
            json.dump(kept, f)
        again = self.restart()
        for sid in "abcd":
            again.on_event(ev("SessionStart", sid=sid))
        colors = [c for _, _, c, _ in self.who()]
        self.assertEqual((colors[0], colors[2], colors[3]), ("#FF8FA3", "#F9E27D", "#7FDBCA"))  # these were fine
        self.assertIn(colors[1], state.COLORS)
        apart = min(state.color_distance(a, b) for i, a in enumerate(colors) for b in colors[:i])
        self.assertGreaterEqual(apart, state.TOO_CLOSE, colors)
        kept["sessions"][1]["color"] = "#FFA24D"  # today's orange, beside the yellow: the later of the two moves
        with open(path, "w") as f:
            json.dump(kept, f)
        third = self.restart()
        for sid in "abcd":
            third.on_event(ev("SessionStart", sid=sid))
        colors = [c for _, _, c, _ in self.who()]
        self.assertEqual((colors[0], colors[1], colors[3]), ("#FF8FA3", "#FFA24D", "#7FDBCA"))
        self.assertGreaterEqual(state.color_distance(colors[2], "#FFA24D"), state.TOO_CLOSE)

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

    def test_an_order_dragged_in_the_overlay_is_kept_across_a_restart(self):
        hub = self.three()
        names = {sid: name for sid, name, _, _ in self.who()}
        hub.on_overlay({"type": "reorder", "names": [names["c"], names["a"], names["b"]]})
        self.assertEqual([sid for sid, _, _, _ in self.who()], ["c", "a", "b"])
        hub.on_overlay({"type": "reorder", "names": ["nobody", 3]})  # names it does not know move nothing
        self.assertEqual([sid for sid, _, _, _ in self.who()], ["c", "a", "b"])
        self.restart()
        for sid in "bac":  # they come back in another order
            self.hub.listen(sid)
        self.assertEqual([sid for sid, _, _, _ in self.who()], ["c", "a", "b"])
        self.hub.on_event(ev("SessionStart", sid="d"))
        self.assertEqual([sid for sid, _, _, _ in self.who()][-1], "d", "a new session goes at the end")

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

    def test_stop_hook_ends_the_turn_of_the_session_that_was_asked_to_stop(self):
        hub = self.hub
        hub.on_event(ev("UserPromptSubmit", prompt="go"))
        call = ev("PreToolUse", tool_name="Bash", tool_input={"command": "npm test"})
        self.assertEqual(self.hook("stop.sh", call).stdout, "")  # nobody asked
        with hub.lock:
            self.assertTrue(hub._stop_turn(hub.sessions.by_id["s1"]))
        self.assertEqual(self.hook("stop.sh", ev("PreToolUse", sid="s2")).stdout, "", "another session goes on")
        told = json.loads(self.hook("stop.sh", call).stdout)
        self.assertIs(told["continue"], False)
        self.assertEqual(told["hookSpecificOutput"]["permissionDecision"], "deny")  # this call is not made either
        self.assertEqual(self.hook("stop.sh", call).stdout, "")  # once
        hub.reconcile()
        self.assertEqual(self.session()["state"], "idle")
        with hub.lock:
            hub._stop_turn(hub.sessions.by_id["s1"])
        told = json.loads(self.hook("stop.sh", ev("PostToolUse", tool_name="Bash")).stdout)
        self.assertEqual((told["continue"], "hookSpecificOutput" in told), (False, False))

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
        base.MIN_SHOWN, old = 0, base.MIN_SHOWN
        self.addCleanup(setattr, base, "MIN_SHOWN", old)
        proc = self.start_permission_hook()
        self.assertTrue(self.hub.decide("deny"))
        decision = json.loads(proc.communicate(timeout=5)[0])["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("overlay", decision["message"])
        self.spoken()

    def test_words_spoken_at_a_permission_prompt_turn_it_down_and_follow_as_the_next_message(self):
        hub = self.hub
        hub.on_event(ev("UserPromptSubmit", prompt="clean up"))
        proc = self.start_permission_hook()
        hub.follow_up("Do not delete it, rename it instead", session="s1", delay=0)
        decision = json.loads(proc.communicate(timeout=5)[0])["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("more details", decision["message"])
        self.assertEqual(hub.requests, [])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "stop", "s1")), "its turn goes on without the words")
        self.assertEqual(hub.followups.get("s1"), ["Do not delete it, rename it instead"])
        hub.on_event(ev("Stop", last_assistant_message=tag("I will wait for your details.")))  # the turn ended
        self.assertNotIn("I will wait for your details.", self.spoken())  # nothing to hear: the words are on their way
        self.assertEqual(hub.collect(hub.listen("s1")), "Do not delete it, rename it instead")

    def test_words_spoken_at_a_permission_prompt_can_be_made_to_wait(self):
        hub = self.hub
        hub.cfg.voice_at_prompt = "wait"
        hub.on_event(ev("UserPromptSubmit", prompt="clean up"))
        proc = self.start_permission_hook()
        hub.follow_up("Do not delete it, rename it instead", session="s1", delay=0)
        self.assertTrue(wait_for(lambda: hub.followups.get("s1")))
        self.assertEqual(len(hub.requests), 1, "the request is still open")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "stop", "s1")))
        base.MIN_SHOWN, old = 0, base.MIN_SHOWN
        self.addCleanup(setattr, base, "MIN_SHOWN", old)
        self.assertTrue(hub.decide("allow"))
        proc.communicate(timeout=5)
        self.spoken()

    def test_permission_hook_hands_claude_the_chosen_option(self):
        base.MIN_SHOWN, old = 0, base.MIN_SHOWN
        self.addCleanup(setattr, base, "MIN_SHOWN", old)
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
                  terminals: [],
                  activeTerminal: { processId: Promise.resolve(Number(process.env.SHELL_PID)) },
                  onDidChangeActiveTerminal: (f) => { went.push(f); return { dispose() {} }; },
                  onDidChangeWindowState: (f) => ({ dispose() {} }),
                  onDidOpenTerminal: (f) => ({ dispose() {} }),
                  onDidCloseTerminal: (f) => ({ dispose() {} }),
                };""")
        # It also keeps a request open with the hub (see the next test), so it is ended by hand.
        go = ("const x = require('./extension.js'); x.activate({ subscriptions: [] }); require('vscode').went[0]();"
              "setTimeout(() => process.exit(0), 600);")
        # Told within two seconds of the hub starting, or the hub has not looked for the terminals yet.
        self.assertTrue(wait_for(lambda: subprocess.run(
            ["node", "-e", go], cwd=ext, env={**self.env, "SHELL_PID": str(pids["a"])}, timeout=10).returncode == 0
            and self.call("/target", {})["target"] == "alpha", 8), "the hub did not move the focus")


    @unittest.skipUnless(__import__("shutil").which("node"), "needs node to run the editor extension")
    def test_the_editor_extension_types_escape_into_the_terminal_of_a_session_that_is_stopped(self):
        """The real extension code, with a stand-in for the editor, against a real hub: the
        cancel key on a working session ends in one Escape, without Enter, in its terminal."""
        import pty
        import shutil
        sessions = os.path.join(self.tmp, ".claude", "sessions")
        os.makedirs(sessions)
        ours, theirs = pty.openpty()  # the terminal the session runs in
        shell = subprocess.Popen(["sleep", "30"], stdin=theirs)
        os.close(theirs)
        self.addCleanup(os.close, ours)
        self.addCleanup(shell.wait)
        self.addCleanup(shell.kill)
        with open(os.path.join(sessions, f"{shell.pid}.json"), "w") as f:
            json.dump({"pid": shell.pid, "sessionId": "a", "status": "busy", "statusUpdatedAt": time.time() * 1000}, f)
        self.start_hub()
        self.call("/event", ev("UserPromptSubmit", sid="a", cwd="/work/alpha", prompt="go"))
        ext = os.path.join(self.tmp, "ext")
        os.makedirs(os.path.join(ext, "node_modules", "vscode"))
        shutil.copy(os.path.join(ROOT, "vscode", "extension.js"), ext)
        typed = os.path.join(self.tmp, "typed.json")
        with open(os.path.join(ext, "node_modules", "vscode", "index.js"), "w") as f:
            f.write("""
                const fs = require("fs");
                const typed = [];
                const terminal = (pid) => ({
                  processId: Promise.resolve(pid),
                  sendText: (text, enter) => { typed.push([pid, text, enter]); fs.writeFileSync(process.env.TYPED, JSON.stringify(typed)); },
                });
                exports.window = {
                  state: { focused: true },
                  terminals: [terminal(1), terminal(Number(process.env.SHELL_PID))],
                  activeTerminal: undefined,
                  onDidChangeActiveTerminal: (f) => ({ dispose() {} }),
                  onDidChangeWindowState: (f) => ({ dispose() {} }),
                  onDidOpenTerminal: (f) => ({ dispose() {} }),
                  onDidCloseTerminal: (f) => ({ dispose() {} }),
                };""")
        editor = subprocess.Popen(["node", "-e", "require('./extension.js').activate({ subscriptions: [] });"], cwd=ext,
                                  env={**self.env, "SHELL_PID": str(shell.pid), "TYPED": typed})
        self.addCleanup(editor.wait)
        self.addCleanup(editor.kill)
        time.sleep(1.5)  # the hub has found the session's terminal, and the editor's request is with it
        self.call("/talk", {"action": "cancel"})
        self.assertTrue(wait_for(lambda: os.path.exists(typed), 8), "nothing was typed into the terminal")
        time.sleep(1.5)  # long enough for a second Escape, which must not come
        with open(typed) as f:
            self.assertEqual(json.load(f), [[shell.pid, "\x1b", False]])

    @unittest.skipUnless(__import__("shutil").which("node"), "needs node to run the editor extension")
    def test_the_editor_extension_types_clear_into_the_terminal_of_a_session_told_to_clear(self):
        """The real extension code, with a stand-in for the editor, against a real hub: "clear
        the chat" said to a session at its prompt ends in Ctrl+C and then /clear with Enter
        in its terminal, and in nothing else."""
        import pty
        import shutil
        sessions = os.path.join(self.tmp, ".claude", "sessions")
        os.makedirs(sessions)
        ours, theirs = pty.openpty()  # the terminal the session runs in
        shell = subprocess.Popen(["sleep", "30"], stdin=theirs)
        os.close(theirs)
        self.addCleanup(os.close, ours)
        self.addCleanup(shell.wait)
        self.addCleanup(shell.kill)
        with open(os.path.join(sessions, f"{shell.pid}.json"), "w") as f:
            json.dump({"pid": shell.pid, "sessionId": "a", "status": "idle", "statusUpdatedAt": time.time() * 1000}, f)
        self.start_hub()
        self.call("/event", ev("SessionStart", sid="a", cwd="/work/alpha"))
        ext = os.path.join(self.tmp, "ext")
        os.makedirs(os.path.join(ext, "node_modules", "vscode"))
        shutil.copy(os.path.join(ROOT, "vscode", "extension.js"), ext)
        typed = os.path.join(self.tmp, "typed.json")
        with open(os.path.join(ext, "node_modules", "vscode", "index.js"), "w") as f:
            f.write("""
                const fs = require("fs");
                const typed = [];
                const terminal = (pid) => ({
                  processId: Promise.resolve(pid),
                  sendText: (text, enter) => { typed.push([pid, text, enter]); fs.writeFileSync(process.env.TYPED, JSON.stringify(typed)); },
                });
                exports.window = {
                  state: { focused: true },
                  terminals: [terminal(1), terminal(Number(process.env.SHELL_PID))],
                  activeTerminal: undefined,
                  onDidChangeActiveTerminal: (f) => ({ dispose() {} }),
                  onDidChangeWindowState: (f) => ({ dispose() {} }),
                  onDidOpenTerminal: (f) => ({ dispose() {} }),
                  onDidCloseTerminal: (f) => ({ dispose() {} }),
                };""")
        editor = subprocess.Popen(["node", "-e", "require('./extension.js').activate({ subscriptions: [] });"], cwd=ext,
                                  env={**self.env, "SHELL_PID": str(shell.pid), "TYPED": typed})
        self.addCleanup(editor.wait)
        self.addCleanup(editor.kill)
        time.sleep(1.5)  # the hub has found the session's terminal, and the editor's request is with it
        self.call("/follow-up", {"text": "Hey Claude, clear the chat.", "session": "alpha", "delay": 0})
        self.assertTrue(wait_for(lambda: os.path.exists(typed), 8), "nothing was typed into the terminal")
        time.sleep(1.0)
        with open(typed) as f:
            self.assertEqual(json.load(f), [[shell.pid, "\x03", False], [shell.pid, "/clear\r", False]])

    @unittest.skipUnless(__import__("shutil").which("node"), "needs node to run the editor extension")
    def test_the_editor_extension_brings_a_sessions_terminal_to_the_front(self):
        """The real extension code, with a stand-in for the editor, against a real hub: asked
        for a session's terminal, the editor shows that one, with the keyboard in it, and
        types nothing."""
        import pty
        import shutil
        sessions = os.path.join(self.tmp, ".claude", "sessions")
        os.makedirs(sessions)
        ours, theirs = pty.openpty()  # the terminal the session runs in
        shell = subprocess.Popen(["sleep", "30"], stdin=theirs)
        os.close(theirs)
        self.addCleanup(os.close, ours)
        self.addCleanup(shell.wait)
        self.addCleanup(shell.kill)
        with open(os.path.join(sessions, f"{shell.pid}.json"), "w") as f:
            json.dump({"pid": shell.pid, "sessionId": "a", "status": "idle", "statusUpdatedAt": time.time() * 1000}, f)
        self.start_hub()
        self.call("/event", ev("SessionStart", sid="a", cwd="/work/alpha"))
        self.assertIsNone(self.call("/terminal", {"show": ""})["shown"], "no editor yet")
        ext = os.path.join(self.tmp, "ext")
        os.makedirs(os.path.join(ext, "node_modules", "vscode"))
        shutil.copy(os.path.join(ROOT, "vscode", "extension.js"), ext)
        done = os.path.join(self.tmp, "done.json")
        with open(os.path.join(ext, "node_modules", "vscode", "index.js"), "w") as f:
            f.write("""
                const fs = require("fs");
                const done = [];
                const note = (...what) => { done.push(what); fs.writeFileSync(process.env.DONE, JSON.stringify(done)); };
                const terminal = (pid) => ({
                  processId: Promise.resolve(pid),
                  sendText: (text, enter) => note("typed", pid, text, enter),
                  show: (keepKeyboard) => note("shown", pid, keepKeyboard),
                });
                exports.window = {
                  state: { focused: true },
                  terminals: [terminal(1), terminal(Number(process.env.SHELL_PID))],
                  activeTerminal: undefined,
                  onDidChangeActiveTerminal: (f) => ({ dispose() {} }),
                  onDidChangeWindowState: (f) => ({ dispose() {} }),
                  onDidOpenTerminal: (f) => ({ dispose() {} }),
                  onDidCloseTerminal: (f) => ({ dispose() {} }),
                };""")
        editor = subprocess.Popen(["node", "-e", "require('./extension.js').activate({ subscriptions: [] });"], cwd=ext,
                                  env={**self.env, "SHELL_PID": str(shell.pid), "DONE": done})
        self.addCleanup(editor.wait)
        self.addCleanup(editor.kill)
        # Once the hub has found the session's terminal and the editor's request is with it.
        self.assertTrue(wait_for(lambda: self.call("/terminal", {"show": "alpha"})["shown"] == "alpha", 8), "no editor could be asked")
        self.assertTrue(wait_for(lambda: os.path.exists(done), 8), "the terminal was not shown")
        with open(done) as f:
            self.assertEqual(json.load(f)[0], ["shown", shell.pid, False])

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
