# claude-speaks

Brief voice mode for Claude Code. After each turn, a local voice reads a 1–2 sentence
spoken summary, never the full output. It starts speaking while the reply is still streaming.

## Status

- Working day to day on the author's machine (WSL2 Linux). The live copy runs from
  `~/.claude/hooks/` and is registered in `~/.claude/settings.json`.
- This repo is a **copy** of those scripts, not yet packaged. Paths inside still point
  at `$HOME/.claude/hooks/` and `~/.local/share/{kokoro,piper}`.
- Planned as a **private** GitHub repo to start. The author reviews and commits; Claude never commits or pushes.

## How it works

| Hook event | Script | Job |
|---|---|---|
| UserPromptSubmit | `hooks/voice-reminder.sh` | Injects an instruction: open the final message with ONE line that is exactly a speak tag |
| MessageDisplay | `hooks/display.sh` | Runs per streamed batch of lines. A line that is only a speak tag is spoken immediately and re-rendered as "🔊 …" |
| Stop | `hooks/speak.sh` | Fallback. Reads `last_assistant_message` (or polls the transcript for up to 3 s on older versions), skips the line if display.sh already spoke it |
| Notification (`permission_prompt`) | `hooks/notify.sh` | Says "I need your input" |

- `hooks/tts-lib.sh`: shared code. Picks the engine (macOS `say`, then Kokoro, then Piper,
  then `spd-say`, then `espeak-ng`). Runs `synth | paplay` under `setsid` so the whole
  process group can be killed. New speech stops old speech (pid file `.tts.pid`).
- `hooks/kokoro-say.py`: reads stdin, writes 24 kHz s16le PCM. Voice and speed come from
  `KOKORO_VOICE` (default `af_heart`) and `KOKORO_SPEED` (default 1.1).
- `hooks/settings-snippet.json`: the `hooks` block as registered in settings.json.
- Toggle: voice is off while `~/.claude/voice-off` exists.
- Runtime files (never commit): `voice.log` (contains spoken summaries), `.tts.pid`, `.state/`.

## Key facts learned

- MessageDisplay holds each batch until the hook returns, so keep `display.sh` fast:
  about 5 ms with no tag, about 50 ms with one. Output `hookSpecificOutput.displayContent`
  to replace the shown text. The transcript keeps the original.
- `final` marks the last batch. Deltas are whole lines except possibly the final one.
- Stop input has `last_assistant_message`. The transcript can lag, so it's only a fallback.
- Only own-line tags are spoken by display.sh, so inline mentions of the tag in prose are ignored.
- Kokoro on CPU takes about 1.2 s to synthesize two sentences, including model load (reloaded per call).

## Deps (current machine)

- apt: `jq`, `espeak-ng`, `pulseaudio-utils` (`paplay`)
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

## To discuss / do

1. Package as a Claude Code plugin (hooks via the plugin, paths via `${CLAUDE_PLUGIN_ROOT}`).
2. `install.sh` (deps, uv, model download, no bundled models), `uninstall.sh`, and an on/off command.
3. README: the problem it solves for the author, a demo video with sound, how it works, and
   the costs (a few dozen tokens per prompt, about 1 s before speech starts).
4. Possible improvements: a warm Kokoro daemon for lower latency; a cross-session queue
   (sessions currently cut each other off); stopping speech on a new prompt.
5. MIT license, plus links to the Kokoro (Apache 2.0) and Piper voice licenses.
6. Support claims: Linux/WSL tested, macOS untested.
