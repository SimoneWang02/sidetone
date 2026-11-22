"""Choosing the languages push-to-talk listens for: the rule, the command, the install script, the hub."""
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import unittest.mock

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


class LeaningToTheLastLanguage(unittest.TestCase):
    """A short recording the model is unsure of is also written in the language last heard for sure."""

    def listener(self, guess, sure, readings):
        """`readings`: language -> (text, mean log-probability) the fake model writes in it."""
        listener = stt.Transcriber("small", "en,it,zh")
        named = listener._named = stt.Named(None, listener.languages)
        named.detect_language = lambda _: None
        asked = self.asked = []

        class Whisper:
            def transcribe(self, audio, language, **options):
                asked.append(language if not options.get("multilingual") else "guess")
                if options.get("multilingual"):
                    named.heard, named.sure, language = guess, sure, guess
                text, score = readings[language]
                return [types.SimpleNamespace(text=text, avg_logprob=score, tokens=[1, 2, 3])], types.SimpleNamespace(language=language)

        listener._model = Whisper()
        return listener

    SI = {"en": ("See you.", -0.64), "it": ("Sì.", -0.66)}  # measured on Paola saying "Sì."

    def test_unsure_and_close_it_keeps_to_the_last_language(self):
        listener = self.listener("en", 0.66, self.SI)
        listener.last = "it"
        self.assertEqual((listener.transcribe(bytes(32000)), listener.heard, listener.leaned), ("Sì.", "it", True))
        self.assertEqual(self.asked, ["guess", "it"])
        self.assertEqual(listener.last, "it")  # a lean does not change what was last heard for sure

    def test_sure_long_switched_off_or_clearly_better_the_guess_stands(self):
        listener = self.listener("en", 0.97, self.SI)
        listener.last = "it"
        self.assertEqual((listener.transcribe(bytes(32000)), listener.leaned, listener.last), ("See you.", False, "en"))
        listener = self.listener("en", 0.66, self.SI)
        listener.last = "it"
        self.assertEqual(listener.transcribe(bytes(int(stt.RATE * 2 * 4.5))), "See you.")  # 4.5 s: long enough
        listener = self.listener("en", 0.66, self.SI)
        listener.last, listener.lean = "it", False
        self.assertEqual(listener.transcribe(bytes(32000)), "See you.")
        listener = self.listener("it", 0.17, {"it": ("Procedi.", -0.74), "en": ("Pochedy", -1.09)})  # measured
        listener.last = "en"
        self.assertEqual((listener.transcribe(bytes(32000)), listener.heard, listener.last), ("Procedi.", "it", "it"))
        listener = self.listener("en", 0.66, self.SI)  # nothing heard for sure yet
        self.assertEqual(listener.transcribe(bytes(32000)), "See you.")
        self.assertEqual(self.asked, ["guess"])


class TheCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs-test-")
        self.config = os.path.join(self.tmp, "cfg", "sidetone", "config.json")
        # No hub in this run folder, so the real one is never told anything.
        self.env = {**os.environ, "HOME": self.tmp, "XDG_CONFIG_HOME": os.path.join(self.tmp, "cfg"),
                    "CS_RUN": os.path.join(self.tmp, "run"), "CS_STATE": self.tmp}

    def run_it(self, *args, script="bin/sidetone"):
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


class WhereItRuns(unittest.TestCase):
    """Push-to-talk on the graphics card when it can be, else on the processor (`whisper_device`)."""

    def load(self, device, ready="", fails=False):
        made = []

        def model(name, device, compute_type):
            if device == "cuda" and fails:
                raise RuntimeError("CUDA failed with error out of memory")
            made.append((name, device, compute_type))
            return types.SimpleNamespace(model=None, transcribe=lambda *a, **k: ([], None))

        t = stt.Transcriber("small", "en,it", device)
        with unittest.mock.patch("faster_whisper.WhisperModel", model), \
                unittest.mock.patch.object(stt, "gpu_ready", lambda roots=None: ready):
            t.load()
        return t, made

    def test_the_card_takes_the_larger_model(self):
        for device in ("auto", "gpu"):
            t, made = self.load(device)
            self.assertEqual(made, [("large-v3-turbo", "cuda", "float16")])
            self.assertEqual((t.running, t.why_not_gpu), ("large-v3-turbo on the graphics card", ""))

    def test_without_a_card_or_its_libraries_the_processor(self):
        t, made = self.load("auto", ready="no NVIDIA graphics card found")
        self.assertEqual(made, [("small", "cpu", "int8")])
        self.assertEqual((t.running, t.why_not_gpu), ("small on the processor", "no NVIDIA graphics card found"))
        t, made = self.load("cpu")
        self.assertEqual((made, t.why_not_gpu), ([("small", "cpu", "int8")], ""))  # never even asked

    def test_a_card_that_fails_falls_back_to_the_processor(self):
        t, made = self.load("gpu", fails=True)
        self.assertEqual(made, [("small", "cpu", "int8")])
        self.assertIn("out of memory", t.why_not_gpu)

    def test_the_libraries_are_found_in_the_nvidia_packages(self):
        with tempfile.TemporaryDirectory() as root:
            for part, name in (("cublas", "libcublas.so.12"), ("cudnn", "libcudnn.so.9"), ("cuda_nvrtc", "libnvrtc.so.12")):
                os.makedirs(os.path.join(root, part, "lib"))
                open(os.path.join(root, part, "lib", name), "w").close()
            self.assertEqual([os.path.basename(f) for f in stt.gpu_libraries([root])], ["libcublas.so.12", "libcudnn.so.9"])
        self.assertEqual(stt.gpu_libraries(["/nowhere"]), [])



class ChosenInTheWindow(HubCase):
    def test_choosing_it_in_the_window_loads_it_again_there(self):
        import settings
        hub = self.make()
        hub.transcriber = stt.Transcriber("small", "en", "auto")
        hub.transcriber._model = object()
        self.assertIsNone(settings.apply(hub, "whisper_device", "cpu"))
        self.assertEqual((hub.transcriber.device, hub.transcriber._model, hub.cfg.whisper_device), ("cpu", None, "cpu"))
        self.assertIsNotNone(settings.apply(hub, "whisper_device", "tpu"))


class MixedLanguages(unittest.TestCase):
    """A message that goes from one language to another, cut at its pauses (`stt.runs`)."""
    S = stt.RATE

    def test_each_run_of_one_language_on_its_own(self):
        # The author's own mix, 2026-11-22: Italian (0.72 sure), English twice, Chinese twice.
        found = [({"it": 0.72, "en": 0.2}, 0, 72000), ({"en": 0.98}, 86000, 128000), ({"en": 0.96}, 133000, 171000),
                 ({"zh": 0.99}, 181000, 221000), ({"zh": 1.0}, 222000, 248000)]
        self.assertEqual(stt.runs(found, ["en", "it", "zh"]), [("it", 0, 72000), ("en", 86000, 171000), ("zh", 181000, 248000)])

    def test_unsure_or_short_stretches_go_with_their_neighbour(self):
        found = [({"it": 0.99}, 0, 3 * self.S), ({"en": 0.24, "it": 0.2}, 3 * self.S, 6 * self.S)]  # measured: no mix
        self.assertEqual(stt.runs(found, ["en", "it"]), [])
        found = [({"en": 0.98}, 0, self.S // 2), ({"it": 0.99}, self.S, 4 * self.S)]  # "ok" before Italian
        self.assertEqual(stt.runs(found, ["en", "it"]), [])
        found = [({"en": 0.3}, 0, self.S), ({"it": 0.99}, self.S, 4 * self.S), ({"en": 0.97}, 4 * self.S, 7 * self.S)]
        self.assertEqual(stt.runs(found, ["en", "it"]), [("it", 0, 4 * self.S), ("en", 4 * self.S, 7 * self.S)])

    def test_only_the_named_languages(self):
        found = [({"es": 0.6, "it": 0.35}, 0, 3 * self.S), ({"en": 0.99}, 3 * self.S, 6 * self.S)]
        self.assertEqual(stt.runs(found, ["en", "it"]), [])  # Italian taken for Spanish: not sure enough of it
        self.assertEqual(stt.runs(found, []), [("es", 0, 3 * self.S), ("en", 3 * self.S, 6 * self.S)])


class MixedRecording(unittest.TestCase):
    """The transcriber with a stand-in model: only an unsure long recording is looked at again."""

    def transcriber(self, sure, runs):
        t = stt.Transcriber("small", "en,it,zh")
        written = []

        def write(audio, language, options):
            written.append("whole" if options.get("multilingual") else language)
            words = "All of it." if options.get("multilingual") else {"it": "Va bene.", "en": "And then English.", "zh": "中文的话"}[language]
            return (words, -0.3,
                    types.SimpleNamespace(language="en"))

        t._model = types.SimpleNamespace()
        t._named = types.SimpleNamespace(heard="en", sure=sure)
        t._write, t._runs = write, lambda audio: runs
        t.load = lambda: None
        return t, written

    def test_an_unsure_long_one_is_written_part_by_part(self):
        t, written = self.transcriber(0.66, [("it", 0, 72000), ("en", 72000, 171000), ("zh", 171000, 248000)])
        self.assertEqual(t.transcribe(bytes(2 * 248000)), "Va bene. And then English. 中文的话")
        self.assertEqual((t.parts, t.heard), (["it", "en", "zh"], "en"))  # the most speech in English
        self.assertEqual(written, ["whole", "it", "en", "zh"])

    def test_a_sure_one_or_with_it_off_is_left_alone(self):
        t, written = self.transcriber(0.97, [("it", 0, 72000), ("en", 72000, 171000)])
        self.assertEqual((t.transcribe(bytes(2 * 171000)), t.parts), ("All of it.", []))
        t, written = self.transcriber(0.66, [("it", 0, 72000), ("en", 72000, 171000)])
        t.mixed = False
        self.assertEqual((t.transcribe(bytes(2 * 171000)), t.parts), ("All of it.", []))
