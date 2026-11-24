"""Global hotkeys on Linux, through the X server (XGrabKey): from any app, pressed and let go
(push-to-talk needs both), no permission. On a Wayland desktop this reaches the keys only while
an X11 window has the keyboard, so there the keys can be given to the desktop's own shortcuts
instead (`sidetone talk`, see docs). Hotkeys are written the Windows way in config.json
("Ctrl+Alt+Space"): Ctrl, Alt, Shift, and Win for the Super key.
"""
from __future__ import annotations

import os
import threading
from typing import Callable

NAMES = {"space": "space", "backspace": "BackSpace", "back": "BackSpace", "delete": "Delete", "del": "Delete",
         "return": "Return", "enter": "Return", "tab": "Tab", "escape": "Escape", "esc": "Escape",
         "up": "Up", "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End",
         "pageup": "Prior", "prior": "Prior", "pagedown": "Next", "next": "Next",
         "plus": "equal", "oemplus": "equal", "minus": "minus", "oemminus": "minus",
         "comma": "comma", "period": "period"}


def keysym_name(part: str) -> str:
    p = part.strip().lower()
    if p in NAMES:
        return NAMES[p]
    if len(p) == 2 and p[0] == "d" and p[1].isdigit():
        return p[1]
    if p.startswith("f") and p[1:].isdigit():
        return "F" + p[1:]
    return p


class Hotkeys:
    """Calls `pressed(name)` and `released(name)` from its own thread."""

    def __init__(self, pressed: Callable[[str], None], released: Callable[[str], None], note: Callable[[str], None]):
        self.pressed, self.released, self.note = pressed, released, note
        self.wanted: dict[str, str] = {}
        self.paused = False
        self._lock = threading.Lock()
        self._display = None
        self._grabbed: dict[tuple[int, int], str] = {}
        self._held: set[tuple[int, int]] = set()
        self._dirty = False
        try:
            from Xlib import X, XK, display
            self.X, self.XK = X, XK
            self._display = display.Display(os.environ.get("DISPLAY") or None)
            self._root = self._display.screen().root
        except Exception as e:  # noqa: BLE001  no X server, or python-xlib missing
            note(f"hotkeys off: no X server to ask ({e})")
            return
        threading.Thread(target=self._listen, name="hotkeys", daemon=True).start()

    def set(self, keys: dict[str, str]) -> None:
        if keys == self.wanted:
            return
        self.wanted = dict(keys)
        self._apply()

    def pause(self, paused: bool) -> None:
        if paused != self.paused:
            self.paused = paused
            self._apply()

    def _masks(self, mods: int) -> list[int]:
        X = self.X
        # The same key with Caps Lock or Num Lock on is another key to X: grab those too.
        return [mods | extra for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask)]

    def _apply(self) -> None:
        """Asks the listening thread to grab again: one X connection both grabs and reads, and
        only from that thread."""
        self._dirty = True

    def _grab(self) -> None:
        X = self.X
        self._dirty = False
        with self._lock:
            for (code, mods) in list(self._grabbed):
                for m in self._masks(mods):
                    self._root.ungrab_key(code, m)
            self._grabbed.clear()
            refused = []
            if not self.paused:
                for name, combo in sorted(self.wanted.items()):
                    mods, code = 0, 0
                    for part in combo.split("+"):
                        p = part.strip().lower()
                        if p in ("ctrl", "control"):
                            mods |= X.ControlMask
                        elif p in ("alt", "option"):
                            mods |= X.Mod1Mask
                        elif p == "shift":
                            mods |= X.ShiftMask
                        elif p in ("win", "super", "cmd"):
                            mods |= X.Mod4Mask
                        elif p:
                            sym = self.XK.string_to_keysym(keysym_name(part))
                            code = self._display.keysym_to_keycode(sym) if sym else 0
                    if not code:
                        continue
                    errors = []
                    for m in self._masks(mods):
                        self._root.grab_key(code, m, True, X.GrabModeAsync, X.GrabModeAsync, onerror=lambda *a: errors.append(a))
                    self._display.sync()
                    if errors:
                        refused.append(f"{name} ({combo})")
                    else:
                        self._grabbed[(code, mods)] = name
            self._display.flush()
        if refused:
            self.note("keys another app holds: " + ", ".join(refused))

    def _name(self, code: int, state: int) -> str | None:
        X = self.X
        mods = state & (X.ControlMask | X.Mod1Mask | X.ShiftMask | X.Mod4Mask)
        return self._grabbed.get((code, mods))

    def _listen(self) -> None:
        import select
        X = self.X
        d = self._display
        waiting = None  # an event taken out early, to see whether a release was only a repeat
        while True:
            if self._dirty:
                self._grab()
            if waiting is None and not d.pending_events():
                select.select([d], [], [], 0.2)
                if not d.pending_events():
                    continue
            event, waiting = (waiting, None) if waiting is not None else (d.next_event(), None)
            if event.type not in (X.KeyPress, X.KeyRelease):
                continue
            if event.type == X.KeyRelease and d.pending_events():
                # A key held down repeats as release and press at the same moment: not let go.
                following = d.next_event()
                if following.type == X.KeyPress and following.detail == event.detail and following.time == event.time:
                    continue
                waiting = following
            self._handle(event.type, event)

    def _handle(self, kind: int, event) -> None:
        name = self._name(event.detail, event.state)
        if name is None and kind == self.X.KeyRelease:
            # Let go after the Ctrl or Alt: the state no longer has them, so find it by its key.
            name = next((n for (code, _), n in self._grabbed.items() if code == event.detail and (code, n) in self._held), None)
        if name is None:
            return
        if kind == self.X.KeyPress:
            if (event.detail, name) in self._held:
                return  # still held
            self._held.add((event.detail, name))
            self.pressed(name)
        else:
            self._held.discard((event.detail, name))
            self.released(name)
