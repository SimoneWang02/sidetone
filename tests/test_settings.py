"""The settings window's side in the hub: what it offers, what a choice does, what is kept.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import base  # noqa: E402
import overlay  # noqa: E402
import settings  # noqa: E402
import terminal  # noqa: E402
from hub import Config, Hub  # noqa: E402
from tts import NullEngine  # noqa: E402


class Window:
    """Stands in for the overlay: keeps what it was sent."""

    def __init__(self):
        self.sent, self.reconfigured = [], 0

    def send(self, msg):
        self.sent.append(msg)

    def reconfigure(self):
        self.reconfigured += 1

    def of(self, kind):
        return [m for m in self.sent if m.get("type") == kind]


class SettingsCase(unittest.TestCase):
    def make(self, **cfg):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.engine = NullEngine(0.0)
        self.engine.speed = 1.1
        self.cfg = Config(run=self.tmp, state=self.tmp, engine="null", usage_shown=False,
                          mute_file=os.path.join(self.tmp, "voice-off"),
                          config_path=os.path.join(self.tmp, "config", "config.json"),
                          sessions_dir=os.path.join(self.tmp, "claude-sessions"), **cfg)
        self.hub = Hub(self.cfg, self.engine)
        self.addCleanup(self.hub.speech.close)
        self.hub.terminals.write = lambda tty, data: True
        self.hub.terminals.sleep = lambda seconds: None
        self.window = self.hub.overlay = Window()
        return self.hub

    def saved(self):
        with open(self.cfg.config_path) as f:
            return json.load(f)


class Offered(SettingsCase):
    def test_every_setting_is_one_the_hub_has(self):
        fields = Config.__dataclass_fields__
        for _, section in settings.SECTIONS:
            for item in section:
                key = item["key"]
                if key == "mute":
                    continue
                if key.startswith("overlay.hotkeys."):
                    self.assertIn(key[16:], overlay.DEFAULTS["hotkeys"], key)
                elif key.startswith("overlay."):
                    self.assertIn(key[8:], overlay.DEFAULTS, key)
                elif key.startswith("terminal."):
                    self.assertIn(key[9:], terminal.DEFAULTS, key)
                else:
                    self.assertIn(key, fields, key)

    def test_what_a_new_install_has_is_among_the_choices(self):
        hub = self.make()
        for section in settings.describe(hub):
            for item in section["items"]:
                if item["kind"] in ("choice", "pick"):
                    self.assertIn(item["value"], [o[0] for o in item["options"]], item["key"])
                elif item["kind"] == "number":
                    self.assertTrue(item["min"] <= item["value"] <= item["max"], item["key"])
                elif item["kind"] == "switch":
                    self.assertIsInstance(item["value"], bool, item["key"])
                else:
                    self.assertIsInstance(item["value"], str, item["key"])

    def test_every_hotkey_can_be_set_in_the_window(self):
        offered = {item["key"][16:] for _, section in settings.SECTIONS for item in section if item["kind"] == "key"}
        self.assertEqual(offered, set(overlay.DEFAULTS["hotkeys"]))

    def test_the_voices_section_lists_each_project_with_the_voices_there_are(self):
        hub = self.make()
        for sid, folder in (("a", "/w/web"), ("b", "/w/api")):
            hub.on_event({"hook_event_name": "SessionStart", "session_id": sid, "cwd": folder})
        hub.voices = lambda: {"choosable": True, "builtin": ["af_heart", "bm_fable", "ef_dora"], "custom": ["mine"],
                              "pool": ["bm_fable", "af_heart"], "projects": {"web": "af_heart", "api": "mine", "closed-long-ago": "af_heart"}}
        voices = next(s for s in settings.describe(hub) if s["name"] == "Voices")["items"]
        self.assertFalse([i for i in voices if i["key"].startswith("voice_of.")])  # no part for each project
        self.assertEqual([i["name"] for i in voices if i["kind"] == "heading"], ["English"])
        english = [(i["voice"], i["value"], i["more"], i["help"]) for i in voices if i["kind"] == "voice"]
        self.assertEqual(english, [("bm_fable", True, False, "British man, Okay"), ("af_heart", True, False, "American woman, Excellent"),
                                   ("mine", False, True, "Your own voice")])  # Spanish is not offered
        hub.voices = lambda: {"choosable": False, "builtin": [], "custom": [], "pool": [], "projects": {}}
        self.assertNotIn("Voices", [s["name"] for s in settings.describe(hub)])  # an engine with one voice: nothing to choose

    def test_each_voice_shows_the_seconds_it_takes_here(self):
        import time
        hub = self.make(whisper_language="en,it")
        hub.voices = lambda: {"choosable": True, "builtin": ["af_heart", "if_sara"], "custom": [], "pool": ["af_heart"],
                              "projects": {}, "piper": ["piper:it_IT-paola-medium"], "zh": []}
        timed = []

        def took(text, voice):
            timed.append((voice, text))
            return 0.3 if voice.startswith("piper:") else 0.52
        hub.speech.engine.time, hub.speech.engine.has = took, lambda v: True
        tags = lambda: {i["voice"]: i.get("tag") for s in settings.describe(hub) if s["name"] == "Voices" for i in s["items"] if i["kind"] == "voice"}
        self.assertEqual(set(tags().values()), {None})  # not timed yet: no number
        for _ in range(100):
            if not getattr(hub, "_timing", False):
                break
            time.sleep(0.02)
        self.assertEqual(tags(), {"af_heart": "0.5 s", "if_sara": "0.5 s", "piper:it_IT-paola-medium": "0.3 s"})
        self.assertEqual(len(timed), 3 * 6)  # a voice of each group (Kokoro English, Kokoro Italian, Paola): once to load, five to time
        self.assertIn(("if_sara", settings.TIMED["it"]), timed)  # the same sentence for a language's voices
        with open(os.path.join(hub.cfg.state, settings.TIMES_FILE)) as f:
            self.assertEqual(json.load(f)["kokoro:it"], 0.52)  # kept, so it is timed once
        hub._voice_times = None
        tags()
        self.assertEqual(len(timed), 18)

    def test_a_language_you_do_not_speak_is_switched_off(self):
        hub = self.make(whisper_language="en,it,zh", whisper_model="small")
        hub.voices = lambda: {"choosable": True, "builtin": ["af_heart", "if_sara"], "custom": [], "pool": ["af_heart"],
                              "projects": {}, "piper": [], "zh": ["zh:zf_049"]}
        heads = lambda: {i["key"]: (i["spoken"], i["last"]) for s in settings.describe(hub) if s["name"] == "Voices" for i in s["items"] if i["kind"] == "heading"}
        listed = lambda: [i.get("group") for s in settings.describe(hub) if s["name"] == "Voices" for i in s["items"] if i["kind"] == "voice"]
        self.assertEqual(heads(), {"heading.en": (True, False), "heading.it": (True, False), "heading.zh": (True, False)})
        self.assertIsNone(hub.set_setting("speak.zh", False))
        self.assertEqual(self.saved()["whisper_language"], "en,it")  # push-to-talk listens for the others only
        self.assertEqual(hub.cfg.whisper_language, "en,it")  # at once
        self.assertEqual(heads()["heading.zh"], (False, False))
        self.assertNotIn("zh", listed())  # no voices to choose for it
        self.assertIsNone(hub.set_setting("speak.it", False))
        self.assertEqual((hub.cfg.whisper_model, hub.cfg.whisper_language), ("small.en", "en"))  # English alone: its own model
        self.assertEqual(heads()["heading.en"], (True, True))  # the last one on
        self.assertEqual(hub.set_setting("speak.en", False), "keep at least one language")
        self.assertIsNone(hub.set_setting("speak.zh", True))
        self.assertEqual(hub.cfg.whisper_language, "en,zh")
        hub.cfg.whisper_language = "en,es"  # a language the window does not list is kept
        self.assertIsNone(hub.set_setting("speak.it", True))
        self.assertEqual(hub.cfg.whisper_language, "en,it,es")

    def test_each_language_has_its_voices_ticked_in_order(self):
        hub = self.make(whisper_language="auto")
        hub.voices = lambda: {"choosable": True, "builtin": ["af_heart", "bm_fable", "if_sara", "im_nicola", "zf_xiaobei"],
                              "custom": [], "pool": ["af_heart"], "projects": {}, "piper": ["piper:it_IT-paola-medium"], "zh": ["zh:zf_001"]}
        voices = next(s for s in settings.describe(hub) if s["name"] == "Voices")["items"]
        self.assertEqual([i["name"] for i in voices if i["kind"] == "heading"], ["English", "Italian", "Chinese"])
        self.assertEqual([i["voice"] for i in voices if i.get("group") == "zh"], ["zh:zf_001"])  # not Kokoro 1.0's zf_xiaobei
        italian = [i["voice"] for i in voices if i.get("group") == "it" and i["value"]]
        self.assertEqual(italian, ["if_sara", "im_nicola", "piper:it_IT-paola-medium"])  # tts.PREFERRED_VOICE until chosen
        self.assertIsNone(hub.set_setting("voices_order.it", ["if_sara", "piper:it_IT-paola-medium", "im_nicola"]))
        self.assertIsNone(hub.set_setting("voice_in.it.im_nicola", False))
        self.assertEqual(hub.cfg.language_voices["it"], ["if_sara", "piper:it_IT-paola-medium"])
        self.assertIsNone(hub.set_setting("voice_in.en.bm_fable", True))
        self.assertEqual(hub.cfg.voice_pool, ["af_heart", "bm_fable"])
        self.assertIsNotNone(hub.set_setting("voices_order.zh", []))  # never none at all
        self.assertIsNotNone(hub.set_setting("voice_in.en.nobody", True))
        self.assertEqual(self.saved(), {"language_voices": {"it": ["if_sara", "piper:it_IT-paola-medium"]}, "voice_pool": ["af_heart", "bm_fable"]})

        hub.voices = lambda: {"choosable": False, "builtin": [], "custom": [], "pool": [], "projects": {}}
        self.assertNotIn("Voices", [s["name"] for s in settings.describe(hub)])  # an engine with one voice: nothing to choose


class Chosen(SettingsCase):
    def test_the_cancel_key_interrupting_claude_is_on_or_off(self):
        hub = self.make(cancel_stops="never")  # a word from before the switch
        read = lambda: {i["key"]: i["value"] for s in settings.describe(hub) for i in s["items"]}["cancel_stops"]
        self.assertIs(read(), False)
        self.assertIsNone(hub.set_setting("cancel_stops", True))
        self.assertIs(read(), True)
        hub.cfg.cancel_stops = "sent"
        self.assertIs(read(), True)

    def test_confirming_before_sending_is_on_or_off(self):
        hub = self.make()
        for value in (True, False):
            self.assertIsNone(hub.set_setting("followup_confirm", value), value)
            self.assertIs(hub.cfg.followup_confirm, value)
        self.assertIsNone(hub.set_setting("talk_tail", 0.33))
        self.assertEqual(hub.cfg.talk_tail, 0.3)  # to the slider's step

    def test_one_volume_for_the_voice_and_the_sounds(self):
        """The author, 2026-11-20: "do one thing for both so it's more consistent"."""
        hub = self.make()
        self.engine.volume = 1.0
        hub.sounds = type("Sounds", (), {"master": 1.0})()
        self.assertIsNone(hub.set_setting("volume", 60))  # 0 to 100, like a game's master volume
        self.assertEqual((self.engine.volume, hub.sounds.master, self.saved()["volume"]), (0.6, 0.6, 60))
        self.assertNotIn("sound_volume", settings.items(hub))

    def test_a_choice_takes_effect_and_is_kept(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("label", "always"))
        self.assertEqual(hub.cfg.label, "always")
        self.assertEqual(self.saved(), {"label": "always"})
        self.assertIsNone(hub.set_setting("speed", 1.33))  # to the nearest step
        self.assertEqual((hub.cfg.speed, self.engine.speed), (1.35, 1.35))
        self.assertIsNone(hub.set_setting("talk_tail", 99))  # no further than it goes
        self.assertEqual(hub.cfg.talk_tail, 1)
        self.assertEqual(self.saved(), {"label": "always", "speed": 1.35, "talk_tail": 1})

    def test_every_setting_has_a_default_it_can_take(self):
        hub = self.make()
        for key, item in settings.items(hub).items():
            if not key.startswith("voice_in."):
                self.assertEqual(settings._fit(item, settings.default(key)), settings.default(key), key)

    def test_a_section_is_reset_to_what_a_new_install_has(self):
        """The author, 2026-11-20: "for each category ... a reset button at the end"."""
        hub = self.make()
        open(self.cfg.mute_file, "a").close()
        for key, value in (("speed", 1.4), ("label", "always"), ("overlay.layout", "island"), ("history_time", True)):
            self.assertIsNone(hub.set_setting(key, value))
        voice = next(s for s in settings.describe(hub) if s["name"] == "Speech")
        self.assertTrue(voice["resettable"] and voice["changed"])
        self.assertIsNone(hub.set_setting("reset", "Speech"))
        self.assertEqual((hub.cfg.speed, self.engine.speed, hub.cfg.label), (Config.speed, Config.speed, Config.label))
        self.assertFalse(os.path.exists(self.cfg.mute_file))  # the voice is on again
        self.assertEqual((hub.cfg.overlay["layout"], hub.cfg.history_time), ("island", True))  # other sections stay
        voice = next(s for s in settings.describe(hub) if s["name"] == "Speech")
        self.assertFalse(voice["changed"])
        self.assertEqual(self.saved()["speed"], Config.speed)  # what the next hub starts with
        self.assertIsNone(hub.set_setting("reset", "overlay"))  # any case, as from the command line
        self.assertEqual(hub.cfg.overlay["layout"], overlay.DEFAULTS["layout"])
        self.assertEqual(self.window.of("settings"), [])  # the window was shut: nothing sent to it
        self.assertIsNotNone(hub.set_setting("reset", "Colors"))

    def test_a_description_names_the_key_it_speaks_of(self):
        hub = self.make()
        mute = settings.items(hub)["mute"]
        described = {i["key"]: i for s in settings.describe(hub) for i in s["items"]}
        self.assertEqual(described["mute"]["help"], "No voice for any session. The mute key (Ctrl+Alt+M) does the same.")
        self.assertIn("the talk key (Ctrl+Alt+Space)", described["followup_confirm"]["help"])
        self.assertEqual(mute["help"], "No voice for any session. The mute key does the same.")  # SECTIONS itself unchanged
        hub.set_setting("overlay.hotkeys.mute", "")
        described = {i["key"]: i for s in settings.describe(hub) for i in s["items"]}
        self.assertEqual(described["mute"]["help"], "No voice for any session. The mute key does the same.")

    def test_the_summary_is_in_your_language_or_one_chosen(self):
        """The author, 2026-11-20: "either dynamic ... or letting the user choose with a select"."""
        hub = self.make(reply_language="english")  # the old name of English
        self.assertEqual(settings.read(hub, "reply_language"), "en")
        item = settings.items(hub)["reply_language"]
        self.assertEqual((item["kind"], item["options"]),
                         ("pick", [["spoken", "Match My Language"], ["en", "English"], ["it", "Italian"], ["zh", "Chinese"]]))
        self.assertIsNone(hub.set_setting("reply_language", "it"))
        self.assertEqual((base.fixed_language(hub.cfg), self.saved()["reply_language"]), ("it", "it"))
        self.assertIsNone(hub.set_setting("reply_language", "spoken"))
        self.assertEqual(base.fixed_language(hub.cfg), "")
        self.assertIsNotNone(hub.set_setting("reply_language", "fr"))  # its voices not heard yet

    def test_setting_names_are_in_title_case(self):
        small = {"a", "an", "the", "of", "in", "to", "by", "for", "on", "or", "and", "at", "as"}
        for _, section in settings.SECTIONS:
            for item in section:
                words = item["name"].strip('"').split()
                for i, word in enumerate(words):
                    if i and i < len(words) - 1 and word in small:
                        continue
                    self.assertTrue(word[0].isupper() or not word[0].isalpha(), item["name"])

    def test_the_voices_have_no_reset(self):
        hub = self.make()
        with unittest.mock.patch.object(settings, "_voices", lambda hub: [{"key": "voice_in.en.af_heart", "kind": "voice", "name": "Heart", "help": "", "voice": "af_heart", "group": "en", "more": False}]):
            voices = next(s for s in settings.describe(hub) if s["name"] == "Voices")
        self.assertFalse(voices["resettable"])

    def test_what_is_kept_is_what_a_new_hub_starts_with(self):
        hub = self.make()
        for key, value in (("label", "always"), ("usage_models", "near"), ("turn_tokens", "all"),
                           ("overlay.usage_layout", "line"), ("overlay.hotkeys.repeat", "Ctrl+Shift+R"), ("terminal.tint", "all")):
            self.assertIsNone(hub.set_setting(key, value), key)
        home = os.path.dirname(os.path.dirname(self.cfg.config_path))
        os.rename(os.path.dirname(self.cfg.config_path), os.path.join(home, "sidetone"))
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
            fresh = Config.load()
        self.assertEqual((fresh.label, fresh.usage_models, fresh.turn_tokens), ("always", "near", "all"))
        self.assertEqual((fresh.overlay["usage_layout"], fresh.overlay["hotkeys"]["repeat"], fresh.terminal["tint"]),
                         ("line", "Ctrl+Shift+R", "all"))
        self.assertEqual(fresh.overlay["hotkeys"]["talk"], "Ctrl+Alt+Space")  # the keys not touched are as they were

    def test_every_setting_at_the_top_of_the_file_is_read_back_at_start(self):
        hub = self.make()
        top = [i for _, section in settings.SECTIONS for i in section if "." not in i["key"] and i["key"] != "mute"]
        for item in top:
            value = (item["options"][-1][0] if item["kind"] in ("choice", "pick") else not settings.read(hub, item["key"])
                     if item["kind"] == "switch" else item["max"])
            self.assertIsNone(hub.set_setting(item["key"], value), item["key"])
        home = os.path.dirname(os.path.dirname(self.cfg.config_path))
        os.rename(os.path.dirname(self.cfg.config_path), os.path.join(home, "sidetone"))
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
            fresh = Config.load()
        for item in top:
            self.assertEqual(getattr(fresh, item["key"]), getattr(hub.cfg, item["key"]), item["key"])

    def test_a_file_that_cannot_be_read_is_not_written_over(self):
        # A slip while editing config.json by hand: the next choice in the window, or the
        # overlay dragged, wrote a file of that one setting, and every other one was lost.
        hub = self.make()
        os.makedirs(os.path.dirname(self.cfg.config_path))
        broken = '{"label": "always", "speed": 1.3,\n "voices": {"api": "am_michael"}\n'  # the closing brace left out
        with open(self.cfg.config_path, "w") as f:
            f.write(broken)
        self.assertIsNone(hub.set_setting("usage_models", "all"))  # taken at once, only not kept
        hub.place_overlay(False, corner="top-left")
        hub.set_terminal(tint="all")
        with open(self.cfg.config_path) as f:
            self.assertEqual(f.read(), broken)
        with open(os.path.join(self.tmp, "hub.log")) as f:
            self.assertIn("cannot be read", f.read())
        os.remove(self.cfg.config_path)  # and with no file at all, one is made
        hub.place_overlay(False, corner="top-left", offset_x=20)
        self.assertEqual(self.saved(), {"overlay": {"corner": "top-left", "offset_x": 20}})

    def test_a_value_of_the_wrong_kind_is_left_for_its_default(self):
        # Edited by hand: a word where a number belongs made every overlay update fail.
        home = tempfile.mkdtemp(prefix="cs-cfg-")
        os.makedirs(os.path.join(home, "sidetone"))
        with open(os.path.join(home, "sidetone", "config.json"), "w") as f:
            json.dump({"usage_warn": "80%", "label": "always", "speed": 1, "followup_confirm": "ask",
                       "overlay": {"opacity": "high", "offset_x": 20.5, "hotkeys": {"talk": 5, "repeat": "F9"}},
                       "terminal": {"strength": 0.2, "pulse": "yes"}}, f)
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home, "CS_STATE": home}):
            cfg = Config.load()
        self.assertEqual((cfg.usage_warn, cfg.label, cfg.speed, cfg.followup_confirm), (80.0, "always", 1, "ask"))
        self.assertEqual((cfg.overlay["opacity"], cfg.overlay["offset_x"]), (overlay.DEFAULTS["opacity"], 20.5))
        self.assertEqual((cfg.overlay["hotkeys"]["talk"], cfg.overlay["hotkeys"]["repeat"]), ("Ctrl+Alt+Space", "F9"))
        self.assertEqual((cfg.terminal["strength"], cfg.terminal["pulse"]), (0.2, terminal.DEFAULTS["pulse"]))
        with open(os.path.join(home, "hub.log")) as f:
            logged = f.read()
        for name in ("usage_warn", "overlay.opacity", "overlay.hotkeys.talk", "terminal.pulse"):
            self.assertIn(name, logged)

    def test_a_file_that_is_not_json_gives_the_defaults(self):
        home = tempfile.mkdtemp(prefix="cs-cfg-")
        os.makedirs(os.path.join(home, "sidetone"))
        with open(os.path.join(home, "sidetone", "config.json"), "w") as f:
            f.write('{"label": "always",')
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home, "CS_STATE": home}):
            cfg = Config.load()
        self.assertEqual(cfg.label, "never")
        with open(os.path.join(home, "hub.log")) as f:
            self.assertIn("cannot be read", f.read())

    def test_what_cannot_be_is_refused_and_changes_nothing(self):
        hub = self.make()
        self.assertIn("one of", hub.set_setting("label", "loudly"))
        self.assertIn("no setting", hub.set_setting("idle_exit", 5))  # a real setting, but not one the window offers
        self.assertIn("number", hub.set_setting("speed", "fast"))
        self.assertIn("key", hub.set_setting("overlay.hotkeys.talk", "Ctrl+Alt"))  # the keys held, and no key
        self.assertIn("key", hub.set_setting("overlay.hotkeys.talk", "A+B"))
        self.assertEqual((hub.cfg.label, hub.cfg.speed, hub.cfg.overlay["hotkeys"]["talk"]), ("never", 1.1, "Ctrl+Alt+Space"))
        self.assertFalse(os.path.exists(self.cfg.config_path))

    def test_the_overlay_is_told_of_its_own_settings_at_once(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("overlay.layout", "island"))
        self.assertEqual((hub.cfg.overlay["layout"], self.window.reconfigured), ("island", 1))
        self.assertIsNone(hub.set_setting("overlay.row_lines", "2"))  # from the command line it comes as words
        self.assertEqual(hub.cfg.overlay["row_lines"], 2)
        self.assertIsNone(hub.set_setting("overlay.hotkeys.jump", "Ctrl+Alt+T"))
        self.assertIsNone(hub.set_setting("overlay.hotkeys.repeat", ""))  # no key
        self.assertEqual(self.window.reconfigured, 4)
        self.assertEqual(self.saved()["overlay"], {"layout": "island", "row_lines": 2, "hotkeys": {"jump": "Ctrl+Alt+T", "repeat": ""}})

    def test_the_voice_is_switched_with_its_file(self):
        hub = self.make()
        self.assertFalse(settings.read(hub, "mute"))
        self.assertIsNone(hub.set_setting("mute", True))
        self.assertTrue(os.path.exists(self.cfg.mute_file))
        self.assertTrue(settings.read(hub, "mute"))
        self.assertIsNone(hub.set_setting("mute", "off"))
        self.assertFalse(os.path.exists(self.cfg.mute_file))

    def test_a_terminal_setting_reaches_the_terminals(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("terminal.strength", 0.2))
        self.assertEqual((hub.cfg.terminal["strength"], hub.terminals.settings["strength"]), (0.2, 0.2))
        self.assertEqual(self.saved(), {"terminal": {"strength": 0.2}})

    def test_the_play_button_lets_a_voice_be_heard_and_changes_nothing(self):
        hub = self.make()
        self.engine.has = lambda voice: True  # an engine with voices to choose from
        before = list(hub.cfg.voice_pool)
        self.assertIsNone(hub.set_setting("play", "bm_fable"))
        self.assertTrue(hub.speech.wait_idle(5))
        self.assertIsNone(hub.set_setting("play", "if_sara"))
        self.assertTrue(hub.speech.wait_idle(5))
        self.assertEqual(self.engine.spoken, [("Hello, this is how I sound.", "bm_fable"), ("Ciao, questa \u00e8 la mia voce.", "if_sara")])
        hub.speech.pause()  # held, so the presses wait: a second one takes the place of the first
        hub.set_setting("play", "bm_fable")
        hub.set_setting("play", "if_sara")
        self.assertEqual([u.voice for u in hub.speech.waiting()], ["if_sara"])
        hub.speech.resume()
        self.assertEqual(hub.cfg.voice_pool, before)
        self.assertFalse(os.path.exists(self.cfg.config_path))


class Shown(SettingsCase):
    def test_the_key_leaves_it_to_the_window_whether_to_shut_or_come_forward(self):
        hub = self.make()
        hub.on_overlay({"type": "hotkey", "name": "settings"})
        opened = self.window.of("settings")[-1]
        self.assertTrue(opened["open"] and opened["toggle"])
        self.assertEqual([s["name"] for s in opened["sections"]], ["Speech", "Talking", "Overlay", "Figures", "Terminal", "Keys"])
        hub.on_overlay({"type": "settings", "open": False})  # it was in front, so the window shut and said so
        self.assertFalse(hub._settings_open)
        hub.on_overlay({"type": "hotkey", "name": "settings"})  # behind another program it would only come forward
        self.assertTrue(self.window.of("settings")[-1]["toggle"])
        self.assertTrue(hub._settings_open)
        self.assertNotIn("toggle", hub.show_settings(True) and self.window.of("settings")[-1])  # the command opens, whatever
        hub.show_settings(False)
        self.assertEqual(self.window.of("settings")[-1], {"type": "settings", "open": False})

    def test_a_choice_made_in_the_window_comes_back_as_it_stands(self):
        hub = self.make()
        hub.show_settings(True)
        hub.on_overlay({"type": "setting", "key": "aside", "value": False})
        self.assertIs(hub.cfg.aside, False)
        shown = {i["key"]: i["value"] for s in self.window.of("settings")[-1]["sections"] for i in s["items"]}
        self.assertIs(shown["aside"], False)
        before = len(self.window.of("settings"))
        hub.on_overlay({"type": "setting", "key": "aside", "value": "sometimes"})  # refused: drawn as it is, still off
        self.assertEqual(len(self.window.of("settings")), before + 1)
        self.assertIs(hub.cfg.aside, False)
        hub.cfg.aside = "always"  # from before the switch
        self.assertIs(settings.read(hub, "aside"), True)

    def test_a_window_closed_by_hand_opens_at_the_next_press(self):
        hub = self.make()
        hub.show_settings(True)
        hub.on_overlay({"type": "settings", "open": False})  # its cross, or Esc
        hub.on_overlay({"type": "hotkey", "name": "settings"})
        self.assertTrue(self.window.of("settings")[-1]["open"])

    def test_a_window_that_was_started_anew_has_no_settings_open(self):
        hub = self.make()
        hub.show_settings(True)
        hub.on_overlay({"type": "ready"})
        hub.on_overlay({"type": "hotkey", "name": "settings"})
        self.assertTrue(self.window.of("settings")[-1]["open"])

    def test_a_setting_changed_while_the_window_is_shut_sends_it_nothing(self):
        hub = self.make()
        hub.set_setting("label", "always")
        self.assertEqual(self.window.of("settings"), [])


class Muted(SettingsCase):
    """The mute key: the voice off for every session and on again, with a sound and a notice."""

    def test_the_key_switches_the_voice_and_says_so(self):
        hub = self.make()
        played = []
        hub.sounds = unittest.mock.Mock(play=played.append)
        hub.speech.stop_all = unittest.mock.Mock()
        hub.on_overlay({"type": "hotkey", "name": "mute"})
        self.assertTrue(os.path.exists(self.cfg.mute_file))
        hub.speech.stop_all.assert_called_once()  # the line being said is cut
        banner = self.window.of("banner")[-1]
        self.assertEqual((banner["icon"], banner["text"], banner["hint"]), ("muted", "Voice is muted", "Ctrl+Alt+M turns it on"))
        hub.on_overlay({"type": "hotkey", "name": "mute"})
        self.assertFalse(os.path.exists(self.cfg.mute_file))
        self.assertEqual((self.window.of("banner")[-1]["text"], played), ("Voice is on", ["voice_off", "voice_on"]))

    def test_the_overlay_is_told_the_voice_is_off(self):
        hub = self.make()
        hub.toggle_mute()
        self.assertTrue(self.window.of("state")[-1]["muted"])
        hub.toggle_mute()
        self.assertFalse(self.window.of("state")[-1]["muted"])

    def test_no_sound_when_feedback_is_off(self):
        hub = self.make(talk_feedback="none")
        played = []
        hub.sounds = unittest.mock.Mock(play=played.append)
        hub.toggle_mute()
        hub.toggle_mute()
        self.assertEqual(played, [])

    def test_the_key_is_in_the_window(self):
        hub = self.make()
        self.assertEqual(settings.read(hub, "overlay.hotkeys.mute"), "Ctrl+Alt+M")


if __name__ == "__main__":
    unittest.main()
