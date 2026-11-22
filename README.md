<img src="assets/logo.png" width="96" alt="The mark: a round light with voice bars in it and an arc around it">

# Sidetone

*Sidetone was called claude-speaks until November 2026.*

Eyes-free Claude Code. A local voice tells you, in one or two sentences, what each session just
did. It starts speaking while the reply is still streaming, so you keep your eyes on your own work.

I built it because I code next to Claude Code, and every reply meant moving my eyes to another
screen, reading, and finding my place again. The model was fast; noticing it and switching to
it was the slow part. Sidetone cuts that delay in both directions: Claude reaches you by
voice and a small overlay, and you answer by hotkey or by talking, without changing windows.

Everything runs on your machine. No cloud speech service, and no extra LLM call: Claude writes
its own spoken line as the first line of its reply.

> Status: built for and tested on one machine (Windows 11 + WSL2 Ubuntu). The voice parts are
> plain Linux and should work elsewhere; macOS is untested. The overlay and hotkeys are Windows only.

## What you get

- **A spoken line per turn.** "Tests pass, ready for your review." Never the whole reply.
- **It starts early.** The line is spoken as soon as it streams in. Sound comes out about
  0.3 s after the line is written (measured on the speakers' own output), often before the
  rest of the reply has finished printing.
- **Several sessions take turns.** One line at a time. "Needs you" goes before "done". Each
  project has its own voice. The overlay shows who is talking; without an overlay the
  project's name is spoken first when more than one session is active.
- **A glass overlay** (Windows): a slim bar of frosted glass with one status light per session:
  a spinner while it works, a pulsing amber light when it needs you, a check when it is done.
  Move the mouse onto it and a panel unfolds beside it with each session's name (each in its
  own color, chosen to be as different as possible from the colors of the sessions already
  open; `"colors"` in the settings is a list of your own), a short title, what it is doing, its task progress and elapsed time. While a session talks, a bubble
  next to its light shows the sentence, and bars follow the real sound of the voice.
  `Ctrl+Alt+L` keeps the panel out. Hold `Ctrl+Alt` and grab the bar with the mouse to drag it
  anywhere, on any monitor; it stays there. Without those keys the mouse goes straight through
  the bar to whatever is underneath (`"drag_keys": ""` lets you drag it any time), and it never
  takes focus. Everything that moves is drawn in step with your screen's refresh rate.
- **Answer permission prompts from anywhere.** The overlay shows what a session wants to run.
  `Ctrl+Alt+Y` allows, `Ctrl+Alt+N` denies. The dialog in the terminal keeps working too;
  whichever you use first wins.
- **Answer Claude's questions with a number key, or in your own words.** A multiple-choice
  question is shown with numbered options and read out; `Ctrl+Alt+1` to `4` picks one. Or hold
  the talk key and say something else: your words go back as the answer.
- **Push-to-talk follow-ups.** Hold `Ctrl+Alt+Space`, say "also add a test for the empty case",
  release. While you hold the key, that session's light and the bubble next to it show your
  own voice as a wave, so you can see the microphone hears you, and a glint of light runs along
  "Release to send" and the other words about each step (`"talk_text"` under `overlay`: `shimmer`, `pulse` or `still`;
  `"talk_text_color"` gives the words a color of your own). A local Whisper model transcribes it and
  it is sent at once to the session in focus, even if that session is idle; the light then
  shows a paper plane (moving dots while it works, a struck-out microphone when nothing went
  out; `"talk_sign": "line"` under `overlay` puts that sign beside the session's name
  instead), the bubble shows what was sent, and a short sound tells you without looking: two notes going up for
  sent, the same note twice when it waits for a busy session, two notes going down when it was
  not sent (`talk_feedback` can be `sound`, `voice` or `none`; `sound_volume` is 0 to 1). The focus is on
  whichever session spoke last, shown by a frame around its light; hold `Ctrl+Alt` and turn the
  mouse wheel to move it to another session, or type a prompt to one (`"focus_on_prompt": false` turns that off). Sent the wrong thing? `Ctrl+Alt+Backspace` within
  four seconds takes it back: words still waiting for a busy session are removed, and a session
  that already has them is told to ignore them (`unsend_seconds`; 0 turns it off). If you would rather check the text first, set
  `followup_delay` to a few seconds (`Ctrl+Alt+Backspace` takes it back in that time) or
  `followup_confirm` to `true` (nothing is sent until you tap the talk key again).
- **Not heard on a Discord call.** While you hold the talk key, Discord mutes you, and it
  unmutes you when you let go. It takes one minute of setup in Discord: see
  [On a Discord call](#on-a-discord-call).
- **Side questions.** Words for a busy session normally reach it after the step it is on, and
  change what it does. Start with "by the way" ("by the way, which file was that?") and they do not wait: a throwaway
  copy of that session answers within a few seconds from what the session already knows, in
  the session's voice, while the session works on undisturbed. It never sees the question or
  the answer, and the copy cannot read files or run commands, like Claude Code's own `/btw`.
  `Ctrl+Alt+Backspace` drops the question while it is being answered; if no answer comes,
  the words go to the session after all. `aside` is `busy` (default), `always` (idle sessions
  too) or `off`; `aside_words` are the openings. `aside_model` is `session` (default: the
  session's own model, which reuses the conversation the session has saved, so an answer
  takes a few seconds even in a long session) or a model's name such as `haiku`.
- **Clear the chat by voice.** Say "clear the chat" (or "clear the context", "slash clear")
  to a session that is at its prompt and the VS Code extension types `/clear` into its
  terminal; the session never gets the words. A session cannot run `/clear` itself, and
  only the editor can type into its terminals, so this needs the extension. A session that
  is working or asking you something is left alone and its light says so. `clear_by_voice:
  false` turns it off; `clear_words` are the phrases.
- **Which terminal is which.** With several sessions open, the terminal of the session in focus
  takes a faint tint of that session's color, the color its name has in the overlay, and lights
  up brighter for a moment when you move the focus to it. No extension is needed: the hub
  writes to the terminal each session runs in, which works in VS Code's terminal and most
  others. `sidetone terminal tint all` lets every terminal wear its color all the time,
  `tint off` none; `sidetone terminal find` lights up the one in focus again.
- **Go to a terminal, and its session has the focus.** With the small VS Code extension
  (the installer offers it when it finds VS Code, `--vscode` or `--no-vscode` answers ahead;
  or `sidetone vscode install`, run in a VS Code terminal), switching to another terminal
  in VS Code selects the session running there, so push-to-talk goes to the terminal you are
  looking at. VS Code reports a change of terminal, not every click: going back into the
  terminal you were last in changes nothing. `sidetone terminal follow off` turns it off.
  The other way round, `sidetone terminal show` takes you to the terminal of the session
  in focus (give it a key with `"jump"` under `hotkeys`; it has none by default). It works
  inside VS Code's window and does not bring that window in front of other programs.
- **How much is used.** Ask by voice ("what's my usage?") and the hub says how much of the
  plan's five hours and week is used and when they start again; the words go to no session.
  `sidetone usage` prints the same. A thin arc around each session's light shows how full its context is (`context_shown`: `arc`, `text`, `both`, `off`), and a card under the rows gives the figures of the session under the mouse: context, tokens of the reply, time and tasks.
- **Say it again.** `Ctrl+Alt+R` repeats the last line of the session in focus.
- **Your own voices.** Pick a voice per project, blend two into a new one, or load a Kokoro
  voice file.

### Layouts

The sessions can be shown in two ways. `Ctrl+Alt+K` switches between them, and the voice says
which one you are on.

- **bar**: a column of lights in one piece of glass at the side of the screen, wherever you
  drag it; the details unfold beside it.
- **island**: a row of lights, each with a dash of its session's color, at the top middle of
  the screen until you drag it somewhere else; the bubble and the details drop down from it
  (or open upward when it sits in the lower half of the screen).

## Install

Needs: Linux or WSL2, a recent [Claude Code](https://claude.com/claude-code) (built on 2.1.325;
it relies on the `MessageDisplay`, `PermissionRequest` and `asyncRewake` hooks), `jq`, `curl`,
PulseAudio tools (`paplay`, `parec`) and [`uv`](https://docs.astral.sh/uv/).

```bash
sudo apt install jq curl pulseaudio-utils     # Debian/Ubuntu
git clone https://github.com/SimoneWang02/sidetone && cd sidetone
./install.sh
```

`install.sh` creates a Python environment in `~/.local/share/kokoro/venv`, downloads the Kokoro
voice model (about 350 MB), and adds the hooks to `~/.claude/settings.json`. Your existing
hooks are kept and a backup of the file is written first. It also links the command into
`~/.local/bin` as `sidetone` and the shorter `st`. It asks once which languages you will
speak to it (`./install.sh --languages en,it` answers in advance; `sidetone languages`
changes it later). The Whisper model for push-to-talk (about 460 MB for the default size) is
downloaded too; `--no-models` leaves it for the first time you use the talk key. Where it finds an
NVIDIA graphics card it offers to run push-to-talk and the voice there (`--gpu` or `--no-gpu`
answers ahead): a larger speech model that gets more words right, as fast as the small one on the
processor, and each spoken line starting sooner, for about 4.5 GB of downloads. `./uninstall.sh` removes the hooks again.

Start a new Claude Code session and it speaks. To see and hear everything without doing real
work, run `st demo` in a terminal.

## Using it

| Key (Windows) | Does |
|---|---|
| `Ctrl+Alt+L` | Overlay: keep the panel out ↔ only the lights |
| `Ctrl+Alt+K` | Overlay: switch layout (bar ↔ island) |
| `Ctrl+Alt+S` | Open or close the settings window |
| `Ctrl+Alt+Y` / `Ctrl+Alt+N` | Allow / deny the permission prompt shown in the overlay |
| `Ctrl+Alt+1` … `Ctrl+Alt+4` | Answer the question shown in the overlay |
| hold `Ctrl+Alt` | Show the details panel while held |
| `Ctrl+Alt+Up` / `Ctrl+Alt+Down` | Move the focus to the session above or below (claimed only while two or more are open). In the island layout it is `Ctrl+Alt+Left` / `Ctrl+Alt+Right` |
| `Ctrl+Alt` + mouse wheel | The same with the wheel |
| hold `Ctrl+Alt+Space` | Talk to the session in focus; release to send |
| `Ctrl+Alt+Backspace` | Stop recording, take back a follow-up, cut the line being spoken, or stop the session in focus (at once in VS Code with the extension, elsewhere at its next step) |
| none (`jump` under `hotkeys`) | Go to the terminal of the session in focus: VS Code brings it to the front with the keyboard in it (needs the extension; claimed only while that can be done). `sidetone terminal show` does the same |
| `Ctrl+Alt+R` | Repeat the last line of the session in focus |

The keys that answer something (allow, deny, the numbers, cancel) are only claimed while they
can act, so other programs keep those combinations the rest of the time. Every key can be
changed or switched off in the settings file. With the panel kept out, rest the mouse on it
for a moment to see the last few lines that were spoken.

```
sidetone status                 what each session is doing, and what is queued
sidetone say [-v VOICE] TEXT    speak a line
sidetone stop                   stop speaking and clear the queue
sidetone on | off               voice on or off for every session
sidetone allow | deny           answer the permission prompt on screen
sidetone answer N               pick option N of the question on screen
sidetone follow-up [-s PROJECT] TEXT
sidetone target [PROJECT]       who a spoken follow-up goes to
sidetone repeat                 hear the focused session's last line again
sidetone sound sent|queued|failed   hear the short sounds that answer push-to-talk
sidetone discord-key            press F24 in 3 s, for Discord's Push to Mute keybind to record
sidetone voices                 every voice, and which project has which
sidetone languages en,it        the languages push-to-talk listens for (name only the ones you speak)
sidetone voice PROJECT VOICE    give a project a voice
sidetone voice mix NAME af_heart=0.6 bm_george=0.4     blend a new voice
sidetone voice add NAME FILE    load your own Kokoro voice file (.npy)
sidetone overlay dots|list|toggle|restart     only the lights, or kept open
sidetone overlay layout NAME|next   bar or island
sidetone overlay move           makes the bar easy to find and drag (or hold Ctrl+Alt and drag it)
sidetone overlay monitor N | corner top-left|top-right|bottom-left|bottom-right
sidetone terminal               how sessions' own terminals are marked
sidetone terminal tint focus|all|off     whose terminal wears its session's color
sidetone terminal find [PROJECT]         light a session's terminal up for a moment
sidetone terminal show [PROJECT]         bring a session's terminal to the front in VS Code
sidetone terminal strength N | background COLOR | pulse on|off|N | title on|off
sidetone terminal follow on|off          going to a terminal in VS Code selects its session
sidetone vscode install|uninstall        the VS Code extension that reports the terminal you are in
sidetone settings               open the settings window (Ctrl+Alt+S); "settings close" shuts it
sidetone settings list          every setting the window has, and what it is now
sidetone settings KEY VALUE     change one at once, e.g. settings overlay.layout island
sidetone demo                   three made-up sessions through every state
sidetone hub start|stop|restart
sidetone log                    follow the speech log
```

The settings window (`Ctrl+Alt+S`) has the ones most people change: voice, voices per project,
push-to-talk, how the overlay looks, the figures, the terminal tint and every hotkey. A change
takes effect at once and is written to `~/.config/sidetone/config.json`. That file is
optional and holds all of them:

```json
{
  "voices": { "my-project": "bm_george" },
  "label": "never",
  "repeat": "focus",
  "titles": "ask",
  "whisper_model": "small.en",
  "followup_delay": 0,
  "followup_confirm": false,
  "unsend_seconds": 4,
  "talk_feedback": "sound",
  "sound_volume": 0.3,
  "aside": "busy",
  "aside_words": ["by the way", "btw"],
  "overlay": {
    "layout": "bar",
    "corner": "top-right",
    "glass": "blur",
    "opacity": 0.9,
    "talk_sign": "light",
    "talk_text": "shimmer",
    "keep_talk_key": "held",
    "talk_frees_keys": true,
    "drag_keys": "Ctrl+Alt",
    "row_lines": 1,
    "history": "session",
    "history_after": 0.1,
    "hover": "always",
    "hotkeys": { "talk": "Ctrl+Alt+Space", "toggle": "Ctrl+Alt+L" }
  },
  "terminal": {
    "tint": "focus",
    "strength": 0.08,
    "background": "#181818",
    "light_background": "#F8F8F8",
    "pulse": true,
    "pulse_strength": 0.15,
    "title": false,
    "follow": true
  }
}
```

`terminal.background` is your terminal's own background color, which the session's color is
mixed into; the default suits VS Code's Dark Modern theme. With the VS Code extension, a window
with a light theme uses `terminal.light_background` instead (the default suits Light Modern);
set either if your theme's terminal is another color.
`terminal.title` also writes the session's name into the terminal's title. A VS Code tab only
shows that with `"terminal.integrated.tabs.title": "${sequence}"` in VS Code's settings, and
Claude Code writes a title of its own unless `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` is `1`, which
`"env": {"CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"}` in `~/.claude/settings.json` does for every session.

### On a Discord call

Without this, what you say to a session also goes to the people in your call. Sidetone cannot
mute Discord from the outside (Windows ignores a mute set on another program's microphone), and
Discord cannot see the talk key: Sidetone keeps that key from every other program while you hold
it, so it does not type a space or pause a video in the window you are in. So Sidetone holds down
a second key while you talk, `F24` (no keyboard has it, so nothing else reacts), and Discord's own
**Push to Mute** does the muting. Set it up once, in the Discord desktop app:

1. User Settings (the gear at the bottom left), then **Keybinds** under App Settings.
2. **Add a Keybind**. A new row appears at the top of the list; click "Unassigned" under Action
   and choose **Push to Mute**.
3. Click the row's keybind box so it records, then run `sidetone discord-key`. It presses `F24`
   for you after three seconds. Keep your hands off the keyboard until the box shows `F24`
   alone: `Ctrl + F24` never matches.
4. **Stop Recording**, and close Discord's settings: its keybinds are off while that page is open.

To check: hold the talk key and speak while you watch your picture in a voice channel. The green
ring around it stays dark.

Push to Mute works when Discord is set to Voice Activity; with Push to Talk, Discord sends nothing
unless you hold its own key anyway. `push_to_mute` in `config.json` turns this off, and
`push_to_mute_key` holds another key instead, for another program with a push-to-mute key of
its own.

## How it works

```
Claude sessions ──hooks (bash + curl)──▶ hub (Python) ──stdin──▶ overlay (Windows)
                  Unix socket, owner-only   voice · queue · state  ◀─stdout── hotkeys
```

- A `UserPromptSubmit` hook asks Claude to open its final message with one line inside a speak
  tag. A `MessageDisplay` hook sees that line the moment it streams in, hands it to the hub and
  shows it as "🔊 …". The same tag carries a title of a few words that Claude gives the session,
  which is what the overlay shows beside the project name (`"titles": "auto"` turns that off).
- The **hub** is one small background process. It keeps the Kokoro voice loaded, speaks one
  line at a time, and tracks what every session is doing from the other hooks. It listens on a
  Unix socket that only your user can open, never on a network port.
- The **overlay** is a small Windows program. The hub builds it on first start from
  `overlay/Overlay.cs` with the C# compiler that ships with Windows (nothing to install; it
  lands in `%LOCALAPPDATA%\sidetone`), runs it as a child, and talks to it over its
  stdin and stdout. Windows itself blurs what is behind the glass. While a line plays, the hub
  listens to the speakers' own output and sends its loudness, which is what the wave draws.
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
- Push-to-talk listens for the languages you name: `sidetone languages en,it` (the install
  script asks the same question). A sentence of four seconds is text in about 0.7 to 0.8 s,
  with one language or with five (measured with `tests/stt_speed.py` on a 24-thread desktop
  CPU, no graphics card). With two or more, each recording is taken as whichever of your
  languages it sounds most like, so name only the ones you speak.
  English alone uses the English-only model, anything else the multilingual one of the same size.
  `auto` allows any language, but short sentences are easily mistaken for the wrong one. The
  command writes `whisper_model` and `whisper_language` in the settings, which you can also
  set by hand, for example to a larger model. Claude gets your words in the language you
  spoke; its spoken summaries stay in English.
- Own voices are Kokoro voice files or blends of existing voices. Cloning a voice from a
  recording is not something Kokoro can do.
- Without Kokoro the hub falls back to the system voice (macOS `say`, speech-dispatcher or
  espeak-ng): one voice for every session, everything else the same.
- The overlay does not show over games in exclusive fullscreen; use borderless windowed mode.
  The voice still works.
- The glass has rounded corners on Windows 11 and square ones on Windows 10. `"glass": "none"`
  gives plain dark glass without the blur; `"acrylic"` asks Windows for its heavier blur, which
  on Windows 11 comes out the same as `"blur"`.
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

128 tests with a silent voice and a fake microphone. They include the real hook scripts talking
to a hub over its socket, and a hub process that is killed and restarted.
`python3 tests/overlay_check.py OUT_DIR --glass` (Windows/WSL) saves a picture of each overlay
view. It captures only the overlay's own rectangles, and shows the see-through glass over a
test card of its own, so nothing else on your screen ends up in a picture.

## License

[MIT](LICENSE). It downloads and uses, but does not include:

- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) voice model, Apache 2.0, through
  [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and OpenAI's Whisper models
- Optionally [Piper](https://github.com/rhasspy/piper) as a fallback voice; each Piper voice
  has its own license in its model card
