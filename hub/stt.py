"""Push-to-talk: record the microphone while the key is held, then turn the recording into text.

Both parts run locally: `parec` (PulseAudio) for the microphone, faster-whisper for the words.
"""
from __future__ import annotations

import array
import gc
import importlib.util
import shutil
import subprocess
import threading
import time

RATE = 16000  # what Whisper expects


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


class Transcriber:
    """Whisper kept loaded after its first use. `small.en` reads a short sentence in under a second on CPU.

    `language` is for multilingual models such as `small`: one code ("it"), several ("en,it":
    each recording is taken as whichever of them it sounds most like), or "auto" for any language.
    Naming the languages you speak matters for short sentences, which are easily mistaken for
    some other language. English-only models (names ending in ".en") ignore it.
    """

    def __init__(self, model: str = "small.en", language: str | list = "en"):
        self.name = model
        codes = [c.strip().lower() for c in (language if isinstance(language, str) else ",".join(language)).split(",")]
        codes = [c for c in codes if c and c != "auto"]
        self.languages = ["en"] if model.endswith(".en") else codes  # empty: any language
        self.heard = ""  # the language of the last recording
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def load(self) -> None:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # slow import, and downloads the model once

                self._model = WhisperModel(self.name, device="cpu", compute_type="int8")

    def unload(self) -> None:
        """Give the model's memory back; the next use loads it again."""
        with self._lock:
            self._model = None
        gc.collect()

    def transcribe(self, pcm: bytes) -> str:
        import numpy as np

        self.load()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        language = self.languages[0] if len(self.languages) == 1 else None
        if len(self.languages) > 1:  # which of the user's languages is this?
            likely = dict(self._model.detect_language(audio)[2])
            language = max(self.languages, key=lambda code: likely.get(code, 0.0))
        # The voice filter drops silence first; without it Whisper invents words for an empty recording.
        segments, info = self._model.transcribe(audio, language=language, beam_size=1, vad_filter=True,
                                                condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        self.heard = getattr(info, "language", language or "")
        return text
