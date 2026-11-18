"""How much of the plan is used up, and how full a session's context is.

Nothing here needs a hub. The plan's figures come from Claude Code's own `/usage`, asked through
a headless call: measured on 2.1.327 it answers in about a second and makes no request to a
model, so asking costs nothing. Its answer is text written for people; `parse` reads it loosely
and a line it does not understand gives no figure, never a wrong one. A session's context is
counted from the end of Claude Code's record of that session, which on a test session gave to
the token what `/context` showed at the same moment.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import signal
import subprocess
from typing import NamedTuple

# Variables that tie a new Claude Code process to the session whose hook started the hub. The
# same list as in hub.py, which cannot be imported from here; a test keeps the two alike.
OWN_SESSION = re.compile(r"CLAUDECODE\Z|CLAUDE_(PID|EFFORT)\Z|CLAUDE_CODE_(CHILD|MESSAGING|SESSION)_"
                         r"|CLAUDE_CODE_(SSE_PORT|ENTRYPOINT|EXECPATH)\Z")
SORRY = "I could not read the usage."
WINDOW = 1_000_000  # tokens; measured for Fable 5.2, Opus 5.5 and Haiku 5.5. The record does not say it.


class Window(NamedTuple):
    used: float  # percent of it that is used, 0 to 100
    resets: str  # when it starts again, as Claude Code writes it, without the time zone:
    #              "Nov 18, 2:39am"; "" = not said


class Usage(NamedTuple):
    five_hour: Window | None  # None = no figure
    week: Window | None       # all models together
    models: dict              # the week of one model, by its name: {"Fable": Window}


def ask(program: str = "", timeout: float = 20.0, cwd: str = "") -> tuple[str, str]:
    """Run `/usage` and wait for it: (what it printed, "") or ("", why there is nothing).

    Hooks are off, so the call neither speaks nor shows up as a session, and no MCP server is
    started for it. `cwd` should be a folder of the user's own with no project in it; "" is
    one made for this under the run folder. stdin is closed: with an open one that sends
    nothing, Claude Code waits three seconds for it before it starts."""
    program = program or shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    folder = cwd or os.path.join(os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache"),
                                 "claude-speaks", "usage")
    env = {k: v for k, v in os.environ.items() if not OWN_SESSION.match(k)}
    cmd = [program, "-p", "--no-session-persistence", "--strict-mcp-config",
           "--settings", '{"disableAllHooks": true}', "--", "/usage"]
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        proc = subprocess.Popen(cmd, cwd=folder, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as e:
        return "", f"could not start {program}: {e.strerror or e}"
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # its own group, so what it started goes too
        except OSError:
            pass
        proc.communicate()
        return "", f"no answer in {timeout:.0f}s"
    if proc.returncode != 0:
        return "", (err or out).strip()[:300] or f"exit {proc.returncode}"
    return out, "" if out.strip() else "an empty answer"


# "Current session: 15% used <dot> resets Nov 18, 2:39am (America/New_York)"
LINE = re.compile(r"^[ \t]*([A-Za-z0-9][^:%\n]{0,60}?)[ \t]*:[ \t]*(\d{1,3}(?:\.\d+)?)[ \t]*%[ \t]*used\b([^\n]*)$",
                  re.MULTILINE)


def parse(text: str) -> Usage:
    """The figures in what `/usage` printed. Of two lines for one window the first counts."""
    five_hour, week, models = None, None, {}
    for label, percent, rest in LINE.findall(text or ""):
        used = float(percent)
        if used > 100:
            continue
        m = re.search(r"\bresets?\b[ \t]*(?:at |on )?([^()\n]*)", rest, re.IGNORECASE)
        window = Window(used, m.group(1).strip(" \t\r,;-") if m else "")
        kind, name = _which(label)
        if kind == "five_hour":
            five_hour = five_hour or window
        elif kind == "week":
            week = week or window
        elif kind == "model":
            models.setdefault(name, window)
    return Usage(five_hour, week, models)


def _which(label: str) -> tuple[str, str]:
    """Which window a line is about, from the words before its colon: "Current session" is
    the five hours, "Current week (all models)" the week, "Current week (Fable)" Fable's."""
    low = label.lower()
    if "week" in low or re.search(r"\b(7|seven)[ -]?day", low):
        inside = re.search(r"\(([^()]*)\)", label)
        name = re.sub(r"\s+only\Z", "", inside.group(1).strip(), flags=re.IGNORECASE) if inside else ""
        if not name or re.search(r"\ball\b", name, re.IGNORECASE):
            return "week", ""
        return ("model", name) if re.fullmatch(r"[A-Za-z][A-Za-z0-9. ]{0,29}", name) else ("", "")
    if "session" in low or re.search(r"\b(5|five)[ -]?h(ou)?r", low):
        return "five_hour", ""
    return "", ""


def clock(resets: str) -> str:
    """The time of day in a `resets` text, as a voice can read it: "2:39 AM", "3 PM", "14:30";
    "" when there is none."""
    m = re.search(r"\b(\d{1,2})(?::(\d\d))?[ ]?([ap])\.?m\b", resets or "", re.IGNORECASE)
    if m:
        return f"{int(m.group(1))}{':' + m.group(2) if m.group(2) else ''} {m.group(3).upper()}M"
    m = re.search(r"\b(\d{1,2}):(\d\d)\b", resets or "")
    return f"{int(m.group(1))}:{m.group(2)}" if m else ""


def say(usage: Usage | None) -> str:
    """One or two short sentences for the voice, the five hours first: "15 percent of the five
    hours used, back at 2:39 AM. The week is at 37 percent, Fable at 70." """
    if not usage:
        return SORRY
    said = []
    if usage.five_hour:
        at = clock(usage.five_hour.resets)
        said.append(f"{usage.five_hour.used:.0f} percent of the five hours used" + (f", back at {at}" if at else "") + ".")
    rest = [f"The week is at {usage.week.used:.0f} percent"] if usage.week else []
    for name, window in usage.models.items():
        rest.append(f"{name} at {window.used:.0f}" if rest else f"The {name} week is at {window.used:.0f} percent")
    if rest:
        said.append(", ".join(rest) + ".")
    return " ".join(said) or SORRY


# Is a spoken sentence a question about the plan's usage? A yes takes the words away from the
# session they were said to, so it has to be one for sure. All of this must hold: it names the
# usage or one of its windows (TOPIC); it begins like a question or a request for it (ASKING),
# or is nothing but "usage" with a few small words (BARE); and every word in it is one such a
# question is made of (WORDS). Any other word ("memory", "meter", "overlay", "hub") makes it
# something to hand to the session.
TOPIC = re.compile(r"\busage\b|\b(five|5) hours?\b|\bweekly (limit|window)\b")
ASKING = re.compile(r"(whats|what is|what s|what are|hows|how is|how s|how much|how close|how far|"
                    r"tell me|give me|show me|check|report|when (does|do|is|will)|(do|did|have|am) i)\b")
BARE = frozenset("usage my the our current plan weekly week five 5 hour hours window please now check report".split())
WORDS = BARE | frozenset("""
    what whats s is are how hows much close far tell give show me when does do did will have has am i ive
    of in on for to at about a this that it there any some still already yet so up left remaining used use
    using got get going doing looking look like right currently today tonight percent percentage subscription
    limit limits reset resets start starts again back until out over near been be total overall
    claude fable opus sonnet haiku model models all""".split())
# "Five hours" alone can be about anything; with one of these it is about the window.
OF_A_WINDOW = frozenset("usage used use left remaining reset resets back start starts window limit".split())
OPEN_END = frozenset("of in on for to at about a the my".split())  # a sentence that stops here is not finished
# Words a spoken question opens with. "Alright, so what's the usage?" was the author's first
# real one (2026-11-18), and "alright" sent it to the session.
POLITE = re.compile(r"((hey|hi|ok|okay|alright|all right|right|yeah|yes|sure|oh|so|um|uh|well|and|also|then|now|"
                    r"claude|please|by the way|btw) )+")
CAN_YOU = re.compile(r"(can|could|would|will) you (please |just |quickly )*")


def asks(text: str) -> bool:
    """Whether these spoken words ask for the plan's usage. The speech model writes loosely:
    no question mark at times, "use age" for usage, "5-hour" or "five hour"."""
    said = re.sub(r"['\u2019]", "", (text or "").lower())
    said = " ".join(re.sub(r"[^a-z0-9]+", " ", said).split())
    said = re.sub(r"\buse age\b|\busages\b", "usage", said)
    m = POLITE.match(said)
    said = said[m.end():] if m else said
    m = CAN_YOU.match(said)
    said = said[m.end():] if m else said
    words = said.split()
    if not words or len(words) > 14 or not TOPIC.search(said) or not WORDS.issuperset(words):
        return False
    if OF_A_WINDOW.isdisjoint(words) or words[-1] in OPEN_END:
        return False
    return bool(ASKING.match(said)) or ("usage" in words and BARE.issuperset(words))


class Context(NamedTuple):
    tokens: int     # in the session's context after its last reply
    window: int     # what the context can hold
    percent: float  # how full that is, 0 to 100


def transcript(projects_dir: str, sid: str) -> str:
    """Where Claude Code keeps its record of a session; "" if it has none. Hooks are handed
    this as `transcript_path`."""
    found = glob.glob(os.path.join(glob.escape(projects_dir), "*", glob.escape(sid) + ".jsonl"))
    return found[0] if found else ""


def context(path: str, window: int = WINDOW, tail: int = 1_000_000) -> Context | None:
    """How full a session's context is, from the end of its record; None with nothing to go on.

    The last reply of the session itself (not of a helper it started) says what was read for
    it: fresh input plus what was saved plus what was reused. That is the context as it was
    then, and the number `/context` and the status line show. A compaction after that reply
    leaves a line that says what was kept, which then is the figure. Only the last `tail`
    bytes are read (2 ms for a megabyte), so a record that ends in more than that without a
    reply, such as one very large pasted picture, gives None until the next reply."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - tail))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"assistant"' not in line and '"compact_boundary"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:  # the first line of the part that was read is cut
            continue
        tokens = _tokens(entry) if isinstance(entry, dict) else 0
        if tokens:
            return Context(tokens, window, min(100.0, 100.0 * tokens / window) if window > 0 else 0.0)
    return None


def _tokens(entry: dict) -> int:
    """The context a line of the record tells of; 0 for a line that tells of none. An error
    written in the model's place is such a line: it counts nothing."""
    if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
        kept = (entry.get("compactMetadata") or {}).get("postTokens")
        return kept if isinstance(kept, int) and kept > 0 else 0
    if entry.get("type") != "assistant" or entry.get("isSidechain"):
        return 0
    message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
    parts = [usage.get(k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
    return sum(p for p in parts if isinstance(p, int) and p > 0)
