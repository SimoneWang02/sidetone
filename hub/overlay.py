"""The Windows overlay: a child process the hub tells what to draw (see overlay/Overlay.cs).

The two sides exchange one JSON object per line over the child's stdin and stdout, so there is
no port to protect and the window disappears by itself when the hub exits.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from typing import Callable

import stale

SOURCES = ("Overlay.cs", "overlay.ps1")  # what the window is made from

DEFAULTS = {
    "enabled": True,
    "mode": "dots",  # dots = only the lights; the details come out under the mouse | list = details always out
    # How the sessions are shown: bar (a column of lights at the side, details beside it) |
    # island (a row of lights at the top middle of the screen, details dropping down from it)
    "layout": "bar",
    "island_x": 0.5,  # the island's own place: where its middle is across the screen (0 = left, 1 = right)
    "island_y": 10,  # and how far down from the top, in pixels. Dragging it sets both.
    "monitor": 0,  # 0 = the primary monitor, 1 and up = the others in Windows' order
    "corner": "top-right",  # top-right | top-left | bottom-right | bottom-left
    "offset_x": 12,
    "offset_y": 96,  # below the title bar and tabs of a maximized app
    "opacity": 0.9,  # closed capsules while nothing is happening
    "list_opacity": 1.0,
    "glass": "blur",  # blur = Windows blurs what is behind | acrylic = heavier blur | none = plain dark glass
    "flash_seconds": 4,
    # Held by themselves these keys bring the panel out; with the mouse wheel they move the focus. "" = off
    "focus_wheel": "Ctrl+Alt",
    # Held to take hold of the bar with the mouse: drag it, or turn the wheel on it. Without them
    # the mouse goes straight through the bar to the window underneath. "" = the bar takes the
    # mouse whenever it is on it (a plain click still reaches what is underneath).
    "drag_keys": "Ctrl+Alt",
    # Keeping the held talk key from other programs needs a keyboard hook. "held": in only while
    # the hotkey's Ctrl/Alt are down and during the hold; "always": for a talk key without them; "off".
    "keep_talk_key": "held",
    # While you talk, hide the talk hotkey's Ctrl and Alt from other programs, so that a click
    # is a plain click and not a Ctrl+Alt+click (which a video player, for one, ignores).
    "talk_frees_keys": True,
    # What brings the details out: always = the mouse resting on the bar, or holding Ctrl+Alt |
    # keys = only holding Ctrl+Alt (or the key that keeps them out), so a mouse passing over
    # the bar, in a game for one, changes nothing
    "hover": "always",
    # What the history under the kept-out details shows: session = the lines of the session the
    # mouse is on (before it touched one: the session in focus) | all = every session's lines
    "history": "session",
    # Lines a sentence may take in a session's row of the details: 1 = cut with dots, and the bar
    # never changes size; 2 or 3 = the row grows and the bar stretches to keep lights and rows level.
    "row_lines": 1,
    # Where push-to-talk's sign (dots, paper plane, not sent) goes: light = inside the session's
    # status light | line = at the right of its name in the details
    "talk_sign": "light",
    # How "Release to send" moves while the talk key is held: shimmer = a glint of light runs
    # along the words | pulse = they breathe between two pinks | still = no motion
    "talk_text": "shimmer",
    # The color of those words: "" = a soft white with a white glint, the color of no session |
    # "#RRGGBB" = your own ("#FF8FA6" is the microphone's pink they had at first)
    "talk_text_color": "",
    # The mark on the light of a session that has words of yours waiting: number = how many
    # messages, white on the color below; it covers the light for a moment as they are taken
    # in, then shrinks into the upper right | clock = a small clock whose hand goes round |
    # dot = a plain breathing dot
    "waiting_mark": "number",
    "waiting_hold": 0.9,  # seconds the number covers the whole light before it goes to the corner
    "waiting_many": "face",  # more than nine messages waiting: face = a shocked face | number = "9+"
    # Its color: the red of a notification | "#RRGGBB" = your own ("#FF6E8A" is the microphone's pink)
    "waiting_color": "#FF3B30",
    # allow, deny, cancel and option1-4 are only claimed while there is something for them to act on.
    "hotkeys": {"toggle": "Ctrl+Alt+L", "allow": "Ctrl+Alt+Y", "deny": "Ctrl+Alt+N",
                "talk": "Ctrl+Alt+Space", "cancel": "Ctrl+Alt+Backspace",
                "repeat": "Ctrl+Alt+R", "missed": "Ctrl+Alt+U", "layout": "Ctrl+Alt+K",
                # Move the focus to the session before or after; claimed only while there are two or more.
                # The first pair is for the bar, where the lights run down; the second for the island,
                # where they run across. Only the pair of the layout in use is claimed.
                "focus_prev": "Ctrl+Alt+Up", "focus_next": "Ctrl+Alt+Down",
                "focus_left": "Ctrl+Alt+Left", "focus_right": "Ctrl+Alt+Right",
                "option1": "Ctrl+Alt+1", "option2": "Ctrl+Alt+2", "option3": "Ctrl+Alt+3", "option4": "Ctrl+Alt+4"},
}
LAYOUTS = ["bar", "island"]
RETRY_AFTER = 30.0  # seconds before a crashed overlay is started again
ASSEMBLIES = ["PresentationFramework", "PresentationCore", "WindowsBase", "System.Xaml", "System.Web.Extensions",
              "System.Windows.Forms", "System.Drawing"]


def _windows_path(path: str) -> str:
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, check=True).stdout.strip()


def build(source: str, log: Callable[[str], None] = lambda line: None) -> str | None:
    """Compile Overlay.cs into a Windows program and return its path (as WSL sees it).

    Uses the C# compiler that ships with Windows, so nothing has to be installed. The program is
    kept in %LOCALAPPDATA%\\claude-speaks under a name that changes with the source, so it is
    built once per version. Returns None when that is not possible; the caller then falls back
    to running the same source through PowerShell.
    """
    try:
        powershell = shutil.which("powershell.exe") or ""
        windows = powershell.split("/System32/")[0]  # .../Windows
        compiler = next((c for c in (f"{windows}/Microsoft.NET/Framework64/v4.0.30319/csc.exe",
                                     f"{windows}/Microsoft.NET/Framework/v4.0.30319/csc.exe") if os.path.isfile(c)), None)
        if not compiler:
            return None
        with open(source, "rb") as f:
            version = hashlib.sha1(f.read()).hexdigest()[:10]
        appdata = subprocess.run(["cmd.exe", "/c", "echo %LOCALAPPDATA%"], capture_output=True, text=True, cwd=windows,
                                 timeout=20).stdout.strip()
        if not appdata or "%" in appdata:
            return None
        folder = subprocess.run(["wslpath", "-u", appdata], capture_output=True, text=True, check=True).stdout.strip()
        folder = os.path.join(folder, "claude-speaks")
        program = os.path.join(folder, f"claude-speaks-overlay-{version}.exe")
        if os.path.isfile(program):
            return program
        os.makedirs(folder, exist_ok=True)
        for old in os.listdir(folder):  # earlier versions; one still running cannot be deleted and is skipped
            if old.startswith("claude-speaks-overlay-") and old.endswith(".exe"):
                try:
                    os.unlink(os.path.join(folder, old))
                except OSError:
                    pass
        framework = _windows_path(os.path.dirname(compiler))
        done = subprocess.run(
            [compiler, "/nologo", "/target:winexe", "/optimize+", f"/out:{_windows_path(folder)}\\{os.path.basename(program)}",
             f"/lib:{framework}\\WPF", *[f"/r:{name}.dll" for name in ASSEMBLIES], _windows_path(source)],
            capture_output=True, text=True, cwd=windows, timeout=120)
        if done.returncode != 0 or not os.path.isfile(program):
            log("overlay could not be compiled: " + " ".join((done.stdout + done.stderr).split())[:400])
            return None
        log(f"overlay program built: {appdata}\\claude-speaks\\{os.path.basename(program)}")
        return program
    except (OSError, subprocess.SubprocessError) as e:
        log(f"overlay could not be compiled: {e}")
        return None


def command(script: str, log: Callable[[str], None] = lambda line: None) -> list[str]:
    """How to start the overlay: the compiled program, or else the PowerShell script next to it."""
    if os.environ.get("CLAUDE_SPEAKS_OVERLAY") != "script":
        program = build(os.path.join(os.path.dirname(script), "Overlay.cs"), log)
        if program:
            return [program]
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", _windows_path(script)]


class Overlay:
    def __init__(self, script: str, config: dict, on_message: Callable[[dict], None] = lambda m: None,
                 log: Callable[[str], None] = lambda line: None):
        self.script, self.config, self.on_message, self.log = script, config, on_message, log
        self.proc: subprocess.Popen | None = None
        self.ready = False
        self._lock = threading.Lock()
        self._state: dict | None = None  # last state message, replayed when the window (re)starts
        self._started = 0.0
        self._source: dict = {}  # the overlay's source files as they were when the window was started

    def outdated(self) -> bool:
        """The window on screen was started from an older source than is on disk now."""
        return bool(self.proc and self._source and stale.changed(self._source, os.path.dirname(self.script), SOURCES))

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("powershell.exe") and shutil.which("wslpath"))

    def send(self, msg: dict) -> None:
        """Deliver a message, starting the window if needed. State is kept for a later start."""
        with self._lock:
            if msg.get("type") == "state":
                self._state = msg
            if not self.ready:
                self._start()
                return
            self._write(msg)

    def reconfigure(self) -> None:
        """Send the settings again after one of them changed."""
        with self._lock:
            if self.ready:
                self._write({"type": "config", **{k: v for k, v in self.config.items() if k != "enabled"}})

    def restart(self) -> None:
        self.stop()
        with self._lock:
            self._started = 0.0
            self._start()

    def stop(self) -> None:
        with self._lock:
            proc, self.proc, self.ready = self.proc, None, False
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()  # the window exits when its input ends
                proc.wait(3)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()

    def _start(self) -> None:
        if self.proc or time.monotonic() - self._started < RETRY_AFTER:
            return
        self._started = time.monotonic()
        self._source = stale.prints(os.path.dirname(self.script), SOURCES)
        try:
            self.proc = subprocess.Popen(
                command(self.script, self.log), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd="/mnt/c/Windows" if os.path.isdir("/mnt/c/Windows") else None,
            )
        except (OSError, subprocess.CalledProcessError) as e:
            self.log(f"overlay could not start: {e}")
            return
        threading.Thread(target=self._read, args=(self.proc,), name="overlay", daemon=True).start()

    def _write(self, msg: dict) -> None:
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())  # ASCII-only: no code page trouble
            self.proc.stdin.flush()
        except (OSError, AttributeError, ValueError):
            self.ready = False

    def _read(self, proc: subprocess.Popen) -> None:
        for raw in proc.stdout:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("type")
            if kind == "ready":
                with self._lock:
                    self.ready = True
                    self._write({"type": "config", **{k: v for k, v in self.config.items() if k != "enabled"}})
                    if self._state:
                        self._write(self._state)
                self.log("overlay ready")
            elif kind == "mode":
                self.config["mode"] = msg.get("mode", "dots")  # survives an overlay restart
            elif kind == "error":
                self.log(f"overlay: {msg.get('message')}")
            self.on_message(msg)
        with self._lock:
            if self.proc is proc:
                self.proc, self.ready = None, False
        self.log("overlay exited")
