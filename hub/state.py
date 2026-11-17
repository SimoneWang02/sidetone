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
KEPT_FOR = 15 * 60  # after a hub restart, a session that has not reported yet keeps its name, color and voice this long

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
    title: str = ""  # a few words on what it is about: Claude Code's name for it, else see Hub._title_from
    named: str = ""  # that name as Claude Code has it; empty while the title is our own
    settled: bool = False  # our own title came from the first reply and stays; before that it follows the prompt
    activity: str = ""  # what it is doing, while working
    note: str = ""  # how the last turn ended, shown when not working
    tasks: dict[str, bool] = field(default_factory=dict)  # task id -> completed
    turn_started: float | None = None
    spoken: str | None = None  # line already spoken this turn, so Stop doesn't repeat it
    last_speech: str = ""
    permission_mode: str = ""  # default | plan | acceptEdits | auto | ... as last reported by a hook
    seen_file: bool = False  # Claude Code's own session file was seen for it (see claude_sessions.py)
    order: int = 0  # its place in the bar: lower comes first, and it keeps it across a hub restart
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
        # Sessions an earlier hub knew that have not reported to this one yet (see keep()).
        self.kept: dict[str, dict] = {}
        self.kept_at = 0.0

    def touch(self, sid: str, cwd: str) -> Session:
        """Return the session, creating it on first sight (the hub may start after the session)."""
        now = time.monotonic()
        for old in [k for k, s in self.by_id.items() if now - s.updated > FORGET_AFTER]:
            del self.by_id[old]
        if self.kept and now - self.kept_at > KEPT_FOR:
            self.kept.clear()
        s = self.by_id.get(sid)
        if s is None:
            was = self.kept.pop(sid, None)
            if was:  # known before the hub restarted: the same name, color, voice and place as then
                s = Session(id=sid, cwd=cwd or was["cwd"], name=was["name"],
                            voice=self.pinned.get(was["name"], was["voice"]), color=was["color"],
                            title=was["title"], named=was["named"], settled=was["settled"],
                            state=was["state"], note=was["note"], order=was["order"])
            else:
                name = self._unique_name(os.path.basename(cwd.rstrip("/")) or "session")
                s = Session(id=sid, cwd=cwd, name=name, voice=self._voice_for(name), color=self._color_for(name),
                            order=1 + max([o.order for o in self.by_id.values()]
                                          + [k["order"] for k in self.kept.values()], default=0))
            self.by_id[sid] = s
            if any(o.order > s.order for o in self.by_id.values()):  # it belongs before one that is already back
                in_order = sorted(self.by_id.items(), key=lambda item: item[1].order)
                self.by_id.clear()
                self.by_id.update(in_order)
        s.updated = now
        return s

    def remove(self, sid: str) -> None:
        self.by_id.pop(sid, None)
        self.kept.pop(sid, None)

    def identities(self) -> list[dict]:
        """What makes each session recognisable, in the order of the bar, to be handed to keep()
        after a restart. Includes the ones an earlier hub knew that have not reported yet, so a
        second restart soon after the first does not lose them."""
        back = [{"id": s.id, "cwd": s.cwd, "name": s.name, "voice": s.voice, "color": s.color,
                 "title": s.title, "named": s.named, "settled": s.settled, "state": s.state, "note": s.note,
                 "seen_file": s.seen_file, "order": s.order} for s in self.by_id.values()]
        return sorted(back + list(self.kept.values()), key=lambda entry: entry["order"])

    def keep(self, entries) -> None:
        """Take over what an earlier hub knew about its sessions (the list identities() gave).

        Names, colors and voices are handed out in the order sessions turn up, and after a restart
        they turn up in a different order: without this, two sessions of one project swapped
        names, colors and voices. Each one gets its own back when it next reports (see touch).
        Until then nobody else is given its name, color or voice.
        """
        self.kept, self.kept_at = {}, time.monotonic()
        for order, entry in enumerate(entries if isinstance(entries, list) else [], 1):
            try:
                sid, state = str(entry["id"]), str(entry.get("state") or "idle")
                ended = state in ("idle", "done", "failed")  # a turn or a prompt that was open may be over by now
                self.kept[sid] = {
                    "id": sid, "cwd": str(entry.get("cwd") or ""), "name": str(entry["name"]),
                    "voice": str(entry["voice"]), "color": str(entry["color"]),
                    "title": str(entry.get("title") or ""), "named": str(entry.get("named") or ""),
                    "settled": bool(entry.get("settled")), "state": state if ended else "idle",
                    "note": str(entry.get("note") or "") if ended else "",
                    "seen_file": bool(entry.get("seen_file")), "order": order,
                }
            except (KeyError, TypeError, AttributeError):
                continue

    def active_count(self) -> int:
        now = time.monotonic()
        return sum(1 for s in self.by_id.values() if now - s.updated <= ACTIVE_WINDOW)

    def _unique_name(self, base: str) -> str:
        taken = {s.name for s in self.by_id.values()} | {k["name"] for k in self.kept.values()}
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base} {n}"
        return name

    def _color_for(self, name: str) -> str:
        """Same project, same color every time, unless a live session already has it."""
        start = zlib.crc32(name.encode()[::-1]) % len(COLORS)
        order = [COLORS[(start + i) % len(COLORS)] for i in range(len(COLORS))]
        live = {s.color for s in self.by_id.values()} | {k["color"] for k in self.kept.values()}
        return next((c for c in order if c not in live), order[0])

    def _voice_for(self, name: str) -> str:
        """Same project, same voice every time. A new project gets one nobody else has, if any is left."""
        if name in self.pinned:
            return self.pinned[name]
        live = {s.voice for s in self.by_id.values()} | {k["voice"] for k in self.kept.values()}
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
        for k in self.kept.values():
            if k["name"] == name:
                k["voice"] = voice

    def _save(self) -> None:
        if not self.voices_file:
            return
        try:
            with open(self.voices_file, "w") as f:
                json.dump(self.remembered, f, indent=2, sort_keys=True)
        except OSError:
            pass
