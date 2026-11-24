# Sidetone

Eyes-free Claude Code. A local voice reads a 1–2 sentence spoken summary of each turn, never the
full output, and starts while the reply is still streaming. With several sessions open they
speak one at a time, each with its own label and voice.

The story: **attention latency**. The slow part of working with agents is the human noticing a
session and switching to it. The project cuts that delay in both directions (session → you,
you → session) so you can keep your eyes on your own work.

## Where things are written down

This file is what every session needs; it was cut down from 150,000 characters on 2026-11-19 at
the author's asking, and the rest was moved unchanged:

- `TODO.md`: what is left, in the order to do it (try what is built, decide, speech in the
  author's languages, small extras, what the first public version needs, release, the
  documentation last), then what is done. Update it when something on it is done or a new
  idea comes up; a new item goes in the step it belongs to.
- `docs/dev/features.md`: how each part works and why, feature by feature, with the settings,
  what the author said and what was measured. Search it for a setting's or a function's name
  before changing a feature, and add to it when you change one.
- `docs/dev/facts.md`: measured facts about Claude Code's hooks and session files, Windows, WPF,
  glass and motion, sound, the speech models, this machine.
- `docs/dev/history.md`, `docs/dev/name-and-logo.md` (the name, the color `#006896`, the logo),
  `docs/dev/similar-projects.md`.

## Rules for working here

- Several sessions work in this repo at once. Stage only your own paths, look at `git status`
  before committing. The repo is private (github.com/SimoneWang02/sidetone); Claude may commit
  and push.
- The live hub is the author's. Restarting it cuts off a recording in progress: look first with
  `pgrep -x parec -a` (a recorder with `--rate=16000` means they are talking; the one with
  `monitor` is the loudness meter). Not `pgrep -af parec`, which finds the shell running it.
  A change in `Overlay.cs` needs `sidetone overlay restart`; a new default in `hub/overlay.py`
  or any hub file needs `sidetone hub restart`. `sidetone status` says when the running hub or
  overlay is older than the code.
- No code for faults that only happen while the tool is being worked on (restarts, live edits);
  report the cause instead (the author: "there's no need in the final product").
- New looks and behaviours come as settings with sensible defaults, not replacements: people who
  download it should be able to customize as much as possible. A new setting gets a line in
  `settings.SECTIONS` so the settings window has it (a test checks it is a real setting).
  Left out, and only in `config.json`: paths and the hub's own internals, values another command
  sets (`whisper_model` from `sidetone languages`), and lines the author took out of the window
  (a comment in `SECTIONS` says when and why). Agreed 2026-11-21.
- Default hotkeys must not clash with popular programs' own keys; a key another program holds is
  shared through the keyboard hook (`share_taken_keys`).
- The hooks and the hub change together (a hub from before a tag change may not speak the line).
- `listen.sh` and `permission.sh` run for hours and bash reads a script as it goes: keep each one
  function called on its last line, so editing them does not break listeners already running.
- The author listens rather than reads: the point goes in the spoken line, written replies stay
  short. The look matters to them: agree it, show it (pictures with `tests/overlay_check.py`, or
  live), measure gaps in pixels.
- Things they have not yet tried by hand are marked so in `TODO.md`; do not claim them as done.

## Status

- Working day to day on the author's machine (WSL2 Linux, Windows 11). The live hooks run
  **from this repo**: `~/.claude/settings.json` points at `~/personal/sidetone/hooks/`
  (`hooks/settings-snippet.json` is that block). Rollback: `~/.claude/settings.json.bak-before-hub`.
- `README.md`, `LICENSE` (MIT), `install.sh` / `uninstall.sh` (merge the hooks into an existing
  `settings.json`, link `sidetone` and `st` into `~/.local/bin`, ask which languages you speak,
  offer the VS Code extension). Not yet a plugin, not yet public, Windows overlay only.

## How it works

```
Claude sessions ──hooks (bash + curl)──▶ hub (Python, in the Kokoro venv) ──stdin──▶ overlay (Windows)
                  Unix socket, owner-only   session state · speech queue   ◀─stdout── hotkeys
```

| Hook event | Script | Job |
|---|---|---|
| UserPromptSubmit | `hooks/voice-reminder.sh` | Injects an instruction: open the final message with ONE line that is exactly a speak tag |
| MessageDisplay | `hooks/display.sh` | Runs per streamed batch. Sends a batch containing a speak tag to the hub, which queues the speech and returns the "🔊 …" rewrite |
| Stop | `hooks/speak.sh` | Tells the hub the turn ended; the hub speaks the line only if streaming missed it |
| Notification (`permission_prompt`, `elicitation_dialog`) | `hooks/notify.sh` | Hub marks the session "needs you" and says "I need your input" |
| PermissionRequest | `hooks/permission.sh` | Holds a request open on the hub until the prompt is answered. Prints the hub's allow/deny, or nothing if it was answered in the terminal |
| PreToolUse, PostToolUse | `hooks/stop.sh` | Ends the turn when the hub was asked to stop this session (a file named after it in `$CS_RUN/stop`). After a step, hands Claude the words spoken to it while it works (`$CS_RUN/steer`). About 2.5 ms when nobody asked |
| Stop, SessionStart, UserPromptSubmit (`asyncRewake`) | `hooks/listen.sh` | Background listener: waits on the hub for a spoken follow-up for this session, prints it for Claude and exits 2, which wakes the session |
| SessionStart, SessionEnd, UserPromptSubmit, PreToolUse, PostToolUse(Failure), TaskCreated, TaskCompleted, StopFailure | `hooks/report.sh` (async) | Forwards the payload so the hub knows what each session is doing. `--start` also starts the hub |

Where the code is:

- `hub/`: the one background process, Python in the Kokoro venv. HTTP over a Unix socket at
  `$XDG_RUNTIME_DIR/sidetone/hub.sock` (no TCP port, so no web page or other machine can
  make it speak, approve or type). Started lazily by the hooks, one at a time by `flock`, exits
  after 30 min with no sessions. `hub.py` the `Hub` and `main`; `base.py` settings (`Config`),
  small records and helpers; `permissions.py` and `talk.py` are parts of the `Hub` class
  (requests and questions; push-to-talk, words on their way, side questions, stopping,
  clearing); `server.py` HTTP; `state.py` sessions, colors, tags; `tts.py` voices and the speech
  queue (Kokoro, Piper, Kokoro's Chinese model); `stt.py` push-to-talk with faster-whisper;
  `sounds.py` short signals; `packs.py` languages as packs to install (Chinese's model and
  voices, Piper's), with `samples/` to hear a voice before its download (`sndfile.py`); `overlay.py` starts and feeds the overlay; `terminal.py` tints terminals; `claude_sessions.py` reads `~/.claude/sessions/*.json`; `usage.py` plan usage and
  context; `settings.py` the settings window's sections; `stale.py` notices outdated code;
  `demo.py` made-up sessions.
- `overlay/Overlay.cs`: the Windows overlay (bar, panel, bubble, settings window), compiled by
  the hub with Windows' own `csc.exe` (C# 5 only, ASCII source); `overlay.ps1` is the fallback.
  It only draws; all logic is in the hub so it can be tested. JSON lines over stdin and stdout.
- `vscode/`: the VS Code extension (0.6.0): the focus follows the terminal in front, and the
  hub can have it type Escape (stop), `/clear`, or show a terminal. `sidetone vscode install`.
- `bin/sidetone` (`st`): every command (`sidetone` with no arguments lists them).
- `hooks/tts-lib.sh`: every hook still works without a hub, through a system voice.
- Config: `~/.config/sidetone/config.json` (every setting; also `sidetone settings list`).
  Runtime: `~/.local/state/sidetone/` (`hub.log`, `voice.log`, `voices.json`), the run
  folder `$XDG_RUNTIME_DIR/sidetone/` (`sessions.json`, `followups.json`). Voice off while
  `~/.claude/voice-off` exists.

## Testing

- `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests` (silent engine,
  fake microphone, the real hook scripts over a socket, a real hub killed and restarted).
- `tests/overlay_check.py OUT_DIR [--glass] [--only=NAME]`: a picture of every overlay view,
  taken from the overlay's own windows. `tests/keys_check.py`: the keyboard hook with a spare key.
- A real session without the author: `claude --model haiku` in a detached tmux session (unset
  the inherited `CLAUDE*` variables; `--setting-sources project` keeps the user's hooks out,
  `--permission-mode default` makes it ask), driven with `send-keys`, read with `capture-pane`.
  Wait between steps with `python3 -c "import time; time.sleep(2)"`.
- `sidetone hub stop` and `uninstall.sh` act on the real hub of this `XDG_RUNTIME_DIR` even
  with a fake `HOME`; a test that runs `uninstall.sh` needs `--keep-vscode` or a stand-in `code`.
- Keep `hooks/display.sh` fast: Claude Code holds each streamed batch until it returns
  (about 5 ms without a tag, 10 ms with one).

## Deps (current machine)

- apt: `jq`, `curl`, `espeak-ng`, `pulseaudio-utils` (`paplay`)
- `uv` in `~/.local/bin`, with a Python 3.12 venv in `~/.local/share/kokoro/venv` (`kokoro-onnx`,
  `faster-whisper`; the Whisper model is downloaded to the Hugging Face cache on first use)
- `pulseaudio-utils` also provides `parec` for the microphone
- Models: `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the kokoro-onnx GitHub release `model-files-v1.0`.
  Piper 2023.11.14-2 binary plus `en_US-lessac-medium` from Hugging Face (fallback).
- An NVIDIA RTX 5070 (12 GB) that WSL sees; nothing in the project uses it yet.
