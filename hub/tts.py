"""Speech for the hub: a queue that speaks one line at a time, and the engines that make sound."""
from __future__ import annotations

import array
import importlib.util
import math
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

# Lower speaks first. "notice" is feedback to something the user just did; "progress" can wait.
PRIORITY = {"needs_you": 0, "allowed": 0, "denied": 0, "notice": 0, "failed": 1, "done": 2, "progress": 3}
# The hub's own short answers ("Sent.", "Allowed."). They are said in a session's voice but are
# not what the session said, so they neither replace its waiting line nor are replaced by it.
FEEDBACK = {"allowed", "denied", "notice"}


@dataclass
class Utterance:
    text: str
    voice: str
    session: str = ""  # session id; empty for lines not tied to a session
    kind: str = "done"  # needs_you | failed | done
    src: str = ""  # where the line came from, for the log
    entry: dict | None = None  # its record in the hub's history, marked once it was actually spoken
    heard: float | None = None  # seconds from starting to speak it until sound really came out, if measured
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

    STYLE_SHAPE = (510, 1, 256)  # how Kokoro stores one voice

    def __init__(self, kokoro_dir: str, speed: float, fallback_voice: str, custom_dir: str = ""):
        self.dir, self.speed, self.fallback_voice = kokoro_dir, speed, fallback_voice
        self.custom_dir = custom_dir  # the user's own voices, one .npy file each
        self.custom: dict = {}
        self.voices: set[str] = set()
        self.kokoro = None
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()

    def load(self) -> None:
        from kokoro_onnx import Kokoro  # heavy import; done here so the socket is up first

        self.kokoro = Kokoro(f"{self.dir}/kokoro-v1.0.onnx", f"{self.dir}/voices-v1.0.bin")
        self.voices = set(self.kokoro.get_voices())
        self.reload_custom()
        self._pcm("Ready.", self.fallback_voice)  # the first synthesis is much slower than the rest

    def reload_custom(self) -> None:
        import numpy as np

        self.custom = {}
        if not os.path.isdir(self.custom_dir):
            return
        for name in sorted(os.listdir(self.custom_dir)):
            if name.endswith(".npy"):
                try:
                    self.custom[name[:-4]] = self.as_style(np.load(os.path.join(self.custom_dir, name)))
                except (OSError, ValueError):
                    pass

    def as_style(self, array):
        """Check an array is a Kokoro voice and return it in the stored shape."""
        import numpy as np

        array = np.asarray(array, dtype=np.float32)
        if array.shape == (self.STYLE_SHAPE[0], self.STYLE_SHAPE[2]):
            array = array[:, None, :]
        if array.shape != self.STYLE_SHAPE:
            raise ValueError(f"not a Kokoro voice: expected an array of shape {self.STYLE_SHAPE}, got {array.shape}")
        return array

    def has(self, voice: str) -> bool:
        return voice in self.voices or voice in self.custom

    def style(self, voice: str):
        return self.custom[voice] if voice in self.custom else self.kokoro.get_voice_style(voice)

    def save_custom(self, name: str, array) -> None:
        import numpy as np

        array = self.as_style(array)
        os.makedirs(self.custom_dir, exist_ok=True)
        np.save(os.path.join(self.custom_dir, f"{name}.npy"), array)
        self.custom[name] = array

    def remove_custom(self, name: str) -> bool:
        if self.custom.pop(name, None) is None:
            return False
        try:
            os.unlink(os.path.join(self.custom_dir, f"{name}.npy"))
        except OSError:
            pass
        return True

    def arm(self) -> None:
        self._stop.clear()

    def _pcm(self, text: str, voice: str) -> bytes:
        import numpy as np

        samples, _ = self.kokoro.create(text, voice=self.custom.get(voice, voice), speed=self.speed, lang="en-us")
        return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()

    def speak(self, parts: list[str], voice: str) -> float | None:
        """Speak the parts in order, synthesizing each while the previous one plays.

        Returns seconds until the first audio was handed to the player, or None if nothing played.
        """
        if self._stop.is_set():
            return None
        if not self.has(voice):
            voice = self.fallback_voice
        started, first = time.monotonic(), None
        proc = self._proc = subprocess.Popen(
            # A small buffer: by default the player waits for more audio before it starts, which
            # delayed a labelled line by about 0.3 s (measured on the speakers' output).
            ["paplay", "--raw", f"--rate={self.RATE}", "--format=s16le", "--channels=1", "--latency-msec=50"],
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


class CommandEngine:
    """A system voice run as a command per line (macOS `say`, speech-dispatcher, espeak-ng).

    One voice for every session, but the queue, labels and overlay work the same.
    """

    COMMANDS = {
        "say": lambda text: ["say", "-r", "210", text],
        "spd-say": lambda text: ["spd-say", "-w", text],
        "espeak-ng": lambda text: ["espeak-ng", text],
    }

    def __init__(self, command: Callable[[str], list[str]]):
        self.command = command
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()

    def load(self) -> None:
        pass

    def arm(self) -> None:
        self._stop.clear()

    def speak(self, parts: list[str], voice: str) -> float | None:
        if self._stop.is_set():
            return None
        started = time.monotonic()
        try:  # its own process group, so stop() also reaches any helper it starts
            proc = self._proc = subprocess.Popen(self.command(" ".join(parts)), stdin=subprocess.DEVNULL,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                 start_new_session=True)
        except OSError:
            return None
        first = time.monotonic() - started
        proc.wait()
        self._proc = None
        return first

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass


class Meter:
    """Listens to what is really coming out of the speakers while a line is spoken.

    It records the sound card's own output (PulseAudio's "monitor" of the default sink), so the
    loudness it reports is in step with what is heard whatever the player's delay, and works for
    every voice engine. Nothing is kept: each 40 ms becomes one number from 0 to 1.
    """

    RATE = 8000
    STEP = 0.04  # seconds per loudness value

    def __init__(self, device: str = "@DEFAULT_MONITOR@"):
        self.device = device
        self._proc: subprocess.Popen | None = None
        self._started = 0.0
        self._heard: float | None = None
        self._peak = 0.05  # loudest moment lately; levels are relative to it, so a quiet voice still moves

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("parec"))

    def start(self, on_levels: Callable[[list[float], float], None]) -> None:
        self.stop()
        self._started, self._heard = time.monotonic(), None
        try:
            proc = self._proc = subprocess.Popen(
                ["parec", f"--device={self.device}", "--raw", f"--rate={self.RATE}", "--format=s16le", "--channels=1",
                 "--latency-msec=30"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        threading.Thread(target=self._listen, args=(proc, on_levels), name="meter", daemon=True).start()

    def stop(self) -> float | None:
        """Stop listening. Returns how long after start() sound first came out, or None if none did."""
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.kill()
        return self._heard

    def level(self, chunk: bytes) -> float:
        """Loudness of one piece of 16-bit audio, from 0 to 1 relative to the loudest lately."""
        samples = array.array("h", chunk[:len(chunk) // 2 * 2])
        rms = math.sqrt(sum(x * x for x in samples) / max(1, len(samples))) / 32768
        self._peak = max(rms, self._peak * 0.995, 0.02)
        return round(min(1.0, rms / self._peak) ** 0.8, 2) if rms > 0.002 else 0.0

    def _listen(self, proc: subprocess.Popen, on_levels: Callable[[list[float], float], None]) -> None:
        size = int(self.RATE * self.STEP) * 2
        while True:
            chunk = proc.stdout.read(size)
            if len(chunk) < size or self._proc is not proc:
                return
            level = self.level(chunk)
            if level and self._heard is None:
                self._heard = time.monotonic() - self._started
            on_levels([level], self.STEP)


def make_engine(name: str, kokoro_dir: str, speed: float, fallback_voice: str, custom_dir: str = ""):
    """`name` is kokoro, null, one of CommandEngine.COMMANDS, or auto (the best one installed)."""
    kokoro = os.path.isfile(f"{kokoro_dir}/kokoro-v1.0.onnx") and importlib.util.find_spec("kokoro_onnx")
    if name in ("kokoro", "auto") and kokoro and shutil.which("paplay"):
        return KokoroEngine(kokoro_dir, speed, fallback_voice, custom_dir)
    for command, build in CommandEngine.COMMANDS.items():
        if name in (command, "auto", "kokoro") and shutil.which(command):
            return CommandEngine(build)
    return NullEngine()


class SpeechQueue:
    """Speaks one utterance at a time, most urgent first.

    `label_for(utterance)` is asked just before speaking, so the label reflects the sessions
    active at that moment. `on_change(utterance or None)` fires when a line starts and when it
    ends. `on_done(utterance, label, waited, first_audio, outcome)` is for logging.
    With a `meter`, `on_audio(utterance, levels, step)` reports how loud the voice is as it plays.
    All of them are called without the queue's lock held, so they may take the hub's lock.
    """

    def __init__(self, engine, *, max_age: float = 60.0,
                 label_for: Callable[[Utterance], str] = lambda u: "",
                 on_change: Callable[[Utterance | None], None] = lambda u: None,
                 on_done: Callable[..., None] = lambda *a: None,
                 on_audio: Callable[..., None] = lambda *a: None):
        self.engine, self.max_age = engine, max_age
        self.label_for, self.on_change, self.on_done, self.on_audio = label_for, on_change, on_done, on_audio
        self.meter: Meter | None = None  # set by the hub when there is an overlay to draw the voice on
        self.queued: list[Utterance] = []
        self.current: Utterance | None = None
        self._cond = threading.Condition()
        self._closed = False
        self._paused = False
        self._paused_at = 0.0
        self._cut: Utterance | None = None  # the line push-to-talk cut; resume() brings it back
        self._stopped = False  # the line being spoken was stopped by us, so it was not heard in full
        self._thread = threading.Thread(target=self._run, name="speech", daemon=True)
        self._thread.start()

    def put(self, u: Utterance) -> None:
        with self._cond:
            if u.session and u.kind not in FEEDBACK:  # a session's newer line replaces its queued one
                self.queued = [q for q in self.queued if q.session != u.session or q.kind in FEEDBACK]
            self.queued.append(u)
            self._cond.notify_all()

    def drop_session(self, session: str) -> None:
        """Forget everything a session wanted to say, including the line being spoken."""
        with self._cond:
            self.queued = [q for q in self.queued if q.session != session]
            if self._cut and self._cut.session == session:
                self._cut = None
            if self.current and self.current.session == session:
                self._stop()

    def _stop(self) -> None:
        """Stop the sound. Call with the lock held."""
        self._stopped = self.current is not None
        self.engine.stop()

    def pause(self) -> None:
        """Go quiet (the user is talking): cut the current line and hold the rest."""
        with self._cond:
            if not self._paused:
                self._paused, self._paused_at, self._cut = True, time.monotonic(), self.current
            self._stop()

    def resume(self, answering: str = "") -> None:
        """Speak again. The line that was cut is said again from its start, before the others,
        unless it belongs to the session the user was `answering` (they cut it on purpose).
        The quiet time does not count towards a line's age, however long the user spoke."""
        with self._cond:
            if self._paused:
                cut, self._cut = self._cut, None
                if cut and not (answering and cut.session == answering):
                    self.queued.append(cut)
                quiet = time.monotonic() - self._paused_at
                for q in self.queued:
                    q.created += quiet
            self._paused = False
            self._cond.notify_all()

    def skip(self) -> None:
        """Cut the line being spoken; queued lines follow as usual."""
        with self._cond:
            if self.current:
                self._stop()

    def stop_all(self) -> None:
        with self._cond:
            self.queued.clear()
            self._cut = None
            self._stop()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self.queued.clear()
            self._cut = None
            self._stop()
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
                    self.current, self._stopped = u, False
                    self.engine.arm()  # under the lock, so a stop arriving from now on is kept
            if stale:
                self.on_done(u, "", waited, None, "dropped-stale")
                continue
            label = self.label_for(u)
            self.on_change(u)
            parts = ([label + "."] if label else []) + sentences(u.text)
            meter = self.meter
            if meter:
                meter.start(lambda levels, step: self.on_audio(u, levels, step))
            try:
                first = self.engine.speak(parts, u.voice)
            finally:
                if meter:
                    u.heard = meter.stop()
            with self._cond:
                self.current = None
                outcome = "cut" if self._stopped else "spoken"
                self._cond.notify_all()
            self.on_change(None)
            self.on_done(u, label, waited, first, outcome)
