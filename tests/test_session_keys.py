"""The new-session key and the end key (Ctrl+Alt+Plus, Ctrl+Alt+Minus): what the hub asks of the
editor, when the keys are claimed, and the session that starts getting the focus.

Run: ~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import base  # noqa: E402
import hub as hub_module  # noqa: E402
from test_hub import FakeOverlay, FakeSounds, HubCase, ev, wait_for  # noqa: E402

# A stand-in for the editor, for the real extension to run against: two terminals of ours, and a
# note of every terminal it opens (its folder, the terminal it is split from), shows and types into.
EDITOR = """
    const fs = require("fs");
    const done = [];
    const note = (...what) => { done.push(what); fs.writeFileSync(process.env.DONE, JSON.stringify(done)); };
    const terminal = (pid) => ({
      pid, processId: Promise.resolve(pid),
      sendText: (text, enter) => note("typed", pid, text, enter),
      show: (keepKeyboard) => note("shown", pid, keepKeyboard),
    });
    let opened = 9000;
    const nothing = (f) => ({ dispose() {} });
    exports.workspace = { workspaceFolders: [], onDidChangeWorkspaceFolders: nothing };
    exports.ColorThemeKind = { Light: 1, Dark: 2, HighContrast: 3, HighContrastLight: 4 };
    exports.window = {
      state: { focused: true },
      terminals: [terminal(4001), terminal(4002)],
      activeTerminal: undefined,
      createTerminal: (options) => {
        const parent = options.location && options.location.parentTerminal;
        note("opened", options.cwd || "", parent ? parent.pid : null, Object.keys(options).sort());
        return terminal(++opened);
      },
      onDidChangeActiveTerminal: nothing, onDidChangeWindowState: nothing, onDidOpenTerminal: nothing,
      onDidCloseTerminal: nothing, onDidChangeActiveColorTheme: nothing,
      activeColorTheme: { kind: 2 },
    };"""


class SessionKeys(HubCase):
    def make(self, **kw):
        hub = super().make(label="never", **kw)
        hub.overlay = self.overlay = FakeOverlay()
        self.addCleanup(setattr, hub_module.terminal_mod, "tty_of", hub_module.terminal_mod.tty_of)
        hub_module.terminal_mod.tty_of = lambda pid: {4001: "/dev/pts/41", 4002: "/dev/pts/42"}.get(pid)
        hub.on_event(ev("SessionStart", sid="a", cwd="/w/a"))
        hub.on_event(ev("SessionStart", sid="b", cwd="/w/b"))
        hub.sessions.by_id["a"].tty, hub.sessions.by_id["b"].tty = "/dev/pts/41", "/dev/pts/42"
        hub.talk_target = "a"
        return hub

    def live(self):
        keys = self.overlay.of("keys")
        return keys[-1]["live"] if keys else []

    def test_the_keys_are_claimed_only_with_an_editor_that_can_do_it(self):
        hub = self.make()
        hub.publish()
        self.assertNotIn("new_session", self.live())
        self.assertNotIn("end_session", self.live())
        hub.editor_waits([4001], shows=True, clears=True)  # an extension from before 0.5.0
        hub.publish()
        self.assertNotIn("new_session", self.live())
        editor = hub.editor_waits([4001], shows=True, clears=True, opens=True)
        hub.publish()
        self.assertIn("new_session", self.live())
        self.assertIn("end_session", self.live())
        hub.editor_done(editor)
        hub.talk_target = "b"  # its terminal is in no editor: nothing to end there
        hub.editor_waits([4001], opens=True)
        hub.publish()
        self.assertIn("new_session", self.live())
        self.assertNotIn("end_session", self.live())

    def test_a_new_session_opens_beside_the_one_in_focus_and_gets_the_focus(self):
        hub = self.make()
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertTrue(editor.wake.is_set())
        self.assertEqual(editor.open, [{"cwd": "/w/a", "beside": 4001}])
        self.assertEqual(hub.editor_done(editor), [])  # nothing typed into a terminal of ours
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/a", source="startup"))
        self.assertEqual(hub._target().id, "c")
        hub.talk_target = "a"
        hub.on_event(ev("SessionStart", sid="d", cwd="/w/a", source="startup"))  # opened by hand: no focus
        self.assertEqual(hub._target().id, "a")

    def test_with_no_session_a_new_one_opens_in_the_editors_own_folder(self):
        hub = self.make()
        for sid in list(hub.sessions.by_id):
            hub.on_event(ev("SessionEnd", sid=sid))
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertEqual(editor.open, [{"cwd": "", "beside": None}])

    def test_the_editors_window_is_brought_up_by_its_folders_name(self):
        hub = self.make()
        hub.editor_waits([4001], opens=True, folder="vscode-remote://wsl%2Bubuntu/w/my%20app")
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertEqual(self.overlay.of("raise"), [{"type": "raise", "name": "my app"}])

    def test_as_a_tab_it_names_no_terminal_to_sit_beside(self):
        """`terminal.new_session` "tab": a terminal of its own, still asked of the editor that
        holds the terminal of the session in focus, in that session's folder, and its session
        still gets the focus."""
        hub = self.make()
        self.assertEqual(hub.cfg.terminal["new_session"], "beside")  # a new install: as it was
        self.assertIsNone(hub.set_setting("terminal.new_session", "tab"))
        other = hub.editor_waits([4002], opens=True)  # another window of the editor, asked first
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertEqual(editor.open, [{"cwd": "/w/a", "beside": None}])
        self.assertEqual(other.open, [])
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/a", source="startup"))
        self.assertEqual(hub._target().id, "c")
        self.assertIsNotNone(hub.set_setting("terminal.new_session", "window"))  # not a place
        self.assertEqual(hub.cfg.terminal["new_session"], "tab")
        self.assertIsNone(hub.set_setting("terminal.new_session", "beside"))
        hub.talk_target = "a"
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "new_session"})
        self.assertEqual(editor.open, [{"cwd": "/w/a", "beside": 4001}])

    def extension(self, hub):
        """Start the real extension code, with a stand-in for the editor, against the hub over
        its socket. Returns what reads the notes of what it did in the editor."""
        server = hub_module.serve(hub, os.path.join(self.tmp, "hub.sock"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        ext = os.path.join(self.tmp, "ext")
        os.makedirs(os.path.join(ext, "node_modules", "vscode"))
        shutil.copy(os.path.join(ROOT, "vscode", "extension.js"), ext)
        with open(os.path.join(ext, "node_modules", "vscode", "index.js"), "w") as f:
            f.write(EDITOR)
        done = os.path.join(self.tmp, "done.json")
        editor = subprocess.Popen(["node", "-e", "require('./extension.js').activate({ subscriptions: [] });"], cwd=ext,
                                  env={**os.environ, "CS_RUN": self.tmp, "DONE": done})
        self.addCleanup(editor.wait)
        self.addCleanup(editor.kill)

        def notes():
            try:
                with open(done) as f:
                    return json.load(f)
            except (OSError, ValueError):  # not yet written, or being written
                return []
        return notes

    @unittest.skipUnless(shutil.which("node"), "needs node to run the editor extension")
    def test_the_editor_extension_opens_it_split_or_as_a_tab(self):
        """The real extension code, with a stand-in for the editor, against the hub over its
        socket. Beside: the new terminal is split from the one of the session in focus. As a
        tab: it is given no place at all, so the editor puts it where its new terminals go.
        Both in that session's folder, shown with the keyboard in it, and `claude` typed."""
        hub = self.make()
        folder = os.path.join(self.tmp, "a")
        os.makedirs(folder)
        hub.sessions.by_id["a"].cwd = folder
        notes = self.extension(hub)

        def press(so_far):
            waiting = lambda: any(e.opens and "/dev/pts/41" in e.ttys and not e.wake.is_set() for e in hub.editors)  # noqa: E731
            self.assertTrue(wait_for(waiting, 8), "the editor's request never came")
            hub.on_overlay({"type": "hotkey", "name": "new_session"})
            self.assertTrue(wait_for(lambda: len(notes()) == so_far + 3, 8), f"the editor opened nothing: {notes()}")
            return notes()[so_far:]

        self.assertEqual(press(0), [["opened", folder, 4001, ["cwd", "location"]],
                                    ["shown", 9001, False], ["typed", 9001, "claude", True]])
        self.assertIsNone(hub.set_setting("terminal.new_session", "tab"))
        self.assertEqual(press(3), [["opened", folder, None, ["cwd"]],
                                    ["shown", 9002, False], ["typed", 9002, "claude", True]])

    def test_the_end_key_asks_then_ends_and_closes_the_terminal_once_ended(self):
        hub = self.make()
        hub.sounds = FakeSounds()
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertFalse(editor.wake.is_set(), "one press only asks")
        asked = self.overlay.of("banner")[-1]
        self.assertEqual((asked["icon"], asked["text"], asked["hint"]), ("end", "End a?", "Ctrl+Alt+Minus to confirm"))
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "Ending a\u2026")  # in the question's place
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "exit"}])
        self.assertEqual(editor.close, [], "the terminal stays until the session has ended")
        editor = hub.editor_waits([4001, 4002], opens=True)
        self.assertEqual(hub.sounds.played, [], "no sound until it has really ended")
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [4001])
        self.assertEqual(hub.sounds.played, ["ended"])
        # A session that ends by itself does not have its terminal closed, nor its sound.
        editor = hub.editor_waits([4001, 4002], opens=True)
        hub.on_event(ev("SessionEnd", sid="b", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [])
        self.assertEqual(hub.sounds.played, ["ended"])

    def test_ending_shows_its_progress_until_it_has_ended(self):
        hub = self.make()
        self.assertTrue(hub.cfg.end_progress)  # a new install
        self.end_twice(hub)
        shown = self.overlay.of("banner")[-1]
        self.assertEqual((shown["icon"], shown["text"], shown["seconds"]), ("clearing", "Ending a\u2026", base.END_SHOWN))
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        done = self.overlay.of("banner")[-1]
        self.assertEqual((done["icon"], done["text"]), ("cleared", "Ended a"))
        # Another banner that took its place stays: nothing says "Ended" over it.
        hub.talk_target = "b"
        hub.editor_waits([4001, 4002], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "Ending b\u2026")
        hub.on_overlay({"type": "hotkey", "name": "mute"})
        hub.on_event(ev("SessionEnd", sid="b", reason="prompt_input_exit"))
        self.assertEqual(self.overlay.of("banner")[-1]["icon"], "muted")
        # Switched off, the question only goes.
        hub = self.make()
        self.assertIsNone(hub.set_setting("end_progress", False))
        self.end_twice(hub)
        self.assertEqual(self.overlay.of("banner")[-1], {"type": "banner"})
        so_far = len(self.overlay.of("banner"))
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertEqual(self.overlay.of("banner")[so_far:], [])

    def test_a_late_second_press_only_asks_again(self):
        hub = self.make()
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub._end_armed = ("a", time.monotonic() - 4)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertFalse(editor.wake.is_set())

    def test_only_the_question_on_screen_is_confirmed(self):
        """Clear asked, then end asked: the clear key again only asks, as nothing on screen said
        it would clear (the author lost a conversation so, 2026-11-22). The same the other way, and
        after the mute key's banner."""
        hub = self.make()
        editor = hub.editor_waits([4001], opens=True, clears=True)
        for first, second in (("clear", "end_session"), ("end_session", "clear"), ("clear", "mute"), ("end_session", "mute")):
            hub.on_overlay({"type": "hotkey", "name": first})
            hub.on_overlay({"type": "hotkey", "name": second})
            hub.on_overlay({"type": "hotkey", "name": first})
            self.assertFalse(editor.wake.is_set(), f"{first}, {second}, {first}")
            self.assertIn("?", self.overlay.of("banner")[-1]["text"])  # asked again
            hub._clear_armed = hub._end_armed = None
        hub.on_overlay({"type": "hotkey", "name": "clear"})
        hub.on_overlay({"type": "hotkey", "name": "clear"})
        self.assertTrue(editor.wake.is_set())

    def test_a_close_asked_between_two_requests_goes_to_the_next(self):
        hub = self.make()
        editor = hub.editor_waits([4001], opens=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.editor_done(editor)
        hub.on_event(ev("SessionEnd", sid="a"))  # no editor waiting at this moment
        editor = hub.editor_waits([4001], opens=True)
        self.assertEqual(editor.close, [4001])
        self.assertTrue(editor.wake.is_set())

    # --- a session with work in the background: Claude Code asks before it exits ---------------

    def end_twice(self, hub, **can):
        """The end key pressed twice with an editor waiting: /exit is typed. Returns the editor
        that waits after it."""
        can = {"opens": True, "confirms": True, **can}
        editor = hub.editor_waits([4001, 4002], **can)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "exit"}])
        return hub.editor_waits([4001, 4002], **can)

    def file(self, hub, sid, status, waiting_for=None, at=None):
        """Claude Code's own file for a session: what it says the session is doing now."""
        os.makedirs(hub.cfg.sessions_dir, exist_ok=True)
        with open(os.path.join(hub.cfg.sessions_dir, f"{sid}.json"), "w") as f:
            json.dump({"sessionId": sid, "pid": os.getpid(), "status": status, "waitingFor": waiting_for,
                       "statusUpdatedAt": (at or time.time()) * 1000}, f)

    def asks(self, hub, sid="a"):
        """Claude Code asks before it exits: its file says so, and the hub looks at it every second."""
        self.file(hub, sid, "waiting", "dialog open")
        hub.reconcile()

    def test_claude_code_asks_first_the_overlay_asks_and_the_key_once_more_ends_it(self):
        hub = self.make()
        hub.sounds = FakeSounds()
        self.assertEqual(hub.cfg.end_background, "ask")  # a new install
        editor = self.end_twice(hub)
        self.asks(hub)
        asked = self.overlay.of("banner")[-1]
        self.assertEqual((asked["icon"], asked["text"], asked["hint"], asked["below"], asked["seconds"]),
                         ("end", "a has background work", "Ctrl+Alt+Minus to end anyway", True, base.END_ANYWAY))
        self.assertEqual(hub.sounds.played, ["queued"])
        self.assertFalse(editor.wake.is_set(), "nothing is answered before you say so")
        hub.reconcile()
        self.assertEqual(hub.sounds.played, ["queued"], "asked once, however long it waits")
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "Ending a\u2026")
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "confirm"}])
        editor = hub.editor_waits([4001, 4002], opens=True, confirms=True)
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [4001])
        self.assertEqual(hub.sounds.played, ["queued", "ended"])

    def test_only_a_dialog_opened_after_exit_was_typed_is_taken_for_the_question(self):
        hub = self.make(end_background="end")
        self.file(hub, "a", "waiting", "dialog open", at=time.time() - 5)  # a picker that was open: Escape closes it
        editor = self.end_twice(hub)
        hub.reconcile()
        self.file(hub, "a", "waiting", "permission prompt")  # asked meanwhile: an Enter would allow it
        hub.reconcile()
        self.file(hub, "a", "shell")  # at its prompt, a command of its own running: /exit not typed yet
        hub.reconcile()
        self.file(hub, "b", "waiting", "dialog open")  # another session's dialog
        hub.reconcile()
        self.assertFalse(editor.wake.is_set())
        self.assertFalse([b for b in self.overlay.of("banner") if "background" in str(b.get("text"))])
        self.asks(hub)
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "confirm"}])

    def test_end_anyway_answers_without_asking(self):
        hub = self.make()
        self.assertIsNone(hub.set_setting("end_background", "end"))
        editor = self.end_twice(hub)
        so_far = len(self.overlay.of("banner"))
        self.asks(hub)
        self.assertEqual(hub.editor_done(editor), [{"pid": 4001, "key": "confirm"}])
        self.assertEqual(self.overlay.of("banner")[so_far:], [])
        # Its editor between two requests at that moment: the next one is handed the answer.
        hub.talk_target = "b"
        editor = hub.editor_waits([4001, 4002], opens=True, confirms=True)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.editor_done(editor)
        self.asks(hub, "b")
        editor = hub.editor_waits([4001, 4002], opens=True, confirms=True)
        self.assertEqual(hub.editor_done(editor), [{"pid": 4002, "key": "confirm"}])

    def test_left_in_the_terminal_the_overlay_only_says_so(self):
        """`end_background: terminal`, and an editor whose extension cannot type the answer."""
        for setting, can in (("terminal", {}), ("ask", {"confirms": False}), ("end", {"confirms": False})):
            hub = self.make()
            self.assertIsNone(hub.set_setting("end_background", setting))
            editor = self.end_twice(hub, **can)
            self.asks(hub)
            said = self.overlay.of("banner")[-1]
            self.assertEqual((said["icon"], said["text"], said["hint"]), ("end", "a asks in its terminal", ""), setting)
            hub.on_overlay({"type": "hotkey", "name": "end_session"})  # not an answer: the first question again
            self.assertEqual(self.overlay.of("banner")[-1]["text"], "End a?")
            self.assertFalse(editor.wake.is_set(), setting)
        self.assertIsNotNone(hub.set_setting("end_background", "always"))  # not one of the three

    def test_only_the_second_question_on_screen_is_answered(self):
        hub = self.make()
        editor = self.end_twice(hub)
        self.asks(hub)
        hub.on_overlay({"type": "hotkey", "name": "mute"})  # its banner takes the question's place
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "End a?")
        hub._end_armed = None
        hub._end_held("a")
        hub._end_armed = ("a", time.monotonic() - base.END_ANYWAY - 1)  # it went by itself
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "End a?")
        hub._end_armed = None
        hub._end_held("a")
        hub.talk_target = "b"  # the focus is on another session: the key is about that one
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "End b?")
        self.assertFalse(editor.wake.is_set())

    def test_answered_in_the_terminal_nothing_is_typed_and_its_terminal_stays(self):
        """ "Stay" chosen in the terminal while the overlay asks: its file no longer says it
        waits. The key then types nothing, and the session keeps its terminal when it ends later."""
        hub = self.make()
        hub.sounds = FakeSounds()
        editor = self.end_twice(hub)
        self.asks(hub)
        self.file(hub, "a", "idle")
        hub.on_overlay({"type": "hotkey", "name": "end_session"})  # before the hub has looked again
        self.assertEqual(self.overlay.of("banner")[-1], {"type": "banner"})
        self.assertFalse(editor.wake.is_set(), "an Enter would go to its prompt")
        hub.reconcile()
        self.assertEqual(hub._ending, {})
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [])
        self.assertEqual(hub.sounds.played, ["queued"])
        # The same when the hub looks first: the question goes from the overlay by itself.
        hub.talk_target = "b"
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(hub.editor_done(editor), [{"pid": 4002, "key": "exit"}])
        editor = hub.editor_waits([4001, 4002], opens=True, confirms=True)
        self.asks(hub, "b")
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "b has background work")
        self.file(hub, "b", "shell")
        hub.reconcile()
        self.assertEqual(self.overlay.of("banner")[-1], {"type": "banner"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertEqual(self.overlay.of("banner")[-1]["text"], "End b?")

    def test_a_prompt_taken_since_means_it_goes_on(self):
        """A question the hub never saw (answered within the second): the next prompt says it stayed."""
        hub = self.make()
        editor = self.end_twice(hub)
        hub.on_event(ev("UserPromptSubmit", sid="a", prompt="go on"))
        self.assertEqual(self.overlay.of("banner")[-1], {"type": "banner"})  # "Ending ..." goes with it
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertEqual(editor.close, [])

    @unittest.skipUnless(shutil.which("node"), "needs node to run the editor extension")
    def test_the_editor_extension_types_exit_and_then_the_enter_that_answers(self):
        """The real extension code: it says it can confirm, types Escape, Ctrl+C and /exit for
        the end key, and a single Enter for the key pressed once more."""
        hub = self.make()
        notes = self.extension(hub)
        waiting = lambda: any(e.confirms and "/dev/pts/41" in e.ttys and not e.wake.is_set() for e in hub.editors)  # noqa: E731
        self.assertTrue(wait_for(waiting, 8), "the editor's request never came, or it cannot confirm")
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertTrue(wait_for(lambda: len(notes()) == 3, 8), f"not typed: {notes()}")
        self.assertEqual(notes(), [["typed", 4001, "\x1b", False], ["typed", 4001, "\x03", False], ["typed", 4001, "/exit\r", False]])
        self.assertTrue(wait_for(waiting, 8), "the editor did not ask again")
        self.asks(hub)
        hub.on_overlay({"type": "hotkey", "name": "end_session"})
        self.assertTrue(wait_for(lambda: len(notes()) == 4, 8), f"not answered: {notes()}")
        self.assertEqual(notes()[3], ["typed", 4001, "\r", False])


class OneSessionTwoTerminals(SessionKeys):
    """One conversation open in two terminals (resumed in a second one): closing one of them
    does not take it off the overlay."""

    def test_closing_one_of_its_terminals_keeps_it(self):
        hub = self.make()
        s = hub.sessions.by_id["a"]
        s.pids = [4001, 4002]
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))
        self.assertIn("a", hub.sessions.by_id)
        hub.on_event(ev("SessionEnd", sid="a", reason="prompt_input_exit"))  # and the other one too
        self.assertNotIn("a", hub.sessions.by_id)

    def test_cleared_in_one_of_its_terminals_it_goes_on_in_the_other(self):
        hub = self.make()
        hub.sessions.by_id["a"].pids = [4001, 4002]
        name = hub.sessions.by_id["a"].name
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a", reason="clear"))
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/a", source="clear"))
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message="<speak>Still here.</speak>"))
        self.assertEqual(hub.sessions.by_id["a"].name, name)
        self.assertEqual(hub.sessions.by_id["a"].state, "done")  # its turn is still heard
        self.assertNotEqual(hub.sessions.by_id["c"].name, hub.sessions.by_id["a"].name)

    def test_cleared_with_the_clear_key_the_light_goes_with_its_terminal(self):
        """The hub typed /clear into the terminal the light is about: the conversation that starts
        there keeps the name, color, voice and place, and the one that goes on in the other
        terminal is a session of its own from its next sign of life."""
        hub = self.make()
        s = hub.sessions.by_id["a"]
        s.pids = [4001, 4002]
        before = {k: getattr(s, k) for k in ("name", "color", "voice", "order")}
        editor = hub.editor_waits([4001], opens=True, clears=True)
        hub.on_overlay({"type": "hotkey", "name": "clear"})
        hub.on_overlay({"type": "hotkey", "name": "clear"})
        self.assertTrue(editor.wake.is_set())
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a", reason="clear"))
        self.assertNotIn("a", hub.sessions.by_id)
        self.assertEqual(hub.sessions.by_id["cleared:a"].name, before["name"])  # its light stays, the arc at 0
        hub.on_event(ev("SessionStart", sid="c", cwd="/w/a", source="clear"))
        self.assertEqual({k: getattr(hub.sessions.by_id["c"], k) for k in before}, before)
        self.assertEqual([o.name for o in hub.sessions.by_id.values()].count(before["name"]), 1)
        self.assertEqual(self.overlay.of("banner")[-1]["text"], f"Cleared {before['name']}")
        # The other terminal still has the old conversation: it is heard, under a name of its own.
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message="<speak>Still here.</speak>"))
        self.assertEqual(hub.sessions.by_id["a"].state, "done")
        self.assertNotEqual(hub.sessions.by_id["a"].name, before["name"])

    def test_the_terminal_that_is_left_is_found(self):
        hub = self.make()
        s = hub.sessions.by_id["a"]
        s.pids, s.tty, s.seen_file = [4001, 4002], "/dev/pts/41", True
        live = {"a": {"pid": 4002, "pids": [4002], "status": "idle", "status_at": 0, "name": ""}}
        self.addCleanup(setattr, hub_module.claude_sessions, "read", hub_module.claude_sessions.read)
        hub_module.claude_sessions.read = lambda directory: live
        hub.reconcile()
        self.assertEqual((s.pids, s.tty), ([4002], "/dev/pts/42"))


class SubagentPrompts(SessionKeys):
    """A subagent sent to the background asks for permission after the turn that started it
    has ended: its prompt stays open, so the keys and a spoken yes can answer it."""

    def ask(self, hub, agent=""):
        body = ev("PermissionRequest", sid="a", cwd="/w/a", tool_name="Bash", tool_input={"command": "ls /etc"})
        if agent:
            body["agent_id"] = agent
        return hub.request_permission(body)

    def test_the_end_of_the_turn_leaves_a_subagents_prompt_open(self):
        hub = self.make()
        req = self.ask(hub, agent="a1ee82860a16a140d")
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message="<speak>Started it.</speak>"))
        self.assertIn(req, hub.requests)
        self.assertEqual(hub.sessions.by_id["a"].state, "needs_you")
        hub.on_event(ev("PostToolUse", sid="a", cwd="/w/a", tool_name="Bash", tool_input={"command": "ls /etc"}))
        self.assertNotIn(req, hub.requests)  # allowed in the terminal: its call ran

    def test_the_sessions_own_prompt_still_goes_with_its_turn(self):
        hub = self.make()
        req = self.ask(hub)
        hub.on_event(ev("Stop", sid="a", cwd="/w/a", last_assistant_message="<speak>Done.</speak>"))
        self.assertNotIn(req, hub.requests)

    def test_the_end_of_the_session_takes_a_subagents_prompt(self):
        hub = self.make()
        req = self.ask(hub, agent="x1")
        hub.on_event(ev("SessionEnd", sid="a", cwd="/w/a"))
        self.assertNotIn(req, hub.requests)


if __name__ == "__main__":
    unittest.main()
