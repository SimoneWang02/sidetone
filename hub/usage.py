"""How much of the plan is used up, and how full a session's context is.

Nothing here needs a hub. The plan's figures come from Claude Code's own `/usage`, asked through
a headless call: measured on 2.1.327 it answers in about a second and makes no request to a
model, so asking costs nothing. Its answer is text written for people; `parse` reads it loosely
and a line it does not understand gives no figure, never a wrong one. A session's context is
counted from the end of Claude Code's record of that session, which on a test session gave to
the token what `/context` showed at the same moment.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import unicodedata
from typing import NamedTuple

import procs

# Variables that tie a new Claude Code process to the session whose hook started the hub. The
# same list as in hub.py, which cannot be imported from here; a test keeps the two alike.
OWN_SESSION = re.compile(r"CLAUDECODE\Z|CLAUDE_(PID|EFFORT)\Z|CLAUDE_CODE_(CHILD|MESSAGING|SESSION)_"
                         r"|CLAUDE_CODE_(SSE_PORT|ENTRYPOINT|EXECPATH)\Z")
SORRY = "I could not read the usage."
SORRY_IT = "Non sono riuscito a leggere i consumi."
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
    program = program or shutil.which("claude") or os.path.expanduser("~/.local/bin/claude" + (".exe" if os.name == "nt" else ""))
    folder = cwd or os.path.join(os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache"),
                                 "sidetone", "usage")
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
        procs.end_tree(proc)  # its own group, so what it started goes too
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


def say(usage: Usage | None, lang: str = "en") -> str:
    """One or two short sentences for the voice, the five hours first: "15 percent of the five
    hours used, back at 2:39 AM. The week is at 37 percent, Fable at 70." In Italian with
    `lang` "it"; English for any other."""
    if lang == "it":
        return _say_it(usage)
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


def _say_it(usage: Usage | None) -> str:
    """`say` in Italian: "Hai usato il 15 percento delle cinque ore, si azzera alle 2:39. La
    settimana è al 37 percento, Fable al 70." """
    if not usage:
        return SORRY_IT
    said = []
    if usage.five_hour:
        at = clock24(usage.five_hour.resets)
        said.append(f"Hai usato il {usage.five_hour.used:.0f} percento delle cinque ore" + (f", si azzera alle {at}" if at else "") + ".")
    rest = [f"La settimana è al {usage.week.used:.0f} percento"] if usage.week else []
    for name, window in usage.models.items():
        rest.append(f"{name} al {window.used:.0f}" if rest else f"La settimana di {name} è al {window.used:.0f} percento")
    if rest:
        said.append(", ".join(rest) + ".")
    return " ".join(said) or SORRY_IT


def clock24(resets: str) -> str:
    """`clock` on a 24-hour clock, as Italian says the time: "2:39 AM" gives "2:39", "3 PM" "15"."""
    said = clock(resets)
    m = re.fullmatch(r"(\d{1,2})(?::(\d\d))? ([AP])M", said)
    if not m:
        return said
    hour = int(m.group(1)) % 12 + (12 if m.group(3) == "P" else 0)
    return f"{hour}:{m.group(2)}" if m.group(2) else str(hour)


def say_context(percent: float | None, lang: str = "en") -> str:
    """How full a session's context is, for the voice."""
    if percent is None:
        return "Non so ancora quanto è pieno il contesto." if lang == "it" else "I don't know how full the context is yet."
    return f"Il contesto è al {percent:.0f} percento." if lang == "it" else f"The context is at {percent:.0f} percent."


def asked(text: str) -> tuple[str, str]:
    """What spoken words ask the hub rather than the session: (what, language), what being
    "usage" (the plan), "context" (how full the session's is) or "both"; ("", "") for words
    that are for the session."""
    if asks(text):
        return "usage", "en"
    if asks_context(text):
        return "context", "en"
    what = _asks_it(text)
    return (what, "it") if what else ("", "")


def asks_context(text: str) -> bool:
    """Whether these English words ask how full the session's context is: "how full is the
    context?", "what's the context at?". As strict as `asks`."""
    said = re.sub(r"['\u2019]", "", (text or "").lower())
    said = " ".join(re.sub(r"[^a-z0-9]+", " ", said).split())
    m = POLITE.match(said)
    said = said[m.end():] if m else said
    m = CAN_YOU.match(said)
    said = said[m.end():] if m else said
    words = said.split()
    if not words or len(words) > 12 or "context" not in words or not CONTEXT_WORDS.issuperset(words):
        return False
    return words[-1] not in OPEN_END and bool(ASKING_CONTEXT.match(said))


def _asks_it(text: str) -> str:
    """`asked` for Italian words: "quanto ho usato?", "quanto stai consumando?", "quant'è il
    contesto al momento?" (the author's own, 2026-11-19). Every word must be one such a
    question is made of, as in English."""
    said = unicodedata.normalize("NFKD", (text or "").lower())
    said = "".join(c for c in said if not unicodedata.combining(c))  # "è" is written "e"
    said = " ".join(re.sub(r"[^a-z0-9]+", " ", said).split())  # "quant'è" is "quant e"
    m = POLITE_IT.match(said)
    said = said[m.end():] if m else said
    words = said.split()
    if not words or len(words) > 16 or not WORDS_IT.issuperset(words) or words[-1] in OPEN_END_IT:
        return ""
    if not ASKING_IT.match(said) and not BARE_IT.issuperset(words):
        return ""
    plan, context = bool(TOPIC_IT.search(said)), "contesto" in words
    return "both" if plan and context else "usage" if plan else "context" if context else ""


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
# Fewer words than for the usage: "what is the context window of this model" is for the session.
CONTEXT_WORDS = frozenset("""
    context full fullness how hows much big what whats s is are the my our your this session current currently
    now right at in of percent percentage left remaining used so far still there it tell me give check""".split())
ASKING_CONTEXT = re.compile(r"(whats|what is|what s|hows|how is|how s|how much|how full|tell me|give me|check)\b")

# The same in Italian, with the accents taken off. "Uso" and "usato" alone are too common to
# name the plan, so they count only with the words around them all being of such a question.
TOPIC_IT = re.compile(r"\b(usage|consum\w*|utilizzo|uso|usat[oa]|usando|limit[ei]|(cinque|5) ore)\b")
ASKING_IT = re.compile(r"(quanto|quanta|quanti|quante|quant|come|com|a che punto|dimmi|fammi sapere|mi dici|"
                       r"qual|quale|che|quando|cosa|hai|ho|abbiamo|sei|siamo)\b")
BARE_IT = frozenset("usage consumi consumo utilizzo contesto il lo la i gli le mio miei mia piano per favore adesso ora".split())
WORDS_IT = BARE_IT | frozenset("""
    quanto quanta quanti quante quant come com a che punto dimmi fammi sapere mi dici qual quale cosa quando
    e il l lo la i gli le al allo alla ai agli alle del dello della dei degli delle di da in su per con
    ho hai ha abbiamo avete sto stai sta stiamo sei siamo sono si ci ne
    usato usata usati usando uso consumato consumata consumando consumi consumo consumare utilizzo usage
    limite limiti cinque 5 ore settimana settimanale piano abbonamento finestra contesto pieno piena
    momento adesso ora oggi finora ancora gia rimasto rimasta rimasti rimane resta restano manca mancano
    percentuale percento cento azzera azzerano resetta ricomincia riparte torna tornano totale
    claude fable opus sonnet haiku modello modelli tutto tutti""".split())
OPEN_END_IT = frozenset("di del della il la lo a al per e in su con".split())
POLITE_IT = re.compile(r"((hey|hi|ehi|ei|ok|okay|allora|senti|dai|e|beh|be|quindi|ma|claude|comunque|scusa|"
                       r"per favore|a proposito) )+")


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


class Turn(NamedTuple):
    output: int   # written by the model in this turn
    fresh: int    # read for it that had not been read before: new input and what was saved for later
    reused: int   # read again from what had been saved
    replies: int  # requests to the model

    def tokens(self, how: str = "new") -> int:
        """One figure for it: new = everything but what was read again (the default; the rest
        grows with the length of the conversation, not with the request) | output | all."""
        return _figure(self.output, self.fresh, self.reused, how)


def _figure(output: int, fresh: int, reused: int, how: str) -> int:
    return output if how == "output" else output + fresh + (reused if how == "all" else 0)


class Tally(NamedTuple):
    """What a whole session has used so far, read from its record a piece at a time (see tally)."""
    path: str = ""
    at: int = 0           # how much of the record has been read: up to the end of its last whole line
    output: int = 0       # as in Turn, over every reply
    fresh: int = 0
    reused: int = 0
    seconds: float = 0.0  # time the model and its tools were at work
    last: float | None = None  # when the last prompt, reply or tool result read was written (epoch seconds)
    reply: str = ""       # the reply the read ended in: its lines can go on in the next piece
    counts: tuple = (0, 0, 0)  # what that reply has been counted for so far

    def tokens(self, how: str = "new") -> int:
        return _figure(self.output, self.fresh, self.reused, how)


def tally(path: str, was: Tally | None = None) -> Tally | None:
    """What the session has used, `was` carried on with what was written to its record since;
    None if the record cannot be read. Tokens as in turn(). The time at work is the time before
    each reply and each tool result, counted from the line before it; the time before a prompt
    is the user's, and is left out. So it holds what Claude was busy with, a wait on a
    permission prompt included, and none of the time the session sat waiting for you. Helpers'
    replies are left out, as in turn()."""
    if not was or was.path != path:
        was = Tally(path)
    try:
        with open(path, "rb") as f:
            f.seek(was.at)
            data = f.read()
    except OSError:
        return None
    end = data.rfind(b"\n") + 1  # a line still being written is read next time
    _, _, output, fresh, reused, seconds, last, reply, counts = was
    for line in data[:end].decode("utf-8", "replace").splitlines():
        if '"assistant"' not in line and '"user"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain") or entry.get("type") not in ("user", "assistant"):
            continue
        try:
            when = datetime.datetime.fromisoformat(str(entry.get("timestamp"))).timestamp()
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content")
        work = entry["type"] == "assistant" or (
            isinstance(content, list) and any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content))
        if work and last is not None and when > last:
            seconds += when - last
        last = when
        if entry["type"] != "assistant" or not isinstance(message.get("usage"), dict):
            continue
        count = lambda key: message["usage"].get(key) if isinstance(message["usage"].get(key), int) else 0  # noqa: E731
        seen = (count("output_tokens"), count("input_tokens") + count("cache_creation_input_tokens"), count("cache_read_input_tokens"))
        key = str(message.get("id") or "")
        if key and key == reply:  # another line of the same reply: only what it adds
            new = tuple(map(max, seen, counts))
            added, counts = tuple(n - o for n, o in zip(new, counts)), new
        else:
            added, reply, counts = seen, key, seen
        output, fresh, reused = output + added[0], fresh + added[1], reused + added[2]
    return Tally(path, was.at + end, output, fresh, reused, seconds, last, reply, counts)


def turn(path: str, start: int | None = None, tail: int = 4_000_000) -> Turn | None:
    """What the session's last turn used, added up from the replies in its record; None with
    nothing to go on. `start`: how long the record was when the turn's prompt came, so
    everything after it is the turn. Without it (the hub started in the middle of the turn)
    the last `tail` bytes are searched for the last prompt. A reply is written as several
    lines that all carry its counts, so each is taken once; helpers' replies are left out."""
    try:
        size = os.path.getsize(path)
        known = start is not None and 0 <= start <= size
        with open(path, "rb") as f:
            f.seek(start if known else max(0, size - tail))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    replies: dict = {}
    for line in lines:
        if '"assistant"' not in line and '"user"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        if entry.get("type") == "user":
            content = message.get("content")
            answer = isinstance(content, list) and any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content)
            if not known and not answer:  # a prompt: the turn begins here
                replies = {}
            continue
        if entry.get("type") != "assistant" or not isinstance(message.get("usage"), dict):
            continue
        count = lambda key: message["usage"].get(key) if isinstance(message["usage"].get(key), int) else 0  # noqa: E731
        seen = (count("output_tokens"), count("input_tokens") + count("cache_creation_input_tokens"), count("cache_read_input_tokens"))
        before = replies.get(message.get("id") or len(replies), (0, 0, 0))
        replies[message.get("id") or len(replies)] = tuple(map(max, seen, before))
    if not replies:
        return None
    return Turn(*(sum(r[i] for r in replies.values()) for i in range(3)), len(replies))


def tokens_text(n: int) -> str:
    """A number of tokens for a small place: 640, 1.2k, 64k, 2.5M."""
    if n < 1000:
        return str(n)
    if n < 9950:
        return f"{n / 1000:.1f}k"
    if n < 999_500:
        return f"{n / 1000:.0f}k"
    return f"{n / 1_000_000:.1f}M"


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
