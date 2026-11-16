# claude-speaks

Eyes-free Claude Code. A local voice reads a 1–2 sentence spoken summary of each turn, never the
full output, and starts while the reply is still streaming. With several sessions open they
speak one at a time, each with its own label and voice.

The story: **attention latency**. The slow part of working with agents is the human noticing a
session and switching to it. The project cuts that delay in both directions (session → you,
you → session) so you can keep your eyes on your own work.

## Status

- Working day to day on the author's machine (WSL2 Linux). Since 2026-11-16 the live hooks run
  **from this repo**: `~/.claude/settings.json` points at `~/personal/claude-speaks/hooks/`.
  Rollback: `~/.claude/settings.json.bak-before-hub` plus the old scripts in `~/.claude/hooks/`.
- Not yet packaged as a plugin. Paths outside the repo: `~/.local/share/{kokoro,piper}`.
- Private GitHub repo: github.com/SimoneWang02/claude-speaks. Claude may commit and push.

## Roadmap (decided with the author 2026-11-16)

1. **Hub and voice queue**: done; the author confirmed it by ear on 2026-11-16.
2. **Windows overlay**: built 2026-11-16; waiting for the author's check by eye (look, position,
   `Ctrl+Alt+L`, behaviour over a game). Native window (PowerShell + WPF, started by the hub, JSON
   lines over stdin/stdout), see-through and click-through. Two modes: faint dots that expand to
   one line on a change, and a full list.
3. **Allow or deny by hotkey**: built 2026-11-16 and verified end to end against a real session
   through `claude-speaks allow|deny`; the author still has to try the actual `Ctrl+Alt+Y` /
   `Ctrl+Alt+N` keys. `PermissionRequest` hook long-polls the hub; the terminal dialog stays usable
   and whichever answers first wins.
4. **Push-to-talk follow-ups**: built 2026-11-16 and verified end to end without the author (a
   sentence played through the speakers was recorded, transcribed and delivered to a real idle
   session, which acted on it). The author still has to try it with their own voice and the real
   key. Hold `Ctrl+Alt+Space`, local `faster-whisper`, delivered to the session that spoke last
   through an `asyncRewake` hook.

Milestones 2 to 4 were built in one sitting while the author was away ("you continue, I'll
approve anything"). **Still to be checked by the author**: how the overlay looks and where it
sits, behaviour over a game, and the physical hotkeys (`Ctrl+Alt+L`, `Y`, `N`, `Space`,
`Backspace`); none of those can be seen or pressed from WSL.
Decisions: overlay is Windows-native (must be usable over games; no browser chrome);
sessions are told apart by a spoken label plus a stable voice per project.
Later: plugin packaging, `install.sh`, README with latency numbers and a demo video with sound,
short sounds, stereo placement, a "what did I miss" key, MIT license, and a settings panel
where every voice can be customized (the author's idea; today the same choices live in
`config.json` as `voices` and `voice_pool`).

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
| Stop, SessionStart (`asyncRewake`) | `hooks/listen.sh` | Background listener: waits on the hub for a spoken follow-up for this session, prints it for Claude and exits 2, which wakes the session |
| SessionStart, SessionEnd, UserPromptSubmit, PreToolUse, PostToolUse(Failure), TaskCreated, TaskCompleted, StopFailure | `hooks/report.sh` (async) | Forwards the payload so the hub knows what each session is doing. `--start` also starts the hub |

- `hub/hub.py`: the one background process. HTTP over a Unix socket at
  `$XDG_RUNTIME_DIR/claude-speaks/hub.sock` (not a TCP port, so no web page or other machine can
  make it speak, and later approve or inject). Started lazily by the hooks, single instance by
  `flock`, exits after 30 min with no sessions.
- `hub/tts.py`: Kokoro kept loaded, synthesized sentence by sentence into `paplay`. Queue rules:
  one line at a time; needs-you > failed > done; a session's newer line replaces its queued one;
  lines older than 60 s are dropped; a new prompt silences that session.
- `hub/state.py`: session registry. Label = folder name, spoken only when more than one session
  was active in the last 15 min. Voice = stable hash of the name over a pool of 13 clearer
  English Kokoro voices, never one a live session already uses.
- `hub/overlay.py` + `overlay/overlay.ps1` + `overlay/Overlay.cs`: the on-screen overlay, a child
  process of the hub (only where `powershell.exe` exists). The hub sends `config`, `state` (one
  ready-to-draw row per session) and `flash` (one line for a few seconds, sent when a line starts
  being spoken, or instead of speech when the voice is off); the window sends `ready`, `hotkey`,
  `mode`, `error`. All logic lives in the hub so it can be tested; the C# only draws.
  Glyphs: ● working, ▲ needs you, ✔ done, ✖ failed, ○ idle, 🔊 on the row being spoken.
- Permission prompts (`Request` in `hub/hub.py`): the overlay shows the oldest open request at once
  (what, the exact command, the keys) and keeps it solid until answered. The voice waits for
  Claude Code's own "still waiting" notification (about 6 s) so it does not nag someone answering
  in the terminal, then says "Permission needed: …". A request with no notification after
  `permission_grace` (9 s) counts as answered in the terminal. A hotkey only works after the
  request has been on screen 0.7 s; the hub says "Allowed." or "Denied." as feedback.
  Questions and plan approvals (`AskUserQuestion`, `ExitPlanMode`) are never offered to the hotkeys.
- Push-to-talk (`hub/stt.py` and the talk methods in `hub/hub.py`): while the talk key is held
  the voice goes quiet and `parec` records the default microphone; on release (plus a 0.4 s tail)
  `faster-whisper` `small.en` transcribes it. The overlay shows the text for `followup_delay`
  (2 s, `Ctrl+Alt+Backspace` cancels), then the hub hands it to that session's listener and says
  "Sent.". Target: the session that spoke last; a quick tap of the talk key picks the next one.
  A busy session gets the follow-up right after its current reply. With no listener yet, the
  text waits in the hub until the session next stops. The cancel key also cuts the line being spoken.
- Hotkeys (rebind or blank them under `overlay.hotkeys`): `toggle` Ctrl+Alt+L and `talk`
  Ctrl+Alt+Space are always claimed; `allow` Ctrl+Alt+Y, `deny` Ctrl+Alt+N and `cancel`
  Ctrl+Alt+Backspace are claimed only while they can act, so other programs keep them otherwise.
- `hub/demo.py`: three made-up sessions that go through every state (`claude-speaks demo`).
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/claude-speaks`: `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `allow`/`deny`,
  `follow-up [-s PROJECT] TEXT`, `talk start|stop|cancel`, `overlay dots|list|toggle|restart`, `demo`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 49 tests with a silent engine and fake microphone, including the real hook
  scripts over a socket and a hub process that is killed and restarted.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/claude-speaks/config.json` with `voices` (project name → voice),
  `voice_pool`, `label` (`auto`/`always`/`never`), `max_age`, `idle_exit`, `default_voice`, `speed`,
  and `overlay` (`enabled`, `mode`, `corner`, `offset_x`, `offset_y`, `opacity`, `list_opacity`,
  `flash_seconds`, `hotkeys`), `permission_grace`, `whisper_model`, `mic_source`, `followup_delay`,
  `talk_tail`. `CLAUDE_SPEAKS_OVERLAY=off` disables the overlay.
- `~/.local/state/claude-speaks/voices.json`: the voice each project was given, kept so it stays
  the same across hub restarts (a future settings panel would edit this and `config.json`).
- Toggle: voice is off while `~/.claude/voice-off` exists (the hub still tracks state).
- Runtime files live outside the repo: `~/.local/state/claude-speaks/` (`voice.log` contains
  spoken summaries, `hub.log`, `.state/`, `.tts.pid`).
- `hooks/settings-snippet.json`: the `hooks` block as registered in settings.json.

## Key facts learned

- MessageDisplay holds each batch until the hook returns, so keep `display.sh` fast:
  about 5 ms with no tag, about 10 ms with one (one `curl` to the hub). Output
  `hookSpecificOutput.displayContent` to replace the shown text. The transcript keeps the original.
- `final` marks the last batch. Deltas are whole lines except possibly the final one.
- Stop input has `last_assistant_message`. The transcript can lag, so it's only a fallback.
- Only own-line tags are spoken, so inline mentions of the tag in prose are ignored.
- Latency, line written → first audio handed to the player: about 0.2 s with the warm hub,
  about 1.2 s without it (model reloaded per call).
- `Kokoro.create_stream` batches by phoneme count, not by sentence, so the hub splits sentences
  itself. With a label, the label is the first (very short) piece.
- Edits to `~/.claude/settings.json` hooks are picked up by running sessions at once.
- A Unix socket path is limited to about 108 characters; keep the run directory short.
- Permission hook facts (measured 2026-11-16 by driving a real session in tmux): the terminal
  dialog appears about 0.5 s after the `PermissionRequest` hook starts and stays usable while the
  hook runs. A hook "allow" closes the dialog at once. If the user answers "yes" in the terminal
  the hook is NOT told and keeps running (no signal, stdout stays open); if the user presses Esc
  the hook gets SIGTERM. Blank lines before the JSON are harmless. Notification
  `permission_prompt` fires only if the dialog is still open after about 6 s. No Stop event
  follows an Esc, so an interrupted session can look "working" until its next event.
- To test hooks without the author: run `claude --model haiku` in a detached tmux session (unset
  the inherited `CLAUDE*` variables), drive it with `tmux send-keys`, read it with `capture-pane`.
- `asyncRewake` facts (measured 2026-11-16): a hook with `asyncRewake: true` that exits 2 wakes
  an idle session within a second; its stderr reaches Claude and the terminal shows "Stop hook
  feedback". Delivered while the session is busy, it is handled right after the current reply.
  It works from both Stop and SessionStart. Claude Code kills these hooks when the session exits.
  Its `timeout` is enforced, so the listener asks for 86400 s.
- Speech-to-text facts: `small.en` (int8, CPU) transcribes 4.4 s of speech in about 0.7 s,
  `base.en` in 0.3 s but drops punctuation. The WSLg microphone works through `parec`. Without a
  tail after key release the last word is cut. After a hub restart idle sessions are unknown
  until their listener reconnects (it retries every 5 s).
- Not used but possible: channels could also inject messages and relay permission prompts, but
  need `--dangerously-load-development-channels` at every start.
- Overlay facts: it is ready about 0.6 s after launch. `Add-Type` in PowerShell 5.1 compiles
  C# 5 only (no `$""`, `?.`, `nameof`, `out var`), and the source is kept ASCII. Running the
  script from the `\\wsl.localhost\...` path with `-ExecutionPolicy Bypass` works here. The default
  position leaves 150 px on the right so it does not cover a maximized window's buttons.
  To see it from WSL without capturing the user's screen: send `config` with `opaque: true`, ask
  for `bounds`, and capture exactly that rectangle with `Graphics.CopyFromScreen`.
- Machine facts: PowerShell 5.1 with WPF, stdin pipes from WSL into `powershell.exe` work,
  execution policy undefined (use `-ExecutionPolicy Bypass`), WSLg mic is `RDPSource`,
  `dev.tty.legacy_tiocsti=0` (no typing into a terminal from outside), tmux 3.6 installed.

## Deps (current machine)

- apt: `jq`, `curl`, `espeak-ng`, `pulseaudio-utils` (`paplay`)
- `uv` in `~/.local/bin`, with a Python 3.12 venv in `~/.local/share/kokoro/venv` (`kokoro-onnx`,
  `faster-whisper`; the Whisper model is downloaded to the Hugging Face cache on first use)
- `pulseaudio-utils` also provides `parec` for the microphone
- Models: `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the kokoro-onnx GitHub release `model-files-v1.0`.
  Piper 2023.11.14-2 binary plus `en_US-lessac-medium` from Hugging Face (fallback).

## Similar projects (researched 2026-11-15; star counts and details unverified)

None of these speak while the reply is still streaming. That's this project's differentiator.
Others: no extra LLM call (Claude writes its own spoken line), fully local and free, plain shell.

- **cc-vox**, github.com/BestSithInEU/cc-vox. Closest design: hooks ask for a "📢" summary
  line, the Stop hook speaks it (max 2 sentences), with a headless-Claude summary as fallback.
  Several backends (Qwen3-TTS, Fish Speech, Chatterbox, Kokoro in Docker, pocket-tts) and a playback lock. Plugin. About 1 star.
- **aloud**, github.com/softcane/aloud. macOS only (Claude Code + Codex). Kokoro kept warm in a
  daemon, hooks talk to it over a Unix socket. Summarizes in code (strips markdown and code,
  redacts secrets). Priority interruption: question > permission > failure > done. pipx. About 9 stars.
- **codeshrew blog "persistent voice mode"**, codeshrew.github.io/ai-lab-notes (2026-02-13).
  Re-injects a short reminder every turn; Claude calls a say script (Kokoro over HTTP); uses flock to stop overlaps.
- **claude-code-hooks-mastery (disler)**, github.com/disler/claude-code-hooks-mastery. Popular
  reference (about 4k stars). The Stop hook makes a separate LLM call for the message; ElevenLabs, then OpenAI, then pyttsx3; a TTS queue.
- **claude-voice (adjit)**, github.com/adjit/claude-voice. Kokoro ONNX with paplay/aplay/ffplay
  (very close stack). Stop-hook summary (200 characters max) and/or an MCP speak tool. Plugin. About 0 stars.
- **VoiceMode**, github.com/mbailey/voicemode. Two-way voice conversation (Whisper.cpp + Kokoro, or OpenAI),
  MCP or plugin. About 1.5k stars, the most active. A different goal: conversation, not summaries.
- **herald**, github.com/al3xjohnson/herald. Summary (max_words) or alert sounds; macOS/Windows voices or ElevenLabs.
- **clarvis**, github.com/nickpending/clarvis. Tag prefix plus an LLM summary; ElevenLabs or system voice. Archived 2026-04.
- **AgentVoices**, bennycheung.github.io/hear-your-ai-agents-work. A `COMPLETED:` line extracted by regex;
  one ElevenLabs voice per subagent; macOS.

Ideas worth borrowing: warm TTS daemon (aloud), cross-session queue/flock (codeshrew, cc-vox),
priority interruption (aloud), stop speech on a new prompt.

### Overlays and session monitors (researched 2026-11-16; details unverified)

All silent. None speaks, so voice + several sessions + overlay + answering without switching is open.

- **macOS notch apps** (crowded): Claude Island, Vibe Notch, Vibe Island, Bezel, Claude Visor,
  CodeIsland. Session list plus Allow/Deny from the notch, fed by hooks.
- **claude-code-session-hud**, github.com/tchurkin/claude-code-session-hud. Windows only: a
  colored tab per chat with its state, usage meter. About 1 star.
- **claudeye** (overlay for sessions in tmux panes), **ClawdPanel** (token usage bar),
  **claude-hud** by jarrodwatts (a status line, one session; popular).
