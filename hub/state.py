"""Sessions the hub knows about, and how hook payloads map to what each one is doing."""
from __future__ import annotations

import os
import re
import time
import zlib
from dataclasses import dataclass, field

# Kokoro's clearer English voices, ordered so neighbours differ in accent and gender.
VOICE_POOL = [
    "af_heart", "bm_george", "am_michael", "bf_emma", "af_bella", "am_fenrir", "bm_fable",
    "af_nicole", "am_puck", "bf_isabella", "af_kore", "af_sarah", "af_aoede",
]

ACTIVE_WINDOW = 15 * 60  # a session counts as active this long after its last event
FORGET_AFTER = 6 * 3600  # sessions killed without a SessionEnd are dropped after this

_SPEAK_LINE = re.compile(r"^\s*<speak>\s*(.*?)\s*</speak>\s*$")
_SPEAK_LAST = re.compile(r".*<speak>(.*)</speak>")


def split_display(delta: str) -> tuple[str | None, str]:
    """Return (speech, display) for one streamed batch.

    Only a line that is nothing but a speak tag counts, so prose that mentions the tag is left alone.
    """
    speech, shown = None, []
    for line in delta.split("\n"):
        m = _SPEAK_LINE.match(line)
        if m:
            speech = m.group(1)
            line = f"🔊 {speech}"
        shown.append(line)
    return speech, "\n".join(shown)


def speech_from_message(message: str) -> str:
    """The speak line of a finished reply: the last own-line tag, else the last tag anywhere."""
    for line in reversed(message.splitlines()):
        m = _SPEAK_LINE.match(line)
        if m:
            return m.group(1)
    m = _SPEAK_LAST.match(re.sub(r"[\r\n]", " ", message))
    return m.group(1).strip() if m else ""


def describe(tool: str, tool_input: dict) -> str:
    """A short human line for what a tool call is doing."""
    file = os.path.basename(str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""))
    if tool == "Bash":
        return tool_input.get("description") or "Running a command"
    if tool in ("Edit", "Write", "NotebookEdit"):
        return f"Editing {file}" if file else "Editing"
    if tool == "Read":
        return f"Reading {file}" if file else "Reading"
    if tool in ("Grep", "Glob"):
        return "Searching"
    if tool in ("Agent", "Task"):
        return tool_input.get("description") or "Running a subagent"
    if tool in ("WebSearch", "WebFetch"):
        return "Browsing the web"
    if tool.startswith("mcp__"):
        return "Using " + tool.split("__")[1].replace("_", " ")
    return tool


@dataclass
class Session:
    id: str
    cwd: str
    name: str
    voice: str
    state: str = "idle"  # idle | working | needs_you | done | failed
    activity: str = ""  # what it is doing, while working
    note: str = ""  # how the last turn ended, shown when not working
    tasks: dict[str, bool] = field(default_factory=dict)  # task id -> completed
    turn_started: float | None = None
    spoken: str | None = None  # line already spoken this turn, so Stop doesn't repeat it
    last_speech: str = ""
    updated: float = field(default_factory=time.monotonic)

    def snapshot(self) -> dict:
        now = time.monotonic()
        return {
            "id": self.id,
            "name": self.name,
            "voice": self.voice,
            "state": self.state,
            "activity": self.activity,
            "note": self.note,
            "tasks_done": sum(self.tasks.values()),
            "tasks_total": len(self.tasks),
            "turn_seconds": round(now - self.turn_started) if self.turn_started else None,
            "last_speech": self.last_speech,
            "idle_seconds": round(now - self.updated),
        }


class Sessions:
    """Registry keyed by session id. Not thread-safe: the hub holds its lock around every call."""

    def __init__(self, pool: list[str], pinned: dict[str, str]):
        self.pool = pool
        self.pinned = pinned  # project name -> voice, from the config file
        self.by_id: dict[str, Session] = {}

    def touch(self, sid: str, cwd: str) -> Session:
        """Return the session, creating it on first sight (the hub may start after the session)."""
        now = time.monotonic()
        for old in [k for k, s in self.by_id.items() if now - s.updated > FORGET_AFTER]:
            del self.by_id[old]
        s = self.by_id.get(sid)
        if s is None:
            name = self._unique_name(os.path.basename(cwd.rstrip("/")) or "session")
            s = self.by_id[sid] = Session(id=sid, cwd=cwd, name=name, voice=self._voice_for(name))
        s.updated = now
        return s

    def remove(self, sid: str) -> None:
        self.by_id.pop(sid, None)

    def active_count(self) -> int:
        now = time.monotonic()
        return sum(1 for s in self.by_id.values() if now - s.updated <= ACTIVE_WINDOW)

    def _unique_name(self, base: str) -> str:
        taken = {s.name for s in self.by_id.values()}
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base} {n}"
        return name

    def _voice_for(self, name: str) -> str:
        """Same project, same voice every time; step to the next one if a live session has it."""
        if name in self.pinned:
            return self.pinned[name]
        in_use = {s.voice for s in self.by_id.values()}
        start = zlib.crc32(name.encode()) % len(self.pool)
        for i in range(len(self.pool)):
            voice = self.pool[(start + i) % len(self.pool)]
            if voice not in in_use:
                return voice
        return self.pool[start]
