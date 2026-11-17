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
- `README.md`, `LICENSE` (MIT) and `install.sh` / `uninstall.sh` exist since 2026-11-16. The
  install script merges the hooks into an existing `settings.json` (tested on a throwaway home
  folder) but its download and environment steps have not been run on a clean machine.
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
Second round, same day, on the author's request (all built and pushed; verified from WSL only):
- Weak spots fixed: session state now also read from Claude Code's own session files (Esc,
  closed terminals); follow-ups to sessions that act without asking need a confirming tap;
  other languages and unloading for Whisper; talk target marked in the list; system-voice
  engines when Kokoro is missing; `install.sh` run in throwaway folders.
- Voices: choose per project, blend (`voice mix`), load a Kokoro voice file (`voice add`).
  The author asked for "selectable or uploadable"; cloning from a recording is not possible
  with Kokoro and was not built. A settings panel (their earlier idea) is still open.
- Features: number keys answer Claude's questions, `Ctrl+Alt+U` catch-up, `Ctrl+Alt+R` repeat,
  spoken progress in long turns.
- Overlay polish: monitor choice, drag to move (`claude-speaks overlay move`), history on hover.
- **Still to be checked by the author** in addition to the list above: dragging the overlay,
  hovering the list, the number keys, `Ctrl+Alt+U`/`R`, and the confirming tap.

Third round, 2026-11-17: the author ran `cs demo` and said the overlay was not what they had
pictured: "i was expecting an executable that create the overlay with glass like design. for
each session a status, and overall vertical so when on focus, each session display a quick
title and if a session is speaking make a 'wave'-like vfx like someone speaking and the audio
is visualized". Rebuilt to that (verified from WSL by pictures only; **the author has not
seen it yet**):
- a compiled Windows program (built by the hub with Windows' own `csc.exe`), not a script
- a vertical glass bar with one animated status light per session; real blur by Windows
- opens under the mouse ("on focus" was read as hover; `Ctrl+Alt+L` pins it open) to show
  name, a short title and activity per session. The author saw this version and said it
  "looks" right, then asked for direct dragging and more animation (built the same night)
- while a session talks: a speech bubble beside its light, and bars driven by the real sound
- `claude-speaks` and `cs` are linked into `~/.local/bin` by `install.sh`

Decisions: overlay is Windows-native (must be usable over games; no browser chrome);
sessions are told apart by a spoken label plus a stable voice per project.
Later: plugin packaging, a demo video with sound for the README, short sounds, stereo placement,
a "what did I miss" key, and a settings panel
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
  was active in the last 15 min and no overlay is on screen (the author, 2026-11-17: "i dont
  think it's necessary to say the project folder whenever it speaks"; the bubble and the voice
  already say who it is). `label: always` brings it back. Voice = stable hash of the name over a pool of 13 clearer
  English Kokoro voices, never one a live session already uses.
- `hub/overlay.py` + `overlay/Overlay.cs` (+ `overlay/overlay.ps1` as fallback): the on-screen
  overlay, a child process of the hub (only where `powershell.exe` exists). `overlay.build()`
  compiles `Overlay.cs` with `csc.exe` of .NET Framework 4 (ships with Windows; about 0.2 s)
  into `%LOCALAPPDATA%\claude-speaks\claude-speaks-overlay-<hash of the source>.exe`, once per
  version of the source; if that fails the same source runs through PowerShell `Add-Type`
  (`CLAUDE_SPEAKS_OVERLAY=script` forces that). The hub sends `config`, `state` (one
  ready-to-draw row per session, with `title` and `synth`), `flash` (a line shown for a few
  seconds, sent when it starts being spoken, or instead of speech when the voice is off) and
  `wave` (loudness values while a line plays); the program sends `ready`, `hotkey`, `mode`,
  `moved`, `bounds`, `error`. All logic lives in the hub so it can be tested; the C# only draws.
- What it draws: three glass windows (`Glass`). The **bar** is a column of status lights
  (`Orb`: spinner = working, pulsing amber "!" = needs you, check = done, cross = failed, small
  ring = idle, five voice bars = speaking). The **panel** unfolds beside the bar, each row level
  with its light: name, title, activity, meta; below the rows (above them for a bar at the
  bottom of the screen) come the request, the push-to-talk banner and the history. It is out
  in list mode, under the mouse, while moving, and while a request or banner is showing. The
  **bubble** appears beside the light of the session that is talking while the panel is away:
  name, title, the sentence, and the voice flowing behind the text. Mode names are still
  `dots` (lights only) and `list` (panel kept out).
- Motion (asked for by the author on 2026-11-17: "more fps, more animation ... when hovering
  the status the details pop out instantly with no animation"): one `Frame` step per
  `CompositionTarget.Rendering` (in step with the screen; about 150 to 190 a second on the
  author's machine), running only while something moves. The panel and bubble unfold by
  growing their window's height on a soft spring; rows slide in one after another; lights pop
  on a state change, send out a ring, draw their check stroke by stroke, grow under the mouse.
  `still: true` in `config` turns motion off for pictures. `bounds` replies carry `clock` and
  `frames`, so the frame rate can be measured from outside.
- Dragging (asked for the same day: "i just want it to be drag and move"): while the mouse is
  on the bar, the bar takes the mouse (move cursor, brighter edge). Left button down starts a
  drag that follows the cursor frame by frame until the button is up; a press that did not
  move it is re-sent as a click to whatever is underneath, so plain clicks still pass through.
  The drop is reported as `moved` (monitor, nearest corner, offsets) and saved to `config.json`.
  **Not tried with a real mouse yet** (it cannot be done from WSL without moving the user's cursor).
- Titles: `Session.title` is Claude Code's own name for the session (the `name` field of its
  session file, a slug such as `eyes-free-claude-speaks`, turned into words) and, until that
  exists, the first line of the last prompt, cut to 44 characters (`state.short_title`).
- Voice wave: `tts.Meter` runs `parec` on the default sink's monitor while a line plays, turns
  each 40 ms into a loudness from 0 to 1 and the hub forwards it as `wave`. It is the real
  output, so it is in step with the sound for every engine. Without `parec` the row says
  `synth` and the overlay makes up a motion. The same meter gives `heard=` in `voice.log`: the
  time from starting to speak a line until sound really came out.
- Permission prompts (`Request` in `hub/hub.py`): the overlay shows the oldest open request at once
  (what, the exact command, the keys) and keeps it solid until answered. The voice waits for
  Claude Code's own "still waiting" notification (about 6 s) so it does not nag someone answering
  in the terminal, then says "Permission needed: …". A request with no notification after
  `permission_grace` (9 s) counts as answered in the terminal. A hotkey only works after the
  request has been on screen 0.7 s; the hub says "Allowed." or "Denied." as feedback.
  Questions and plan approvals (`AskUserQuestion`, `ExitPlanMode`) are never offered to the hotkeys.
- Push-to-talk (`hub/stt.py` and the talk methods in `hub/hub.py`): while the talk key is held
  the voice goes quiet and `parec` records the default microphone; on release (plus a 0.4 s tail)
  `faster-whisper` `small.en` transcribes it. It is sent at once (the author, 2026-11-17: "too many
  clicks ... it's ctrl+alt+space and then again to confirm", and chose "send at once" over a
  pause): `followup_delay` is 0 and `followup_confirm` is off by default; both can be turned
  back on. The hub hands it to that session's listener, shows "sent → name: text" for 2.5 s and says
  "Sent.". Target: the session that spoke last; a quick tap of the talk key picks the next one.
  A busy session gets the follow-up right after its current reply. With no listener yet, the
  text waits in the hub until the session next stops. The cancel key also cuts the line being spoken.
- Hotkeys (rebind or blank them under `overlay.hotkeys`): always claimed are `toggle` Ctrl+Alt+L,
  `talk` Ctrl+Alt+Space, `repeat` Ctrl+Alt+R and `missed` Ctrl+Alt+U (Ctrl+Alt+M is taken by
  another program on the author's machine). Claimed only while they can act: `allow` Ctrl+Alt+Y,
  `deny` Ctrl+Alt+N, `option1`-`option4` Ctrl+Alt+1-4 and `cancel` Ctrl+Alt+Backspace.
- Focus (asked for by the author on 2026-11-17: "combine ctrl+alt and the mouse wheel to decide
  which session to focus on. also whichever spoke last gets focused"): the focus is the hub's
  `talk_target`, the session a spoken follow-up goes to. It moves to whoever speaks, and
  `Hub.focus(step)` moves it by hand and stops at the first and last session (the author asked
  that the wheel not jump from the bottom back to the top). Rows carry `target`; the overlay draws a frame that glides
  to that light and lights its row. `Ctrl+Alt` + wheel (`overlay.focus_wheel`, `""` turns it off)
  sends `focus_prev` / `focus_next` and brings the panel out for 1.6 s. Windows only reports
  the wheel to a background program through a low-level mouse hook, which sits in the path of
  all mouse input, so the overlay installs it only while those keys are down and there are at
  least two sessions, and swallows only the wheel. The wheel alone works while the mouse is on
  the bar. **Not tried with a real mouse yet.**
- Questions: `PermissionRequest` also fires for `AskUserQuestion`, with the questions and options
  in `tool_input`. Single-choice questions with 2 to 4 options become a `Request` with
  `questions`; `choose(n)` records the label and, after the last one, the hook returns allow
  with `updatedInput.answers` (question text → label). Others are only announced.
- History and catching up: the hub keeps the last 100 lines sessions said. `last_seen` moves on
  every prompt and hotkey; `catch_up()` replays lines newer than it. The overlay gets the last 6
  with each `state` and shows them while the cursor rests on the list (found by polling the
  cursor position, since the window is click-through).
- `hub/claude_sessions.py`: reads `~/.claude/sessions/<pid>.json` (pid, sessionId, status
  busy/idle). `Hub.reconcile()` runs every second: idle there but working here means the turn
  was interrupted; a session that had a file and lost it is gone. Undocumented files, so
  sessions that never had one are left alone.
- Voices: `voices.json` remembers project → voice; own voices are `.npy` style arrays of shape
  (510, 1, 256) in `~/.local/share/claude-speaks/voices/`, passed to Kokoro as arrays.
- Overlay placement: `monitor`, `corner`, `offset_x`, `offset_y` of the bar. Dragging it reports
  the nearest corner and offsets, which the hub saves into `config.json`. The panel and bubble
  go on the side of the bar that faces the middle of the screen.
- `tests/overlay_check.py OUT_DIR [--glass]`: manual check that saves a picture of every overlay view.
- `hub/demo.py`: three made-up sessions that go through every state (`claude-speaks demo`).
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/claude-speaks` (linked by `install.sh` into `~/.local/bin` as `claude-speaks` and `cs`;
  on the author's machine since 2026-11-16): `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `allow`/`deny`, `answer N`, `missed`, `repeat`, `voices`, `voice …`, `target [PROJECT]`,
  `follow-up [-s PROJECT] TEXT`, `talk start|stop|cancel`,
  `overlay dots|list|toggle|restart|move|monitor N|corner NAME`, `demo`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 76 tests with a silent engine and fake microphone, including the real hook
  scripts over a socket and a hub process that is killed and restarted.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/claude-speaks/config.json` with `voices` (project name → voice),
  `voice_pool`, `label` (`auto`/`always`/`never`), `max_age`, `idle_exit`, `default_voice`, `speed`,
  and `overlay` (`enabled`, `mode`, `monitor`, `corner`, `offset_x`, `offset_y`, `opacity`,
  `list_opacity`, `glass` (`blur`/`acrylic`/`none`), `flash_seconds`, `hotkeys`), `permission_grace`, `whisper_model`, `mic_source`, `followup_delay`,
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
  about 1.2 s without it (model reloaded per call). Measured on the sink's monitor
  (2026-11-17), real sound followed 0.4 s later for a labelled line, because `paplay` waits for
  more audio before it starts; with `--latency-msec=50` it follows within 0.07 s, so sound is
  out about 0.3 s after the line is written. `paplay`'s exit time says nothing reliable about
  when the sound ended on the WSLg sink.
- Glass facts (measured 2026-11-17 on Windows 11 build 26300 with a throwaway WPF window):
  `SetWindowCompositionAttribute` with accent state 3 (blur) or 4 (acrylic) blurs behind a
  WPF `AllowsTransparency` window, but always the whole window rectangle: `SetWindowRgn`
  clips the window's own drawing and not the blur, and a `DwmEnableBlurBehindWindow` region
  changes nothing. `DwmSetWindowAttribute(33 /*corner preference*/, 2)` rounds the window
  (about 8 px) and does clip the blur, and adds a soft shadow. So every piece of glass is its
  own window exactly as big as what it shows; free shapes such as capsules cannot be blurred.
  WPF removes `WS_EX_LAYERED` from a window without `AllowsTransparency`, so click-through
  needs `AllowsTransparency`. A `/target:winexe` program started from WSL still gets its
  stdin and stdout pipes.
- Motion facts (measured 2026-11-17): the blur does not fade with the window's opacity (at
  opacity 0.35 the content is faint and the blur is still full), so a fade-in would pop.
  Growing the window is the only smooth way to bring glass in, and a see-through WPF window
  only resizes cleanly while its top left corner stays put (the picture is drawn from that
  corner; moving and resizing in one go shows the old picture in the new place for a frame).
  Showing or resizing a window makes WPF render at once, which fires `Rendering` again from
  inside the handler: without a re-entry guard the steps nested about thirty deep and the
  motion froze for 0.2 s at the start of every opening. Measuring a size right after changing
  text needs `UpdateLayout()` first, or the old size comes back.
- Taking pictures of the overlay without the user's screen in them: ask for `bounds` (real
  window rectangles from `GetWindowRect`), capture, ask again and retake if they changed (a
  row that shrinks between the two leaves a strip of screen in the picture; this happened
  once). For the see-through look, put a test card window behind it first and only capture
  once that card reported it was drawn.
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
  script from the `\\wsl.localhost\...` path with `-ExecutionPolicy Bypass` works here. `csc.exe`
  has the same C# 5 limit. The default position is the top right, 96 px down, below the title
  bar and tabs of a maximized window. `opaque: true` in `config` draws it without see-through
  and without rounded corners, for pictures.
- Session-file facts (measured): `status` is only `busy` or `idle`; it stays `busy` during a
  permission dialog and flips to `idle` within 0.2 s of Esc. The file is removed when the
  session exits. The Bash tool's process is not a child of the session's pid, so "approved in
  the terminal, still running" cannot be seen that way.
- The Notification `permission_prompt` also fires for question dialogs after about 6 s.
- Memory: the hub holds about 0.5 GB with Kokoro loaded and about 1.2 GB once Whisper `small.en`
  has been loaded by the first push-to-talk.
- `claude-speaks hub stop` and `uninstall.sh` act on the hub of the current `XDG_RUNTIME_DIR`,
  whatever `HOME` is, so a test with a fake home folder still stops the real hub.
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
