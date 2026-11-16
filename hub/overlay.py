"""The Windows overlay: a child process the hub tells what to draw (see overlay/Overlay.cs).

The two sides exchange one JSON object per line over the child's stdin and stdout, so there is
no port to protect and the window disappears by itself when the hub exits.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Callable

DEFAULTS = {
    "enabled": True,
    "mode": "dots",  # dots | list
    "corner": "top-right",  # top-right | top-left | bottom-right | bottom-left
    "offset_x": 150,  # keeps clear of the window buttons of a maximized app
    "offset_y": 8,
    "opacity": 0.35,  # dots while nothing is happening
    "list_opacity": 0.85,
    "flash_seconds": 4,
    "hotkeys": {"toggle": "Ctrl+Alt+L", "allow": "Ctrl+Alt+Y", "deny": "Ctrl+Alt+N"},
}
RETRY_AFTER = 30.0  # seconds before a crashed overlay is started again


class Overlay:
    def __init__(self, script: str, config: dict, on_message: Callable[[dict], None] = lambda m: None,
                 log: Callable[[str], None] = lambda line: None):
        self.script, self.config, self.on_message, self.log = script, config, on_message, log
        self.proc: subprocess.Popen | None = None
        self.ready = False
        self._lock = threading.Lock()
        self._state: dict | None = None  # last state message, replayed when the window (re)starts
        self._started = 0.0

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
        try:
            win_path = subprocess.run(["wslpath", "-w", self.script], capture_output=True, text=True,
                                      check=True).stdout.strip()
            self.proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", win_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
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
