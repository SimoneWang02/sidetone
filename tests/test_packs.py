"""Languages as packs: fetching a language's files whole or not at all, only the voices chosen,
the languages that are on, and what is said for a line in one that is off."""
import functools
import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import numpy as np  # noqa: E402

import base  # noqa: E402
import packs  # noqa: E402
from test_hub import HubCase, ev  # noqa: E402


def pt_file(values, folder="49") -> bytes:
    """A voice as hexgrad's .pt files hold it: a zip with the tensor's floats in data/0."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(f"{folder}/data.pkl", b"\x80\x02.")  # never read
        z.writestr(f"{folder}/byteorder", b"little")
        z.writestr(f"{folder}/data/0", np.asarray(values, dtype="<f4").tobytes())
        z.writestr(f"{folder}/version", b"3\n")
    return out.getvalue()


class Server:
    """Files served over HTTP from memory, by path; `cut` paths send half and stop."""

    def __init__(self, files: dict):
        self.files, self.asked = files, []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.asked.append(self.path)
                body = outer.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}"

    def close(self):
        self.http.shutdown()
        self.http.server_close()


def source(server, path, body):
    return (server.url + path, len(body), hashlib.sha256(body).hexdigest())


class Fetching(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cs-packs-")
        self.server = Server({"/model": b"m" * 5000, "/bad": b"x" * 10})
        self.addCleanup(self.server.close)

    def test_a_file_arrives_whole_and_checked(self):
        seen = []
        dest = os.path.join(self.dir, "model.onnx")
        packs.fetch(source(self.server, "/model", b"m" * 5000), dest, lambda d, t: seen.append((d, t)))
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), b"m" * 5000)
        self.assertEqual(seen[-1], (5000, 5000))

    def test_a_wrong_file_is_not_kept(self):
        dest = os.path.join(self.dir, "model.onnx")
        for wrong in ((self.server.url + "/bad", 10, "0" * 64),  # not the file it should be
                      (self.server.url + "/model", 9999, None),  # shorter than it should be
                      (self.server.url + "/missing", 1, None)):
            with self.subTest(wrong), self.assertRaises(packs.Failed):
                packs.fetch(wrong, dest)
            self.assertEqual(os.listdir(self.dir), [])  # neither the file nor a .part

    def test_a_voice_file_is_read_without_pytorch(self):
        values = np.arange(510 * 256, dtype=np.float32).reshape(510, 1, 256)
        self.assertTrue(np.array_equal(packs.voice_from_pt(pt_file(values)), values))
        for wrong in (pt_file(np.zeros(10)), b"not a zip"):
            with self.subTest(len(wrong)), self.assertRaises(packs.Failed):
                packs.voice_from_pt(wrong)


class Chinese(unittest.TestCase):
    """Only the voices chosen are fetched, one file each, into the model's voice file."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cs-packs-")
        self.voices = {name: np.full((510, 1, 256), i, dtype=np.float32)
                       for i, name in enumerate(["zf_049", "zf_006", "zm_056", "zm_057", "zf_001"])}
        files = {f"/repo/voices/{n}.pt": pt_file(v) for n, v in self.voices.items()}
        files.update({"/model": b"onnx" * 100, "/repo/config.json": b"{}"})
        self.server = Server(files)
        self.addCleanup(self.server.close)
        self.installed = []
        for name, value in (("ZH_MODEL", source(self.server, "/model", files["/model"])),
                            ("ZH_CONFIG", source(self.server, "/repo/config.json", b"{}")),
                            ("ZH_REPO", self.server.url + "/repo/"), ("ZH_PACKAGE_BYTES", 1000)):
            patcher = unittest.mock.patch.object(packs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.package = False
        for name, fake in (("has_zh_package", lambda: self.package), ("install_package", self.install)):
            patcher = unittest.mock.patch.object(packs, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def install(self, spec):
        self.installed.append(spec)
        self.package = True

    def test_the_pack_with_four_voices(self):
        self.assertFalse(packs.installed("zh", self.dir))
        wanted = ["zf_049", "zf_006", "zm_056", "zm_057"]
        size = packs.needs("zh", ["zh:" + v for v in wanted], self.dir)
        self.assertEqual(size, 400 + 1000 + 4 * packs.ZH_VOICE_BYTES)
        steps, seen = [], []
        packs.install_zh(wanted, self.dir, progress=lambda d, t: seen.append((d, t)), step=steps.append)
        self.assertEqual(packs.zh_installed(self.dir), sorted(wanted))
        self.assertEqual(self.installed, [packs.ZH_PACKAGE])
        self.assertEqual(steps, ["Chinese model", "Chinese pronunciation", "Chinese voices"])
        self.assertTrue(all(t == size and d <= size for d, t in seen), seen[-3:])
        self.assertNotIn("/repo/voices/zf_001.pt", self.server.asked)  # not chosen, not fetched
        with np.load(os.path.join(self.dir, packs.ZH_FILES[1])) as saved:
            self.assertTrue(np.array_equal(saved["zm_056"], self.voices["zm_056"]))
        self.assertEqual(packs.needs("zh", ["zh:" + v for v in wanted], self.dir), 0)

    def test_a_voice_ticked_later_is_half_a_megabyte(self):
        packs.install_zh(["zf_049"], self.dir)
        self.server.asked.clear()
        self.assertEqual(packs.needs("zh", ["zh:zf_049", "zh:zf_001"], self.dir), packs.ZH_VOICE_BYTES)
        self.assertEqual(packs.add_zh_voices(["zf_049", "zf_001"], self.dir), ["zf_001"])
        self.assertEqual(self.server.asked, ["/repo/voices/zf_001.pt"])
        self.assertEqual(packs.zh_installed(self.dir), ["zf_001", "zf_049"])

    def test_removing_it_frees_the_model(self):
        packs.install_zh(["zf_049"], self.dir)
        self.assertGreater(packs.remove_zh(self.dir), 400)
        self.assertFalse(packs.installed("zh", self.dir))
        self.assertEqual(os.listdir(self.dir), [])

    def test_a_name_that_is_not_a_voice_is_refused_before_anything_is_written(self):
        for wrong in ("../../etc", "zf_049/../x", "nobody"):
            with self.subTest(wrong), self.assertRaises(packs.Failed):
                packs.add_zh_voices([wrong], self.dir)
        self.assertFalse(os.path.exists(os.path.join(self.dir, packs.ZH_FILES[1])))

    def test_turning_chinese_on_fetches_it_first_and_a_failure_turns_nothing_on(self):
        config = os.path.join(self.dir, "config.json")
        with unittest.mock.patch.object(packs, "KOKORO_DIR", self.dir), \
             unittest.mock.patch.object(packs, "installed", lambda lang, d=self.dir: bool(packs.zh_installed(d))), \
             unittest.mock.patch.object(packs, "install_zh", side_effect=packs.Failed("no network")):
            with self.assertRaises(packs.Failed):
                packs.turn_on(config, "en,zh", say=lambda *a: None)
        self.assertFalse(os.path.exists(config))  # not saved
        with self.assertRaises(ValueError):
            packs.turn_on(config, "en,xx", say=lambda *a: None)  # a wrong code: nothing fetched either
        self.assertEqual(self.server.asked, [])
        said = []
        with unittest.mock.patch.object(packs, "KOKORO_DIR", self.dir), \
             unittest.mock.patch.object(packs, "install_zh", functools.partial(packs.install_zh, kokoro_dir=self.dir)), \
             unittest.mock.patch.object(packs, "installed", lambda lang, d=self.dir: bool(packs.zh_installed(d))):
            self.assertEqual(packs.turn_on(config, "en,zh", say=said.append), ("small", "en,zh"))
        self.assertEqual(packs.zh_installed(self.dir), ["zf_006", "zf_049", "zm_056", "zm_057"])
        self.assertTrue(said[0].startswith("Installing Chinese ("), said)
        with open(config) as f:
            self.assertEqual(json.load(f)["whisper_language"], "en,zh")


class LanguagesOn(unittest.TestCase):
    def cfg(self, **kw):
        return base.Config(run="/nonexistent", state="/nonexistent", **kw)

    def test_the_languages_listened_for_are_the_ones_spoken(self):
        self.assertEqual(base.languages_on(self.cfg()), ["en"])  # a new install: English
        self.assertEqual(base.languages_on(self.cfg(whisper_model="small", whisper_language="en, IT")), ["en", "it"])
        self.assertEqual(base.languages_on(self.cfg(whisper_model="small.en", whisper_language="it")), ["en"])
        self.assertEqual(base.languages_on(self.cfg(whisper_model="small", whisper_language="auto")), [])
        self.assertEqual(base.languages_on(self.cfg(reply_language="it")), ["en", "it"])  # chosen in the settings

    def test_the_reminder_names_them(self):
        home = tempfile.mkdtemp(prefix="cs-home-")
        os.makedirs(os.path.join(home, "sidetone"))

        def told(config):
            with open(os.path.join(home, "sidetone", "config.json"), "w") as f:
                json.dump(config, f)
            return subprocess.run(["bash", os.path.join(ROOT, "hooks", "voice-reminder.sh")], capture_output=True, text=True,
                                  env={**os.environ, "HOME": home, "XDG_CONFIG_HOME": home}).stdout

        self.assertIn("plain spoken English whatever language I used", told({}))
        self.assertIn("plain spoken English whatever language I used", told({"whisper_model": "small.en", "whisper_language": "it"}))
        self.assertIn("when its two-letter code is one of en, it, zh, and in English otherwise",
                      told({"whisper_model": "small", "whisper_language": "en,it,zh"}))
        self.assertIn("in the language of my last message;", told({"whisper_model": "small", "whisper_language": "auto"}))
        self.assertIn("plain spoken Italian whatever language I used", told({"reply_language": "it"}))


class NotInstalled(HubCase):
    """A line in a language that is off, or not installed, is not read in another voice."""
    VOICES = {"af_heart", "am_michael", "if_sara", "im_nicola", "zf_xiaoxiao", "zm_yunxi"}

    def make(self, **cfg):
        hub = super().make(**cfg)
        self.engine.voices = set(self.VOICES)
        self.engine.has = lambda v: v in self.engine.voices
        return hub

    def said(self, hub, line):
        hub.on_display(ev("MessageDisplay", delta=line))
        self.spoken()
        return self.engine.spoken[-1]

    def test_chinese_without_its_pack_says_so_in_english(self):
        hub = self.make(whisper_model="small", whisper_language="en,zh")
        text, voice = self.said(hub, '<speak lang="zh">好了。</speak>')
        self.assertEqual(text, "Answered in Chinese, which is not installed.")
        self.assertEqual(voice, self.session()["voice"])  # Kokoro 1.0's espeak Chinese is not used
        self.engine.voices.add("zh:zf_049")  # installed
        self.assertEqual(self.said(hub, '<speak lang="zh">好了。</speak>'), ("好了。", "zh:zf_049"))

    def test_a_language_that_is_off_is_not_spoken(self):
        hub = self.make()  # English only
        self.assertEqual(self.said(hub, '<speak lang="it">Fatto.</speak>')[0], "Answered in Italian, which is not installed.")
        self.engine.voices.add("zh:zf_049")  # installed but off
        self.assertEqual(self.said(hub, '<speak lang="zh">好了。</speak>')[0], "Answered in Chinese, which is not installed.")
        hub.cfg.whisper_model, hub.cfg.whisper_language = "small", "en,it"
        self.assertEqual(self.said(hub, '<speak lang="it">Fatto.</speak>'), ("Fatto.", "if_sara"))
        self.assertEqual(self.said(hub, "<speak>Done.</speak>")[0], "Done.")

    def test_a_language_with_no_voice_at_all(self):
        hub = self.make(whisper_model="small", whisper_language="auto")
        self.assertEqual(self.said(hub, '<speak lang="de">Fertig.</speak>')[0], "Answered in German, which has no voice here.")

    def test_the_stop_event_follows_the_same_rule(self):
        hub = self.make()
        hub.on_event(ev("Stop", last_assistant_message='<speak lang="zh">好了。</speak>\nmore'))
        self.spoken()
        self.assertEqual(self.engine.spoken[-1][0], "Answered in Chinese, which is not installed.")


if __name__ == "__main__":
    unittest.main()


class FromTheWindow(HubCase):
    """Install on Chinese's heading, a voice ticked to be fetched, Remove under the card."""

    class Engine:
        def __init__(self, folder):
            self.dir = self.piper_dir = folder
            self.zh, self.spoken, self.voices, self.custom, self.piper = set(), [], {"af_heart", "am_michael"}, {}, {}
            self.reloaded = 0

        def zh_voices(self):
            return set(self.zh)

        def has(self, v):
            return v in self.voices or (v.startswith("zh:") and v[3:] in self.zh)

        def reload_zh(self):
            self.reloaded += 1

        def load(self):
            pass

        def arm(self):
            pass

        def speak(self, parts, voice):
            self.spoken.append((" ".join(parts), voice))
            return 0.0

        def stop(self):
            pass

    def make(self, **cfg):
        cfg.setdefault("whisper_model", "small")
        cfg.setdefault("whisper_language", "en,it")
        hub = super().make(**cfg)
        hub.cfg.config_path = os.path.join(self.tmp, "config.json")
        self.engine = hub.speech.engine = self.Engine(self.tmp)
        return hub

    def heading(self, hub):
        import settings
        return next(i for i in settings._voices(hub) if i.get("key") == "heading.zh")

    def finish(self, hub):
        import settings
        for _ in range(200):
            if not any(j.get("busy") for j in settings.jobs(hub).values()):
                return
            import time
            time.sleep(0.01)
        self.fail("the install did not finish")

    def test_install_shows_its_size_then_how_far_then_turns_chinese_on(self):
        hub = self.make()
        self.assertEqual(self.heading(hub)["pack"], "missing")
        self.assertTrue(self.heading(hub)["summary"].startswith("Not installed, "))
        self.assertIsNotNone(hub.set_setting("speak.zh", True))  # not before it is installed
        gate = threading.Event()

        def install_zh(voices, folder, progress, step):
            step("Chinese model")
            progress(100, 400)
            gate.wait(5)
            self.engine.zh.update(voices)

        with unittest.mock.patch.object(packs, "install_zh", install_zh):
            self.assertIsNone(hub.set_setting("install.zh", True))
            for _ in range(100):
                if self.heading(hub).get("progress"):
                    break
                import time
                time.sleep(0.01)
            shown = self.heading(hub)
            self.assertEqual((shown["pack"], shown["progress"]), ("installing", 0.25))
            self.assertTrue(shown["summary"].startswith("Chinese model, "), shown["summary"])
            gate.set()
            self.finish(hub)
        self.assertIn("zh", hub.cfg.whisper_language)
        self.assertGreater(self.engine.reloaded, 0)
        self.assertNotIn("install", self.heading(hub))
        self.assertEqual(self.said_in_chinese(hub), "zh:zf_049")

    def said_in_chinese(self, hub):
        hub.on_display(ev("MessageDisplay", delta='<speak lang="zh">好了。</speak>'))
        self.spoken()
        return self.engine.spoken[-1][1]

    def test_a_failed_install_says_why_and_can_be_tried_again(self):
        hub = self.make()
        with unittest.mock.patch.object(packs, "install_zh", side_effect=packs.Failed("could not download it: timed out")):
            hub.set_setting("install.zh", True)
            self.finish(hub)
        shown = self.heading(hub)
        self.assertEqual((shown["pack"], shown["summary"]), ("failed", "could not download it: timed out"))
        self.assertNotIn("zh", hub.cfg.whisper_language)

    def test_a_voice_not_downloaded_is_fetched_when_ticked_then_ticked(self):
        import settings
        hub = self.make(whisper_language="en,zh")
        self.engine.zh = {"zf_049", "zf_006", "zm_056", "zm_057"}
        line = next(i for i in settings._voices(hub) if i.get("voice") == "zh:zm_030")
        self.assertEqual((line["tag"], line["preview"]), ("0.5 MB", False))
        with unittest.mock.patch.object(packs, "add_zh_voices", lambda names, folder, progress: self.engine.zh.update(names)):
            self.assertIsNone(hub.set_setting("voice_in.zh.zh:zm_030", True))
            self.finish(hub)
        self.assertIn("zh:zm_030", settings.in_use(hub, "zh"))
        self.assertNotIn("fetch", next(i for i in settings._voices(hub) if i.get("voice") == "zh:zm_030"))

    def test_remove_turns_it_off_and_frees_its_files(self):
        import settings
        hub = self.make(whisper_language="en,zh")
        self.engine.zh = {"zf_049"}
        for f in packs.ZH_FILES:
            with open(os.path.join(self.tmp, f), "wb") as out:
                out.write(b"x" * 1000)
        remove = next(i for i in settings._voices(hub) if i.get("kind") == "pack")
        self.assertEqual(remove["key"], "remove.zh")
        self.assertIn("Frees", remove["help"])
        self.engine.zh = set()  # what the engine reads once the files are gone
        self.assertIsNone(hub.set_setting("remove.zh", True))
        self.assertNotIn("zh", hub.cfg.whisper_language)
        self.assertFalse(any(os.path.exists(os.path.join(self.tmp, f)) for f in packs.ZH_FILES))
        self.assertEqual(self.heading(hub)["pack"], "missing")
