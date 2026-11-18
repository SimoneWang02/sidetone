#!/usr/bin/env python3
"""claude-speaks hub: the one local process every Claude Code hook reports to.

It keeps the voice loaded, speaks sessions one at a time, and tracks what each session is
doing. It listens on a Unix socket only, so nothing outside this user account can make it
speak. The client side is hooks/lib.sh.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import select
import signal
import socket
import socketserver
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # run with -I, so add our own dir
import collections  # noqa: E402

import claude_sessions  # noqa: E402
import demo  # noqa: E402
import overlay as overlay_mod  # noqa: E402
import sounds as sounds_mod  # noqa: E402
import stale  # noqa: E402
import stt  # noqa: E402
import terminal as terminal_mod  # noqa: E402
from state import (FORGET_AFTER, VOICE_POOL, Sessions, describe, permission_summary, short_title,  # noqa: E402
                   speech_from_message, split_display, title_from_message)
from tts import Meter, NullEngine, SpeechQueue, Utterance, make_engine  # noqa: E402

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
class Pending:
    """A follow-up on screen, not sent yet."""
    session: str
    text: str
    confirm: bool  # True: wait for a tap of the talk key; False: goes out when the timer ends
    timer: threading.Timer | None = None


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

    @property
    def question(self) -> dict | None:
        """The question the number keys answer next, if this is a question at all."""
        return self.questions[len(self.answers)] if len(self.answers) < len(self.questions) else None
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
    label: str = "auto"  # auto (several sessions and no overlay to show who talks) | always | never
    # Where a session's title comes from. "ask": each session is asked to name what it is working
    # on, in its speak tag, and may change that as the work moves on. "auto": never asked; the
    # title is Claude Code's own name for the session, else the start of its first spoken line.
    titles: str = "ask"
    # What a quick tap of the talk key does (a press too short to be speech). "none": nothing,
    # the focus is moved with the arrow keys or the wheel. "next": the focus goes to the next
    # session, as it did before those keys existed.
    talk_tap: str = "none"
    # A session that starts to speak takes the focus. When the talk key goes down within this
    # many seconds of that, you cannot have meant the new speaker: nobody reacts that fast. The
    # words then go to the session that had the focus before. 0 = the key always goes to
    # whoever has the focus in that instant.
    focus_reach_back: float = 1.0
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
    # Ask for a confirming tap before sending a spoken follow-up: False (the default; it is sent
    # after followup_delay unless cancelled), True, or "auto" (only for sessions that would act
    # on it without asking, i.e. not in default or plan mode).
    followup_confirm: bool | str = False
    # How the hub answers a spoken follow-up: "sound" (a short sound the moment it goes out, a
    # different one when it has to wait for a busy session or was not sent), "voice" ("Sent."
    # in the session's voice, which waits its turn behind a line being spoken) or "none".
    # Without a way to play sounds, "sound" falls back to the voice.
    talk_feedback: str = "sound"
    sound_volume: float = 0.3  # 0 to 1
    whisper_language: str = "en"  # for multilingual models such as "small": "it", "en,it" (the ones you speak), or "auto"
    whisper_unload_minutes: float = 10  # free the speech model's memory after this long unused; 0 = keep
    sessions_dir: str = os.path.expanduser("~/.claude/sessions")  # Claude Code's own session files
    config_path: str = ""  # the user's config.json; overlay placement chosen by dragging is saved there
    voices_dir: str = os.path.expanduser("~/.local/share/claude-speaks/voices")  # the user's own voices
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
            os.path.join(env["XDG_RUNTIME_DIR"], "claude-speaks")
            if env.get("XDG_RUNTIME_DIR") else f"/tmp/claude-speaks-{os.getuid()}")
        cfg = cls(
            run=run,
            state=env.get("CS_STATE") or os.path.join(
                env.get("XDG_STATE_HOME") or f"{home}/.local/state", "claude-speaks"),
            kokoro_dir=env.get("KOKORO_DIR") or f"{home}/.local/share/kokoro",
            engine=env.get("CLAUDE_SPEAKS_TTS", "auto"),
            default_voice=env.get("KOKORO_VOICE", "af_heart"),
            speed=float(env.get("KOKORO_SPEED", "1.1")),
        )
        path = cfg.config_path = os.path.join(env.get("XDG_CONFIG_HOME") or f"{home}/.config",
                                              "claude-speaks", "config.json")
        try:
            with open(path) as f:
                user = json.load(f)
        except FileNotFoundError:
            user = {}
        for key in ("voices", "voice_pool", "label", "max_age", "idle_exit", "default_voice", "speed",
                    "permission_grace", "whisper_model", "mic_source", "followup_delay", "talk_tail", "unsend_seconds", "cancel_stops",
                    "followup_confirm", "whisper_language", "whisper_unload_minutes", "repeat", "talk_tap", "focus_reach_back", "titles",
                    "talk_feedback", "sound_volume",
                    "progress", "progress_after", "progress_interval"):
            if key in user:
                setattr(cfg, key, user[key])
        wanted = user.get("overlay") or {}
        cfg.overlay.update({k: v for k, v in wanted.items() if k != "hotkeys"})
        cfg.overlay["hotkeys"].update(wanted.get("hotkeys") or {})
        if env.get("CLAUDE_SPEAKS_OVERLAY") == "off":
            cfg.overlay["enabled"] = False
        cfg.terminal.update(user.get("terminal") or {})
        if env.get("CLAUDE_SPEAKS_TERMINAL") == "off":  # write to no terminal at all
            cfg.terminal.update(tint="off", pulse=False, title=False)
        return cfg


class Hub:
    def __init__(self, cfg: Config, engine):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.sessions = Sessions(cfg.voice_pool, cfg.voices, os.path.join(cfg.state, "voices.json"))
        self.last_event = time.monotonic()
        self.overlay = None  # anything with send(dict); set by main() or the tests
        self.terminals = terminal_mod.Terminals(cfg.terminal)  # marks each session's own terminal
        self._shown: dict | None = None  # last state sent to the overlay, to skip repeats
        self.requests: list[Request] = []  # open permission prompts, oldest first
        self.recorder = None  # stt.Recorder, set by main() or the tests
        self.transcriber = None  # stt.Transcriber
        self.sounds = None  # sounds.Sounds, set by main() or the tests
        self.listeners: dict[str, Listener] = {}  # session id -> its waiting hook
        # session id -> text not yet picked up. Kept on disk too (in the run folder, owner-only),
        # so what was said to a busy session is not lost when the hub restarts.
        self.followups: dict[str, list[str]] = self._kept_followups()
        # Sessions whose words could not be handed over yet (busy, or no listener): their light
        # carries a mark until they are.
        self._waiting: set[str] = set(self.followups)
        self._stopping: dict[str, Stopping] = {}  # sessions asked to end their turn, until they have
        self._clear_stops()  # what a hub before this one asked for is not wanted any more
        self.talk_target: str | None = None  # session a spoken follow-up goes to
        self._kept_sessions: dict | None = None  # what sessions.json last said (see _keep_sessions)
        self._front = ""  # the terminal the editor last said you were in (see terminal_in_front)
        self.history: collections.deque = collections.deque(maxlen=100)  # lines sessions said, newest last
        self._restore_sessions()
        self._talk_shown: tuple | None = None  # what the overlay shows for push-to-talk while it can still change session
        self._mic_meter = Meter()  # turns microphone audio into a loudness for the overlay
        self._talking: float | None = None  # when the talk key went down
        self._transcribing = False  # the key is up and the words are not out of the speech model yet
        self._heard: object | None = None  # that recording; the cancel key clears it, and its words are dropped
        self._pending: Pending | None = None  # the follow-up being shown
        self._sent: Sent | None = None  # the one that went out last, while it can still be taken back
        self._unload: threading.Timer | None = None  # frees the speech model after a quiet while
        self.last_seen = time.time()  # last sign the user was there: a prompt, a hotkey, a catch-up
        self._focus_lost: tuple[str, float] = ("", 0.0)  # the session a speaker last took the focus from, and when
        self._progress_said: dict[str, float] = {}  # session id -> when it last announced progress
        self._keys: list | None = None  # hotkeys the overlay was last told to claim
        self.speech = SpeechQueue(engine, max_age=cfg.max_age, label_for=self._label_for,
                                  on_change=self._speech_changed, on_done=self._log_speech,
                                  on_audio=self._voice_levels)

    # --- hook events -------------------------------------------------------------------------

    def on_event(self, ev: dict) -> None:
        """Update a session from any hook payload other than MessageDisplay."""
        if ev.get("session_id"):
            self._apply(ev)
            self.publish()

    def _apply(self, ev: dict) -> None:
        sid, event = ev["session_id"], ev.get("hook_event_name", "")
        with self.lock:
            self.last_event = time.monotonic()
            if event == "SessionEnd":
                self._forget(sid, "session ended")
                return
            s = self.sessions.touch(sid, ev.get("cwd", ""))
            s.permission_mode = str(ev.get("permission_mode") or s.permission_mode)
            if event in ("PostToolUse", "PostToolUseFailure"):  # that tool ran: its prompt was answered
                self._settle(sid, "answered in the terminal", ev.get("tool_name"), ev.get("tool_input"))
            elif event in ("UserPromptSubmit", "Stop", "StopFailure"):
                self._settle(sid, "turn moved on")

            if event == "UserPromptSubmit":
                self.last_seen = time.time()
                prompt = str(ev.get("prompt") or "")
                self._title_from(s, prompt=prompt)
                s.state, s.activity, s.note = "working", "Thinking", ""
                s.turn_started, s.spoken = time.monotonic(), None
                if s.tasks and all(s.tasks.values()):
                    s.tasks.clear()
                if not prompt.lstrip().startswith("<"):
                    # You typed: you have moved on and the old line is stale. A voice follow-up
                    # arrives as markup, often while you have not heard the reply yet, so that
                    # reply stays in the queue and is spoken in full.
                    self.speech.drop_session(sid)
                    self._unstop(sid, "a new prompt was typed")  # that is a new turn: it must run
            elif event == "PreToolUse":
                s.state, s.activity = "working", describe(ev.get("tool_name", ""), ev.get("tool_input") or {})
            elif event in ("PostToolUse", "PostToolUseFailure"):
                if ev.get("is_interrupt"):  # you pressed Esc; no Stop event will follow
                    s.state, s.activity, s.note, s.turn_started = "idle", "", "interrupted", None
                else:
                    s.state, s.activity = "working", "Thinking"
            elif event == "TaskCreated":
                s.tasks.setdefault(ev.get("task_id", ""), False)
            elif event == "TaskCompleted":
                s.tasks[ev.get("task_id", "")] = True
                self._maybe_say_progress(s)
            elif event == "Notification":
                if ev.get("notification_type") in NEEDS_INPUT:
                    waiting = [r for r in self.requests if r.session == sid and not r.confirmed]
                    if waiting:  # we know what it is asking for, so say that
                        waiting[0].confirmed = True
                        if waiting[0].question:
                            self._say(s, _read_out(waiting[0].question), "needs_you", "question")
                        else:
                            self._say(s, f"Permission needed: {waiting[0].summary}", "needs_you", "permission")
                    else:
                        s.state, s.note = "needs_you", "needs your input"
                        self._say(s, "I need your input", "needs_you", "notify")
            elif event == "Stop":
                s.state, s.activity, s.turn_started = "done", "", None
                message = str(ev.get("last_assistant_message") or "")
                speech = speech_from_message(message)
                s.note = speech or "done"
                self._title_from(s, reply=speech, given=title_from_message(message))
                if speech and speech != s.spoken and not self._spoken_without_hub(sid, speech):
                    self._say(s, speech, "done", "stop")
                elif not speech:
                    self._flash(s, "done")  # nothing is spoken for this turn, so show it instead
                self._unstop(sid, "its turn ended by itself")
                s.spoken = None
            elif event == "StopFailure":
                s.state, s.activity, s.turn_started = "failed", "", None
                error = str(ev.get("error") or "unknown").replace("_", " ")
                s.note = f"error: {error}"
                self._say(s, f"I hit an error: {error}", "failed", "stop-failure")

    def _forget(self, sid: str, why: str) -> None:
        self._settle(sid, why)
        self._release(sid)
        self.followups.pop(sid, None)
        self._waiting.discard(sid)
        self._unstop(sid)
        self._keep_followups()
        if self.talk_target == sid:
            self.talk_target = None
        self.sessions.remove(sid)
        self.speech.drop_session(sid)

    # --- who is who, across a restart ---------------------------------------------------------

    def _sessions_file(self) -> str:
        return os.path.join(self.cfg.run, "sessions.json")

    def _restore_sessions(self) -> None:
        """Bring back the sessions an earlier hub knew, each with its own name, color, voice,
        title and place in the bar.

        Those are handed out in the order sessions turn up, and after a restart they turn up in
        another order, so sessions of the same project swapped them (the author, 2026-11-17: "the
        colors, like their status, might have influenced each other"). A session Claude Code
        still lists is back at once, working if it is busy there. One that had a session file
        and has none now ended meanwhile. The rest get theirs back when they next report.
        """
        try:
            path = self._sessions_file()
            if time.time() - os.path.getmtime(path) > FORGET_AFTER:
                return
            with open(path) as f:
                kept = json.load(f)
            self.sessions.keep(kept.get("sessions"))
        except (OSError, ValueError, AttributeError):
            return
        colors = {sid: was["color"] for sid, was in self.sessions.kept.items()}  # as they are now
        for e in kept.get("history") or []:  # what was said before the restart, for repeat and the history
            if (isinstance(e, dict) and isinstance(e.get("time"), (int, float))
                    and all(isinstance(e.get(k), str) for k in ("session", "name", "spoken_name", "voice", "text", "kind"))):
                self.history.append({**e, "color": colors.get(e["session"]) or str(e.get("color") or ""),
                                     "heard": bool(e.get("heard"))})
        live = claude_sessions.read(self.cfg.sessions_dir)
        can_tell = os.path.isdir(self.cfg.sessions_dir)
        for sid, was in list(self.sessions.kept.items()):
            info = live.get(sid)
            if info:
                s = self.sessions.touch(sid, was["cwd"])
                s.seen_file = True
                if info["status"] == "busy":
                    s.state, s.activity, s.note = "working", "Thinking", ""
                    if info["status_at"]:  # it became busy when its turn began
                        s.turn_started = time.monotonic() - max(0.0, time.time() - info["status_at"])
            elif was["seen_file"] and can_tell:
                del self.sessions.kept[sid]
        focus = kept.get("focus")
        if isinstance(focus, str) and focus in self.sessions.by_id:
            self.talk_target = focus
        log(self.cfg, "hub.log", f"sessions from before the restart: {len(self.sessions.by_id)} back, "
                                 f"{len(self.sessions.kept)} expected")

    def _keep_sessions(self) -> None:
        """Write down who is who whenever that changed (owner-only, in the run folder: titles can
        hold words from a prompt). Call with the lock held."""
        # The last lines said go along, so that repeat and the history have something after a
        # restart (the author pressed repeat after one and got "Nothing from ... yet").
        kept = {"sessions": self.sessions.identities(), "focus": self.talk_target,
                "history": [dict(e) for e in list(self.history)[-KEPT_LINES:]]}
        if kept == self._kept_sessions:
            return
        self._kept_sessions = kept
        try:
            path = self._sessions_file()
            with os.fdopen(os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                json.dump(kept, f)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def reconcile(self) -> None:
        """Catch what hooks cannot report, from Claude Code's own session files: a turn you
        interrupted with Esc, and a session whose terminal was closed."""
        live = claude_sessions.read(self.cfg.sessions_dir)
        changed = False
        with self.lock:
            for s in list(self.sessions.by_id.values()):
                info, quiet = live.get(s.id), time.monotonic() - s.updated
                if info:
                    s.seen_file = True
                    if s.tty is None:  # the terminal it runs in, to mark it (see terminal.py)
                        s.tty = terminal_mod.tty_of(info["pid"])
                    if info.get("name") and info["name"] != s.named:  # Claude Code's own name for the session
                        s.named = info["name"]
                        if not s.given:  # its own words for what it is doing say more than that name
                            s.title = short_title(info["name"])
                    if (info["status"] == "idle" and s.state in ("working", "needs_you") and quiet > 3
                            and time.time() - info["status_at"] > 2):
                        self._settle(s.id, "interrupted")
                        s.state, s.activity, s.note, s.turn_started = "idle", "", "interrupted", None
                        changed = True
                elif s.seen_file and quiet > 5:  # it had a file and no longer does: the session is gone
                    self._forget(s.id, "session gone")
                    changed = True
            # A session that was asked to stop: its hook takes the file away as it ends the turn.
            for sid, stopping in list(self._stopping.items()):
                s = self.sessions.by_id.get(sid)
                if not s:
                    self._unstop(sid)
                elif not os.path.exists(self._stop_file(sid)):
                    del self._stopping[sid]
                    self._settle(sid, "stopped")
                    s.state, s.activity, s.note, s.turn_started = "idle", "", "stopped", None
                    if not (self._talking or self._transcribing or self._pending):
                        self._talk("stopped", s, "Stopped", seconds=2.5)
                    log(self.cfg, "hub.log", f"stop [{sid[:8]}] its turn was ended {time.monotonic() - stopping.at:.1f} s after the key")
                    changed = True
                elif s.state in BUSY:
                    stopping.busy = True
                elif stopping.busy or time.monotonic() - stopping.at > STOP_WAIT:
                    self._unstop(sid, "its turn ended by itself")
                    changed = True
            # Words that waited for a busy session go out once it is no longer busy. After a
            # reply that happens by itself (its new listener asks for them); after an interrupt
            # no hook runs, so the listener it has had since its last prompt is woken here.
            for sid, waiting in self.followups.items():
                s, listener = self.sessions.by_id.get(sid), self.listeners.get(sid)
                if waiting and s and listener and not listener.wake.is_set() and s.state not in BUSY:
                    listener.wake.set()
                    log(self.cfg, "hub.log", f"follow-up [{sid[:8]}] sent, now that the session has stopped")
        if changed:
            self.publish()

    def on_display(self, ev: dict) -> dict | None:
        """MessageDisplay: speak a speak-tag line as soon as it streams in; return the rewrite."""
        speech, shown, title = split_display(str(ev.get("delta") or ""))
        sid = ev.get("session_id")
        if not speech or not sid:
            return None
        with self.lock:
            self.last_event = time.monotonic()
            s = self.sessions.touch(sid, ev.get("cwd", ""))
            s.spoken = speech
            self._title_from(s, reply=speech, given=title)
            self._say(s, speech, "done", "stream")
        self.publish()
        return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}

    def _title_from(self, s, prompt: str = "", reply: str = "", given: str = "") -> None:
        """What a session is called beside its name.

        Best is `given`: the title the session wrote into the speak tag of a reply (the hook
        asks for one, see `Config.titles`). It says what the session is working on, in its own
        words, follows the work as it moves on, and from the first one nothing else replaces it.

        Without one: Claude Code's own name for the session (see reconcile), and failing that
        our own title, for a session Claude Code has not named (it names one within a second
        of the first typed prompt, but never one that was started by voice).

        The first reply decides: its spoken line says what the session turned out to be about,
        and that title then stays. Until then a typed prompt stands in. A prompt that opens with
        markup is no one's words (a voice follow-up reaches Claude wrapped in
        "<task-notification>"), and the follow-up itself is not used either: the author asked
        to wait for the reply instead of naming a session from the start of a spoken ramble.
        """
        if given and self.cfg.titles != "auto":
            s.title, s.given = short_title(given), True
        if s.given or s.named or s.settled:
            return
        if reply:
            s.title, s.settled = short_title(reply), True
        elif prompt and not prompt.lstrip().startswith("<"):
            s.title = short_title(prompt)

    def say(self, text: str, voice: str | None = None, kind: str = "notice") -> None:
        """A line from the command line, not tied to a session."""
        self.speech.put(Utterance(text=text, voice=voice or self.cfg.default_voice, kind=kind, src="cli"))

    def snapshot(self) -> dict:
        with self.lock:
            sessions = [s.snapshot() for s in self.sessions.by_id.values()]
        outdated = {"hub": stale.changed(), "overlay": bool(getattr(self.overlay, "outdated", lambda: False)())}
        return {"sessions": sessions, "muted": self._muted(), "outdated": outdated, **self.speech.snapshot()}

    # --- catching up -------------------------------------------------------------------------

    def repeat(self) -> bool:
        """Say again the last line of the session in focus (the one the wheel or the last speaker
        chose), or with `repeat: last` the last line anyone said."""
        with self.lock:
            self.last_seen = time.time()
            s = self._target() if self.cfg.repeat != "last" else None
            lines = [e for e in self.history if not s or e.get("session") == s.id]
            entry = lines[-1] if lines else None
            nothing = f"Nothing from {_spoken_name(s.name)} yet." if s else "Nothing to repeat."
        if not entry:
            self.say(nothing, kind="notice")
            return False
        self._replay(entry, "repeat")
        return True

    def _replay(self, entry: dict, src: str, named: bool = False) -> None:
        """Say a line from the history again. It belongs to its session like the first time, so
        the overlay shows it at that session's light; `named` says the session's name first."""
        with self.lock:
            live = entry.get("session", "") in self.sessions.by_id
        self.speech.put(Utterance(text=entry["text"], voice=entry["voice"], session=entry["session"] if live else "",
                                  kind="notice", src=src, entry=entry,
                                  label=entry["spoken_name"] if named or not live else None))

    def catch_up(self, limit: int = 8) -> int:
        """Replay what sessions said since the user was last seen (a prompt, a hotkey, a catch-up)."""
        with self.lock:
            missed = [e for e in self.history if e["time"] > self.last_seen][-limit:]
            self.last_seen = time.time()
        if not missed:
            self.say("Nothing new.", kind="notice")
            return 0
        self.say(f"You missed {len(missed)} update{'s' if len(missed) != 1 else ''}.", kind="notice")
        for entry in missed:
            self._replay(entry, "catch-up", named=True)
        return len(missed)

    def _maybe_say_progress(self, s) -> None:
        """During a long turn, say how far its task list is, but not often."""
        done, total, now = sum(s.tasks.values()), len(s.tasks), time.monotonic()
        if (self.cfg.progress and total >= 3 and done < total and s.turn_started
                and now - s.turn_started >= self.cfg.progress_after
                and now - self._progress_said.get(s.id, 0) >= self.cfg.progress_interval):
            self._progress_said[s.id] = now
            self._say(s, f"{done} of {total} steps done", "progress", "progress")

    # --- voices ------------------------------------------------------------------------------

    def voices(self) -> dict:
        engine = self.speech.engine
        with self.lock:
            projects = {**self.sessions.remembered, **self.sessions.pinned}
            open_now = {s.name: s.voice for s in self.sessions.by_id.values()}
        return {"choosable": hasattr(engine, "custom"), "builtin": sorted(getattr(engine, "voices", [])),
                "custom": sorted(getattr(engine, "custom", {})), "pool": list(self.cfg.voice_pool),
                "projects": {**projects, **open_now}}

    def set_voice(self, project: str, voice: str) -> str | None:
        """Give a project a voice. Returns an error message, or None when done."""
        engine = self.speech.engine
        if not hasattr(engine, "has"):
            return "this machine's voice engine has only one voice"
        if not engine.has(voice):
            return f"no voice called {voice}; see: claude-speaks voices"
        with self.lock:
            self.sessions.set_voice(project, voice)
        return None

    def add_voice(self, name: str, path: str | None = None, mix: dict | None = None) -> str | None:
        """Add one of the user's own voices: from a Kokoro voice file, or as a blend of existing ones."""
        import numpy as np

        engine = self.speech.engine
        if not hasattr(engine, "save_custom"):
            return "own voices need the Kokoro voice engine"
        if not re.fullmatch(r"[a-z0-9_]{1,32}", name) or name in engine.voices:
            return "a voice name is 1 to 32 lowercase letters, digits or _, and not a built-in name"
        try:
            if mix:
                unknown = [v for v in mix if not engine.has(v)]
                total = sum(float(w) for w in mix.values())
                if unknown or total <= 0:
                    return f"unknown voice: {unknown[0]}" if unknown else "the weights must add up to more than zero"
                array = sum(engine.style(v) * (float(w) / total) for v, w in mix.items())
            elif path and path.endswith(".pt"):
                return ("that is a PyTorch file; convert it first with: "
                        "python -c \"import torch, numpy; numpy.save('voice.npy', torch.load('FILE').numpy())\"")
            else:
                loaded = np.load(path, allow_pickle=False)
                if hasattr(loaded, "files"):  # an archive of several voices, like Kokoro's own voices file
                    if name not in loaded.files:
                        return f"that archive holds several voices ({', '.join(loaded.files[:8])}...); name one of them"
                    loaded = loaded[name]
                array = loaded
            engine.save_custom(name, array)
        except OSError as e:
            return f"could not read the file: {e.strerror or e}"
        except ValueError as e:
            reason = str(e) if str(e).startswith("not a Kokoro voice") else "it is not a plain numeric .npy array"
            return f"that file cannot be used as a voice: {reason}"
        return None

    def remove_voice(self, name: str) -> str | None:
        engine = self.speech.engine
        if not hasattr(engine, "remove_custom") or not engine.remove_custom(name):
            return f"no voice of yours is called {name}"
        return None

    # --- permission prompts ------------------------------------------------------------------

    def request_permission(self, ev: dict) -> Request | None:
        """A session is showing a permission prompt. Returns a request the caller waits on,
        or None when there is nothing for the hub to answer."""
        sid, tool = ev.get("session_id"), str(ev.get("tool_name") or "")
        if not sid:
            return None
        with self.lock:
            self.last_event = time.monotonic()
            s = self.sessions.touch(sid, ev.get("cwd", ""))
            tool_input = ev.get("tool_input") or {}
            questions = _answerable(tool_input) if tool == "AskUserQuestion" else []
            if questions:  # the number keys can answer these
                req = Request(session=sid, tool=tool, tool_input=tool_input, summary=questions[0]["question"],
                              detail="", questions=questions)
                s.state, s.note = "needs_you", f"asks: {questions[0]['question']}"
            elif tool in OWN_DIALOG:
                s.state, s.note = "needs_you", "has a question for you" if tool == "AskUserQuestion" else "has a plan for you"
                req = None
            else:
                summary, detail = permission_summary(tool, tool_input)
                req = Request(session=sid, tool=tool, tool_input=tool_input, summary=summary, detail=detail)
                s.state, s.note = "needs_you", f"wants to: {summary}"
            if req:
                self.requests.append(req)
                self._show_request()
        self.publish()
        return req

    def decide(self, decision: str) -> bool:
        """Answer the request on screen (hotkey or command line). False if there was nothing to answer."""
        with self.lock:
            req = self.requests[0] if self.requests else None
            if not req or req.question or req.shown is None or time.monotonic() - req.shown < MIN_SHOWN:
                return False  # nothing there, a question, or it appeared too recently to have been read
            self.last_seen = time.time()
            s = self.sessions.by_id.get(req.session)
            self._resolve(req, decision, "hotkey")
            if s:
                self.speech.drop_session(s.id)  # stop "permission needed" if it is still being said
                self._say(s, "Allowed." if decision == "allow" else "Denied.",
                          "allowed" if decision == "allow" else "denied", "decision")
        self.publish()
        return True

    def choose(self, number: int) -> bool:
        """Answer the question on screen with its option number (1 to 4)."""
        with self.lock:
            req = self.requests[0] if self.requests else None
            question = req.question if req else None
            if (not question or req.shown is None or time.monotonic() - req.shown < MIN_SHOWN
                    or not 1 <= number <= len(question["options"])):
                return False
            self.last_seen = time.time()
            self._answer(req, question["options"][number - 1]["label"], "hotkey")
        self.publish()
        return True

    def _answer(self, req: Request, answer: str, why: str, echo: bool = True) -> None:
        """Give `answer` to the question on screen: an option's label, or with `why` "voice" the
        user's own words (Claude gets them as it gets a typed "Other"). After the last question
        the hook hands all answers to Claude. `echo` says the answer back. Call with the lock held."""
        req.answers[req.question["question"]] = answer
        s = self.sessions.by_id.get(req.session)
        if s:
            self.speech.drop_session(s.id)  # stop reading the options out
        if req.question:  # more questions in the same prompt: on to the next
            req.shown = time.monotonic()
            if s:
                s.note = f"asks: {req.question['question']}"
                self._say(s, f"{answer + '. ' if echo else ''}Next. {_read_out(req.question)}", "needs_you", "question")
            self._show_request()
        else:
            self._resolve(req, "answer", why)
            if s and echo:
                self._say(s, f"Answered: {answer}.", "allowed", "decision")

    def abandon(self, req: Request, why: str, interrupted: bool = False) -> None:
        """The request ended without the hub answering it (answered in the terminal, hook killed...)."""
        with self.lock:
            s = self.sessions.by_id.get(req.session)
            self._resolve(req, None, why)
            if interrupted and s and not req.decision:
                s.state, s.activity, s.note, s.turn_started = "idle", "", "interrupted", None
        self.publish()

    def _settle(self, sid: str, why: str, tool: str | None = None, tool_input: dict | None = None) -> None:
        """Close a session's open requests; with a tool given, only the one for that exact call."""
        for req in [r for r in self.requests if r.session == sid]:
            if tool is None or (req.tool == tool and _same_call(tool, req.tool_input, tool_input or {})):
                self._resolve(req, None, why)

    def _resolve(self, req: Request, decision: str | None, why: str) -> None:
        if req.done.is_set():
            return
        req.decision = decision
        self.requests.remove(req)
        req.done.set()
        s = self.sessions.by_id.get(req.session)
        if s and s.state == "needs_you" and not any(r.session == req.session for r in self.requests):
            s.state, s.note = "working", ""
        log(self.cfg, "hub.log", f"permission [{req.session[:8]}] {req.tool}: {decision or 'no answer'} ({why})")
        self._show_request()

    def _show_request(self) -> None:
        """Keep the overlay showing the oldest open request; that is the one the hotkeys answer."""
        req = self.requests[0] if self.requests else None
        if req and req.shown is None:
            req.shown = time.monotonic()
        if not self.overlay:
            return
        if not req:
            self.overlay.send({"type": "request"})
            return
        s = self.sessions.by_id.get(req.session)
        keys = self.cfg.overlay.get("hotkeys", {})
        more = len(self.requests) - 1
        if req.question:
            options, total = req.question["options"], len(req.questions)
            self.overlay.send({
                "type": "request", "name": s.name if s else "", "color": s.color if s else "",
                "text": f"asks: {req.question['question']}",
                "options": [o["label"] for o in options],  # drawn one to a line, each behind its number
                "detail": "\n".join(f"{i}  {o['label']}" for i, o in enumerate(options, 1)),
                "keys": f"{keys.get('option1', '')} to {keys.get(f'option{len(options)}', '')} answers"
                        + (f"  \u00b7  question {len(req.answers) + 1} of {total}" if total > 1 else "")
                        + (f"  \u00b7  {more} more waiting" if more else ""),
            })
            return
        self.overlay.send({
            "type": "request", "name": s.name if s else "", "color": s.color if s else "", "text": f"wants to: {req.summary}",
            "detail": req.detail[:300],
            "keys": f"{keys.get('allow', '')} allow  \u00b7  {keys.get('deny', '')} deny" + (f"  \u00b7  {more} more waiting" if more else ""),
        })

    def place_overlay(self, tell_window: bool = True, **changes) -> None:
        """Change where the overlay sits (monitor, corner, offsets) and remember it."""
        self.cfg.overlay.update(changes)
        if tell_window and self.overlay and hasattr(self.overlay, "reconfigure"):
            self.overlay.reconfigure()
        self._save_settings("overlay", changes)

    def _save_settings(self, section: str, changes: dict) -> None:
        """Write settings chosen while running into that section of the user's config.json."""
        if not self.cfg.config_path:
            return
        try:
            with open(self.cfg.config_path) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        saved.setdefault(section, {}).update(changes)
        try:
            os.makedirs(os.path.dirname(self.cfg.config_path), exist_ok=True)
            with open(self.cfg.config_path, "w") as f:
                json.dump(saved, f, indent=2)
        except OSError as e:
            log(self.cfg, "hub.log", f"could not save the {section} settings: {e}")

    def reload_languages(self) -> dict:
        """Take up the languages chosen with `claude-speaks languages` (written to config.json)
        without a restart: the next push-to-talk loads the model for them."""
        try:
            with open(self.cfg.config_path) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        model = saved.get("whisper_model") or self.cfg.whisper_model
        language = saved.get("whisper_language") or self.cfg.whisper_language
        if (model, language) != (self.cfg.whisper_model, self.cfg.whisper_language):
            self.cfg.whisper_model, self.cfg.whisper_language = model, language
            if self.transcriber:
                self.transcriber = stt.Transcriber(model, language)
            log(self.cfg, "hub.log", f"push-to-talk now listens with {model} for: {language}")
        return {"model": model, "languages": language, "push_to_talk": bool(self.transcriber)}

    def set_terminal(self, **changes) -> None:
        """Change how sessions' terminals are marked (see terminal.py), at once, and remember it."""
        self.cfg.terminal.update(changes)
        self.terminals.settings.update(changes)
        self.publish()
        self._save_settings("terminal", changes)

    def find_terminal(self, name: str = "") -> str | None:
        """Light up the terminal of the session called `name`, or of the one in focus. Returns
        the session's name, or None when there is no such session or it has no terminal."""
        with self.lock:
            s = (next((x for x in self.sessions.by_id.values() if x.name == name), None) if name
                 else self._target())
            found = (s.name, s.tty, s.color) if s and s.tty else None
        if not found:
            return None
        self.terminals.pulse(found[1], found[2], asked=True)
        return found[0]

    def set_layout(self, name: str) -> str | None:
        """Show the sessions in another layout ("next" goes round them) and remember the choice."""
        names = overlay_mod.LAYOUTS
        if name == "next":
            current = self.cfg.overlay.get("layout", names[0])
            name = names[(names.index(current) + 1) % len(names)] if current in names else names[0]
        if name not in names:
            return None
        self.place_overlay(layout=name)
        self.say(f"{name} layout", kind="notice")
        return name

    def on_overlay(self, msg: dict) -> None:
        if msg.get("type") == "ready":
            # A window that has just started is handed the sessions again by its own module, and
            # nothing else: tell it the question that is still open and the keys that are live.
            with self.lock:
                self._keys = None
                if self.requests:
                    self._show_request()
            self.publish()
            return
        if msg.get("type") == "moved":  # dragged to a new place
            placed = {k: msg[k] for k in ("monitor", "corner", "offset_x", "offset_y", "island_x", "island_y") if k in msg}
            self.place_overlay(False, **placed)  # the window already knows; this saves it
            return
        if msg.get("type") == "mode":  # details kept out, or only the lights: the same after a hub restart
            if msg.get("mode") in ("dots", "list"):
                self.place_overlay(False, mode=msg["mode"])
            return
        if msg.get("type") != "hotkey":
            return
        name = msg.get("name")
        if name != "missed":  # any other key press shows the user is there
            self.last_seen = time.time()
        if name in ("allow", "deny"):
            self.decide(name)
        elif name and name.startswith("option"):
            self.choose(int(name[6:]))
        elif name == "repeat":
            self.repeat()
        elif name == "missed":
            self.catch_up()
        elif name == "talk":
            self.talk_start()
        elif name == "talk_end":
            self.talk_end()
        elif name == "cancel":
            self.cancel()
        elif name in ("focus_next", "focus_prev"):
            self.focus(1 if name == "focus_next" else -1)
        elif name == "layout":
            self.set_layout("next")

    # --- push-to-talk ------------------------------------------------------------------------

    def talk_start(self) -> bool:
        """The talk key went down: go quiet and record."""
        with self.lock:
            if self._talking or not self.recorder:
                return False
            s = self._target()
            before, since = self._focus_lost
            if time.monotonic() - since < self.cfg.focus_reach_back and before in self.sessions.by_id:
                # Another session began to speak in the moment the key went down and took the
                # focus: the words are for the one that had it when you decided to speak.
                s = self.sessions.by_id[before]
            self._focus_lost = ("", 0.0)
            if not s:
                self._talk("failed", None, "No Claude session to talk to", seconds=2)
                return False
            self._talking = time.monotonic()
            self._sent = None  # speaking again: what went out before stays out
            self.talk_target = s.id  # the session shown as listening is the one that gets it
            if not (self._pending and self._pending.confirm):  # that one may be about to get its confirming tap
                self._cancel_pending()
                self._talk("listening", s)
        self.speech.pause()
        self.recorder.start()
        if self.transcriber:  # load the model while the user is still speaking
            threading.Thread(target=self.transcriber.load, daemon=True).start()
        self.publish()
        return True

    def talk_end(self) -> None:
        """The talk key came up. A hold is transcribed. A quick tap confirms the follow-up on
        screen if one is waiting for that, and otherwise picks the next session."""
        with self.lock:
            if not self._talking:
                return
            held, self._talking = time.monotonic() - self._talking, None
            confirming = self._pending if self._pending and self._pending.confirm else None
            tap, said_to, heard = held < TAP, None, None
            if not tap:
                # Who was listening when the key came up gets the words. Decided here, before
                # the tail of the recording and the second or two of turning it into text:
                # the focus may move on in that time, and the words must not follow it.
                said_to = self._target()
                self._cancel_pending()
                self._transcribing = True
                heard = self._heard = object()
                self._talk("transcribing", said_to)
        try:
            pcm = self.recorder.stop(tail=0 if tap else self.cfg.talk_tail)
        except Exception:
            self._transcribing, self._heard = False, None
            raise
        # A line cut by the key is said again, unless you held the key to answer that very session.
        self.speech.resume(answering=said_to.id if said_to else "")
        if tap and confirming:
            self._send(confirming)
        elif tap:
            with self.lock:
                ids = list(self.sessions.by_id) if self.cfg.talk_tap == "next" else []
                if ids:
                    self.talk_target = ids[(ids.index(self._target().id) + 1) % len(ids)]
                    self._talk("focus", self.sessions.by_id[self.talk_target], seconds=1.6)
        else:
            threading.Thread(target=self._transcribe, args=(pcm, said_to.id if said_to else None, heard),
                             daemon=True).start()
        self.publish()

    def _transcribe(self, pcm: bytes, session: str | None = None, job: object | None = None) -> None:
        started = time.monotonic()
        try:
            text = self.transcriber.transcribe(pcm) if self.transcriber else ""
        except Exception as e:  # a broken model must not take the hub down
            log(self.cfg, "hub.log", f"transcription failed: {e}")
            text = ""
        heard = getattr(self.transcriber, "heard", "") if text else ""
        log(self.cfg, "hub.log", f"talk: {len(pcm) / 2 / stt.RATE:.1f}s recorded, peak level {stt.loudness(pcm):.2f}, "
                                 f"transcribed in {time.monotonic() - started:.1f}s"
                                 f"{' as ' + heard if heard else ''}: {text or '(nothing heard)'}")
        if self._unload:
            self._unload.cancel()
        if self.transcriber and self.cfg.whisper_unload_minutes:
            self._unload = threading.Timer(self.cfg.whisper_unload_minutes * 60, self.transcriber.unload)
            self._unload.daemon = True
            self._unload.start()
        if job is not None and self._heard is not job:  # the cancel key, while this was being worked out
            log(self.cfg, "hub.log", "talk: cancelled before it was sent")
            return
        try:
            said_to = self.sessions.by_id.get(session or "")
            if not text:
                self._talk("failed", said_to or self._target(), "Didn't catch that", seconds=2)
                self._signal("failed")
            elif session and not said_to:  # it ended while the words were being worked out
                self._talk("failed", None, "That session is gone, not sent", seconds=2.5)
                self._signal("failed")
                log(self.cfg, "hub.log", f"follow-up [{session[:8]}] not sent: the session is gone")
            else:
                self.follow_up(text, session)
        finally:
            if job is None or self._heard is job:
                self._transcribing, self._heard = False, None

    def follow_up(self, text: str, session: str | None = None, delay: float | None = None) -> bool:
        """Show a follow-up, then send it to the session.

        A heard follow-up (no `delay` given) goes out after `followup_delay` (at once by default),
        or, with `followup_confirm` on, only after a confirming tap of the talk key.
        """
        with self.lock:
            s = self.sessions.by_id.get(session) if session else self._target()
            if not s:
                return False
            self._cancel_pending()
            keys = self.cfg.overlay.get("hotkeys", {})
            confirm = delay is None and self._needs_confirmation(s)
            pending = self._pending = Pending(s.id, text, confirm)
            if confirm:
                hint = f"tap {keys.get('talk') or 'the talk key'} to send  \u00b7  {keys.get('cancel', '')} cancels"
                pending.timer = threading.Timer(CONFIRM_WINDOW, self._expire, args=(pending,))
            else:
                hint = f"{keys.get('cancel', '')} cancels" if keys.get("cancel") else ""
                pending.timer = threading.Timer(self.cfg.followup_delay if delay is None else delay,
                                                self._send, args=(pending,))
            self._talk("ready", s, text, hint)
            pending.timer.daemon = True
            pending.timer.start()
        self.publish()
        return True

    def _send(self, pending: Pending) -> None:
        with self.lock:
            if self._pending is not pending:
                return  # cancelled or replaced meanwhile
            pending.timer.cancel()
            self._pending = None
            s = self.sessions.by_id.get(pending.session)
            if not s:
                self._talk(None)
                return
            shown = max(2.5, self.cfg.unsend_seconds)  # what went out, for as long as it can be taken back
            self._talk("sent", s, pending.text, seconds=shown)
            asking = next((r for r in self.requests if r.session == s.id and r.question), None)
            if asking:  # it is waiting on a question, so these words are the answer to it
                self._answer(asking, pending.text, "voice", echo=False)
                log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] given as the answer to its question")
                self._signal("sent", s, "Sent.")
            else:
                listener = self._deliver(s, pending.text)
                if not listener:
                    self._talk("queued", s, pending.text, seconds=max(3.5, shown))
                log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] {'sent' if listener else 'waiting for the session to stop'}")
                self._signal("sent" if listener else "queued", s, "Sent." if listener else "Queued.")
            if self.cfg.unsend_seconds > 0:
                self._sent = Sent(s.id, pending.text, time.monotonic(), answer=bool(asking))
                done = threading.Timer(self.cfg.unsend_seconds + 0.05, self.publish)  # gives the cancel key back
                done.daemon = True
                done.start()
        self.publish()

    def _deliver(self, s, text: str) -> bool:
        """Hand words to a session. True: its listener has them now. False: they wait in the
        hub. Call with the lock held."""
        self.followups.setdefault(s.id, []).append(text)
        self._keep_followups()
        # A session has a listener all the time (see listen.sh), also in the middle of
        # a reply; then the words wait and it gets them right after (see reconcile).
        listener = self.listeners.get(s.id) if s.state not in BUSY else None
        if listener:
            listener.wake.set()
        else:
            self._waiting.add(s.id)
        return bool(listener)

    def _unsendable(self) -> Sent | None:
        """The follow-up the cancel key would take back right now, if any."""
        sent = self._sent
        return sent if sent and time.monotonic() - sent.at < self.cfg.unsend_seconds else None

    def _take_back(self) -> bool:
        """The cancel key shortly after sending: words still waiting in the hub are removed;
        words the session already has cannot be, so it is told to ignore them. Call with the
        lock held."""
        sent, self._sent = self._unsendable(), None
        s = self.sessions.by_id.get(sent.session) if sent else None
        if not s:
            return False
        waiting = self.followups.get(s.id, [])
        after = f"{time.monotonic() - sent.at:.1f} s after it went out"  # the log's own times are whole seconds
        if not sent.answer and sent.text in waiting:
            del waiting[len(waiting) - 1 - waiting[::-1].index(sent.text)]
            if not waiting:
                self.followups.pop(s.id, None)
                self._waiting.discard(s.id)
            self._keep_followups()
            self._talk("failed", s, "Taken back", seconds=2)
            log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] taken back {after}, before the session got it")
        elif self.cfg.cancel_stops != "never" and self._stop_turn(s):
            self._talk("stopped", s, "Taken back: stopping it", seconds=3)
            log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] taken back {after}, when the session had it: its turn is being stopped")
        else:
            self._deliver(s, TAKE_BACK)
            self._talk("failed", s, "Taken back: it is told to ignore that", seconds=3)
            log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] taken back {after}, when the session had it: told to ignore it")
        self._signal("failed")
        return True

    # --- stopping a turn ---------------------------------------------------------------------

    def _stop_file(self, sid: str) -> str:
        return os.path.join(self.cfg.run, "stop", sid)

    def _stop_turn(self, s) -> bool:
        """Ask a session to end the turn it is in. Nothing outside a terminal can press Esc in
        it, and a signal ends the whole session, so a file named after the session is left
        for hooks/stop.sh, which ends the turn at the session's next tool call or as the one
        that is running finishes. Until then the session is not spoken for: what it says
        about that turn is not wanted. Call with the lock held."""
        if not SAFE_ID.match(s.id):
            return False
        try:
            os.makedirs(os.path.dirname(self._stop_file(s.id)), mode=0o700, exist_ok=True)
            os.close(os.open(self._stop_file(s.id), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
        except OSError:
            return False
        self._stopping[s.id] = Stopping(time.monotonic(), s.state in BUSY)
        self.speech.drop_session(s.id)
        return True

    def _unstop(self, sid: str, why: str = "") -> None:
        """The turn is over, or another one is wanted: nothing is to be stopped any more."""
        if self._stopping.pop(sid, None) is None:
            return
        try:
            os.unlink(self._stop_file(sid))
        except OSError:
            pass
        if why:
            log(self.cfg, "hub.log", f"stop [{sid[:8]}] not needed: {why}")

    def _clear_stops(self) -> None:
        try:
            for name in os.listdir(os.path.join(self.cfg.run, "stop")):
                os.unlink(os.path.join(self.cfg.run, "stop", name))
        except OSError:
            pass

    def _stoppable(self):
        """The session whose turn the cancel key would end when there is nothing else for it
        to cancel: the one in focus, while it works."""
        s = self._target() if self.cfg.cancel_stops == "always" else None
        return s if s and s.state == "working" and s.id not in self._stopping else None

    def _expire(self, pending: Pending) -> None:
        """Nobody confirmed it in time: better dropped than sent late and out of context."""
        with self.lock:
            if self._pending is not pending:
                return
            self._pending = None
            self._talk("failed", self.sessions.by_id.get(pending.session), "Not sent", seconds=2)
            self._signal("failed")
        self.publish()

    def cancel(self) -> None:
        """The cancel key: stop recording, or take back a follow-up (one still being worked
        out, one on screen, or one sent in the last few seconds), or cut the line being spoken,
        or, with none of those, end the turn of the session in focus."""
        stopped = False
        with self.lock:
            talking, self._talking = self._talking, None
            about = self.sessions.by_id.get(self._pending.session) if self._pending else self._target()
            had_pending = self._cancel_pending()
            # Let go already, the words not out of the speech model yet: they are dropped when they come.
            hearing, took_back = self._transcribing and self._heard is not None, False
            if hearing:
                self._transcribing, self._heard = False, None
            if talking or had_pending or hearing:
                self._talk("failed", about, "Cancelled", seconds=1.5)
                self._signal("failed")
            else:
                took_back = self._take_back()
                s = self._stoppable()
                if not took_back and s and not self.speech.current and self._stop_turn(s):
                    stopped = True
                    self._talk("stopped", s, "Stopping at its next step", seconds=3)
                    self._signal("failed")
                    log(self.cfg, "hub.log", f"stop [{s.id[:8]}] asked for with the cancel key")
        if talking:
            self.recorder.stop()
            self.speech.resume()
        elif not (had_pending or took_back or hearing or stopped):
            self.speech.skip()
        self.publish()

    def listen(self, sid: str, cwd: str = "") -> Listener:
        """A session's hook starts waiting for follow-ups; it replaces that session's older one."""
        with self.lock:
            self.sessions.touch(sid, cwd)  # after a hub restart this is how an idle session reappears
            self._release(sid)
            listener = self.listeners[sid] = Listener(sid)
            s = self.sessions.by_id.get(sid)
            if self.followups.get(sid) and not (s and s.state in BUSY):
                listener.wake.set()
            return listener

    def collect(self, listener: Listener) -> str | None:
        """What the hook should hand to Claude, or None if it should just exit."""
        with self.lock:
            if listener.released or self.listeners.get(listener.session) is not listener:
                return None
            del self.listeners[listener.session]
            text = " ".join(self.followups.pop(listener.session, [])) or None
            self._keep_followups()
            waited = listener.session in self._waiting
            self._waiting.discard(listener.session)
            if text:
                self._unstop(listener.session, "it was given new words")  # they start a turn that must run
            s = self.sessions.by_id.get(listener.session)
            # Words that had to wait are now with the session: say so on its light, unless
            # push-to-talk is showing something of its own there.
            last = self._unsendable()  # words that can still be taken back keep their own sign
            if (text and waited and s and TAKE_BACK not in text and (not last or last.session == s.id)
                    and not (self._talking or self._transcribing or self._pending)):
                self._talk("sent", s, text, seconds=2.5)
        if text and waited:
            self.publish()  # the mark for waiting words leaves the light
        return text

    def stop_listening(self, listener: Listener) -> None:
        with self.lock:
            if self.listeners.get(listener.session) is listener:
                del self.listeners[listener.session]

    def _followups_file(self) -> str:
        return os.path.join(self.cfg.run, "followups.json")

    def _kept_followups(self) -> dict[str, list[str]]:
        """Follow-ups an earlier hub had not delivered yet, unless they are stale (over an hour old)."""
        try:
            path = self._followups_file()
            if time.time() - os.path.getmtime(path) > 3600:
                return {}
            with open(path) as f:
                kept = json.load(f)
            return {str(sid): [str(t) for t in texts] for sid, texts in kept.items() if texts}
        except (OSError, ValueError, AttributeError):
            return {}

    def _keep_followups(self) -> None:
        try:
            path = self._followups_file()
            if not self.followups:
                if os.path.exists(path):
                    os.unlink(path)
                return
            with os.fdopen(os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                json.dump(self.followups, f)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def _release(self, sid: str) -> None:
        old = self.listeners.pop(sid, None)
        if old:
            old.released = True
            old.wake.set()

    def focus(self, step: int) -> str | None:
        """Move the focus (who a spoken follow-up goes to) to the next or previous session.
        It stops at the first and the last one: turning the wheel further does not jump round."""
        with self.lock:
            ids = list(self.sessions.by_id)
            if not ids:
                return None
            s = self.sessions.by_id[ids[max(0, min(len(ids) - 1, ids.index(self._target().id) + step))]]
            self._focus_on(s)
            name, tty, color = s.name, s.tty, s.color
        self.publish()
        if tty:  # chosen by hand: its terminal lights up for a moment, so it can be found
            self.terminals.pulse(tty, color)
        return name

    def _focus_on(self, s) -> None:
        """Give this session the focus because the user chose it. Call with the lock held."""
        self.talk_target = s.id
        self._focus_lost = ("", 0.0)  # chosen by hand: nothing to reach back to
        if self._talk_shown:  # what is on screen for push-to-talk follows the focus
            if self._pending:
                self._pending.session = s.id
            self._talk(self._talk_shown[0], s, *self._talk_shown[1:])

    def terminal_in_front(self, pid: int, switched: bool = True) -> str | None:
        """The editor says you are now in the terminal that process `pid` (its shell) runs in:
        the session running there gets the focus. Returns its name, or None when nothing changed.

        `switched`: you went to another terminal inside the editor. Otherwise the editor's
        window only came to the front, which counts when that is another terminal than the
        last one reported (several windows), and not when it is the same one: coming back to
        the window should not take the focus away from a session that spoke meanwhile.
        No pulse: you are looking at that terminal already."""
        if not self.cfg.terminal.get("follow", True):
            return None
        tty = terminal_mod.tty_of(pid)
        with self.lock:
            same, self._front = tty == self._front, tty
            s = next((x for x in self.sessions.by_id.values() if tty and x.tty == tty), None)
            if not s or (same and not switched) or self._target() is s:
                return None
            self.last_seen = time.time()  # you are there
            self._focus_on(s)
            name = s.name
        log(self.cfg, "hub.log", f"focus on {name}: its terminal ({tty}) came to the front")
        self.publish()
        return name

    def _target(self):
        """Who a follow-up goes to: the chosen session, else the one that spoke last, else the newest."""
        s = self.sessions.by_id.get(self.talk_target or "")
        if not s and self.sessions.by_id:
            s = max(self.sessions.by_id.values(), key=lambda x: x.updated)
        return s

    def _cancel_pending(self) -> bool:
        if not self._pending:
            return False
        self._pending.timer.cancel()
        self._pending = None
        self._talk(None)
        return True

    def _needs_confirmation(self, s) -> bool:
        wanted = self.cfg.followup_confirm
        return s.permission_mode not in PROMPTING_MODES if wanted == "auto" else bool(wanted)

    def _talk(self, state: str | None, s=None, text: str = "", hint: str = "", seconds: float = 0) -> None:
        """Tell the overlay where push-to-talk stands: listening, transcribing, ready (waiting for a
        go-ahead), sent, failed (the text says why), focus (a tap moved it), or None for nothing.
        It is shown on the session it is about; it stays until replaced unless `seconds` is given."""
        self._talk_shown = (state, text, hint) if state in ("listening", "ready") else None
        if self.overlay:
            self.overlay.send({"type": "talk", "state": state, "name": s.name if s else "", "text": text,
                               "hint": hint, "seconds": seconds} if state else {"type": "talk"})

    def _mic_heard(self, chunk: bytes) -> None:
        """A moment of the microphone while the talk key is held: the overlay shows it as a wave."""
        if self.overlay:
            self.overlay.send({"type": "mic", "levels": [self._mic_meter.level(chunk)], "step": len(chunk) / 2 / stt.RATE})

    # --- overlay -----------------------------------------------------------------------------

    def publish(self) -> None:
        """Send the overlay what to draw, if it changed. Call without the lock held."""
        with self.lock:
            self._keep_sessions()
            several = len(self.sessions.by_id) > 1
            marks = {s.tty: terminal_mod.Mark(s.color, several and self._target() is s,
                                              " \u00b7 ".join(filter(None, [s.name, s.title])))
                     for s in self.sessions.by_id.values() if s.tty}
        self.terminals.show(marks)
        if not self.overlay:
            return
        current = self.speech.current
        speaking = current.session if current else None
        with self.lock:
            rows = [{
                "name": s.name,
                "color": s.color,
                "state": s.state,
                "title": s.title,
                "text": "Stopping at its next step" if s.id in self._stopping else s.activity if s.state == "working" else s.note,
                "meta": " \u00b7 ".join(filter(None, [
                    f"{sum(s.tasks.values())}/{len(s.tasks)}" if s.tasks else "",
                    _elapsed(time.monotonic() - s.turn_started) if s.state == "working" and s.turn_started else "",
                    self._waiting_note(s.id),
                ])),
                "waiting": self._waiting_count(s.id),  # words of yours it has not been handed yet
                "speaking": s.id == speaking,
                "target": len(self.sessions.by_id) > 1 and self._target() is s,  # in focus: follow-ups go here
                "synth": not self.speech.meter,  # no real loudness to draw: the overlay makes up a motion
            } for s in self.sessions.by_id.values()]
            asking = self.requests[0].question if self.requests else None
            keys = sorted(([f"option{i}" for i in range(1, len(asking["options"]) + 1)] if asking
                           else ["allow", "deny"] if self.requests else [])
                          + (["cancel"] if self._talking or self._transcribing or self._pending or current or self._unsendable()
                             or self._stoppable() else [])
                          + (["focus_next", "focus_prev"] if len(self.sessions.by_id) > 1 else []))
            now = time.time()
            # Newest first, and up to four lines of each session: the overlay shows those of the
            # session under the mouse, so one that talks a lot must not push the others out.
            each, history = collections.Counter(), []
            for e in reversed(self.history):
                if each[e["name"]] < 4 and len(history) < 24:
                    each[e["name"]] += 1
                    history.append({"ago": _ago(now - e["time"]), "name": e["name"], "color": e.get("color", ""), "text": e["text"]})
            new_keys, self._keys = keys != self._keys, keys
            new_rows, self._shown = (rows, history) != self._shown, (rows, history)
        if new_keys:  # claim allow/deny/cancel only while they can do something
            self.overlay.send({"type": "keys", "live": keys})
        if new_rows:
            self.overlay.send({"type": "state", "sessions": rows, "history": history})

    def _waiting_count(self, sid: str) -> int:
        return len(self.followups.get(sid, ())) if sid in self._waiting else 0

    def _waiting_note(self, sid: str) -> str:
        n = self._waiting_count(sid)
        return "" if not n else "1 message waiting" if n == 1 else f"{n} messages waiting"

    def _flash(self, s, text: str, state: str | None = None) -> None:
        """Expand the overlay's dots into one line about this session for a few seconds."""
        if self.overlay:
            self.overlay.send({"type": "flash", "state": state or s.state, "name": s.name, "text": text,
                               "seconds": self.cfg.overlay.get("flash_seconds", 4)})

    def _voice_levels(self, u: Utterance, levels: list[float], step: float) -> None:
        """How loud the line being spoken is right now: the overlay draws it as a wave."""
        if not self.overlay or not u.session:
            return
        with self.lock:
            s = self.sessions.by_id.get(u.session)
            name = s.name if s else None
        if name:
            self.overlay.send({"type": "wave", "name": name, "levels": levels, "step": step})

    def _speech_changed(self, u: Utterance | None) -> None:
        """A line starts or ends: show it while it is heard, and mark which session is speaking."""
        if u and u.session:
            with self.lock:
                s = self.sessions.by_id.get(u.session)
                if s:
                    # A follow-up answers whoever spoke last. Not while you are talking, though:
                    # a line that starts between the key going down and your words being sent
                    # must not take them away from the session you were talking to.
                    if u.kind not in ("allowed", "denied", "progress") and not (self._talking or self._transcribing):
                        if self.talk_target and self.talk_target != s.id:  # who had it, and since when it is gone
                            self._focus_lost = (self.talk_target, time.monotonic())
                        self.talk_target = s.id
                    kind = u.entry["kind"] if u.kind == "notice" and u.entry else u.kind  # said again: as it first looked
                    self._flash(s, u.text, FLASH_LOOK.get(kind, kind))
        self.publish()

    # --- helpers -----------------------------------------------------------------------------

    def _muted(self) -> bool:
        return os.path.exists(self.cfg.mute_file)

    def _signal(self, name: str, s=None, words: str = "") -> None:
        """Answer something the user did by voice: with a sound, played at once beside whatever
        is being spoken, or with `words` in the session's voice (see `Config.talk_feedback`)."""
        mode = self.cfg.talk_feedback
        if mode == "sound" and self.sounds:
            if not self._muted():
                self.sounds.play(name)
        elif mode != "none" and s and words:
            self._say(s, words, "allowed", "follow-up")

    def _say(self, s, text: str, kind: str, src: str) -> None:
        if s.id in self._stopping and kind in ("done", "progress"):
            log(self.cfg, "hub.log", f"stop [{s.id[:8]}] not spoken, its turn is being stopped: {text[:80]}")
            return
        s.last_speech = text
        entry = None
        if kind in ("done", "failed", "needs_you", "progress"):  # what a session said, not our own feedback
            entry = {"time": time.time(), "session": s.id, "name": s.name, "color": s.color,
                     "spoken_name": _spoken_name(s.name), "voice": s.voice, "text": text, "kind": kind, "heard": False}
            self.history.append(entry)
        if self._muted():
            self._flash(s, text, FLASH_LOOK.get(kind, kind))  # voice is off
        else:
            self.speech.put(Utterance(text=text, voice=s.voice, session=s.id, kind=kind, src=src, entry=entry))

    def _spoken_without_hub(self, sid: str, speech: str) -> bool:
        """True if display.sh spoke this line itself while the hub was down (it leaves a marker)."""
        marker = os.path.join(self.cfg.state, ".state", f"{sid}.spoken")
        try:
            with open(marker) as f:
                said = f.read()
            os.unlink(marker)
        except OSError:
            return False
        return said == speech

    def _label_for(self, u: Utterance) -> str:
        """The spoken project name, used only when nothing else tells sessions apart: several
        are active and there is no overlay on screen showing who is talking."""
        with self.lock:
            s = self.sessions.by_id.get(u.session)
            several = self.sessions.active_count() > 1
        shown = bool(self.overlay) and getattr(self.overlay, "ready", True)
        if s is None or self.cfg.label == "never" or (self.cfg.label == "auto" and (shown or not several)):
            return ""
        return _spoken_name(s.name)

    def _log_speech(self, u: Utterance, label: str, waited: float, first: float | None, outcome: str) -> None:
        if u.entry is not None and outcome == "spoken" and first is not None:
            u.entry["heard"] = True
        timing = f"waited={waited * 1000:.0f}ms"
        if first is not None:
            timing += f" first_audio={first * 1000:.0f}ms"
        if u.heard is not None:  # measured on the speakers' own output
            timing += f" heard={u.heard * 1000:.0f}ms"
        said = f"{label}. {u.text}" if label else u.text
        log(self.cfg, "voice.log", f"[{u.session[:8] or 'cli'}] src={u.src} {outcome} voice={u.voice} {timing} speech={said}")


def _spoken_name(name: str) -> str:
    """A session's name as it is said aloud: "api-server" becomes "api server"."""
    return re.sub(r"[-_.]+", " ", name).strip()


KEPT_LINES = 40  # how many of the last lines said are kept across a restart
BUSY = ("working", "needs_you")  # states of a session in the middle of a turn
FLASH_LOOK = {"allowed": "done", "denied": "failed", "progress": "working"}  # speech kind -> overlay glyph
NUMBER_WORDS = ("One", "Two", "Three", "Four")


def _same_call(tool: str, asked: dict, ran: dict) -> bool:
    """Is the tool call that ran the one a prompt was open for? A question answered in the
    terminal comes back with the answers added to it, so only its questions are compared."""
    if tool == "AskUserQuestion":
        return asked.get("questions") == ran.get("questions")
    return asked == ran


def _answerable(tool_input: dict) -> list:
    """The questions of an AskUserQuestion call if the number keys can answer all of them:
    single choice, two to four options each. Otherwise an empty list."""
    questions = tool_input.get("questions")
    if not isinstance(questions, list) or not questions:
        return []
    for q in questions:
        options = q.get("options") if isinstance(q, dict) else None
        if (not isinstance(options, list) or not 2 <= len(options) <= 4 or q.get("multiSelect")
                or not q.get("question") or not all(isinstance(o, dict) and o.get("label") for o in options)):
            return []
    return questions


def _read_out(question: dict) -> str:
    options = " ".join(f"{NUMBER_WORDS[i]}: {o['label']}." for i, o in enumerate(question["options"]))
    return f"Question: {question['question']} {options}"


def _ago(seconds: float) -> str:
    return "now" if seconds < 60 else _elapsed(seconds)


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


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # the default logger assumes a TCP client address
        pass

    def _send(self, body: dict | None, status: int) -> None:
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        hub: Hub = self.server.hub
        if self.path == "/state":
            self._reply(hub.snapshot())
        elif self.path == "/voices":
            self._reply(hub.voices())
        elif self.path == "/health":
            self._reply({"ok": True, "pid": os.getpid()})
        else:
            self._reply({"error": "not found"}, 404)

    def do_POST(self) -> None:
        hub: Hub = self.server.hub
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return self._reply({"error": "bad json"}, 400)
        if self.path == "/event":
            hub.on_event(body)
            self._reply({})
        elif self.path == "/display":
            self._reply(hub.on_display(body))
        elif self.path == "/say":
            hub.say(str(body.get("text", "")), body.get("voice"), body.get("kind", "done"))
            self._reply({})
        elif self.path == "/permission":
            self._permission(hub, body)
        elif self.path == "/listen":
            self._listen(hub, body)
        elif self.path == "/voice":
            action = body.get("action", "set")
            if action == "set":
                error = hub.set_voice(str(body.get("project", "")), str(body.get("voice", "")))
            elif action == "add":
                error = hub.add_voice(str(body.get("name", "")), body.get("path"), body.get("mix"))
            else:
                error = hub.remove_voice(str(body.get("name", "")))
            self._reply({"error": error})
        elif self.path == "/target":
            with hub.lock:
                match = next((s for s in hub.sessions.by_id.values() if s.name == body.get("session")), None)
                if match:
                    hub.talk_target = match.id
                target = hub._target()
            hub.publish()
            self._reply({"target": target.name if target else None, "found": bool(match) or not body.get("session")})
        elif self.path == "/follow-up":
            sid = None
            if body.get("session"):  # a project name from the command line
                with hub.lock:
                    sid = next((s.id for s in hub.sessions.by_id.values() if s.name == body["session"]), "?")
            delay = body.get("delay")  # typed, not heard, so it needs no confirming tap
            self._reply({"queued": hub.follow_up(str(body.get("text", "")), sid,
                                                 hub.cfg.followup_delay if delay is None else delay)})
        elif self.path == "/talk":  # the talk and cancel keys, for use without the overlay
            action = body.get("action")
            if action == "start":
                return self._reply({"ok": hub.talk_start()})
            hub.talk_end() if action == "stop" else hub.cancel()
            self._reply({"ok": True})
        elif self.path == "/sound":  # to hear what a sound is like
            self._reply({"played": bool(hub.sounds and hub.sounds.play(str(body.get("name", ""))))})
        elif self.path == "/answer":
            self._reply({"answered": hub.choose(int(body.get("option") or 0))})
        elif self.path == "/replay":
            self._reply({"count": hub.catch_up() if body.get("what") == "missed" else int(hub.repeat())})
        elif self.path == "/decide":
            self._reply({"answered": hub.decide("allow" if body.get("decision") == "allow" else "deny")})
        elif self.path == "/stop":
            hub.speech.stop_all()
            self._reply({})
        elif self.path == "/overlay":
            if not hub.overlay:
                return self._reply({"error": "the overlay is not available here"}, 409)
            if body.get("restart"):
                hub.overlay.restart()
            elif body.get("move"):
                hub.overlay.send({"type": "move"})
            elif "layout" in body:
                return self._reply({"layout": hub.set_layout(str(body["layout"]))})
            elif "monitor" in body or "corner" in body:
                hub.place_overlay(**{k: body[k] for k in ("monitor", "corner") if k in body})
            elif "hover" in body:  # whether the mouse alone brings the details out
                if body["hover"] not in ("keys", "always"):
                    return self._reply({"error": "hover is one of: keys, always"}, 400)
                hub.place_overlay(hover=body["hover"])
                return self._reply({"hover": body["hover"]})
            else:
                hub.overlay.send({"type": "mode", "mode": body.get("mode", "toggle")})
            self._reply({})
        elif self.path == "/terminal":
            if "front" in body:  # from the editor: the terminal of this process is the one you are in
                try:
                    pid = int(body["front"])
                except (TypeError, ValueError):
                    return self._reply({"error": "front is a process id"}, 400)
                return self._reply({"focus": hub.terminal_in_front(pid, body.get("why") != "window")})
            if "find" in body:  # light up one session's terminal, to see which it is
                return self._reply({"found": hub.find_terminal(str(body["find"] or ""))})
            changes = {k: body[k] for k in terminal_mod.DEFAULTS if k in body}
            if changes.get("tint", "focus") not in terminal_mod.TINTS:
                return self._reply({"error": "tint is one of: " + ", ".join(terminal_mod.TINTS)}, 400)
            if changes:
                hub.set_terminal(**changes)
            self._reply({"terminal": hub.cfg.terminal})
        elif self.path == "/languages":
            self._reply(hub.reload_languages())
        elif self.path == "/demo":
            threading.Thread(target=demo.run, args=(hub,), name="demo", daemon=True).start()
            self._reply({})
        elif self.path == "/shutdown":
            self._reply({})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._reply({"error": "not found"}, 404)


    def _permission(self, hub: Hub, body: dict) -> None:
        """Hold the hook's request open until the prompt is answered here or elsewhere."""
        req = hub.request_permission(body)
        if not req:
            return self._reply(None)
        while not req.done.wait(0.25):
            if self._client_gone():  # Claude Code killed the hook: you pressed Esc
                hub.abandon(req, "hook ended", interrupted=True)
            elif not req.confirmed and time.monotonic() - req.created > hub.cfg.permission_grace:
                hub.abandon(req, "answered in the terminal")
        if not req.decision:
            return self._reply(None)  # no output: Claude Code's own prompt stays in charge
        if req.decision == "answer":  # the chosen options go back as the tool's own answers field
            decision = {"behavior": "allow", "updatedInput": {**req.tool_input, "answers": req.answers}}
        else:
            decision = {"behavior": req.decision}
        if req.decision == "deny":
            decision["message"] = "Denied by the user from the claude-speaks overlay."
        self._reply({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}})

    def _listen(self, hub: Hub, body: dict) -> None:
        """Hold a session's listener hook until there is a follow-up for it."""
        sid = body.get("session_id")
        if not sid:
            return self._reply(None)
        listener = hub.listen(sid, body.get("cwd", ""))
        hub.publish()
        while not listener.wake.wait(0.5):
            if self._client_gone():  # the session exited and took its hook with it
                return hub.stop_listening(listener)
        text = hub.collect(listener)
        self._reply({"text": text} if text else None)

    def _client_gone(self) -> bool:
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True

    def _reply(self, body: dict | None = None, status: int = 200) -> None:
        try:
            self._send(body, status)
        except OSError:  # the client hung up while we were waiting
            pass


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    hub: Hub


def serve(hub: Hub, sock: str) -> Server:
    """Bind the socket (owner-only) and return the server; the caller runs serve_forever()."""
    if os.path.exists(sock):
        os.unlink(sock)
    old = os.umask(0o077)
    try:
        server = Server(sock, Handler)
    finally:
        os.umask(old)
    server.hub = hub
    return server


def main() -> int:
    cfg = Config.load()
    os.makedirs(cfg.run, mode=0o700, exist_ok=True)
    os.makedirs(cfg.state, exist_ok=True)
    lock = open(os.path.join(cfg.run, "hub.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another hub already owns the socket

    hub = Hub(cfg, make_engine(cfg.engine, cfg.kokoro_dir, cfg.speed, cfg.default_voice, cfg.voices_dir))
    if cfg.overlay.get("enabled") and overlay_mod.Overlay.available():
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overlay", "overlay.ps1")
        hub.overlay = overlay_mod.Overlay(script, cfg.overlay, on_message=hub.on_overlay,
                                          log=lambda line: log(cfg, "hub.log", line))
        if Meter.available() and not isinstance(hub.speech.engine, NullEngine):
            hub.speech.meter = Meter()  # the overlay's voice wave follows the real sound
        hub.publish()  # starts the window now, so it is ready before the first session speaks
    if sounds_mod.Sounds.available() and not isinstance(hub.speech.engine, NullEngine):
        hub.sounds = sounds_mod.Sounds(cfg.sound_volume)
    if stt.Recorder.available() and stt.Transcriber.available():
        hub.recorder = stt.Recorder(cfg.mic_source)
        hub.recorder.on_chunk = hub._mic_heard
        hub.transcriber = stt.Transcriber(cfg.whisper_model, cfg.whisper_language)
    server = serve(hub, cfg.sock)
    stop = lambda *_: threading.Thread(target=server.shutdown, daemon=True).start()  # noqa: E731
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def exit_when_idle() -> None:
        while cfg.idle_exit:
            time.sleep(30)
            with hub.lock:
                idle = not hub.sessions.by_id and time.monotonic() - hub.last_event > cfg.idle_exit
            if idle:
                log(cfg, "hub.log", "no sessions left, exiting")
                server.shutdown()
                return

    def keep_current() -> None:  # elapsed times and Claude Code's session files change without any event
        while True:
            time.sleep(1)
            hub.reconcile()
            hub.publish()

    threading.Thread(target=exit_when_idle, daemon=True).start()
    threading.Thread(target=keep_current, daemon=True).start()
    log(cfg, "hub.log", f"hub started pid={os.getpid()} engine={type(hub.speech.engine).__name__}")
    try:
        server.serve_forever()
    finally:
        hub.speech.close()
        hub.terminals.close()
        if hub.overlay:
            hub.overlay.stop()
        server.server_close()
        try:
            os.unlink(cfg.sock)
        except OSError:
            pass
        log(cfg, "hub.log", "hub stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
