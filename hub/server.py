"""The hub's door: HTTP over a Unix socket, one small request per hook or command.

Where there are no Unix sockets for Python (Windows), or when SIDETONE_TRANSPORT=tcp, the door
is a port on 127.0.0.1 instead, which any program on the machine and any web page could reach:
so every request must carry a token that only the user's own files hold (`hub.addr`, beside the
lock, "PORT TOKEN"), a request a browser sends (it has an Origin header) is refused, and the Host
must be this machine, against a web page that renames itself to 127.0.0.1.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import select
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler

import demo
import settings as settings_mod
import terminal as terminal_mod
from base import EDITOR_WAIT


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        token = getattr(self.server, "token", "")
        if not token:
            return True  # the Unix socket: only the owner can open it at all
        host = (self.headers.get("Host") or "").split(":")[0]
        if (self.headers.get("Origin") is not None or host not in ("127.0.0.1", "localhost")
                or not hmac.compare_digest(self.headers.get("X-Sidetone-Token", ""), token)):
            self.send_error(403)
            return False
        return True

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
            hub.say(str(body.get("text", "")), body.get("voice"), body.get("kind", "done"), str(body.get("session") or ""))
            self._reply({})
        elif self.path == "/permission":
            self._permission(hub, body)
        elif self.path == "/listen":
            self._listen(hub, body)
        elif self.path == "/editor":
            self._editor(hub, body)
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
        elif self.path == "/usage":  # the plan's usage now; said aloud too with {"say": true}
            read = hub.usage()
            if body.get("say"):
                with hub.lock:
                    s = hub._target()
                    if s:
                        hub._say_aside(s, read["line"])
            self._reply(read)
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
        elif self.path == "/press":  # the push-to-mute key pressed once, for Discord to record (sidetone discord-key)
            key = str(body.get("key") or hub.cfg.push_to_mute_key)
            if not hub.overlay:
                return self._reply({"pressed": False})
            hub.overlay.send({"type": "hold_key", "key": key})
            threading.Timer(0.3, hub.overlay.send, args=({"type": "hold_key", "key": ""},)).start()
            self._reply({"pressed": True, "key": key})
        elif self.path == "/sound":  # to hear what a sound is like
            self._reply({"played": bool(hub.sounds and hub.sounds.play(str(body.get("name", ""))))})
        elif self.path == "/answer":
            self._reply({"answered": hub.choose(int(body.get("option") or 0))})
        elif self.path == "/replay":
            self._reply({"count": int(hub.repeat())})
        elif self.path == "/decide":
            self._reply({"answered": hub.decide("allow" if body.get("decision") == "allow" else "deny")})
        elif self.path == "/stop":
            hub.speech.stop_all()
            self._reply({})
        elif self.path == "/settings":  # the settings window, or one setting from the command line
            if "key" in body:
                error = hub.set_setting(str(body["key"]), body.get("value"))
                return self._reply({"error": error})
            if body.get("list"):
                return self._reply({"sections": settings_mod.describe(hub)})
            if not hub.overlay:
                return self._reply({"error": "the settings window needs the overlay, which is not available here"}, 409)
            self._reply({"open": hub.show_settings(body.get("open"))})
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
            if "show" in body:  # have the editor bring one session's terminal to the front
                return self._reply({"shown": hub.show_terminal(str(body["show"] or ""))})
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
            decision["message"] = req.message or "Denied by the user from the sidetone overlay."
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

    def _editor(self, hub: Hub, body: dict) -> None:
        """Hold an editor's request until a key is wanted in one of its terminals, or for a
        while; it asks again at once (and anew when its terminals change)."""
        try:
            pids = [int(pid) for pid in body.get("terminals") or []]
        except (TypeError, ValueError):
            return self._reply({"error": "terminals is a list of process ids"}, 400)
        can = body.get("can")
        can = can if isinstance(can, list) else []
        editor = hub.editor_waits(pids, shows="show" in can, clears="clear" in can, opens="open" in can,
                                  theme=str(body.get("theme") or ""))
        end = time.monotonic() + EDITOR_WAIT
        while not editor.wake.wait(0.5) and time.monotonic() < end and not self._client_gone():
            pass
        self._reply({"keys": hub.editor_done(editor), "show": editor.show, "open": editor.open, "close": editor.close})

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


UNIX = hasattr(socketserver, "ThreadingUnixStreamServer")


class Server(socketserver.ThreadingUnixStreamServer if UNIX else socketserver.ThreadingTCPServer):
    daemon_threads = True
    hub: Hub
    token = ""


class PortServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False
    hub: Hub
    token = ""


def serve(hub: Hub, sock: str, addr: str = "") -> Server | PortServer:
    """Bind the door and return the server; the caller runs serve_forever(). A Unix socket
    (owner-only) where there are any; else a port on 127.0.0.1 and a token, written to `addr`."""
    for old_door in (sock, addr):
        if old_door and os.path.exists(old_door):
            os.unlink(old_door)
    if UNIX and os.environ.get("SIDETONE_TRANSPORT") != "tcp":
        old = os.umask(0o077)
        try:
            server = Server(sock, Handler)
        finally:
            os.umask(old)
        server.hub = hub
        return server
    server = PortServer(("127.0.0.1", 0), Handler)
    server.hub, server.token = hub, secrets.token_urlsafe(32)
    old = os.umask(0o077)
    try:  # written whole, then put in place, so a reader never sees half of it
        with open(addr + ".part", "w") as f:
            f.write(f"{server.server_address[1]} {server.token}\n")
        os.replace(addr + ".part", addr)
    finally:
        os.umask(old)
    return server
