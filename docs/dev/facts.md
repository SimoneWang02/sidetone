# Facts learned

Measured facts about Claude Code, Windows, WPF, sound, speech models and this machine. Moved here unchanged from `CLAUDE.md` on 2026-11-19.


- MessageDisplay holds each batch until the hook returns, so keep `display.sh` fast:
  about 5 ms with no tag, about 10 ms with one (one `curl` to the hub). Output
  `hookSpecificOutput.displayContent` to replace the shown text. The transcript keeps the original.
- `final` marks the last batch. Deltas are whole lines except possibly the final one.
- Stop input has `last_assistant_message`. The transcript can lag, so it's only a fallback.
- Only own-line tags are spoken, so inline mentions of the tag in prose are ignored.
- `displayContent` can add lines of its own (measured 2026-11-26, Claude Code 2.1.332, a haiku
  session in tmux): a line put before the batch with an empty line after it is shown as a
  paragraph of its own above the reply's first line, in a batch with a speak tag or without.
  Of words handed to a session by `listen.sh` the terminal itself shows "● Stop hook feedback"
  and nothing else; of words handed after a step (`additionalContext`) nothing at all.
- `display.sh` reading `lib.sh` before its fast path costs 0.8 ms a batch (4.75 ms to 5.55 ms,
  300 runs each, taken in turn, 2026-11-26; it is the `cd … && pwd` for `CS_ROOT`). Asking
  whether a folder holds a file (`compgen -G`) costs nothing that could be measured.
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
  `sidetone usage [say]` give the same. `Hub._count_context` runs on Stop, PostToolUse,
  UserPromptSubmit and SessionStart: `usage.context(transcript_path, context_window)` (the
  last main-chain assistant line's input plus both cache counts, or a newer compaction's
  `postTokens`; 2 ms) goes into `Session.context` and from there into the row
  (`context_shown`, see the next point). The window's size is a setting, one million as measured
  for the models tried; the transcript does not say it. Measured 2026-11-22: the reply of a
  turn that is one reply reaches the record about 0.3 s after its Stop, so the count at Stop
  found nothing (first turn: no arc) or the reply before; it is counted again with the turn's
  tokens, `RECOUNT` 1.5 s later.
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
  newer one. Lines also carry `kind`. That dot is off since 2026-11-19 (the author: "I
  don't like the tick with the white ball on top right ... don't use the white ball");
  `history_missed: true` brings it back. A `/clear` also takes that session's lines out of
  the history now, since the next chat in that terminal has the same name. With `history: all` (every session's lines mixed),
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
  `config.json` is kept), and `sidetone languages [CODES]` shows or changes it later.
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
  runs on the author's CPU (Core Ultra 7 270K, 24 threads, int8, on the CPU; the RTX 5070 was not used), model
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
- Exiting with work in the background (measured 2026-11-26, Claude Code 2.1.332, a throwaway
  session in tmux with `sleep 900` left running by the Bash tool): `/exit` does not exit. It
  shows "Background work is running", "The following will stop when you exit:", the list
  ("shell · Sleep 900 seconds in background") and "1. Exit and stop tasks", "2. Move to
  background and exit", "3. Stay", the first one chosen. Enter exits and the command is
  stopped (0.2 s); Escape is "Stay" and the prompt is back. No hook fires for it. Read in the
  program's own text, not tried: the list is every background task still running (commands,
  agents, monitors, scheduled tasks and loops), Ctrl+C or Ctrl+D twice ask the same, and in a
  worktree "Exiting worktree session" comes instead. The author's "sidetone 6", asked this
  the same day, had an artifact's comment watch armed in its transcript; what its list named
  was not seen.
- Session-file facts on 2.1.332 (measured 2026-11-26, the same session): `status` has two more
  values than the next note says. `shell`: at its prompt with a command of its own left
  running, where `idle` was. `waiting`, with `waitingFor` saying for what: `permission prompt`
  while a tool asks, `dialog open` for the /model picker and for the question before exiting
  above (there 0.3 s after /exit), and `shell` again when read a second after Escape. The
  hub takes only `idle` for "at its prompt" (`Talk._cannot_clear`, the interrupted turn in
  `reconcile`): not yet looked at for a session with a command left running.
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
- `sidetone hub stop` and `uninstall.sh` act on the hub of the current `XDG_RUNTIME_DIR`,
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
- Machine facts: an NVIDIA GeForce RTX 5070 with 12 GB (driver 617.14), which WSL sees
  (`/usr/lib/wsl/lib/nvidia-smi`, `/dev/dxg`); nothing in the project uses it yet. Notes
  here once said "no graphics card", meaning only that none was used; a session repeated it
  to the author as fact on 2026-11-19 and was corrected ("ho una 5070").
- Whisper on the RTX 5070 (2026-11-22): the author's 102 kept recordings (1.7 to 64 s,
  median 10 s; 94 English, 8 Italian) through the hub's own `stt.Transcriber` with
  `en,it,zh`, one after another so leaning worked as live. ctranslate2 4.9.0 sees the card
  (`get_cuda_device_count() == 1`) but needs cuBLAS 12 and cuDNN 9 on `LD_LIBRARY_PATH`;
  borrowed for the test from the voice-clone venv's `nvidia/cublas/lib` and `nvidia/cudnn/lib`
  (0.8 and 1.0 GB). Median time per recording, and for those under 4 s:
  `small` CPU int8 (what runs now) 0.81 s / 0.68 s; `small` GPU float16 0.17 / 0.08;
  `large-v3-turbo` GPU float16 0.18 / 0.13; `large-v3` GPU 0.40 / 0.23; `large-v3-turbo`
  CPU int8 2.93 / 2.85 (too slow to be the default without a card). Loading: turbo on the
  GPU 1.8 s once downloaded (the first download took 78 s; `large-v3` 102 s).
  All five agreed on the language of every recording (no short, unsure ones among them).
  The words: turbo and large-v3 differ from `small` in 10% of the words and from each other
  in 5%; by reading, both large ones are clearly better, mostly on short clips and Italian:
  "Yeah, uh, gone." / "Yeah, go on."; "Dero at the side by side." / "They are side by side";
  "è perfatto" / "perfetto"; "esvego" / "eseguo"; "attestare" / "addestrare"; "by coding" /
  "vibe coding". large-v3 punctuates long Italian better than turbo, at twice the time.
- Kokoro on the RTX 5070 (2026-11-22): the first sentence of the last 40 English lines the
  hub spoke (about 22 words, 7 s of speech), `af_heart`. Making it: CPU (onnxruntime 1.32,
  24 threads) median 0.78 s, at most 1.51 s; GPU (onnxruntime-gpu 1.22.0 in a test venv,
  `Kokoro.from_session` with the CUDA provider) median 0.13 s, at most 0.22 s. Only up to the
  first comma (about 5 words, 1.8 s of speech): CPU 0.20 s, GPU 0.06 s. `voice.log` showed
  `first_audio` 0.55 to 1.5 s for those lines, so making the sentence is nearly all of it.
  onnxruntime-gpu replaces onnxruntime (same module name; 433 MB) and needs, besides cuBLAS
  and cuDNN, NVIDIA's cudart 12, curand 10, cufft 11 and nvrtc 12 (`ldd` of
  `libonnxruntime_providers_cuda.so`); loaded by full path first, like Whisper's.
- Short answers on the RTX 5070 (2026-11-22): 43 clips said by the voices (10 Italian answers
  by Paola, Sara and Nicola; 5 English by two voices; 3 Chinese by Xiaoxiao), through the hub's
  `Transcriber` with `en,it,zh` and leaning on. `large-v3-turbo` on the card, after Italian:
  4 in the wrong language (two "Sì." of three, both Chinese one-character answers), 0.14 s
  each; after English: 12 ("Sì." as "See you", "Ok, continua." as "Ok, continue.", "Fallo."
  as English). `small` on the processor: 5 after Italian (all three "Sì.", and "Yes." taken
  for Italian), 15 after English, 0.70 s each. So the larger model fixes "Procedi" and most
  short Italian after Italian, but one syllable stays too short for either, and a short
  Italian answer right after English is still mostly heard as English.
- Claude's own dictation (2026-11-26, code.claude.com/docs/en/voice-dictation and
  claude.com/docs/office-agents/dictation): the sound goes to Anthropic's servers and a
  speech-to-text company under contract writes the words; neither the company nor the model is
  named. Only with a claude.ai sign-in (not an API key), free, not counted in `/usage`, and no
  public interface another program can call: the Claude API has no speech-to-text. The words
  appear while you speak. "Tuned for coding vocabulary", with the project's name and the git
  branch added as hints. One language at a time, the `language` setting, of 20: English and
  Italian are there, Chinese is not, and nothing switches by itself.
- Names as hints to Whisper (2026-11-26): the author's 407 kept recordings (90 minutes; 376
  English, 31 Italian) through the hub's `Transcriber`, `large-v3-turbo` on the card, with
  faster-whisper's `hotwords`. As it runs now: "Claude" written 12 times and "cloud" or
  "clawed" 14; "Sidetone" never, "side tone" 3 times. With `hotwords="Claude, Sidetone"`:
  Claude 19, cloud 7, Sidetone 4 (also from "scyton"), no time added (median 0.19 s), no
  recording's language changed, nothing invented. With 19 words (those two and Kokoro, Whisper,
  Piper, overlay, hub, hooks, hotkey, push-to-talk, GitHub, WSL, tmux, VS Code, Fable, Opus,
  Sonnet, Haiku): Claude 27, cloud 1, "five coding" became "Vibe coding", but 4 recordings
  got words nobody said ("Closed captioning by" twice, "Visual Studio Code" as "VSL Studio
  Code" twice) and "Client data?" became "Claude and Data". So a few names help and a long
  list harms. Either way 3.5 to 4.3% of all words change, mostly punctuation-like ("all
  right" / "alright", "eight" / "8"). `beam_size=5` in place of 1 fixed none of the names and
  took 0.24 s where 1 takes 0.20.
- What the kept recordings sound like, and where the model is unsure (2026-11-26, 417
  recordings, all from the desk microphone through WSLg's `RDPSource`, 44.1 kHz brought to
  16 kHz; the headphones in use have no microphone). Speech at -18 dB of full scale in nearly
  all of them (-20 to -17, so something upstream evens the level out), peaks at -5 dB, none
  clipped; the room's noise at -54 dB, so speech is 35 dB over it (22 dB in the worst
  twentieth); no dead gaps; sound up to 7 kHz, so not a telephone band. Speech starts within
  60 ms of the key in 18 recordings and they are heard no worse. Whisper's own probability for
  each word (`word_timestamps=True`, 10,285 words): the middle word 0.98, 6% under 0.5, 1.5%
  under 0.3, most of those "okay", "yeah", "like", "the". Unsure words (under 0.5) by length
  of recording: under 3 s 13%, 3 to 10 s 8%, 10 to 30 s 6%, over 30 s 5%; in the first tenth
  of a recording 13%, after it 5%; English 8%, Italian 6%; noisier recordings (under 28 dB)
  no worse than quiet ones. The wrong words are unsure ones: "side" of "side tone" 0.30 and
  "five" of "five coding" 0.23 (the lowest hundredth), "cloud" for "Claude" 0.59 (the lowest
  tenth, 38% of them under 0.5), where "the", "overlay" and "session" are at 0.96 to 0.98.
  A recording with little sound above 4 kHz is a short one with few s sounds, not another
  microphone (32 of them, median 2.8 s): that was first taken for a telephone band.
- Who says the lines (2026-11-26, `voice.log` since 2026-11-22, 506 lines): Heart 256 and
  Bella 80 (Kokoro's own grades A and A-), Emma 119 (B-), Paola 27, the rest 24. A line's
  first sound 0.12 s after it is asked for (median; 0.32 s for the slowest tenth). Kokoro's
  VOICES.md: "Weakness on short utterances, especially less than 10-20 tokens", which is what
  a session's label said by itself before its line is.
- Ours against ElevenLabs, by others' scores (2026-11-26, artificialanalysis.ai). Voices, by
  blind votes between two voices saying the same text (Elo, 106 models): Eleven v4 Turbo 1342
  and Eleven v4 1340 (first and second), Eleven v3 1194 (23rd), Turbo v2.5 1094, Multilingual
  v2 1091, Flash v2.5 1075 (58th), Kokoro 82M v1.0 1060 (69th). 280 points apart means the
  better one is picked 5 times in 6; 15 points apart, about evenly. Speech to text, words
  wrong in 100 on their own English test set (AA-WER): ElevenLabs Scribe v3 1.95 and Scribe v2
  2.18 (3.67 dollars per 1000 minutes), Whisper large-v3 4.07 to 4.53 by host, large-v3-turbo
  4.62 (Groq's). None of it is the author's voice, and none was measured here.
- Free speech-to-text models ahead of Whisper (2026-11-26, from write-ups found by a search,
  not the leaderboards' own pages, and none tried here). Hugging Face's Open ASR Leaderboard,
  average words wrong in 100: NVIDIA Nemotron 3.5 Transcribe 5.33 (first among free models, by
  apidog.com on 2026-10-29); Qwen3-ASR 1.7B 5.40, Cohere Transcribe 5.77, Granite Speech 4.1
  5.96, Parakeet TDT v2 6.02 (by pinggy.io, the board of 2026-10-09); Whisper large-v3 7.16,
  41st. Artificial Analysis puts Mistral's Voxtral Small first among free models at 2.8, on
  the test where Scribe v3 has 1.95 and turbo 4.62. By language: Qwen3-ASR 1.7B (Apache 2.0)
  has English, Italian and Chinese among 30 languages and 22 Chinese dialects, and its report
  (arxiv 2601.21337) says it was trained to use context given in the system prompt;
  `pip install qwen-asr`, `Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-1.7B",
  dtype=torch.bfloat16, device_map="cuda:0")`. Cohere Transcribe (2 billion parameters, 14
  languages with all three, the weights behind a form). Parakeet TDT 0.6B v3 has 25 European
  languages and no Chinese; Canary-Qwen 2.5B is English only. The card had 6.6 of its 12 GB in
  use with the hub running turbo.
- Kokoro, by its own card (huggingface.co/hexgrad/Kokoro-82M, read 2026-11-26): 82 million
  parameters, Apache 2.0, built on StyleTTS 2 and ISTFTNet, v1.0 on 2025-01-27, trained on "a
  few hundred hours of audio" for "about $1000 for 1000 hours of A100"; 8 languages, 54 voices.
- Free voices above Kokoro (2026-11-26, the same blind votes, the list of models whose weights
  are published; what each needs is from write-ups found by a search, not tried here): Fish
  Audio Drama 3 1278 (35 billion parameters, said to need a 48 GB card; free under 500,000
  dollars of revenue a year); Breeze TTS 2 1229 (English and Chinese, about 7.7 GB of card
  memory, 12 GB advised; weights for research and non-commercial use only); Ming-3.0-tts
  1181; Gradium's Phonon 31M 1108 (English only, Apache 2.0, a 64.5 MB file, on the
  processor, first sound in 7 ms by its maker's count, `pip install ptts`); Fish Audio S2 Pro
  1104; Step Audio EditX 1101; Mistral's Voxtral TTS 1094; NVIDIA's Magpie 1064; Kokoro 1060.
  Below it: Chatterbox 1021 (the author's ears said the same on 2026-11-19), XTTS v2 917.
  No time to first sound for Eleven v4 was found; "Eleven v4 Turbo" scores the same as v4.
- Phonon 31M tried here (2026-11-26; `ptts` 0.7.1 from PyPI, by Gradium, in
  `~/.cache/sidetone-voice-trials/2026-11-26/phonon-venv`, its 63 MB model under `hf/` there;
  on the processor only, 24 threads: `ptts.available_devices()` gives `cpu` alone). Loads in
  0.28 s once fetched (4.4 s the first time). First sound 0.03 to 0.07 s after the text
  (median 0.037 s, by `tts.stream`), a line made in 11% of its length. 37 English voices in
  its catalog (Harper, Hadley and Preston tried), no speed setting, 24 kHz, English only.
  Five lines the hub had spoken, by those three and by Heart at 1.1, are on a page with the
  voices under letters and every clip at one loudness (`index.html` there; the key: A Hadley,
  B Heart, C Harper, D Preston), opened for the author the same night. It does not copy a
  voice: `ptts` has `clone_voice` (from about 10 s at 24 kHz), but this model answers
  `supports_voice_cloning` with False.
- Ming-3.0-tts-0.5B tried here (2026-11-26, on the author's "Ok, prova Ming allora";
  github.com/inclusionAI/Ming-3.0-tts at c88c023 and huggingface.co/inclusionAI/Ming-3.0-tts-0.5B,
  MIT for code and weights by both pages; `ming-src`, `ming-venv` (7.3 GB) and `ming-0.5b`
  (2.8 GB) in `~/.cache/sidetone-voice-trials/2026-11-26/`; its pinned torch 2.6 replaced by
  2.8.0+cu128 for the RTX 5070, everything else as its requirements.txt, pynini from pip).
  On the card, in bfloat16: loads in 1.4 s, 2.85 GB of card memory, 44.1 kHz. A line takes
  about as long to make as to say: 82 to 93% of its length (5.6 s for 6.8 s of speech, 12.2 s
  for 14.3 s), at 14 to 16 steps a second; five words ("Done, both fixes are live.") 1.9 to
  2.3 s. Nothing comes out until a piece of up to 24 words is whole, so no first sound before
  about 2 to 6 s. Built-in voices by name (`task="IP"`, `controls={"ip": "US_Emma"}`; UK_George
  also tried). Languages by its card: Chinese, English, German, Spanish, French, Korean,
  Japanese; no Italian. The five lines by Emma, George and Heart are on `ming.html` there,
  the voices under numbers (the key: 1 Heart, 2 Emma, 3 George), opened for the author.
  Importing transformers once without `HF_HOME` set made it "migrate" the default Hugging
  Face cache (0 files moved).
- Breeze TTS 2 by its own card (huggingface.co/BreezeBlue/Breeze-TTS-2, read 2026-11-26): 3
  billion parameters, 7.7 GiB of card memory (14.4 on its fast path, a 24 GB card), no ready
  voices (one is described in words or copied from a recording), English and Chinese, run
  from its GitHub repository, speed given for an H100 only (0.32 of the speech's length,
  first sound under 40 ms). Not tried: 6.4 GB of the RTX 5070 was free with the hub on it.
- The voice read back by the speech model (2026-11-26): 80 lines the hub really spoke (2,800
  words), made by Kokoro at speed 1.1 and written down by `large-v3-turbo`. Words that differ:
  Heart 1.5%, Bella 1.0%, Emma 1.7% (as British, the way the hub asks), nearly all of them a
  number written in digits or "colour"; real ones about 1 word in 400 ("scores" as "score
  is", "ear" as "tier"), and "Sidetone" and "Claude" as "side tone" and "clawed" from our own
  voice too. Emma given American pronunciation by mistake said "got it" as "gartit" and "top"
  as "tarp": a British voice needs `en-gb`.
- How much is said (2026-11-26, `voice.log` and the kept recordings): the voice says 11,000 to
  42,000 characters on a working day (about 27,000), the author about 27 minutes.
- From the talk key to the reply's first sound (2026-11-22, the author's last 12 spoken
  messages to one session, both models on the RTX 5070): release delay 0.4 s (`talk_tail`);
  transcription 0.14 to 0.5 s; from the transcript (the kept recording's time, in ms) to Claude
  Code queueing it, 7 to 35 ms, so the listener's long poll costs nothing; queued to the turn
  starting, 10 to 20 ms; the turn to Claude's first written output, 1.0 to 18.8 s (the model,
  and nearly all of the wait); the spoken line to its first sound, about 70 ms. In the last
  0.6 s of the last 25 recordings the speech had nearly always ended before the key came up
  (1 to 3% of the peak); the key's click arrives 0.1 to 0.15 s after release (30 to 100% of the
  peak, one or two 50 ms chunks), then quiet, so stopping at the first quiet after the click
  would save only about 0.15 s of the 0.4.
- A Bluetooth headset sounds bad while we record if Windows' default microphone is the headset's
  own: opening it puts the headset in call mode (hands-free, 16 kHz mono here, against 48 kHz
  stereo). WSLg shows one microphone, `RDPSource`, so `mic_source` cannot pick another one.
  Measured 2026-11-24: default recording device (all three roles) the Bose hands-free, and with
  `parec` open `msrdc` held a capture session on it. Earlier that day the default was the Nuroum;
  what switched it is not known (nothing in `hub/`, `overlay/` or `tests/headset` sets a default).
  Pairing again made the Nuroum the default (calls: the Bose), and `msrdc` then recorded from it
  with nothing restarted.
  The Nuroum is the webcam (a Camera device of the same name), so it does not follow the author to
  another room. Read, not tried: over Bluetooth LE Audio, Windows (26100.4484 or later, and a
  driver that does it) can keep stereo with the microphone open ("Format when microphone is
  active", Microsoft). Bose's LE Audio is a beta in firmware 10.12.12 (What Hi-Fi: Android and
  Windows; ecoustics: Bose lists only Android; nothing found on its microphone over LE Audio).
  Tried the same day with LE Audio on in the Bose app (the author's word; firmware 10.12.14) and
  paired again: Windows now lists the headset's LE Audio services (184E, 1850, ...), but with the
  null driver (`UmPass`), no LE Audio driver was found running, and all its sound devices still
  come from the classic A2DP and hands-free drivers. So sound is not going over LE Audio here. Not
  known: whether Windows has the "Use LE Audio when available" switch on this PC, and whether a
  newer driver (now Realtek 18.4032.2510.901, USB 13D3:3616, board ASRock Z890-C) would do it.
  The pairing also renamed the headset in Windows from "Bose QC Ultra 2 HP" to "Leviathan" (same
  address), so anything that finds it by "Bose" in its name misses it.
  After that its microphone gave nothing (23:56 and twice after): `waveInOpen` succeeds in 0.74 s
  and no sound comes in 15 s, in the same test code that had recorded it 5 times out of 5 an hour
  earlier, and in `Headset.cs`. Why is not known; what changed between is LE Audio on in the Bose
  app and the new pairing.
  Paired again after the author was told to turn LE Audio off ("Done and connected"): the
  microphone opened in 0.66 s with sound and the call, 2026-11-25, 00:00.
- Machine facts: PowerShell 5.1 with WPF, stdin pipes from WSL into `powershell.exe` work,
  execution policy undefined (use `-ExecutionPolicy Bypass`), WSLg mic is `RDPSource`,
  `dev.tty.legacy_tiocsti=0` (no typing into a terminal from outside), tmux 3.6 installed.

- Scratches at the start of spoken lines through AirPods (2026-11-21): the voice was played with a
  50 ms buffer and no silence around it. The same line played with 50 ms, then with paplay's
  own buffer: "only the first one has scratches". Speech now plays as the short sounds do
  (`KokoroEngine.LATENCY_MS`, `LEAD` 0.1 s, `TAIL` 0.3 s of silence; see `sounds.py`). 150 ms
  still left "a bit of scratches"; now 300 ms.
  Not caused by a busy processor: still heard with the other jobs paused.
  The scratches that were left came from the loudness meter (2026-11-21): PulseAudio runs a sink
  with the smallest buffer any of its streams asks for, and a recorder of the sink's monitor
  counts. WSL's RDPSink gives at most 130 ms whatever the player asks (`pactl list sinks`:
  "configured 130000 usec" with `--latency-msec=300`); the meter's `parec` at 30 ms took it to
  "configured 30000 usec". The same line through paplay alone, and through Windows' own player,
  had no scratches for the author; the preview, with the meter, did. At 130 ms or more the
  meter leaves the sink at 130 (measured at 100: 100). Its recording then comes in bursts:
  four 40 ms pieces at once every 170 ms (at 30 ms: one or two every 50 to 60 ms).

- Words spoken after a Ctrl+C waited about five minutes (2026-11-21, "waiting for the session to
  stop" until the next reply ended). The hub had been restarted a minute before. Tried again
  with a throwaway session on the live hooks: interrupted mid-command with Esc, then spoken to;
  the words were "queued" and went out 10 s later (`reconcile` saw the session file go idle),
  and the session answered. So the delay came with the restart, a fault of working on the
  tool; no code for it.

- Time to make one sentence, per voice program (2026-11-21, the author's machine, the hub
  running beside it; median of 4, a short sentence of about 9 words and a long one of about 17):
  Kokoro Heart 0.39 and 0.74 s, Piper Lessac 0.26 and 0.27, Kokoro Sara 0.35 and 0.51, Piper
  Paola 0.30 and 0.36, Kokoro's Chinese model (zf_049) 0.49 and 0.61. Piper's lead grows with
  the sentence: in Italian it is 0.05 to 0.15 s, in English up to half a second. A first run of
  Heart's short sentence took 0.85 s, so single numbers are noisy. From `voice.log`
  (`first_audio`, previews only, the same sentence each): Kokoro English 377 ms (34), Italian
  236 ms (3), Chinese model 339 ms (5), Piper 296 ms (2).

## A failed request's hook, and the usage limit (2026-11-26, Claude Code 2.1.332)

From the night of 2026-11-26, when the author's sessions reached the usage limit at 01:53:
`voice.log` against each session's record and its agents' (`<session id>/subagents/*.jsonl`).

- `StopFailure` fires for a failed request of a subagent too, under the session's own
  `session_id`; there is no `SubagentStopFailure`. Measured: two lines were spoken at the
  second two agents met the limit (01:53:44 and 01:53:50) while the session's own record has
  no request and no error then. Read from the program, not seen in a payload: every hook's
  input is built by one function that adds `agent_id` and `agent_type` from the agent's
  context, as measured for PermissionRequest below; only a subagent "with delegated
  observation" is left out.
- Its fields: `error` (`rate_limit` here; the hook's matcher runs on it), `error_details`,
  `last_assistant_message`, which is the text Claude Code shows: "You've hit your monthly
  spend limit · raise it at https://claude.ai/settings/usage?... · your 5-hour limit resets
  4:20am (America/New_York)" (one wording seen). Its output and exit code are ignored.
- At the limit an agent's end still wakes its session ("<task-notification>", with a
  UserPromptSubmit), and the session's request fails in 0.3 s with the same error: 01:53:10.29
  the agent, 01:53:10.65 the session. Once Claude Code has written "Usage limit reached · set
  to continue automatically at 4:20am" a later agent's end is queued without a request. At
  the reset each session gets "Your claude.ai usage limit has reset. Continue the task you
  were working on..." and goes on by itself.
- An agent handing its work back reaches the session as "Another Claude session sent a
  message:" and then `<agent-message from="...">` (its record; `MDt` in the program, with "A
  peer session sent a message" beside it). Not measured: whether UserPromptSubmit's `prompt`
  has that opening or starts at the markup. `base.typed` takes neither for typed words.
- The program is one 400 MB file; a pattern with a long `.{300}` before it took `grep -a`
  over two minutes, `mmap` and `find` in Python a second.

## Subagents' permission prompts (measured 2026-11-22, Claude Code 2.1.330, a lab of haiku sessions)

- A subagent's PermissionRequest carries `agent_id` and `agent_type` (the session's own has
  neither); its Notification (`permission_prompt`) does not say which agent.
- For a subagent sent to the background, Claude Code shows its own dialog only once the
  PermissionRequest hook has returned: held by the hub for 9 s (`permission_grace`), the dialog
  came at 16 s after the prompt was typed; held with no end, it never came, and the agent's view
  showed it as still working. Its notification came 6, 15 and 36 s after the request, i.e. after
  the hub let go. So the hub can answer it only in those first seconds, and must let go for the
  terminal to show it.
- The main turn usually ends (Stop) while the background agent runs on, so a subagent's request
  can still be open when its session's turn ends.

## VS Code types late while its window is hidden (read from its logs, 2026-11-24)

`terminal.sendText` of an extension goes through the editor's window. The extension logged both
/clear sent at 23:57:29 and 23:57:40; Claude Code got both at 23:57:47.0. In those minutes that
window's `renderer.log` (`%APPDATA%\Code\logs`, window2) has the remote extension host responsive
and unresponsive once a minute, at second 46.95 and 50.9, from 23:35 on, and the agent host's
connection reopened at the same second: timers run once a minute, as Chromium does for a window
that has been hidden a while. So what is typed through it can wait up to a minute. Read from the
logs; not reproduced on purpose, and no Chromium switch against it tried.
