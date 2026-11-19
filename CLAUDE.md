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
  folder). Its download and environment steps ran on 2026-11-17 in an empty home folder
  with nothing cached (22 s, 906 MB; the hub from that install spoke and its speech model
  wrote the sentence back), not yet on a machine without the apt tools and `uv`. It also
  fetches the Whisper model since then; before, the first push-to-talk waited for it.
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
| PreToolUse, PostToolUse | `hooks/stop.sh` | Ends the turn when the hub was asked to stop this session (a file named after it in `$CS_RUN/stop`). About 2.5 ms when nobody asked |
| Stop, SessionStart, UserPromptSubmit (`asyncRewake`) | `hooks/listen.sh` | Background listener: waits on the hub for a spoken follow-up for this session, prints it for Claude and exits 2, which wakes the session |
| SessionStart, SessionEnd, UserPromptSubmit, PreToolUse, PostToolUse(Failure), TaskCreated, TaskCompleted, StopFailure | `hooks/report.sh` (async) | Forwards the payload so the hub knows what each session is doing. `--start` also starts the hub |

- The hub's code is in five files since 2026-11-17 (it was one of 2,100 lines; sections
  were moved whole): `hub/hub.py` has the `Hub` itself (hook events, who is who across a
  restart, catching up, voices, the overlay feed) and `main`; `hub/base.py` the settings
  (`Config`), the small records (`Request`, `Pending`, `Sent`, `Stopping`, `Editor`,
  `Aside`, `Listener`) and helpers that need no hub; `hub/permissions.py` and
  `hub/talk.py` are parts of the `Hub` class (`class Hub(Permissions, Talk)`: requests and
  questions; push-to-talk, words on their way, side questions, taking back, stopping);
  `hub/server.py` is the HTTP layer. Where these notes say `hub/hub.py` for one of those
  things, look there. `hub.py` still offers every name of `base`, so `from hub import
  Config` works; the three waits the tests shorten (`MIN_SHOWN`, `TAP`, `CONFIRM_WINDOW`)
  are read as `base.NAME` wherever they are used and set on `base` in the tests.
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
- The mode is remembered (2026-11-17): the overlay reports `mode` when the list key or the
  command changes it, and `Hub.on_overlay` saves it to `config.json` (`overlay.mode`), so
  details that were kept out are out again after a hub restart. Before, every restart went
  back to `dots`, and since the history under the rows only shows in `list`, the author
  missed it after one ("I don't see the history anymore").
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
  new place was saved. Later that day: "sometimes the cursor is not aligned" with the bar
  while dragging. `BeginDrag` took the grab point from `GetCursorPos` when the press was
  handled, which is after the mouse has moved on; it now takes it from the press
  (`e.GetPosition`). The author dragged it afterwards: "Perfect, it seems to be working."
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
  Colors too near each other (same evening; the author, with four sessions of this project
  open: "The palette of colors is not very distinctive. There's not much contrast between
  claude-speaks 2 and claude-speaks 4. One is orange, the other one is yellow"). The ten
  colors had near twins, and a session simply got the next free one in the list. Measured
  as distance in CIELAB (`state.color_distance`), that orange (`#FFB86B`) and the yellow
  were 25 apart, pink and teal are 77. Now: eight colors, the nearest two 32 apart (yellow
  and lime; no eighth soft color is further than about 36 from all the others); a session
  that joins others gets the free color furthest from all of theirs (`_color_for`), and
  alone a project still has its own color every time; at a hub restart a session whose
  color is nearer than `state.TOO_CLOSE` (40) to that of one before it in the bar gets
  the furthest free one (`Sessions.keep`), which is how sessions already open are set
  right. `colors` in `config.json` is a list of your own (`#RRGGBB`, at least two). For
  the author's four it changed one: claude-speaks 2 from orange to violet, nearest two
  then 59 apart. (Seen with two sessions open on 2026-11-18, pink and violet: "they look
  good. I like the colors". The palette with four or more open they have not judged.)
  Minutes later: "Can't you just use a prefix
  palette of color? Like 10, 20, 30. I don't know the maximum" number of sessions. So the
  list is twenty now: the eight soft ones first (`state.SOFT`), handed out while one of them
  is still at least 40 from every color in use (about five sessions), then twelve stronger
  ones that were worked out, each the furthest from all before it among colors readable on
  dark glass and clear of the status lights and of white. The nearest two of the twenty are
  29 apart; thirty could only be had 25 apart, which is the orange and yellow again. A
  twenty-first session shares the color the fewest have. Claude Code itself sets no limit
  to the number of sessions.
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
- The cancel key stops a turn (2026-11-17, `Hub._stop_turn`, `hooks/stop.sh`, `cancel_stops`).
  The author, having learned that taking words back from a session that already has them
  only tells it to ignore them: "I thought you were already doing that by terminating
  process", and wanted `Ctrl+Alt+Backspace` to be the stop key in general ("more universal");
  a double press was "too much work" and a key of its own was turned down for Backspace.
  One press does the first that applies: throw away a recording; take back what was just
  sent (words still in the hub are removed, a session that has them is stopped); cut the
  line being spoken; end the turn of the session in focus while it is `working`
  (`Hub._stoppable`; the key is claimed for as long as that holds). Stopping: the hub
  leaves an empty file `$CS_RUN/stop/<session id>` and `stop.sh`, on the session's next
  `PreToolUse` or `PostToolUse`, removes it and prints `continue: false` (for `PreToolUse`
  with a refusal of that call), which ends the turn there; Claude sees the reason and does
  not go on by itself. No `Stop` event follows, so `reconcile` sees the file gone and sets
  the session idle with the note "stopped". While a stop is asked for the session's own
  lines are not spoken, its row says "Stopping at its next step" and its light shows a
  stop sign (`talk` step `stopped`). The asking is called off when the turn ends by
  itself, when a prompt is typed, when the session is handed new words, and when a hub
  starts. `cancel_stops`: `always` (default), `sent` (only when taking words back) or
  `never` (told to ignore, as below). Tried with the real hook on a throwaway session;
  The author pressed it the same night on a session working in small steps ("its turn was
  ended 1.8 s after the key"). A turn that only writes text has no step to stop at.
- Stopping at once through the editor (2026-11-17, `stop_at_once`, `Hub._press`, `/editor`,
  `vscode/extension.js` 0.2.0). Only the editor can type into its terminals. The extension
  keeps one request open with the hub (`POST /editor` with the process ids of its terminals,
  held for `EDITOR_WAIT` 25 s and asked again; anew when a terminal opens or closes); the
  hub keeps it as an `Editor` with terminal → process id, and `_stop_turn` hands the one
  that holds the session's terminal `{"pid", "key": "escape"}`, which the extension types
  with `Terminal.sendText(text, false)`. It knows no other key, so the hub cannot have
  anything else typed. Measured with tmux on a throwaway session: one Escape or one Ctrl+C
  interrupts a working session; a second Ctrl+C at the prompt closes the session, a second
  Escape there opens its rewind list. So Escape is asked for once (`Stopping.pressed`) and
  only of a session in a turn; if it had not begun yet or no editor was waiting, `reconcile`
  asks within a second. The file for the hook is left in place either way and cleared when
  the session is seen to have stopped. The foreground `sleep` of a test prompt is refused
  by Claude Code itself now; a small script that counts stands in for it. Tested with the
  real extension code, a stand-in editor and a real hub. **Not tried in the author's VS
  Code: it runs 0.1.0 until its extension host is restarted.**
- Side questions (2026-11-17; the author, by voice: "I was wondering if you could do a slash,
  by the way, BTW ... it lets me skip the queue and ask a by the way question", meaning Claude
  Code's `/btw`). Spoken words for a session in the middle of a turn that open with "by the
  way" or "btw" (`aside_words`) do not wait: `Hub._ask_aside` starts a throwaway copy of
  that session (`Hub.aside_run`: `claude -p --resume ID --fork-session
  --no-session-persistence`, hooks off, on the session's own model and effort, see the end
  of this point; in the session's folder, without the variables that tie a
  process to the session whose hook started the hub), and its answer is said in the session's
  voice (`_say_aside`: kind `notice`, so it and the session's own waiting line do not replace
  each other; in the history as kind `aside`, so repeat and catch-up have it). The session
  never sees the question or the answer. Offered a second talk key or opening words, the
  author chose the words ("starting with the words by the way, that's fine"). While the copy
  thinks, the overlay shows the `talk` step `aside`: moving dots, the words, "Answering on
  the side"; the cancel key drops the question then, before it would stop the session's
  turn. No answer (error, or none in `aside_timeout`, 60 s): the words go to the session
  like any others (`_hand_over`, which is what `_send` did before). `aside`: `busy`
  (default; an idle session gets the words as usual and can act on them), `always`, `off`.
  `aside_model`: `session` (default) or a model's name such as `haiku`. Why not `/btw` itself: it
  has to be typed into the session, and the request behind it (`side_question`) is only
  open to programs that started the session or to Remote Control. Measured on a session in
  the middle of a turn, Claude Code 2.1.327: 4.7 to 6.4 s to an answer. What it costs (the
  author asked whether it uses more than `/btw`; measured with `--output-format json` on a
  conversation of 165 to 210 thousand tokens): the copy reads the whole conversation as new
  input, since a saved conversation is only reused by the same model; 16 cents a question
  at list prices while the copy also saved it (a second question seconds later did not
  reuse that), 10.5 cents with `DISABLE_PROMPT_CACHING=1`, which the hub now sets. `/btw`
  reads the same tokens from what the session has saved, about 4 cents on Fable 5.2 by the
  price list (worked out, not measured). Haiku 5.5 costs five times more per token above
  100 thousand tokens of prompt, which is where the 10 cents come from. The author then said
  the cost on Fable does not matter to them ("I'm not paying per API") and that ideally they
  want the real thing: "I want to call the function by the way ... it's like a parallel
  processing question". Two things were measured for that. (1) The real `/btw`, typed into
  a throwaway session in tmux while it worked, answers at once, and its answer reaches a
  `SubagentStop` hook as `last_assistant_message` with an empty `agent_type`, so it could be
  spoken; the suggestion for the next prompt arrives the very same way. But its answer box
  stays open until Esc or Enter and takes whatever is typed next: a second `/btw` typed
  into it was lost, and its letters are the box's own commands (c copy, f fork, x clear).
  The hub cannot see what a terminal is showing, Esc with no box open interrupts the turn
  and Enter with a permission prompt open approves it, so typing it through the VS Code
  extension was not built. (2) A copy on the session's own model and effort, with no tool
  taken away, begins its request exactly as the session does and so reuses what the session
  has saved, which is what `/btw` does inside: on this session 272 thousand tokens were read
  from what was saved and 32 thousand were new, answered by Fable in 4.5 s; on a small
  Haiku session 1.5 s. `--tools ""`, `--disallowedTools` and plan mode each lose the reuse;
  `--permission-mode default` with rules that make every tool ask (`hub.ASIDE_ASK`) keeps
  it, and a copy told to run a command was refused. That is the default now
  (`aside_model: session`); the model and effort are read from the end of Claude Code's
  record of the session (`hub.session_model`, `projects_dir`). A named model works as
  before: no tools, nothing saved. With hooks off the
  copy neither spoke nor showed up in the hub. Tried by the author with their own voice on
  2026-11-18, through the live hub, while this session worked: "By the way, what time is
  it right now?" was answered aloud in 3.2 s ("I can't read the clock from a side
  question, but the last time I saw in the log was about ten to two"). Their first try,
  "Oh, by the way ...", waited for the session: the opening had to be the very first
  word. Since then small words before it are passed over (`base.ASIDE_LEAD`) and the copy
  is told the day and time (`base.aside_prompt`); neither tried by voice yet.
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
- Words that wait are marked on the light (2026-11-17). Words for a busy session showed
  "waiting" for 3.5 s and then nothing, and the author took that as not heard. `Hub._waiting`
  holds the sessions whose words could not be handed over (`_deliver` found no listener to
  wake); their rows carry `waiting` (how many) and "1 message waiting" in `meta`. The
  overlay draws a small red dot at the upper right of the light
  (`Orb.Mark`) until `collect` hands the words over, which shows `sent` on that light for
  2.5 s unless push-to-talk is showing something of its own. The `queued` step is a clock
  in the light (`Badge` kind `wait`), no longer the plane. The author tried it the same
  evening: "the clock was good", but the dot, then in the microphone's pink, should be red
  ("more intuitive"), so it is the red of a notification now (`overlay.waiting_color`,
  `"#FF6E8A"` for the pink). The red dot they then found "not very intuitive. It doesn't
  feel like there's one in queue", and chose, from three ideas, the clock kept small on
  the light: `overlay.waiting_mark` is `clock` (default; its hand goes round, and with two
  or more messages it shows the number) or `dot`. The clock on the light "feel weird" too;
  their own design, built next: `number` (now the default), the count in white on a red
  disc with no border, which covers the whole light for `overlay.waiting_hold` seconds (0.9)
  as the words go into the queue, then shrinks and glides to the upper right
  (`Orb.WaitingSince`, set whenever the count grows). With `number` and `dot` the `queued`
  step puts no sign in the light. Seen by them on 2026-11-18: asked to speak twice to a
  session kept busy for it, they did, and said in a third message while two waited:
  "Looks good." Above nine
  messages the disc is a shocked face (`Orb.Shocked`, drawn, since WPF here has no color
  emoji; `overlay.waiting_many`: `face` or `number` for "9+"), the author's idea on
  seeing "9+": "very dense in that circle". That face was first a shocked one in white on
  red, which they found "kind of scary ... not funny", then yellow with its tongue out, which
  looked "mentally ill"; they asked for one that is fed up with so many requests, so it is
  yellow; the fourth is drawn after a picture they gave as the look to go for: brows raised
  in the middle, oval eyes with a line under each, a wavy mouth turned down (`Orb.Dismayed`;
  in the corner it needs a radius of about 9 to be read, and the number's disc was made the
  same size on the author's word, `overlay.waiting_size`). The author on the face and the
  number in its corner: "That's really perfect." Digits are centered by the box of their own
  strokes (`Orb.Number`): placed by their line of text they sat up to a pixel low. `overlay.waiting_cover` says which messages show their number across
  the whole light: `never` (default since the author said "just put it top right"; the
  number comes up in its corner with a small jump), `first` or `each`. To show the mark on the live overlay: `claude-speaks follow-up -s NAME TEXT`
  several times for a session that is busy.
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
- Hotkeys (rebind or blank them under `overlay.hotkeys`; `jump` has no key by default, see further down): always claimed are `toggle` Ctrl+Alt+L,
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
- A short press left the listening sign up (2026-11-18; the author, typed: "it got stuck in
  recording wtf"). Since the tap does nothing, nothing followed a press shorter than
  `base.TAP` (0.35 s) that would take "Release to send" off the light: the hub had stopped
  recording, the sign stayed until the next hold. `talk_end` now takes it away
  (`_talk(None)`) and `hub.log` says "talk: a press of 0.17s, too short to be a recording";
  a tap left no line before, which is why the log could not say what had happened. Tried
  through the live hub with `talk start` and `talk stop`. **Not confirmed that this is what
  the author saw**: a short press is the only way found to that picture, and by the time it
  was looked at the hub was not recording and no recorder was running. Read on the way,
  not mended: a hold whose press the keyboard hook took (`taken`) ends only by the release
  reaching that hook, or by the repeats stopping, and that second way is off before the
  first repeat and after another key was pressed; and the cancel key ends the hub's
  recording without telling the overlay's `holding`. If Windows ever drops the hook in the
  middle of a hold, the overlay would go on thinking the key is down and ignore the talk
  key until it is restarted.
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
- The talk key reaches back (2026-11-17, `focus_reach_back`, 1 s): a session that starts to
  speak takes the focus, also in the split second before the talk key goes down, and the
  words then went to it instead of the session the author meant (three times that day; the
  last report: "If I start speaking when another Claude session starts speaking as well, the
  icon I see, it's not the recording icon"). `_speech_changed` notes whom a speaker took the
  focus from and when (`_focus_lost`); `talk_start` goes back to that session if it was
  under a second ago. A focus chosen by hand clears the note. What the overlay draws in
  that moment was checked in pictures and is right (`talk-while-another-speaks`): the
  listening sign stays on the session spoken to, the other light shows its voice.
- A command allowed in the terminal (2026-11-17, `claude_sessions.tool_shells`, the loop over
  `requests` in `Hub.reconcile`): no hook reports a yes typed in the terminal, so a prompt
  that had waited more than six seconds left its session on "needs you" until the command
  was done. The author, told it was a small flaw and hard to mend: "if it's fixable ...
  that would be for the best, right?" A `Request` for the Bash tool notes which commands of
  the session were running when it asked (`shells`); once a second the hub looks for a new
  one whose command line holds the start of the command asked about (`_runs`; up to its
  first quote, so another command of the same session starting meanwhile does not count),
  and closes the request as "allowed in the terminal: its command is running". Tried on a
  throwaway session: the state went from "needs you" to "working" within half a second of
  Enter in the terminal. Linux only (it reads `/proc`), Bash only: an edit or a web
  fetch allowed in the terminal still waits for its end, which comes quickly.
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
- A typed prompt takes the focus (2026-11-18, `focus_on_prompt`, on by default; built
  while the author was away, on "list me ... the next things to do ... and you'll do it",
  **not agreed with them and not seen in use**). In `_apply`, a `UserPromptSubmit` whose
  prompt is not markup gives that session the focus (`_focus_on`), except while the talk
  key is held or words are on their way. It fills the gap of the editor not reporting a
  click back into the terminal you were in last. A session started by a script with the
  hooks on takes the focus too. Asked to try it that evening, the author opened a second
  session and typed to it; the focus had already gone there when they went to its
  terminal, so the try showed nothing of this rule, and the asking confused them ("so what
  do I do?"). It can only be seen when a session has spoken and taken the focus and you
  then type into the terminal you were in all along: left to turn up in use.
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
- The jump key has no key any more (2026-11-18, evening). Asked to try it, the author did
  not see its purpose and, told it was the session's own idea, said: "I think we can just
  delete this one ... I don't think I'll use it", because their terminals are "side by
  side", and "the highlights already give me ... the point to look at". `jump` is `""` in
  the default hotkeys, so no key is claimed; what is behind it (`terminal show`, the
  extension's `show`) is left in, since their own idea needs it, which they wanted kept on
  the list without meaning to do it soon: with terminals as tabs, one shown at a time,
  moving the focus in the overlay could bring that session's terminal up by itself
  (`TODO.md`). What follows is how it was built.
- Session → terminal, the jump key (2026-11-18, `Talk.show_terminal`, `_showable`, hotkey
  `jump` = `Ctrl+Alt+T`, `claude-speaks terminal show [PROJECT]`, `vscode/extension.js`
  0.3.0; built while the author was away, **key and letter not agreed with them, not
  pressed by anyone**). The extension's held request now says what it can do (`"can":
  ["escape", "show"]`), and the hub's answer can carry `show`, a list of process ids; the
  extension calls `terminal.show(false)` on those, which brings the terminal up with the
  keyboard in it. An `Editor` without `shows` (0.2.0) is never asked, and the key is only
  live (`keys` → `jump`) while an editor that shows holds the terminal of the session in
  focus, or did up to `EDITOR_GAP` (3 s) ago, since its requests end every 25 s and the next
  comes 0.2 s later; a show asked for in that gap waits in `_show_wanted` for the next
  request. Inside VS Code's window only: nothing brings the window itself in front of
  other programs. `Ctrl+Alt+Enter` was passed over as the key because VS Code uses it
  (replace all). The overlay treats `jump` like the keys that answer: claimed while live.
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
  Since 2026-11-17 it asks each window of its own overlay for its picture (`PrintWindow`
  with flag 2, through `tests/overlay_capture.ps1`, one PowerShell process for the run; the
  window is found by the exact rectangle of the `bounds` reply), so nothing that lies over
  or behind it on the screen is in the picture, the live overlay included; each run proves
  that with a colored window laid over it and exits 1 if it cannot. Only the glass views are
  still copied from the screen, over a test card, at a place it finds free of other
  programs' always-on-top windows.
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
  for 3 s after the hold with no sign of them (longer while the "sent" or "waiting" sign
  of the words is up, so that Backspace with the keys never let go still takes them back;
  `WatchTalkKeys`, 2026-11-17, not pressed by anyone yet). While they are hidden, Windows no longer
  matches the other hotkeys, so the hook does (`claims`): cancel, repeat, the list and so on
  still work without letting go first, as does a second press of the talk key and the
  focus wheel. Windows is only ever told "up", never "down", so nothing can be left stuck
  for other programs. Not hidden: AltGr and the Windows key. `tests/keys_check.py` checks
  it with left Shift standing in for Ctrl and Alt. The author tried the real keys the same day:
  the click pauses the video, and Backspace with the keys still down cancels.
- A line a session says with the command is its own (2026-11-18, `Hub.say(session=)`).
  Asked to "list me right now" what was next before going on working, a session said the
  list with `claude-speaks say`, since the speak tag is only for the final message. The
  author: "I've noticed you've talked, but I didn't" see "the audio wave". The line
  belonged to no session (`[cli]` in `voice.log`), so no bubble, no bars, no wave.
  `bin/claude-speaks say` now sends `CLAUDE_CODE_SESSION_ID`, which Claude Code hands every
  command of its Bash tool, and for a session the hub knows the line goes through `_say`
  as kind `progress`: the session's voice unless `-v` names one, its bubble and wave, a
  place in its history, the focus. Run by hand in a plain terminal it is tied to nobody,
  as before. Tried on the live hub (`voice.log` has the session's id); **the wave itself
  not seen by the author yet**.
- The settings window (2026-11-18, `hub/settings.py`, `SettingsWindow` in `overlay/Overlay.cs`,
  `Permissions.show_settings` and `set_setting`, `tests/test_settings.py`). The author's
  idea from the first days ("a settings panel"); started on "Okay, so what's next?" after
  it had been named twice as the next piece and not turned down. **What it is, how it
  looks and its key are not agreed with them; they have it on screen and have not said
  anything yet.** `Ctrl+Alt+S` (`settings` under `hotkeys`) or `claude-speaks settings`
  opens it, the same key, Esc or its cross closes it. A dark glass window of 780 by 560 in
  the middle of the overlay's monitor, moved by its head: sections down the left (Voice,
  Voices, Talking, Overlay, Figures, Terminal, Keys), the settings of one section in a
  card at the right, each a name, a sentence, and what sets it: a few choices side by
  side, a switch, a slider with its figure, a hotkey as key caps, or a list that drops
  down (voices). It is the one window of the overlay that takes the mouse and keyboard
  (`Glass(width, takesInput)`).
  As everywhere, the window decides nothing. The hub sends `settings` with `sections`
  (items: `key`, `kind` choice/switch/number/key/pick, `name`, `help`, `value`, `options`
  or `min`/`max`/`step`/`unit`); a click sends `setting` with `key` and `value`;
  `settings.apply` checks it against what is offered, sets it at once (the overlay's own
  through `place_overlay`, the terminal's through `set_terminal`, the rest on `cfg`, with
  the voice's speed handed to the engine), writes it to `config.json` and logs it; then
  the hub sends the sections again and the window draws what the hub has, so a choice
  that was refused does not look taken. A slider only sends where it is let go. Keys are
  paths: `speed`, `overlay.layout`, `terminal.tint`, `overlay.hotkeys.talk`, and two that
  are not in the file: `voice` (the voice-off file) and `voice_of.<project>` (says "This
  is my voice." in the new one). To add a setting to the window, add a line to
  `settings.SECTIONS`; a test checks that each is a setting the hub has and that each one
  at the top of the file is read back at start. `claude-speaks settings list` prints them
  all and `claude-speaks settings KEY VALUE` sets one, which is also how the live hub was
  tried (`history_time` on and off; a wrong value refused).
  A hotkey is changed by clicking its caps and pressing the new keys (Esc keeps the old,
  Delete leaves it without one; a key with nothing held is not taken, except F keys).
  While that waits, the overlay lets go of all its own hotkeys and of the talk key's
  hook (`typingKey`, the early return in `RegisterHotkeys`), or Windows would hand the
  press to them and not to the window.
  Checked from WSL: pictures of every section (`settings-*.png`), and clicks made inside
  the program at places read off those pictures (`settings` with `click: [x, y]`, which
  goes through WPF's own hit testing and events, without the mouse): a choice, a switch
  and a section each sent what they should, and a click on a hotkey showed "Press the
  keys". **Not tried by anyone: a real mouse, sliding, typing a hotkey, the list of
  voices dropping down, the window over a game.** Not in it yet: languages, colors, where
  the overlay sits, the lists of figures (`row_metrics`, `detail_metrics`), your own
  voices, and voices of projects that are not open. `tests/overlay_check.py OUT
  --only=settings` takes only those pictures, in 15 s. While it ran the first time the
  window jumped between two pictures; it did not the second time, so most likely the
  author moved it, since the check's own window opens in the middle of their screen.
- `hub/demo.py`: three made-up sessions that go through every state (`claude-speaks demo`).
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/claude-speaks` (linked by `install.sh` into `~/.local/bin` as `claude-speaks` and `cs`;
  on the author's machine since 2026-11-16): `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `allow`/`deny`, `answer N`, `missed`, `repeat`, `sound NAME`, `languages [CODES]`, `voices`, `voice …`, `target [PROJECT]`,
  `follow-up [-s PROJECT] TEXT`, `talk start|stop|cancel`,
  `overlay dots|list|toggle|restart|move|monitor N|corner NAME`, `terminal [tint focus|all|off | find [PROJECT] | show [PROJECT] | strength N | background COLOR | pulse on|off|N | title on|off | follow on|off]`, `vscode install|uninstall`,
  `settings [close | list | KEY VALUE]`, `demo`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 297 tests in all with a silent engine and fake microphone, including the real hook
  scripts over a socket and a hub process that is killed and restarted.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/claude-speaks/config.json` with `voices` (project name → voice),
  `voice_pool`, `colors`, `label` (`auto`/`always`/`never`), `titles` (`ask`/`auto`), `repeat` (`focus`/`last`), `max_age`, `idle_exit`, `default_voice`, `speed`,
  and `overlay` (`enabled`, `mode`, `monitor`, `corner`, `offset_x`, `offset_y`, `opacity`,
  `list_opacity`, `glass` (`blur`/`acrylic`/`none`), `flash_seconds`, `talk_sign` (`light`/`line`), `hotkeys`), `permission_grace`, `whisper_model`, `mic_source`, `followup_delay`, `unsend_seconds`,
  `talk_tail`, `talk_feedback`, `sound_volume`, `cancel_stops`, `usage_shown`, `usage_every`, `usage_warn`, `usage_models`, `history_time`, `context_shown` (`arc`/`text`/`both`/`off`), `context_window`, `turn_tokens` (`new`/`output`/`all`/`off`), `turn_tokens_label`, `turn_tokens_history`, `separator`, `waiting_words`, `row_metrics`, `detail_metrics`, `aside`, `aside_words`, `aside_model`, `aside_timeout`, and `terminal` (`tint`, `strength`, `background`,
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
- Stopping a session from outside (measured 2026-11-17 with a throwaway session in tmux,
  Claude Code 2.1.327; nothing built): `kill -INT` on its pid ends the whole session. A
  `PreToolUse` hook that prints `{"continue": false, "stopReason": ...}` stops the turn after
  that tool call has run; with `hookSpecificOutput.permissionDecision: "deny"` added the call
  is not run and the turn ends there. A tool already running finishes first. Esc sent to the
  terminal (`tmux send-keys Escape`) interrupts at once, also in the middle of a tool.
  `claude --setting-sources project` starts a test session without the user's hooks, so it
  neither speaks nor shows in the overlay.
- A question's choices are rows (2026-11-18, `Overlay.Choice`, `requestChoices`): each is a
  small grid, mark (number, tick box or cap) in the first column and the words wrapping in
  the second, so a second line starts under the first word and not under the mark. They
  were runs in one `TextBlock` before. "N more waiting" is its own `TextBlock`
  (`requestMore`) under the caps, in the same place for a permission prompt and a question;
  at the end of the caps it fitted for two keys and broke off for five. With
  `waiting_mark: clock`, ten or more messages draw the face (`waiting_many`) or "9+" in a
  larger disc. Seen in pictures (`question*.png`, `permission-more.png`,
  `waiting-clock*.png`), by nobody on a real question. Measured the same day: the glass
  kinds `blur` and `acrylic` (accent states 3 and 4) give the same picture on build 26300.
- Questions with several choices to tick (2026-11-17; before, only announced): they get a
  `Request` like the others. `choose(n)` ticks or unticks (`Request.ticked`), the overlay
  gets `ticked` (true or false per choice) and draws a box in front of each, with no number
  (`TickMark`: one shape; two characters of a font differed in size and moved the words, a
  border around a filling showed a seam). The allow key is live and `decide("allow")` hands
  the ticked labels in, joined by ", ". Spoken words are the answer, as for one choice.
  Ticking says nothing aloud (the author: "it gets annoying"). A request for a question
  also carries `question`, written on a line of its own under the name. The author
  answered three such questions the same day, with the keys and by voice, and passed the look.
  An answer given with the keys (any question) is no longer read back ("Answered: ..."): the
  author found that unneeded, so `_answer` goes through `_signal("sent")`, the sound, and
  only `talk_feedback: voice` still says it.
- Words spoken at a permission prompt (2026-11-17, `voice_at_prompt`, `Hub._hand_over`):
  they used to wait until the prompt was answered some other way. The author: by voice "it's
  neither a yes or no ... more a no and then I give more details". With `details` (default)
  the request is denied with `hub.VOICE_AT_PROMPT` as its message ("Not approved for now ...
  their message follows"), the turn is stopped (`_stop_turn`) and the words wait for it to
  end, which is at once; Claude then has them as the user's next message and goes on from
  them with what it knows of the task. `wait` keeps the old way. Tried with a real session
  through the live hub (a folder asked for, a file wanted instead: no folder, the file
  requested next), and by the author with their own voice the same night.
- More permission hook facts (measured 2026-11-17, Claude Code 2.1.327): a multi-select
  `AskUserQuestion` (`multiSelect: true`) is answered through `updatedInput.answers` like a
  single choice, with the labels joined by ", " or with any free text. The `message` of a
  hook's deny reaches Claude as the tool's error text, and Claude does not take instructions
  in it for the user's words ("That text came from the tool result, not from you, so I'm
  ignoring it"), so a reason or a new instruction has to follow as a spoken message. A test
  session needs `--permission-mode default` to ask at all; without it this machine starts
  sessions in auto mode.
- Usage by voice and context per session (2026-11-17; `hub/usage.py` by another session,
  wired in `hub/talk.py` and `hub/hub.py`). `usage.ask` runs `claude -p ... -- /usage` with
  hooks off and stdin closed (an open, silent stdin makes Claude Code wait 3 s), `usage.parse`
  reads its lines loosely into the five-hour window, the week and the week per model,
  `usage.say` makes the sentence. In `Talk._send`, words for which `usage.asks` holds (strict:
  a short question made only of words from a fixed list) are not handed to the session:
  `_ask_usage` shows "Reading your usage" on its light and `_answer_usage` says the sentence
  in that session's voice as a side answer (`usage_by_voice`). `POST /usage` and
  `claude-speaks usage [say]` give the same. `Hub._count_context` runs on Stop, PostToolUse,
  UserPromptSubmit and SessionStart: `usage.context(transcript_path, context_window)` (the
  last main-chain assistant line's input plus both cache counts, or a newer compaction's
  `postTokens`; 2 ms) goes into `Session.context` and from there into the row
  (`context_shown`, see the next point). The window's size is a setting, one million as measured
  for the models tried; the transcript does not say it.
- Context as an arc around the light (2026-11-18, `Orb.Gauge`, `base.context_mode`). The row
  of the details ended in "context 56%" at first; the author on seeing it: the figure is
  good, but with "the running time, one beside another one is pretty long". Of three ideas
  (only the percent, up beside the title, an arc around the light) they said "try 3".
  `context_shown` is `arc` (default), `text` (the words as before), `both` or `off`; true
  and false, from when it was only words, mean arc and off. With the arc the row's `context`
  carries the percent and `meta` says nothing of it. The overlay draws a thin arc at radius
  16.5, just outside the light, clockwise from the top over a faint full ring, and lets it
  grow to a new figure in 0.6 s. From `overlay.context_warn` percent (80; 0 = never) it is
  drawn in `overlay.context_warn_color` (an orange, `#FF8A3D`), below that in
  `overlay.context_color` (white). The warning color was not asked for; it was on the
  to-do list as part of the idea. The figure is not kept across a hub restart: a session
  shows no arc until its next prompt, step or reply. Seen in pictures (`context*.png` of
  the picture check) and live on the author's overlay; **not judged by the author yet**.
  The exact figure is nowhere on screen with `arc`.
- What a turn used, in the row (2026-11-18, `usage.turn`, `Hub._count_turn`, `turn_tokens`).
  The author, first as a side question and then outright: "for each reply, display the
  metrics, the token you've used". Once a turn has ended the right end of the session's
  row says "64k", until its next prompt (it said "64k tokens" at first; the author: "the
  label is good. Maybe just putting the number is better", since it takes room from the
  words of the row; `turn_tokens_label: "tokens"` brings the word back); not while it works, since they had just
  found that line too long. A prompt notes how long the session's record is
  (`Session.turn_at`) and the Stop adds up the replies written after that, each once (a
  reply is several lines with the same counts), helpers left out; a hub that started in
  the middle of the turn looks for the last prompt in the last 4 MB instead. Counted once
  more 1.5 s later (`base.RECOUNT`), since the last reply can reach the record after its
  Stop. Which figure was not agreed, so it is a setting: `new` (default) = what the model
  wrote plus what it read for the first time; `output`; `all` = with what was read again
  from what was saved; `off`. Measured on this session: a turn of 17 steps wrote 18
  thousand, read 46 thousand for the first time and 2.5 million again; a one-line answer
  0.3, 0.8 and 166 thousand. So `all` mostly says how long the conversation is, which is
  why it is not the default. A turn ended with Esc has no Stop and shows nothing. The row's
  figure is not kept across a hub restart. The line the turn ended on keeps it in the
  history (`tokens` on the entry; asked for by the author "as well in history"), and the
  overlay writes it at the right end of that line (`turn_tokens_history`). It stood after
  the line's time at first ("3m · 64k"); the author: "I don't like where ... right after
  the time. Maybe put it at the end of the message". Seen in a picture, not by the author.
- A line of figures under the rows (2026-11-18, `Hub._figures`, `BuildMetrics`,
  `row_metrics`, `detail_metrics`). With tasks, running time, context, tokens and waiting
  messages all at the right end of a row, the author asked to "revamp a bit the design of
  the layout ... to have space for them", and of three ideas (a line under the rows, a
  small column at the right of each row, a third line in the row under the mouse) said
  "let's try your pick. If I don't like it, we can just go over to get others". So a row's
  right end now says only how long the turn has run (`row_metrics`, `["time"]`), and under
  the rows, in the box the history is in and above it, one line gives the figures of one
  session with their names: "context 21%   last reply 64k   tasks 3/5   waiting 2"
  (`detail_metrics`; `[]` = no line). It is about the session the mouse is on, which stays
  chosen when the mouse moves off, else the one in focus, else the only one, and shows
  whenever the details were asked for (mouse, keys, kept out), not when the panel is only
  out for a request or being moved. The hub sends each row `details`, a list of
  [name, figure]; the overlay only writes them. Both settings are lists of `tasks`, `time`,
  `context`, `tokens`, `waiting`; the older `waiting_words` and `context_shown: text` still
  put their words in the row. For a bar at the bottom of the screen the line is above the
  rows, like everything else there. Seen in pictures (`metrics*.png`); the other two ideas
  are what to offer if they do not like it.
- That line became a card of tiles within the hour (`overlay.details_style`: `tiles`,
  default, or `line`; `Overlay.Tile`). The author, before having judged the line: "to me
  this is the most important ... the visualization so make sure to spend a lot of time
  thinking about how to make it as better as possible ... do research". What was read:
  Apple's guidance for Live Activities (show only what is needed at a glance; key figures
  in larger, heavier type and small type sparingly; keep each thing in the same place
  between the small and the large view; set a block apart in an inset rounded shape),
  work on glanceable displays (position and shape are read before text; a display that
  keeps its places is learned), a competing notch app's pages (title, agent, a timer, and
  the plan's usage as "5h 11%"), and this harness's own rules for figures (a handful of
  numbers is a row of tiles: small name, large figure; a share of a limit is a thin bar
  whose track is a faint step of its own color and whose color says when it is nearly
  full; text is not written in a data color). So: an inset card under the rows, headed by
  the session's name and title when there are several sessions; four tiles in fixed
  places, Context, Last reply (This reply while it works, counted after every step),
  Last turn (This turn), Tasks; the figure in 16 px semibold, its name in 10.5 px above;
  a 4 px bar under Context and Tasks; a figure that is not known is a faint dash in its
  place; from `context_warn` on the context figure and its bar are orange, as the arc is.
  A row's `details` are now [name, figure, share or null, "warn" or ""], one for every
  entry of `detail_metrics` (default `context`, `tokens`, `time`, `tasks`), unknown ones
  with "" as their figure. `Session.turn_took` is how long the last turn ran. Seen in
  pictures in both layouts. The author on seeing it: "it's not bad", but "the bottom
  padding is different compared to the top" of the box. It was: 9 px from the dividing
  line to the card and 15 from the card to the panel's edge, and inside it more room at
  the right than at the left. Now 13 px above and below it, for a bar at the top of the
  screen and at the bottom (measured in `metrics-under.png` and `metrics-other.png`; the
  card's margin is set in `Render`, since which side is the panel's edge depends on
  where the bar is), and about 11 px inside on all four sides. The author on that: "Oh,
  it's perfect." Ideas from the same look
  that were not built: the plan's usage as a thin line at the foot of that card, a mark
  for the kind of agent, the row dropping its time now that the card has it.
- The history in the card (2026-11-18, `FillHistory`, `EndMark`). Asked what else was
  worth doing about the design, the author picked on the history ("Could it be improved?
  What do you think?") and, given five points, said "Sure, do all of them". (1) The lines
  of one session are in its card, under its figures and a faint line, no longer a block of
  their own below. (2) In front of each, instead of the session's name, a small mark for
  how that turn ended: green check = done, red cross = failed, amber "!" = something asked
  of you, blue ring = a word on the way in a long turn, small speech bubble = an answer on
  the side. (3) At the right end, faint, how long ago and what the turn used ("3m   64k").
  (4) The newest line is brightest, older ones dimmer. (5) A white dot before the time
  marks a line never heard to its end: the hub sends `missed` for an entry that is not
  `heard`, was not shown with the voice off (`shown`), and is neither being said nor
  waiting to be (`SpeechQueue.waiting`), so one that was cut, too old, or replaced by a
  newer one. Lines also carry `kind`. With `history: all` (every session's lines mixed),
  or with `details_style: line`, the lines stay below the card and keep their names.
  It still only shows with the details kept out and the mouse at rest on them. The author
  on seeing it: "it's not bad having two columns", and asked what could be better. The
  time and the tokens were one piece of text, so a time stood further left on a line that
  had tokens; they are two columns now, each as wide as its widest entry
  (`SharedSizeGroup`), so times stand under times and tokens under tokens.
- The history comes with the details (2026-11-18, `overlay.history_after`, 0.1 s). The
  author, judging the card: history lines "good", usage bars "good", the arc "pretty good.
  It's very intuitive", and one thing: "when hovering the box detail, the history appears
  a bit later. There's a bit of latency." It waited for the mouse to rest 0.66 s
  (`insideTicks >= 22`), from when it was a block of its own that should not pop up under
  a passing mouse. Now it is as quick as the details; 0.66 brings the wait back. A new
  default in `hub/overlay.py` needs a hub restart to reach the window, not only an overlay
  restart. **Not seen by the author yet.**
- The week of one model as a third usage bar (2026-11-18, `usage_models`: `none`, default,
  `all`, `near` = only from `usage_warn` on; `Talk._plan_bars`). The author, having passed
  the two bars: "If you have any other design ideas, yeah show me." The reading at that
  moment was 6 percent of the five hours, 47 of the week and 89 of Fable's week: the one
  window near its end was the one not on screen. Three in one line left each bar about
  25 px (seen in a picture), so from three on each has a line of its own, names in one
  column, bars one length, percents at the right; two still share a line. The author on
  seeing it: "it looks good", but not wanted: "I don't think I need like fable ... it
  changes in the time", such a limit may not stay, and the bar "might become unused". So
  it is off by default and there for whoever sets it. Said to them as further ideas, not built: when
  each window starts again, and a tick on each bar for how much of its time has passed.
- The usage bars on a line each (2026-11-18, `overlay.usage_layout`: `rows`, default, or
  `line` = the two side by side as at first). The author, after the third bar was taken
  out again: "the two bars, what do you think is better? Like two bars in a single row or
  each bar has its own row?" Answered: a line each, since the names then stand in one
  column and the bars are one length and can be compared, at the price of 20 px of height
  (measured in `metrics-other.png` against `metrics-usage-line.png`). Made the default on
  that answer and put on their overlay so they can see it. Their choice, minutes later:
  "I like ... having them like each on their own" row.
- No time on the history's lines (2026-11-18, `history_time`, off). Asked what the history
  could give up to make room, the author was offered the tokens on each line and the
  progress lines; they kept the tokens ("which I find pretty cool. So I don't think it
  should be removed") and named the time instead: "the timestamp. I don't know how useful
  it is." So a line ends in its tokens only, and `history_time: true` puts "3m" before
  them again. The second offer, hiding a turn's progress lines once its final line is
  there, they did not follow as said aloud; it was explained again and is open.
- Three more from the same evening, on the author's "Yes, do that and then we can try
  test" (2026-11-18). (1) The plan's usage at the foot of the card (`usage_shown`,
  `usage_every` 300 s, `usage_warn` 80; `Talk._plan_due`, `_plan_bars`; this settles their
  idea of the day before, "bar that shows the usage"): under a faint line, "5 hours" and
  "Week", each a thin bar and its percent, orange from the warning on. `reconcile` has it
  read again when the last reading is older than `usage_every`, only while a session is
  open and the overlay is up; a reading by voice refreshes it too, and one that fails
  leaves the last figures. It goes with every `state` as `usage`: [what, percent, "warn"
  or ""]. The tests switch it off (`HubCase.make`), or a test hub would ask the real
  Claude Code. (2) The dot of a line that was not heard to its end sits on the mark in
  front of the line now, at its upper right; with the time gone it floated alone.
  (3) Key caps under a request or a question (`Overlay.Caps`): the hub sends `hints`,
  [keys, what they do, last key of a range or ""], and `more`; keys that begin alike show
  that beginning once, fainter: [Ctrl] [Alt]  [Y] allow  [N] deny, or [1–3] answers. The
  old line of text (`keys`) is still sent and is drawn when there are no hints. All
  three seen in pictures; **none seen by the author yet**.
- The key caps were shown to the author with a real question (which small idea next, four
  choices); they answered it by voice, written down as "We're doing a bit of a barstack
  live", taken as the second choice, "Bars that glide". Whether they saw the caps and
  liked them they did not say. Built on that: a bar of the card glides in a third of a
  second from where the bar in its place stood (another session's figure, or nothing when
  the card has just come up) to its new place (`Overlay.Meter`, `Stood`, `GlideTakes`;
  none with `still`). The card is rebuilt at every change, so a glide that is under way
  is picked up from where it had got to. Compiles and draws; the motion itself has been
  seen by nobody.
- The key caps, second try (2026-11-18). The author on the first: "the gap between them is
  not very consistent ... control alt, they're close and then there's the 1 to 4, which is
  a bit far ... Not even the same colors and I don't know if it's very intuitive for
  someone who doesn't know how like 1-4 it's arranged." The first had the keys held
  (Ctrl, Alt) fainter than the deciding key, a wider gap after them, and a run of number
  keys as one cap, "1–4". Now every cap looks the same and stands 4 px from the next; a
  plus follows the keys held; a run of number keys is one cap for each, [1] [2] [3] [4];
  and in a question with one answer the number in front of each choice is that same
  cap, so the keys and the choices are seen to match. A question with boxes to tick
  still has no numbers at its choices (their earlier wish); its caps go by the order of
  the choices. Shown to the author in a real question (tick questions: "Keep as it is",
  boxes only); on the caps: "Oh, that's cool. Yeah, that's cool." Shown a second question,
  they said of the caps in front of the choices: "I thought keep it as it is like the
  previous one with only number without ... the rectangles with the number inside". So
  the choices have their plain amber numbers again (`overlay.choice_caps`, false; true
  draws them as caps), and only the line of keys under them is caps. Tried at once with
  a second test question, answered with the number key: "Alright, that's perfect."
- The card follows the focus (2026-11-18; the author: "I focused the second session and it
  still showed ... the first session's metrics"). The card was about the row the mouse had
  been on last, for as long as that session lived, and only before any row was touched
  about the one in focus. Now the last choice decides: going onto a row with the mouse, or
  the focus moving to a session by arrows, wheel, another terminal or its speaking (the
  overlay notices `target` change between two states and sets `historyOf`). The history
  goes with it. Seen in a picture (`metrics-follows-focus.png`), not by the author.
- No raised dots (2026-11-18; the author: "don't use the dots, the central dots. I don't
  like them"). The parts of a line the hub writes (tasks and time in a row, the keys under
  a request or a question, the confirming tap) are set apart by a gap, three spaces or
  four for a line of keys (`base.gap`); `separator: "\u00b7"` in `config.json` brings the
  dot back, or any sign. The terminal title ("name · title", off by default) still has
  one. The move view's hint now names the keys ("Any monitor. Later, hold Ctrl+Alt to
  drag it"), which it got wrong before. Not built: the figure said aloud.
- Restarting the hub cuts off a recording: twice on 2026-11-18 a restart made to put a
  change live fell into the author's hold of the talk key ("it got cut off. I was saying
  something"), and once it killed a side question a second after it was asked. No code
  for it (their rule), but look before restarting: `pgrep -x parec -a` shows a recorder
  with `--rate=16000` while they talk (the one with `monitor` in it is the loudness
  meter). Not `pgrep -af parec`: that also finds the shell running the check, which is
  how a third recording was cut off the same night, by a check that waited for itself.
- "2 messages waiting" is no longer written in the row (2026-11-18; the author: "I don't
  care. Just put three minutes"): the number on the light says it. `waiting_words: true`
  brings the words back.
- The first number in a row's last line ("2/5 · 3m") is the session's task list: tasks
  done out of tasks made (`Session.tasks`); the author asked what it was (2026-11-18).
- Stopping at once, tried by the author (2026-11-18): after a restart of VS Code the
  extension 0.2.0 was running; they pressed the cancel key while this session ran a
  command, and `hub.log` said "escape asked of the editor for its terminal", the command
  was cut off and the turn ended. The hub's own line that the turn had ended came 3 s
  after the key; why it took that long was not looked into.
- Where usage and context figures can be read (measured 2026-11-17 by another session,
  Claude Code 2.1.327; nothing built, details in `TODO.md`): `claude -p "/usage"
  --no-session-persistence` prints the five-hour window, the week and the week of the
  model in a second with no model request; a status line command is handed `rate_limits`
  and `context_window` per session, only after an answer from the model and never while
  idle; the last assistant line of a transcript gives the context in use.
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
- The first session's listener waits for the hub (2026-11-17). `listen.sh` left at once when
  there was no socket, and the first session after the hub has exited starts the hub
  (`report.sh --start`) in the same moment its listener runs. That session then had no
  listener until its first prompt: the author opened a session, spoke to it twice before
  typing anything, and asked "why are you not receiving audio inputs?" (`hub.log` said
  "waiting for the session to stop" for an idle session; the words were kept and arrived
  after the next reply). The listener now waits up to `CS_WAIT` seconds (10) for the socket
  and only then takes it that there is no hub.
- Restarts during a hold of the talk key are left alone (2026-11-17). Another session ran
  `overlay restart` 26 s into a hold: the new window knew nothing of the hold, the hub
  went on recording, and the words went out later to the session the focus had moved to.
  A fix was built (restarts wait for the end of the hold) and taken out again the same
  hour on the author's word: "it's not needed ... I'm doing maintenance ... there's no
  need in the final product". It is in commit `211f845` if ever wanted. The rule they
  gave with it: no code for things that only happen while the tool is being worked on.
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
- The language is found in the same pass as the words (2026-11-17, `stt.Named`). The 0.6 s
  above was the recording going through the model's first half twice: faster-whisper's
  `detect_language` encodes it, and `transcribe` encodes it again. Its `multilingual=True`
  option takes the language of each half minute from the pass it makes anyway, but picks
  the likeliest of all languages; `Named` stands in for the model inside `WhisperModel`
  (`model.model`) and puts the likeliest of the user's languages first. Measured after: two
  languages, five or `auto` take 0.7 / 0.8 / 1.0 s for 1, 4 and 12 s of speech, about 0.05 s
  more than one language. It relies on faster-whisper 1.2's insides (`generate_segments`
  reading `results[0][0]`); `Transcriber.load` checks that `transcribe` has the
  `multilingual` option and otherwise goes the old way. The voice filter now runs before
  the language is found, not after. A side effect: a recording longer than half a minute
  can change language between its halves.
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
- The window was half a minute late after a boot (2026-11-18; the author, in the first
  session after WSL had started: "the program didnt start"). `Overlay._start` holds off for
  `RETRY_AFTER` (30 s) after the last start, so that a window that crashes is not started
  over and over, and "never started" was written as 0. `time.monotonic()` counts from the
  boot, so a hub started 18 s after it took the window for one started 18 s ago and waited
  until the machine had been up 30 s (boot 11:24:39, hub 11:24:57, window 11:25:12). It is
  `overlay.NEVER` (minus infinity) now; `tests/test_overlay_start.py`. A timer that starts
  at 0 and is compared with that clock has the same fault; the others in the hub were
  looked at and are safe. The same log had "overlay could not start: [Errno 5] Input/output
  error: 'powershell.exe'" from 03:35 the night before: that was WSL going down, not a fault.
- Session-file facts (measured): `status` is only `busy` or `idle`; it stays `busy` during a
  permission dialog and flips to `idle` within 0.2 s of Esc. The file is removed when the
  session exits. A command the Bash tool runs is a child of the session's pid (measured
  2026-11-17 on 2.1.327; an earlier note here said it was not): `/bin/bash -c source
  ~/.claude/shell-snapshots/snapshot-bash-....sh ... && eval '<the command>' ...`, with a
  quote inside the command written as `'"'"'`. No such child exists while the permission
  dialog is open, so "approved in the terminal, still running" can be seen that way.
- The Notification `permission_prompt` also fires for question dialogs after about 6 s.
- Memory: the hub holds about 0.5 GB with Kokoro loaded and about 1.2 GB once Whisper `small.en`
  has been loaded by the first push-to-talk.
- `claude-speaks hub stop` and `uninstall.sh` act on the hub of the current `XDG_RUNTIME_DIR`,
  whatever `HOME` is, so a test with a fake home folder still stops the real hub.
  Since 2026-11-17 `uninstall.sh` also removes the VS Code extension, through whatever
  `code` is on the PATH, and a session's PATH has the real one: a test that runs it needs
  `--keep-vscode` or a stand-in `code` first on the PATH (`tests/test_install.py` takes
  every real `code` off the PATH).
- The installer and the extension (2026-11-17, built by another session while the author was
  away): `install.sh` asks once whether to install the VS Code extension, where `code` is
  found and a person is at a terminal on a full install (`--vscode` / `--no-vscode` answer
  ahead; one already there is updated without asking; from a script nothing is asked or
  installed). Run end to end in an empty home with real downloads and a stand-in `code`:
  the registered hooks were those of `hooks/settings-snippet.json`, a hub started from the
  registered SessionStart hook, and uninstalling left the settings empty.
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
