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
| MessageDisplay | `hooks/display.sh` | Runs per streamed batch. Sends a batch containing a speak tag to the hub, which queues the speech and returns the "🔊 …" rewrite. With `words_in_terminal`, also the first batch after words of yours, which the hub writes above it ("🎤 …") |
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
  A part Kokoro cannot say is left out and the rest of the line is said (2026-11-21, found in
  a bug pass): Kokoro raises `ValueError` for a sentence with no phonemes (`✓`, `-`, `` ` ``,
  a zero-width space, measured), and its Chinese model for one it cannot spell. Before, that
  error ended the speech thread, and the hub said nothing more until it was restarted. Any
  other error from an engine is now logged in `voice.log` as `failed` and the queue goes on.
  A voice that fails to load (a damaged model file, no memory for it) gives way to the first
  system voice installed (`tts.fallback_engine`: say, spd-say, espeak-ng), which says once "My
  main voice failed to load" and `hub.log` has the reason (2026-11-21, the author agreed). Before,
  the speech thread ended at start, and the hooks did not fall back because the hub was up.
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
  that from `config.json` like `titles`. Since 2026-11-20 (the author: "either dynamic, so
  depending on the input language, the output must match it ... or letting the user choose
  with a select") it can be any language with a voice: `reply_language: it` and so on, a
  dropdown in the window ("Match My Language", English, Italian, Chinese: the languages
  whose voices were chosen and heard, `settings.SUMMARY_LANGUAGES`; the author, the same hour:
  "we can just limit to Italian, English and Chinese ... add the rest in the future". The
  first label, "Same as Yours", they found unclear and offered "reactive to input");
  `base.fixed_language` reads it, "english" being the old name of `en`. The hook then asks
  for that language whatever was used, with its `lang` in the tag, and side questions are
  answered in it. The hub's own words ("Sent.", "I need your
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
  Languages as packs (2026-11-23, agreed from a second machine without Chinese: "for chinese
  i want to install it from settings no?"; "i dont need all 100 chinese voices"): a language is
  on or off, and on means installed. `hub/packs.py` fetches a pack from pinned versions
  (kokoro-onnx's release for the ONNX model, hexgrad/Kokoro-82M-v1.1-zh at one commit for
  `config.json` and the voices, rhasspy's for Piper and Paola), each file checked against its
  size and SHA-256 before it is moved in place (a cut download leaves nothing). Chinese is the
  325 MB model, `misaki-fork[zh]==0.9.6` (about 100 MB installed, through `uv`) and only the
  voices ticked, one `voices/<name>.pt` each (about 0.5 MB), read without PyTorch
  (`voice_from_pt`: the zip's `data/0` is the 510 x 256 floats; its pickle is never loaded)
  and written into `voices-v1.1-zh.bin` beside those already there; zf_049 and zm_056 fetched
  this way equal kokoro-onnx's own `voices-v1.1-zh.bin` to the last bit. 428 MB with the four
  default voices. Italian's two Kokoro voices are in the English model, so Italian is free;
  Paola is 63 MB plus the Piper program, 26 MB (`install_piper`). `sidetone languages en,zh`
  (and install.sh's question, which calls it) fetches first and saves the choice after, so a
  language whose pack did not come is not turned on; `--no-download` with `install.sh
  --no-models`. The running hub takes up a new Chinese at `/languages` (`reload_zh`).
  The languages that are on (`base.languages_on`: those push-to-talk listens for, plus
  `reply_language`; "auto" all) are the only ones spoken (the author: "people who doesnt have
  installed chinese, are not expecting chinese responses"). The voice reminder names them
  ("when its two-letter code is one of en, it, and in English otherwise"; English alone, "plain
  spoken English whatever language I used"). A line still tagged with a language that is off,
  or that has no voice here, is not read in another language's voice: `Hub._say_line` says
  "Answered in Chinese, which is not installed." (or "..., which has no voice here." for
  German), and the written reply has the line; the author: "yes that works for me". Kokoro
  1.0's espeak Chinese voices are no longer used (`_voices_of`). An engine with no `has` (the
  silent one) says every line as before.
  In the settings window (the same day): a language not installed has a dim heading with
  "Not installed, 428 MB" and an Install button where its switch is (a round and a square download icon were tried the same day; the author kept the word) (`PackHead` in
  `Overlay.cs`; `_pack_heading`, `install` in `settings.py`); the hub installs in a thread and
  draws the window again at most about three times a second, the heading showing "141 MB of 428
  MB" beside a bar (the part coming, "Chinese model", was before it; the author: not necessary); a failure shows why, in a soft red, and Try Again. Done, the
  language is turned on (installed means on) and the engine reads its voices again. Once
  installed, its card lists, after the ticked voices, the clearest not downloaded yet
  (`fetchable`) with "0.5 MB" in their tag and no ▶; ticking one fetches it (its tag counts
  the percent) and ticks it once it is there. Under the card, "Remove Chinese" with what it
  frees, asking first as Reset does ("Click Again to Remove"); the package stays. Turning
  Chinese on without its pack is refused. The author installed Chinese this way on the second
  machine the same evening (hub.log: "installed zh" at 20:02). Then Italian's switch lagged
  ("why toggling on and off italian there's a lag"): every change of languages called
  `reload_zh`, which dropped the Chinese model and waited for its lock while the model was
  loading (several seconds, the first time after the install), so the clicks waited and came
  in all at once. `reload_zh` now keeps the model, without waiting, when the voices are the
  same, and `_zh_pcm` holds the model it loaded, so a reload meanwhile no longer breaks a line
  being made (it broke the timing of zh:zf_049: "'NoneType' object has no attribute 'create'").
  Then, agreed as a whole ("do all"): (1) a voice can be heard before it is downloaded. Each
  voice the window can list before its download (the four Install brings, the clearest after
  them up to `MOST_VOICES`, and Paola) says the window's sample sentence at the default speed
  in a small Ogg file in `hub/samples/` (13 files, 220 KB; made by `tests/record_samples.py`,
  which fetches what is missing into a folder of its own). They are read and written with
  libsndfile through ctypes (`hub/sndfile.py`), which paplay already needs, so no package is
  added. `KokoroEngine` speaks a `sample:<voice>` by playing the recording once;
  `settings.preview` uses it while the voice is not here, and ▶ shows its square as for any
  voice. A language not installed opens like the others: its voices with ▶, the four Install
  brings tagged "Comes with it", and no switches (`_listen_only`; `switch: false` in
  `Overlay.cs`). (2) The summary language lists only languages installed (and the one chosen,
  if it is not), choosing one that is not is refused, and Remove puts "Match My Language"
  back if Chinese was chosen. (3) Remove shows under the heading of a language that is
  installed but off (`always`), as it has no card then. Recording Paola found that
  rhasspy/piper-voices' main branch now writes phonemes of two letters ("aɪ") that Piper
  2023.11.14-2 refuses ("Phonemes must be one codepoint"), so she said nothing: her files now
  come from its tag v1.0.0. Pictures: `settings-pack-listen.png`, `settings-pack-off.png`. Pictures: `settings-pack-missing.png`,
  `-installing`, `-failed`, `-installed`, `-remove` (`tests/overlay_check.py
  --only=settings-pack`).
  A line with no `lang` (2026-11-22, `language.guess`, called from `Hub._voice_for` with the
  line itself). Seen 2026-11-19: a session answered in Italian without the mark, and the
  English voice read it. The author, offered it as the next thing: "just proceed"; asked
  whether it should be a setting, they left it to Claude, who chose none: it only fills in a
  missing mark, a mark is never second-guessed (`lang="en"` stays English), and
  `reply_language: english` still keeps every line in the session's own voice. Chinese,
  Japanese and Hindi by their script (two characters at least); Italian, Spanish, French and
  Portuguese by their small everyday words and letters (è, ñ, ã...), words shared with
  English left out. Only the Latin-letter languages named in `whisper_language` are weighed
  when one is (Italian is then never taken for Spanish); all four otherwise. Sure enough means
  two signs at least, twice the English ones and more than the next language; anything less
  stays English, so "Fatto." alone is read by the English voice. Each guess is written to
  `hub.log` ("a line with no lang, guessed it"). Not from the language Whisper heard last:
  Whisper is the part that already goes wrong. Side answers are guessed too when Whisper gave
  no language.
- Recordings kept (`keep_recordings`, "Keep My Recordings" under Talking; off for new installs,
  on for the author). 2026-11-22, the author: "register every message I send and create a voice
  model based on my messages, my speaking". `Hub._keep_recording` writes each recording that was
  heard as something (also one cancelled afterwards) to `<state>/recordings/` as a 16 kHz mono
  WAV, and a line to `list.jsonl`: file, text, language, seconds, time, Whisper model, project.
  About 32 KB a second. The folder is owner-only. `sidetone recordings` counts them.
- Short recordings lean to the last language (`whisper_lean`, on; 2026-11-19, the author:
  "you can fix this issue, just let me know [the] downside [and] upside"). Four of their
  short Italian recordings in a row had come back as English or Chinese. Measured on 18
  short clips said by the voices (Paola, af_heart, zh_001), `small` with `en,it,zh`: the
  wrong guesses were "Sì" and "Va bene, vai" taken for English at 0.65 sure; every English
  and Chinese clip was 0.97 or more. Writing each clip in its two likeliest languages and
  keeping the better score alone did not work (scores within 0.02, and English clips lost
  to Chinese). What is built (`stt.Transcriber`): when a recording is under 4 s, the model
  is under 0.9 sure, and its guess is not the language last heard for sure, it is also
  written in that language and kept so unless the guess scores better by more than 0.1
  (mean log-probability per token). Same clips, last language Italian: 0 of 18 wrong (2
  before); last English: 3 (2 before; "Quant'è il contesto" kept English, its words almost
  the same); last Chinese: 2 (as before). The second writing costs about 0.6 s, only for
  unsure short clips. The log line says "(leaned to it ...)" when it happens.
- Mixed languages in one message (2026-11-22, `whisper_mixed`, on; "Mixed Languages" in the
  window; `stt.runs`, `Transcriber._runs`). The author's first try, Italian then English then
  Chinese in 16.5 s, came back as English only ("Well, I'm going to try English as well ...")
  at 0.66 sure: Whisper takes one language per half minute and dropped or translated the
  rest. The author on building it: "sure, go on". Now, when a recording is 4 s or longer and
  the model is under 0.9 sure of its language, the voice filter cuts it at pauses of 0.3 s,
  the language of every stretch is found in one batched pass, a stretch under 1 s or under
  0.6 sure goes with the one before it, and if two or more languages remain each run is
  written in its own and the parts joined; `heard` is the language with the most speech. The
  same recording then gave "Va bene, io inizierò a parlare in italiano da qui. and then I'll
  try English as well. I hope it doesn't have any conflict. 中文的话我觉得看一下吧 看一下怎么样",
  in 1.2 s on the card (0.2 s without). Of the author's 113 kept recordings, 4 of the long
  ones were unsure and only the mixed one was split. Checking every recording instead cost
  0.34 s each (every stretch is padded to Whisper's 30 s), so it waits for an unsure one. A
  switch in the middle of a sentence with no pause still comes out in one language. The log
  line says "(mixed: it, en, zh)".
  Tuned the same hour on the author's next two tries: "试一下吧" at the end (0.9 s, 0.90 Chinese)
  was under the 1 s floor and became Italian, and a message that began in Italian the model
  took for Hungarian (0.86) stayed all English. Each stretch is now weighed among the named
  languages alone, at 0.7 and 0.75 s: on the per-stretch likelihoods of all 78 kept recordings
  with pauses this splits the three mixed ones and none of the others it would look at (0.6
  also split "Aspetta, fammi sentire side by side, ..." and wrote its Italian as English).
  The three now: it/en/zh, en/it/zh, and en/zh ("Ah, it was too short. I said in Chinese.
  试一下吧 就看一下怎么样 试一下吧": its Italian opening still came out in English).
- Push-to-talk on the graphics card (2026-11-22, `whisper_device`: auto, cpu, gpu, "Transcribe
  On" in the window; `whisper_gpu_model`, `large-v3-turbo`, config.json only, like
  `whisper_model`). Measured first on the author's 102 kept recordings (`docs/dev/facts.md`):
  turbo on the RTX 5070 takes 0.18 s where `small` on the processor takes 0.81 s, and gets
  clearly more words right. The author: "Sure proceed", and on whether it is worth it for
  others, "for me, yes"; offered as an install-time question only where a card is found,
  since it costs about 3.4 GB of downloads. `stt.gpu_ready` says why not (no card, no
  libraries, one that would not load); `Transcriber.load` then falls back to `whisper_model`
  on the processor, and also when the card fails to take the model (out of memory). NVIDIA's
  cuBLAS 12 and cuDNN 9 come from their pip packages (`stt.GPU_PACKAGES`, the versions the
  voice clone already runs with) and are loaded by full path, shared, before the model goes
  on the card (`ctypes.CDLL(..., RTLD_GLOBAL)`, retried in rounds since one needs another);
  ctranslate2 opens them by name only then, so no `LD_LIBRARY_PATH`. Measured that way: 2.0 s
  for the first recording with loading, 0.17 s after. `install.sh` asks where `nvidia-smi`
  names a card (`--gpu`, `--no-gpu`), keeps an earlier yes, and fetches the model. The hub
  logs "talk: speech model large-v3-turbo on the graphics card" (or the processor, and why)
  once each time it changes; `list.jsonl` names the model each recording was heard with.
  Choosing it in the window unloads the model, which loads where it now belongs at the next
  press of the talk key.
- Overlay size (2026-11-22, `overlay.size`, percent, 100; "Size" in the Overlay section, 75 to
  150 in steps of 5). The author, told Windows' display scale already sizes it: "we could let
  the user pick ... You decide"; a percentage like Windows' own. `Glass.Zoom` puts a
  `ScaleTransform` as the `LayoutTransform` of each window's content (bar, details, bubble,
  mute mark; their one-pixel edge stays), and the details and bubble are as much wider.
  What turns the mouse into places along the bar divides by it (`AlongBar`, the press that
  starts a drag), and the placing beside the bar uses the windows' own widths and the scaled
  mute mark. The settings window is not changed by it. Pictures at 75 and 150
  (`tests/overlay_check.py --only=size`): closed, open and speaking, rows level with their
  lights and the bubble with the speaker. The mouse over the bar at another size is not
  checked from WSL.
  It follows the slider while it is dragged (`SettingsWindow.Previewing`, as the glass slider
  does; the author: "I'm wanting it to be more responsive"), and is saved when it is let go.
- Reduce Motion (2026-11-22, `overlay.still`, off; "Reduce Motion" in the Overlay section;
  the author, offered it with an overall size as the first of "more of the overlay as a
  setting": "Oh yes"). The overlay already had `still` for the pictures of
  `tests/overlay_check.py` (`Ui.Motionless`): the panel and bubble take their height at once,
  rows and the bubble show without sliding in, the gauge, the waiting mark and the glide do
  not move, and "Release to send" does not glint. The live voice levels still move. It is
  also on while Windows' "Animation effects" are off (`SystemParameters.ClientAreaAnimation`,
  read when the settings come). Seen in the settings window's picture.
- Three fixes from the review of the overlay (2026-11-25, `docs/dev/overlay-review.md`: the
  author chose to improve today's overlay over the 50 designs, and of a drawn preview of the
  three said "all three steps look good"). Compiled and in the unit tests, no pictures. Live
  on the author's screen since the 26th: the tick seen and turned off (below), nothing said
  yet of the working light, the third **not seen by anyone yet**.
  - Working Light (`overlay.working_motion`, calm or lively; in the Overlay section for a
    day, then only in `config.json`: the author, 2026-11-26, "I don't think is needed ...
    just put a single spinning speed", and calm stays). The review found the working arc at 0.73 turns a second beside the
    pulse of "needs you" at 0.72: the commonest state and the urgent one at one tempo. Calm:
    one turn in 5 s, the arc of one length (1.6 rad), the dot at rest (`Ui.WorkingCalm`, in
    `Orb.OnRender`). Lively is the motion it had. The frames still run while a session works.
  - Session Color on the Bar (`overlay.session_tick`, off). On for one day: the author,
    2026-11-26, with it live, by voice: "at the right side right now of each bowl [light]
    there's a bar displaying the color of this session. Like visually I don't like it
    much", and yes to off for a new install. Why it looked wrong: two colors on every light, the state's and the session's,
    and the first two sessions' colors (`#8AB4FF`, `#FFA24D`) are nearly those of "working"
    and "needs you", so the tick read as a second state; and it is there all the time for
    a bar that is closed and calm, since the details come out with every name whenever a
    session needs you. Kept as a setting. What it was for: a closed bar says what each
    session is doing and not which session it is. `Row.Tick`: 3 by 18 px in the session's
    color, 2 px inside the bar's edge on the side the details come out (1 px clear of the
    frame round the light in focus), in the bar layout only; the island keeps its dash
    (`Pip`). It is the color of the name in the details and of the terminal's tint. Not drawn
    and not built: a name beside a light that needs you, because the details are out with
    every name while a request waits (`IsOpen`).
  - Every light on the screen (`Fit`, no setting: a bar that runs off the screen is a fault,
    not a taste; the author: "if the size goes over the monitor size, yeah, they should
    shrink"). The author doubted anyone opens twenty sessions and asked whether to limit
    them; not limited, since the overlay does not open sessions and could only hide one that
    needs you. `zoom` is now the size in use: `overlay.size` (`asked`), or as much less as it
    takes for the lights (44 px each and 8 for the edge) to fit the room from the bar's
    place to the end of the screen (the width, for the island), never under 40 %. Checked at
    each `Render`. The details and the bubble shrink with the bar, so rows stay level with
    their lights; their words get smaller too, which at twenty sessions on a 768 px screen
    (63 %) is small. Beside a bar the room also holds the card of the details (`CardRoom`,
    104 units; the card and what is round it measured 102): the first pictures (2026-11-26,
    `many-*` in `tests/overlay_check.py`: twenty sessions in the 620 units a 768 px laptop
    has, and an island of 63 lights on a screen 2560 wide) had every light on the screen,
    but the details with their card were 70 px taller than the bar that filled the room,
    so they were pushed along it and every name stood two lights from its own. With the
    card's room the details end 0 px from the bar's end. Not covered: a request or the
    history, which can be taller than the card and push the rows the same way, as beside
    any bar near the screen's end. With the default place and a 48 px taskbar nothing
    changes up to 18 sessions on a 1080p screen at 100 %, 13 at 125 %, 10 at 150 %, 11 on a
    768 px laptop (measured there: 11 at 100 %, 12 at 97 %, 20 at 63 %), 27 on the author's
    own (1440 px high, no taskbar). Seen in pictures only: no screen has held that many
    real sessions.
- Character (`overlay.character`: none, familiars, operators; none by default) and Character
  Place (`overlay.character_place`: edge, inside), in the Overlay section (2026-11-25). A small
  pixel-art figure with the bubble that acts what its session is doing. Where it came from:
  the 50-design prompt (`docs/dev/overlay-redesign-prompt.md`), then plushies ("very AI
  generated"), an aquarium (lovely large, "incredibly small" as an overlay), twelve sketched
  alternatives ("I like none of them"), six looks for the bubble, and the author's taste
  ("I love pixel art ... I play a lot of games"); of the last previews, "all three of them are
  pretty good. So we can just put them as selection by the user ... You can build them". The
  previews are in `docs/dev/looks/` (`characters.html` is the one built from).
  - Familiars: five creatures, each with a temper and its own acting (a calm lantern whose
    flame flares with the voice, an excitable ember, a sleepy sprout, a shy shellback that
    hides in its shell when its session fails, a grumpy toadstool). Operators: five people on
    the line, each with their own headset and something of their own (hoodie with cat ears, a
    pendant, a bandana, earbuds and a beard, an aerial and a scarf). The third look shown, a
    pencil sketch, is not built.
  - `hub/characters.py` draws them, ported from the previews' JavaScript: shapes filled in
    flat bands of tone on a 40 by 40 grid, a contact shadow where a part lies on another, an
    outline in the part's darkest tone, then single pixels. Each session gets a sheet: one
    row of 40 px cells for each moment (idle 4 s, working 2, speaking at four
    loudnesses 1 s each, needs 5 then 1 repeated, done 4 then 1, failed 2, listening 2; 12
    frames a second since 2026-11-26, 8 at first, the author: "could we put more FPS?";
    `LAYOUT`), as a PNG. Its figure follows its color (`kind_of`), so a project
    keeps its own. Measured at 12 frames a second: 0.52 s for a familiar's sheet, 1.27 s for an
    operator's, 35 to 42 kB (2400 by 480 px), drawn once in a thread (`Sheets`) and kept beside the overlay's program in
    `%LOCALAPPDATA%\sidetone\characters`, named by the drawing's own version.
  - The hub sends each row's sheet (`sprite`, "" while it is drawn) and the layout
    (`sprite_layout`) with the state. The overlay (`Sprite`) only crops a cell: the bubble's
    session's moment (listening if you are talking to it, speaking, else its state), the time
    since that moment began, and while it speaks the loudness of its voice for the row.  It
    does not jump when the moment or the session changes: it did at first (rising from below
    the edge, then 4 of its pixels up and down in a third of a second), and the author,
    2026-11-26: "the animation seems cut when jumping", then "I don't think they should be
    jumpy whenever I switch session ... their body is cut off from the bottom side"). Nor when
    done ("when they're done, they're jumping"): they raise their arms and smile, feet down.
    When another session's figure takes the same place in the same moment, it shows that
    moment's repeating part, not its start (needs you waving, done cheering). The
    cells are 44 px with the 40 px drawing 4 rows down (`OFF`), so raised leaves and hair are
    not cut flat at the top. Edge: in a window
    of its own (`perch`, see-through, click-through, no blur) on the bubble's top edge, at
    its end away from the bar, 80 px; the bubble keeps its size ("On the edge is cool").
    Inside: 60 px in the bubble beside the words, which grows 50 px wider and no taller
    ("decrease the size to make them fit").
  - Character in the Details (`overlay.character_details`, on; 2026-11-26). The first build
    showed nothing for the author, whose details are always out ("most of the time I put the
    details always as seen ... show selected session, which is the one that I use mostly"),
    and the bubble only comes with the details away. Now with the details out too: in Selected
    Session the shown session's character stands on the details' top edge (edge) or sits
    48 px in its row (inside); in All Sessions each row has one, 32 px, beside its words. Idle
    and working ones hold their first frame, so only a session with news moves (`UpdateSprite`).
  - Seen in pictures (`overlay_check.py --only=character`): both kinds, both places,
    speaking, needs you, done, failed; Selected Session on the edge and inside, All Sessions.
    Not in the request card yet, and Reduce Motion holds the first frame.
    It counts lights of the usual height: rows grown by `row_lines` 2 or 3 can still pass
    the screen.
  - Both settings have their new-install values built into the window, so an overlay
    started by a hub from before them shows the new look; the settings window lists them
    once the hub is restarted.
- The terminal tint on a light theme (2026-11-22, `terminal.light_background`, `#F8F8F8`,
  VS Code's Light Modern; the author, offered it: "Yes, so you're basically [doing] light mode
  and dark mode, right?"). The extension (0.6.0) sends `theme: "light" | "dark"` with each
  `/editor` request, from `activeColorTheme.kind` (Light and HighContrastLight are light), and
  asks again when the theme changes (`onDidChangeActiveColorTheme`). `Hub.editor_waits` keeps
  that window's terminals in `Terminals.light`, and `Terminals.background(tty)` mixes the color
  and the pulse into the light background for them. An older extension sends no theme and
  changes nothing. VS Code has no way to read a theme's actual colors, so a theme whose
  terminal is neither of the two defaults needs them set. Checked with the real extension and
  a stand-in editor: light, then dark after the theme changed. Not seen on a light theme by
  the author (they use a dark one).
- The voice on the graphics card (2026-11-22, `voice_device`: auto, cpu, gpu, "Voice Made On"
  in the Speech section). The author asked what else could cut the time from talking to
  hearing ("parlare, ricezione, processare ... sono il core"); of the steps, the start of
  the voice was the largest left in our hands (`first_audio` 0.55 to 1.5 s), and they said
  "Yes, proceed". Measured: the first sentence of a line 0.78 s on the processor, 0.12 s on
  the card (`docs/dev/facts.md`). `KokoroEngine._session` makes each onnxruntime session (the
  main model and the Chinese one) with the CUDA provider when onnxruntime-gpu is installed and
  NVIDIA's libraries load (`gpu.load(gpu.VOICE_PARTS)`), checks that the card's provider
  really started, and otherwise uses the processor, keeping why in `why_not_gpu`; `hub.log`
  says "the voice is made on the graphics card" (or the processor, and why) after each load.
  Piper's voices stay on the processor (their own program). The window's choice moves it at
  once (`set_device`, about a second, in a thread). `hub/gpu.py` holds what Whisper and the
  voice share: the packages, pinned, and loading the libraries by full path. onnxruntime-gpu
  1.26.0 is its last release for CUDA 12 (1.27 on link `libcudart.so.13`); it is the same
  module as onnxruntime, which kokoro-onnx and faster-whisper pull in again at every install,
  so `install.sh` uninstalls that one and reinstalls onnxruntime-gpu only
  (`--reinstall-package`), tried in a scratch venv. faster-whisper's silence filter asks for
  the processor itself, so it is unchanged. Loading on the card takes longer at the hub's
  start (6.8 s with the Chinese model, in the background).
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
  By the details too (2026-11-19, `overlay.panel_drag`, on; `PressPanel`): with the details
  kept out (the list key), "I should be able to move the entire overlay"; only the narrow bar
  could be grabbed, and the panel let every click through to what was behind it. Now the
  panel catches the mouse while the cursor is on it in list mode; a drag moves the bar and
  the panel goes along (`PlaceSides` each step, no folding), a click without a move is passed
  through as for the bar (`PassClick`). It never puts a light elsewhere.
  The same evening: "I cannot move the layout right now". A press starts the drag, and the
  frames follow it (`DragStep`), but nothing started the frames: with the overlay still they
  had stopped, the drag was left begun, and every press after it was ignored (`Press` returns
  while dragging). The bar's presses were saved by the frames that the mouse over a light
  starts; the panel's were not. Both now start them (`Run(true)`).
- The history following the mouse without lag (2026-11-19, the author: "if I move it real
  fast, there's a latency, there's a lag"). Measured with the mouse's stand-in going from row
  to row every 60 ms in list mode: a full redraw takes 4 to 8 ms, but every new history has
  another height, and the panel went there with the spring it opens with (about half a
  second), at about 10 ms a frame for resizing the glass window; it never caught up and what
  was below its height stayed cut off. A quick spring of about 60 ms was "better, but ...
  I want it to be more responsive", so a panel already fully open now takes a new height at
  once (`Glass.settled`); opening keeps the soft spring. "It's super responsive." Asked
  whether a faster animation is the standard instead: under a tenth of a second reads as at
  once, and the animation must not hold the words back. So `overlay.resize`: quick (the
  default, "Sure, yes") grows at once and shrinks in about 90 ms, easing from wherever it is;
  instant does both at once.
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
- The details as a zoom of three views (2026-11-22, `overlay.mode`: `dots` Bar Only, `list` All
  Sessions, `focus` Selected Session; `Listed`, `Chosen`, `Ui.OnlyFocus` in `Overlay.cs`): the
  details key goes through them in that order and round again. All Sessions keeps every row to
  one line; Selected Session shows the card and only the row of the card's session (the session
  in focus; the mouse on another light shows that one only while it stays on the light or the
  card, then the card goes back, the author 2026-11-22: "when I unhover from them, it should
  re-display the current" session), its sentence in full (up to ten lines), the other rows left
  out and the lights at their own spacing. Lines Per Session left the window. The author: "first
  only bar, second one row per each detail box, third only one detail box with all the rows of
  the summary". Tried and not liked the same night: rows that grow with a long sentence (they
  push the lights apart), every row as tall as three lines, the chosen session in a bubble, the
  other rows kept as empty places, and a long sentence floating over the rows below as a card.
  Picture `focus-only.png`.
- How see-through the glass is (2026-11-21, `overlay.glass_clear`, 50; `Ui.GlassClear`,
  `Ui.GlassFill`): one slider from 0 to 100 % instead of Blur or Plain (`overlay.glass`, still
  read; "none" stays plain). 0 is plain dark glass with no blur (a tint of 92 %); above it the
  blur is on and the tint over it goes from 92 % down, 55 to 65 % at 50 (the look it always had),
  20 to 30 % at 100. The author: "both are glass-like. Do you think we could do percentage like
  from 0 to 100? It's like basically opacity". Opacity at Rest left the window the same day,
  its default 100 %. The glass follows the slider while it moves (`SettingsWindow.Previewing`;
  the hub is told on release); the author: "it updates only on release. Can you make it more
  responsive".
- The status lights' colors and the glass's color (2026-11-23, while the author was away, from
  "Make more of the overlay a setting" in `TODO.md`): `overlay.working_color`, `needs_you_color`,
  `done_color`, `failed_color`, `idle_color` (`Ui.Working` ... `Ui.Idle`, `Ui.Amber` for needs
  you, `Ui.SetStateColors`), the defaults the colors they always had. needs_you's color is also
  `Ui.AmberEdge`: a request's edge, its "▲", the numbers of its choices and its keys. Each state
  keeps its own shape, so a light still reads without color vision. `overlay.glass_color`: ""
  is the dark slate (#3A4150 at the top of the blurred glass); a color of your own takes the
  top, and the bottom and the solid glass are made from it in the slate's proportions
  (`Ui.GlassFill`; 0.32 of it at the bottom, 0.74 and 0.35 for solid), so "#3A4150" looks as
  "" does. Pictures `own-colors*.png` (violet, orange-red, cyan, pink, grey on plum glass); a
  test checks every `*_color` default is a color and is read by `Overlay.cs`.
  In the settings window the same day, section Colors (after Overlay): the five lights, Glass and
  Microphone (`mic_color`). The author asked where the colors could be found (only in
  `config.json`, so nobody would), then chose "swatches + hex" over themes only and a color
  wheel. Kind `color` (`settings.color`, `SettingsWindow.ColorBox`): a dot of the color and its
  code, typed over in place (Enter or a click elsewhere takes it, Esc puts it back; typed in the
  window rather than in the list so the keys go where the window's keys go); a click on the dot
  or the arrow drops down nine ready colors (`LIGHT_SWATCHES`, `GLASS_SWATCHES`, the setting's own
  default first), a color wheel in the tenth place, and Reset when it is not the default. The
  wheel (2026-11-24; the author asked whether a picker would be better, then: "remove one and
  make it a color picker icon") swaps the ready colors for a picker of any color by eye
  (`ColorPlane`): a square of the hue's shades (white to full color across, to black down) and
  a bar of hues under it, 144 units wide like the row of dots. A drag shows the color at once in
  the box's dot and code and on the overlay (`SettingsWindow.PreviewingColor`, as the Size slider
  does); it is chosen when the list shuts (a click elsewhere), and the list opens on the ready
  colors again next time. Picture `settings-colors-picker.png` (`click_list`, a click inside the
  open list). A drag is not tried by a test: a made-up click has no place. The glass's "" is drawn as the slate,
  its code faint. The waiting mark's and the context arc's colors and the session palette are
  still only in `config.json`. Pictures `settings-colors.png`, `settings-colors-open.png` (the
  open list is reported with the settings window's place, `SettingsWindow.ListArea`). A swatch
  clicked and a code typed are not tried by a test: the check's clicks reach only the window.
  **Not seen or tried by the author yet.**
- What a clear looks and sounds like (2026-11-21): no "sent" sign and no "sent" sound, which are
  for words that went to a session; its own sound once Claude Code has ended the conversation, a
  quick run down four notes (`sounds.TONES["cleared"]`); and the light stays through it with its
  context at 0 (`Sessions.stand_in`, a `standin` Session named "cleared:<id>" in its place for up
  to `HEIR_WITHIN`), so the overlay's arc winds back to nothing and the session Claude Code starts
  after it takes the same light, its context at 0 too. The author: "I don't think I should see
  and hear the sound and the icon of sending a message ... I want the animation of the arc of
  the context to go to reset to zero, because it's cool animation".
- The clear key (2026-11-21, `clear` Ctrl+Alt+C, `Hub.clear_key`, `CLEAR_TWICE` 3 s): pressed
  once it asks in a banner like the mute key's, "Clear sidetone?" (first "Clear the chat of sidetone?", shortened at the author's asking) with "Ctrl+Alt+C to
  confirm" beside it and a bin (Segoe Fluent Icons E74D; an eraser, E75C, first: "I don't like it much"; picture `clear-ask.png`), gone by
  itself after 3 s; pressed again in time it does what "clear the chat" does for the session in
  focus. Claimed only while that session's terminal is in an editor that can type /clear
  (`_clearable_here`). The author: "making it like a shortcut", Ctrl+C at first (taken by copying
  and by Claude Code's interrupt), then "double click it to confirm". It asked on the light for
  1.5 s first, then in the permission prompt's box with a cancel key for 5 s; having tried that:
  like "voice is muted", "it would automatically go away in three seconds, there's no need for
  the backspace to cancel that". Word types "©" with Ctrl+Alt+C: shared then.
  Only the question on screen counts: the end key's question or the mute key's banner, which
  take the clear question's place, drop it (and the clear key's drops the end key's). The author,
  2026-11-22, lost a conversation to Ctrl+Alt+C, Ctrl+Alt+Minus, Ctrl+Alt+C: the third press
  cleared with "End …?" on screen.
  Clearing shows its progress (2026-11-24, `clear_progress`, on; `Talk._show_clearing`,
  `_hide_clearing`; pictures `clear-under-way`, `clear-slow`, `clear-done`): the question's row
  becomes a turning ring and "Clearing sidetone 2…", after `base.CLEAR_SLOW` (5 s) with "waiting
  for the editor", then a check and "Cleared sidetone 2" for 1.5 s. Pressed meanwhile the key only
  shows it again. The same for a clear by voice. The author had pressed "many times, it didn't
  work": the hub had both, the extension sent both, and VS Code typed neither for 18 s, its window
  being hidden (`docs/dev/facts.md`). Given up after 10 s before, so the second press typed a second
  /clear, and both came at once; a clear is now under way for `base.CLEAR_CONFIRM` (75 s) before it
  counts as not done. Known: words spoken to the session while its clear waits in VS Code can be
  stopped and cleared by it. Keys for stopping (Escape) and ending (/exit) wait in VS Code the same.
  Bug hunt in a lab, 2026-11-22 (a hub of its own run inside a script, keys handed to it as the
  overlay hands them, haiku sessions in tmux, a stand-in for the extension typing into the
  panes): clear, end and new session in every order, and the clear key next to mute, cancel,
  repeat, the details key, settings and focus. The extension now types Escape before Ctrl+C and
  /clear (0.5.1): Claude Code's "Teach auto mode about your environment?" sits at a prompt its own
  file calls idle, and the Enter after /clear answered its "Yes" and ran /auto-mode-setup. A
  dialog Claude Code does report (a /model picker, a permission prompt) already makes the clear
  wait for the end of the turn. As built: the cancel key does not take the clear question away
  (a second clear press then clears); the focus keys stop at the first and last row.
- The new-session and end keys (2026-11-22, `new_session` Ctrl+Alt+Plus, `end_session`
  Ctrl+Alt+Minus, `Hub.new_session_key`, `Hub.end_session_key`, `END_TWICE` 3 s, `NEW_WAIT` 60 s;
  the extension 0.5.0, `openNew`, `close`). The author: "Ctrl Alt plus and Ctrl Alt minus to add a
  terminal session and remove it". New: the editor opens a terminal split beside the one of the
  session in focus (`location: {parentTerminal}`), in that session's folder (checked to be a
  folder; else the editor's own), types `claude` into it (the word is in the extension, the hub
  only names folder and terminal) and puts the keyboard there; the first session to start with
  `source: startup` within 60 s gets the focus. With no session, a terminal of its own. End:
  asks like the clear key ("End sidetone 2?", a power sign, Segoe Fluent Icons E7E8); the second
  press has the editor type Escape, Ctrl+C, `/exit` 150 ms apart (measured in a tmux session on
  haiku, 2026-11-22: ends it both mid-turn, where Escape stops the turn and Ctrl+C then shows
  "press again to exit", and at an idle prompt with words half typed), and once SessionEnd comes
  the hub asks the editor to close that terminal (`_ending`, `_ended_by_key`; handed to the
  next request if the editor was between two). A session that ends by itself keeps its terminal.
  Ended by the key, it has a sound of its own once SessionEnd comes (2026-11-22, `TONES["ended"]`:
  G4, E-flat 4, G3, falling a minor third and then to the octave below, 0.29 s), or "Session ended."
  in its voice with spoken feedback, as a clear has. The author: "it doesn't have a sound ... it's a
  negative thing". Not tried by hand yet.
  Claimed only while an editor that can do it is there (`_can_open`, `_endable_here`). Hotkeys
  name the keys "Plus" and "Minus" (a "+" would split the combination; `Ui.KeyNamed`,
  `NameOfKey`), drawn as "+" and "-" on the caps. Word has Ctrl+Alt+Minus for a long dash: shared.
- Where a new session opens (2026-11-26, `terminal.new_session`, "New Session Opens" under
  Terminal: `beside` | `tab`; `sidetone terminal new beside|tab`). The author, by voice:
  "whenever I do Ctrl Alt Plus, the terminal is always created side by side. I think there
  should be a feature setting that lets me create a new tab, which is not side by side".
  `beside` (the default, as it was): split next to the terminal of the session in focus.
  `tab`: a terminal of its own, which VS Code lists as a new tab of the terminal panel and
  shows alone (or wherever its `terminal.integrated.defaultLocation` sends new terminals).
  Only the hub changed: with `tab`, `Hub.new_session_key` names no terminal to sit beside
  (`"beside": null`), which the extension has opened as a terminal of its own since 0.5.0
  (what it did with no session), so there is no new extension to install. Still asked of the
  window that holds the focused session's terminal, in that session's folder, `claude` typed,
  the keyboard in it, and the session that starts gets the focus. It goes with Switching Moves
  the Keyboard (`terminal.jump`): as tabs only one terminal is in sight, and that setting
  brings up the one of the session you move to. "A new tab" was taken to mean a tab of the
  terminal panel; a tab in the editor area (`TerminalLocation.Editor`) would be a third value
  and needs the extension changed: not built. Tests: what the hub asks, and the real extension
  with a stand-in editor over the hub's socket
  (`test_the_editor_extension_opens_it_split_or_as_a_tab`: `createTerminal` is given
  `location.parentTerminal` for beside and no `location` for a tab). Picture
  `settings-terminal.png`. Tried by the author the same hour, as a tab: "it works well".
- Answering a permission prompt by voice (2026-11-21, `spoken_verdict`, `SPOKEN_YES`, `SPOKEN_NO`):
  a bare yes or no (English, Italian, Chinese; "please", "thanks" after it allowed) allows or
  denies as the keys do; anything longer turns the request down and follows as the next message
  (`voice_at_prompt` "details", out of the window the same day). Before, a spoken "yes" was taken
  as more to go on and refused the request; the author: "even if I use the voice, I can still
  say yes or no", then "I can just say yes or no to approve or refuse". "Okay" is left out, as
  one says it to oneself.
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
  (Never, Acting alone = `"auto"`, Always; a switch since 2026-11-21, the author finding "Acting
  alone" unclear and then taking it out, `"auto"` still read from config.json) and "Time to cancel before sending" (0 to 5 s; out of the window on 2026-11-21, the author:
  "if it's unsure ... they could just toggle the confirmation before sending"). The hub hands it to that session's listener, shows "sent → name: text" for 2.5 s and
  plays a short sound (see the next point). Target: the session that spoke last; a quick tap of the talk key picks the next one.
  A busy session gets the follow-up right after its current reply. Since 2026-11-21 it gets it
  after the step it is on (`followup_when`, "step"; "A Busy Session Hears You" under Talking):
  the hub leaves the words in `$CS_RUN/steer/<session>` (`_leave_for_step`, worded as `STEER`),
  and `hooks/stop.sh` at the next PostToolUse takes the file by renaming it and gives it to
  Claude as `additionalContext`, which Claude reads within the same turn (tried with a haiku
  session and a hook of its own: told mid-turn to end with a word, it did). The words stay in
  followups until taken, so the cancel key can still take them back (`_sync_steer` claims the
  file back the same way, by renaming); the hub learns they were taken from report.sh's copy of
  the step (`_steered`) or at the end of the reply, and a reply with no further step gets them
  at its end as before. Why: Claude Code itself passes a message typed while it works "as soon
  as those tool calls finish, within the same turn" (its docs, found by a research agent the
  same day), while spoken words waited for the whole reply; the author: "instead of queuing
  audios, I'm putting more info into the request". The research also found accidental
  interrupts a top complaint, so this steers without interrupting. With no listener yet, the
  text waits in the hub until the session next stops. The cancel key also cuts the line being spoken.
- Your words in the terminal (2026-11-26, `words_in_terminal`, "Your Words in the Terminal" under
  Talking, off; `Talk._handed`, `_shown_said`, `Hub.on_display`, `hooks/display.sh`). The author:
  "whenever I say something, the transcript gets displayed only on the overlay, but not in the
  terminal. Why?" Because spoken words reach a session as a hook's feedback (`listen.sh`, exit
  2) or as a step's `additionalContext`, never as a typed prompt, and Claude Code shows of the
  first only "● Stop hook feedback" and of the second nothing. With the setting on, the hub
  keeps the words it hands a session (at `collect`, and when a step has read them in
  `_sync_steer`) and writes them as `🎤 words` and an empty line above the next lines that
  session shows, through the rewrite `display.sh` already asks for (`displayContent`). One line
  for one handing over, as Claude is given them; not the hub's own `TAKE_BACK`. So that it is
  the first lines of the reply and not only the spoken one (a reply may begin with other words,
  and has no tag with the voice off), the hub leaves an empty file `$CS_RUN/said/<session>`
  while it has such words, and `display.sh` sends a batch with no tag to the hub only while
  that folder holds a file: with the setting off the hook is as fast as before (measured, see
  `facts.md`). Dropped unshown when a prompt is typed (they were said to a turn that was
  interrupted) and when the session ends; the folder is emptied when a hub starts. Why off,
  with the reasons under an info sign (`tag`, `tag_help`, as Piper's "Faster" has; the author:
  "put it as a setting, default as no ... a info icon to show the downside of them activating
  it"): the line is on screen only, since the saved conversation keeps the reply as written,
  and it comes with the reply, not when you speak. Tried with a haiku session in tmux and a
  hub of its own: said to an idle session, and said to one that was reading files (shown
  after "Read 1 file", above the lines that followed). **Not tried by the author.** Two other
  ways were weighed and not built: Claude told to repeat the words (tokens, may reword them,
  pushes the spoken line down), and the VS Code extension typing them as a real prompt (in
  the prompt history and the saved conversation, but up to a minute late with its window
  hidden, VS Code only, and the hub cannot see a half-typed line or an open permission
  prompt, which its Enter would answer).
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
- In Italian and Chinese (2026-11-19, the author's words: "per by the way userei comunque,
  ad esempio e comunque che ore sono?"). `aside_words` has "comunque" and "a proposito" and
  three Chinese ones ("顺便问一下" and the like, matched without a word boundary since Chinese
  has no spaces); `ASIDE_LEAD` passes over Italian small words ("e", "allora", "senti" ...).
  The copy is told to answer in the language the speech model heard (`Pending.lang`,
  `Aside.lang`, `base.aside_prompt(question, lang)`), and the answer is said with the
  session's voice for that language; with `reply_language: english` it stays English. Known
  risk: "comunque" also opens ordinary messages ("comunque, procedi"), and while the session
  works those become side questions. Not tried by voice yet.
- Usage and context by voice in Italian (2026-11-19, their examples: "quanto stai
  consumando? quant'è il contesto al momento?"). `usage.asked` returns what is asked (usage,
  context or both) and the language: English as before (`asks`), the session's context in
  English (`asks_context`: "how full is the context?"; a smaller word list, so "what is the
  context window of this model" still goes to the session), and Italian (`_asks_it`, accents
  taken off, every word one such a question is made of). The context is known already and
  said at once (`usage.say_context`); the usage is read as before and said in Italian
  (`usage.say(read, "it")`, times on a 24-hour clock, `clock24`) with the Italian voice.
  Not tried by voice yet.
- Taking words back after they went out (2026-11-17, `Hub._take_back`, `unsend_seconds`, 4;
  0 = off). Since 2026-11-21 words still waiting in the hub for a busy session can be taken
  back however long they have waited (`_unsendable`), and the time is out of the window: the
  author, "what is the purpose of increasing that timer ... I would increase into infinity";
  once a session has the words the cancel key stops it anyway (`cancel_stops`), and after the
  time it used to stop the session's work while the waiting words still went to it. The author wanted an easier way to cancel; offered a spoken ending ("never mind")
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
  `talk` Ctrl+Alt+Space, `repeat` Ctrl+Alt+R, `settings` Ctrl+Alt+S and `mute` Ctrl+Alt+M
  (2026-11-19, `Permissions.toggle_mute`: the voice-off file for every session, cuts the line being
  said, the sounds `voice_off`/`voice_on` and a banner "Voice off" or "Voice on"). The author asked
  for "M for mute", but on their machine the NVIDIA overlay (`NVIDIA Overlay.exe`) holds
  Ctrl+Alt+M: with it closed a probe got the key, and it came back by itself within minutes and
  took it again. Confirmed in the registry: `HKCU\Software\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS`
  holds each NVIDIA shortcut as virtual-key codes, and `MicToggleHKey0-2` are Ctrl, Alt, M: the
  overlay's "toggle microphone", NVIDIA's default, so many machines with an NVIDIA card will have
  it. The same place has `PMOCOverlayVisibilityHKey` = Ctrl+Alt+R (its performance overlay),
  which is our repeat key; the hub has always got R first, which could flip if NVIDIA's overlay
  starts before it. The overlay reports a taken key only
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
  the repeat key spoke while muted. `_replay` (repeat) and `say` without a
  session went to the voice without asking; while muted a replayed line is now shown at
  its light, and the hub's own words are left unsaid. 2026-11-21: the repeat key pressed again
  while the line is heard (a replay, or the line the first time) starts it over at once; it was
  queued behind itself ("I didn't get the first part ... it cued the next replay").
  The icon is drawn (`MutedSpeaker`), not the font's: at 14 px the font's speaker had a small
  cross at its side that could not be made out (the author: "not very clear because ... very
  small", wanting a slash over the speaker). A speaker with two waves and a slash across all
  of it, cut free of what it crosses by a gap; the same in the card's corner, the line, the
  "Voice off" notice and the mark past the bar.
  One row for both (2026-11-19, the author: "when I mute ... I see a layout, then after a
  few seconds I see another layout. One layout does enough. I think the side-by-side is
  good"; and of "Voice on": "the label and the icon, I don't think they're vertically
  aligned ... make it coherent"). The mute key's notice was a title with the key on a line
  under it, then gave way to the details' line with the key beside it; and "Voice on" had
  an emoji speaker (11 px tall, 10 px gap, 1 px high) where the others had the drawn one
  (14 and 12 px, gaps 8 and 7). Now both notices and the line are `Overlay.VoiceRow`: the
  drawn speaker at 15 px, struck out or sounding in the blue of "working"
  (`MutedSpeaker.Struck`), a 7 px gap, the words, the key beside them. The hub says "Voice
  is muted" with "Ctrl+Alt+M turns it on" and "Voice is on". Measured in the pictures:
  icon and letters within 0.5 px of the same middle in all three.
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
- A headset's button to talk (2026-11-24, `headset_button`, `headset_seconds`, `headset_send`;
  `hub/headset.py`, `headset/Headset.cs`). The author was listening to a message while walking
  away from the PC and wanted to answer. What was measured with their Bose is in `TODO.md`
  ("AirPods paired with the PC"); the test for it is `tests/headset`. While a session speaks and
  for `headset_seconds` (60) after, the Windows program holds a media session of its own, so a
  press comes to it and not to the music; the rest of the time it holds none. With no music
  playing it says paused: a press is Play, and a Pause (headphones that pause when taken off) is
  ignored. With music it has to appear anew saying playing to get the press, which then is a
  Pause and does not stop the music. It looks once a second whether that changed. A media key of
  the keyboard (seen by a keyboard hook just before) and a double press are passed on to the
  music. A press opens the microphone whose name in brackets is that of the headphones in use
  (Windows' default microphone may be on the desk), reports a call to Windows (`CALLS`, 11 24H2;
  compiled without where that is missing) and plays a tone; the audio comes to the hub as it
  is recorded and takes the place of `parec`'s (`talk_start(mic)`). Two quick presses come back
  as the call's end (or, not seen, a mute) and send. `headset_send: auto` also sends after 4 s of
  silence, until the presses have once worked on those headphones (`headsets.json` in the state
  folder), and never over music, where it may have been headphones taken off. Dropped, with a
  lower tone and why on the light: 8 s without the microphone, 10 s with nothing said, 120 s
  without an end. The voice waits 5.5 s after it (`BACK`), as the headphones take about five
  to switch back. A press also confirms words that wait for a tap. No code for a brand.
- Discord muted while you talk (2026-11-20, `push_to_mute`, true; `push_to_mute_key`, `F24`;
  `Talk._push_to_mute`, `HoldKey` in `Overlay.cs`, `sidetone discord-key`). The author, by
  voice: "is it possible that when talking I don't speak to Discord?", then "yes and make it a
  setting". The hub sends `hold_key` with the key just before the recorder starts and `""`
  once the recording ends (after `talk_tail`) or is dropped; the overlay presses the key down
  (`keybd_event`, marked as its own so its hook lets it through) and lets it go, and lets it
  go when it exits. In Discord's Keybinds, Push to Mute is given that key: Discord itself
  mutes you while it is held (Push to Mute works in Voice Activity mode; with Push to Talk
  Discord sends nothing anyway). F24 because no keyboard has it, so nothing else reacts;
  `sidetone discord-key` presses it after 3 s so Discord's keybind recorder can take it.
  Tried first and dropped the same night: muting Discord's own microphone stream in Windows
  (`IAudioSessionManager2` on the capture endpoints, `ISimpleAudioVolume.SetMute`). Windows
  accepts it (`GetMute` reads 1) but does not apply it to a capture stream: the author still
  saw Discord's green ring, and WSL's own stream (`msrdc`) muted the same way still recorded
  the room unchanged. Discord's Push to Mute on the talk key itself does not work either:
  the overlay keeps the talk key's press from other programs ("it's still green" with
  Ctrl+Alt+Space bound in Discord). Discord sees F24 alone: the overlay already sends Ctrl and
  Alt up during a hold (`MaskKeys`). Discord takes the injected key, in its recorder and as a
  keybind: tried by the author 2026-11-21, the ring stayed dark ("It's perfect, I think").
  Their first recording came out as Ctrl + F24, which never matches during a hold (Ctrl is
  masked); recorded with hands off the keyboard it is F24 alone.
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
- History and saying it again: the hub keeps the last 100 lines sessions said. (A catch-up key,
  `missed` Ctrl+Alt+U, replayed every line since the last prompt or hotkey; it mostly said "Nothing
  new", and the author had it removed on 2026-11-20: "You can remove it. I will use the replay
  anyway." A version counting only lines said while you were away is on the branch
  `away-catch-up`.) `repeat()` says again the
  last line of the session in focus (the author, 2026-11-17, after trying the key: "it would be
  better to have it replay the selected session, also i noticed the detail box doesnt come
  out"); `repeat: last` brought back the last line anyone said, until the author had it removed on
  2026-11-20 ("once a session starts talking, the focus automatically goes to that one ... it's
  easier if ... that shortcut automatically repeats the last message from that session").
  With no session in focus it says the last line anyone said. A replayed line
  is tied to its session (`Hub._replay`), so its bubble, voice bars and wave show as they did
  the first time; before, it belonged to no session and nothing showed. The overlay gets the newest lines with each
  `state`, up to four of each session, and shows them while the cursor rests on the list
  (found by polling the cursor position, since the window is click-through). It shows the
  lines of the session under the mouse (`historyOf`; before a row was touched, the session
  in focus): the author hovered another session, saw it light up and expected its history
  (2026-11-17). `overlay.history: all` shows every session's lines mixed, as before.
  In Selected Session the history is in the card whenever the details are out, without the
  mouse resting (`overlay.focus_history: always`, "History in Selected Session"; `rest` waits
  as All Sessions does). The author, 2026-11-22: "it would be cool to also have the history
  displayed by default"; the other rows are left out there, so it has the room.
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
  the one in focus has `strength` (0.09, shown as 30 % in the settings window where 100 % is 0.3; it was 0.14 until the author said "less tint maybe", then 0.08 until they found 27 % "such a weird number") of its overlay color mixed into `background`
  (`#181818`, VS Code's dark theme; the real background cannot be asked for from outside, the
  answer would land in Claude Code's input; with a light theme, see below). `all` tints every terminal (the others at half
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
  in their four terminals and said "looks good". Tab names: VS Code
  shows a written title only with `"terminal.integrated.tabs.title": "${sequence}"`, and Claude
  Code writes its own title ("✳ Claude Code", then a summary of the prompt) unless
  `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1`. Checked 2026-11-20 in tmux: the variable works when set
  in the `env` block of a settings file, and then Claude Code writes no title at all. All three
  (VS Code's setting, the `env` block in `~/.claude/settings.json`, `terminal title on`) were
  turned on that day at the author's yes, and turned off again the same hour: "I don't like
  them this much. I would prefer [Claude's own] session [title] ... I think you should revert
  this." Kept as a setting, off by default.
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
- The window follows the focus (2026-11-24, `terminal.window`, `Talk._bring_window`, extension
  0.7.0). The author, with three projects in three VS Code windows: "whenever I switch this
  session in the overlay, I want the Visual Studio Code page to pop up in front", but not over
  another program. Each window's held request now carries `folder`, what it has open (a saved
  workspace file, or its one folder; else "", and it cannot be brought up) and `"window"` in
  `can`. When the focus moved by hand has rested for `WINDOW_REST` (0.25 s; turning the wheel
  past a session brings nothing), every window is told the folder of the session's window, and
  the one in front (`vscode.window.state.focused`, which only the window knows) runs
  `vscode.openFolder` on it, which VS Code answers by showing the window that has it open.
  Always with `forceNewWindow`, so it can never replace what the window in front has open; only
  for a window that is still there (`_showable`), as one that is gone would be opened anew. The
  terminal is shown too, whether or not `jump` is on, or the window's report of its own active
  terminal would move the focus to another session there. Measured with `code --new-window
  FOLDER` (the same path in VS Code): the other window in front after 80 ms, the same three
  windows, no reload. Chosen over raising it from the overlay: no Windows code, no matching of
  window titles, and nothing about it is Windows only.
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
  Tried again 2026-11-20: cleared, but the session "went straight to the bottom of the
  overlay bar", since the session `/clear` starts has a new id and a new one went last. Now
  `Sessions.clearing` keeps the cleared one's name, color, voice and place by folder, and the
  `SessionStart` with `source: "clear"` in that folder within `HEIR_WITHIN` (30 s) takes them
  (not its title: the chat is new). Two sessions of one folder cleared in the same 30 s
  could swap places. The same try showed a misheard order: "I'll clear this hat." went to
  the session as a prompt.
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
  The author still had YouTube pause while talking (2026-11-22: "whenever I watch YouTube it
  pauses the video when I talk ... make it a setting"). So the hook now goes in at the first
  of the hotkey's other keys (`AnyMod`: Ctrl, say), not once all are down, which leaves the
  gap only for a talk key pressed within 30 ms of the very first modifier. A window entry
  for `keep_talk_key` came and went the same hour: the author had meant the trouble of
  2026-11-17 ("right now I don't have any issues with YouTube"); `always` and `off` stay in
  config.json.
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
  the voice's speed handed to the engine), writes it to `config.json` and logs it (through
  `settings.save_all`, one change at a time, which the overlay's place and the terminal's
  settings use too; since 2026-11-21 a `config.json` that is there but is not JSON, a slip
  while editing it by hand, is left as it is and `hub.log` says so: before, it was written
  over with the one setting just chosen, and every other one in it was lost. At start,
  `Config._checked` leaves out each value of the wrong kind, a word where a number belongs,
  checked against the field's annotation or, inside `overlay` and `terminal`, the default's
  type; whole and decimal numbers stand for each other. Each is named in `hub.log` and its
  default stays; a file that is not JSON gives the defaults. Before, one such value made every
  overlay update fail, and a broken file stopped the hub starting. The author agreed, 2026-11-21); then
  the hub sends the sections again and the window draws what the hub has, so a choice
  that was refused does not look taken. A slider only sends where it is let go. Keys are
  paths: `speed`, `overlay.layout`, `terminal.tint`, `overlay.hotkeys.talk`, and two that
  are not in the file: `mute` (the voice-off file; called `voice`, "Voice", "Speak a short
  summary of each reply" until 2026-11-20, when the author took it for short or long answers:
  "it sounds like it's more like a mute or not") and `voice_of.<project>` (says "This
  is my voice." in the new one). To add a setting to the window, add a line to
  `settings.SECTIONS`; a test checks that each is a setting the hub has and that each one
  at the top of the file is read back at start. `sidetone settings list` prints them
  all and `sidetone settings KEY VALUE` sets one, which is also how the live hub was
  tried (`history_time` on and off; a wrong value refused).
  The Keys page (2026-11-22, the author asked whether its names and descriptions were
  intuitive, then "do them all"): grouped under small titles (`heading(...)` in `SECTIONS`,
  drawn like the language titles on the Voices page; `items` leaves them out, they are not
  settings): Speaking (Talk, Cancel or Stop, Mute, Say It Again), Answering (Allow, Deny,
  Answer 1 to 4), Moving Between Sessions, Window (Details, Switch Layout, Settings, Clear the
  Chat). Every key got a line, all written as what it does ("Repeats ...", not "Repeat ...").
  The four Focus keys are now Previous / Next Session (Bar) and (Island), since "focus" was a
  programmer's word and only the first of each pair said which layout it served.
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
  A reset button under each section's card (2026-11-20, the author: "for each category I
  think it would be cool to have like a reset button at the end"; `settings.reset`,
  `settings.default`, `SettingsWindow.ResetButton`). "Reset" (first "Reset to defaults"; the
  author asked for one word, and it stays at the left, where Windows and macOS put "Restore
  Defaults" in a dialog), faint while the
  section's `changed` is false; the first click turns it into "Click Again to Reset" on the
  tool's blue for 4 s, the second sends the setting `reset` with the section's name, and the
  hub puts each setting that differs back through `apply`, so it acts at once and is written
  to config.json. A default is what a new install has: `Config`'s own, `overlay.DEFAULTS`,
  `terminal.DEFAULTS`, the voice on. Voices has none (a project's voice comes from the
  pool), so no button there. Also `sidetone settings reset SECTION`. Not drawn in a picture:
  the author's own settings window was open where the test one opens.
  A sentence that speaks of the mute, talk, cancel or repeat key gets the key it has now,
  "the mute key (Ctrl+Alt+M)" (`settings._with_keys`, 2026-11-20, the author: "in the
  description ... include also the shortcut key"); a key with no combination gets nothing.
  Setting names in title case (2026-11-20, the author: "all setting[s] ... the title should be
  in title case"); small words (of, the, to, ...) stay small inside a name. A test checks it.
  A dropdown (`Pick`) closes on a second click on it (2026-11-20, the author: "if I click
  again the select shouldn't it be closing"): the popup shut on the press, as for any click
  outside it, and the release opened it again; a release within 400 ms of it shutting now
  leaves it shut. Checked with the real mouse 2026-11-22: with a press and release at the same
  instant (a quick tap) the list opened again, because the moment it shut was taken from
  `Closed`, which comes after the release; it is now taken when `IsOpen` turns false.
  Removed the same night: the spoken progress in long turns ("3 of 5 steps done" once a
  task list had 3 or more steps, after 45 s of work, at most once a minute; `progress`,
  `progress_after`, `progress_interval`, `Hub._maybe_say_progress`). It had never spoken in
  the author's use; heard in a made-up session, they said: "I don't like it much. I think
  you could just remove this setting." Task counts still show in the figures.
  "Sent." and "Queued." in the language you spoke (2026-11-20, the author, with the feedback
  on Voice: "Can you do that in Chinese?"): `base.FEEDBACK_WORDS` has Italian and Chinese,
  said in the session's voice for that language; with a summary language chosen, that one.
  The hub's other words stay English.
  The same hour the author took the choice out of the window: "I think we can remove this
  setting. I think the sound is kind of necessary ... only to sound". `talk_feedback` stays
  in config.json (and the words where no sound can be played); Sound Volume explains the sounds.
  Then one Volume for the voice and the sounds (`volume`, 0 to 100 like a game's master
  volume, 100 by default, at their word: "video games ... have master volume and they go from 0
  to 100"; the author:
  "do one thing for both so it's more consistent ... maybe I want it overall below the
  window[s] system"): both players get `paplay --volume` (PulseAudio's scale, 65536 = the
  system's own), set at once by `base.set_volume`; `sound_volume` (0.3) stays in config.json
  as the tones' level beside the voice, out of the window. Kokoro only; the system voices
  used without a hub keep the system volume.
  "Say the Project Name" became "Say the Session Name" (the author: "the project name is
  actually you saying the session name"). The settings window is resized from any edge or
  corner (`AddGrips`, at least 700 by 400) and maximized by a button between minimize and
  close or a double click on its top (`ToggleMax`: the work area of its screen; dragged
  from there, it goes back to its size under the mouse); the settings keep at most 760 px
  wide, in the middle (the author: "for settings panel to be resizable and also to have
  like a maximized size button"). Checked with the real mouse 2026-11-22 (every edge and
  corner, the smallest size, the button, double clicks, moving it): a double click to restore
  left the window at the top of the screen, as the first press already restored it under the
  mouse. Maximized, a press now only remembers the point, and the window comes back to its size
  once the mouse moves past the system's drag distance with the button held, as a title bar
  does. The Reset button checked the same way: one click asks, 4 s later it is back to Reset
  and a click asks again, two clicks within 4 s reset.
  The Voice section in the order of use (the author: "most use should be on top"; proposed
  and agreed): Mute, Volume, Speed, Language of the Summary, Say the Session Name.
  Names: Earshot, Switchboard, Hark and Heard are all taken by tools for coding agents
  (found by searching, 2026-11-18), so they were not offered; Squelch, Sidetone and
  Tally were, as radio and studio words for what it does.
- **Usage Labels** (2026-11-22). The plan's two usage bars are called "5H" and "7D" by
  default (`usage_labels: short`), as CodeIsland labels them, to leave the bars more room;
  `long` keeps "5 hours" and "Week". A model's own week keeps its name. The author asked
  for it by voice: "still understandable and it also saves space". Made in `Hub._plan_bars`;
  the overlay sizes the name column to fit, so it needed no change. Out of the settings
  window the same day (the author: "I don't think that is needed"); still read from
  `config.json`.
- **The card's figures are the session's totals** (2026-11-20). The author found "This
  reply" and "This turn" "not very intuitive"; "Tokens" and "Running" alone would read as
  totals, "Turn tokens" and "Turn time" were offered, and the author chose to make them
  totals instead, each turn's own figure staying at the end of its line in the history
  (and the running turn's clock in the row). Their two choices: a /clear starts the totals
  again, and the time counts only while Claude works. `detail_metrics` is now `context`,
  `session_tokens` ("Total Tokens"), `session_time` ("Total Time", in title case as the
  author likes it; the author agreed
  the prefix the same evening, so they do not read as figures of the moment beside Context); `tokens` and `time`, each turn's
  own, are still a choice and now say "Turn Tokens" and "Turn Time". Both come from the
  session's record (`usage.tally`, `Hub._count_session`): read once from the top when the
  hub first sees the session, so a hub restart loses nothing (0.4 s for the largest record
  here, 77 MB), then from where it stopped at each prompt, step and end (0.1 ms). Tokens
  count as `turn_tokens` says (`new` by default), each reply once, helpers left out. The
  time is the gap before each reply and each tool result, so a wait on a permission prompt
  counts and the time the session sat waiting for you does not; while a turn runs, the
  time since the last line written (or since the prompt) is added, so it moves like the
  row's clock. A /clear gives the chat a new id and record, so its totals start at zero
  without anything done for it. Measured on this session: 85k tokens, 5 minutes at work.
- `hub/demo.py`: three made-up sessions that go through every state (`sidetone demo`).
- **Fallback**: every hook still works with no hub (`hooks/tts-lib.sh`, engine order macOS `say`,
  Kokoro, Piper, `spd-say`, `espeak-ng`). `display.sh` then leaves a marker so the Stop event
  does not repeat the line once the hub is back.
- `bin/sidetone` (linked by `install.sh` into `~/.local/bin` as `sidetone` and `st`;
  on the author's machine since 2026-11-16): `status`, `say [-v VOICE] TEXT`, `stop`, `on`/`off`, `allow`/`deny`, `answer N`, `repeat`, `sound NAME`, `languages [CODES]`, `voices`, `voice …`, `target [PROJECT]`,
  `follow-up [-s PROJECT] TEXT`, `talk start|stop|cancel`,
  `overlay dots|list|toggle|restart|move|monitor N|corner NAME`, `terminal [tint focus|all|off | find [PROJECT] | show [PROJECT] | strength N | background COLOR | pulse on|off|N | title on|off | follow on|off]`, `vscode install|uninstall`,
  `settings [close | list | KEY VALUE]`, `demo`, `hub start|stop|restart`, `log`.
- `tests/test_hub.py`: 301 tests in all with a silent engine and fake microphone, including the real hook
  scripts over a socket and a hub process that is killed and restarted.
  Run: `~/.local/share/kokoro/venv/bin/python -I -m unittest discover -s tests`
- Config (optional): `~/.config/sidetone/config.json` with `voices` (project name → voice),
  `voice_pool`, `colors`, `label` (`always`/`never`, `never` by default; `auto`, said only with several sessions and no overlay, dropped 2026-11-20: "make it two choices ... I want to reduce [friction]"), `titles` (`ask`/`auto`), `max_age`, `idle_exit`, `default_voice`, `speed`,
  and `overlay` (`enabled`, `mode`, `monitor`, `corner`, `offset_x`, `offset_y`, `opacity`,
  `list_opacity`, `glass` (`blur`/`acrylic`/`none`), `flash_seconds`, `talk_sign` (`light`/`line`), `hotkeys`), `permission_grace`, `whisper_model`, `mic_source`, `followup_delay`, `unsend_seconds`,
  `talk_tail`, `push_to_mute`, `push_to_mute_key`, `headset_button`, `headset_seconds`, `headset_send`, `talk_feedback`, `sound_volume`, `cancel_stops`, `clear_by_voice`, `clear_progress`, `clear_words`, `usage_shown`, `usage_every`, `usage_warn`, `usage_models`, `usage_labels`, `history_time`, `context_shown` (`arc`/`text`/`both`/`off`), `context_window`, `turn_tokens` (`new`/`output`/`all`/`off`), `turn_tokens_label`, `turn_tokens_history`, `separator`, `waiting_words`, `row_metrics`, `detail_metrics`, `aside`, `aside_words`, `aside_model`, `aside_timeout`, and `terminal` (`tint`, `strength`, `background`,
  `pulse`, `pulse_strength`, `title`, `follow`). `SIDETONE_OVERLAY=off` disables the overlay.
- `~/.local/state/sidetone/voices.json`: the voice each project was given, kept so it stays
  the same across hub restarts (a future settings panel would edit this and `config.json`).
- Toggle: voice is off while `~/.claude/voice-off` exists (the hub still tracks state).
  Muted, `display.sh` still sends a speak line to the hub, which shows it at the session's light,
  and still rewrites it as "🔊 …": the reminder stops at the mute, but a session goes on writing
  the tag it wrote before (the author saw the raw tag, 2026-11-24).
- Runtime files live outside the repo: `~/.local/state/sidetone/` (`voice.log` contains
  spoken summaries, `hub.log`, `.state/`, `.tts.pid`).
- `hooks/settings-snippet.json`: the `hooks` block as registered in settings.json.

- The Voices page of the settings window (2026-11-21; `settings._voices`, `catalog`, `in_use`,
  `set_in_use`, `preview`, `voice_label`; `Folded`, `PlayButton`, `Grip`, `Drag` in
  `Overlay.cs`). The author: "there's a menu voice ... and another one which is labeled
  voices. Maybe these two are too similar", the page "shows only the current sessions ...
  there's no label, there's no preview ... these layout are also centered", and "for each
  language to associate the models". Agreed: the Voice section is now **Speech**; the list
  of settings is stretched (up to `ListMost`), so a section of short lines is as wide as the
  others. The page is headed parts (`kind: heading`): Sessions, one dropdown per open project
  (its English voice, offered English voices only, the ticked ones first) with a ▶ and its
  Italian and Chinese voices under it; then one card per language of `SUMMARY_LANGUAGES`
  with every voice this machine has that speaks it (Kokoro's by their first letter, Piper's
  by their model name, `zh:` the Chinese model's, one's own voices as English), each a
  `kind: voice` line: a readable name (`voice_label`: "Heart", "American woman"; the Chinese
  model's numbered voices "Woman 1"), a ▶ (`play`: the voice says `SAMPLES[lang]`, nothing
  changes) and a tick. Ticked voices are, for English, `voice_pool` (new projects get the
  first one no open session has; now in the pool's order, it was from a place picked by the
  project's name), and for Italian and Chinese `language_voices[lang]`, which `_voice_for`
  shares out in order (changing it hands them out again at once). The ticked come first in
  their order and are dragged by six dots at the left (`voices_order.<lang>`); the others
  wait under "More Voices (N)". At least one stays ticked. A project keeps the voice it had
  even when that voice is no longer in the pool (`Sessions._voice_for`): before, a voice
  chosen by hand outside the pool was replaced at its next start. Pictures:
  `settings-voices.png`, `settings-voices-tall.png`.
  The same morning, "the English models are too many ... just keep the best ones, the fastest
  ones, the most clear": the pool is now eight (`state.VOICE_POOL`: Heart, Michael, Bella,
  George, Nicole, Fenrir, Emma, Puck) by Kokoro's own grades (VOICES.md of
  hexgrad/Kokoro-82M, `settings.ENGLISH_GRADES`), and the window leaves out the English
  voices graded D or F and Piper's English (kept for when Kokoro is missing); the other seven
  graded C or better wait under More Voices. On 2026-11-22 Nicole left the default pool, now
  seven ("I don't like it ... I'll disable it myself on my end, but for other people, don't put
  it in the default selected"); the author's own `voice_pool` still has her. Each card line says the grade ("American woman,
  quality A", first written "grade A"; the author: "quality is much more intuitive"). Then one
  word for every language (`quality`, `QUALITY_WORDS`; the author: "in English, I see quality A,
  B, C+ ... in Chinese, I see clarity, X out of Y. Can you make a standard?"): Kokoro's A and A-
  Excellent, the Bs Good, the Cs Okay (Italian's two voices are graded C too); Chinese by thirds
  of the measured clarity, Good, Okay, Basic; Piper's Okay, and after it a small "Faster" with an i in a circle that says why when the mouse
  rests on it (`voice_tag`, `FASTER`; `Tag` in `Overlay.cs`; the author: "make that title case
  and faster might not be very explaining ... an info icon on why"; picture
  `settings-voices-italian.png`). The same day the tag became seconds on every voice ("give the
  seconds for each model"; "It could change on different devices, no?"): each computer times
  its own, once and silently, the first time the window lists a voice (`time_voices`, kept in
  `voice-times.json` in the state folder), one sentence a language (`TIMED`), the middle of five.
  One time per `timing_group` (Kokoro per accent, its Chinese model, each Piper model): timed
  voice by voice, Kokoro's English ones ranged 0.50 to 0.71 s on one sentence, which was noise.
  The engine makes one sentence at a time (`KokoroEngine._making`), as espeak is not for two at
  once. On the author's machine: Kokoro American 0.51, British 0.54, Italian 0.53, Paola 0.37,
  the Chinese model 0.64. Then a switch on each language's heading for whether you speak it
  (`spoken`, `set_spoken`, key `speak.<lang>`; the author: "if someone speaks only English,
  they should be able to disable the other languages ... the fewer the languages to detect, the
  less ambiguous the words are"): it is `whisper_language`, the same as install.sh's question and
  `sidetone languages`, saved with `stt.save_languages` and taken up at once
  (`reload_languages`; English alone gets the English-only model). Off, the heading is dim, does
  not open and lists no voices; the last language on cannot go off; languages the window does
  not list (Spanish, say) are kept. Lines in a language that is off still use its voices.
  Picture: `settings-voices-italian.png` (Chinese off). The page's sentence
  says what the words mean. "Fair" was first for Okay; the author: "what is fair though?". None is faster: every Kokoro voice is the same model. Projects keep the voices
  they had.
  Then: "keep some ... that are not so good but are faster ... for each language". Measured on
  this machine (a sentence of about 4 s, the live hub running beside): Piper 0.29 s (Lessac)
  and 0.34 s (Paola), Kokoro 0.47 to 0.82 s for its English, Italian and Chinese voices alike,
  the Chinese model 0.47 s. So the faster ones are Piper's: its English Lessac is back under
  More Voices, and a Piper voice says "faster (Piper)" ("American woman, faster (Piper)").
  Chinese has no Piper voice installed (Piper has `zh_CN-huayan`).
  Then the Sessions part came out (the author: "what is the point of it ... each language has
  its order ... if it has two, maybe they can alternate. Three, they can do one, two, three,
  one, two, three"): the page is the three language cards. A voice unticked is no longer
  given, also to a project that had it (`Sessions._voice_for` keeps a project's voice only
  while it is in the pool, as before); a voice given by hand with `sidetone voice PROJECT
  VOICE` is pinned instead (`Hub.set_voice` writes it to config.json's `voices`).
  Then "for Chinese there are too many models": the Chinese card lists only the four the author
  picked on 2026-11-19 (`settings.CHINESE_SHOWN`, from `tts.PREFERRED_VOICE`), any other ticked
  in `language_voices`, and Piper's Chinese voices if installed; the other 99 of the Chinese
  model and Kokoro 1.0's eight (espeak, graded D) are left out and still work by name.
  Then "for each language making a drop-down list so I can quickly scroll between the
  languages", and "do they all have the same description beneath the language?" (they did,
  nearly). Each language is now a heading that opens and closes its card (`fold`; `FoldHead`
  and `openGroups` in `Overlay.cs`, all closed when the window starts), with its ticked voices
  named at the right ("Heart, Michael, Bella and 5 more"; then a count, "8 voices", which the
  author found "might be misleading" as it counted only the ticked; now "4 of 12 ticked", the
  ticked out of all the card lists, then "not very conventional", so "4 selected"), and one sentence for the whole page
  under its title (`kind: intro`). Pictures: `settings-voices-open.png` (English opened).
  A voice unticked while its language is open keeps its place, without its tick, until the
  language or the window is closed, and only then goes under More Voices (the author,
  2026-11-21: "whenever I untick a voice it immediately goes to like more voices"); ticked
  again it goes back to that place, and it can be dragged with the ticked ones meanwhile
  (`places`, `kept`, `Block`, `KeepPlaces`, `Tick` in `Overlay.cs`; the hub knows nothing of it).
  Then at most twelve voices a language (`MOST_VOICES`; "maximum 10 or 15"): the ticked in
  their order, then the best of the rest (`rank`), one's own voices always. The page's sentence
  now says the purpose first ("Each open session speaks in its own voice, so you know who is
  talking"), after the author did not follow "the next ticked voice ... a project keeps its
  English one from day to day". A closed language says how many voices are ticked ("8
  voices"), not their names, and nothing while open (the names: "I don't like it much").
  A ▶ pressed again, or another ▶, cuts the preview playing and plays the new one
  (`SpeechQueue.drop_src("preview")`); they queued up before ("I hear the preview twice").
  The Chinese order (`settings.CHINESE_CLARITY`, 2026-11-21): each of the Chinese model's 100
  Chinese voices said five work sentences, faster-whisper "small" (told to write simplified
  characters) wrote them down, and they are ordered by the share of characters it got wrong,
  then by how sure it was. 7 to 15 % wrong, mostly homophones (登录 heard as 登陆) and numbers;
  best zf_049, zf_006, zm_056, zm_057, zm_030. The four the author picked rank 33 (zm_009),
  34 (zm_010), 88 (zf_001) and 98 (zf_002): the measure is about being understood, not taste.
  The line says it: "Chinese woman, clarity 1 of 100". The window lists the four ticked and
  the eight clearest. A first run read 30 % wrong for zf_001: Whisper wrote traditional
  characters until told otherwise (`initial_prompt`).
  The ▶ shows a square while its preview plays, and a click on it stops it
  (`stop_preview`; `Hub._previewing` sends the window again when a preview starts or ends).
  The author asked for it ("then there's the square to stop it"), and said "yeah" to it.
