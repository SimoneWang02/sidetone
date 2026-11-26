"""Permission prompts and questions: what a session asks is shown, said, and answered with
the keys or by voice. A part of the hub (see hub.py), which is the only thing that uses it.
"""
from __future__ import annotations

import json
import time

import base
import claude_sessions
import overlay as overlay_mod
import settings as settings_mod
import stt
from state import permission_summary
from base import OWN_DIALOG, Request, _answerable, _read_out, _same_call, log


class Permissions:
    """The hub's methods for requests. They use the hub's lock, sessions, speech and overlay."""

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
                if tool == "Bash":  # to see it start, should it be allowed in the terminal (see reconcile)
                    pid = (claude_sessions.read(self.cfg.sessions_dir).get(sid) or {}).get("pid")
                    req.shells = set(claude_sessions.tool_shells(pid)) if pid else None
                s.state, s.note = "needs_you", f"wants to: {summary}"
            if req:
                req.agent = str(ev.get("agent_id") or "")
                self.requests.append(req)
                self._show_request()
        self.publish()
        return req

    def decide(self, decision: str) -> bool:
        """Answer the request on screen (hotkey or command line). False if there was nothing to answer."""
        with self.lock:
            req = self.requests[0] if self.requests else None
            if not req or req.shown is None or time.monotonic() - req.shown < base.MIN_SHOWN:
                return False  # nothing there, or it appeared too recently to have been read
            s = self.sessions.by_id.get(req.session)
            if req.question:  # only a question with choices to tick takes the allow key: it hands them in
                ticked = [o["label"] for i, o in enumerate(req.question["options"]) if i in req.ticked]
                if not (req.question.get("multiSelect") and decision == "allow" and ticked):
                    return False
                self._answer(req, ", ".join(ticked), "hotkey")  # how Claude Code itself writes several choices
            else:
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
            if (not question or req.shown is None or time.monotonic() - req.shown < base.MIN_SHOWN
                    or not 1 <= number <= len(question["options"])):
                return False
            label = question["options"][number - 1]["label"]
            if question.get("multiSelect"):  # tick or untick; the allow key hands the ticked ones in
                on = number - 1 not in req.ticked
                (req.ticked.add if on else req.ticked.discard)(number - 1)
                if req.session in self.sessions.by_id:
                    self.speech.drop_session(req.session)  # stop reading the options out
                self._show_request()  # the box shows it; said aloud at every press it was a nuisance
            else:
                self._answer(req, label, "hotkey")
        self.publish()
        return True

    def _answer(self, req: Request, answer: str, why: str, echo: bool = True) -> None:
        """Give `answer` to the question on screen: an option's label, or with `why` "voice" the
        user's own words (Claude gets them as it gets a typed "Other"). After the last question
        the hook hands all answers to Claude. `echo` answers with the sound for "sent" (or says
        the answer back, see `Config.talk_feedback`). Call with the lock held."""
        req.answers[req.question["question"]] = answer
        req.ticked.clear()  # the next question starts with nothing ticked
        s = self.sessions.by_id.get(req.session)
        if s:
            self.speech.drop_session(s.id)  # stop reading the options out
        if req.question:  # more questions in the same prompt: on to the next
            req.shown = time.monotonic()
            if s:
                s.note = f"asks: {req.question['question']}"
                said = f"{answer}. " if echo and self.cfg.talk_feedback == "voice" else ""
                self._say(s, f"{said}Next. {_read_out(req.question, req.place)}", "needs_you", "question")
            self._show_request()
        else:
            self._resolve(req, "answer", why)
            if s and echo:  # a short sound; the answer itself is only said back with talk_feedback "voice"
                self._signal("sent", s, f"Answered: {answer}.")

    def abandon(self, req: Request, why: str, interrupted: bool = False) -> None:
        """The request ended without the hub answering it (answered in the terminal, hook killed...)."""
        with self.lock:
            s = self.sessions.by_id.get(req.session)
            self._resolve(req, None, why)
            if interrupted and s and not req.decision:
                s.state, s.activity, s.note, s.turn_started = "idle", "", "interrupted", None
        self.publish()

    def _settle(self, sid: str, why: str, tool: str | None = None, tool_input: dict | None = None, agents: bool = False) -> None:
        """Close a session's open requests; with a tool given, only the one for that exact call.
        Without one (its turn moved on), not those of its subagents: one sent to the background
        goes on after the turn that started it has ended, and its prompt is still open (found in
        the lab, 2026-11-22: the allow key and a spoken yes could not answer it). `agents`: those
        too (the session has ended)."""
        for req in [r for r in self.requests if r.session == sid]:
            if tool is None and req.agent and not agents:
                continue
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
        wide = base.gap(self.cfg, True)  # between the parts of the line about the keys
        if req.question:
            options, several = req.question["options"], bool(req.question.get("multiSelect"))
            self.overlay.send({
                "type": "request", "name": s.name if s else "", "color": s.color if s else "",
                "text": f"asks: {req.question['question']}",
                "question": req.question["question"],  # written on a line of its own under the name
                "place": req.place,  # "1 of 2", beside the name
                # Drawn one to a line: behind its number, or, with several to tick, behind a box.
                "options": [o["label"] for o in options],
                **({"ticked": [i in req.ticked for i in range(len(options))]} if several else {}),
                "detail": "\n".join(f"{i}  {o['label']}" for i, o in enumerate(options, 1)),
                # The same as parts, for key caps: [the keys, what they do, the last key of a range or ""].
                "hints": [h for h in ([keys.get("option1", ""), "tick" if several else "answers",
                                       str(keys.get(f"option{len(options)}", "")).rpartition("+")[2]],
                                      [keys.get("allow", ""), "confirms", ""] if several else None) if h and h[0]],
                "more": more,
                "keys": f"{keys.get('option1', '')} to {keys.get(f'option{len(options)}', '')} "
                        + (f"tick{wide}{keys.get('allow', '')} confirms" if several else "answers")
                        + (f"{wide}{more} more waiting" if more else ""),
            })
            return
        self.overlay.send({
            "type": "request", "name": s.name if s else "", "color": s.color if s else "", "text": f"wants to: {req.summary}",
            "detail": req.detail[:300],
            "hints": [h for h in ([keys.get("allow", ""), "allow", ""], [keys.get("deny", ""), "deny", ""]) if h[0]],
            "more": more,
            "keys": f"{keys.get('allow', '')} allow{wide}{keys.get('deny', '')} deny" + (f"{wide}{more} more waiting" if more else ""),
        })

    def place_overlay(self, tell_window: bool = True, **changes) -> None:
        """Change where the overlay sits (monitor, corner, offsets) and remember it."""
        self.cfg.overlay.update(changes)
        if tell_window and self.overlay and hasattr(self.overlay, "reconfigure"):
            self.overlay.reconfigure()
        self._save_settings("overlay", changes)

    def _save_settings(self, section: str, changes: dict) -> None:
        """Write settings chosen while running into that section of the user's config.json."""
        settings_mod.save_all(self.cfg, [([section, key], value) for key, value in changes.items()])

    def reload_languages(self) -> dict:
        """Take up the languages chosen with `sidetone languages` (written to config.json)
        without a restart: the next push-to-talk loads the model for them."""
        try:
            with open(self.cfg.config_path) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        engine = self.speech.engine
        if hasattr(engine, "reload_zh"):  # `sidetone languages` may have just installed Chinese
            engine.reload_zh()
        model = saved.get("whisper_model") or self.cfg.whisper_model
        language = saved.get("whisper_language") or self.cfg.whisper_language
        if (model, language) != (self.cfg.whisper_model, self.cfg.whisper_language):
            self.cfg.whisper_model, self.cfg.whisper_language = model, language
            if self.transcriber:
                self.transcriber = stt.Transcriber(model, language, self.cfg.whisper_device, self.cfg.whisper_gpu_model)
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

    # --- the settings window (what it offers and what a choice does: settings.py) -----------

    _settings_open = False

    def show_settings(self, open: bool | None = None) -> bool:
        """Open or close the settings window. None = the key: the window shuts if it is in
        front of you and comes to the front if it is not, which only the window can tell (it
        may be open behind another program); it says so if it shut."""
        self._settings_open = True if open is None else bool(open)
        if self.overlay:
            self.overlay.send({"type": "settings", "open": True, "title": settings_mod.NAME, "sections": settings_mod.describe(self), **({"toggle": True} if open is None else {})}
                              if self._settings_open else {"type": "settings", "open": False})
        return self._settings_open

    def toggle_mute(self) -> bool:
        """The mute key: the voice off for every session, or on again (the same as `sidetone
        off` and `on`). Muting cuts the line being said and drops those waiting; while muted,
        what sessions say is shown instead. Answered with a sound and a moment's notice on the
        overlay. Returns True if the voice is now off."""
        muted = not self._muted()
        if muted and self.sounds and self.cfg.talk_feedback != "none":
            self.sounds.play("voice_off")  # before the file: sounds are quiet while muted
        settings_mod.apply(self, "mute", muted)
        if not muted and self.sounds and self.cfg.talk_feedback != "none":
            self.sounds.play("voice_on")
        log(self.cfg, "hub.log", "voice " + ("off" if muted else "on") + " (mute key)")
        if self.overlay:
            key = self.cfg.overlay.get("hotkeys", {}).get("mute", "")
            # The same row as the details show while muted (Overlay.VoiceRow), the key beside the words.
            # It takes the place of a clear or end question, which no longer counts.
            self._clear_armed = self._end_armed = None
            self._clear_shown = ""
            self.overlay.send({"type": "banner", "icon": "muted" if muted else "voice",
                               "text": "Voice is muted" if muted else "Voice is on",
                               "hint": f"{key} turns it on" if muted and key else "",
                               "seconds": 2.5 if muted else 1.5})
        if self._settings_open and self.overlay:
            self.overlay.send({"type": "settings", "open": True, "title": settings_mod.NAME, "sections": settings_mod.describe(self)})
        return muted

    def mute_session(self, name: str | None = None, muted: bool | None = None) -> tuple[str, bool] | None:
        """The key that mutes one session: the voice off for the session in focus (or the one of
        that name), or on again, while the others go on speaking. `muted`: what it should be, or
        None to change it over. Muting cuts its line being said and drops those it has waiting,
        but not its asking for you while `muted_asks` is on. Answered like the mute key: a
        sound, and a moment's notice with the session's name. Returns its name and whether it is
        now muted, or None when there is no such session."""
        with self.lock:
            s = (next((x for x in self.sessions.by_id.values() if x.name == name), None) if name else self._target())
            if not s or s.standin:
                return None
            was, s.muted = s.muted, (not s.muted) if muted is None else bool(muted)
            label, now, sid = s.name, s.muted, s.id
        if now == was:
            return label, now
        if now:
            if self.sounds and self.cfg.talk_feedback != "none" and not self._muted():
                self.sounds.play("voice_off")
            self.speech.drop_session(sid, spare=("needs_you",) if self.cfg.muted_asks else ())
        elif self.sounds and self.cfg.talk_feedback != "none" and not self._muted():
            self.sounds.play("voice_on")
        log(self.cfg, "hub.log", f"voice {'off' if now else 'on'} for {label} alone")
        if self.overlay:
            key = self.cfg.overlay.get("hotkeys", {}).get("mute_session", "")
            self._clear_armed = self._end_armed = None  # as the mute key: its row takes the place of a question
            self._clear_shown = ""
            self.overlay.send({"type": "banner", "icon": "muted" if now else "voice",
                               "text": f"{label} is muted" if now else f"{label} is unmuted",
                               "hint": f"{key} turns it on" if now and key else "",
                               "seconds": 2.5 if now else 1.5})
        self.publish()
        return label, now

    def set_setting(self, key: str, value) -> str | None:
        """Something was chosen, in the window or with `sidetone settings KEY VALUE` (the key
        `reset` with a section's name puts that section back as a new install has it). Returns
        what is wrong with it, or None. The window is then told how things stand: it draws
        what the hub has, so a choice that was not taken does not look as if it were."""
        if key == "play":  # the ▶ beside a voice: heard, nothing changed
            settings_mod.preview(self, str(value or ""))
            return None
        if key == "stop_preview":  # the square that stands in for the ▶ while it plays
            self.speech.drop_src("preview")
            return None
        error = settings_mod.reset(self, value) if key == "reset" else settings_mod.apply(self, key, value)
        if error:
            log(self.cfg, "hub.log", f"setting not changed: {error}")
        if self._settings_open and self.overlay:
            self.overlay.send({"type": "settings", "open": True, "title": settings_mod.NAME, "sections": settings_mod.describe(self)})
        return error

    def on_overlay(self, msg: dict) -> None:
        if msg.get("type") == "ready":
            # A window that has just started is handed the sessions again by its own module, and
            # nothing else: tell it the question that is still open and the keys that are live.
            self._settings_open = False  # a new window has no settings open
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
        if msg.get("type") == "reorder":  # a light dragged to another place in the bar: kept so
            names = msg.get("names")
            with self.lock:
                moved = isinstance(names, list) and self.sessions.reorder([str(n) for n in names])
            if moved:
                log(self.cfg, "hub.log", "sessions put in a new order: " + ", ".join(map(str, names)))
                self.publish()
            return
        if msg.get("type") == "mode":  # details kept out, or only the lights: the same after a hub restart
            if msg.get("mode") in ("dots", "list", "focus"):
                self.place_overlay(False, mode=msg["mode"])
            return
        if msg.get("type") == "setting":  # chosen in the settings window
            self.set_setting(str(msg.get("key", "")), msg.get("value"))
            return
        if msg.get("type") == "settings":  # the window was closed there
            self._settings_open = bool(msg.get("open"))
            return
        if msg.get("type") != "hotkey":
            return
        name = msg.get("name")
        if name in ("allow", "deny"):
            self.decide(name)
        elif name and name.startswith("option"):
            self.choose(int(name[6:]))
        elif name == "repeat":
            self.repeat()
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
        elif name == "jump":
            self.show_terminal()
        elif name == "clear":
            self.clear_key()
        elif name == "new_session":
            self.new_session_key()
        elif name == "end_session":
            self.end_session_key()
        elif name == "settings":
            self.show_settings()
        elif name == "mute":
            self.toggle_mute()
        elif name == "mute_session":
            self.mute_session()
