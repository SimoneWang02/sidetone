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
import signal
import socketserver
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # run with -I, so add our own dir
from state import VOICE_POOL, Sessions, describe, speech_from_message, split_display  # noqa: E402
from tts import SpeechQueue, Utterance, make_engine  # noqa: E402

NEEDS_INPUT = ("permission_prompt", "elicitation_dialog")  # Notification types worth interrupting for


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
        for key in ("voices", "voice_pool", "label", "max_age", "idle_exit", "default_voice", "speed"):
            if key in user:
                setattr(cfg, key, user[key])
        return cfg


class Hub:
    def __init__(self, cfg: Config, engine):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.sessions = Sessions(cfg.voice_pool, cfg.voices)
        self.last_event = time.monotonic()
        self.speech = SpeechQueue(engine, max_age=cfg.max_age, label_for=self._label_for, on_done=self._log_speech)

    # --- hook events -------------------------------------------------------------------------

    def on_event(self, ev: dict) -> None:
        """Update a session from any hook payload other than MessageDisplay."""
        sid, event = ev.get("session_id"), ev.get("hook_event_name", "")
        if not sid:
            return
        with self.lock:
            self.last_event = time.monotonic()
            if event == "SessionEnd":
                self.sessions.remove(sid)
                self.speech.drop_session(sid)
                return
            s = self.sessions.touch(sid, ev.get("cwd", ""))

            if event == "UserPromptSubmit":
                s.state, s.activity, s.turn_started, s.spoken = "working", "Thinking", time.monotonic(), None
                if s.tasks and all(s.tasks.values()):
                    s.tasks.clear()
                self.speech.drop_session(sid)  # you have moved on; the old line is stale
            elif event == "PreToolUse":
                s.state, s.activity = "working", describe(ev.get("tool_name", ""), ev.get("tool_input") or {})
            elif event in ("PostToolUse", "PostToolUseFailure"):
                s.state, s.activity = "working", "Thinking"
            elif event == "TaskCreated":
                s.tasks.setdefault(ev.get("task_id", ""), False)
            elif event == "TaskCompleted":
                s.tasks[ev.get("task_id", "")] = True
            elif event == "Notification":
                if ev.get("notification_type") in NEEDS_INPUT:
                    s.state = "needs_you"
                    self._say(s, "I need your input", "needs_you", "notify")
            elif event == "Stop":
                s.state, s.activity, s.turn_started = "done", "", None
                speech = speech_from_message(str(ev.get("last_assistant_message") or ""))
                if speech and speech != s.spoken and not self._spoken_without_hub(sid, speech):
                    self._say(s, speech, "done", "stop")
                s.spoken = None
            elif event == "StopFailure":
                s.state, s.activity, s.turn_started = "failed", "", None
                error = str(ev.get("error") or "unknown").replace("_", " ")
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
        return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}

    def say(self, text: str, voice: str | None = None, kind: str = "done") -> None:
        """A line from the command line, not tied to a session."""
        self.speech.put(Utterance(text=text, voice=voice or self.cfg.default_voice, kind=kind, src="cli"))

    def snapshot(self) -> dict:
        with self.lock:
            sessions = [s.snapshot() for s in self.sessions.by_id.values()]
        return {"sessions": sessions, "muted": self._muted(), **self.speech.snapshot()}

    # --- helpers -----------------------------------------------------------------------------

    def _muted(self) -> bool:
        return os.path.exists(self.cfg.mute_file)

    def _say(self, s, text: str, kind: str, src: str) -> None:
        s.last_speech = text
        if not self._muted():
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

    def _reply(self, body: dict | None = None, status: int = 200) -> None:
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
        elif self.path == "/stop":
            hub.speech.stop_all()
            self._reply({})
        elif self.path == "/shutdown":
            self._reply({})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._reply({"error": "not found"}, 404)


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

    threading.Thread(target=exit_when_idle, daemon=True).start()
    log(cfg, "hub.log", f"hub started pid={os.getpid()} engine={type(hub.speech.engine).__name__}")
    try:
        server.serve_forever()
    finally:
        hub.speech.close()
        server.server_close()
        try:
            os.unlink(cfg.sock)
        except OSError:
            pass
        log(cfg, "hub.log", "hub stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
