# claude-speaks

Eyes-free Claude Code. A local voice tells you, in one or two sentences, what each session just
did. It starts speaking while the reply is still streaming, so you keep your eyes on your own work.

I built it because I code next to Claude Code, and every reply meant moving my eyes to another
screen, reading, and finding my place again. The model was fast; noticing it and switching to
it was the slow part. claude-speaks cuts that delay in both directions: Claude reaches you by
voice and a small overlay, and you answer by hotkey or by talking, without changing windows.

Everything runs on your machine. No cloud speech service, and no extra LLM call: Claude writes
its own spoken line as the first line of its reply.

> Status: built for and tested on one machine (Windows 11 + WSL2 Ubuntu). The voice parts are
> plain Linux and should work elsewhere; macOS is untested. The overlay and hotkeys are Windows only.

## What you get

- **A spoken line per turn.** "Tests pass, ready for your review." Never the whole reply.
- **It starts early.** The line is spoken as soon as it streams in, about 0.2 s after it is
  written, often before the rest of the reply has finished printing.
- **Several sessions take turns.** One line at a time. "Needs you" goes before "done". Each
  project has its own voice, and its name is spoken first when more than one session is active.
- **An overlay** (Windows): a faint dot per session in a screen corner. When something is said
  it expands to one line for a few seconds. `Ctrl+Alt+L` switches to a full list with what each
  session is doing, its task progress and elapsed time. It is see-through, click-through and
  never takes focus.
- **Answer permission prompts from anywhere.** The overlay shows what a session wants to run.
  `Ctrl+Alt+Y` allows, `Ctrl+Alt+N` denies. The dialog in the terminal keeps working too;
  whichever you use first wins.
- **Answer Claude's questions with a number key.** A multiple-choice question is shown with
  numbered options and read out; `Ctrl+Alt+1` to `4` picks one.
- **Push-to-talk follow-ups.** Hold `Ctrl+Alt+Space`, say "also add a test for the empty case",
  release. A local Whisper model transcribes it, the overlay shows the text for two seconds
  (`Ctrl+Alt+Backspace` takes it back), and it goes to the session that spoke last, even if that
  session is idle. A quick tap of the same key picks another session. A session that acts
  without asking (auto, accept-edits or bypass mode) only gets it after a confirming tap.
- **Catch up.** `Ctrl+Alt+U` replays what your sessions said since you were last there;
  `Ctrl+Alt+R` repeats the last line. Long turns say "3 of 5 steps done" along the way.
- **Your own voices.** Pick a voice per project, blend two into a new one, or load a Kokoro
  voice file.

## Install

Needs: Linux or WSL2, a recent [Claude Code](https://claude.com/claude-code) (built on 2.1.325;
it relies on the `MessageDisplay`, `PermissionRequest` and `asyncRewake` hooks), `jq`, `curl`,
PulseAudio tools (`paplay`, `parec`) and [`uv`](https://docs.astral.sh/uv/).

```bash
sudo apt install jq curl pulseaudio-utils     # Debian/Ubuntu
git clone https://github.com/SimoneWang02/claude-speaks && cd claude-speaks
./install.sh
```

`install.sh` creates a Python environment in `~/.local/share/kokoro/venv`, downloads the Kokoro
voice model (about 350 MB), and adds the hooks to `~/.claude/settings.json`. Your existing
hooks are kept and a backup of the file is written first. It also links the command into
`~/.local/bin` as `claude-speaks` and the shorter `cs`. The Whisper model for push-to-talk
(about 250 MB) is downloaded the first time you use the talk key. `./uninstall.sh` removes the
hooks again.

Start a new Claude Code session and it speaks. To see and hear everything without doing real
work, run `cs demo` in a terminal.

## Using it

| Key (Windows) | Does |
|---|---|
| `Ctrl+Alt+L` | Overlay: dots ↔ list |
| `Ctrl+Alt+Y` / `Ctrl+Alt+N` | Allow / deny the permission prompt shown in the overlay |
| `Ctrl+Alt+1` … `Ctrl+Alt+4` | Answer the question shown in the overlay |
| hold `Ctrl+Alt+Space` | Talk to the session that spoke last; a quick tap picks the next session, or confirms a follow-up waiting for it |
| `Ctrl+Alt+Backspace` | Take back a follow-up, stop recording, or cut the line being spoken |
| `Ctrl+Alt+U` | Replay what was said since you were last there |
| `Ctrl+Alt+R` | Repeat the last line |

The keys that answer something (allow, deny, the numbers, cancel) are only claimed while they
can act, so other programs keep those combinations the rest of the time. Every key can be
changed or switched off in the settings file. Rest the mouse on the list for a moment to see
the last few lines that were spoken.

```
claude-speaks status                 what each session is doing, and what is queued
claude-speaks say [-v VOICE] TEXT    speak a line
claude-speaks stop                   stop speaking and clear the queue
claude-speaks on | off               voice on or off for every session
claude-speaks allow | deny           answer the permission prompt on screen
claude-speaks answer N               pick option N of the question on screen
claude-speaks follow-up [-s PROJECT] TEXT
claude-speaks target [PROJECT]       who a spoken follow-up goes to
claude-speaks missed | repeat        catch up, or hear the last line again
claude-speaks voices                 every voice, and which project has which
claude-speaks voice PROJECT VOICE    give a project a voice
claude-speaks voice mix NAME af_heart=0.6 bm_george=0.4     blend a new voice
claude-speaks voice add NAME FILE    load your own Kokoro voice file (.npy)
claude-speaks overlay dots|list|toggle|restart
claude-speaks overlay move           drag it somewhere else; it stays there
claude-speaks overlay monitor N | corner top-left|top-right|bottom-left|bottom-right
claude-speaks demo                   three made-up sessions through every state
claude-speaks hub start|stop|restart
claude-speaks log                    follow the speech log
```

Settings are optional and live in `~/.config/claude-speaks/config.json`:

```json
{
  "voices": { "my-project": "bm_george" },
  "label": "auto",
  "whisper_model": "small.en",
  "followup_confirm": "auto",
  "overlay": {
    "corner": "top-right",
    "opacity": 0.35,
    "hotkeys": { "talk": "Ctrl+Alt+Space", "toggle": "Ctrl+Alt+L" }
  }
}
```

## How it works

```
Claude sessions ──hooks (bash + curl)──▶ hub (Python) ──stdin──▶ overlay (Windows)
                  Unix socket, owner-only   voice · queue · state  ◀─stdout── hotkeys
```

- A `UserPromptSubmit` hook asks Claude to open its final message with one line inside a speak
  tag. A `MessageDisplay` hook sees that line the moment it streams in, hands it to the hub and
  shows it as "🔊 …".
- The **hub** is one small background process. It keeps the Kokoro voice loaded, speaks one
  line at a time, and tracks what every session is doing from the other hooks. It listens on a
  Unix socket that only your user can open, never on a network port.
- The **overlay** is a child of the hub, started through `powershell.exe`. The two talk over
  the child's stdin and stdout.
- A `PermissionRequest` hook holds each permission prompt open on the hub until you answer it
  in either place. The voice only announces a prompt that has waited about six seconds, so it
  stays quiet when you are answering in the terminal anyway.
- A background `asyncRewake` hook per session waits on the hub. When you send a follow-up it
  hands the text to Claude, which wakes the session.
- If the hub is not running, every hook falls back to speaking directly, so the voice never
  depends on it.

## Costs and limits

- A few dozen extra tokens per prompt (the instruction and Claude's spoken line).
- The hub uses about 0.5 GB of memory with the voice loaded, and about 1.2 GB while the Whisper
  model is loaded (from the first push-to-talk until ten minutes after the last one). Each spoken
  line is a short burst of CPU.
- Push-to-talk understands English out of the box. For another language set `whisper_model` to
  a multilingual model such as `small` and `whisper_language` to its code or `auto`.
- Own voices are Kokoro voice files or blends of existing voices. Cloning a voice from a
  recording is not something Kokoro can do.
- Without Kokoro the hub falls back to the system voice (macOS `say`, speech-dispatcher or
  espeak-ng): one voice for every session, everything else the same.
- The overlay does not show over games in exclusive fullscreen; use borderless windowed mode.
  The voice still works.
- A follow-up reaches Claude as a hook message, so in the terminal it reads "Stop hook
  feedback" instead of your words.
- If a prompt waited more than six seconds and you then approve it in the terminal, the session
  stays marked "needs you" until that tool finishes.
- Question keys handle single-choice questions with up to four options; others are announced
  and answered in the terminal.

## Tests

```bash
~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests
```

69 tests with a silent voice and a fake microphone. They include the real hook scripts talking
to a hub over its socket, and a hub process that is killed and restarted.
`python3 tests/overlay_check.py OUT_DIR` (Windows/WSL) saves a picture of each overlay view.

## License

[MIT](LICENSE). It downloads and uses, but does not include:

- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) voice model, Apache 2.0, through
  [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and OpenAI's Whisper models
- Optionally [Piper](https://github.com/rhasspy/piper) as a fallback voice; each Piper voice
  has its own license in its model card
