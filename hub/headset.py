"""Talking through a headset: its button starts a recording from its own microphone, two presses
send it. The Windows side is headset/Headset.cs, a program of its own beside the overlay, started
only where `headset_button` is on. A part of the hub (see hub.py)."""
from __future__ import annotations

import base64
import glob
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import traceback
from typing import Callable

import stt
from base import NEVER, log

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "headset", "Headset.cs")
WINRT = ("System.Runtime", "System.Runtime.InteropServices.WindowsRuntime", "System.Threading.Tasks", "System.ObjectModel")
METADATA = ("Foundation", "Media", "ApplicationModel", "Devices", "Storage", "System")
RETRY_AFTER = 30.0  # seconds before a program that ended by itself is started again
OPENING = 8.0  # seconds the microphone may take to open
BACK = 5.5  # seconds the headphones take to switch back from the microphone: what is played before is lost
LOUD = 0.04  # a moment louder than this (0 to 1) is taken for speech
QUIET = 4.0  # seconds of silence after speech that send, where they do (see `_by_silence`)
NOTHING = 10.0  # seconds without any speech after which a recording is dropped: started by mistake
LONGEST = 120.0  # seconds after which a recording nobody ended is dropped


def build(source: str = SOURCE, log: Callable[[str], None] = lambda line: None) -> str | None:
    """Compile Headset.cs and return the program's path (as WSL sees it), or None. Like the
    overlay's `build`; with CALLS left out where this Windows has no call control devices."""
    import overlay
    try:
        windows = (shutil.which("powershell.exe") or "").split("/System32/")[0]
        framework = f"{windows}/Microsoft.NET/Framework64/v4.0.30319"
        compiler = f"{framework}/csc.exe"
        if not os.path.isfile(compiler):
            return None
        with open(source, "rb") as f:
            version = hashlib.sha1(f.read()).hexdigest()[:10]
        appdata = subprocess.run(["cmd.exe", "/c", "echo %LOCALAPPDATA%"], capture_output=True, text=True, cwd=windows,
                                 timeout=20).stdout.strip()
        if not appdata or "%" in appdata:
            return None
        folder = os.path.join(subprocess.run(["wslpath", "-u", appdata], capture_output=True, text=True, check=True).stdout.strip(), "sidetone")
        program = os.path.join(folder, f"sidetone-headset-{version}.exe")
        if os.path.isfile(program):
            return program
        os.makedirs(folder, exist_ok=True)
        for old in glob.glob(os.path.join(folder, "sidetone-headset-*.exe")):
            try:
                os.unlink(old)
            except OSError:  # still running
                pass
        at, meta = overlay._windows_path(framework), overlay._windows_path(f"{windows}/System32/WinMetadata")
        said = ""
        for calls in (["/define:CALLS"], []):
            done = subprocess.run(
                [compiler, "/nologo", "/target:winexe", "/platform:x64", "/optimize+", *calls,
                 f"/out:{overlay._windows_path(folder)}\\{os.path.basename(program)}",
                 "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", *[f"/r:{at}\\{name}.dll" for name in WINRT],
                 *[f"/r:{meta}\\Windows.{name}.winmd" for name in METADATA], overlay._windows_path(source)],
                capture_output=True, text=True, cwd=windows, timeout=120)
            if done.returncode == 0 and os.path.isfile(program):
                log("headset program built" + ("" if calls else ", without calls"))
                return program
            said = said or " ".join((done.stdout + done.stderr).split())[:400]
        log("headset program could not be compiled: " + said)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"headset program could not be compiled: {e}")
    return None


class Program:
    """The Windows program: words go in, messages come out."""

    def __init__(self, on_message: Callable[[dict], None], log: Callable[[str], None] = lambda line: None,
                 command: Callable[[], list] | None = None):
        self.on_message, self.log = on_message, log
        self.command = command or (lambda: [p] if (p := build(log=log)) else [])
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._started = NEVER

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("powershell.exe") and shutil.which("wslpath"))

    def say(self, word: str) -> None:
        with self._lock:
            if not self.proc:
                return
            try:
                self.proc.stdin.write((word + "\n").encode())
                self.proc.stdin.flush()
            except (OSError, ValueError):
                pass  # it ended: `_read` says so

    def start(self) -> None:
        """Start it, if it is not running, without waiting: it may have to be compiled."""
        with self._lock:
            if self.proc or time.monotonic() - self._started < RETRY_AFTER:
                return
            self._started = started = time.monotonic()
        threading.Thread(target=self._run, args=(started,), name="headset", daemon=True).start()

    def _run(self, started: float) -> None:
        command = self.command()
        if not command:
            return
        with self._lock:
            if self._started != started:  # turned off meanwhile
                return
            try:
                proc = self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                    cwd="/mnt/c/Windows" if os.path.isdir("/mnt/c/Windows") else None)
            except OSError as e:
                self.log(f"headset program could not start: {e}")
                return
        self._read(proc)

    def stop(self) -> None:
        with self._lock:
            proc, self.proc, self._started = self.proc, None, NEVER
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()  # it ends with its input
                proc.wait(3)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()

    def _read(self, proc: subprocess.Popen) -> None:
        for raw in proc.stdout:
            try:
                self.on_message(json.loads(raw))
            except ValueError:
                continue
            except Exception:  # noqa: BLE001  one message must not end the reading
                self.log(f"headset message failed: {traceback.format_exc(limit=-3).strip()}")
        with self._lock:
            ours = self.proc is proc
            if ours:
                self.proc = None
        if ours:
            self.log("headset program exited")
            self.on_message({"type": "gone"})


class Microphone:
    """The headset's microphone, in the place of stt.Recorder."""

    def __init__(self, program: Program):
        self.program = program
        self.on_chunk = None
        self.sent = True  # how the recording ends: the tone that says so
        self._chunks: list[bytes] = []
        self._on = False

    def start(self) -> None:
        self._chunks, self._on, self.sent = [], True, True
        self.program.say("open")

    def feed(self, pcm: bytes) -> None:
        if self._on:
            self._chunks.append(pcm)
            if self.on_chunk:
                self.on_chunk(pcm)

    def stop(self, tail: float = 0.0) -> bytes:
        """No tail: the presses, or the silence, come after the last word."""
        if self._on:
            self._on = False
            self.program.say("close" if self.sent else "drop")
        return b"".join(self._chunks)


class Headset:
    """The hub's methods for the headset's button. They use the hub's lock, sessions and push-to-talk."""
    headset: Program | None = None
    headset_mic: Microphone | None = None
    _headset_until = NEVER  # the button is Sidetone's until then
    _headset_held = False
    _headset: dict | None = None  # the recording under way through the headset
    _headset_ending = threading.Lock()

    def headset_setup(self, program: Program | None = None) -> None:
        self.headset = program or Program(self.on_headset, lambda line: log(self.cfg, "hub.log", line))
        self.headset_mic = Microphone(self.headset)
        self.headset_mic.on_chunk = self._mic_heard

    def headset_spoke(self, u) -> None:
        """A line starts, or (None) ends: the button answers it, for `headset_seconds` after its end."""
        if not (self.headset and self.cfg.headset_button):
            return
        if u and u.session and u.kind not in ("allowed", "denied"):
            self._headset_line = True
            self._headset_until = float("inf")
        elif not u and getattr(self, "_headset_line", False):
            self._headset_line = False
            self._headset_until = time.monotonic() + self.cfg.headset_seconds
        self.headset_tick()

    def headset_tick(self) -> None:
        """Once a second: whose the button is, and whether a recording goes on for too long."""
        if not self.headset:
            return
        with self.lock:
            waiting = bool(self._pending and self._pending.confirm)  # a press confirms it
            want = bool(self.cfg.headset_button and (self._headset or waiting or time.monotonic() < self._headset_until))
            changed, self._headset_held = want != self._headset_held, want
            running = self._headset
        if changed:
            self.headset.say("hold" if want else "release")
        if self.cfg.headset_button:
            self.headset.start()  # ready before the first press: finding the headphones takes it some seconds
        elif not running:
            self.headset.stop()
        if not running:
            return
        now = time.monotonic()
        if not running["opened"]:
            if now - running["since"] > OPENING:
                self._headset_drop(running, "The headset's microphone did not open")
        elif not running["spoke"]:
            if now - running["opened"] > NOTHING:
                self._headset_drop(running, "Nothing said, not sent")
        elif now - running["opened"] > LONGEST:
            self._headset_drop(running, "Never ended, not sent")
        elif self._by_silence(running) and now - running["loud"] > QUIET:
            self._headset_end(running, "silence")

    def _by_silence(self, running: dict) -> bool:
        """Whether silence sends this recording. "auto": on headphones whose two presses have not
        been seen to end one yet, and not when it began over music, where taking headphones off
        looks like a press. With no call to end there is no other way."""
        how = self.cfg.headset_send
        if how == "silence" or (how == "presses" and not running["call"]):
            return True
        return how == "auto" and not running["music"] and running["device"] not in self._headset_known()

    def _headset_file(self) -> str:
        return os.path.join(self.cfg.state, "headsets.json")

    def _headset_known(self) -> list:
        """The headphones whose presses have ended a recording."""
        try:
            with open(self._headset_file()) as f:
                known = json.load(f)
            return known if isinstance(known, list) else []
        except (OSError, ValueError):
            return []

    def on_headset(self, msg: dict) -> None:
        kind = msg.get("type")
        running = self._headset
        if kind == "ready" and self._headset_held:
            self.headset.say("hold")
        elif kind == "press":
            self._headset_pressed(bool(msg.get("music")))
        elif kind == "audio" and running:
            pcm = base64.b64decode(msg.get("pcm") or "")
            if stt.loudness(pcm) > LOUD:
                running["loud"], running["spoke"] = time.monotonic(), True
            self.headset_mic.feed(pcm)
        elif kind == "opened" and running:
            running.update(opened=time.monotonic(), loud=time.monotonic(), device=str(msg.get("device") or ""), call=bool(msg.get("call")))
            log(self.cfg, "hub.log", f"headset: {running['device']} opened after {running['opened'] - running['since']:.2f}s"
                + ("" if running["call"] else ", without a call"))
            if running["music"] and not running["call"] and self.cfg.headset_send != "silence":
                # Only silence could end it, and it may be headphones that were taken off.
                self._headset_drop(running, "Pause the music first, not sent")
        elif kind == "end" and running and running["opened"]:
            known = self._headset_known()
            if running["device"] not in known:
                try:
                    with open(self._headset_file(), "w") as f:
                        json.dump(known + [running["device"]], f)
                except OSError:
                    pass
            self._headset_end(running, f"presses ({msg.get('how')})")
        elif kind == "closed" and running and running is self._headset:  # by itself
            self._headset_drop(running, "The headset's microphone stopped" if running["opened"] else "The headset's microphone did not open",
                               str(msg.get("error") or ""))
        elif kind == "gone":
            self._headset_held = False
            if running:
                self._headset_drop(running, "The headset's microphone stopped")
        elif kind in ("error", "note"):
            log(self.cfg, "hub.log", f"headset: {msg.get('message')}")

    def _headset_pressed(self, music: bool) -> None:
        with self.lock:
            confirming = self._pending if self._pending and self._pending.confirm else None
            busy = bool(self._talking or self._headset or self._transcribing)
            mine = not busy and not confirming and time.monotonic() < self._headset_until
            if mine:
                now = time.monotonic()
                self._headset = {"since": now, "opened": 0.0, "loud": now, "spoke": False, "device": "", "call": False, "music": music}
        if confirming:
            self._send(confirming)
        elif mine:
            log(self.cfg, "hub.log", "headset: pressed" + (", over music" if music else ""))
            if not self.talk_start(self.headset_mic):
                self._headset = None

    def _headset_take(self, running: dict) -> bool:
        """Whether this recording is still to be ended, by whoever asks first."""
        with self._headset_ending:
            if self._headset is not running:
                return False
            self._headset = None
            return True

    def _headset_end(self, running: dict, how: str) -> None:
        if self._headset_take(running):
            log(self.cfg, "hub.log", f"headset: ended by {how}")
            self.headset_mic.sent = True
            # A minute more from here: your words may be followed by others.
            self._headset_until = max(self._headset_until, time.monotonic() + self.cfg.headset_seconds)
            self.talk_end()

    def _headset_drop(self, running: dict, words: str, why: str = "") -> None:
        if self._headset_take(running):
            log(self.cfg, "hub.log", f"headset: dropped, {words.lower()}" + (f" ({why})" if why else ""))
            self.headset_mic.sent = False
            self.talk_drop(words)
