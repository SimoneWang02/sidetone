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

1. **Hub and voice queue**: built; waiting for the author's check by ear.
2. **Windows overlay**: native window (PowerShell + WPF, started by the hub, JSON lines over
   stdin/stdout), see-through and click-through. Two modes switched by `Ctrl+Alt+L`: faint dots
   that expand to one line on a change, and a full list.
3. **Allow or deny by hotkey**: `PermissionRequest` hook long-polls the hub; `Ctrl+Alt+Y` /
   `Ctrl+Alt+N` from any app. First test whether the terminal dialog stays usable while the hook waits.
4. **Push-to-talk follow-ups**: hold `Ctrl+Alt+Space`, local `faster-whisper`, delivered to the
   session that spoke last through an `asyncRewake` hook (fallback: `tmux send-keys`).

The author checks each milestone by ear and eye before the next one starts.
Decisions: overlay is Windows-native (must be usable over games; no browser chrome);
sessions are told apart by a spoken label plus a stable voice per project.
Later: plugin packaging, `install.sh`, README with latency numbers and a demo video with sound,
short sounds, stereo placement, a "what did I miss" key, MIT license.

## How it works

```
Claude sessions ──hooks (bash + curl)──▶ hub (Python, in the Kokoro venv)
                  Unix socket, owner-only   session state · speech queue
```

| Hook event | Script | Job |
|---|---|---|
| UserPromptSubmit | `hooks/voice-reminder.sh` | Injects an instruction: open the final message with ONE line that is exactly a speak tag |
| MessageDisplay | `hooks/display.sh` | Runs per streamed batch. Sends a batch containing a speak tag to the hub, which queues the speech and returns the "🔊 …" rewrite |
| Stop | `hooks/speak.sh` | Tells the hub the turn ended; the hub speaks the line only if streaming missed it |
| Notification (`permission_prompt`, `elicitation_dialog`) | `hooks/notify.sh` | Hub marks the session "needs you" and says "I need your input" |
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
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/claude-speaks`: `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 21 tests with a silent engine, including the real hook scripts over a socket.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/claude-speaks/config.json` with `voices` (project name → voice),
  `voice_pool`, `label` (`auto`/`always`/`never`), `max_age`, `idle_exit`, `default_voice`, `speed`.
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
- Hook facts for the next milestones (from the docs, not yet tried): Notification
  `permission_prompt` fires only after the prompt has waited about 6 s, `PermissionRequest`
  fires at once and can return `decision.behavior` allow/deny; `asyncRewake: true` hooks wake
  an idle session when they exit 2 (their `timeout` is still enforced); hooks inherit the
  terminal's environment (e.g. `TMUX_PANE`); channels could also inject messages and relay
  permission prompts but need `--dangerously-load-development-channels`.
- Machine facts: PowerShell 5.1 with WPF, stdin pipes from WSL into `powershell.exe` work,
  execution policy undefined (use `-ExecutionPolicy Bypass`), WSLg mic is `RDPSource`,
  `dev.tty.legacy_tiocsti=0` (no typing into a terminal from outside), tmux 3.6 installed.

## Deps (current machine)

- apt: `jq`, `curl`, `espeak-ng`, `pulseaudio-utils` (`paplay`)
- `uv` in `~/.local/bin`, with a Python 3.12 venv in `~/.local/share/kokoro/venv` (`kokoro-onnx`)
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
