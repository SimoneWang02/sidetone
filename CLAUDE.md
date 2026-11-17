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
What is left (things to try by hand, open decisions, rough edges, ideas not started) is kept in
`TODO.md`; the author asked for that list to live in its own file. Update it when something
on it is done or a new idea comes up.

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
| Stop, SessionStart, UserPromptSubmit (`asyncRewake`) | `hooks/listen.sh` | Background listener: waits on the hub for a spoken follow-up for this session, prints it for Claude and exits 2, which wakes the session |
| SessionStart, SessionEnd, UserPromptSubmit, PreToolUse, PostToolUse(Failure), TaskCreated, TaskCompleted, StopFailure | `hooks/report.sh` (async) | Forwards the payload so the hub knows what each session is doing. `--start` also starts the hub |

- `hub/hub.py`: the one background process. HTTP over a Unix socket at
  `$XDG_RUNTIME_DIR/claude-speaks/hub.sock` (not a TCP port, so no web page or other machine can
  make it speak, and later approve or inject). Started lazily by the hooks, single instance by
  `flock`, exits after 30 min with no sessions.
- `hub/tts.py`: Kokoro kept loaded, synthesized sentence by sentence into `paplay`. Queue rules:
  one line at a time; needs-you > failed > done; a session's newer line replaces its queued one;
  lines older than 60 s are dropped; a new **typed** prompt silences that session.
- Replies are queued, not cut (the author, 2026-11-17: "could you queue all these responses
  instead of cutting?", after a reply was lost while they were talking). What happened: the
  reply arrived while the talk key was held, started on release, and three seconds later their
  own follow-up reached the same session as a "new prompt" and silenced it; the next session's
  line then played, so it sounded as if that session had cut in. Since then: a prompt that is
  markup (a voice follow-up arrives wrapped in `<task-notification>`) does not silence; the
  hub's own short answers ("Sent.", "Allowed.", kinds in `tts.FEEDBACK`) do not replace a
  session's waiting line; a line cut by the talk key is said again from its start on release,
  unless the key was held to answer that very session (`SpeechQueue.resume(answering)`); and
  time spent holding the key does not count towards the 60 s. `voice.log` now says `cut`
  for a line that was stopped, and such a line stays "not heard" for catching up.
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
- Rows keep one height (2026-11-17): a sentence being said used to wrap to three lines in its
  row of the panel, and since each light is kept level with its row, the bar stretched while
  the panel was out. The author noticed it on hovering ("it ... increase ... the height") and
  chose, from three offered, to cut the sentence to one line with dots. `overlay.row_lines`
  (1 to 3, default 1) brings the wrapping and the stretching back. The bubble still shows the
  whole sentence. They then asked by voice what the choices meant, so the choice may not
  have been an informed one; ask again if they do not like what they see.
- Layouts (2026-11-17): `overlay.layout` is `bar` or `island`; `Ctrl+Alt+K` or
  `claude-speaks overlay layout NAME|next` switches, and `Hub.set_layout` saves it. `island` lays
  the lights out sideways at the top middle of the screen, with a dash of the session's color
  under each light, and drops the panel and bubble from its middle. It keeps its own place
  (`island_x`: where its middle is across the screen, 0 to 1; `island_y`: pixels from the top),
  set by dragging; the author asked for that after finding only the bar could be moved. In the
  lower half of the screen it opens upward. The author
  asked to see four ideas ("living" with lights sized by importance, "island", "edge" as a thin
  line of light at the side of the screen, "tiles" with a window per session), tried them, and
  kept bar and island; the other three were removed again (they are in commit `8558c4a` if
  wanted back). Switching layout forgets the rows and rebuilds them.
- **Where this is heading** (the author, same day): "in the future I want the user that
  downloads this tool to have maximum capability to customize their experience". So new looks
  and behaviours should arrive as settings with sensible defaults, not as replacements, and a
  settings window (see `TODO.md`) is the place they are meant to end up.
- Messages are handled strictly one at a time (`Handle` queues what arrives while one is being
  handled): creating or showing a window lets WPF run the next queued message early, which
  changed the list of sessions while it was being walked ("Collection was modified").
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
  Since 2026-11-17 the bar only takes the mouse while `Ctrl+Alt` is held (`overlay.drag_keys`,
  `""` = whenever the mouse is on it, as before). The author tried a plain click, which
  reached the window underneath, but disliked seeing the move cursor every time the mouse
  crossed the bar: "it would be wiser to ... drag and move when I have the combination of
  alt and control". Without the keys nothing of the bar is in the mouse's way now (no move
  cursor, no brighter edge, no wheel on the bar); it still unfolds under the mouse, which
  only needs the cursor's position. `claude-speaks overlay move` works without the keys.
  The author dragged it with the keys held the same day ("it works. Now perfect"), and the
  new place was saved.
- What brings the details out (`overlay.hover`, 2026-11-17): `always` (default) = the mouse
  resting on the bar, as ever; `keys` = only holding Ctrl+Alt or the list key, and then a
  mouse passing over the bar changes nothing at all (no light growing under it either).
  `claude-speaks overlay hover always|keys`. Asked whether the bar should stop opening under
  the mouse because of games, the author said yes, as the default, and took it back a minute
  later ("Actually never mind ... I like hovering ... opening up its details"), so the
  default did not change and `keys` is untried on screen.
- Name colors (asked for by voice on 2026-11-17: "if ... either the session title or the folder
  name could be different color, would be ... much easier to read"; read as: the name should
  stand apart from the title, and sessions from each other): `Session.color`, one of
  `state.COLORS`, stable per project name and not shared by two live sessions. Rows, history
  lines and requests carry `color`; the overlay writes the name in it and leaves the title white.
  One of the ten was a pink (`#FF8FA3`) next to the microphone's own (`#FF8FA6`), so "Release
  to send", the one line written in the microphone's color because it asks you to do
  something, looked like the name of the session that had it; the author, 2026-11-17: "very
  similar to the brand color, especially of the first terminal, which is not really great".
  First the name color was changed, to an orchid (`#F27FFF`); an hour later the author
  said: "I kind of like the pink that was before for the first terminal. I think what you
  should change is the action label." So the pink is a name color again and the words
  changed instead: a soft white with a white glint, the color of no session
  (`overlay.talk_text_color`, `""` by default; `"#FF8FA6"` brings the pink words back). The
  microphone's wave, light and sign are still pink. Left from the first try: a session
  kept across a restart with a color that is not in the list gets a new one
  (`Sessions.keep`), its old lines too.
- "Release to send" moves (2026-11-17; the author, right after the color talk: "putting an
  animation on the text ... would be great"; which animation was not said, so it is a
  setting with three choices). `overlay.talk_text`: `shimmer` (default; a glint of light
  crosses the words in a second and stays away for half of one), `pulse` (the words breathe
  between soft and full) or `still`. `Ui.MicLive` is the brush for
  it, shared by the bubble and the row and moved once per frame by `Ui.MoveMicInk` while the
  step is `listening`; the glint is a gradient placed in pixels from the start of the line,
  240 px of travel, which fits these words and would need measuring for longer ones. Seen in
  pictures taken while it ran, all three styles, in the white and in a color of one's own.
  The author saw the glint on the white words the same day: "I think it's good. Yeah, I
  like it." Minutes later they asked for "more" of it and for it to be "consistent": "put
  a glint to all action labels", naming "Working out what you said". Read as: every line
  the overlay itself writes about a push-to-talk step (`listening`, `transcribing`,
  `focus`, `failed`), not the user's own quoted words, which stay plain white, and not
  what a session is doing. `TalkInk` gives those steps `Ui.LiveInk` (the same moving ink in
  normal weight; `Ui.MicInk` is the bold one for "Release to send"). "More": the glint is
  wider (150 px), the resting white softer so it shows, it is back 0.3 s after it left,
  and it travels at one speed over the real length of the words (`Ui.GlintFor`, estimated
  from the number of letters). The author on seeing it: "It works, I like it. Yeah, that's
  perfect."
- Titles: `Session.title` is Claude Code's own name for the session (the `name` field of its
  session file, a slug such as `eyes-free-claude-speaks`, turned into words). Claude Code
  writes that name within a second of the first typed prompt, but a session started by voice
  only ever has the placeholder it gets at start (`nameSource: "derived"`, the folder plus two
  characters, `claude-speaks-3f`), which is ignored. Without a name the hub makes its own title
  (`Hub._title_from`): the spoken line of the first reply, cut to 44 characters
  (`state.short_title`), which then stays; before that reply, the first line of a typed
  prompt. The author asked for this on 2026-11-17 ("can't you just wait for the first response
  to come out from Claude and then decide what to name the session?") after seeing
  `<task-notification>` as a title: a voice follow-up reaches Claude wrapped in that markup,
  and the `UserPromptSubmit` event carries the wrapper as the prompt, so prompts that open
  with `<` are never used.
- Titles written by the session itself (2026-11-17): all of the above gave titles such as
  "Your Italian came through, so I ticked the…", and with four sessions in one folder the
  author could not tell them apart ("the title ... is not very fitting ... it doesn't give
  me immediately the idea of what session you are specifically"). Now the reminder asks for
  the title inside the speak tag, `<speak title="Login page redesign">...</speak>`: 2 to 5
  words naming the task, kept from turn to turn and changed only when the work moves on.
  `state.split_display` and `title_from_message` read it, `Hub._title_from(given=...)` sets
  it and marks the session `given`, after which neither Claude Code's name nor a first
  sentence replaces it; it survives a hub restart with the rest. A tag without a title
  still works. `titles: auto` in `config.json` turns the asking off (the hook reads that
  file itself) and makes the hub ignore titles in tags. With the voice off nothing is
  asked, so titles stay as they were. The hooks and the hub must be changed together:
  a hub from before this change does not speak a line whose tag has a title.
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
  back on. The hub hands it to that session's listener, shows "sent → name: text" for 2.5 s and
  plays a short sound (see the next point). Target: the session that spoke last; a quick tap of the talk key picks the next one.
  A busy session gets the follow-up right after its current reply. With no listener yet, the
  text waits in the hub until the session next stops. The cancel key also cuts the line being spoken.
- Taking words back after they went out (2026-11-17, `Hub._take_back`, `unsend_seconds`, 4;
  0 = off). The author wanted an easier way to cancel; offered a spoken ending ("never mind")
  and an unsend key, they pointed out that the spoken one could throw away a message they
  meant ("maybe I don't want to cancel it even though I say never mind") and chose the key:
  "I like the backspace". For that long after "sent", the cancel key acts on the words that
  just went out (`Hub._sent`), before it would cut a line being spoken: words still waiting
  in the hub for a busy session are removed ("Taken back"); words the session already has
  cannot be, so it gets `hub.TAKE_BACK` as a follow-up ("Ignore the last thing I said by
  voice ... do not undo it unless I ask"), which Claude Code hands over after the reply it is
  in. That text goes through the listener's usual wrapper, so listeners started before this
  change deliver it too. The "sent" bubble stays for those 4 s (it was 2.5), the cancel key
  is claimed for them, and holding the talk key again ends them. The key also works in the second or two between letting
  go and "sent" (`Hub._heard`): the author's first try "wasn't immediate", most likely a
  press in that gap, where the key was not even claimed; the words are now dropped when
  they come back from the speech model. The author pressed the real key
  the same day right after speaking to an idle session: it had the words already, got the
  ignore message after its reply and answered that it had changed nothing. **Not tried by
  hand yet: a busy session, where the words are removed** (done once through
  `claude-speaks follow-up` and `talk cancel` on the live hub).
- Sounds instead of "Sent." (2026-11-17; the author, in Italian: the word waits in the queue
  behind a line being spoken, so it comes late and is of little use; they suggested a sound or
  a visual effect and agreed to this): `hub/sounds.py` makes three short sounds in code and
  plays each through its own `paplay`, beside the voice and not through its queue: two notes
  going up = sent, the same note twice = waiting for a busy session, two notes going down =
  not heard, not sent or cancelled. `Hub._signal` picks by `talk_feedback`: `sound` (default),
  `voice` ("Sent." or "Queued." as before; also used when there is no `paplay`), `none`.
  `sound_volume` is 0 to 1 (0.3). Quiet while the voice is off. `claude-speaks sound NAME`
  plays one. Measured on the sink's monitor: sound within a few hundredths of a second, about
  0.2 s long. "Allowed." and "Denied." are still spoken. **The author has not said yet
  whether the sounds are right**; the pitches are in `sounds.TONES`.
- What push-to-talk shows (changed 2026-11-17: the author did not like the text line with
  arrows, "listening → name", and it kept the old name when the focus moved): the hub sends
  `talk` with a step (`listening`, `transcribing`, `ready`, `sent`, `failed`, `focus`), the
  session it is about, and the words; the overlay shows it in the bubble beside that session's
  light (or in its row when the panel is out). While listening the hub also sends `mic`
  loudness values from the recorder, drawn as a wave in the microphone's own color, and the
  light becomes voice bars in that color. `Hub.focus()` re-sends what is on screen for the new
  session, and a pending follow-up moves with it. `banner` is now only used by the overlay
  itself (move mode). The step is shown as a small animated sign with words underneath; the
  name and title stay where they always are (the author did not like "listening" and "sent"
  taking the title's place and suggested moving it or using icons). The sign first sat at the
  right of the session's first line (`Badge`: microphone, moving dots, paper plane, cross).
  Since 2026-11-17 it is inside the session's light (the author, by voice: "it would be better
  if we put the icon inside the bowl instead of the details"; "bowl" was read as the round
  light; they saw it and said "that's good"): `Orb.Sign`, drawn by `Badge.Draw`. While listening the light keeps
  its voice bars; then pink with dots, green with a paper plane, red with a struck-out
  microphone (a plain cross there already means the session failed). The words stay in the
  bubble or row. `overlay.talk_sign` is `light` (default) or `line` (as before). With no
  session to show it on, the sign is still in the bubble. The paper plane was redrawn the
  same day (the author: "it doesn't feel centered"): its three corners are equally far from
  the middle and it is the same on both sides of its line of flight (`Badge.Aim`).
- Hotkeys (rebind or blank them under `overlay.hotkeys`): always claimed are `toggle` Ctrl+Alt+L,
  `talk` Ctrl+Alt+Space, `repeat` Ctrl+Alt+R and `missed` Ctrl+Alt+U (Ctrl+Alt+M is taken by
  another program on the author's machine). Claimed only while they can act: `allow` Ctrl+Alt+Y,
  `deny` Ctrl+Alt+N, `option1`-`option4` Ctrl+Alt+1-4 and `cancel` Ctrl+Alt+Backspace, and
  with two or more sessions `focus_prev` Ctrl+Alt+Up and `focus_next` Ctrl+Alt+Down.
- The arrow keys move the focus (2026-11-17). Before, besides the wheel, a quick tap of the
  talk key went to the next session; the author on being asked to try it: "I don't think
  it's very intuitive ... control-alt-space, it's used for speaking ... better solution might
  be using the arrow keys." Now the tap does nothing (`talk_tap: next` brings it back) and
  Ctrl+Alt+Up/Down send the same `focus_prev`/`focus_next` as the wheel, stop at the ends
  like it, and bring the panel out for a moment. While claimed they are taken from every
  program, and VS Code uses these two in its editor to add a cursor above or below; they
  can be bound to other keys or blanked. In the island layout, where the lights run across,
  it is Ctrl+Alt+Left/Right instead (`focus_left`, `focus_right`; the author: "more intuitive
  if you use the horizontal arrow keys"). Only the pair of the layout in use is claimed, so
  VS Code keeps the other (it moves an editor between groups with Left and Right).
- Focus (asked for by the author on 2026-11-17: "combine ctrl+alt and the mouse wheel to decide
  which session to focus on. also whichever spoke last gets focused"): the focus is the hub's
  `talk_target`, the session a spoken follow-up goes to. It moves to whoever speaks, and
  `Hub.focus(step)` moves it by hand and stops at the first and last session (the author asked
  that the wheel not jump from the bottom back to the top). A line that starts between the talk
  key going down and the words being sent does not take the focus (`Hub._transcribing`): on
  2026-11-17 the author spoke to one session, another one's reply started on release, and the
  words went to that one. The words go to whoever was listening when the key came up
  (`talk_end` hands that session to `_transcribe`): the author let go, moved the focus at
  once, and the words followed the focus to another session ("it went to another session"),
  because the receiver was only looked up when the text came back from the speech model, one
  to two seconds later. A first fix picked the receiver after the tail of the recording
  (`talk_tail`, 0.4 s), and it happened again within minutes ("I immediately switched ...
  it redirected the audio to you"): the switch fell inside that tail. Now it is picked the
  moment the key comes up, before the tail. Moving the focus while the key is still held does move who gets
  them, as the listening sign shows. If that session ends meanwhile, nothing is sent ("That
  session is gone, not sent"). Rows carry `target`; the overlay draws a frame that glides
  to that light and lights its row. `Ctrl+Alt` + wheel (`overlay.focus_wheel`, `""` turns it off)
  sends `focus_prev` / `focus_next` and brings the panel out for 1.6 s. Windows only reports
  the wheel to a background program through a low-level mouse hook, which sits in the path of
  all mouse input, so the overlay installs it only while those keys are down and there are at
  least two sessions, and swallows only the wheel. The wheel alone works while the mouse is on
  the bar. Holding the same keys for 0.2 s also brings the panel out while they are held (the
  author: "ctrl+alt should open the details"), except during push-to-talk, which shows in its
  bubble. AltGr (right Alt, which Windows reports as Ctrl+Alt) is ignored for both.
- Questions: `PermissionRequest` also fires for `AskUserQuestion`, with the questions and options
  in `tool_input`. Single-choice questions with 2 to 4 options become a `Request` with
  `questions`; `choose(n)` records the label and, after the last one, the hook returns allow
  with `updatedInput.answers` (question text → label). Others are only announced.
  The overlay gets the labels as `options` and writes each on a line of its own behind its
  number (the author found them unreadable run together on one line).
  Since 2026-11-17 a question can also be answered in your own words (the author: "let's say I
  want to clarify, I want to put my notes. Can I send an audio instead of picking a choice?").
  Before, words spoken to a session waiting on a question sat in the queue until the question
  was answered some other way. Now `Hub._send` gives them to `Hub._answer` as the answer to
  the question on that session; Claude Code takes any text in `answers`, as for a typed
  "Other" (checked with a real session: "Which drink? → Neither, sparkling water with lemon ·
  Allowed by PermissionRequest hook"). Only for questions that have a `Request`, so not for
  multiple choice or more than four options, and not for permission prompts.
  A question answered in the terminal used to stay on the overlay until the turn ended (the
  author, same day: "I chose the answer via Visual Studio Code. I still see the prompt"): the
  call that ran comes back in `PostToolUse` with the answers added to its input, so it never
  equalled the open request. `_same_call` compares only the questions (checked for real: the
  request is closed in the second the dialog is answered).
- History and catching up: the hub keeps the last 100 lines sessions said. `last_seen` moves on
  every prompt and hotkey; `catch_up()` replays lines newer than it. `repeat()` says again the
  last line of the session in focus (the author, 2026-11-17, after trying the key: "it would be
  better to have it replay the selected session, also i noticed the detail box doesnt come
  out"); `repeat: last` in the settings brings back the last line anyone said. A replayed line
  is tied to its session (`Hub._replay`), so its bubble, voice bars and wave show as they did
  the first time; before, it belonged to no session and nothing showed. Catch-up still says
  each session's name first (`Utterance.label`). The overlay gets the newest lines with each
  `state`, up to four of each session, and shows them while the cursor rests on the list
  (found by polling the cursor position, since the window is click-through). It shows the
  lines of the session under the mouse (`historyOf`; before a row was touched, the session
  in focus): the author hovered another session, saw it light up and expected its history
  (2026-11-17). `overlay.history: all` shows every session's lines mixed, as before.
- Follow-ups waiting for a busy session are also written to `followups.json` in the run folder
  (owner-only, dropped when over an hour old), because a hub restart lost one for real: the
  author asked a question by voice during a reply, and a restart made while working on the
  overlay wiped it. The overlay shows such a message as waiting (`talk` step `queued`).
- Who is who across a hub restart (2026-11-17): names ("claude-speaks 2"), colors and voices
  are handed out in the order sessions turn up, and after a restart they turn up in another
  order, so sessions of one project swapped them. The author noticed with five sessions open
  ("the colors, like their status, might have influenced each other, especially when
  claude-speaks reset"). `Hub._keep_sessions` writes `sessions.json` in the run folder
  (owner-only; ignored when over 6 hours old) on every change: per session its id, name,
  voice, color, title, state, note and place (`Session.order`), plus the focus and the last
  40 lines said (`KEPT_LINES`), so repeat and the history under the rows still have
  something after a restart.
  `Hub._restore_sessions` reads it at start: a session Claude Code still lists is back at
  once, working if it is busy there; one that had a session file and has none now is dropped;
  the rest wait in `Sessions.kept` and get theirs back when they next report (for 15 minutes,
  `state.KEPT_FOR`), and until then no new session is given their name, color or voice.
- Which terminal is which (2026-11-17; the author, by voice, with four sessions in four VS
  Code terminals: "is there a possibility to highlight the terminal which is associated
  with" the session selected in the overlay): `hub/terminal.py`. The hub finds the terminal
  each session runs in (`tty_of`: what `/proc/<pid>/fd/0` of the pid in its session file points
  to, `/dev/pts/N`; `Session.tty`) and writes requests to it that terminals understand: OSC 11
  "use this background color", OSC 111 "use your own again", OSC 2 "this is your title".
  `Hub.publish` hands `Terminals.show` one `Mark` (color, in focus, title) per terminal and it
  writes only what changed. Default `tint: focus`: with two or more sessions, the terminal of
  the one in focus has `strength` (0.08; it was 0.14 until the author said "less tint maybe") of its overlay color mixed into `background`
  (`#181818`, VS Code's dark theme; the real background cannot be asked for from outside, the
  answer would land in Claude Code's input). `all` tints every terminal (the others at half
  strength), `off` none. `Hub.focus` (wheel, tap) also calls `Terminals.pulse`: 14 steps over
  0.7 s from `pulse_strength` down to the resting tint (0.15; the author, having seen
  it at 0.42, said "maybe the flash might be too much", and it came down with the tint;
  `terminal pulse off` removes it). `claude-speaks terminal find
  [PROJECT]` does the same on request. Stopping the hub gives every terminal its own
  background back, and a terminal seen for the first time is reset, which clears what a hub
  that died left. `title` (off by default) writes "name · title"; control characters are
  taken out, since a title can hold words from a prompt. `CLAUDE_SPEAKS_TERMINAL=off` writes
  to no terminal (the tests that start a real hub use it; the others record the writes).
  Checked: VS Code's terminal (xterm.js, in its `node_modules.asar`) handles OSC 11 and 111;
  the live hub found all four terminals. The author saw the tint and the flash at these strengths
  in their four terminals and said "looks good". Tab names are not solved: VS Code
  shows a written title only with `"terminal.integrated.tabs.title": "${sequence}"`, and Claude
  Code writes its own title unless started with `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1`; neither
  is set on the author's machine, and nobody has checked which title wins.
- The other way round, terminal → session (2026-11-17; the author, by voice: "if I focus on
  a terminal it would be great to automatically select that" session): `vscode/` is a VS
  Code extension of two files (`extension.js`, `package.json`; no build step, no
  dependencies). On `onDidChangeActiveTerminal` it posts `{"front": <the terminal's shell
  pid>, "why": "switch"}` to the hub's socket at `/terminal`; when its window comes to the
  front, the same with `"why": "window"`. `Hub.terminal_in_front` finds the session whose
  `tty` is that process's terminal and gives it the focus (`_focus_on`, shared with the
  wheel), without a flash. A `window` report only counts when it names another terminal than
  the last report (several windows): coming back to the window must not take the focus from
  a session that spoke meanwhile. `terminal.follow: false` ignores the reports.
  `vscode/pack.py` zips the folder into a `.vsix` and `claude-speaks vscode install` hands
  it to `code --install-extension` (the `code` of a VS Code terminal installs on the WSL
  side, where the hub's socket is; `extensionKind` is `workspace` for that reason). Measured:
  VS Code 1.146 started it at once, without a reload ("_doActivateExtension ...
  activationEvent: 'onStartupFinished'" in `~/.vscode-server/data/logs/*/exthost*/`).
  Installed on the author's machine; **nobody has switched terminals with it yet**. Limit:
  VS Code reports a change of the active terminal, not keyboard focus, so clicking back
  into the terminal you were last in reports nothing.
- `hub/stale.py`: the hub takes a fingerprint of each of its own files as it starts (of
  what they hold, not their time of change, so a file that was only touched does not count),
  and the overlay does the same for its source when a window is started. `/state` carries
  `outdated` (`hub`: the files that differ now; `overlay`: true or false), and
  `claude-speaks status` turns it into a note with the command that applies the change. A
  file another session is still working on counts too, so the note is a reason to look, not
  an order to restart.
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
- The held talk key is kept from other programs (2026-11-17; the author held `Ctrl+Alt+Space`
  while watching YouTube and the video paused). A hotkey only keeps a key to itself while its
  Ctrl and Alt are down too; over a long hold one of them is let go, and the key then repeats
  into whatever has the keyboard. From the hotkey until the key is up, `KeepKey` puts in a
  keyboard hook that takes every further press of that one key (`OnKey`). The release was
  passed on at first, and the author found the same day that the video then stopped "on
  release": the browser acts on a release alone. Since then the hook takes the whole hold,
  press and release too, so the program in front never learns the key was touched. Measured
  with a spare key: when a release is kept from Windows it goes on thinking the key is down,
  and when the press was kept too it never thinks so; so a release can only be kept if its
  press was, and the hook has to be in before the talk key goes down. `WatchTalkKeys` puts it
  in as soon as the hotkey's other keys (Ctrl, Alt) are down, and keeps it for the hold; the
  hook then starts the hold itself (`taken`) and the hotkey never fires. A talk key that goes
  down within about 30 ms of Ctrl and Alt still arrives as a plain hotkey, and that hold goes
  the old way (repeats kept, release passed on, so a video can still pause then).
  `overlay.keep_talk_key`: `held` (default), `always` (hook in all the time, for a talk key
  without Ctrl or Alt) or `off`. If a kept release is ever lost, the hold ends a second after
  the key stops repeating. That safeguard is dropped as soon as another key goes down during
  the hold: a keyboard repeats only the key pressed last, so an arrow pressed to move the
  focus while talking ended the recording a second later (the author, 2026-11-17: with the
  wheel "it continues ... but whenever I use the arrows, it stops"). `tests/keys_check.py` checks both ways from WSL with a spare key
  (F20, no Ctrl or Alt). Not checked from WSL: the hook going in on the real Ctrl and Alt.
  The author's wider idea, that holding Ctrl+Alt switches off every other key, was not built:
  it would also take the Ctrl+Alt shortcuts of other programs and, on keyboards such as the
  Italian one, characters typed with those keys. It is in `TODO.md` as a possible setting.
- Ctrl and Alt are hidden from other programs while talking (2026-11-17, `MaskKeys` in
  `overlay/Overlay.cs`, `overlay.talk_frees_keys`, on by default). The author could not pause
  a video by clicking it while holding the talk keys; their own test showed the click fails
  with Ctrl+Alt held even without Space, so the player ignores a Ctrl+Alt+click. Letting go
  of Ctrl and Alt and keeping Space works, but they found that "not very intuitive". So when
  a hold begins the overlay sends key-ups for the talk hotkey's Ctrl, Alt and Shift (marked
  as its own, after a tap of an unused key so that Alt coming up opens no menu), and keeps
  counting them as down itself (`Pressed`) until their real release reaches the hook, or
  for 3 s after the hold with no sign of them. While they are hidden, Windows no longer
  matches the other hotkeys, so the hook does (`claims`): cancel, repeat, the list and so on
  still work without letting go first, as does a second press of the talk key and the
  focus wheel. Windows is only ever told "up", never "down", so nothing can be left stuck
  for other programs. Not hidden: AltGr and the Windows key. `tests/keys_check.py` checks
  it with left Shift standing in for Ctrl and Alt. The author tried the real keys the same day:
  the click pauses the video, and Backspace with the keys still down cancels.
- `hub/demo.py`: three made-up sessions that go through every state (`claude-speaks demo`).
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/claude-speaks` (linked by `install.sh` into `~/.local/bin` as `claude-speaks` and `cs`;
  on the author's machine since 2026-11-16): `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `allow`/`deny`, `answer N`, `missed`, `repeat`, `sound NAME`, `languages [CODES]`, `voices`, `voice …`, `target [PROJECT]`,
  `follow-up [-s PROJECT] TEXT`, `talk start|stop|cancel`,
  `overlay dots|list|toggle|restart|move|monitor N|corner NAME`, `terminal [tint focus|all|off | find [PROJECT] | strength N | background COLOR | pulse on|off|N | title on|off | follow on|off]`, `vscode install|uninstall`,
  `demo`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 148 tests with a silent engine and fake microphone, including the real hook
  scripts over a socket and a hub process that is killed and restarted.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/claude-speaks/config.json` with `voices` (project name → voice),
  `voice_pool`, `label` (`auto`/`always`/`never`), `titles` (`ask`/`auto`), `repeat` (`focus`/`last`), `max_age`, `idle_exit`, `default_voice`, `speed`,
  and `overlay` (`enabled`, `mode`, `monitor`, `corner`, `offset_x`, `offset_y`, `opacity`,
  `list_opacity`, `glass` (`blur`/`acrylic`/`none`), `flash_seconds`, `talk_sign` (`light`/`line`), `hotkeys`), `permission_grace`, `whisper_model`, `mic_source`, `followup_delay`, `unsend_seconds`,
  `talk_tail`, `talk_feedback`, `sound_volume`, and `terminal` (`tint`, `strength`, `background`,
  `pulse`, `pulse_strength`, `title`, `follow`). `CLAUDE_SPEAKS_OVERLAY=off` disables the overlay.
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
  A new folder first shows a trust dialog (Down, Enter). To wait between steps use
  `python3 -c "import time; time.sleep(2)"`: `read -t 1 < /dev/null` returns at once, and
  keys sent without a real wait land in the wrong dialog.
- `asyncRewake` facts (measured 2026-11-16): a hook with `asyncRewake: true` that exits 2 wakes
  an idle session within a second; its stderr reaches Claude and the terminal shows "Stop hook
  feedback". Delivered while the session is busy, it is handled right after the current reply.
  It works from both Stop and SessionStart. Claude Code kills these hooks when the session exits.
  Its `timeout` is enforced, so the listener asks for 86400 s.
  Measured 2026-11-17: it also works from UserPromptSubmit. The prompt is not held up, the hook
  outlives the turn, an Esc does not kill it, and it wakes the interrupted session. Each
  prompt starts another one and the older ones live on, so something has to retire them
  (the hub releases a session's older listener when a new one reports).
- A session has a listener all the time (2026-11-17). Before, only from a Stop or a start:
  the author interrupted this session with Ctrl+C, spoke to it, and the words "didn't go
  through", because an interrupt ends a turn without a Stop and nothing was listening. Now
  `listen.sh` also runs on every prompt. Since a listener is then there in the middle of a
  reply too, the hub decides by the session's state: to a busy session (`BUSY`: working or
  needs you) words wait, and `reconcile` hands them over within a second of it stopping,
  whether the reply ended or was interrupted. Checked with a real session: spoken to while
  busy, interrupted two seconds later, woken two seconds after that.
- Editing a hook script while it runs (2026-11-17): bash reads a script from its file as it
  goes, by position. `listen.sh` waits for hours, and when another session edited it in place
  the listeners already running read on in the middle of the new text: "line 19: r: command
  not found", a syntax error, exit 2. That woke the session with the error, and the words the
  author had just spoken to it were lost (they were still in `hub.log`). `listen.sh` and
  `permission.sh` are now one function called on the last line (read whole before it runs),
  and a test edits the script under a waiting listener. Listeners started before a fix like
  this keep the fault: end them with `kill` (their trap exits quietly), after which words to
  that session wait in the hub until its next prompt or stop.
- Languages (2026-11-17): the author also speaks Italian to it; the English-only model dropped
  those recordings or invented English ("But I'll see you in Italy in a few days."). Their
  `config.json` now has `whisper_model: small` and `whisper_language: "en,it"`. With several
  languages named, `Transcriber` asks the model which one a recording is and picks the likeliest
  of the named ones (a short clip was detected as English with only 0.26 certainty). Measured
  with Kokoro's Italian voices as the speaker: `small` got Italian right, about 1.2 s per
  sentence with detection against 0.7 s for `small.en`; loudness down to a peak of 0.03 made no
  difference. The repo default stays `small.en`.
- Choosing languages (2026-11-17): asked whether new installs should start with the
  multilingual model, the author said: "What if we let the people choose the language they
  speak? So ... we don't include all languages." So `install.sh` asks once, at a terminal,
  which languages you will speak (`--languages en,it` answers in advance; a choice already in
  `config.json` is kept), and `claude-speaks languages [CODES]` shows or changes it later.
  Both go through `stt.setup` (run as `hub/stt.py languages CONFIG CODES`): English alone gives
  the English-only model of the size already chosen, anything else the multilingual one with
  `whisper_language` set to those codes, `auto` any language. Codes are checked against
  `stt.LANGUAGES`, a copy of faster-whisper's list (a test compares the two), so the check
  works before the Python environment exists. A running hub takes the choice up at once
  (`POST /languages`, `Hub.reload_languages`); the model loads on the next push-to-talk.
  Tests are in `tests/test_languages.py`. The question itself was tried with a pretend
  terminal in a throwaway home folder, not by a person.
- What the choice of languages costs (measured 2026-11-17 with `tests/stt_speed.py`, asked
  for by the author as numbers for when the tool is published: "it'll be great to have some
  metrics"). Kokoro spoke English and Italian sentences of about 1, 4 and 12 s; median of 5
  runs on the author's CPU (Core Ultra 7 270K, 24 threads, int8, no graphics card), model
  already loaded. One language: 0.6 / 0.7 / 0.9 s for English with `small.en`, 0.6 / 0.8 /
  1.0 s for Italian with `small`. Two languages (`en,it`): 1.2 to 1.4 / 1.4 to 1.5 / 1.5 to
  1.7 s. Five languages and `auto`: the same as two. So working out the language costs about
  0.6 s whatever the number of languages, and nothing else differs: `small` told "English"
  was as quick as `small.en` on the same clips (0.61 / 0.70 / 0.88 against 0.64 / 0.73 /
  0.91 s). Before measuring, the author was told the English-only model is the faster one;
  that was wrong. Every clip was taken as the right language and written correctly under
  every choice, so these clean, synthetic voices say nothing about how often a real short
  recording is mistaken for another language. Loading a model takes 0.5 to 0.8 s once it is
  on disk.
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
