"""Speech for the hub: a queue that speaks one line at a time, and the engines that make sound."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

PRIORITY = {"needs_you": 0, "allowed": 0, "denied": 0, "failed": 1, "done": 2}


@dataclass
class Utterance:
    text: str
    voice: str
    session: str = ""  # session id; empty for lines not tied to a session
    kind: str = "done"  # needs_you | failed | done
    src: str = ""  # where the line came from, for the log
    created: float = field(default_factory=time.monotonic)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


class NullEngine:
    """Records what would be spoken. Used by the tests and when no voice is installed."""

    def __init__(self, duration: float = 0.0):
        self.duration = duration
        self.spoken: list[tuple[str, str]] = []  # (text, voice)
        self._stop = threading.Event()

    def load(self) -> None:
        pass

    def arm(self) -> None:
        self._stop.clear()

    def speak(self, parts: list[str], voice: str) -> float | None:
        if self._stop.is_set():
            return None
        self.spoken.append((" ".join(parts), voice))
        self._stop.wait(self.duration)
        return 0.0

    def stop(self) -> None:
        self._stop.set()


class KokoroEngine:
    """Kokoro kept loaded in this process, played through paplay."""

    RATE = 24000
    GAP = b"\0" * int(RATE * 0.15) * 2  # silence between parts (16-bit mono)

    def __init__(self, kokoro_dir: str, speed: float, fallback_voice: str):
        self.dir, self.speed, self.fallback_voice = kokoro_dir, speed, fallback_voice
        self.kokoro = None
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()

    def load(self) -> None:
        from kokoro_onnx import Kokoro  # heavy import; done here so the socket is up first

        self.kokoro = Kokoro(f"{self.dir}/kokoro-v1.0.onnx", f"{self.dir}/voices-v1.0.bin")
        self.voices = set(self.kokoro.get_voices())
        self._pcm("Ready.", self.fallback_voice)  # the first synthesis is much slower than the rest

    def arm(self) -> None:
        self._stop.clear()

    def _pcm(self, text: str, voice: str) -> bytes:
        import numpy as np

        samples, _ = self.kokoro.create(text, voice=voice, speed=self.speed, lang="en-us")
        return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()

    def speak(self, parts: list[str], voice: str) -> float | None:
        """Speak the parts in order, synthesizing each while the previous one plays.

        Returns seconds until the first audio was handed to the player, or None if nothing played.
        """
        if self._stop.is_set():
            return None
        if voice not in self.voices:
            voice = self.fallback_voice
        started, first = time.monotonic(), None
        proc = self._proc = subprocess.Popen(
            ["paplay", "--raw", f"--rate={self.RATE}", "--format=s16le", "--channels=1"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for i, part in enumerate(parts):
                pcm = self._pcm(part, voice)
                if self._stop.is_set():
                    break
                proc.stdin.write(self.GAP + pcm if i else pcm)
                proc.stdin.flush()
                if first is None:
                    first = time.monotonic() - started
            proc.stdin.close()
            proc.wait()
        except OSError:  # the player was killed by stop()
            pass
        finally:
            if proc.poll() is None:
                proc.kill()
            self._proc = None
        return first

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.kill()


def make_engine(name: str, kokoro_dir: str, speed: float, fallback_voice: str):
    if name == "kokoro" and os.path.isfile(f"{kokoro_dir}/kokoro-v1.0.onnx"):
        return KokoroEngine(kokoro_dir, speed, fallback_voice)
    return NullEngine()


class SpeechQueue:
    """Speaks one utterance at a time, most urgent first.

    `label_for(utterance)` is asked just before speaking, so the label reflects the sessions
    active at that moment. `on_change(utterance or None)` fires when a line starts and when it
    ends. `on_done(utterance, label, waited, first_audio, outcome)` is for logging.
    All three are called without the queue's lock held, so they may take the hub's lock.
    """

    def __init__(self, engine, *, max_age: float = 60.0,
                 label_for: Callable[[Utterance], str] = lambda u: "",
                 on_change: Callable[[Utterance | None], None] = lambda u: None,
                 on_done: Callable[..., None] = lambda *a: None):
        self.engine, self.max_age = engine, max_age
        self.label_for, self.on_change, self.on_done = label_for, on_change, on_done
        self.queued: list[Utterance] = []
        self.current: Utterance | None = None
        self._cond = threading.Condition()
        self._closed = False
        self._paused = False
        self._thread = threading.Thread(target=self._run, name="speech", daemon=True)
        self._thread.start()

    def put(self, u: Utterance) -> None:
        with self._cond:
            if u.session:  # a session's newer line replaces its queued one
                self.queued = [q for q in self.queued if q.session != u.session]
            self.queued.append(u)
            self._cond.notify_all()

    def drop_session(self, session: str) -> None:
        """Forget everything a session wanted to say, including the line being spoken."""
        with self._cond:
            self.queued = [q for q in self.queued if q.session != session]
            if self.current and self.current.session == session:
                self.engine.stop()

    def pause(self) -> None:
        """Go quiet (the user is talking): cut the current line and hold the rest."""
        with self._cond:
            self._paused = True
            self.engine.stop()

    def resume(self) -> None:
        with self._cond:
            self._paused = False
            self._cond.notify_all()

    def skip(self) -> None:
        """Cut the line being spoken; queued lines follow as usual."""
        with self._cond:
            if self.current:
                self.engine.stop()

    def stop_all(self) -> None:
        with self._cond:
            self.queued.clear()
            self.engine.stop()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self.queued.clear()
            self.engine.stop()
            self._cond.notify_all()

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Block until nothing is queued or being spoken. For tests and clean shutdown."""
        with self._cond:
            return self._cond.wait_for(lambda: not self.queued and self.current is None, timeout)

    def snapshot(self) -> dict:
        with self._cond:
            return {
                "speaking": self.current.session if self.current else None,
                "queued": [{"session": q.session, "kind": q.kind, "text": q.text} for q in self.queued],
            }

    def _run(self) -> None:
        self.engine.load()
        while True:
            with self._cond:
                self._cond.wait_for(lambda: (self.queued and not self._paused) or self._closed)
                if self._closed:
                    return
                u = min(self.queued, key=lambda q: (PRIORITY.get(q.kind, 2), q.created))
                self.queued.remove(u)
                waited = time.monotonic() - u.created
                stale = waited > self.max_age  # old news by now; saying it late would only confuse
                if stale:
                    self._cond.notify_all()
                else:
                    self.current = u
                    self.engine.arm()  # under the lock, so a stop arriving from now on is kept
            if stale:
                self.on_done(u, "", waited, None, "dropped-stale")
                continue
            label = self.label_for(u)
            self.on_change(u)
            parts = ([label + "."] if label else []) + sentences(u.text)
            first = self.engine.speak(parts, u.voice)
            with self._cond:
                self.current = None
                self._cond.notify_all()
            self.on_change(None)
            self.on_done(u, label, waited, first, "spoken")
