"""Talking through a headset: whose its button is, what starts and ends a recording, what is dropped.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests
"""
import base64
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_hub  # noqa: E402
from test_hub import ev, tag, wait_for  # noqa: E402
import base  # noqa: E402
import headset  # noqa: E402

BOSE = "Headphones (Bose)"
LOUD = base64.b64encode(b"\x00\x40" * 800).decode()
SILENT = base64.b64encode(b"\x00\x00" * 800).decode()


class Program:
    """Stands in for the Windows program: keeps the words it was told."""

    def __init__(self):
        self.said, self.proc, self.started, self.stopped = [], None, 0, 0

    def say(self, word):
        self.said.append(word)

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class HeadsetCase(test_hub.HubCase):
    def make(self, **kw):
        hub = super().make(**{"followup_delay": 0.05, "talk_tail": 0, "label": "never", "headset_button": True, **kw})
        hub.overlay = self.overlay = test_hub.FakeOverlay()
        hub.recorder, hub.transcriber = test_hub.FakeRecorder(), test_hub.FakeTranscriber()
        self.addCleanup(setattr, headset, "BACK", headset.BACK)
        headset.BACK = 0.1
        hub.headset_setup(Program())
        self.said = hub.headset.said
        hub.on_event(ev("SessionStart", sid="a", cwd="/w/a"))
        return hub

    def speak(self, hub):
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("A is done.")))
        self.assertTrue(hub.speech.wait_idle())

    def opened(self, hub, music=False, call=True, device=BOSE):
        hub.on_headset({"type": "press", "button": "Play", "music": music})
        hub.on_headset({"type": "opened", "device": device, "call": call})

    def talks(self):
        return [(m.get("state"), m.get("text", "")) for m in self.overlay.of("talk")]

    def later(self, hub, what, seconds):
        hub._headset[what] -= seconds
        hub.headset_tick()


class WhoseTheButtonIs(HeadsetCase):
    def test_it_is_sidetones_while_a_session_speaks_and_a_while_after(self):
        hub = self.make()
        hub.headset_tick()
        self.assertEqual(self.said, [], "nobody has spoken: it is the music's")
        self.speak(hub)
        self.assertEqual(self.said, ["hold"])
        hub._headset_until = time.monotonic() - 1
        hub.headset_tick()
        self.assertEqual(self.said, ["hold", "release"])
        hub.on_headset({"type": "press", "button": "Play"})  # one that was on its way
        self.assertIsNone(hub._headset)

    def test_off_it_takes_nothing_and_the_program_is_not_started(self):
        hub = self.make(headset_button=False)
        self.speak(hub)
        hub.headset_tick()
        self.assertEqual((self.said, hub.headset.started), ([], 0))

    def test_turned_off_it_gives_the_button_back_and_the_program_ends(self):
        hub = self.make()
        self.speak(hub)
        hub.cfg.headset_button = False
        hub.headset_tick()
        self.assertEqual(self.said[-1], "release")
        self.assertTrue(hub.headset.stopped)

    def test_a_program_that_has_just_started_is_told_again(self):
        hub = self.make()
        self.speak(hub)
        hub.on_headset({"type": "ready"})
        self.assertEqual(self.said, ["hold", "hold"])


class Talking(HeadsetCase):
    def test_a_press_records_and_two_presses_send(self):
        hub = self.make()
        listener = hub.listen("a")
        self.speak(hub)
        self.opened(hub)
        self.assertEqual(self.said, ["hold", "open"])
        self.assertIn(("listening", ""), self.talks())
        self.assertFalse(hub.recorder.recording, "the desk's microphone stays closed")
        for _ in range(3):
            hub.on_headset({"type": "audio", "pcm": LOUD})
        self.assertTrue(self.overlay.of("mic"), "the voice is shown as a wave")
        heard = []
        hub.transcriber.transcribe = lambda pcm: heard.append(len(pcm)) or "also add a test"
        hub.on_headset({"type": "end", "how": "call"})
        hub.on_headset({"type": "closed", "error": ""})
        self.assertTrue(listener.wake.wait(3))
        self.assertEqual(hub.collect(listener), "also add a test")
        self.assertEqual((self.said[-1], heard), ("close", [4800]))
        self.assertIsNone(hub._talking)
        with open(os.path.join(self.tmp, "headsets.json")) as f:
            self.assertEqual(json.load(f), [BOSE])

    def test_a_short_recording_is_not_taken_for_a_tap(self):
        hub = self.make()
        self.assertGreater(base.TAP, 0)
        listener = hub.listen("a")
        self.speak(hub)
        self.opened(hub)
        hub.on_headset({"type": "end", "how": "call"})
        self.assertTrue(listener.wake.wait(3))

    def test_silence_sends_until_the_presses_have_worked_on_these_headphones(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub)
        self.later(hub, "opened", 1)
        hub.on_headset({"type": "audio", "pcm": LOUD})
        self.later(hub, "loud", headset.QUIET - 1)
        self.assertTrue(hub._headset, "a pause to think")
        self.later(hub, "loud", 2)
        self.assertEqual(self.said[-1], "close")
        self.assertTrue(wait_for(lambda: ("sent", "also add a test") in self.talks() or any(t[0] == "ready" for t in self.talks())))
        with open(os.path.join(self.tmp, "headsets.json"), "w") as f:
            json.dump([BOSE], f)
        wait_for(lambda: not hub._transcribing)
        self.opened(hub)
        hub.on_headset({"type": "audio", "pcm": LOUD})
        self.later(hub, "loud", 60)
        self.assertTrue(hub._headset, "only the presses end it now")
        hub.cancel()

    def test_over_music_silence_does_not_send(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub, music=True)
        hub.on_headset({"type": "audio", "pcm": LOUD})
        self.later(hub, "loud", 60)
        self.assertTrue(hub._headset)
        self.later(hub, "opened", headset.LONGEST)
        self.assertIn(("failed", "Never ended, not sent"), self.talks())
        self.assertEqual(self.said[-1], "drop")

    def test_over_music_headphones_that_cannot_end_it_are_not_listened_to(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub, music=True, call=False)
        self.assertIn(("failed", "Pause the music first, not sent"), self.talks())
        self.assertIsNone(hub._talking)

    def test_the_other_ways_to_send(self):
        hub = self.make(headset_send="presses")
        self.speak(hub)
        self.opened(hub)
        hub.on_headset({"type": "audio", "pcm": LOUD})
        self.later(hub, "loud", 60)
        self.assertTrue(hub._headset)
        hub.cancel()
        self.opened(hub, call=False)  # no call, so no presses
        hub.on_headset({"type": "audio", "pcm": LOUD})
        self.later(hub, "loud", 60)
        self.assertIsNone(hub._headset)
        wait_for(lambda: not hub._transcribing)
        hub.cfg.headset_send = "silence"
        self.opened(hub, music=True)
        hub.on_headset({"type": "audio", "pcm": LOUD})
        self.later(hub, "loud", 60)
        self.assertIsNone(hub._headset)

    def test_the_voice_goes_on_once_the_headphones_are_back(self):
        hub = self.make()
        headset.BACK = 0.4
        self.speak(hub)
        self.opened(hub)
        hub.on_display(ev("MessageDisplay", sid="a", cwd="/w/a", delta=tag("Another line.")))
        hub.on_headset({"type": "end", "how": "call"})
        time.sleep(0.2)
        self.assertNotIn("Another line.", [s[0] if isinstance(s, tuple) else s for s in self.engine.spoken])
        self.assertTrue(wait_for(lambda: "Another line." in str(self.engine.spoken)))

    def test_a_press_confirms_words_that_wait_for_it(self):
        hub = self.make(followup_confirm=True)
        listener = hub.listen("a")
        self.speak(hub)
        self.opened(hub)
        hub.on_headset({"type": "end", "how": "call"})
        self.assertTrue(wait_for(lambda: hub._pending and hub._pending.confirm))
        hub._headset_until = time.monotonic() - 1
        hub.headset_tick()
        self.assertEqual(self.said[-1], "close", "the button is still held: no release")
        hub.on_headset({"type": "press", "button": "Play"})
        self.assertTrue(listener.wake.wait(3))


class GoneWrong(HeadsetCase):
    def dropped(self, hub, words):
        self.assertIn(("failed", words), self.talks())
        self.assertIsNone(hub._talking)
        self.assertIsNone(hub._headset)
        self.assertFalse(hub._transcribing)
        self.assertTrue(wait_for(lambda: not hub.speech._paused), "the voice came back")

    def test_a_microphone_that_does_not_open(self):
        hub = self.make()
        self.speak(hub)
        hub.on_headset({"type": "press", "button": "Play"})
        self.later(hub, "since", headset.OPENING + 1)
        self.dropped(hub, "The headset's microphone did not open")
        hub.on_headset({"type": "closed", "error": "late"})  # it says so too: nothing more to do

    def test_one_that_says_why(self):
        hub = self.make()
        self.speak(hub)
        hub.on_headset({"type": "press", "button": "Play"})
        hub.on_headset({"type": "closed", "error": "Windows error 4"})
        self.dropped(hub, "The headset's microphone did not open")

    def test_headphones_out_of_reach_while_talking(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub)
        hub.on_headset({"type": "closed", "error": "no sound came from it"})
        self.dropped(hub, "The headset's microphone stopped")

    def test_the_program_ended(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub)
        hub.on_headset({"type": "gone"})
        self.dropped(hub, "The headset's microphone stopped")
        self.assertFalse(hub._headset_held)

    def test_nothing_said_is_not_sent(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub)
        hub.on_headset({"type": "audio", "pcm": SILENT})
        self.later(hub, "opened", headset.NOTHING + 1)
        self.dropped(hub, "Nothing said, not sent")

    def test_the_cancel_key_drops_it(self):
        hub = self.make()
        self.speak(hub)
        self.opened(hub)
        hub.cancel()
        self.dropped(hub, "Cancelled")
        self.assertEqual(self.said[-1], "drop")

    def test_the_talk_key_still_records_from_the_desk(self):
        hub = self.make()
        self.speak(hub)
        hub.talk_start()
        self.assertTrue(hub.recorder.recording)
        hub.on_headset({"type": "press", "button": "Play"})
        self.assertNotIn("open", self.said, "one recording at a time")
        hub.cancel()
        self.assertFalse(hub.recorder.recording)


class TheProgram(unittest.TestCase):
    def test_words_go_in_and_messages_come_out_until_it_ends(self):
        got = []
        program = headset.Program(got.append, command=lambda: [sys.executable, "-c",
            "import sys\nprint('{\"type\":\"ready\"}', flush=True)\nfor l in sys.stdin:\n print('{\"type\":\"got\",\"word\":\"%s\"}' % l.strip(), flush=True)\n if l.strip() == 'die': break"])
        program.start()
        self.assertTrue(wait_for(lambda: {"type": "ready"} in got))
        program.say("hold")
        self.assertTrue(wait_for(lambda: {"type": "got", "word": "hold"} in got))
        program.say("die")
        self.assertTrue(wait_for(lambda: {"type": "gone"} in got))
        program.start()  # not again at once
        self.assertIsNone(program.proc)
        program.stop()
        program.start()
        self.assertTrue(wait_for(lambda: program.proc))
        proc = program.proc
        program.stop()
        self.assertIsNotNone(proc.poll())
        proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
