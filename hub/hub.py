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
import demo  # noqa: E402
import overlay as overlay_mod  # noqa: E402
from state import (VOICE_POOL, Sessions, describe, permission_summary,  # noqa: E402
                   speech_from_message, split_display)
from tts import SpeechQueue, Utterance, make_engine  # noqa: E402

NEEDS_INPUT = ("permission_prompt", "elicitation_dialog")  # Notification types worth interrupting for
OWN_DIALOG = ("AskUserQuestion", "ExitPlanMode")  # tools whose prompt is a question, not a yes/no
MIN_SHOWN = 0.7  # a request must be on screen this long before a hotkey can answer it


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
    decision: str | None = None  # allow | deny | None (answered elsewhere)
    done: threading.Event = field(default_factory=threading.Event)


@dataclass
class Config:
    run: str  # socket and lock
    state: str  # logs
    kokoro_dir: str = ""
    engine: str = "kokoro"  # kokoro | null
    default_voice: str = "af_heart"
    speed: float = 1.1
    voices: dict = field(default_factory=dict)  # project name -> voice
    voice_pool: list = field(default_factory=lambda: list(VOICE_POOL))
    label: str = "auto"  # auto (only with several sessions) | always | never
    max_age: float = 60.0  # seconds a line may wait before it is dropped
    idle_exit: float = 1800.0  # seconds with no sessions before the hub exits; 0 = never
    # Claude Code sends a notification once a permission prompt has waited about 6 s. A request
    # with no such notification after this long was answered in the terminal.
    permission_grace: float = 9.0
    overlay: dict = field(default_factory=lambda: {**overlay_mod.DEFAULTS, "hotkeys": dict(overlay_mod.DEFAULTS["hotkeys"])})
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
            engine=env.get("CLAUDE_SPEAKS_TTS", "kokoro"),
            default_voice=env.get("KOKORO_VOICE", "af_heart"),
            speed=float(env.get("KOKORO_SPEED", "1.1")),
        )
        path = os.path.join(env.get("XDG_CONFIG_HOME") or f"{home}/.config", "claude-speaks", "config.json")
        try:
            with open(path) as f:
                user = json.load(f)
        except FileNotFoundError:
            return cfg
        for key in ("voices", "voice_pool", "label", "max_age", "idle_exit", "default_voice", "speed",
                    "permission_grace"):
            if key in user:
                setattr(cfg, key, user[key])
        wanted = user.get("overlay") or {}
        cfg.overlay.update({k: v for k, v in wanted.items() if k != "hotkeys"})
        cfg.overlay["hotkeys"].update(wanted.get("hotkeys") or {})
        if env.get("CLAUDE_SPEAKS_OVERLAY") == "off":
            cfg.overlay["enabled"] = False
        return cfg


class Hub:
    def __init__(self, cfg: Config, engine):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.sessions = Sessions(cfg.voice_pool, cfg.voices)
        self.last_event = time.monotonic()
        self.overlay = None  # anything with send(dict); set by main() or the tests
        self._shown: dict | None = None  # last state sent to the overlay, to skip repeats
        self.requests: list[Request] = []  # open permission prompts, oldest first
        self.speech = SpeechQueue(engine, max_age=cfg.max_age, label_for=self._label_for,
                                  on_change=self._speech_changed, on_done=self._log_speech)

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
                self._settle(sid, "session ended")
                self.sessions.remove(sid)
                self.speech.drop_session(sid)
                return
            s = self.sessions.touch(sid, ev.get("cwd", ""))
            if event in ("PostToolUse", "PostToolUseFailure"):  # that tool ran: its prompt was answered
                self._settle(sid, "answered in the terminal", ev.get("tool_name"), ev.get("tool_input"))
            elif event in ("UserPromptSubmit", "Stop", "StopFailure"):
                self._settle(sid, "turn moved on")

            if event == "UserPromptSubmit":
                s.state, s.activity, s.note = "working", "Thinking", ""
                s.turn_started, s.spoken = time.monotonic(), None
                if s.tasks and all(s.tasks.values()):
                    s.tasks.clear()
                self.speech.drop_session(sid)  # you have moved on; the old line is stale
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
            elif event == "Notification":
                if ev.get("notification_type") in NEEDS_INPUT:
                    waiting = [r for r in self.requests if r.session == sid and not r.confirmed]
                    if waiting:  # we know what it is asking for, so say that
                        waiting[0].confirmed = True
                        self._say(s, f"Permission needed: {waiting[0].summary}", "needs_you", "permission")
                    else:
                        s.state, s.note = "needs_you", "needs your input"
                        self._say(s, "I need your input", "needs_you", "notify")
            elif event == "Stop":
                s.state, s.activity, s.turn_started = "done", "", None
                speech = speech_from_message(str(ev.get("last_assistant_message") or ""))
                s.note = speech or "done"
                if speech and speech != s.spoken and not self._spoken_without_hub(sid, speech):
                    self._say(s, speech, "done", "stop")
                elif not speech:
                    self._flash(s, "done")  # nothing is spoken for this turn, so show it instead
                s.spoken = None
            elif event == "StopFailure":
                s.state, s.activity, s.turn_started = "failed", "", None
                error = str(ev.get("error") or "unknown").replace("_", " ")
                s.note = f"error: {error}"
                self._say(s, f"I hit an error: {error}", "failed", "stop-failure")

    def on_display(self, ev: dict) -> dict | None:
        """MessageDisplay: speak a speak-tag line as soon as it streams in; return the rewrite."""
        speech, shown = split_display(str(ev.get("delta") or ""))
        sid = ev.get("session_id")
        if not speech or not sid:
            return None
        with self.lock:
            self.last_event = time.monotonic()
            s = self.sessions.touch(sid, ev.get("cwd", ""))
            s.spoken = speech
            self._say(s, speech, "done", "stream")
        self.publish()
        return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}

    def say(self, text: str, voice: str | None = None, kind: str = "done") -> None:
        """A line from the command line, not tied to a session."""
        self.speech.put(Utterance(text=text, voice=voice or self.cfg.default_voice, kind=kind, src="cli"))

    def snapshot(self) -> dict:
        with self.lock:
            sessions = [s.snapshot() for s in self.sessions.by_id.values()]
        return {"sessions": sessions, "muted": self._muted(), **self.speech.snapshot()}

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
            if tool in OWN_DIALOG:
                s.state, s.note = "needs_you", "has a question for you" if tool == "AskUserQuestion" else "has a plan for you"
                req = None
            else:
                summary, detail = permission_summary(tool, ev.get("tool_input") or {})
                req = Request(session=sid, tool=tool, tool_input=ev.get("tool_input") or {}, summary=summary, detail=detail)
                s.state, s.note = "needs_you", f"wants to: {summary}"
                self.requests.append(req)
                self._show_request()
        self.publish()
        return req

    def decide(self, decision: str) -> bool:
        """Answer the request on screen (hotkey or command line). False if there was nothing to answer."""
        with self.lock:
            req = self.requests[0] if self.requests else None
            if not req or req.shown is None or time.monotonic() - req.shown < MIN_SHOWN:
                return False  # nothing there, or it appeared too recently to have been read
            s = self.sessions.by_id.get(req.session)
            self._resolve(req, decision, "hotkey")
            if s:
                self.speech.drop_session(s.id)  # stop "permission needed" if it is still being said
                self._say(s, "Allowed." if decision == "allow" else "Denied.",
                          "allowed" if decision == "allow" else "denied", "decision")
        self.publish()
        return True

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
            if tool is None or (req.tool == tool and req.tool_input == (tool_input or {})):
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
        self.overlay.send({
            "type": "request", "name": s.name if s else "", "text": f"wants to: {req.summary}",
            "detail": req.detail[:300],
            "keys": f"{keys.get('allow', '')} allow  \u00b7  {keys.get('deny', '')} deny" + (f"  \u00b7  {more} more waiting" if more else ""),
        })

    def on_overlay(self, msg: dict) -> None:
        if msg.get("type") == "hotkey" and msg.get("name") in ("allow", "deny"):
            self.decide(msg["name"])

    # --- overlay -----------------------------------------------------------------------------

    def publish(self) -> None:
        """Send the overlay what to draw, if it changed. Call without the lock held."""
        if not self.overlay:
            return
        current = self.speech.current
        speaking = current.session if current else None
        with self.lock:
            rows = [{
                "name": s.name,
                "state": s.state,
                "text": s.activity if s.state == "working" else s.note,
                "meta": " \u00b7 ".join(filter(None, [
                    f"{sum(s.tasks.values())}/{len(s.tasks)}" if s.tasks else "",
                    _elapsed(time.monotonic() - s.turn_started) if s.state == "working" and s.turn_started else "",
                ])),
                "speaking": s.id == speaking,
            } for s in self.sessions.by_id.values()]
            if rows == self._shown:
                return
            self._shown = rows
        self.overlay.send({"type": "state", "sessions": rows})

    def _flash(self, s, text: str, state: str | None = None) -> None:
        """Expand the overlay's dots into one line about this session for a few seconds."""
        if self.overlay:
            self.overlay.send({"type": "flash", "state": state or s.state, "name": s.name, "text": text,
                               "seconds": self.cfg.overlay.get("flash_seconds", 4)})

    def _speech_changed(self, u: Utterance | None) -> None:
        """A line starts or ends: show it while it is heard, and mark which session is speaking."""
        if u and u.session:
            with self.lock:
                s = self.sessions.by_id.get(u.session)
                if s:
                    self._flash(s, u.text, {"allowed": "done", "denied": "failed"}.get(u.kind, u.kind))
        self.publish()

    # --- helpers -----------------------------------------------------------------------------

    def _muted(self) -> bool:
        return os.path.exists(self.cfg.mute_file)

    def _say(self, s, text: str, kind: str, src: str) -> None:
        s.last_speech = text
        if self._muted():
            self._flash(s, text, {"allowed": "done", "denied": "failed"}.get(kind, kind))  # voice is off
        else:
            self.speech.put(Utterance(text=text, voice=s.voice, session=s.id, kind=kind, src=src))

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
        """The spoken project name, used only when it helps tell sessions apart."""
        with self.lock:
            s = self.sessions.by_id.get(u.session)
            several = self.sessions.active_count() > 1
        if s is None or self.cfg.label == "never" or (self.cfg.label == "auto" and not several):
            return ""
        return re.sub(r"[-_.]+", " ", s.name).strip()

    def _log_speech(self, u: Utterance, label: str, waited: float, first: float | None, outcome: str) -> None:
        timing = f"waited={waited * 1000:.0f}ms"
        if first is not None:
            timing += f" first_audio={first * 1000:.0f}ms"
        said = f"{label}. {u.text}" if label else u.text
        log(self.cfg, "voice.log", f"[{u.session[:8] or 'cli'}] src={u.src} {outcome} voice={u.voice} {timing} speech={said}")


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
            else:
                hub.overlay.send({"type": "mode", "mode": body.get("mode", "toggle")})
            self._reply({})
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
        decision = {"behavior": req.decision}
        if req.decision == "deny":
            decision["message"] = "Denied by the user from the claude-speaks overlay."
        self._reply({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}})

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

    hub = Hub(cfg, make_engine(cfg.engine, cfg.kokoro_dir, cfg.speed, cfg.default_voice))
    if cfg.overlay.get("enabled") and overlay_mod.Overlay.available():
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overlay", "overlay.ps1")
        hub.overlay = overlay_mod.Overlay(script, cfg.overlay, on_message=hub.on_overlay,
                                          log=lambda line: log(cfg, "hub.log", line))
        hub.publish()  # starts the window now, so it is ready before the first session speaks
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

    def refresh_overlay() -> None:  # elapsed times change even when no event arrives
        while True:
            time.sleep(5)
            hub.publish()

    threading.Thread(target=exit_when_idle, daemon=True).start()
    threading.Thread(target=refresh_overlay, daemon=True).start()
    log(cfg, "hub.log", f"hub started pid={os.getpid()} engine={type(hub.speech.engine).__name__}")
    try:
        server.serve_forever()
    finally:
        hub.speech.close()
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
