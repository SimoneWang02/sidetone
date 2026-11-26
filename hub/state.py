"""Sessions the hub knows about, and how hook payloads map to what each one is doing."""
from __future__ import annotations

import json
import os
import re
import time
import zlib
from dataclasses import dataclass, field

# Kokoro's clearest English voices, by the grades Kokoro gives them (VOICES.md of
# hexgrad/Kokoro-82M), best first (settings.KOKORO_GRADES): the first sessions get the clearest
# voices. Seven; the others graded C or better are a tick away in the settings window. Nicole is
# not ticked at first.
VOICE_POOL = [
    "af_heart", "af_bella", "bf_emma", "am_michael", "am_fenrir", "am_puck", "bm_george",
]

# One color per session for its name in the overlay. Soft, easy to tell apart on dark glass,
# and none of them the plain blue, amber, green or red the status lights use. The fifth is
# nearly the microphone's pink. Eight that are far apart, and who gets which is decided by
# distance (_color_for). Then twelve more, each the color furthest from all before it among
# colors light enough to read on dark glass and clear of the status lights and of the white of
# titles; they are stronger than the first eight, which is what keeps twenty apart: the
# nearest two of the twenty are 29 apart, of thirty it would be 25.
COLORS = ["#8AB4FF", "#FFA24D", "#B07CFF", "#7FDBCA", "#FF8FA3", "#F9E27D", "#B9F27C", "#FF7FD9",
          "#A98C68", "#0CC006", "#00FBAB", "#EDF11C", "#FE5910", "#ED44EC", "#8C9802", "#AA85A7",
          "#A3FA30", "#DAF0B8", "#FE4B93", "#F1B8FF"]
SOFT = 8  # the first so many of the list are the soft ones, handed out before the others
# Two name colors nearer than this are hard to tell apart at a glance. Measured as the
# distance between them in CIELAB, where equal steps look about equally big to the eye:
# that orange and the yellow were 25 apart, the pink and the teal are 77.
TOO_CLOSE = 40.0

ACTIVE_WINDOW = 15 * 60  # a session counts as active this long after its last event
FORGET_AFTER = 6 * 3600  # sessions killed without a SessionEnd are dropped after this
KEPT_FOR = 15 * 60  # after a hub restart, a session that has not reported yet keeps its name, color and voice this long
HEIR_WITHIN = 30.0  # seconds a cleared session's place waits for the session Claude Code starts after it

# The spoken line. Its tag may carry the session's own title and, when the line is not in
# English, its language: <speak title="Login page redesign" lang="it">...</speak>, in any order.
_ATTRS = r"""((?:\s+[A-Za-z]+\s*=\s*(?:"[^"]*"|'[^']*'))*)"""
_SPEAK_LINE = re.compile(r"^\s*<speak" + _ATTRS + r"\s*>\s*(.*?)\s*</speak>\s*$")
_SPEAK_LAST = re.compile(r".*<speak" + _ATTRS + r"\s*>(.*)</speak>")
_ATTR = re.compile(r"""([A-Za-z]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def _attrs(text: str) -> dict:
    return {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3)).strip() for m in _ATTR.finditer(text or "")}


def tag_lang(attrs: dict) -> str:
    """The language a speak line says it is in, as a short code ("it", "pt"), or "" for none."""
    m = re.fullmatch(r"([a-z]{2,3})(?:[-_][A-Za-z]+)?", str(attrs.get("lang", "")).lower())
    return m.group(1) if m else ""


def _lab(color: str) -> tuple[float, float, float]:
    """A "#RRGGBB" color in CIELAB (lightness, green to red, blue to yellow)."""
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def curve(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    r, g, b = (linear(int(color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    x = curve((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047)
    y = curve(0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = curve((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def color_distance(a: str, b: str) -> float:
    """How different two colors look: 0 = the same, about 100 = as different as colors get."""
    return sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b))) ** 0.5


def usable_colors(wanted) -> list[str]:
    """The name colors to hand out: the user's own list if it holds at least two, else ours."""
    own = [c.upper() for c in wanted if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)] if isinstance(wanted, list) else []
    own = list(dict.fromkeys(own))
    return own if len(own) >= 2 else list(COLORS)


def split_display(delta: str) -> tuple[str | None, str, str, str]:
    """Return (speech, display, title, lang) for one streamed batch; title and lang are "" when
    the tag has none.

    Only a line that is nothing but a speak tag counts, so prose that mentions the tag is left alone.
    """
    speech, shown, title, lang = None, [], "", ""
    for line in delta.split("\n"):
        m = _SPEAK_LINE.match(line)
        if m:
            attrs = _attrs(m.group(1))
            speech, title, lang = m.group(2), attrs.get("title", ""), tag_lang(attrs)
            line = f"🔊 {speech}"
        shown.append(line)
    return speech, "\n".join(shown), title, lang


def speech_from_message(message: str) -> str:
    """The speak line of a finished reply: the last own-line tag, else the last tag anywhere."""
    return _spoken(message)[0]


def title_from_message(message: str) -> str:
    """The title a finished reply gives its session in its speak tag, or ""."""
    return _spoken(message)[1]


def lang_from_message(message: str) -> str:
    """The language a finished reply gives its speak line, or "" (English)."""
    return _spoken(message)[2]


def _spoken(message: str) -> tuple[str, str, str]:
    m = next((m for m in map(_SPEAK_LINE.match, reversed(message.splitlines())) if m), None)
    m = m or _SPEAK_LAST.match(re.sub(r"[\r\n]", " ", message))
    if not m:
        return ("", "", "")
    attrs = _attrs(m.group(1))
    return (m.group(2).strip(), attrs.get("title", ""), tag_lang(attrs))


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
class Agent:
    """A subagent of a session, while it runs and for a moment after it finished: a small
    companion beside the session's character (`overlay.character_agents`)."""
    task: str  # the few words the Agent tool was given for it (`description`)
    since: float  # when it started, on the clock that counts from the boot: their order
    done: float = 0.0  # when it finished by itself: it cheers for `base.AGENT_CHEER` seconds and is not shown after


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
    given: bool = False  # the title is the session's own, written in its replies; nothing else replaces it
    activity: str = ""  # what it is doing, while working
    note: str = ""  # how the last turn ended, shown when not working
    tasks: dict[str, bool] = field(default_factory=dict)  # task id -> completed
    agents: dict[str, Agent] = field(default_factory=dict)  # Claude Code's agent id -> its subagent that runs or has just finished
    agent_task: str = ""  # the task of the Agent tool's last call, for the agent that starts next
    turn_started: float | None = None
    spoken: str | None = None  # line already spoken this turn, so neither Stop nor a late batch repeats it
    last_speech: str = ""
    permission_mode: str = ""  # default | plan | acceptEdits | auto | ... as last reported by a hook
    seen_file: bool = False  # Claude Code's own session file was seen for it (see claude_sessions.py)
    tty: str | None = None  # the terminal it runs in ("" = none); not looked for yet while None (see terminal.py)
    pids: list = field(default_factory=list)  # the live processes that have it, from Claude Code's files: two when it is open in two terminals
    order: int = 0  # its place in the bar: lower comes first, and it keeps it across a hub restart
    context: float | None = None  # how full its context is, in percent (see usage.context); None = not known
    turn_at: int | None = None  # how long its record was when the turn's prompt came (see usage.turn)
    turn_took: float | None = None  # seconds its last finished turn ran
    turn_since: float = 0.0  # when that prompt came, as the history's lines are timed
    turn_tokens: int | None = None  # what its last turn used, once that has ended; None = not known, or in a turn
    tally: object = None  # what the whole session has used so far (a usage.Tally); None = not read yet
    updated: float = field(default_factory=time.monotonic)
    # Not a session: the light of one just cleared, kept, its context at 0, until the session
    # Claude Code starts after it takes its place (see `Sessions.stand_in`).
    standin: bool = False
    # Its voice is off, the others' is not (the key `mute_session`, `sidetone mute`): what it says
    # is shown at its light instead, as with the voice off for everyone. It stays with the
    # session across /clear and a hub restart, and ends with it.
    muted: bool = False
    # The turn began with words of yours, typed or spoken: how it ends is an answer to you. Not
    # one that a background agent's end woke.
    yours: bool = False
    # It has hit the usage limit and that was said or shown: not news until a turn of its own
    # has ended well (see `Hub._limit_known`).
    limited: bool = False

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
            "agents": [a.task for a in self.agents.values() if not a.done],  # the tasks of its subagents that run
            "turn_seconds": round(now - self.turn_started) if self.turn_started else None,
            "last_speech": self.last_speech,
            "idle_seconds": round(now - self.updated),
            "context": self.context,
            "turn_tokens": self.turn_tokens,
            "tty": self.tty or "",  # the terminal it runs in, where known
            "muted": self.muted,
        }


class Sessions:
    """Registry keyed by session id. Not thread-safe: the hub holds its lock around every call."""

    def __init__(self, pool: list[str], pinned: dict[str, str], voices_file: str | None = None, colors=None):
        self.pool = pool
        self.colors = usable_colors(colors)  # the name colors handed out
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
        # Places of sessions just cleared, by folder: /clear ends a session and starts a new one in
        # the same terminal, which takes the old one's name, color, voice and place in the bar.
        self.cleared: dict[str, tuple[dict, float]] = {}

    def touch(self, sid: str, cwd: str, after_clear: bool = False) -> Session:
        """Return the session, creating it on first sight (the hub may start after the session).
        `after_clear`: it is the one Claude Code started for a cleared conversation."""
        now = time.monotonic()
        for old in [k for k, s in self.by_id.items()
                    if now - s.updated > (HEIR_WITHIN if s.standin else FORGET_AFTER)]:
            del self.by_id[old]
        if self.kept and now - self.kept_at > KEPT_FOR:
            self.kept.clear()
        s = self.by_id.get(sid)
        if s is None:
            was = self.kept.pop(sid, None)
            heir = self.cleared.pop(cwd, None) if after_clear else None
            if heir and now - heir[1] < HEIR_WITHIN and not any(o.name == heir[0]["name"] and not o.standin
                                                                  for o in self.by_id.values()):
                old = heir[0]  # the chat is new, so its title is not kept
                for k in [k for k, o in self.by_id.items() if o.standin and o.name == old["name"]]:
                    del self.by_id[k]  # its light is this one's now
                s = Session(id=sid, cwd=cwd, name=old["name"], voice=self.pinned.get(old["name"], old["voice"]),
                            color=old["color"], order=old["order"], context=0.0, muted=bool(old.get("muted")))
            elif was:  # known before the hub restarted: the same name, color, voice and place as then
                s = Session(id=sid, cwd=cwd or was["cwd"], name=was["name"],
                            voice=self.pinned.get(was["name"], was["voice"]), color=was["color"],
                            title=was["title"], named=was["named"], settled=was["settled"], given=was["given"],
                            state=was["state"], note=was["note"], order=was["order"], muted=was.get("muted", False))
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

    def reorder(self, names: list) -> bool:
        """Put the sessions in the order of `names` (dragged there in the overlay); any not named
        keep their order after those. Each gets a new place, so a session that is only kept from
        before a restart still goes in after them. Returns whether anything moved."""
        rank = {name: i for i, name in enumerate(names)}
        now = sorted(self.by_id.items(), key=lambda item: (rank.get(item[1].name, len(rank)), item[1].order))
        if [sid for sid, _ in now] == list(self.by_id):
            return False
        for place, (_, s) in enumerate(now, 1):
            s.order = place
        later = len(now) + 1
        for kept in sorted(self.kept.values(), key=lambda k: k["order"]):
            kept["order"], later = later, later + 1
        self.by_id.clear()
        self.by_id.update(now)
        return True

    def clearing(self, sid: str) -> None:
        """The session ended by /clear: keep its place for the one that follows (see touch)."""
        s = self.by_id.get(sid)
        if s:
            self.cleared[s.cwd] = ({"name": s.name, "voice": s.voice, "color": s.color, "order": s.order, "muted": s.muted}, time.monotonic())

    def stand_in(self, old: Session) -> None:
        """A session ended by /clear: its light stays, with its context at 0, until the session
        that follows it in the same terminal takes it (see touch), so the overlay's arc winds
        back to nothing instead of the light going out and coming back."""
        self.by_id["cleared:" + old.id] = Session(id="cleared:" + old.id, cwd=old.cwd, name=old.name, voice=old.voice,
                                                  color=old.color, order=old.order, context=0.0, standin=True, muted=old.muted)
        in_order = sorted(self.by_id.items(), key=lambda item: item[1].order)
        self.by_id.clear()
        self.by_id.update(in_order)

    def remove(self, sid: str) -> None:
        self.by_id.pop(sid, None)
        self.kept.pop(sid, None)

    def identities(self) -> list[dict]:
        """What makes each session recognisable, in the order of the bar, to be handed to keep()
        after a restart. Includes the ones an earlier hub knew that have not reported yet, so a
        second restart soon after the first does not lose them."""
        back = [{"id": s.id, "cwd": s.cwd, "name": s.name, "voice": s.voice, "color": s.color,
                 "title": s.title, "named": s.named, "settled": s.settled, "given": s.given,
                 "state": s.state, "note": s.note, "muted": s.muted,
                 "seen_file": s.seen_file, "order": s.order} for s in self.by_id.values() if not s.standin]
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
                    "settled": bool(entry.get("settled")), "given": bool(entry.get("given")),
                    "state": state if ended else "idle",
                    "note": str(entry.get("note") or "") if ended else "",
                    "seen_file": bool(entry.get("seen_file")), "order": order,
                    "muted": bool(entry.get("muted")),
                }
                if self.kept[sid]["color"] not in self.colors:  # a color that is no longer handed out
                    self.kept[sid]["color"] = ""
            except (KeyError, TypeError, AttributeError):
                continue
        # In the order of the bar: a session whose color is gone, or too near the color of one
        # before it, gets the color that is furthest from everybody else's.
        entries = list(self.kept.values())
        for i, entry in enumerate(entries):
            mine, others = entry["color"], [e["color"] for e in entries if e is not entry and e["color"]]
            if mine and all(color_distance(mine, e["color"]) >= TOO_CLOSE for e in entries[:i] if e["color"]):
                continue
            best = self._color_for(entry["name"], others)
            apart = lambda c: min((color_distance(c, o) for o in others), default=0.0)  # noqa: E731
            if not mine or apart(best) > apart(mine):
                entry["color"] = best

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

    def _color_for(self, name: str, others: list[str] | None = None) -> str:
        """The color for a session's name. Alone, a project has the same color every time.
        With other sessions about (`others`: their colors; by default all that are known), it
        is the free color that is furthest from all of theirs, so that two names side by
        side are never an orange and a yellow."""
        soft = self.colors[:SOFT]
        start = zlib.crc32(name.encode()[::-1]) % len(soft)
        order = soft[start:] + soft[:start] + self.colors[SOFT:]
        if others is None:
            others = [s.color for s in self.by_id.values()] + [k["color"] for k in self.kept.values()]
        others = [c for c in others if re.fullmatch(r"#[0-9a-fA-F]{6}", c or "")]
        if not others:
            return order[0]
        free = [c for c in order if c not in others]
        if not free:  # more sessions than colors: the one the fewest have
            return min(order, key=others.count)

        def apart(c: str) -> float:
            return min(color_distance(c, o) for o in others)
        # A soft one while one of those is still clearly apart from everybody; then any.
        gentle = max((c for c in free if c in soft), key=apart, default=None)
        return gentle if gentle and apart(gentle) >= TOO_CLOSE else max(free, key=apart)

    def _voice_for(self, name: str) -> str:
        """Same project, same voice every time. A new project gets one nobody else has, if any is left."""
        if name in self.pinned:
            return self.pinned[name]
        live = {s.voice for s in self.by_id.values()} | {k["voice"] for k in self.kept.values()}
        # Its voice from before, while that voice is still ticked (in the pool). A voice given
        # by hand is pinned instead (`Hub.set_voice`).
        if self.remembered.get(name) in self.pool and self.remembered[name] not in live:
            return self.remembered[name]
        order = list(self.pool)  # in the pool's order, which the settings window lets you change
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
