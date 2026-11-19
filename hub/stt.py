"""Push-to-talk: record the microphone while the key is held, then turn the recording into text.

Both parts run locally: `parec` (PulseAudio) for the microphone, faster-whisper for the words.
"""
from __future__ import annotations

import array
import gc
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import threading
import time

RATE = 16000  # what Whisper expects
SIZES = ("tiny", "base", "small", "medium")  # the Whisper sizes that also come English-only (".en")
ANY = ("auto", "any", "all")
# The languages Whisper has (the list in faster-whisper, kept here so a choice can be checked
# without loading it; a test compares the two).
LANGUAGES = frozenset("""
    af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw
    he hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my
    ne nl nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt
    uk ur uz vi yi yo yue zh
""".split())


def loudness(pcm: bytes) -> float:
    """Peak level of a recording, 0 to 1. Near zero means the microphone heard nothing."""
    samples = array.array("h", pcm[: len(pcm) // 2 * 2])
    return max(max(samples, default=0), -min(samples, default=0)) / 32768


class Recorder:
    """Captures 16 kHz mono from the default microphone between start() and stop()."""

    def __init__(self, source: str = ""):
        self.source = source  # PulseAudio source name; empty = the default one
        self.on_chunk = None  # called with each 0.05 s of audio as it arrives (to show the voice)
        self.proc: subprocess.Popen | None = None
        self._chunks: list[bytes] = []
        self._reader: threading.Thread | None = None

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("parec"))

    def start(self) -> None:
        cmd = ["parec", f"--rate={RATE}", "--channels=1", "--format=s16le", "--raw", "--latency-msec=50"]
        if self.source:
            cmd.append(f"--device={self.source}")
        self._chunks = []
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._reader = threading.Thread(target=self._read, args=(self.proc,), daemon=True)
        self._reader.start()

    def _read(self, proc: subprocess.Popen) -> None:
        while True:
            chunk = proc.stdout.read(1600)  # 0.05 s
            if not chunk:
                return
            self._chunks.append(chunk)
            if self.on_chunk and self.proc is proc:
                self.on_chunk(chunk)

    def stop(self, tail: float = 0.0) -> bytes:
        """Stop recording and return what was captured (16-bit little-endian samples).

        `tail` keeps listening that many seconds first: the last word is still on its way
        through the audio system when the key comes up.
        """
        proc, self.proc = self.proc, None
        if not proc:
            return b""
        if tail:
            time.sleep(tail)
        proc.terminate()
        if self._reader:
            self._reader.join(2)
        return b"".join(self._chunks)


class Named:
    """The speech model, asked which of the user's languages a recording is.

    Working out the language used to be a pass of its own through the first half of the model,
    about 0.6 s, before the pass that writes the words down (measured: 1.4 s for a sentence with
    two languages named, 0.7 s with one). faster-whisper can also take the language from the pass
    it makes anyway (`multilingual=True`), but then it takes the likeliest of all hundred. This
    stands in for the model inside it and puts the likeliest of the named languages first, so
    one pass does both. With no languages named it only notes what was heard.
    """

    def __init__(self, model, languages: list):
        self._model, self._languages, self.heard = model, set(languages), ""
        self.sure = 1.0  # how likely the model found that language, 0 to 1

    def __getattr__(self, name):  # everything else is the model's own
        return getattr(self._model, name)

    def detect_language(self, encoder_output):
        results = self._model.detect_language(encoder_output)  # per recording: [("<|en|>", 0.9), ...], likeliest first
        if self._languages:
            results = [sorted(one, key=lambda pair: pair[0][2:-2] not in self._languages) for one in results]
        if results and results[0]:
            self.heard, self.sure = results[0][0][0][2:-2], results[0][0][1]
        return results


class Transcriber:
    """Whisper kept loaded after its first use. `small.en` reads a short sentence in under a second on CPU.

    `language` is for multilingual models such as `small`: one code ("it"), several ("en,it":
    each recording is taken as whichever of them it sounds most like), or "auto" for any language.
    Naming the languages you speak matters for short sentences, which are easily mistaken for
    some other language. English-only models (names ending in ".en") ignore it.
    """

    # Leaning to the last language. A short recording is easily taken for another language:
    # on 2026-11-19 four of the author's short Italian ones in a row came back as English or
    # Chinese ("quanto ho usato?" as "One dosa, what the?"). Measured on short clips said by
    # the voices: the wrong guesses were all unsure (0.65), real English ones 0.97 or more. So
    # when the model is less sure than UNSURE of a language other than the one you last spoke
    # clearly in, the recording is also written in that one, and kept that way unless the
    # first reading is better by more than MARGIN (Whisper's own mean log-probability per token).
    UNSURE = 0.9
    MARGIN = 0.1
    LONG = 4.0  # seconds; a recording this long tells its language well enough by itself

    def __init__(self, model: str = "small.en", language: str | list = "en"):
        self.name = model
        self.languages = ["en"] if model.endswith(".en") else codes(language)  # empty: any language
        self.heard = ""  # the language of the last recording
        self.lean = True  # see UNSURE; `whisper_lean` in the settings
        self.last = ""  # the language last heard for sure (or in a long recording)
        self.leaned = False  # the last recording was taken in `last` instead of the model's guess
        self._model = None
        self._named = None  # Named, when the language is found in the same pass as the words
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def load(self) -> None:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # slow import, and downloads the model once

                model = WhisperModel(self.name, device="cpu", compute_type="int8")
                # Several languages, or any: find the language in the pass that writes the words.
                # Needs a faster-whisper that can do that (1.1 or later); older ones go the long way.
                if len(self.languages) != 1 and "multilingual" in inspect.signature(model.transcribe).parameters:
                    self._named = model.model = Named(model.model, self.languages)
                self._model = model

    def unload(self) -> None:
        """Give the model's memory back; the next use loads it again."""
        with self._lock:
            self._model = self._named = None
        gc.collect()

    def transcribe(self, pcm: bytes) -> str:
        import numpy as np

        self.load()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        named, options = self._named, {}
        language = self.languages[0] if len(self.languages) == 1 else None
        if named:  # the language is decided inside, half a minute at a time; the one given here is only a start
            named.heard, language, options = "", (self.languages or ["en"])[0], {"multilingual": True}
        elif len(self.languages) > 1:  # which of the user's languages is this? (a pass of its own)
            likely = dict(self._model.detect_language(audio)[2])
            language = max(self.languages, key=lambda code: likely.get(code, 0.0))
            sure = likely.get(language, 0.0)
        text, score, info = self._write(audio, language, options)
        self.heard = named.heard if named else getattr(info, "language", language or "")
        if named:
            sure = named.sure
        elif len(self.languages) <= 1:
            sure = 1.0
        long = len(audio) / RATE >= self.LONG
        self.leaned = False
        if (self.lean and text and not long and sure < self.UNSURE and self.last and self.last != self.heard
                and self.last in self.languages):
            other, other_score, _ = self._write(audio, self.last, {})
            if other and score <= other_score + self.MARGIN:
                text, self.heard, self.leaned = other, self.last, True
            else:
                sure = 1.0  # clearly the other language: a change of language
        if sure >= self.UNSURE or long:
            self.last = self.heard
        return text

    def _write(self, audio, language: str | None, options: dict) -> tuple:
        """The words in a recording, Whisper's mean log-probability per token for them, and its info."""
        # The voice filter drops silence first; without it Whisper invents words for an empty recording.
        segments, info = self._model.transcribe(audio, language=language, beam_size=1, vad_filter=True,
                                                condition_on_previous_text=False, **options)
        segments = list(segments)  # the work happens here, as the pieces are read
        sizes = [max(1, len(getattr(s, "tokens", None) or ())) for s in segments]
        score = (sum(getattr(s, "avg_logprob", 0.0) * n for s, n in zip(segments, sizes)) / sum(sizes)
                 if segments else float("-inf"))
        return " ".join(s.text.strip() for s in segments).strip(), score, info


def codes(languages: str | list) -> list:
    """`"en, IT"`, `"en it"` or a list, as lower-case codes. "auto" (any language) gives none."""
    text = languages if isinstance(languages, str) else ",".join(languages)
    found = [c.lower() for c in text.replace(",", " ").split()]
    return [] if any(c in ANY for c in found) else list(dict.fromkeys(found))


def setup(languages: str | list, model: str = "small.en") -> tuple:
    """The `whisper_model` and `whisper_language` for someone who speaks `languages`.

    English alone gets the English-only model of the same size. Anything else gets the
    multilingual one, told which languages to expect; "auto" lets it guess among all of them.
    Measured (tests/stt_speed.py): the two models are equally quick, and several languages
    cost no more than one since the language is found in the same pass (see Named). What
    naming them buys is that a short recording is not taken for a language you never speak.
    Raises ValueError for a code Whisper does not have.
    """
    text = languages if isinstance(languages, str) else ",".join(languages)
    wanted = codes(text)
    if not wanted and not any(c.lower() in ANY for c in text.replace(",", " ").split()):
        raise ValueError("name at least one language, for example: en  or  en,it  (auto = any language)")
    unknown = [c for c in wanted if c not in LANGUAGES]
    if unknown:
        raise ValueError(f"not a language code the speech model knows: {', '.join(unknown)}"
                         "  (examples: en English, it Italian, es Spanish, fr French, de German, zh Chinese)")
    size = model[:-3] if model.endswith(".en") else model
    if wanted == ["en"]:
        return (size + ".en" if size in SIZES else size), "en"
    return size, ",".join(wanted) or "auto"


def save_languages(path: str, languages: str | list) -> tuple:
    """Write the choice into the user's config.json, keeping everything else in it."""
    try:
        with open(path) as f:
            saved = json.load(f)
    except FileNotFoundError:
        saved = {}
    model, language = setup(languages, saved.get("whisper_model") or "small.en")
    saved.update(whisper_model=model, whisper_language=language)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(saved, f, indent=2)
    os.replace(path + ".tmp", path)
    return model, language


def describe(model: str, language: str) -> str:
    spoken = "English" if model.endswith(".en") else "any language" if not codes(language) else ", ".join(codes(language))
    return f"push-to-talk listens for: {spoken}  (model {model})"


if __name__ == "__main__":  # stt.py languages CONFIG [CODES]: show or choose; used by `sidetone languages`
    import sys

    if len(sys.argv) < 3 or sys.argv[1] != "languages":
        sys.exit("usage: stt.py languages CONFIG [CODES]")
    try:
        if len(sys.argv) > 3:
            print(describe(*save_languages(sys.argv[2], " ".join(sys.argv[3:]))))
        else:
            try:
                with open(sys.argv[2]) as f:
                    saved = json.load(f)
            except FileNotFoundError:
                saved = {}
            print(describe(saved.get("whisper_model") or "small.en", saved.get("whisper_language") or "en"))
    except ValueError as e:  # an unknown code, or a config.json that is not JSON (left untouched)
        sys.exit(str(e))
