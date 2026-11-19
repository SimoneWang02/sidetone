#!/usr/bin/env python3
"""sidetone hub: the one local process every Claude Code hook reports to.

It keeps the voice loaded, speaks sessions one at a time, and tracks what each session is
doing. It listens on a Unix socket only, so nothing outside this user account can make it
speak. The client side is hooks/lib.sh.
"""
from __future__ import annotations

import fcntl
import glob
import json
import os
import re
import select
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import zlib
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
from state import (COLORS, FORGET_AFTER, VOICE_POOL, Sessions, describe, permission_summary, short_title,  # noqa: E402
                   lang_from_message, speech_from_message, split_display, title_from_message)
from tts import LANG_LETTER, PREFERRED_VOICE, Meter, NullEngine, SpeechQueue, Utterance, make_engine  # noqa: E402

import base  # noqa: E402
import usage  # noqa: E402
from base import (ASIDE_ASK, ASIDE_PROMPT, Aside, BUSY, CONFIRM_WINDOW, Config, EDITOR_WAIT, Editor,  # noqa: E402,F401
                  FLASH_LOOK, KEPT_LINES, Listener, MIN_SHOWN, NEEDS_INPUT, NUMBER_WORDS, OWN_DIALOG,  # noqa: E402,F401
                  OWN_SESSION, PROMPTING_MODES, Pending, Request, SAFE_ID, STOP_WAIT, Sent, Stopping,  # noqa: E402,F401
                  TAKE_BACK, TAP, VOICE_AT_PROMPT, _ago, _answerable, _elapsed, _end, _read_out, _runs,  # noqa: E402,F401
                  _same_call, _spoken_name, aside_question, context_mode, log, session_model, spoken_answer)  # noqa: E402,F401
from permissions import Permissions  # noqa: E402
from server import Handler, Server, serve  # noqa: E402,F401
from talk import Talk  # noqa: E402


# What a figure is called under the rows while it is not known (see Hub._figures).
DETAIL_NAMES = {"context": "Context", "tokens": "Last reply", "time": "Last turn", "tasks": "Tasks", "waiting": "Waiting"}


class Hub(Permissions, Talk):
    def __init__(self, cfg: Config, engine):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.sessions = Sessions(cfg.voice_pool, cfg.voices, os.path.join(cfg.state, "voices.json"), colors=cfg.colors)
        self.last_event = time.monotonic()
        self.overlay = None  # anything with send(dict); set by main() or the tests
        self.terminals = terminal_mod.Terminals(cfg.terminal)  # marks each session's own terminal
        self._shown: dict | None = None  # last state sent to the overlay, to skip repeats
        self.plan: dict | None = None  # the plan's usage as last read (see Talk.usage), for the overlay
        self._plan_asked, self._plan_busy = float("-inf"), False
        self.requests: list[Request] = []  # open permission prompts, oldest first
        self.recorder = None  # stt.Recorder, set by main() or the tests
        self.transcriber = None  # stt.Transcriber
        self.sounds = None  # sounds.Sounds, set by main() or the tests
        self.listeners: dict[str, Listener] = {}  # session id -> its waiting hook
        self.editors: list[Editor] = []  # editor windows waiting to be asked for a key
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
        self._shown_by: dict[str, float] = {}  # terminal -> when a request of an editor that can show it last ended
        self._show_wanted: tuple[str, float] = ("", base.NEVER)  # a terminal asked to the front while its editor was between two requests
        self._shown_at: dict[str, float] = {}  # terminal -> when it was last asked to the front
        self._clears_by: dict[str, float] = {}  # terminal -> when a request of an editor that can type /clear into it last ended
        self._clear_wanted: tuple[str, float] = ("", base.NEVER)  # a terminal to be cleared while its editor was between two requests
        self._clearing: dict[str, tuple] = {}  # session -> (its voice, timer) while /clear has been asked for and not yet seen done
        self._clear_after: dict[str, float] = {}  # session -> when "clear the chat" was said while it was busy: cleared once its turn ends
        self._ended: dict[str, float] = {}  # session -> when Claude Code said it ended: its listener must not bring it back
        self.history: collections.deque = collections.deque(maxlen=100)  # lines sessions said, newest last
        self._restore_sessions()
        self._talk_shown: tuple | None = None  # what the overlay shows for push-to-talk while it can still change session
        self._mic_meter = Meter()  # turns microphone audio into a loudness for the overlay
        self._talking: float | None = None  # when the talk key went down
        self._transcribing = False  # the key is up and the words are not out of the speech model yet
        self._heard: object | None = None  # that recording; the cancel key clears it, and its words are dropped
        self._pending: Pending | None = None  # the follow-up being shown
        self._sent: Sent | None = None  # the one that went out last, while it can still be taken back
        self._asides: dict[str, Aside] = {}  # session id -> the side question a copy of it is answering
        self._aside_shown: Aside | None = None  # the one the overlay shows as being answered
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
            with self.lock:
                s = self.sessions.by_id.get(ev["session_id"])
                began = s.turn_started if s else None
            self._apply(ev)
            if began and ev.get("hook_event_name") in ("Stop", "StopFailure"):
                with self.lock:
                    s = self.sessions.by_id.get(ev["session_id"])
                    if s:
                        s.turn_took = time.monotonic() - began  # how long the turn that just ended ran
            self._count_context(ev)
            self._count_turn(ev)
            self.publish()

    def _count_context(self, ev: dict) -> None:
        """How full the session's context is, from the transcript its hook names; counted when
        a reply or a step has just been written there (2 ms for the end of the file)."""
        path = ev.get("transcript_path")
        if not (context_mode(self.cfg) != "off" and path and ev.get("hook_event_name") in ("Stop", "PostToolUse", "UserPromptSubmit", "SessionStart")):
            return
        try:
            read = usage.context(str(path), int(self.cfg.context_window))
        except Exception:  # an odd transcript is no reason to lose the event
            read = None
        if read:
            with self.lock:
                s = self.sessions.by_id.get(ev["session_id"])
                if s:
                    s.context = read.percent

    def _count_turn(self, ev: dict, again: bool = True) -> None:
        """What the turn that just ended used in tokens (see Config.turn_tokens). A prompt notes
        how long the session's record is; the end of the turn adds up what came after. The
        last reply can reach the record a moment after its Stop, so it is counted once more."""
        how, event, path = self.cfg.turn_tokens, ev.get("hook_event_name"), ev.get("transcript_path")
        if how in ("off", False, None) or not path or event not in ("UserPromptSubmit", "PostToolUse", "Stop", "StopFailure"):
            return
        ended = event != "PostToolUse"  # after a step it is what the turn has used so far
        sid = ev["session_id"]
        if event == "UserPromptSubmit":
            try:
                at = os.path.getsize(str(path))
            except OSError:  # its first prompt: nothing written yet
                at = 0
            with self.lock:
                s = self.sessions.by_id.get(sid)
                if s:
                    s.turn_at, s.turn_tokens, s.turn_since = at, None, time.time()
            return
        with self.lock:
            s = self.sessions.by_id.get(sid)
            at = s.turn_at if s else None
        try:
            read = usage.turn(str(path), at)
        except Exception:  # an odd record is no reason to lose the event
            read = None
        if read:
            with self.lock:
                s = self.sessions.by_id.get(sid)
                if s and (s.state == "working") != ended:  # not a late count of a turn after the next one began
                    s.turn_tokens = read.tokens(how if isinstance(how, str) else "new")
                    # The line it ended on keeps the figure in the history. A hub that started
                    # in the middle of the turn does not know when it began: the last half minute.
                    said = [e for e in self.history if e.get("session") == sid and e.get("kind") != "aside"
                            and e["time"] >= (s.turn_since or time.time() - 30)] if ended else []
                    if said:
                        said[-1]["tokens"] = s.turn_tokens
        if again and ended:
            timer = threading.Timer(base.RECOUNT, lambda: (self._count_turn(ev, again=False), self.publish()))
            timer.daemon = True
            timer.start()

    def _apply(self, ev: dict) -> None:
        sid, event = ev["session_id"], ev.get("hook_event_name", "")
        with self.lock:
            self.last_event = time.monotonic()
            if event == "SessionEnd":
                self._cleared(sid, ev.get("reason") == "clear")
                if ev.get("reason") == "clear":
                    # The chat is gone, so are its lines: the session that follows in the same
                    # terminal gets the same name, and the history (kept by name) showed them.
                    self.history = collections.deque((e for e in self.history if e.get("session") != sid),
                                                     maxlen=self.history.maxlen)
                self._forget(sid, "session ended")
                now = time.monotonic()
                self._ended = {k: v for k, v in self._ended.items() if now - v < 3600}
                self._ended[sid] = now
                return
            if sid in self._ended:  # an event of it that came after its end (hooks report on their own)
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
                    self._unclear(sid, "a new prompt was typed")  # clearing after it would throw it away
                    # You are at that session: what you say next is for it. Not in the middle
                    # of push-to-talk, where the words already have their session.
                    if self.cfg.focus_on_prompt and self._target() is not s and not (self._talking or self._transcribing or self._pending):
                        self._focus_on(s)
                        log(self.cfg, "hub.log", f"focus on {s.name}: a prompt was typed to it")
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
                            self._say(s, _read_out(waiting[0].question, waiting[0].place), "needs_you", "question")
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
                    self._say(s, speech, "done", "stop", self._voice_for(s, lang_from_message(message)))
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
        self._clear_after.pop(sid, None)
        self._drop_aside(self._asides.get(sid))
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
        self._plan_due()
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
            # A command allowed in the terminal: no hook says so, and the session went on showing
            # "needs you" until the command was done, minutes later for a long one. But the
            # command then starts, as a child of the session that was not there when it asked.
            for req in [r for r in self.requests if r.shells is not None]:
                pid = (live.get(req.session) or {}).get("pid")
                started = [line for shell, line in claude_sessions.tool_shells(pid).items()
                           if shell not in req.shells] if pid else []
                if any(_runs(line, str(req.tool_input.get("command") or "")) for line in started):
                    self._resolve(req, None, "allowed in the terminal: its command is running")
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
                    if not stopping.pressed:  # it had not begun when it was asked, or no editor was waiting yet
                        stopping.pressed = self._press(s)
                elif stopping.busy or time.monotonic() - stopping.at > STOP_WAIT:
                    if stopping.pressed and stopping.busy:
                        s.note = "stopped"
                        if not (self._talking or self._transcribing or self._pending):
                            self._talk("stopped", s, "Stopped", seconds=2.5)
                    self._unstop(sid, "Escape in its terminal ended the turn" if stopping.pressed else "its turn ended by itself")
                    changed = True
            # Words that waited for a busy session go out once it is no longer busy. After a
            # reply that happens by itself (its new listener asks for them); after an interrupt
            # no hook runs, so the listener it has had since its last prompt is woken here.
            for sid, waiting in self.followups.items():
                s, listener = self.sessions.by_id.get(sid), self.listeners.get(sid)
                if waiting and s and listener and not listener.wake.is_set() and s.state not in BUSY:
                    listener.wake.set()
                    log(self.cfg, "hub.log", f"follow-up [{sid[:8]}] sent, now that the session has stopped")
            if self._clear_after:
                changed = self._clear_when_done() or changed
        if changed:
            self.publish()

    def on_display(self, ev: dict) -> dict | None:
        """MessageDisplay: speak a speak-tag line as soon as it streams in; return the rewrite."""
        speech, shown, title, lang = split_display(str(ev.get("delta") or ""))
        sid = ev.get("session_id")
        if not speech or not sid:
            return None
        with self.lock:
            self.last_event = time.monotonic()
            s = self.sessions.touch(sid, ev.get("cwd", ""))
            s.spoken = speech
            self._title_from(s, reply=speech, given=title)
            self._say(s, speech, "done", "stream", self._voice_for(s, lang))
        self.publish()
        return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}

    def _voice_for(self, s, lang: str) -> str | None:
        """The voice for a line in another language than English: one of Kokoro's voices for
        that language, of the same kind (female or male) as the session's own where there is
        one, and always the same for a session. None = the session's own voice, for English,
        for a language Kokoro has no voice for, and with `reply_language: english`."""
        if not lang or lang == "en" or self.cfg.reply_language == "english":
            return None
        engine = self.speech.engine
        for wanted in (self.cfg.language_voices.get(lang), PREFERRED_VOICE.get(lang)):
            pool = [v for v in ([wanted] if isinstance(wanted, str) else wanted or [])
                    if isinstance(v, str) and hasattr(engine, "has") and engine.has(v)]
            if pool:
                return self._share(s, lang, pool)
        letter = LANG_LETTER.get(lang)
        known = getattr(self.speech.engine, "voices", None) or ()
        choices = sorted(v for v in known if letter and re.fullmatch(letter + r"[fm]_\w+", v))
        if not choices:
            return None
        kind = s.voice[1:2] if re.fullmatch(r"[a-z][fm]_\w+", s.voice or "") else ""
        same = [v for v in choices if v[1] == kind] or choices
        return same[zlib.crc32(s.name.encode()) % len(same)]

    def _share(self, s, lang: str, pool: list) -> str:
        """A voice of `pool` for this session's lines in `lang`: the one it had, else the first
        that no other open session speaks that language with, else one by its name."""
        chosen = self.__dict__.setdefault("_lang_voices", {})
        live = {x.name for x in self.sessions.by_id.values()}
        mine = chosen.get((lang, s.name))
        if mine in pool:
            return mine
        taken = {v for (lg, name), v in chosen.items() if lg == lang and name != s.name and name in live}
        pick = next((v for v in pool if v not in taken), pool[zlib.crc32(s.name.encode()) % len(pool)])
        chosen[(lang, s.name)] = pick
        return pick

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

    def say(self, text: str, voice: str | None = None, kind: str = "notice", session: str = "") -> None:
        """A line from the command line. `session`: the session whose command it is (its Bash
        tool hands every command the session's id), and then it is that session's line, a
        word on the way: its voice unless one is named, its bubble and wave in the overlay,
        and a place in its history. Without one it is tied to no session and only heard."""
        with self.lock:
            s = self.sessions.by_id.get(session) if session else None
            if s:
                self._say(s, text, "progress", "cli", voice)
        if not s and not self._muted():  # muted: nothing to show it on, so it is only left unsaid
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
            s = self.sessions.by_id.get(entry.get("session", ""))
            live = s is not None
            if live and self._muted():
                # The voice is off: shown at its light instead (the author pressed repeat while
                # muted, 2026-11-19, and heard the line).
                self._flash(s, entry["text"], FLASH_LOOK.get(entry.get("kind", ""), entry.get("kind") or None))
        if self._muted():
            self.publish()
            return
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
            return f"no voice called {voice}; see: sidetone voices"
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
        to_say = {id(u.entry) for u in self.speech.waiting() if u.entry is not None}  # asked for before our own lock is taken
        context = context_mode(self.cfg)
        # A row's right end: what the settings name, and what older settings still ask for there.
        in_row = list(self.cfg.row_metrics) + ["waiting"] * bool(self.cfg.waiting_words) + ["context"] * (context in ("text", "both"))
        with self.lock:
            rows = [{
                "name": s.name,
                "color": s.color,
                "state": s.state,
                "title": s.title,
                "text": self._stop_words(s.id) if s.id in self._stopping else s.activity if s.state == "working" else s.note,
                "meta": base.gap(self.cfg).join(figures[key][0] for key in in_row if figures.get(key, ("",))[0]),
                # Its figures for under the rows, each [what it is, the figure, its share of a
                # whole or None, "warn" or ""], in the order of the settings. One that is not
                # known is not left out: its figure is "", so that each keeps its place.
                "details": [list(figures[key][1:]) if figures.get(key) else [DETAIL_NAMES.get(key, str(key)), "", None, ""]
                            for key in self.cfg.detail_metrics],
                "context": s.context if context in ("arc", "both") else None,  # percent of its window: the arc around its light
                "waiting": self._waiting_count(s.id),  # words of yours it has not been handed yet
                "speaking": s.id == speaking,
                "target": len(self.sessions.by_id) > 1 and self._target() is s,  # in focus: follow-ups go here
                "synth": not self.speech.meter,  # no real loudness to draw: the overlay makes up a motion
            } for s in self.sessions.by_id.values() for figures in [self._figures(s)]]
            asking = self.requests[0].question if self.requests else None
            keys = sorted(([f"option{i}" for i in range(1, len(asking["options"]) + 1)]
                           + (["allow"] if asking.get("multiSelect") else []) if asking
                           else ["allow", "deny"] if self.requests else [])
                          + (["cancel"] if self._talking or self._transcribing or self._pending or current or self._unsendable()
                             or self._asides or self._stoppable() else [])
                          + (["focus_next", "focus_prev"] if len(self.sessions.by_id) > 1 else [])
                          + (["jump"] if self._showable(self._target()) else []))
            now = time.time()
            # Newest first, and up to four lines of each session: the overlay shows those of the
            # session under the mouse, so one that talks a lot must not push the others out.
            each, history = collections.Counter(), []
            for e in reversed(self.history):
                if each[e["name"]] < 4 and len(history) < 24:
                    each[e["name"]] += 1
                    history.append({"ago": _ago(now - e["time"]) if self.cfg.history_time else "", "name": e["name"], "color": e.get("color", ""), "text": e["text"],
                                    "tokens": usage.tokens_text(e["tokens"]) if self.cfg.turn_tokens_history and e.get("tokens") else "",
                                    # How that turn ended (done, failed, needs_you, progress, aside), for a
                                    # mark in front of the line; and whether it was never heard to its end:
                                    # cut off, too old when its turn came, or replaced by a newer one.
                                    "kind": e.get("kind", ""),
                                    "missed": self.cfg.history_missed and not (e.get("heard") or e.get("shown") or id(e) in to_say)})
            new_keys, self._keys = keys != self._keys, keys
            bars = self._plan_bars()
            muted = self._muted()
            new_rows, self._shown = (rows, history, bars, muted) != self._shown, (rows, history, bars, muted)
        if new_keys:  # claim allow/deny/cancel only while they can do something
            self.overlay.send({"type": "keys", "live": keys})
        if new_rows:
            self.overlay.send({"type": "state", "sessions": rows, "history": history, "usage": bars, "muted": muted})

    def _figures(self, s) -> dict:
        """What can be said in figures about a session right now. For each (see
        Config.row_metrics): how the right end of its row writes it ("" = not there), what
        it is called under the rows, the figure there, how much of a whole it is (0 to 1, for
        a small bar; None = no whole) and "warn" when that is nearly all of it. Call with the
        lock held."""
        working, waiting, found = s.state == "working", self._waiting_count(s.id), {}
        if s.tasks:
            done, of = sum(s.tasks.values()), len(s.tasks)
            found["tasks"] = (f"{done}/{of}", "Tasks", f"{done}/{of}", done / of, "")
        if working and s.turn_started:
            ran = _elapsed(time.monotonic() - s.turn_started)
            found["time"] = (ran, "This turn", ran, None, "")
        elif s.turn_took is not None:
            found["time"] = ("", "Last turn", _elapsed(s.turn_took), None, "")
        if waiting:
            found["waiting"] = ("1 message waiting" if waiting == 1 else f"{waiting} messages waiting", "Waiting", str(waiting), None, "")
        if s.context is not None and context_mode(self.cfg) != "off":
            warn = float(self.cfg.overlay.get("context_warn") or 0)
            found["context"] = (f"context {s.context:.0f}%", "Context", f"{s.context:.0f}%", s.context / 100,
                                "warn" if warn and s.context >= warn else "")
        if s.turn_tokens:
            used = usage.tokens_text(s.turn_tokens)
            found["tokens"] = ("" if working else f"{used} {self.cfg.turn_tokens_label}".strip(),
                               "This reply" if working else "Last reply", used, None, "")
        return found

    def _waiting_count(self, sid: str) -> int:
        return len(self.followups.get(sid, ())) if sid in self._waiting else 0

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

    def _say(self, s, text: str, kind: str, src: str, voice: str | None = None) -> None:
        if s.id in self._stopping and kind in ("done", "progress"):
            log(self.cfg, "hub.log", f"stop [{s.id[:8]}] not spoken, its turn is being stopped: {text[:80]}")
            return
        s.last_speech = text
        entry = None
        if kind in ("done", "failed", "needs_you", "progress"):  # what a session said, not our own feedback
            entry = {"time": time.time(), "session": s.id, "name": s.name, "color": s.color,
                     "spoken_name": _spoken_name(s.name), "voice": voice or s.voice, "text": text, "kind": kind, "heard": False}
            self.history.append(entry)
        if self._muted():
            self._flash(s, text, FLASH_LOOK.get(kind, kind))  # voice is off
            if entry:
                entry["shown"] = True  # read, not heard: nothing was missed
        else:
            self.speech.put(Utterance(text=text, voice=voice or s.voice, session=s.id, kind=kind, src=src, entry=entry))

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
