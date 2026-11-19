# How each part works, and why

Feature by feature: what it does, the settings behind it, what the author said that made it so, and what was measured. Moved here unchanged from `CLAUDE.md` on 2026-11-19 (it was its "How it works" section). Add to it when you change a feature; search it for a setting's or a function's name.

## Notes

```
Claude sessions ──hooks (bash + curl)──▶ hub (Python, in the Kokoro venv) ──stdin──▶ overlay (Windows)
                  Unix socket, owner-only   session state · speech queue   ◀─stdout── hotkeys
```

| Hook event | Script | Job |
|---|---|---|
| UserPromptSubmit | `hooks/voice-reminder.sh` | Injects an instruction: open the final message with ONE line that is exactly a speak tag |
| MessageDisplay | `hooks/display.sh` | Runs per streamed batch. Sends a batch containing a speak tag to the hub, which queues the speech and returns the "🔊 …" rewrite |
| Stop | `hooks/speak.sh` | Tells the hub the turn ended; the hub speaks the line only if streaming missed it. A batch with the same line that arrives after Stop (seen once, 2026-11-19: six seconds late, so the line was said twice) is not spoken again; the next turn may say the same words |
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
  `$XDG_RUNTIME_DIR/sidetone/hub.sock` (not a TCP port, so no web page or other machine can
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
- Replies in your language (2026-11-19, `reply_language`, `Hub._voice_for`, `tts.voice_lang`,
  `state.tag_lang`). The author, by voice, on being offered it as the next thing: "yes
  proceed". The reminder asks for the spoken line "in the language of my last message", with
  `lang="xx"` in the tag when that is not English; the tag's attributes are read in any
  order (`state._attrs`; the no-hub fallback in `display.sh` takes any too). A line with a
  language gets one of Kokoro's voices for it, of the same kind (female or male) as the
  session's own and always the same for a session; Kokoro is told how to pronounce from the
  voice's first letter (`if_sara` is Italian), so a replayed line keeps its language. The
  installed voices: Italian 2, Spanish 3, French 1, Portuguese 3, Hindi 4, Japanese 5,
  Chinese 8; all seven languages synthesized in a test (Japanese and Chinese go through
  espeak and were not listened to). No voice for the language (German, say): the session's
  own English voice reads it. `reply_language: english` keeps it as before; the hook reads
  that from `config.json` like `titles`. The hub's own words ("Sent.", "I need your
  input") stay English. Heard on the live hub only through `sidetone say -v if_sara`;
  **no session has answered the author in Italian yet.**
  Kokoro's Italian was "troppo robotica" to the author; of Kokoro's Sara and Nicola, Piper's
  Paola and Chatterbox Multilingual (12 to 17 s for 6 s of speech on their CPU) they kept
  Paola "per il momento". So the Kokoro engine also speaks Piper's voices
  (`KokoroEngine.piper`, named `piper:<model>` after each `.onnx` with its `.json` in
  `~/.local/share/piper/voices`; one `piper` process per part, about 0.3 s, resampled from
  22050 to 24000), and a language can have a voice that beats Kokoro's
  (`tts.PREFERRED_VOICE`, `it` = `piper:it_IT-paola-medium`; `language_voices` in
  `config.json` names another). After hearing Pocket TTS and Chatterbox on the graphics
  card too, they kept three: Paola, Sara and Nicola. So a language has a list, best first,
  shared out like the English voices (`Hub._share`): the first session gets Paola, the
  next one no other open session uses, kept per session name.
  Chinese (same evening): Kokoro 1.0's Chinese goes through espeak; the author preferred
  Qwen3's speakers but not their wait, then took four voices of Kokoro's Chinese model
  v1.1-zh ("preferisco questi quattro"): `zh:zf_001`, `zh:zm_009`, `zh:zf_002`,
  `zh:zm_010`. The engine loads that model on its first Chinese line (`KokoroEngine.zh`,
  files `kokoro-v1.1-zh.onnx`, `voices-v1.1-zh.bin`, `config-v1.1-zh.json` beside Kokoro's
  own, phonemes from `misaki-fork[zh]`, `is_phonemes=True`); without them `zh_voices()` is
  empty and Kokoro 1.0's Chinese voices are used. 0.5 to 0.7 s for 5 s of speech on the
  CPU, loaded beside Kokoro at the hub's start when installed (the first Chinese line
  took 5.3 s while it loaded on use; 0.4 s after). `tts.sentences` also cuts after 。！？. English words in a Chinese line ("Control Alt M") came out
  as "❓" and were left out, which the author heard; misaki's `en_callable` now gets
  espeak's English phonemes from kokoro-onnx's `Tokenizer`. Installing `misaki-fork[zh]` into the hub's
  environment was refused by the permission check twice on spoken, unclear yeses, and
  done on the author's typed "si": files in `~/.local/share/kokoro`, `misaki-fork[zh]`
  0.9.6 in the hub's environment, `whisper_language` `en,it,zh`. Heard through the hub.
  The model was copied by hand into the author's Piper folder; `install.sh` does not
  fetch it yet.
- `hub/state.py`: session registry. Label = folder name, spoken only when more than one session
  was active in the last 15 min and no overlay is on screen (the author, 2026-11-17: "i dont
  think it's necessary to say the project folder whenever it speaks"; the bubble and the voice
  already say who it is). `label: always` brings it back. Voice = stable hash of the name over a pool of 13 clearer
  English Kokoro voices, never one a live session already uses.
- `hub/overlay.py` + `overlay/Overlay.cs` (+ `overlay/overlay.ps1` as fallback): the on-screen
  overlay, a child process of the hub (only where `powershell.exe` exists). `overlay.build()`
  compiles `Overlay.cs` with `csc.exe` of .NET Framework 4 (ships with Windows; about 0.2 s)
  into `%LOCALAPPDATA%\sidetone\sidetone-overlay-<hash of the source>.exe`, once per
  version of the source; if that fails the same source runs through PowerShell `Add-Type`
  (`SIDETONE_OVERLAY=script` forces that). The hub sends `config`, `state` (one
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
  `sidetone overlay layout NAME|next` switches, and `Hub.set_layout` saves it. `island` lays
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
  only needs the cursor's position. `sidetone overlay move` works without the keys.
  The author dragged it with the keys held the same day ("it works. Now perfect"), and the
  new place was saved. Later that day: "sometimes the cursor is not aligned" with the bar
  while dragging. `BeginDrag` took the grab point from `GetCursorPos` when the press was
  handled, which is after the mouse has moved on; it now takes it from the press
  (`e.GetPosition`). The author dragged it afterwards: "Perfect, it seems to be working."
- Sessions in an order of your own (2026-11-19, `overlay.reorder_keys`, `Press`, `LiftStep`,
  `EndLift` in `Overlay.cs`, `Sessions.reorder`). The author, by voice: "if we could move the
  ... sessions", by dragging; Ctrl+Alt was already the key for dragging the bar ("they're kind
  of going [to] conflict"). Their own way out, taken as said: "make the whole layout draggable
  by default ... and maybe with control alt you can ... rearrange the sessions". So
  `drag_keys` is `""` by default again (a plain drag moves the bar), but with the plain
  arrow cursor and no brighter edge, which is what they disliked about it before; and with
  Ctrl+Alt held, a press on a light lifts it (a little bigger, above the others) and it
  follows the mouse along the bar while the others slide aside; let go, and the overlay
  sends `reorder` with the names in the new order, which the hub gives each session as its
  `order` and keeps in `sessions.json`, so a restart keeps it. A new session goes at the
  end. With the keys held the cursor is a double arrow along the bar over a light, and
  a drag elsewhere on the bar still moves it. Told them before: the bar takes every press
  on it again, and a game that reads the mouse its own way may miss a click passed on.
  Tried by the author the same night: lights left on top of each other after a drop (the
  drop threw, `lifted` was cleared before `LiftTarget` needed it), the focus frame not
  following (it now adds the light's `Shift`), the held light growing ("I don't like it":
  it keeps its size now, also the size a light has under the mouse), and "sometimes ...
  the whole layout overlay moves" (with the keys held, a press on the bar's rim or
  between two lights fell back to moving the bar; it now always takes the nearest light).
  That last fix did not do it ("I'll still see this issue"), and neither did taking one of
  the keys, or both within 0.4 s, as enough: `hub.log` then showed "ctrl up, alt up" at
  each press that moved the bar, a second after a reorder. So the press decides nothing
  now (`undecided`): the first frames after it look for the keys, and the bar only goes
  with the mouse once it has moved 6 px with none of them held or seen in the last
  0.4 s. A press that moves the bar still writes the keys to `hub.log` ("bar moved by
  the mouse: ...").
  "It's still happening", and the log had no such line: the bar had not moved. What moved
  was most likely the panel: their details are kept out (`mode: list`), and every drag,
  of a light too, folded the panel away and brought it back. Now only a drag of the bar
  folds it (`FoldForDrag`, `BarHeld`); while a light is held the panel stays, and in the
  bar layout its row slides with it (`Row.TextShift`). **Not tried yet.**
- What brings the details out (`overlay.hover`, 2026-11-17): `always` (default) = the mouse
  resting on the bar, as ever; `keys` = only holding Ctrl+Alt or the list key, and then a
  mouse passing over the bar changes nothing at all (no light growing under it either).
  `sidetone overlay hover always|keys`. Asked whether the bar should stop opening under
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
  session file, a slug such as `eyes-free-sidetone`, turned into words). Claude Code
  writes that name within a second of the first typed prompt, but a session started by voice
  only ever has the placeholder it gets at start (`nameSource: "derived"`, the folder plus two
  characters, `sidetone-3f`), which is ignored. Without a name the hub makes its own title
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
  back on, and since 2026-11-19 both are in the settings window under Talking (their idea:
  "un'opzione nei settings per la gente che vuole la conferma"): "Confirm before sending"
  (Never, Acting alone = `"auto"`, Always) and "Time to cancel before sending" (0 to 5 s). The hub hands it to that session's listener, shows "sent → name: text" for 2.5 s and
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
  `sidetone follow-up` and `talk cancel` on the live hub).
- Sounds instead of "Sent." (2026-11-17; the author, in Italian: the word waits in the queue
  behind a line being spoken, so it comes late and is of little use; they suggested a sound or
  a visual effect and agreed to this): `hub/sounds.py` makes three short sounds in code and
  plays each through its own `paplay`, beside the voice and not through its queue: two notes
  going up = sent, the same note twice = waiting for a busy session, two notes going down =
  not heard, not sent or cancelled. `Hub._signal` picks by `talk_feedback`: `sound` (default),
  `voice` ("Sent." or "Queued." as before; also used when there is no `paplay`), `none`.
  `sound_volume` is 0 to 1 (0.3). Quiet while the voice is off. `sidetone sound NAME`
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
  number comes up in its corner with a small jump), `first` or `each`. To show the mark on the live overlay: `sidetone follow-up -s NAME TEXT`
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
  `talk` Ctrl+Alt+Space, `repeat` Ctrl+Alt+R, `missed` Ctrl+Alt+U, `settings` Ctrl+Alt+S and `mute` Ctrl+Alt+M
  (2026-11-19, `Permissions.toggle_mute`: the voice-off file for every session, cuts the line being
  said, the sounds `voice_off`/`voice_on` and a banner "Voice off" or "Voice on"). The author asked
  for "M for mute", but on their machine the NVIDIA overlay (`NVIDIA Overlay.exe`) holds
  Ctrl+Alt+M: with it closed a probe got the key, and it came back by itself within minutes and
  took it again. Confirmed in the registry: `HKCU\Software\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS`
  holds each NVIDIA shortcut as virtual-key codes, and `MicToggleHKey0-2` are Ctrl, Alt, M: the
  overlay's "toggle microphone", NVIDIA's default, so many machines with an NVIDIA card will have
  it. The same place has `PMOCOverlayVisibilityHKey` = Ctrl+Alt+R (its performance overlay),
  which is our repeat key; the hub has always got R first, which could flip if NVIDIA's overlay
  starts before it. That is also why `missed` is U and not M. The overlay reports a taken key only
  once per run (`complained`), so a second try at it fails without a line in `hub.log`.
  Keys shared with another program (2026-11-19, `overlay.share_taken_keys`, true; `shared`,
  `sharedDown` in `Overlay.cs`). The author did not want NVIDIA's key freed, and asked that
  Ctrl+Alt+M "execute both". Windows gives a hotkey to one program only, but a low-level
  keyboard hook sees every key before hotkeys are matched. So a key that `RegisterHotKey`
  refuses is watched by the hook instead, acted on once per press (not on repeats), and passed
  on, so the other program still gets it. The hook is then in for as long as any key is
  shared. Not for the talk key, whose hold is taken from other programs. Each time the keys
  are registered again (a request opens, a setting changes) the real hotkey is tried first.
  Tried from WSL with a pressed Ctrl+Alt+M (`keybd_event`) while the NVIDIA overlay held it:
  muted and unmuted. Then M became the default for everyone, on the author's word: "can you
  not make it Ctrl+Alt+M by default for everyone? And if there's conflict just do both." So
  with the NVIDIA overlay, the key also switches its microphone.
  The mark while muted (2026-11-19, `overlay.muted_mark`, true; `muteChip`, `ShowMuteChip` in
  `Overlay.cs`): the "Voice off" notice goes after 2.5 s, so while the voice is off a small
  glass square with a struck-out speaker stands just past the far end of the bar (under a bar
  at the top, over one at the bottom, at the right of the island). It is a window of its own,
  so the lights and the rows level with them do not move; it goes away while the bar is
  dragged. `state` carries `muted`. The author said "sure" to it when offered, then on
  seeing it: "I don't like the icon underneath the sessions", and asked for words in the
  details instead, adding that a line shown while muted has a flat wave, which already tells
  them. So `muted_mark` is off, and `overlay.muted_line` (on) writes "Voice is muted" and the
  key that turns it on in a section of the panel next to the rows (`mutedBox`), whenever the
  details are out, except while the "Voice off" notice is up. Seen in a picture
  (`mute-line.png`), not by them. Their next idea, the same minute: the struck-out speaker
  in the top right corner of the card of figures (`overlay.muted_icon`, on; `mutedIcon`,
  laid over the card so nothing in it moves; `mute-icon.png`). And a fault they found:
  the repeat key spoke while muted. `_replay` (repeat, catch-up) and `say` without a
  session went to the voice without asking; while muted a replayed line is now shown at
  its light, and the hub's own words are left unsaid.
  The icon is drawn (`MutedSpeaker`), not the font's: at 14 px the font's speaker had a small
  cross at its side that could not be made out (the author: "not very clear because ... very
  small", wanting a slash over the speaker). A speaker with two waves and a slash across all
  of it, cut free of what it crosses by a gap; the same in the card's corner, the line, the
  "Voice off" notice and the mark past the bar.
  Then the place they had meant all along: "not in the ... box, I meant in the top right of
  the session's details whenever there's the response coming out", since they keep the
  details away and see lines in the bubble beside the light. So the same icon is in the
  bubble's top right while muted (`bubbleMuted`, with `muted_icon`), not while push-to-talk
  has the bubble. Seen in a picture (`mute-bubble.png`).
  With that in place, the card's icon was taken out again ("remove it from the metrics
  box"): `muted_card_icon`, off; `muted_icon` is the bubble's now.
  Found on the way: `SpeechQueue.wait_idle` returned before `on_change(None)` and `on_done`
  had run, so a test could read the overlay's state before its last update; it now also
  waits for those (`_settling`). Claimed only while they can act: `allow` Ctrl+Alt+Y,
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
  `terminal pulse off` removes it). `sidetone terminal find
  [PROJECT]` does the same on request. Stopping the hub gives every terminal its own
  background back, and a terminal seen for the first time is reset, which clears what a hub
  that died left. `title` (off by default) writes "name · title"; control characters are
  taken out, since a title can hold words from a prompt. `SIDETONE_TERMINAL=off` writes
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
  `vscode/pack.py` zips the folder into a `.vsix` and `sidetone vscode install` hands
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
- The terminal follows the focus (2026-11-19, `terminal.jump`, `Talk._ask_show`). The
  author, by voice, with two sessions in VS Code terminals that are not side by side:
  "whenever I scroll between the session ... automatically set that terminal to focus".
  When `Hub.focus` moves the focus by hand (arrows, wheel), the editor is asked to show
  that session's terminal, keyboard in it, as the jump key did; a session that speaks and
  takes the focus brings nothing up. An ask not yet answered by the editor is replaced
  by the newer one, so a fast turn of the wheel shows only where it stopped, and for
  `SHOWN_ECHO` (1 s) the editor's report of a terminal the hub asked for does not move
  the focus (it would pull it back to a session the wheel went past). Off by default
  (side by side, all terminals are in sight); on in the author's config. Needs the
  extension 0.3.0 or newer running. Tried by the author minutes later: "it seems to be
  working good."
- Session → terminal, the jump key (2026-11-18, `Talk.show_terminal`, `_showable`, hotkey
  `jump` = `Ctrl+Alt+T`, `sidetone terminal show [PROJECT]`, `vscode/extension.js`
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
- "Clear the chat" by voice (2026-11-19, `Talk._clear_chat`, `_cannot_clear`,
  `base.asks_to_clear`, `clear_by_voice`, `clear_words`, `vscode/extension.js` 0.4.0). The
  author, by voice: "is it possible to say like, hey, Cloud, clear the chat and you use the
  command slash clear", and on hearing how: "Oh yes, build it." No session can run `/clear`
  on itself; it has to be typed, and only the editor can type. Spoken words that are one of
  `clear_words` and nothing more (a greeting before, a "please" after and small words such
  as "the" or "your" count for nothing; "Claude" is also taken as "cloud", which is what the
  speech model writes) are not handed to the session: the hub gives the editor that holds
  its terminal the key `clear`, and the extension types Ctrl+C, and 150 ms later `/clear`
  with Enter. It knows these two by name, `escape` and `clear`, so the hub still cannot
  have anything else typed. Only for a session at its prompt, since that Enter would answer
  a dialog that is open: not while it is working, needs you, is being stopped or has a
  request open, and not while Claude Code's own session file says busy. Then, and with no
  editor that says it can (`"clear"` in `can`), the light shows the struck-out microphone
  with "Not cleared: it is still working" or "Not cleared: no editor to type it", and the
  words go nowhere. An order that falls between two requests of the editor waits for the
  next one (`_clear_wanted`), as for the jump key. Measured with a throwaway session in
  tmux, Claude Code 2.1.328: `/clear` and Enter written in one go clear the conversation;
  one Ctrl+C before it empties a half-typed line, at an empty prompt it only shows "Press
  Ctrl-C again to exit", and the `/clear` after it works in both cases. Tested with the
  real extension code, a stand-in editor and a real hub; `sidetone follow-up -s NAME
  "clear the chat"` goes the same way as the voice. **Not tried in the author's VS Code:
  0.4.0 is installed, and it runs 0.3.0 until "Restart Extension Host".** Said to a
  busy session (working, needs you, a request open, being stopped, or busy in Claude
  Code's own file), the order waits since the same night (the author: "queuing a command
  that asks to clear the chat, which is good"): the clock sign and the waiting notes, and
  `reconcile` types it within a second of the session being back at its prompt
  (`Talk._clear_when_done`, `_clear_after`). It is dropped without a sound by a prompt
  typed meanwhile or words said to that session after it, since clearing would throw
  those away; given up with "Not cleared: its turn ran too long" after `base.CLEAR_WAIT`
  (30 min). Not kept across a hub restart. The code went in under other
  sessions' commit messages (`b6c7626`, `a61c7ad`), which took it along.
  The author tried it the same night after restarting the extension host ("it looks like
  it cleared the chat") and asked for a sign that it got through, "either sound effect or
  just spoken". The two notes of "sent" only said the order went to the editor. Now the
  proof is Claude Code's own `SessionEnd` with `reason: "clear"` for that session
  (`Talk._cleared`; `/clear` ends the conversation and starts one with a new id in the
  same terminal): the two notes of "sent", or "Chat cleared." with `talk_feedback:
  voice`. No such end within `base.CLEAR_CONFIRM` (10 s): the struck-out microphone,
  "Not cleared: the chat is still there", and the low notes. Nothing sounds when the
  order goes out. A run of four notes for "cleared" was played to them first; their
  word: "keep a positive tune and a negative one", the positive being the one for sent.
  A clear that waited is typed by `reconcile`, maybe while you hold the talk key for
  another session, and its "sent" took the listening sign away, since the overlay shows
  one push-to-talk step (the author, 2026-11-19: "I don't see the registering icon
  anymore"; the recording went on and arrived). Late news of a clear (`late=True`,
  `_clear_late`) now leaves the overlay alone while `Talk._talk_held`.
- Words handed over do not take the bubble from a speaker (2026-11-19, `quiet` on the
  `talk` message, `hushed` in `UpdateBubble`). The author: while this session was speaking,
  "session one was done. His message popped out briefly and then your message continued.
  It was just visual stuff." What the log shows for that second: words of theirs had waited
  for session one, its turn ended while another session's line was being said, and the
  "sent" sign for the words handed over is a push-to-talk step, which always had the
  bubble before a sentence being said; so the bubble went to session one for 2.5 s and
  back. Now the hub marks that one step as `quiet` (it is the hub's news, not something
  you are doing), and the overlay then leaves the bubble with whoever is speaking and
  shows only the paper plane on the other light. Seen in a picture
  (`talk-handed-over-while-another-speaks.png`). **That this is what they saw is read from
  the log, not confirmed by them.**
  Minutes later the other half of it, from the author: "I want [it] to be more responsive,
  the pop-out of the detailed message whenever you are speaking": a session had its line
  ready while they talked to another one, "I sent the message and you started speaking
  without like the window popping out". The "sent" sign of their own words stays up for
  the 4 s they can be taken back, and for those seconds it had the bubble, so the speaker
  got it only after half its sentence. Now every step that only reports (`sent`, `queued`,
  `stopped`, `focus`) is sent `quiet` (`Talk._talk`) and gives way to a speaker at once;
  its sign stays on its own light, and the cancel key takes the words back as before. What
  you are doing (`listening`, `transcribing`, `ready`, `aside`) and what went wrong
  (`failed`) keep the bubble. `overlay.sent_first: true` is how it was. **Not seen by the
  author yet.**
- `hub/stale.py`: the hub takes a fingerprint of each of its own files as it starts (of
  what they hold, not their time of change, so a file that was only touched does not count),
  and the overlay does the same for its source when a window is started. `/state` carries
  `outdated` (`hub`: the files that differ now; `overlay`: true or false), and
  `sidetone status` turns it into a note with the command that applies the change. A
  file another session is still working on counts too, so the note is a reason to look, not
  an order to restart.
- `hub/claude_sessions.py`: reads `~/.claude/sessions/<pid>.json` (pid, sessionId, status
  busy/idle). `Hub.reconcile()` runs every second: idle there but working here means the turn
  was interrupted; a session that had a file and lost it is gone. Undocumented files, so
  sessions that never had one are left alone.
- Voices: `voices.json` remembers project → voice; own voices are `.npy` style arrays of shape
  (510, 1, 256) in `~/.local/share/sidetone/voices/`, passed to Kokoro as arrays.
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
  list with `sidetone say`, since the speak tag is only for the final message. The
  author: "I've noticed you've talked, but I didn't" see "the audio wave". The line
  belonged to no session (`[cli]` in `voice.log`), so no bubble, no bars, no wave.
  `bin/sidetone say` now sends `CLAUDE_CODE_SESSION_ID`, which Claude Code hands every
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
  anything yet.** `Ctrl+Alt+S` (`settings` under `hotkeys`) or `sidetone settings`
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
  at the top of the file is read back at start. `sidetone settings list` prints them
  all and `sidetone settings KEY VALUE` sets one, which is also how the live hub was
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
  The author's first look (same evening), three things, all done at once: (1) "make it
  not stand out in front of any other program. It should be hideable like any other
  programs because it's settings": it was always on top and had no place in the taskbar.
  Now an ordinary window (`Topmost` off, in the taskbar and Alt+Tab, a button to put it
  away beside the cross); the key shuts it only when it is in front of you and otherwise
  brings it there, which the window decides (`toggle` in the message, `InFront`), since
  the hub cannot know what lies over it. (2) "the menu ... a different background color
  to compare to the right": the sections stand on a darker ground over the whole height,
  with a hairline at its right. (3) "the label settings with claude-speaks to the right.
  I don't like [it] as a name ... just don't place it there ... maybe place it down left.
  Maybe there's a better name": "Settings" alone heads the menu and the name is small and
  faint at the bottom left. Whether the tool should have another name they left open
  ("maybe we can think about it"); names were offered, nothing renamed. Seen in pictures;
  **the putting away and coming forward are untried**.
  Second look: "that's better", then "instead of settings call it like [claude-speaks]
  or just, yeah, I just want a different name. And also, can you make a logo". So the
  tool's mark and name head the menu (`settings.NAME`, sent as `title`; one place to
  change when a name is chosen) and nothing is at the bottom left. The mark (`Logo` in
  `Overlay.cs`): a session's light while it speaks, a disc with white voice bars (five at
  first, three for a moment, five broader ones since), and around it the context arc, three quarters round, in the microphone's pink,
  which the author once called "the brand color". It is drawn by the overlay and kept
  nowhere as a picture: the window, its taskbar icon and `assets/logo.png` for the README
  (the `logo` message writes it) are the same drawing. The window's switches and sliders
  took that pink (they were the blue of "working"). **Not seen by the author yet.**
  The author then found that a click on its place in the taskbar brought the window up
  but a second click did not put it away: Windows only does that for a window that says
  it can be minimized, and a WPF window with `ResizeMode.NoResize` does not. It is
  `CanMinimize` now, with `WS_MINIMIZEBOX` and `WS_SYSMENU` set on the window (the size is
  unchanged, seen in a picture).
  Asked to try it, they did not see the window at all ("I don't see it open"): opened by
  the command and not by the key, Windows does not let it take the keyboard from the
  program in front, and since it is no longer always on top it came up behind that
  program. `Show` now puts it on top for an instant (`Topmost` on and off) before asking
  for the keyboard. They then saw it and tried the taskbar: "It works perfectly, thanks."
  Names: Earshot, Switchboard, Hark and Heard are all taken by tools for coding agents
  (found by searching, 2026-11-18), so they were not offered; Squelch, Sidetone and
  Tally were, as radio and studio words for what it does.
- `hub/demo.py`: three made-up sessions that go through every state (`sidetone demo`).
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/sidetone` (linked by `install.sh` into `~/.local/bin` as `sidetone` and `st`;
  on the author's machine since 2026-11-16): `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `allow`/`deny`, `answer N`, `missed`, `repeat`, `sound NAME`, `languages [CODES]`, `voices`, `voice …`, `target [PROJECT]`,
  `follow-up [-s PROJECT] TEXT`, `talk start|stop|cancel`,
  `overlay dots|list|toggle|restart|move|monitor N|corner NAME`, `terminal [tint focus|all|off | find [PROJECT] | show [PROJECT] | strength N | background COLOR | pulse on|off|N | title on|off | follow on|off]`, `vscode install|uninstall`,
  `settings [close | list | KEY VALUE]`, `demo`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 301 tests in all with a silent engine and fake microphone, including the real hook
  scripts over a socket and a hub process that is killed and restarted.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/sidetone/config.json` with `voices` (project name → voice),
  `voice_pool`, `colors`, `label` (`auto`/`always`/`never`), `titles` (`ask`/`auto`), `repeat` (`focus`/`last`), `max_age`, `idle_exit`, `default_voice`, `speed`,
  and `overlay` (`enabled`, `mode`, `monitor`, `corner`, `offset_x`, `offset_y`, `opacity`,
  `list_opacity`, `glass` (`blur`/`acrylic`/`none`), `flash_seconds`, `talk_sign` (`light`/`line`), `hotkeys`), `permission_grace`, `whisper_model`, `mic_source`, `followup_delay`, `unsend_seconds`,
  `talk_tail`, `talk_feedback`, `sound_volume`, `cancel_stops`, `clear_by_voice`, `clear_words`, `usage_shown`, `usage_every`, `usage_warn`, `usage_models`, `history_time`, `context_shown` (`arc`/`text`/`both`/`off`), `context_window`, `turn_tokens` (`new`/`output`/`all`/`off`), `turn_tokens_label`, `turn_tokens_history`, `separator`, `waiting_words`, `row_metrics`, `detail_metrics`, `aside`, `aside_words`, `aside_model`, `aside_timeout`, and `terminal` (`tint`, `strength`, `background`,
  `pulse`, `pulse_strength`, `title`, `follow`). `SIDETONE_OVERLAY=off` disables the overlay.
- `~/.local/state/sidetone/voices.json`: the voice each project was given, kept so it stays
  the same across hub restarts (a future settings panel would edit this and `config.json`).
- Toggle: voice is off while `~/.claude/voice-off` exists (the hub still tracks state).
- Runtime files live outside the repo: `~/.local/state/sidetone/` (`voice.log` contains
  spoken summaries, `hub.log`, `.state/`, `.tts.pid`).
- `hooks/settings-snippet.json`: the `hooks` block as registered in settings.json.
