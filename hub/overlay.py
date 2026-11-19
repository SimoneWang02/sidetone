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
    "glass": "blur",  # blur = Windows blurs what is behind | acrylic = its heavier blur (the same picture as blur on Windows 11, measured on build 26300) | none = plain dark glass
    "flash_seconds": 4,
    # Held by themselves these keys bring the panel out; with the mouse wheel they move the focus. "" = off
    "focus_wheel": "Ctrl+Alt",
    # Held to take hold of the bar with the mouse: drag it, or turn the wheel on it. "" (the
    # default since 2026-11-19, so that Ctrl+Alt can reorder) = the bar takes the mouse whenever
    # it is on it, with the plain arrow cursor, and a plain click still reaches what is underneath.
    # "Ctrl+Alt" = only then; without them the mouse goes straight through the bar.
    "drag_keys": "",
    # Held while dragging a light along the bar: that session goes to another place in it. "" = off
    "reorder_keys": "Ctrl+Alt",
    # Keeping the held talk key from other programs needs a keyboard hook. "held": in only while
    # the hotkey's Ctrl/Alt are down and during the hold; "always": for a talk key without them; "off".
    "keep_talk_key": "held",
    # While you talk, hide the talk hotkey's Ctrl and Alt from other programs, so that a click
    # is a plain click and not a Ctrl+Alt+click (which a video player, for one, ignores).
    "talk_frees_keys": True,
    # A key another program has already reserved (Windows gives each to one program only): true =
    # the overlay listens for it through a keyboard hook and passes it on, so both programs act on
    # it (the author, 2026-11-19, with the NVIDIA overlay holding Ctrl+Alt+M: "it execute both");
    # false = that key does nothing for us, as before. Not for the talk key, whose hold is ours alone.
    "share_taken_keys": True,
    # While the voice is off, a small struck-out speaker just past the end of the bar.
    "muted_mark": True,
    # What brings the details out: always = the mouse resting on the bar, or holding Ctrl+Alt |
    # keys = only holding Ctrl+Alt (or the key that keeps them out), so a mouse passing over
    # the bar, in a game for one, changes nothing
    "hover": "always",
    # What the history under the kept-out details shows: session = the lines of the session the
    # mouse is on (before it touched one: the session in focus) | all = every session's lines
    "history": "session",
    # Seconds the mouse rests on the kept-out details before the history joins them (0.66 is
    # what it was at first; the details themselves come after 0.1)
    "history_after": 0.1,
    # The plan's usage at the foot of the card: rows = each bar on a line of its own, names in
    # one column | line = the five hours and the week side by side, as at first
    "usage_layout": "rows",
    # Lines a sentence may take in a session's row of the details: 1 = cut with dots, and the bar
    # never changes size; 2 or 3 = the row grows and the bar stretches to keep lights and rows level.
    "row_lines": 1,
    # Where push-to-talk's sign (dots, paper plane, not sent) goes: light = inside the session's
    # status light | line = at the right of its name in the details
    "talk_sign": "light",
    # Who has the bubble when a session starts to speak while the sign for words that went
    # out ("sent", "waiting", "stopped", "in focus") is still up: False = the speaker, at
    # once, and the sign shows on its own light only | True = the sign's words, for as long
    # as it is up, and the sentence only after that (as it was until 2026-11-19).
    "sent_first": False,
    # How "Release to send" moves while the talk key is held: shimmer = a glint of light runs
    # along the words | pulse = they breathe between two pinks | still = no motion
    # The microphone's color, "#RRGGBB": the light, the bars and the wave of the session you
    # are talking to while the talk key is held. The tool's own blue ("#FF6E8A" is the pink
    # it was at first; "#2E9CC9" a lighter step of the blue, easier to see on dark glass).
    "mic_color": "#006896",
    "talk_text": "shimmer",
    # The color of those words: "" = a soft white with a white glint, the color of no session |
    # "#RRGGBB" = your own ("#FF8FA6" is the microphone's pink they had at first)
    "talk_text_color": "",
    # The mark on the light of a session that has words of yours waiting: number = how many
    # messages, white on the color below; it covers the light for a moment as they are taken
    # in, then shrinks into the upper right | clock = a small clock whose hand goes round |
    # dot = a plain breathing dot
    "waiting_mark": "number",
    "waiting_size": 9.2,  # the radius of the number's disc in its corner, 5 to 13 (6.6 is what it was at first)
    "waiting_hold": 0.9,  # seconds the number covers the whole light before it goes to the corner
    "waiting_many": "face",  # more than nine messages waiting: face = a dismayed face | number = "9+"
    # Whether a number first shows itself across the whole light: never = it comes up in its
    # corner | first = the first message to wait does | each
    "waiting_cover": "never",
    # Its color: the red of a notification | "#RRGGBB" = your own ("#FF6E8A" is the microphone's pink)
    "waiting_color": "#FF3B30",
    # The arc around a light that says how full that session's context is (whether it is drawn
    # at all is `context_shown`, beside `overlay` in the settings). From `context_warn` percent
    # on it takes the second color; 0 = never. Colors: "#RRGGBB".
    # How a session's figures are set out under the rows (which figures: `detail_metrics`,
    # beside `overlay` in the settings): tiles = a card with a tile for each, its name small,
    # the figure large, and a thin bar where it is a share of a whole | line = one line of
    # text, "Context 21%   Last reply 64k"
    "details_style": "tiles",
    # The number in front of each choice of a question: false = a plain number (the author:
    # "only number without ... the rectangles with the number inside") | true = drawn as a
    # key cap, like the keys in the line below the choices
    "choice_caps": False,
    "context_warn": 80,
    "context_color": "#FFFFFF",
    "context_warn_color": "#FF8A3D",
    # allow, deny, cancel and option1-4 are only claimed while there is something for them to act on.
    "hotkeys": {"toggle": "Ctrl+Alt+L", "allow": "Ctrl+Alt+Y", "deny": "Ctrl+Alt+N",
                "talk": "Ctrl+Alt+Space", "cancel": "Ctrl+Alt+Backspace",
                "repeat": "Ctrl+Alt+R", "missed": "Ctrl+Alt+U", "layout": "Ctrl+Alt+K",
                # Go to the terminal of the session in focus; claimed only while an editor with the
                # claude-speaks extension holds that terminal. No key unless you give it one
                # ("Ctrl+Alt+T" was its first): the author saw no use for it with terminals side by side.
                "jump": "",
                # Open and close the settings window.
                "settings": "Ctrl+Alt+S",
                # The voice off for every session, or on again (the author, 2026-11-19: "I would
                # rather have ... a mute shortcut"; "M for mute"). The NVIDIA overlay has Ctrl+Alt+M for
                # its microphone by default; where it does, both act on the key (share_taken_keys), which
                # the author chose over another letter: "if there's conflict just do both".
                "mute": "Ctrl+Alt+M",
                # Move the focus to the session before or after; claimed only while there are two or more.
                # The first pair is for the bar, where the lights run down; the second for the island,
                # where they run across. Only the pair of the layout in use is claimed.
                "focus_prev": "Ctrl+Alt+Up", "focus_next": "Ctrl+Alt+Down",
                "focus_left": "Ctrl+Alt+Left", "focus_right": "Ctrl+Alt+Right",
                "option1": "Ctrl+Alt+1", "option2": "Ctrl+Alt+2", "option3": "Ctrl+Alt+3", "option4": "Ctrl+Alt+4"},
}
LAYOUTS = ["bar", "island"]
RETRY_AFTER = 30.0  # seconds before a crashed overlay is started again
NEVER = float("-inf")  # "not started yet"; 0 would be the moment the machine booted, as the clock here counts from then
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
        self._started = NEVER
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
            self._started = NEVER
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
            elif kind in ("error", "note"):
                self.log(f"overlay: {msg.get('message')}")
            self.on_message(msg)
        with self._lock:
            if self.proc is proc:
                self.proc, self.ready = None, False
        self.log("overlay exited")
