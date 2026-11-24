"""Push-to-talk and what follows from it: words on their way to a session, side questions,
taking words back and stopping a turn. A part of the hub (see hub.py).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time

import base
import claude_sessions
import usage
import stt
import terminal as terminal_mod
from tts import Utterance
from base import (aside_mode, interrupts, ASIDE_ASK, Aside, BUSY, Editor, Listener, OWN_SESSION, PROMPTING_MODES, Pending,
                  SAFE_ID, STEER, Sent, Stopping, TAKE_BACK, VOICE_AT_PROMPT, _end, _spoken_name, aside_question, log,
                  session_model, spoken_answer, spoken_verdict)

CLEAR_TWICE = 3.0  # seconds the clear key's question stays up for the second press
END_TWICE = 3.0  # the same for the end key
NEW_WAIT = 60.0  # seconds after the new-session key in which the first session to start is the one it opened
CLEAR_BUSY = "it is still working"  # why a clear cannot be typed yet, and waits
SHOWN_ECHO = 1.0  # seconds in which the editor's report of a terminal the hub asked to the front is only that


class Talk:
    usage_ask = staticmethod(usage.ask)  # the call to Claude Code; the tests put their own in its place
    _usage_shown = False  # the overlay shows "Reading your usage" and nothing newer
    """The hub's methods for the talk and cancel keys. They use the hub's lock, sessions, speech and overlay."""

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
        self._push_to_mute(True)  # first, so the call hears none of the first word
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
            tap, said_to, heard = held < base.TAP, None, None
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
        finally:
            self._push_to_mute(False)
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
                    # Nothing follows a tap, so nothing else would take "Release to send" away:
                    # it stayed on the light as if the key were still held.
                    self._talk(None)
            log(self.cfg, "hub.log", f"talk: a press of {held:.2f}s, too short to be a recording")
        else:
            threading.Thread(target=self._transcribe, args=(pcm, said_to.id if said_to else None, heard),
                             daemon=True).start()
        self.publish()

    def _keep_recording(self, pcm: bytes, text: str, language: str, session: str | None) -> None:
        """Saves a recording and what it was heard as (`keep_recordings`), for a voice model later."""
        import wave
        folder = os.path.join(self.cfg.state, "recordings")
        now = time.time()
        name = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(now)) + f"_{int(now * 1000) % 1000:03d}.wav"
        try:
            os.makedirs(folder, mode=0o700, exist_ok=True)
            with wave.open(os.path.join(folder, name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(stt.RATE)
                w.writeframes(pcm)
            sess = self.sessions.by_id.get(session or "")
            line = {"file": name, "text": text, "language": language or self.cfg.whisper_language,
                    "seconds": round(len(pcm) / 2 / stt.RATE, 2), "time": time.strftime("%FT%T%z", time.localtime(now)),
                    "model": (getattr(self.transcriber, "running", "") or self.cfg.whisper_model).split(" on ")[0], "project": sess.name if sess else ""}
            with open(os.path.join(folder, "list.jsonl"), "a") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except (OSError, wave.Error) as e:  # a full disk must not lose the words themselves
            log(self.cfg, "hub.log", f"talk: the recording could not be kept: {e}")

    def _transcribe(self, pcm: bytes, session: str | None = None, job: object | None = None) -> None:
        started = time.monotonic()
        try:
            if self.transcriber:
                self.transcriber.lean = self.cfg.whisper_lean
                self.transcriber.mixed = self.cfg.whisper_mixed
            text = self.transcriber.transcribe(pcm) if self.transcriber else ""
        except Exception as e:  # a broken model must not take the hub down
            log(self.cfg, "hub.log", f"transcription failed: {e}")
            text = ""
        heard = getattr(self.transcriber, "heard", "") if text else ""
        running = getattr(self.transcriber, "running", "")
        if running and running != getattr(self, "_running_said", ""):  # once each time it changes
            self._running_said = running
            why = getattr(self.transcriber, "why_not_gpu", "")
            log(self.cfg, "hub.log", f"talk: speech model {running}" + (f" (not the graphics card: {why})" if why else ""))
        leaned = " (leaned to it: unsure, and the last language)" if text and getattr(self.transcriber, "leaned", False) else ""
        if text and getattr(self.transcriber, "parts", None):
            leaned = f" (mixed: {', '.join(self.transcriber.parts)})"
        log(self.cfg, "hub.log", f"talk: {len(pcm) / 2 / stt.RATE:.1f}s recorded, peak level {stt.loudness(pcm):.2f}, "
                                 f"transcribed in {time.monotonic() - started:.1f}s"
                                 f"{' as ' + heard if heard else ''}{leaned}: {text or '(nothing heard)'}")
        if text and self.cfg.keep_recordings:
            self._keep_recording(pcm, text, heard, session)
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
                self.follow_up(text, session, lang=heard)
        finally:
            if job is None or self._heard is job:
                self._transcribing, self._heard = False, None

    def follow_up(self, text: str, session: str | None = None, delay: float | None = None, lang: str = "") -> bool:
        """Show a follow-up, then send it to the session.

        A heard follow-up (no `delay` given) goes out after `followup_delay` (at once by default),
        or, with `followup_confirm` on, only after a confirming tap of the talk key. `lang`: the
        language the speech model heard it in, which a side question is answered in.
        """
        with self.lock:
            s = self.sessions.by_id.get(session) if session else self._target()
            if not s:
                return False
            self._cancel_pending()
            keys = self.cfg.overlay.get("hotkeys", {})
            confirm = delay is None and self._needs_confirmation(s)
            pending = self._pending = Pending(s.id, text, confirm, lang=lang)
            if confirm:
                hint = f"tap {keys.get('talk') or 'the talk key'} to send{base.gap(self.cfg, True)}{keys.get('cancel', '')} cancels"
                pending.timer = threading.Timer(base.CONFIRM_WINDOW, self._expire, args=(pending,))
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
            question = self._aside_question(s, pending.text)
            if self.cfg.clear_by_voice and base.asks_to_clear(pending.text, self.cfg.clear_words):
                self._clear_chat(s, pending.text)
            elif self.cfg.usage_by_voice and (asked := usage.asked(pending.text))[0]:
                self._ask_usage(s, pending.text, *asked)
            elif question:
                self._ask_aside(s, pending.text, question, pending.lang)
            else:
                self._hand_over(s, pending.text, pending.lang)
        self.publish()

    # --- clearing a conversation -------------------------------------------------------------

    def _clear_chat(self, s, text: str) -> None:
        """Words that order the conversation cleared: the session does not get them, its
        editor types /clear into its terminal (see `Config.clear_by_voice`). Call with the
        lock held."""
        why = self._cannot_clear(s)
        if why == CLEAR_BUSY:  # it is in a turn: cleared as soon as that ends (`_clear_when_done`)
            self._clear_after[s.id] = time.monotonic()
            self._talk("queued", s, text, seconds=3.5)
            self._signal("queued", s, "Clears when it is done.")
            log(self.cfg, "hub.log", f"clear [{s.id[:8]}] waits for the end of its turn: {text[:80]}")
            return
        if why:
            self._not_cleared(s, why, text)
            return
        if s.id in self._clearing:
            # Typed already and not yet seen done: a second /clear would land in the next
            # conversation and clear that one too (the author said it twice, 2026-11-19).
            self._talk("sent", s, "Already clearing", seconds=2.5)
            log(self.cfg, "hub.log", f"clear [{s.id[:8]}] already asked for, not typed again: {text[:80]}")
            return
        self._type_clear(s, text)

    def clear_key(self) -> None:
        """The clear key: pressed once it asks, as the mute key's banner says what it did, with
        the key that confirms beside it; pressed again within `CLEAR_TWICE` it clears the session
        in focus as "clear the chat" does, and otherwise the question goes by itself. A
        conversation cleared by a stray press could not be had back. The author, 2026-11-21:
        "double click it to confirm"; then, having seen it asked in the permission prompt's box
        with a cancel key: like "voice is muted", "Ctrl-Alt-C to confirm" at its right, gone in
        three seconds, "there's no need for the backspace to cancel that"."""
        with self.lock:
            s = self._target()
            if not s:
                return
            now, armed = time.monotonic(), self._clear_armed
            if armed and armed[0] == s.id and now - armed[1] < CLEAR_TWICE:
                self._clear_armed = None
                if self.overlay:
                    self.overlay.send({"type": "banner"})
                log(self.cfg, "hub.log", f"clear [{s.id[:8]}] asked for with the clear key")
                self._clear_chat(s, "the clear key")
            else:
                # Only the question on screen counts: the end key's, which this banner replaces, is
                # dropped (the author, 2026-11-22: clear asked, end asked, and the clear key again
                # cleared with no question on screen).
                self._clear_armed, self._end_armed = (s.id, now), None
                key = self.cfg.overlay.get("hotkeys", {}).get("clear", "")
                if self.overlay:
                    self.overlay.send({"type": "banner", "icon": "clear", "text": f"Clear {s.name}?",
                                       "hint": f"{key} to confirm" if key else "", "seconds": CLEAR_TWICE})
        self.publish()

    # --- opening and ending sessions -----------------------------------------------------------

    def new_session_key(self) -> None:
        """The new-session key (the author, 2026-11-22: "Ctrl Alt plus and Ctrl Alt minus to add a
        terminal session and remove it"): the editor opens a terminal split beside the one of the
        session in focus, in that session's folder, and starts Claude Code in it (the extension
        types `claude` itself; the hub only names the folder and the terminal to sit beside). The
        session that starts there gets the focus. With no session, or one whose terminal is in no
        editor, a terminal of its own in any editor that can open one."""
        with self.lock:
            s = self._target()
            tty = s.tty if s and s.tty else ""
            editors = [e for e in self.editors if e.opens and not e.wake.is_set()]
            editor = next((e for e in editors if tty in e.ttys), None) or next(iter(editors), None)
            if not editor:
                log(self.cfg, "hub.log", "new session not asked: no editor that can open one is waiting")
                return
            editor.open.append({"cwd": s.cwd if s else "", "beside": editor.ttys.get(tty)})
            editor.wake.set()
            self._opening = time.monotonic()
        log(self.cfg, "hub.log", f"new session asked of the editor, in {s.cwd if s else 'its own folder'}"
            + (f", beside the terminal of {s.name} ({tty})" if tty in editor.ttys else ""))

    def end_session_key(self) -> None:
        """The end key: pressed once it asks, as the clear key does; pressed again within
        `END_TWICE` the editor ends the session in focus (Escape stops a turn, Ctrl+C empties a line
        half typed, /exit ends it: measured on a working session and an idle one, 2026-11-22) and,
        once Claude Code has ended it, closes its terminal."""
        with self.lock:
            s = self._target()
            if not self._endable_here(s):
                return
            now, armed = time.monotonic(), self._end_armed
            if armed and armed[0] == s.id and now - armed[1] < END_TWICE:
                self._end_armed = None
                if self.overlay:
                    self.overlay.send({"type": "banner"})
                editor = next(e for e in self.editors if e.opens and s.tty in e.ttys and not e.wake.is_set())
                editor.keys.append({"pid": editor.ttys[s.tty], "key": "exit"})
                editor.wake.set()
                self._ending[s.id] = s.tty
                log(self.cfg, "hub.log", f"end [{s.id[:8]}] /exit asked of the editor for its terminal ({s.tty}): the end key")
            else:
                self._end_armed, self._clear_armed = (s.id, now), None  # as the clear key's question
                key = self.cfg.overlay.get("hotkeys", {}).get("end_session", "")
                if self.overlay:
                    self.overlay.send({"type": "banner", "icon": "end", "text": f"End {s.name}?",
                                       "hint": f"{key} to confirm" if key else "", "seconds": END_TWICE})
        self.publish()

    def _ended_by_key(self, sid: str) -> None:
        """A session ended: if the end key asked for it, its terminal is closed now. Call with
        the lock held."""
        tty = self._ending.pop(sid, None)
        if not tty:
            return
        for editor in self.editors:
            if editor.opens and tty in editor.ttys and not editor.wake.is_set():
                editor.close.append(editor.ttys[tty])
                editor.wake.set()
                break
        else:  # its editor is between two requests: the next one is handed it
            self._editor_wanted.append(("close", tty, time.monotonic()))
        log(self.cfg, "hub.log", f"end [{sid[:8]}] ended: its terminal ({tty}) asked closed")
        # Its own sound once it has really ended, as a clear has (or the words, in its voice).
        s = self.sessions.by_id.get(sid)
        if self.cfg.talk_feedback == "sound" and self.sounds:
            if not self._muted():
                self.sounds.play("ended")
        elif self.cfg.talk_feedback != "none" and s and not self._muted():
            self.speech.put(Utterance(text="Session ended.", voice=s.voice, kind="allowed", src="follow-up"))

    def _can_open(self) -> bool:
        """The new-session key is claimed while an editor that can open a terminal is there."""
        return any(e.opens for e in self.editors) or time.monotonic() - self._opens_by < base.EDITOR_GAP

    def _endable_here(self, s) -> bool:
        """The end key is claimed only for a session whose terminal an editor can end and close."""
        return bool(s and s.tty and any(e.opens and s.tty in e.ttys for e in self.editors))

    def _clearable_here(self, s) -> bool:
        """The clear key is claimed only for a session whose terminal an editor can type into."""
        return bool(s and s.tty and any(e.clears and s.tty in e.ttys for e in self.editors))

    def _talk_held(self) -> bool:
        """Push-to-talk is under way (key held, words being worked out or waiting for a
        go-ahead): news that comes later must not take its sign off the overlay, which shows
        one step at a time. Call with the lock held."""
        return bool(self._talking or self._transcribing or self._pending)

    def _not_cleared(self, s, why: str, text: str, late: bool = False) -> None:
        if not (late and self._talk_held()):
            self._talk("failed", s, f"Not cleared: {why}", seconds=4)
        self._signal("failed")
        log(self.cfg, "hub.log", f"clear [{s.id[:8]}] not done, {why}: {text[:80]}")

    def _clear_when_done(self) -> bool:
        """A clear said during a turn: typed once the session is back at its prompt; given up
        when no editor can type it any more or the turn runs past `CLEAR_WAIT`. Called by
        `reconcile` each second with the lock held; true when something changed."""
        changed = False
        for sid, since in list(self._clear_after.items()):
            s = self.sessions.by_id.get(sid)
            why = self._cannot_clear(s) if s else "the session is gone"
            if why == CLEAR_BUSY and time.monotonic() - since < base.CLEAR_WAIT:
                continue
            del self._clear_after[sid]
            changed = True
            if not s:
                continue
            if not why:
                self._type_clear(s, "(said during its turn, which has ended)", late=True)
            else:
                self._not_cleared(s, "its turn ran too long" if why == CLEAR_BUSY else why, "(said during its turn)", late=True)
        return changed

    def _unclear(self, sid: str, why: str) -> None:
        """Forget a clear that waited for the end of a turn. Call with the lock held."""
        if self._clear_after.pop(sid, None) is not None:
            log(self.cfg, "hub.log", f"clear [{sid[:8]}] that waited for the end of its turn dropped: {why}")

    def _type_clear(self, s, text: str, late: bool = False) -> None:
        """`late`: typed when a turn it waited for ended, so maybe while you talk to another
        session; then its light is left as it is."""
        for editor in self.editors:
            if editor.clears and s.tty in editor.ttys and not editor.wake.is_set():
                editor.keys.append({"pid": editor.ttys[s.tty], "key": "clear"})
                editor.wake.set()
                break
        else:  # its editor is between two requests: the next one is handed it
            self._clear_wanted = (s.tty, time.monotonic())
        if not (late and self._talk_held()):
            # Nothing on the light: the arc winding back to 0 shows it is done, and "sent" is for
            # words that went to a session (the author, 2026-11-21: "I don't think I should see
            # and hear the sound and the icon of sending a message").
            self._talk(None)
        log(self.cfg, "hub.log", f"clear [{s.id[:8]}] /clear asked of the editor for its terminal ({s.tty}): {text[:80]}")
        old = self._clearing.pop(s.id, None)
        if old:
            old[1].cancel()
        timer = threading.Timer(base.CLEAR_CONFIRM, self._clear_late, args=(s.id,))
        timer.daemon = True
        self._clearing[s.id] = (s.voice, timer)
        timer.start()

    def _cleared(self, sid: str, by_clear: bool) -> None:
        """The conversation of `sid` ended. If /clear had been typed for it, that is the proof
        it worked (Claude Code ends it with the reason "clear" and starts a new one in the same
        terminal): the sound of "sent", or "Chat cleared." in its voice. Call with the lock held."""
        asked = self._clearing.pop(sid, None)
        if not asked:
            return
        asked[1].cancel()
        if not by_clear:
            log(self.cfg, "hub.log", f"clear [{sid[:8]}] its session ended otherwise, not cleared")
            return
        log(self.cfg, "hub.log", f"clear [{sid[:8]}] done: Claude Code cleared the conversation")
        mode = self.cfg.talk_feedback
        if mode == "sound" and self.sounds:
            if not self._muted():
                self.sounds.play("cleared")
        elif mode != "none" and not self._muted():
            self.speech.put(Utterance(text="Chat cleared.", voice=asked[0], kind="allowed", src="follow-up"))

    def _clear_late(self, sid: str) -> None:
        """No sign of /clear having worked in `CLEAR_CONFIRM` seconds: said so on the light."""
        with self.lock:
            if not self._clearing.pop(sid, None):
                return
            s = self.sessions.by_id.get(sid)
            log(self.cfg, "hub.log", f"clear [{sid[:8]}] not seen done in {base.CLEAR_CONFIRM:.0f}s")
            if s and not self._talk_held():
                self._talk("failed", s, "Not cleared: the chat is still there", seconds=4)
            self._signal("failed")
        self.publish()

    def _cannot_clear(self, s) -> str:
        """Why /clear cannot be typed into this session's terminal now, or "". It goes with
        an Enter, which would answer whatever dialog is open there, and the hub cannot see a
        terminal: so only for a session that the hooks and Claude Code's own file both have
        at its prompt. Call with the lock held."""
        if not s.tty or not (any(e.clears and s.tty in e.ttys for e in self.editors)
                             or time.monotonic() - self._clears_by.get(s.tty, base.NEVER) < base.EDITOR_GAP):
            return "no editor to type it"
        if s.state in BUSY or s.id in self._stopping or any(r.session == s.id for r in self.requests):
            return CLEAR_BUSY
        info = claude_sessions.read(self.cfg.sessions_dir).get(s.id)
        if info and info.get("status") != "idle":
            return CLEAR_BUSY
        return ""

    # --- the plan's usage --------------------------------------------------------------------

    def _ask_usage(self, s, text: str, what: str = "usage", lang: str = "en") -> None:
        """Words that ask how much of the plan is used, or how full this session's context is
        (`what`: usage, context or both): the hub answers them itself, aloud, in the language
        they were asked in, and no session gets them. Call with the lock held."""
        self._signal("sent", s)
        log(self.cfg, "hub.log", f"{'usage' if what != 'context' else 'context'} asked by voice: {text[:80]}")
        if what == "context":  # known already: said at once
            self._talk(None)
            self._say_aside(s, usage.say_context(s.context, lang), self._voice_for(s, lang))
            return
        self._talk("aside", s, text, "Reading your usage\u2026")
        self._usage_shown = True
        threading.Thread(target=self._answer_usage, args=(s.id, what, lang), daemon=True).start()

    def _answer_usage(self, sid: str, what: str = "usage", lang: str = "en") -> None:
        line = self.usage(lang=lang)["line"]
        with self.lock:
            if self._usage_shown:  # nothing newer is on screen
                self._talk(None)
            s = self.sessions.by_id.get(sid) or self._target()
            if s:
                if what == "both":
                    line += " " + usage.say_context(s.context, lang)
                # in that session's voice (or its voice for that language), without touching its own lines
                self._say_aside(s, line, self._voice_for(s, lang))
        self.publish()

    def usage(self, quiet: bool = False, lang: str = "en") -> dict:
        """The plan's usage as it is this moment, asked of Claude Code (about a second and a
        half, no model request): the sentence to say and the figures. They are kept for the
        overlay (`plan`). `quiet`: the regular reading, which is not worth a line in the log
        each time. Not to be called with the lock held."""
        started = time.monotonic()
        try:
            text, why = self.usage_ask(self.cfg.aside_claude, 20.0)
        except Exception as e:  # nothing here may take the hub down
            text, why = "", str(e)
        read = usage.parse(text)
        line = usage.say(read, lang)
        if why or not quiet:
            log(self.cfg, "hub.log", f"usage read in {time.monotonic() - started:.1f}s: {line}" + (f" ({why[:200]})" if why else ""))
        window = lambda w: {"used": w.used, "resets": w.resets} if w else None  # noqa: E731
        got = {"line": line, "five_hour": window(read.five_hour), "week": window(read.week),
               "models": {name: window(w) for name, w in read.models.items()}}
        if got["five_hour"] or got["week"]:  # a reading that failed leaves the last figures
            with self.lock:
                self.plan = got
        return got

    def _plan_due(self) -> None:
        """Read the plan's usage again for the overlay when the last reading is old enough."""
        if not (self.cfg.usage_shown and self.overlay and self.sessions.by_id):
            return
        now = time.monotonic()
        with self.lock:
            if self._plan_busy or now - self._plan_asked < max(30.0, float(self.cfg.usage_every)):
                return
            self._plan_busy, self._plan_asked = True, now

        def read() -> None:
            try:
                self.usage(quiet=True)
            finally:
                self._plan_busy = False
            self.publish()
        threading.Thread(target=read, name="usage", daemon=True).start()

    def _plan_bars(self) -> list:
        """The plan's usage for the foot of the overlay's card: [what, percent, "warn" or ""].
        After the five hours and the week, the week of each model that has a figure of its
        own (`usage_models`: all, near = only from the warning on, none). `usage_labels`
        names the first two "5H" and "7D" or "5 hours" and "Week"."""
        plan = (self.plan if self.cfg.usage_shown else None) or {}
        warn = float(self.cfg.usage_warn or 0)
        near = lambda w: bool(warn and w["used"] >= warn)  # noqa: E731
        short = str(self.cfg.usage_labels).lower() != "long"
        bars = [[name, w] for name, w in (("5H" if short else "5 hours", plan.get("five_hour")),
                                          ("7D" if short else "Week", plan.get("week"))) if w]
        which = str(self.cfg.usage_models).lower()
        if bars and which in ("all", "near"):
            bars += [[name, w] for name, w in (plan.get("models") or {}).items() if w and (which == "all" or near(w))]
        return [[name, round(w["used"]), "warn" if near(w) else ""] for name, w in bars]

    def _hand_over(self, s, text: str, lang: str = "") -> None:
        """Words for a session go out: as the answer to the question it is asking, to its
        listener, or into the hub to wait for the end of its reply. `lang`: the language they
        were heard in, which a spoken "Sent." is said in. Call with the lock held."""
        shown = max(2.5, self.cfg.unsend_seconds)  # what went out, for as long as it can be taken back
        self._unclear(s.id, "words came after it")  # they are for this conversation; a clear first would lose them
        self._talk("sent", s, text, seconds=shown)
        asking = next((r for r in self.requests if r.session == s.id and r.question), None)
        if asking:  # it is waiting on a question, so these words are the answer to it
            self._answer(asking, text, "voice", echo=False)
            log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] given as the answer to its question")
            self._signal("sent", s, "Sent.", lang)
        else:
            prompt = next((r for r in self.requests if r.session == s.id), None)
            verdict = spoken_verdict(text) if prompt else None
            if verdict:  # a bare yes or no: the answer, as the allow and deny keys give it
                self._resolve(prompt, verdict, "voice")
                self.speech.drop_session(s.id)
                self._say(s, "Allowed." if verdict == "allow" else "Denied.",
                          "allowed" if verdict == "allow" else "denied", "decision")
                return
            if prompt and self.cfg.voice_at_prompt != "wait":
                # More to go on, said while it waits for a yes or no. A request can only be
                # allowed or refused, and Claude does not take a refusal's message for the
                # user's words, so: refused for now, its turn ended, and the words follow as
                # the next message, which it builds on with all it knows of the task.
                prompt.message = VOICE_AT_PROMPT
                self._stop_turn(s)  # first: once refused, Claude Code goes on at once, and must find the stop
                self._resolve(prompt, "deny", "voice: more details follow")
            listener = self._deliver(s, text)
            if not listener:
                self._talk("queued", s, text, seconds=max(3.5, shown))
            log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] {'sent' if listener else 'waiting for the session to stop'}")
            self._signal("sent" if listener else "queued", s, "Sent." if listener else "Queued.", lang)
        self._sent = Sent(s.id, text, time.monotonic(), answer=bool(asking))
        if self.cfg.unsend_seconds > 0:
            done = threading.Timer(self.cfg.unsend_seconds + 0.05, self.publish)  # gives the cancel key back
            done.daemon = True
            done.start()

    # --- side questions ----------------------------------------------------------------------

    def _aside_question(self, s, text: str) -> str:
        """The question in words that are a side question for this session right now, else ""."""
        mode = aside_mode(self.cfg)
        if mode not in ("busy", "always") or (mode == "busy" and s.state not in BUSY):
            return ""
        return aside_question(text, self.cfg.aside_words) if SAFE_ID.match(s.id) else ""

    def _ask_aside(self, s, text: str, question: str, lang: str = "") -> None:
        """Have a throwaway copy of the session answer a side question, in the language it was
        heard in, or the one chosen in `reply_language`. Call with the lock held."""
        self._drop_aside(self._asides.get(s.id))  # a newer question for the same session replaces the older
        fixed = base.fixed_language(self.cfg)
        lang = ("" if fixed == "en" else fixed) if fixed else lang
        aside = self._asides[s.id] = Aside(s.id, text, lang=lang)
        self._talk("aside", s, text, "Answering on the side\u2026")
        self._aside_shown = aside
        self._signal("sent", s)
        log(self.cfg, "hub.log", f"side question [{s.id[:8]}] asked: {question[:120]}")
        threading.Thread(target=self._answer_aside, args=(aside, s.cwd, question), daemon=True).start()

    def _answer_aside(self, aside: Aside, cwd: str, question: str) -> None:
        started = time.monotonic()
        try:
            answer, why = self.aside_run(aside, cwd, question)
        except Exception as e:  # no such program, no such folder
            answer, why = "", str(e)
        took = time.monotonic() - started
        with self.lock:
            if self._asides.get(aside.session) is aside:
                del self._asides[aside.session]
            shown, s = self._aside_shown is aside, self.sessions.by_id.get(aside.session)
            if shown:
                self._talk(None)
            if aside.dropped or not s:
                pass  # taken back, replaced by a newer one, or the session ended
            elif answer:
                log(self.cfg, "hub.log", f"side question [{s.id[:8]}] answered in {took:.1f}s")
                self._say_aside(s, answer, self._voice_for(s, aside.lang, answer))
            else:  # the words are not lost: the session gets them like any others
                log(self.cfg, "hub.log", f"side question [{s.id[:8]}] not answered after {took:.1f}s ({why[:200]}); "
                                         "the words go to the session instead")
                if shown:
                    self._hand_over(s, aside.text, aside.lang)
                else:  # push-to-talk is showing something newer: hand them over without a sign
                    self._deliver(s, aside.text)
        self.publish()

    def aside_run(self, aside: Aside, cwd: str, question: str) -> tuple[str, str]:
        """Ask a copy of the session and wait for it: (the answer, "") or ("", why there is none).

        `--resume` with `--fork-session` reads the session's record up to this moment under a
        new id, and `--no-session-persistence` keeps no record of the copy, so the session is
        not touched. Hooks are off for the copy: it must neither speak nor show up here as a
        session. Measured on a session in the middle of a turn: an answer in about 5 s.

        On the session's own model (`aside_model: session`) the request must begin exactly as
        the session's own requests do, or what the session has saved is not reused: same
        model, same effort, same tools. So no tool is taken away (measured: `--tools ""` and
        `--disallowedTools` both make the copy read everything anew, and so does plan mode
        for a part). Rules that make every acting tool ask keep the reuse, and asking is a
        refusal where nobody can answer: a copy told to run a command was refused."""
        program = self.cfg.aside_claude or shutil.which("claude") or os.path.expanduser("~/.local/bin/claude" + (".exe" if os.name == "nt" else ""))
        cmd = [program, "-p", "--resume", aside.session, "--fork-session", "--no-session-persistence"]
        env = {k: v for k, v in os.environ.items() if not OWN_SESSION.match(k)}
        if self.cfg.aside_model in ("", "session"):
            model, effort = session_model(self.cfg.projects_dir, aside.session)
            cmd += ["--permission-mode", "default",
                    "--settings", json.dumps({"disableAllHooks": True, "permissions": {"ask": ASIDE_ASK}})]
            cmd += ["--model", model] if model else []
            cmd += ["--effort", effort] if effort else []
        else:
            cmd += ["--settings", '{"disableAllHooks": true}', "--strict-mcp-config", "--tools", "",
                    "--model", self.cfg.aside_model]
            # Another model reads the whole conversation once and is gone. Saving it for reuse
            # costs up to twice the price of reading it, and a second question seconds later was
            # measured not to reuse it: 16 cents with the saving against 10 without.
            env["DISABLE_PROMPT_CACHING"] = "1"
        with self.lock:
            if aside.dropped:
                return "", "dropped"
            aside.proc = subprocess.Popen(cmd + ["--", base.aside_prompt(question, aside.lang)], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                          start_new_session=True)
        try:
            out, err = aside.proc.communicate(timeout=self.cfg.aside_timeout)
        except subprocess.TimeoutExpired:
            _end(aside.proc)
            aside.proc.communicate()
            return "", f"no answer in {self.cfg.aside_timeout:.0f}s"
        if aside.proc.returncode != 0:
            return "", (err or out).strip() or f"exit {aside.proc.returncode}"
        return spoken_answer(out), "" if out.strip() else "an empty answer"

    def _say_aside(self, s, answer: str, voice: str | None = None) -> None:
        """Say the answer in the session's voice (or `voice`, its voice for another language). It is not what the session said, so it neither
        replaces the session's waiting line nor is replaced by it; it is in the history, so the
        repeat key and catching up have it. Call with the lock held."""
        entry = {"time": time.time(), "session": s.id, "name": s.name, "color": s.color,
                 "spoken_name": _spoken_name(s.name), "voice": voice or s.voice, "text": answer, "kind": "aside", "heard": False}
        self.history.append(entry)
        if self._muted():
            self._flash(s, answer)  # voice is off
            entry["shown"] = True
        else:
            self.speech.put(Utterance(text=answer, voice=voice or s.voice, session=s.id, kind="notice", src="aside", entry=entry))

    def _drop_aside(self, aside: Aside | None) -> bool:
        """Stop waiting for a side question's answer. Call with the lock held."""
        if not aside or aside.dropped:
            return False
        aside.dropped = True
        if aside.proc:
            _end(aside.proc)
        return True

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
            self._leave_for_step(s.id)
        return bool(listener)

    # --- words for a busy session's next step ------------------------------------------------

    def _steer_file(self, sid: str) -> str:
        return os.path.join(self.cfg.run, "steer", sid)

    def _clear_steer(self) -> None:
        try:
            for name in os.listdir(os.path.join(self.cfg.run, "steer")):
                os.unlink(os.path.join(self.cfg.run, "steer", name))
        except OSError:
            pass

    def _leave_for_step(self, sid: str) -> None:
        """Put the words waiting for a busy session where its hook (hooks/stop.sh) finds them
        after the step it is on: Claude reads them then, within the same reply, instead of at
        its end (the author, 2026-11-21, on correcting a session while it works: "instead of
        queuing audios, I'm putting more info into the request"). They stay in followups until
        the hook has taken them, so the cancel key can still take them back. Call with the lock
        held."""
        self._sync_steer(sid)
        texts = [t for t in self.followups.get(sid, []) if t != TAKE_BACK]
        if not texts or self.cfg.followup_when != "step":
            return
        path = self._steer_file(sid)
        try:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            with os.fdopen(os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                f.write(STEER.format(text=" ".join(texts)))
            os.replace(path + ".tmp", path)
        except OSError as e:
            log(self.cfg, "hub.log", f"could not leave words for [{sid[:8]}]'s next step: {e}")
            return
        self._steering[sid] = texts

    def _sync_steer(self, sid: str) -> bool:
        """Take back the words left for a session's next step, if its hook has not taken them.
        True: they were still there (the file is gone now, the words stay in followups). False:
        the session has them, so they leave followups. Call with the lock held."""
        given = self._steering.pop(sid, None)
        if not given:
            return True
        path = self._steer_file(sid)
        claimed = os.path.join(os.path.dirname(path), f".{sid}.hub")  # the hook takes it the same way
        try:
            os.rename(path, claimed)
            os.unlink(claimed)
            return True
        except OSError:
            pass
        waiting = self.followups.get(sid, [])
        for text in given:
            if text in waiting:
                waiting.remove(text)
        if not waiting:
            self.followups.pop(sid, None)
            self._waiting.discard(sid)
        self._keep_followups()
        log(self.cfg, "hub.log", f"follow-up [{sid[:8]}] read by the session after a step")
        return False

    def _steered(self, sid: str) -> None:
        """A step of a session that had words left for it: if its hook took them, show it."""
        if sid in self._steering and not os.path.exists(self._steer_file(sid)):
            given = " ".join(self._steering.get(sid, []))
            if not self._sync_steer(sid):
                s = self.sessions.by_id.get(sid)
                if s and not (self._talking or self._transcribing or self._pending):
                    self._talk("sent", s, given, seconds=2.5, quiet=True)

    def _unsendable(self) -> Sent | None:
        """The follow-up the cancel key would take back right now, if any: one still waiting in
        the hub for a busy session, however long ago it went (the author, 2026-11-21, on a time
        limit: "I would increase into infinity"; after it, the cancel key stopped the session's
        work while the words still went to it later), or one the session got in the last
        `unsend_seconds`, which is then stopped (it would be anyway, by `cancel_stops`)."""
        sent = self._sent
        if not sent:
            return None
        if time.monotonic() - sent.at < self.cfg.unsend_seconds:
            return sent
        return sent if not sent.answer and sent.text in self.followups.get(sent.session, []) else None

    def _take_back(self) -> bool:
        """The cancel key shortly after sending: words still waiting in the hub are removed;
        words the session already has cannot be, so it is told to ignore them. Call with the
        lock held."""
        sent, self._sent = self._unsendable(), None
        s = self.sessions.by_id.get(sent.session) if sent else None
        if not s:
            return False
        self._sync_steer(s.id)  # left for its next step: back in the hub's hands, or already read
        waiting = self.followups.get(s.id, [])
        after = f"{time.monotonic() - sent.at:.1f} s after it went out"  # the log's own times are whole seconds
        if not sent.answer and sent.text in waiting:
            del waiting[len(waiting) - 1 - waiting[::-1].index(sent.text)]
            if not waiting:
                self.followups.pop(s.id, None)
                self._waiting.discard(s.id)
            self._keep_followups()
            self._leave_for_step(s.id)  # what else was waiting goes back for its next step
            self._talk("failed", s, "Taken back", seconds=2)
            log(self.cfg, "hub.log", f"follow-up [{s.id[:8]}] taken back {after}, before the session got it")
        elif interrupts(self.cfg) and self._stop_turn(s):
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
        self._stopping[s.id] = Stopping(time.monotonic(), s.state in BUSY, s.state in BUSY and self._press(s))
        self.speech.drop_session(s.id)
        return True

    def _press(self, s, key: str = "escape") -> bool:
        """Have the editor type a key into the session's terminal, if an editor that holds
        that terminal is waiting to be asked. One Escape interrupts a session that is working
        (measured: so does one Ctrl+C, but a second Ctrl+C closes the session, and a second
        Escape at an idle prompt opens its rewind list), so it is asked for once, and only of
        a session in the middle of a turn. Call with the lock held."""
        if not self.cfg.stop_at_once or not s.tty:
            return False
        for editor in self.editors:
            if s.tty in editor.ttys and not editor.wake.is_set():
                editor.keys.append({"pid": editor.ttys[s.tty], "key": key})
                editor.wake.set()
                log(self.cfg, "hub.log", f"stop [{s.id[:8]}] {key} asked of the editor for its terminal ({s.tty})")
                return True
        return False

    def editor_waits(self, pids: list, shows: bool = False, clears: bool = False, opens: bool = False,
                     theme: str = "") -> Editor:
        """An editor's window asks to be told when a key is wanted in one of its terminals,
        which it names by the process each one runs (its shell). `shows`: it can also bring
        one of them to the front. `clears`: it can also type /clear into one. `opens`: it can
        also open a terminal with a new session, end a session and close its terminal.
        `theme`: "light" or "dark", what its terminals' tint is mixed into."""
        ttys = {tty: pid for pid in pids for tty in [terminal_mod.tty_of(pid)] if tty}
        editor = Editor(ttys, shows=shows, clears=clears, opens=opens)
        repaint = False
        with self.lock:
            self.editors.append(editor)
            if theme in ("light", "dark"):
                light = self.terminals.light
                now = (light | set(ttys)) if theme == "light" else (light - set(ttys))
                repaint = now != light
                self.terminals.light = now
            if opens:
                now, kept = time.monotonic(), []
                for what, tty, since in self._editor_wanted:
                    if now - since >= base.EDITOR_GAP:
                        continue
                    if what == "close" and tty in ttys:
                        editor.close.append(ttys[tty])
                        editor.wake.set()
                    else:
                        kept.append((what, tty, since))
                self._editor_wanted = kept
            if clears:
                tty, since = self._clear_wanted
                if tty in ttys and time.monotonic() - since < base.EDITOR_GAP:  # asked for between two requests
                    editor.keys.append({"pid": ttys[tty], "key": "clear"})
                    editor.wake.set()
                    self._clear_wanted = ("", base.NEVER)
            if shows:
                tty, since = self._show_wanted
                if tty in ttys and time.monotonic() - since < base.EDITOR_GAP:  # asked for between two requests
                    editor.show.append(ttys[tty])
                    editor.wake.set()
                    self._show_wanted = ("", base.NEVER)
        if shows or repaint:
            self.publish()  # the key that goes to a terminal can act now; a new theme, its tint
        return editor

    def editor_done(self, editor: Editor) -> list:
        """Its request ends: what it is asked to type, if anything."""
        with self.lock:
            if editor in self.editors:
                self.editors.remove(editor)
            if editor.shows:
                self._shown_by.update(dict.fromkeys(editor.ttys, time.monotonic()))
            if editor.clears:
                self._clears_by.update(dict.fromkeys(editor.ttys, time.monotonic()))
            if editor.opens:
                self._opens_by = time.monotonic()
            return editor.keys

    def _showable(self, s) -> bool:
        """Whether an editor can bring this session's terminal to the front: one that holds
        it is waiting to be asked, or was a moment ago and is about to ask again. Call with
        the lock held."""
        return bool(s and s.tty) and (any(e.shows and s.tty in e.ttys for e in self.editors)
                                      or time.monotonic() - self._shown_by.get(s.tty, base.NEVER) < base.EDITOR_GAP)

    def show_terminal(self, name: str = "") -> str | None:
        """Bring the terminal of the session called `name`, or of the one in focus, to the
        front in its editor, with the keyboard in it: the way from a session chosen in the
        overlay to the place where you type to it. Only the editor can do that (see
        vscode/extension.js), and only inside its own window. Returns the session's name, or
        None when there is no such session or no editor that could show its terminal."""
        with self.lock:
            s = (next((x for x in self.sessions.by_id.values() if x.name == name), None) if name
                 else self._target())
            if not self._ask_show(s):
                return None
            found = (s.name, s.tty, s.color)
        log(self.cfg, "hub.log", f"terminal of {found[0]} ({found[1]}) asked to the front")
        self.terminals.pulse(found[1], found[2])
        return found[0]

    def _ask_show(self, s) -> bool:
        """Have the editor that holds this session's terminal bring it to the front. Only the
        newest ask counts: one still on its way to the editor is replaced, so turning the
        wheel over three sessions does not show all three in turn. Call with the lock held."""
        if not self._showable(s):
            return False
        self._shown_at[s.tty] = time.monotonic()
        for editor in self.editors:
            if editor.shows and s.tty in editor.ttys:
                if editor.wake.is_set():  # it has been woken and not answered yet
                    editor.show[:] = [editor.ttys[s.tty]]
                else:
                    editor.show.append(editor.ttys[s.tty])
                    editor.wake.set()
                return True
        self._show_wanted = (s.tty, time.monotonic())  # its editor is between two requests: the next one is handed it
        return True

    def _stop_words(self, sid: str) -> str:
        stopping = self._stopping.get(sid)
        return "Stopping" if stopping and stopping.pressed else "Stopping at its next step"

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
        s = self._target() if interrupts(self.cfg) and self.cfg.cancel_stops != "sent" else None
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
        stopped = dropped = False
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
            elif self._asides:  # a side question is being answered: that is what the key takes back
                asked = self._asides.get(about.id if about else "") or list(self._asides.values())[-1]
                dropped = self._drop_aside(asked)
                self._talk("failed", self.sessions.by_id.get(asked.session), "Cancelled", seconds=1.5)
                self._signal("failed")
                log(self.cfg, "hub.log", f"side question [{asked.session[:8]}] dropped with the cancel key")
            else:
                took_back = self._take_back()
                s = self._stoppable()
                if not took_back and s and not self.speech.current and self._stop_turn(s):
                    stopped = True
                    self._talk("stopped", s, self._stop_words(s.id), seconds=3)
                    self._signal("failed")
                    log(self.cfg, "hub.log", f"stop [{s.id[:8]}] asked for with the cancel key")
        if talking:
            self.recorder.stop()
            self._push_to_mute(False)
            self.speech.resume()
        elif not (had_pending or took_back or hearing or stopped or dropped):
            self.speech.skip()
        self.publish()

    def listen(self, sid: str, cwd: str = "") -> Listener:
        """A session's hook starts waiting for follow-ups; it replaces that session's older one."""
        with self.lock:
            if sid in self._ended:
                # A listener can outlive its conversation: after /clear, Claude Code keeps the
                # hook started for the old one running in the same terminal, and its asking
                # again brought the ended session back as a second one in the bar (2026-11-19).
                listener = Listener(sid, released=True)
                listener.wake.set()
                return listener
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
            self._sync_steer(listener.session)  # read after a step already: not again
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
                self._talk("sent", s, text, seconds=2.5, quiet=True)
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
            if self.cfg.terminal.get("jump") and self._ask_show(s):  # its terminal comes up in the editor
                log(self.cfg, "hub.log", f"terminal of {name} ({tty}) asked to the front: the focus moved to it")
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
            if time.monotonic() - self._shown_at.get(tty, base.NEVER) < SHOWN_ECHO:
                return None  # the editor only did as asked, for a focus that has moved on since
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

    def _talk(self, state: str | None, s=None, text: str = "", hint: str = "", seconds: float = 0, quiet: bool = False) -> None:
        """Tell the overlay where push-to-talk stands: listening, transcribing, ready (waiting for a
        go-ahead), sent, failed (the text says why), focus (a tap moved it), or None for nothing.
        It is shown on the session it is about; it stays until replaced unless `seconds` is given.
        `quiet`: it is news of the hub's own and not something the user is doing just now, so
        the overlay shows it on the light and leaves the bubble to a session that is speaking."""
        # A step that only reports (your words went out, it stopped) gives way to a sentence
        # that is being said; what you are doing right now (talking, a question on the side)
        # and what went wrong keep the bubble.
        quiet = quiet or (state in ("sent", "queued", "stopped", "focus") and not self.cfg.overlay.get("sent_first"))
        self._talk_shown = (state, text, hint) if state in ("listening", "ready") else None
        self._aside_shown = None  # whatever is shown now, it is not a side question being answered
        self._usage_shown = False
        if self.overlay:
            self.overlay.send({"type": "talk", "state": state, "name": s.name if s else "", "text": text,
                               "hint": hint, "seconds": seconds, **({"quiet": True} if quiet else {})} if state else {"type": "talk"})

    def _push_to_mute(self, on: bool) -> None:
        """Hold `push_to_mute_key` down while you talk, and let it go: Discord's Push to Mute,
        bound to that key, keeps the call from hearing you. The overlay presses it, on Windows."""
        key = self.cfg.push_to_mute_key if on and self.cfg.push_to_mute else ""
        if self.overlay and (key or not on):
            self.overlay.send({"type": "hold_key", "key": key})

    def _mic_heard(self, chunk: bytes) -> None:
        """A moment of the microphone while the talk key is held: the overlay shows it as a wave."""
        if self.overlay:
            self.overlay.send({"type": "mic", "levels": [self._mic_meter.level(chunk)], "step": len(chunk) / 2 / stt.RATE})
