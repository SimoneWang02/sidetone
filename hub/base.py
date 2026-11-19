"""What the parts of the hub share: its settings, the small records it keeps (a request, a
follow-up on its way, a session asked to stop) and helpers that need no hub.
"""
from __future__ import annotations

import glob
import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

import overlay as overlay_mod
import terminal as terminal_mod
from state import COLORS, VOICE_POOL, speech_from_message


NEEDS_INPUT = ("permission_prompt", "elicitation_dialog")  # Notification types worth interrupting for
OWN_DIALOG = ("AskUserQuestion", "ExitPlanMode")  # tools whose prompt is a question, not a yes/no
MIN_SHOWN = 0.7  # a request must be on screen this long before a hotkey can answer it
TAP = 0.35  # a talk-key press shorter than this picks the next session instead of recording
CONFIRM_WINDOW = 20.0  # seconds a follow-up waits for its confirming tap before it is dropped
PROMPTING_MODES = ("", "default", "plan")  # permission modes in which Claude asks before acting


@dataclass
class Stopping:
    """A session that was asked to end its turn (see Hub._stop_turn)."""
    at: float
    busy: bool  # it has been seen in the middle of a turn since it was asked
    pressed: bool = False  # Escape was typed into its terminal through the editor: stopped at once


@dataclass
class Editor:
    """A window of the editor that waits to be asked for a key in one of its terminals (see
    vscode/extension.js): only the editor can type into them."""
    ttys: dict  # terminal -> the process id the editor knows that terminal by
    keys: list = field(default_factory=list)  # what it is asked for: {"pid": ..., "key": "escape"}
    wake: threading.Event = field(default_factory=threading.Event)
    shows: bool = False  # it can also bring a terminal to the front (the extension from 0.3.0 on says so)
    show: list = field(default_factory=list)  # the terminals it is asked to bring to the front, by process id
    clears: bool = False  # it can also type the command that clears a session's conversation (0.4.0 on)


EDITOR_WAIT = 25.0  # seconds an editor's request is held before it is sent back empty and asked again
CLEAR_WAIT = 1800.0  # seconds "clear the chat" said to a busy session waits for its turn to end
CLEAR_CONFIRM = 10.0  # seconds after /clear was typed by which Claude Code must have ended that conversation, or it counts as not cleared
EDITOR_GAP = 3.0  # seconds an editor counts as still there after a request of its ended: the next one is on its way
NEVER = float("-inf")  # "has not happened", for times on the clock that counts from the boot
RECOUNT = 1.5  # seconds after a turn ended until what it used is added up once more (its last reply may be written late)
STOP_WAIT = 20.0  # seconds a session that was asked to stop may take to show that it is in a turn at all
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")  # a session id that can be a file name


@dataclass
class Sent:
    """The follow-up that went out last: for a few seconds the cancel key takes it back."""
    session: str
    text: str
    at: float
    answer: bool = False  # it was given as the answer to a question, so it cannot be waiting


# What a session is told when words it already has are taken back. It reaches Claude through
# the listener like spoken words, so it is written as the user would say it.
TAKE_BACK = ("Ignore the last thing I said by voice: it was misheard or sent by mistake, and I took it back. "
             "Stop acting on it. If you already changed something because of it, tell me what in one line, "
             "and do not undo it unless I ask.")


@dataclass
class Aside:
    """A side question being answered by a throwaway copy of a session (see Hub._ask_aside)."""
    session: str
    text: str  # the words as they were heard, opening words and all
    proc: subprocess.Popen | None = None
    dropped: bool = False  # the cancel key, a newer side question, or the session ended
    lang: str = ""  # the language the words were heard in, which the answer is given in


# What the copy is asked. It has the whole conversation of the session in front of it, and
# that conversation asks for a speak tag in every reply, hence the words about the tag.
ASIDE_PROMPT = ("This is a side question from me, asked by voice while you work (transcribed by a local speech "
                "model, so a word may be slightly off). Answer it directly from what you already know in this "
                "conversation, in one or two short sentences of plain spoken English: it is read aloud, so no "
                "speak tag, no code, no paths, no symbols and no markdown. You cannot use tools here: if the "
                "answer would need reading a file, running a command or searching, say that it cannot be checked "
                "from a side question. Do not continue or change the task you were working on. ")
# Small words a spoken sentence may begin with before the opening of a side question: the
# author's first real one was "Oh, by the way, what time is it right now?" (2026-11-18), and
# with the "oh" it waited for the session like any other words.
# The Italian ones after them ("e comunque, che ore sono?", the author's own, 2026-11-19).
ASIDE_LEAD = ("oh|ah|so|hey|and|also|alright|all right|right|ok|okay|um|uh|well|yeah|actually|claude"
              "|e|allora|senti|ehi|beh|dai|quindi|ma")
# The name of a language a side question may be heard in, for telling the copy which to answer in.
LANGUAGE_NAMES = {"it": "Italian", "zh": "Chinese", "es": "Spanish", "fr": "French", "de": "German",
                  "pt": "Portuguese", "ja": "Japanese", "hi": "Hindi"}


def aside_prompt(question: str, lang: str = "") -> str:
    """What the copy is asked. It is told the day and the time, which it cannot look up (that
    first real question got "I can't read the clock from a side question"). `lang`: the
    language the question was heard in, which the answer is to be in ("" or "en": English)."""
    told = ASIDE_PROMPT.replace("plain spoken English", f"plain spoken {LANGUAGE_NAMES[lang]}") if lang in LANGUAGE_NAMES else ASIDE_PROMPT
    return told + time.strftime("Right now it is %A, %d %B %Y, %H:%M. ") + "The question: " + question
# Tools a copy on the session's own model may not use: it would have to ask, and nobody is there.
ASIDE_ASK = ["Bash", "Edit", "Write", "NotebookEdit", "Read", "Grep", "Glob", "WebFetch", "WebSearch", "Agent", "Skill", "mcp__*"]
# Variables that tie a new Claude Code process to the session whose hook started the hub.
OWN_SESSION = re.compile(r"CLAUDECODE\Z|CLAUDE_(PID|EFFORT)\Z|CLAUDE_CODE_(CHILD|MESSAGING|SESSION)_"
                         r"|CLAUDE_CODE_(SSE_PORT|ENTRYPOINT|EXECPATH)\Z")


# What Claude is told when its request is turned down because the user began to speak to it.
VOICE_AT_PROMPT = ("Not approved for now: the user is answering by voice with more details instead of a yes or a no. "
                   "Do not retry this or work around it; their message follows.")


@dataclass
class Pending:
    """A follow-up on screen, not sent yet."""
    session: str
    text: str
    confirm: bool  # True: wait for a tap of the talk key; False: goes out when the timer ends
    timer: threading.Timer | None = None
    lang: str = ""  # the language the speech model heard it in ("" when not known)


@dataclass
class Listener:
    """A session's background hook, waiting to carry a spoken follow-up into that session."""
    session: str
    released: bool = False  # a newer listener took over, or the session ended
    wake: threading.Event = field(default_factory=threading.Event)


@dataclass
class Request:
    """One permission prompt a session is showing, which the hub may answer on the user's behalf."""
    session: str
    tool: str
    tool_input: dict
    summary: str  # what is being asked, in a few words
    detail: str  # the exact command or path
    created: float = field(default_factory=time.monotonic)
    shown: float | None = None  # when it became the one the hotkeys act on
    confirmed: bool = False  # Claude Code told us the prompt is still waiting
    decision: str | None = None  # allow | deny | answer | None (answered elsewhere)
    questions: list = field(default_factory=list)  # for AskUserQuestion: the questions, each with options
    answers: dict = field(default_factory=dict)  # question text -> chosen option label
    message: str = ""  # with a deny: what Claude is told beside it (it reads this as the tool's output, not as the user)
    ticked: set = field(default_factory=set)  # a question with several choices to tick: those ticked so far, counted from 0
    shells: set | None = None  # the session's commands that were already running when it asked (None: not known)

    @property
    def question(self) -> dict | None:
        """The question the number keys answer next, if this is a question at all."""
        return self.questions[len(self.answers)] if len(self.answers) < len(self.questions) else None

    @property
    def place(self) -> str:
        """Where that question stands when the dialog has several ("1 of 2"), else nothing. The
        terminal goes on showing the first one until the last is answered, so we say it."""
        return f"{len(self.answers) + 1} of {len(self.questions)}" if len(self.questions) > 1 and self.question else ""
    done: threading.Event = field(default_factory=threading.Event)


@dataclass
class Config:
    run: str  # socket and lock
    state: str  # logs
    kokoro_dir: str = ""
    engine: str = "auto"  # auto | kokoro | say | spd-say | espeak-ng | null
    default_voice: str = "af_heart"
    speed: float = 1.1
    voices: dict = field(default_factory=dict)  # project name -> voice
    voice_pool: list = field(default_factory=lambda: list(VOICE_POOL))
    # The colors sessions' names are written in ("#RRGGBB"). A session that joins others gets
    # the one furthest from theirs, so a short list of very different colors serves best.
    colors: list = field(default_factory=lambda: list(COLORS))
    label: str = "auto"  # auto (several sessions and no overlay to show who talks) | always | never
    # Where a session's title comes from. "ask": each session is asked to name what it is working
    # on, in its speak tag, and may change that as the work moves on. "auto": never asked; the
    # title is Claude Code's own name for the session, else the start of its first spoken line.
    titles: str = "ask"
    # The language of the spoken line. "spoken": the one you wrote or spoke in; a line that is not
    # English carries lang="it" (or another code) in its tag and is said by a voice of that
    # language. "english": always English, as before (the hook then asks for that).
    reply_language: str = "spoken"
    # A voice per language for those lines, such as {"it": "if_sara"}; else tts.PREFERRED_VOICE,
    # else a Kokoro voice of that language picked per session.
    language_voices: dict = field(default_factory=dict)
    # What a quick tap of the talk key does (a press too short to be speech). "none": nothing,
    # the focus is moved with the arrow keys or the wheel. "next": the focus goes to the next
    # session, as it did before those keys existed.
    talk_tap: str = "none"
    # A session that starts to speak takes the focus. When the talk key goes down within this
    # many seconds of that, you cannot have meant the new speaker: nobody reacts that fast. The
    # words then go to the session that had the focus before. 0 = the key always goes to
    # whoever has the focus in that instant.
    focus_reach_back: float = 1.0
    # A prompt typed to a session gives it the focus: you are there, so what you say next is
    # meant for it. It covers what the editor cannot report (going back into the terminal
    # you were in last, a terminal outside the editor). False: only the keys, the wheel,
    # the terminal in front and whoever speaks move the focus.
    focus_on_prompt: bool = True
    repeat: str = "focus"  # what the repeat key says again: the last line of the session in focus | "last" (anyone's)
    max_age: float = 60.0  # seconds a line may wait before it is dropped
    idle_exit: float = 1800.0  # seconds with no sessions before the hub exits; 0 = never
    # Claude Code sends a notification once a permission prompt has waited about 6 s. A request
    # with no such notification after this long was answered in the terminal.
    permission_grace: float = 9.0
    whisper_model: str = "small.en"
    mic_source: str = ""  # PulseAudio source for push-to-talk; empty = the default microphone
    followup_delay: float = 0.0  # seconds a transcript is shown (and can be cancelled) before it is sent; 0 = at once
    talk_tail: float = 0.4  # seconds to keep recording after the talk key is released
    unsend_seconds: float = 4.0  # how long after sending the cancel key still takes the words back; 0 = never
    # What the cancel key stops besides a recording and a line being spoken: "always" = words
    # just taken back from a session that already has them end its turn, and with nothing else
    # to cancel the key ends the turn of the session in focus | "sent" = only the first |
    # "never" = neither; a session that already has the words is told to ignore them
    cancel_stops: str = "always"
    # Asking for the plan's usage by voice ("what's my usage", "how much of the five hours have
    # I used"): the hub answers aloud, the five-hour window first, and the words do not go to
    # a session. False: such words are a session's like any others.
    usage_by_voice: bool = True
    # "Clear the chat" by voice (the author, 2026-11-19: "is it possible to say like, hey,
    # Claude, clear the chat and you use the command slash clear"). No session can run
    # /clear itself, it has to be typed, and only the editor can type into its terminals
    # (see vscode/extension.js). Spoken words that are one of `clear_words` and nothing else,
    # but for a greeting before and a "please" after, are not handed to the session: its
    # editor types /clear into its terminal. Only for a session that is at its prompt, since
    # the Enter that goes with it would answer a dialog that is open. False: such words are
    # a session's like any others.
    clear_by_voice: bool = True
    clear_words: list = field(default_factory=lambda: [
        "clear the chat", "clear the context", "clear the conversation", "clear the session", "clear the history",
        "slash clear", "run slash clear", "do a slash clear", "use slash clear",
        "clear the shot"])  # how the speech model wrote "chat" once (2026-11-19)
    # The plan's usage at the foot of the card of figures in the overlay: the five-hour window
    # and the week, each a thin bar and its percent (the author's idea, 2026-11-17: "bar that
    # shows the usage, the five-hour window and the weekly usage"). Read with the same call
    # as for the voice, every `usage_every` seconds while a session is open and the overlay
    # is up (about a second each time, no request to a model). From `usage_warn` percent on
    # a bar is drawn in the warning color.
    usage_shown: bool = True
    usage_every: float = 300.0
    usage_warn: float = 80.0
    # The week of one model, where the plan counts it apart ("Fable 89%"), as a bar after those
    # two: none | all | near = only from `usage_warn` on. Off unless asked for: the author did
    # not want it, since such a limit comes and goes with the plans.
    usage_models: str = "none"
    # How full each session's context is, counted from its transcript, and where it shows:
    # arc = a thin arc around the session's light, filling clockwise from the top (the author,
    # 2026-11-18, found the words too long beside the running time and chose the arc of three
    # ideas) | text = "context 56%" at the end of its row of the details | both | off.
    # true and false, from when it was only the text, mean arc and off.
    # `context_window`: the size it is held against, in tokens (the transcript does not say
    # it; one million for the models measured).
    context_shown: str | bool = "arc"
    context_window: int = 1_000_000
    # What a turn used in tokens, at the right end of the session's row once the turn has
    # ended ("64k tokens"), until its next prompt (the author, 2026-11-18: "for each reply,
    # display the metrics, the token you've used"). new = what the model wrote plus what it
    # read for the first time, the default: what it reads again at every step of a long
    # conversation would make every figure millions | output = only what it wrote |
    # all = with what was read again | off.
    turn_tokens: str | bool = "new"
    # A word after that figure: "" = the bare number, "64k" (the author on seeing "64k tokens":
    # the label is good, but "just putting the number is better", it takes room from the
    # words of the row) | "tokens" = as it was at first, or any word of your own.
    turn_tokens_label: str = ""
    # The same figure at the right end of each line in the history under the rows: there it
    # stays, where the row loses it at the next prompt (the author asked for it "as well in
    # history", and then for the end of the message, not right after its time).
    turn_tokens_history: bool = True
    # How long ago each line of the history was said ("3m"), before its tokens. Off: asked
    # what the history could give up to make room, the author kept the tokens ("pretty
    # cool") and doubted the time ("I don't know how useful it is"); the lines are in order,
    # newest first, which says most of it.
    history_time: bool = False
    # A white dot on the mark of a history line that was never heard to its end (cut off,
    # too old, replaced). Off since the author, 2026-11-19: "I don't like the tick with the
    # white ball on top right ... don't use the white ball."
    history_missed: bool = False
    # Where a session's figures go (the author, 2026-11-18, with tasks, time, context, tokens
    # and waiting messages all wanting the right end of a row: "revamp a bit the design ...
    # to have space for them", and chose a line of their own under the rows). `row_metrics`:
    # what the right end of each row says, as bare figures. `detail_metrics`: what is said
    # under the rows about the session the mouse is on (else the one in focus), each with
    # its name; [] = nothing. How that looks is the overlay's `details_style`. Both are
    # lists of: tasks (done/all of its task list), time (how long the turn has run, or the
    # last one ran), context, tokens (what the turn has used, or the last one did), waiting
    # (messages of yours held for it).
    row_metrics: list = field(default_factory=lambda: ["time"])
    detail_metrics: list = field(default_factory=lambda: ["context", "tokens", "time", "tasks"])
    # What stands between the parts of a line the hub writes for the overlay (tasks and time
    # in a row, the keys under a request): "" = only a gap (the author, 2026-11-18: "don't
    # use the dots, the central dots. I don't like them") | a sign of your own, "\u00b7" for
    # the raised dot it was.
    separator: str = ""
    # "2 messages waiting" in words at the end of a session's row. Off since the author said
    # of it "I don't care", the number on the light says it already.
    waiting_words: bool = False
    # Stopping at once: where the session runs in a terminal of an editor with the Sidetone
    # extension, Escape is typed into that terminal, which ends the turn in the same moment.
    # False: only by the hook, at the session's next step (which is also what happens anywhere else).
    stop_at_once: bool = True
    # Words spoken to a session that waits at a permission prompt: "details" = they are neither
    # a yes nor a no but more to go on: the request is turned down for now, the turn is ended
    # and the words are the session's next message, so it goes on from them (the terminal's
    # "No, and tell Claude what to do differently") | "wait" = they wait until the prompt is
    # answered some other way
    voice_at_prompt: str = "details"
    # Ask for a confirming tap before sending a spoken follow-up: False (the default; it is sent
    # after followup_delay unless cancelled), True, or "auto" (only for sessions that would act
    # on it without asking, i.e. not in default or plan mode).
    followup_confirm: bool | str = False
    # Side questions. Spoken words that open with one of `aside_words` do not wait for a busy
    # session: a throwaway copy of that session answers them at once from what the session
    # knows, without tools, and the answer is said in the session's voice. The session itself
    # never sees the question or the answer. `aside`: "busy" = only while the session is in
    # the middle of a turn (an idle one gets the words as usual and can act on them) |
    # "always" | "off". `aside_model`: "session" = the copy runs on the session's own model with
    # the session's own tools, which lets it reuse the conversation the session has saved, as
    # Claude Code's `/btw` does (asking is then refused for every tool that acts) | a model's
    # name such as "haiku" = that model reads the whole conversation anew, with no tools at
    # all. If no answer comes within `aside_timeout` seconds, the words go to the session
    # after all. `aside_claude`: the Claude Code program; "" = the one on the PATH.
    aside: str = "busy"
    aside_words: list = field(default_factory=lambda: ["by the way", "btw", "comunque", "a proposito",
                                                       "顺便问一下", "顺便问下", "顺便说一下"])
    aside_model: str = "session"
    aside_timeout: float = 60.0
    aside_claude: str = ""
    projects_dir: str = os.path.expanduser("~/.claude/projects")  # Claude Code's records of each session
    # How the hub answers a spoken follow-up, and an answer given with the keys: "sound" (a short sound the moment it goes out, a
    # different one when it has to wait for a busy session or was not sent), "voice" ("Sent."
    # in the session's voice, which waits its turn behind a line being spoken) or "none".
    # Without a way to play sounds, "sound" falls back to the voice.
    talk_feedback: str = "sound"
    sound_volume: float = 0.3  # 0 to 1
    whisper_language: str = "en"  # for multilingual models such as "small": "it", "en,it" (the ones you speak), or "auto"
    whisper_unload_minutes: float = 10  # free the speech model's memory after this long unused; 0 = keep
    sessions_dir: str = os.path.expanduser("~/.claude/sessions")  # Claude Code's own session files
    config_path: str = ""  # the user's config.json; overlay placement chosen by dragging is saved there
    voices_dir: str = os.path.expanduser("~/.local/share/sidetone/voices")  # the user's own voices
    progress: bool = True  # say "3 of 5 steps done" during long turns
    progress_after: float = 45.0  # only in turns that have already run this many seconds
    progress_interval: float = 60.0  # and at most this often per session
    overlay: dict = field(default_factory=lambda: {**overlay_mod.DEFAULTS, "hotkeys": dict(overlay_mod.DEFAULTS["hotkeys"])})
    # How each session's own terminal is marked (see terminal.py): tint, strength, background, pulse, title.
    terminal: dict = field(default_factory=lambda: dict(terminal_mod.DEFAULTS))
    mute_file: str = os.path.expanduser("~/.claude/voice-off")

    @property
    def sock(self) -> str:
        return os.path.join(self.run, "hub.sock")

    @classmethod
    def load(cls) -> "Config":
        env, home = os.environ, os.path.expanduser("~")
        run = env.get("CS_RUN") or (
            os.path.join(env["XDG_RUNTIME_DIR"], "sidetone")
            if env.get("XDG_RUNTIME_DIR") else f"/tmp/sidetone-{os.getuid()}")
        cfg = cls(
            run=run,
            state=env.get("CS_STATE") or os.path.join(
                env.get("XDG_STATE_HOME") or f"{home}/.local/state", "sidetone"),
            kokoro_dir=env.get("KOKORO_DIR") or f"{home}/.local/share/kokoro",
            engine=env.get("SIDETONE_TTS", "auto"),
            default_voice=env.get("KOKORO_VOICE", "af_heart"),
            speed=float(env.get("KOKORO_SPEED", "1.1")),
        )
        path = cfg.config_path = os.path.join(env.get("XDG_CONFIG_HOME") or f"{home}/.config",
                                              "sidetone", "config.json")
        try:
            with open(path) as f:
                user = json.load(f)
        except FileNotFoundError:
            user = {}
        for key in ("voices", "voice_pool", "colors", "label", "max_age", "idle_exit", "default_voice", "speed",
                    "permission_grace", "whisper_model", "mic_source", "followup_delay", "talk_tail", "unsend_seconds", "cancel_stops", "stop_at_once", "voice_at_prompt", "usage_by_voice", "clear_by_voice", "clear_words", "usage_shown", "usage_every", "usage_warn", "usage_models", "context_shown", "context_window", "turn_tokens", "turn_tokens_label", "turn_tokens_history", "history_time", "history_missed", "separator", "waiting_words", "row_metrics", "detail_metrics",
                    "followup_confirm", "whisper_language", "whisper_unload_minutes", "repeat", "talk_tap", "focus_reach_back", "focus_on_prompt", "titles", "reply_language", "language_voices",
                    "talk_feedback", "sound_volume", "aside", "aside_words", "aside_model", "aside_timeout", "aside_claude", "projects_dir",
                    "progress", "progress_after", "progress_interval"):
            if key in user:
                setattr(cfg, key, user[key])
        wanted = user.get("overlay") or {}
        cfg.overlay.update({k: v for k, v in wanted.items() if k != "hotkeys"})
        cfg.overlay["hotkeys"].update(wanted.get("hotkeys") or {})
        if env.get("SIDETONE_OVERLAY") == "off":
            cfg.overlay["enabled"] = False
        cfg.terminal.update(user.get("terminal") or {})
        if env.get("SIDETONE_TERMINAL") == "off":  # write to no terminal at all
            cfg.terminal.update(tint="off", pulse=False, title=False)
        return cfg




def _runs(shell: str, command: str) -> bool:
    """Is this shell of the Bash tool running that command? Its command line holds the command
    in single quotes, so a command is known by its start, up to its first quote. Two commands
    of one session can start at the same moment (a helper of the session runs its own), and
    only the one that was asked about says the question is answered."""
    start = command.split("'")[0].strip()[:60]
    return start in shell if len(start) >= 6 else True


def _spoken_name(name: str) -> str:
    """A session's name as it is said aloud: "api-server" becomes "api server"."""
    return re.sub(r"[-_.]+", " ", name).strip()


KEPT_LINES = 40  # how many of the last lines said are kept across a restart
BUSY = ("working", "needs_you")  # states of a session in the middle of a turn
# Speech kind -> overlay glyph. None: the session's own state (a side answer comes while it works on).
FLASH_LOOK = {"allowed": "done", "denied": "failed", "progress": "working", "aside": None}
NUMBER_WORDS = ("One", "Two", "Three", "Four")


CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")


def aside_question(text: str, words: list) -> str:
    """The question in spoken words that open with one of `words` ("By the way, where is it?"
    gives "where is it?"), or "" when they do not, or nothing follows."""
    for opening in sorted((w for w in words if isinstance(w, str) and w.strip()), key=len, reverse=True):
        spaced = r"\s+".join(map(re.escape, opening.split()))
        end = "" if CJK.match(opening.strip()[-1]) else r"\b"  # Chinese is written without spaces between words
        m = re.match(rf"\W*(?:(?:{ASIDE_LEAD})\W+)*{spaced}{end}\W*(\w.*)", text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return ""


# What may stand before and after the words that clear a conversation. The speech model
# writes "Claude" as "cloud" as often as not.
CLEAR_LEAD = re.compile(r"((hey|hi|hello|ok|okay|alright|all right|right|yeah|yes|sure|oh|so|um|uh|well|and|also|then|now|"
                        r"claude|cloud|please|just|quickly|can you|could you|would you|will you|lets|i want to|i want you to|"
                        r"ill|i will|id like to|i would like to) )+")  # "I'll": how "alright" came through once
CLEAR_TAIL = re.compile(r"( (please|now|for me|thanks|thank you|claude|cloud|again))+$")
CLEAR_SMALL = re.compile(r"\b(the|this|that|your|my|our|a|whole|entire|current)\b")


def asks_to_clear(text: str, words: list) -> bool:
    """Whether these spoken words are the order to clear the conversation: one of `words`,
    with nothing before it but a greeting and nothing after it but a "please". Small words
    count for nothing ("clear chat", "clear this chat", "clear your context"). Anything
    more is a sentence for the session ("clear the chat history file from the repo")."""
    def plain(said: str) -> str:
        said = re.sub(r"['\u2019]", "", str(said or "").lower())
        said = " ".join(re.sub(r"[^\w]+", " ", said.replace("/", " slash ")).split())
        return " ".join(CLEAR_SMALL.sub(" ", said).split())
    said = plain(text)
    m = CLEAR_LEAD.match(said)
    said = said[m.end():] if m else said
    said = CLEAR_TAIL.sub("", said)
    return bool(said) and said in {plain(w) for w in words if isinstance(w, str)} - {""}


def session_model(projects_dir: str, sid: str) -> tuple[str, str]:
    """The model and effort a session last answered with, read from the end of Claude Code's
    record of it; "" for what cannot be found. The model can change in the middle of a
    session, so it is looked up each time."""
    for path in glob.glob(os.path.join(glob.escape(projects_dir), "*", glob.escape(sid) + ".jsonl")):
        try:
            with open(path, "rb") as f:
                f.seek(max(0, os.path.getsize(path) - 1_000_000))
                lines = f.read().decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"assistant"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:  # the first line of the part that was read is cut
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
                continue
            message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            model, effort = message.get("model"), entry.get("effort")
            if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\[\]-]*", model):
                return model, effort if isinstance(effort, str) and re.fullmatch(r"[a-z]+", effort) else ""
    return "", ""


def spoken_answer(reply: str, limit: int = 500) -> str:
    """A side answer as it is said aloud: the speak line if the copy wrote one after all, no
    markup, and no more than a few sentences."""
    text = speech_from_message(reply) or re.sub(r"</?speak[^>]*>", " ", reply)
    text = re.sub(r"\s+", " ", re.sub(r"[`*#_]+", "", text)).strip()
    if len(text) > limit:
        cut = text[:limit]
        text = cut[:max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! ")) + 1] or cut.rsplit(" ", 1)[0] + "\u2026"
    return text


def _end(proc: subprocess.Popen) -> None:
    """End a process we started in a group of its own, with whatever it started."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def _same_call(tool: str, asked: dict, ran: dict) -> bool:
    """Is the tool call that ran the one a prompt was open for? A question answered in the
    terminal comes back with the answers added to it, so only its questions are compared."""
    if tool == "AskUserQuestion":
        return asked.get("questions") == ran.get("questions")
    return asked == ran


def _answerable(tool_input: dict) -> list:
    """The questions of an AskUserQuestion call if the number keys can answer all of them:
    two to four options each, one to choose or several to tick. Otherwise an empty list."""
    questions = tool_input.get("questions")
    if not isinstance(questions, list) or not questions:
        return []
    for q in questions:
        options = q.get("options") if isinstance(q, dict) else None
        if (not isinstance(options, list) or not 2 <= len(options) <= 4
                or not q.get("question") or not all(isinstance(o, dict) and o.get("label") for o in options)):
            return []
    return questions


def _read_out(question: dict, place: str = "") -> str:
    options = " ".join(f"{NUMBER_WORDS[i]}: {o['label']}." for i, o in enumerate(question["options"]))
    return f"Question{' ' + place if place else ''}: {question['question']} {options}" + (" Tick any, then confirm." if question.get("multiSelect") else "")


def _ago(seconds: float) -> str:
    return "now" if seconds < 60 else _elapsed(seconds)


def gap(cfg: Config, wide: bool = False) -> str:
    """What goes between two parts of a line (see Config.separator); `wide` for a line of keys."""
    sign = str(cfg.separator or "").strip()
    if sign:
        return f"  {sign}  " if wide else f" {sign} "
    return "    " if wide else "   "


def context_mode(cfg: Config) -> str:
    """Where a session's context shows: arc, text, both or off (see Config.context_shown)."""
    wanted = cfg.context_shown
    if wanted is False or wanted in ("off", "none", "never"):
        return "off"
    return wanted if wanted in ("text", "both") else "arc"


def _elapsed(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "<1m"
    return f"{minutes}m" if minutes < 60 else f"{minutes // 60}h{minutes % 60:02d}"


def log(cfg: Config, name: str, line: str) -> None:
    try:
        with open(os.path.join(cfg.state, name), "a") as f:
            f.write(f"{time.strftime('%F %T')} {line}\n")
    except OSError:
        pass


# --- HTTP over the Unix socket -----------------------------------------------------------------
