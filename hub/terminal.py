"""Marks each session's own terminal, so the terminals can be told apart like the lights.

The hub cannot see or change the tabs of a terminal program, but it can write to the terminal
a session runs in (the device its Claude Code process reads the keyboard from). Common
terminals, VS Code's among them, understand a few requests written there:

- "use this background color" (OSC 11), undone by "use your own again" (OSC 111);
- "this is your title" (OSC 2).

So the terminal of the session in focus takes a faint tint of that session's color, the same
color its name has in the overlay, and lights up brighter for a moment when the focus is moved
to it by hand. Each request is a few bytes handed over in one write, which the kernel does not
mix into what Claude Code itself is writing.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import NamedTuple

DEFAULTS = {
    "tint": "focus",  # whose terminal wears its session's color: focus | all (the focus stronger) | off
    "strength": 0.09,  # how much of the color goes into the background, 0 to 1
    "background": "#181818",  # the terminal's own background, which the color is mixed into
    # The same in an editor with a light theme (the VS Code extension says which; 2026-11-22).
    # VS Code's Light Modern panel and terminal; the dark one above is its Dark Modern.
    "light_background": "#F8F8F8",
    "pulse": True,  # moving the focus by hand lights its terminal up brighter for a moment
    "pulse_strength": 0.15,  # how much of the color at the top of that moment, 0 to 1
    "title": False,  # also write the session's name and title into the terminal's title
    # Not about marking: when the editor says which terminal you went to (the VS Code extension in
    # vscode/ does), the session running there gets the focus.
    "follow": True,
    # The other way: moving the focus by hand (arrows, wheel) has the editor bring that session's
    # terminal to the front, with the keyboard in it, for terminals kept as tabs, one in sight at a
    # time. Off by default: terminals side by side are all in sight already.
    "jump": False,
    # And with a project in each of several windows of the editor, that session's window comes up
    # too, with its terminal, as soon as the focus rests; only from another window of the editor,
    # never over another program. Off by default: it covers the window you were in.
    "window": False,
    # Where the new-session key has the editor put the terminal: beside = split next to the one of
    # the session in focus | tab = a terminal of its own, a new tab where the editor puts new
    # terminals, one in sight at a time.
    "new_session": "beside",
}
TINTS = ("focus", "all", "off")
PLACES = ("beside", "tab")  # what `new_session` can be
PULSE_SECONDS = 0.7
PULSE_STEPS = 14
RESET = b"\x1b]111\x1b\\"
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class Mark(NamedTuple):
    """What one session's terminal should show."""
    color: str  # the session's color, "#RRGGBB"
    focused: bool
    title: str = ""


def tty_of(pid: int) -> str:
    """The terminal a process runs in ("/dev/pts/4"), or "" when it has none or it cannot be told."""
    if os.path.isdir("/proc"):
        for fd in (0, 1, 2):
            try:
                path = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if path.startswith(("/dev/pts/", "/dev/tty")) and path != "/dev/tty":
                return path
        return ""
    try:  # no /proc (macOS): ask ps, which answers "ttys003" or "??"
        name = subprocess.run(["ps", "-o", "tty=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return f"/dev/{name}" if name and "?" not in name and os.path.exists(f"/dev/{name}") else ""


def mix(background: str, color: str, amount: float) -> str:
    """`amount` (0 to 1) of `color` mixed into `background`, both "#RRGGBB", written the way
    terminals expect a color: "rgb:RR/GG/BB"."""
    amount = max(0.0, min(1.0, amount))
    try:
        base, tint = (tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for c in (background, color))
    except (ValueError, AttributeError):
        return ""
    return "rgb:" + "/".join(f"{round(b + (t - b) * amount):02x}" for b, t in zip(base, tint))


def write(tty: str, data: bytes) -> bool:
    """Hand `data` to a terminal in one piece. Never waits: a terminal that is not being read is skipped."""
    try:
        fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        return os.write(fd, data) == len(data)
    except OSError:
        return False
    finally:
        os.close(fd)


def _background(spec: str) -> bytes:
    return f"\x1b]11;{spec}\x1b\\".encode() if spec else RESET


def _title(text: str) -> bytes:
    # A title can hold words from a prompt: nothing in it may end the request or start another.
    return b"\x1b]2;" + CONTROL.sub(" ", text)[:120].encode() + b"\x1b\\"


class Terminals:
    """Keeps every session's terminal showing what it should, writing only when that changes."""

    def __init__(self, settings: dict | None = None, write=write, sleep=time.sleep):
        self.settings = {**DEFAULTS, **(settings or {})}
        self.write, self.sleep = write, sleep
        self._lock = threading.Lock()
        self._shown: dict[str, tuple[str, str]] = {}  # terminal -> (background as written, title as written)
        self._pulses: dict[str, int] = {}  # terminal -> number of its latest pulse; an older one stops
        self._closed = False
        self.light: set[str] = set()  # terminals in an editor with a light theme

    def background(self, tty: str) -> str:
        """The background a terminal's color is mixed into: its editor's light or dark one."""
        return self.settings["light_background" if tty in self.light else "background"]

    def _rest(self, mark: Mark) -> float:
        """How much of its color a terminal wears while nothing is happening."""
        tint, strength = self.settings["tint"], float(self.settings["strength"])
        if tint == "focus":
            return strength if mark.focused else 0.0
        if tint == "all":
            return strength if mark.focused else strength / 2
        return 0.0

    def show(self, marks: dict[str, Mark]) -> None:
        """`marks`: terminal -> what it should show. A terminal no longer named gets its own
        background back; one seen for the first time is written to even when it should show
        nothing, which clears what a hub that died may have left there."""
        with self._lock:
            if self._closed:
                return
            if self.settings["tint"] == "off" and not self.settings["pulse"] and not self.settings["title"]:
                marks = {}  # everything is off: write to no terminal, beyond undoing what was shown
            for tty in [t for t in self._shown if t not in marks]:
                self.write(tty, RESET)
                del self._shown[tty]
                self._pulses.pop(tty, None)
            for tty, mark in marks.items():
                amount = self._rest(mark)
                spec = mix(self.background(tty), mark.color, amount) if amount > 0 else ""
                title = mark.title if self.settings["title"] else ""
                was = self._shown.get(tty)
                if was == (spec, title):
                    continue
                data = b""
                if was is None or was[0] != spec:
                    data += _background(spec)
                    self._pulses.pop(tty, None)  # what it should show changed: a pulse under way stops
                if title and (was is None or was[1] != title):
                    data += _title(title)
                if self.write(tty, data):
                    self._shown[tty] = (spec, title)

    def pulse(self, tty: str, color: str, asked: bool = False) -> threading.Thread | None:
        """Light a terminal up in `color` and let it settle back to what it showed: "this one".
        `asked`: the user asked to be shown it, so it happens even with pulses turned off."""
        if not (asked or self.settings["pulse"]) or not tty or not mix(self.background(tty), color, 0):
            return None
        with self._lock:
            if self._closed:
                return None
            number = self._pulses[tty] = self._pulses.get(tty, 0) + 1
        thread = threading.Thread(target=self._pulse, args=(tty, color, number), name="terminal-pulse", daemon=True)
        thread.start()
        return thread

    def _pulse(self, tty: str, color: str, number: int) -> None:
        for step in range(PULSE_STEPS + 1):
            with self._lock:
                if self._pulses.get(tty) != number:
                    return  # a newer pulse took over, or the terminal now shows something else
                rest = self._shown.get(tty, ("", ""))[0]
                if step == PULSE_STEPS:
                    self.write(tty, _background(rest))
                    return
                # From the peak down to the resting color, fast at first and slow at the end.
                at_rest = float(self.settings["strength"]) * (1 if rest else 0)
                peak = max(at_rest, float(self.settings["pulse_strength"]))
                amount = at_rest + (peak - at_rest) * (1 - step / PULSE_STEPS) ** 2
                self.write(tty, _background(mix(self.background(tty), color, amount)))
            self.sleep(PULSE_SECONDS / PULSE_STEPS)

    def close(self) -> None:
        """Give every terminal its own background back (the hub is stopping)."""
        with self._lock:
            for tty, (spec, _) in self._shown.items():
                if spec or tty in self._pulses:
                    self.write(tty, RESET)
            self._shown.clear()
            self._pulses.clear()
            self._closed = True
