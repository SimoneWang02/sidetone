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
                if key == "voice":
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
        hub.voices = lambda: {"choosable": True, "builtin": ["af_heart", "bm_fable", "zz_other"], "custom": ["mine"],
                              "pool": ["bm_fable", "af_heart"], "projects": {"web": "af_heart", "api": "mine", "closed-long-ago": "af_heart"}}
        voices = next(s for s in settings.describe(hub) if s["name"] == "Voices")["items"]
        self.assertEqual([(i["key"], i["value"]) for i in voices], [("voice_of.api", "mine"), ("voice_of.web", "af_heart")])
        self.assertEqual([o[0] for o in voices[0]["options"]], ["bm_fable", "af_heart", "mine", "zz_other"])  # the pool first
        hub.voices = lambda: {"choosable": False, "builtin": [], "custom": [], "pool": [], "projects": {}}
        self.assertNotIn("Voices", [s["name"] for s in settings.describe(hub)])  # an engine with one voice: nothing to choose


class Chosen(SettingsCase):
    def test_confirming_before_sending_takes_on_off_or_auto(self):
        hub = self.make()
        for value, kept in ((True, True), ("auto", "auto"), ("False", False), (False, False)):
            self.assertIsNone(hub.set_setting("followup_confirm", value), value)
            self.assertIs(type(hub.cfg.followup_confirm), type(kept))
            self.assertEqual(hub.cfg.followup_confirm, kept)
        self.assertIsNotNone(hub.set_setting("followup_confirm", "sometimes"))
        self.assertIsNone(hub.set_setting("followup_delay", 1.3))
        self.assertEqual(hub.cfg.followup_delay, 1.5)

    def test_a_choice_takes_effect_and_is_kept(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("label", "always"))
        self.assertEqual(hub.cfg.label, "always")
        self.assertEqual(self.saved(), {"label": "always"})
        self.assertIsNone(hub.set_setting("speed", 1.33))  # to the nearest step
        self.assertEqual((hub.cfg.speed, self.engine.speed), (1.35, 1.35))
        self.assertIsNone(hub.set_setting("unsend_seconds", 99))  # no further than it goes
        self.assertEqual(hub.cfg.unsend_seconds, 10)
        self.assertEqual(self.saved(), {"label": "always", "speed": 1.35, "unsend_seconds": 10})

    def test_what_is_kept_is_what_a_new_hub_starts_with(self):
        hub = self.make()
        for key, value in (("label", "never"), ("progress", False), ("usage_models", "near"), ("turn_tokens", "all"),
                           ("overlay.usage_layout", "line"), ("overlay.hotkeys.repeat", "Ctrl+Shift+R"), ("terminal.tint", "all")):
            self.assertIsNone(hub.set_setting(key, value), key)
        home = os.path.dirname(os.path.dirname(self.cfg.config_path))
        os.rename(os.path.dirname(self.cfg.config_path), os.path.join(home, "sidetone"))
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
            fresh = Config.load()
        self.assertEqual((fresh.label, fresh.progress, fresh.usage_models, fresh.turn_tokens), ("never", False, "near", "all"))
        self.assertEqual((fresh.overlay["usage_layout"], fresh.overlay["hotkeys"]["repeat"], fresh.terminal["tint"]),
                         ("line", "Ctrl+Shift+R", "all"))
        self.assertEqual(fresh.overlay["hotkeys"]["talk"], "Ctrl+Alt+Space")  # the keys not touched are as they were

    def test_every_setting_at_the_top_of_the_file_is_read_back_at_start(self):
        hub = self.make()
        top = [i for _, section in settings.SECTIONS for i in section if "." not in i["key"] and i["key"] != "voice"]
        for item in top:
            value = (item["options"][-1][0] if item["kind"] == "choice" else not settings.read(hub, item["key"])
                     if item["kind"] == "switch" else item["max"])
            self.assertIsNone(hub.set_setting(item["key"], value), item["key"])
        home = os.path.dirname(os.path.dirname(self.cfg.config_path))
        os.rename(os.path.dirname(self.cfg.config_path), os.path.join(home, "sidetone"))
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
            fresh = Config.load()
        for item in top:
            self.assertEqual(getattr(fresh, item["key"]), getattr(hub.cfg, item["key"]), item["key"])

    def test_what_cannot_be_is_refused_and_changes_nothing(self):
        hub = self.make()
        self.assertIn("one of", hub.set_setting("label", "loudly"))
        self.assertIn("no setting", hub.set_setting("idle_exit", 5))  # a real setting, but not one the window offers
        self.assertIn("number", hub.set_setting("speed", "fast"))
        self.assertIn("key", hub.set_setting("overlay.hotkeys.talk", "Ctrl+Alt"))  # the keys held, and no key
        self.assertIn("key", hub.set_setting("overlay.hotkeys.talk", "A+B"))
        self.assertEqual((hub.cfg.label, hub.cfg.speed, hub.cfg.overlay["hotkeys"]["talk"]), ("auto", 1.1, "Ctrl+Alt+Space"))
        self.assertFalse(os.path.exists(self.cfg.config_path))

    def test_the_overlay_is_told_of_its_own_settings_at_once(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("overlay.layout", "island"))
        self.assertEqual((hub.cfg.overlay["layout"], self.window.reconfigured), ("island", 1))
        self.assertIsNone(hub.set_setting("overlay.row_lines", "2"))  # from the command line it comes as words
        self.assertEqual(hub.cfg.overlay["row_lines"], 2)
        self.assertIsNone(hub.set_setting("overlay.hotkeys.jump", "Ctrl+Alt+T"))
        self.assertIsNone(hub.set_setting("overlay.hotkeys.missed", ""))  # no key
        self.assertEqual(self.window.reconfigured, 4)
        self.assertEqual(self.saved()["overlay"], {"layout": "island", "row_lines": 2, "hotkeys": {"jump": "Ctrl+Alt+T", "missed": ""}})

    def test_the_voice_is_switched_with_its_file(self):
        hub = self.make()
        self.assertTrue(settings.read(hub, "voice"))
        self.assertIsNone(hub.set_setting("voice", False))
        self.assertTrue(os.path.exists(self.cfg.mute_file))
        self.assertFalse(settings.read(hub, "voice"))
        self.assertIsNone(hub.set_setting("voice", "on"))
        self.assertFalse(os.path.exists(self.cfg.mute_file))

    def test_a_terminal_setting_reaches_the_terminals(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("terminal.strength", 0.2))
        self.assertEqual((hub.cfg.terminal["strength"], hub.terminals.settings["strength"]), (0.2, 0.2))
        self.assertEqual(self.saved(), {"terminal": {"strength": 0.2}})

    def test_a_project_gets_the_voice_picked_for_it_and_says_so_in_it(self):
        hub = self.make()
        hub.on_event({"hook_event_name": "SessionStart", "session_id": "a", "cwd": "/w/web"})
        hub.voices = lambda: {"choosable": True, "builtin": ["af_heart", "bm_fable"], "custom": [], "pool": ["af_heart", "bm_fable"],
                              "projects": {"web": "af_heart"}}
        given = []
        hub.set_voice = lambda project, voice: given.append((project, voice))
        self.assertIsNone(hub.set_setting("voice_of.web", "bm_fable"))
        self.assertEqual(given, [("web", "bm_fable")])
        self.assertTrue(hub.speech.wait_idle(5))
        self.assertEqual(self.engine.spoken, [("This is my voice.", "bm_fable")])
        self.assertIn("one of", hub.set_setting("voice_of.web", "nobody"))


class Shown(SettingsCase):
    def test_the_key_leaves_it_to_the_window_whether_to_shut_or_come_forward(self):
        hub = self.make()
        hub.on_overlay({"type": "hotkey", "name": "settings"})
        opened = self.window.of("settings")[-1]
        self.assertTrue(opened["open"] and opened["toggle"])
        self.assertEqual([s["name"] for s in opened["sections"]], ["Voice", "Talking", "Overlay", "Figures", "Terminal", "Keys"])
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
        hub.on_overlay({"type": "setting", "key": "aside", "value": "off"})
        self.assertEqual(hub.cfg.aside, "off")
        shown = {i["key"]: i["value"] for s in self.window.of("settings")[-1]["sections"] for i in s["items"]}
        self.assertEqual(shown["aside"], "off")
        before = len(self.window.of("settings"))
        hub.on_overlay({"type": "setting", "key": "aside", "value": "sometimes"})  # refused: drawn as it is, still off
        self.assertEqual(len(self.window.of("settings")), before + 1)
        self.assertEqual(hub.cfg.aside, "off")

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
