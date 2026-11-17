"""Choosing the languages push-to-talk listens for: the rule, the command, the install script, the hub."""
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import stt  # noqa: E402
from test_hub import HubCase  # noqa: E402


class TheRule(unittest.TestCase):
    def test_english_alone_gets_the_english_only_model(self):
        self.assertEqual(stt.setup("en"), ("small.en", "en"))
        self.assertEqual(stt.setup("EN", "small"), ("small.en", "en"))  # back from several languages
        self.assertEqual(stt.setup("en", "base"), ("base.en", "en"))  # the size someone chose is kept

    def test_other_languages_get_the_multilingual_model_and_are_named_to_it(self):
        self.assertEqual(stt.setup("en,it"), ("small", "en,it"))
        self.assertEqual(stt.setup("it"), ("small", "it"))
        self.assertEqual(stt.setup(" IT  en, it "), ("small", "it,en"))
        self.assertEqual(stt.setup(["en", "fr"], "medium.en"), ("medium", "en,fr"))

    def test_auto_means_any_language(self):
        self.assertEqual(stt.setup("auto"), ("small", "auto"))
        self.assertEqual(stt.Transcriber(*stt.setup("any")).languages, [])

    def test_a_model_without_an_english_only_version_is_kept(self):
        self.assertEqual(stt.setup("en", "large-v3"), ("large-v3", "en"))

    def test_what_is_not_a_language_is_refused(self):
        for wrong in ("xx,it", "", "italian please", "e1"):
            with self.subTest(wrong), self.assertRaises(ValueError):
                stt.setup(wrong)


    def test_the_list_of_languages_is_the_speech_models_own(self):
        try:
            from faster_whisper.tokenizer import _LANGUAGE_CODES
        except ImportError:
            self.skipTest("faster-whisper is not installed here")
        self.assertEqual(stt.LANGUAGES, set(_LANGUAGE_CODES))


class OnePass(unittest.TestCase):
    """The language is found in the pass that writes the words, among the named languages only."""

    class Inside:  # what faster-whisper keeps as its model
        is_multilingual = True

        def detect_language(self, encoder_output):  # a short clip mistaken for Welsh
            return [[("<|cy|>", 0.5), ("<|it|>", 0.3), ("<|en|>", 0.1)]]

    def test_the_likeliest_of_the_named_languages_comes_first(self):
        named = stt.Named(self.Inside(), ["en", "it"])
        self.assertEqual([token for token, _ in named.detect_language(None)[0]], ["<|it|>", "<|en|>", "<|cy|>"])
        self.assertEqual(named.heard, "it")
        self.assertTrue(named.is_multilingual)  # everything else is the model's own

    def test_with_any_language_the_order_is_left_alone(self):
        named = stt.Named(self.Inside(), [])
        self.assertEqual(named.detect_language(None)[0][0][0], "<|cy|>")
        self.assertEqual(named.heard, "cy")

    def test_a_recording_is_written_down_in_one_go(self):
        asked = {}
        listener = stt.Transcriber("small", "en,it")
        named = listener._named = stt.Named(self.Inside(), listener.languages)

        class Whisper:
            def detect_language(self, audio):
                raise AssertionError("a pass of its own to find the language")

            def transcribe(self, audio, language, **options):
                asked.update(options, language=language)
                first = named.detect_language(None)[0][0][0][2:-2]  # as the library does for each half minute
                return [types.SimpleNamespace(text=" Ciao Claude. ")], types.SimpleNamespace(language=first)

        listener._model = Whisper()
        self.assertEqual(listener.transcribe(bytes(3200)), "Ciao Claude.")
        self.assertEqual((asked["multilingual"], listener.heard), (True, "it"))


class TheCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.config = os.path.join(self.tmp, "cfg", "claude-speaks", "config.json")
        # No hub in this run folder, so the real one is never told anything.
        self.env = {**os.environ, "HOME": self.tmp, "XDG_CONFIG_HOME": os.path.join(self.tmp, "cfg"),
                    "CS_RUN": os.path.join(self.tmp, "run"), "CS_STATE": self.tmp}

    def run_it(self, *args, script="bin/claude-speaks"):
        return subprocess.run([os.path.join(ROOT, script), *args], env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=60)

    def saved(self):
        with open(self.config) as f:
            return json.load(f)

    def test_it_writes_the_choice_and_keeps_the_other_settings(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w") as f:
            json.dump({"speed": 1.2, "overlay": {"corner": "top-left"}}, f)
        done = self.run_it("languages", "en,it")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("en, it", done.stdout)
        self.assertEqual(self.saved(), {"speed": 1.2, "overlay": {"corner": "top-left"},
                                        "whisper_model": "small", "whisper_language": "en,it"})
        self.assertIn("en, it", self.run_it("languages").stdout)  # asked without codes, it only tells

    def test_a_wrong_code_changes_nothing(self):
        self.run_it("languages", "it")
        done = self.run_it("languages", "xx")
        self.assertEqual(done.returncode, 2)
        self.assertIn("xx", done.stderr)
        self.assertEqual(self.saved()["whisper_language"], "it")

    def test_settings_that_are_not_json_are_left_alone(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w") as f:
            f.write("{ not json")
        self.assertEqual(self.run_it("languages", "it").returncode, 2)
        with open(self.config) as f:
            self.assertEqual(f.read(), "{ not json")

    def test_the_install_script_takes_the_languages(self):
        done = self.run_it("--hooks-only", "--languages", "en,it", script="install.sh")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.saved(), {"whisper_model": "small", "whisper_language": "en,it"})
        with open(os.path.join(self.tmp, ".claude", "settings.json")) as f:
            self.assertIn("Stop", json.load(f)["hooks"])  # and went on to install

    def test_the_install_script_does_not_ask_when_nobody_is_there(self):
        done = self.run_it("--hooks-only", script="install.sh")  # no terminal: nothing to answer the question
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(os.path.exists(self.config))

    def test_the_install_script_stops_at_a_wrong_code(self):
        done = self.run_it("--hooks-only", "--languages", "xx", script="install.sh")
        self.assertEqual(done.returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".claude", "settings.json")))


class TheRunningHub(HubCase):
    def test_it_takes_up_a_new_choice_without_a_restart(self):
        path = os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "config.json")
        hub = self.make(config_path=path)
        hub.transcriber = before = stt.Transcriber(hub.cfg.whisper_model, hub.cfg.whisper_language)
        stt.save_languages(path, "en,it")
        self.assertEqual(hub.reload_languages(), {"model": "small", "languages": "en,it", "push_to_talk": True})
        self.assertEqual((hub.transcriber.name, hub.transcriber.languages), ("small", ["en", "it"]))
        self.assertIsNot(hub.transcriber, before)
        same = hub.transcriber
        hub.reload_languages()  # nothing changed: the loaded model is kept
        self.assertIs(hub.transcriber, same)

    def test_without_push_to_talk_it_only_remembers(self):
        path = os.path.join(tempfile.mkdtemp(prefix="cs-test-"), "config.json")
        hub = self.make(config_path=path)
        stt.save_languages(path, "it")
        self.assertFalse(hub.reload_languages()["push_to_talk"])
        self.assertIsNone(hub.transcriber)
        self.assertEqual(hub.cfg.whisper_language, "it")


if __name__ == "__main__":
    unittest.main()
