"""Sessions the hub knows about, and how hook payloads map to what each one is doing."""
from __future__ import annotations

import json
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

# One color per session for its name in the overlay. Soft, easy to tell apart on dark glass,
# and none of them the plain blue, amber, green or red the status lights use.
COLORS = ["#8AB4FF", "#FFB86B", "#C6A0F6", "#7FDBCA", "#FF8FA3", "#F9E27D", "#B9F27C", "#F5A97F", "#91D7E3", "#F5BDE6"]

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


def short_title(text: str, limit: int = 44) -> str:
    """A few words that say what a session is about, from its name ("fix-login-test") or a prompt."""
    line = next((ln.strip() for ln in str(text or "").splitlines() if ln.strip()), "")
    if re.fullmatch(r"[\w.]+(?:[-_][\w.]+)+", line):  # a slug: make it words
        line = re.sub(r"[-_]+", " ", line)
    line = re.sub(r"\s+", " ", line)
    if len(line) > limit:
        line = line[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "\u2026"
    return line[:1].upper() + line[1:]


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


def permission_summary(tool: str, tool_input: dict) -> tuple[str, str]:
    """(what is being asked, the exact thing it would run or touch) for a permission request."""
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if tool == "Bash":
        return tool_input.get("description") or "run a command", str(tool_input.get("command") or "")
    if tool in ("Edit", "Write", "NotebookEdit"):
        return f"{'write' if tool == 'Write' else 'edit'} {os.path.basename(path)}", path
    if tool == "Read":
        return f"read {os.path.basename(path)}", path
    if tool in ("WebFetch", "WebSearch"):
        target = str(tool_input.get("url") or tool_input.get("query") or "")
        return "use the web", target
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return f"use {parts[1].replace('_', ' ')}", parts[-1]
    return f"use {tool}", ""


@dataclass
class Session:
    id: str
    cwd: str
    name: str
    voice: str
    color: str = COLORS[0]  # its name is written in this color in the overlay
    state: str = "idle"  # idle | working | needs_you | done | failed
    title: str = ""  # a few words on what it is about: Claude Code's name for it, else the last prompt
    named: str = ""  # that name as Claude Code has it; empty while the title comes from a prompt
    activity: str = ""  # what it is doing, while working
    note: str = ""  # how the last turn ended, shown when not working
    tasks: dict[str, bool] = field(default_factory=dict)  # task id -> completed
    turn_started: float | None = None
    spoken: str | None = None  # line already spoken this turn, so Stop doesn't repeat it
    last_speech: str = ""
    permission_mode: str = ""  # default | plan | acceptEdits | auto | ... as last reported by a hook
    seen_file: bool = False  # Claude Code's own session file was seen for it (see claude_sessions.py)
    updated: float = field(default_factory=time.monotonic)

    def snapshot(self) -> dict:
        now = time.monotonic()
        return {
            "id": self.id,
            "name": self.name,
            "voice": self.voice,
            "color": self.color,
            "state": self.state,
            "title": self.title,
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

    def __init__(self, pool: list[str], pinned: dict[str, str], voices_file: str | None = None):
        self.pool = pool
        self.pinned = pinned  # project name -> voice, from the config file
        self.by_id: dict[str, Session] = {}
        # Voices already handed out, kept on disk so a project sounds the same after a restart.
        self.voices_file = voices_file
        self.remembered: dict[str, str] = {}
        if voices_file:
            try:
                with open(voices_file) as f:
                    self.remembered = {str(k): str(v) for k, v in json.load(f).items()}
            except (OSError, ValueError, AttributeError):
                pass

    def touch(self, sid: str, cwd: str) -> Session:
        """Return the session, creating it on first sight (the hub may start after the session)."""
        now = time.monotonic()
        for old in [k for k, s in self.by_id.items() if now - s.updated > FORGET_AFTER]:
            del self.by_id[old]
        s = self.by_id.get(sid)
        if s is None:
            name = self._unique_name(os.path.basename(cwd.rstrip("/")) or "session")
            s = self.by_id[sid] = Session(id=sid, cwd=cwd, name=name, voice=self._voice_for(name),
                                          color=self._color_for(name))
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

    def _color_for(self, name: str) -> str:
        """Same project, same color every time, unless a live session already has it."""
        start = zlib.crc32(name.encode()[::-1]) % len(COLORS)
        order = [COLORS[(start + i) % len(COLORS)] for i in range(len(COLORS))]
        live = {s.color for s in self.by_id.values()}
        return next((c for c in order if c not in live), order[0])

    def _voice_for(self, name: str) -> str:
        """Same project, same voice every time. A new project gets one nobody else has, if any is left."""
        if name in self.pinned:
            return self.pinned[name]
        live = {s.voice for s in self.by_id.values()}
        if self.remembered.get(name) in self.pool and self.remembered[name] not in live:
            return self.remembered[name]
        start = zlib.crc32(name.encode()) % len(self.pool)
        order = [self.pool[(start + i) % len(self.pool)] for i in range(len(self.pool))]
        taken = live | set(self.remembered.values())
        voice = next((v for v in order if v not in taken), None) or next((v for v in order if v not in live), order[0])
        if name not in self.remembered:  # a second session of the same project borrows, it does not rename
            self.remembered[name] = voice
            self._save()
        return voice

    def set_voice(self, name: str, voice: str) -> None:
        """The user chose this voice for a project: remember it and switch its open sessions now."""
        self.remembered[name] = voice
        self._save()
        for s in self.by_id.values():
            if s.name == name:
                s.voice = voice

    def _save(self) -> None:
        if not self.voices_file:
            return
        try:
            with open(self.voices_file, "w") as f:
                json.dump(self.remembered, f, indent=2, sort_keys=True)
        except OSError:
            pass
