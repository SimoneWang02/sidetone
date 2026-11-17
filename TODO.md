# To do

What is left for claude-speaks, as of 2026-11-17. Everything asked for so far is built; this
is what has not been tried by hand, what is undecided, what is rough, and what has not been
started. `CLAUDE.md` has the details of how things work.

## To try by hand

These work in the automated tests or in pictures taken from WSL, but nobody has pressed the
real keys yet.

- [x] Push-to-talk in Italian with a real voice. Done by the author on 2026-11-17, twice.
      First a short mixed sentence, English and then "ciao Claude, mi senti?": both halves
      right, except "Claude" written as "cloud" (3.5 s to transcribe 6.6 s of speech, against
      about 1.5 s for English of that length). Then 27 s that began in English and went on
      with three whole sentences in Italian: all of it arrived and could be acted on, in
      3.6 s. Slips: "push the talk" for "push-to-talk", "in futura" for "in futuro", and the
      first words of the recording may be missing (it starts at "the to-do list"). Not
      tried: a recording that is Italian from its first word.
- [x] Push-to-talk's sign inside the session's light (2026-11-17). The author saw the dots
      and the paper plane and, after the plane was redrawn to sit in the middle, said "that's
      good". Not seen by them yet: the struck-out microphone for "not heard" or cancelled.
      `"talk_sign": "line"` under `overlay` puts the sign back beside the name.
- [x] Hold `Ctrl+Alt`: the details panel comes out while the keys are held (the author,
      2026-11-17: works)
- [x] `Ctrl+Alt` + mouse wheel: the focus moves, and stops at the first and last session
      (the author, 2026-11-17: works)
- [x] `Ctrl+Alt+Y` / `Ctrl+Alt+N` on a real permission prompt. Done by the author on
      2026-11-17 against a throwaway session that asks before running commands: the hub
      logged "deny (hotkey)" and the file was not made, then "allow (hotkey)" and it was.
- [x] `Ctrl+Alt+1` to `4` on a real multiple-choice question. Done by the author on
      2026-11-17 with the third choice of three: the hub logged "answer (hotkey)" and the
      session got that choice.
- [x] Answering a question by voice (built 2026-11-17 on the author's question whether they
      could "send an audio instead of picking a choice"): while a session shows a question,
      hold the talk key and say the answer in your own words. Done by the author the same
      day on a real question: 17 s of speech came back as the answer, word for word.
- [ ] The choices of a question each on a line of their own in the overlay (the author,
      2026-11-17, in that same spoken answer: "the choices are not in new lines. I see them
      all in a single line and it's not very readable"; changed at once, seen in pictures
      only).
- [ ] A question answered in the terminal leaving the overlay at once (mended 2026-11-17
      after the author saw it stay; checked with a real session).
- [x] `Ctrl+Alt+R` (repeat): the author, 2026-11-17: "good for replay".
- [x] `Ctrl+Alt+R` again after the change they asked for the same day: it now says the last
      line of the session in focus (move the focus with `Ctrl+Alt` + wheel first), and the
      bubble with the voice comes out at that session's light while it is said. The author,
      2026-11-17, right after two repeats: "It's perfect. Yeah, I see it."
- [ ] Speaking to a session right after interrupting it (mended 2026-11-17 after the author's
      words to an interrupted session "didn't go through"; checked with a real session,
      not yet by the author): interrupt a reply with Esc or Ctrl+C, hold the talk key and
      say something. It should answer.
- [ ] Words going to the wrong session (the author, 2026-11-17: "i sent an audio to
      claude-speaks 4 but somehow got here (i didnt notice at first)"). Nothing was broken:
      the voice goes to the session in focus, which is the one that spoke last, and this
      session had just spoken while they were looking at the other one's terminal. The
      listening bubble shows who is being spoken to, but it was not noticed. Ideas, none
      built: the focus following the terminal you click (see below, needs a VS Code
      extension); the focus moving to a session when you type to it; saying the session's
      name when the talk key goes down and the focus is not where you last typed.
- [ ] `Ctrl+Alt+U` (what did I miss): the same minute it answered "Nothing new." twice,
      which was right, since nothing had been said since the last message. Not heard yet:
      a real replay, pressed after a session spoke while the author was away from it.
      The author found it hard to grasp (2026-11-17: "so it detects when im away? so far
      ctrl+alt+u says nothing new"). It does not detect anything: "missed" is every line
      said since the last typed prompt or hotkey, so any key pressed after a line (repeat,
      the wheel, push-to-talk) empties it, and a line heard at the desk still counts.
      Ideas offered, none chosen: count a line as missed only when it was said while
      keyboard and mouse had been still for a minute or more (the overlay can ask Windows
      for that), plus lines that were cut or dropped unsaid (each line already carries a
      `heard` mark that catch-up does not use yet).
      Built the same day and parked on the branch `away-catch-up` (commit `07c9ff9`, 121
      tests pass, the overlay compiles; not live, never tried with real idle time). The
      author asked whether it is worth it and, asked again the same day with three choices
      (keep, drop the key, leave it), said: "I think we can leave it for now." So the key
      keeps its old behaviour until they bring it up again. Keep: merge the
      branch and restart the hub. Drop: the offer was to remove the key and the catch-up
      code altogether, since the present version mostly says "Nothing new".
- [x] `Ctrl+Alt+Backspace` while recording (the author, 2026-11-17, right after being asked
      to try it: "Nice it works it works"). Not said: whether the same key also cut a line
      that was being spoken.
- [x] Hold the talk key with a video playing in the browser in front (YouTube): the video
      should neither pause nor change speed, also when Ctrl or Alt is let go before Space.
      The author, 2026-11-17: fine while holding, but "it stops the video on release". The
      release of Space still reached the browser. Changed the same day so that press and
      release are both kept back, and tried again by the author: "It works. It works.
      Nice." Known gap: Space pressed in the very same instant as Ctrl and Alt can still
      pause the video on release.
- [ ] The bar over a game in borderless windowed mode
- [x] A plain click on the bar reaching the window underneath (the author, 2026-11-17: "it
      lands on the window underneath")
- [x] Dragging the bar, which since the same day needs `Ctrl+Alt` held (the author's wish on
      seeing the move cursor whenever the mouse was on the bar): with the keys held the
      move cursor shows on the bar and it can be dragged; without them there is no move
      cursor and clicks and the wheel go to the window underneath. The author, 2026-11-17:
      "Oh yes, it works. Now perfect." The new place was saved to `config.json`.
- [ ] Sessions started from the VS Code extension showing up in the bar
- [ ] The bar no longer getting taller when the mouse is on it while a long sentence is
      said: since 2026-11-17 the sentence is cut to one line in the details (`row_lines`).
- [ ] Clicking while talking (the author, 2026-11-17: "while I talk I cannot right click, so
      for instance I cannot pause the YouTube video"). Not looked into beyond a guess: with
      `Ctrl+Alt` still down the click reaches the browser as Ctrl+Alt+click, which a video
      player may ignore; the overlay passes every click on. To find out: hold only
      `Ctrl+Alt`, without Space, and click the video. If that does not pause it either, it
      is the browser. Since the same day the hold goes on with Space alone, so letting go
      of Ctrl and Alt while talking should give plain clicks.

## To decide

- [ ] Which of the two layouts (`bar`, `island`) is the default for new users. Today it is `bar`.
- [ ] Voice of this project: it speaks with `bf_isabella` since the voice pool changed. Pin
      the earlier `af_heart` back? (`claude-speaks voice claude-speaks af_heart`)
- [ ] "Uploadable" voices: was that cloning a voice from a recording? Kokoro cannot do it; it
      would need a second voice engine.
- [ ] Should the repo default for push-to-talk be the multilingual model? Today the default is
      English-only and the author's own settings switch it to English plus Italian.
- [ ] Should a quick tap of the talk key also stop at the last session, like the wheel? It
      still goes round.

## Rough edges

- [ ] A hub restart still forgets a few things. Names, colors, voices, titles, the order in
      the bar and the focus are kept since 2026-11-17 (`sessions.json`), but not the lines
      sessions said (so catch-up and repeat start empty), the task counts of a running turn,
      or a permission prompt that was open (it can then only be answered in the terminal).
      A turn that ends in the second the hub is down comes back as idle, without its check.
- [x] Titles that say what a session is doing (the author, 2026-11-17, could not tell four
      sessions in one folder apart by their titles, which were the start of each one's
      first spoken sentence). Changed the same day: each session now writes its own title
      of a few words into its speak tag and updates it when the work moves on. The author
      on seeing the first one: "that's perfect. Yeah, it's clear now." Still to watch over
      a longer day: whether titles change too often or too rarely.
- [ ] Something said to a busy session waits until its reply ends, and a turn stuck on an
      unanswered dialog in the terminal holds it back for as long as the dialog is open. The
      overlay shows "waiting" for 3.5 s only; the author took it as not heard (2026-11-17).
      Keep the waiting sign on that session's light until the words are delivered. (Done
      2026-11-17: a waiting message has its own sound, or "Queued." with `talk_feedback: voice`.)
- [ ] Some push-to-talk holds record sound and come back as "nothing heard". Some were
      Italian before the multilingual model, but at least one was English. Cause not found: the
      microphone delivers signal at once, and loudness made no difference in tests. Next
      step: keep the last failed recording (opt-in) so it can be examined.
- [ ] A misheard sentence is sent straight to the session: there is no pause and no confirming
      tap any more (the author's choice). `followup_delay` and `followup_confirm` bring them back.
- [ ] A permission prompt that waited more than six seconds and is then approved in the
      terminal stays "needs you" until that tool finishes.
- [ ] The number keys only answer single-choice questions with up to four options. The same
      limit holds for answering by voice: other questions are only announced, and words
      spoken meanwhile wait until the question is answered in the terminal. A permission
      prompt cannot be answered by voice either (the words wait); "deny, and here is why"
      by voice would be possible, since a deny can carry a message.
- [ ] The spoken project name is off while the overlay is up; with many sessions and eyes
      away from the screen, the voices alone may not be enough to tell them apart.
- [ ] `hub/hub.py` is over 1,100 lines. Split it (permission requests, push-to-talk, the
      HTTP layer) before adding much more.
- [ ] The overlay gets in the way of a game (the author, 2026-11-17, by voice): when the
      mouse passes over the bar while playing, the bar reacts and takes the mouse (it
      unfolds, and a press there starts a drag instead of reaching the game). Their
      suggestion: the bar only answers to the mouse while `Ctrl+Alt` is held; otherwise the
      mouse goes straight through to what is underneath. As a setting, with choices such as
      always, only with the keys held, and (an idea, not asked for) only with the keys held
      while a full-screen program is in front. The keys already bring the panel out, so
      nothing is lost; dragging the bar would then also need the keys.
      Half done on 2026-11-17: the bar takes the mouse (drag, wheel, move cursor) only with
      `Ctrl+Alt` held (`overlay.drag_keys`). Still open: it unfolds whenever the mouse passes
      over it. A setting for that (unfold under the mouse: always, or only with the keys)
      has not been built; the author was not asked whether they want the unfolding gone.
- [ ] `first_audio` in `voice.log` is too high for a line whose first sentence is long (3 to
      8 s logged where the sound started within a second, as `heard` shows). The time is
      taken after the sentence was written to the player, and that write waits until the
      player has taken most of it. Take the time before writing.
- [ ] A hub that is running old code keeps old faults: a fix only counts once the hub was
      restarted. On 2026-11-17 a reply was cut by the author's own voice message two minutes
      after that fault was fixed and committed, because the hub had not been restarted yet.
      Say in `claude-speaks status` when the running hub is older than the code on disk.
- [ ] The picture check can catch the live overlay when the two overlap on screen.
- [ ] `install.sh` has only been run in throwaway folders, never on a clean machine with the
      model download.

## Not started

The author's direction for all of this: people who download the tool should be able to customize
as much of their experience as possible. New looks and behaviours come as settings, not as
replacements.

Bigger pieces:

- [ ] Make more of the overlay a setting: sizes, colors (session palette, status colors, glass
      tint), which keys do what, what the panel rows show, animation speed or none, where the
      bubble goes. Much is fixed in `overlay/Overlay.cs` today.
- [ ] More layouts as options. Three were built and removed on 2026-11-17 (lights sized by
      importance, a thin line of light at the screen edge, one small window per session); the
      code is in commit `8558c4a`.

- [ ] Any language, chosen by the person who installs it (the author, 2026-11-17, said in
      Italian: not only English and Italian, the program should be "customizzabile
      dall'utente che lo scarica", so in the end every language). Listening is nearly there:
      `whisper_language` already takes any language codes, or `auto`, with a multilingual
      model. What is still tied to English:
      - the start: the default model is English-only and nothing asks which languages you
        speak (see "To decide"). `install.sh` could ask, and the settings window should
        offer it.
      - the spoken summaries: the reminder asks Claude for "plain spoken English", and
        `hub/tts.py` has Kokoro pronounce every line as American English (`lang="en-us"`)
      - the voices: the pool is 13 English ones. The installed Kokoro file also has Italian
        (2), Spanish (3), French (1), Portuguese (3), Hindi (4), Japanese (5) and Chinese
        (8); any other language needs a second voice engine or the system voice.
      - the hub's own words ("Sent.", "Allowed.", "I need your input", "Permission needed")
        and the words in the overlay
      A first step that covers most of it: one `language` setting (or one per project) that
      picks the reminder's language, Kokoro's pronunciation and a voice pool for it, and
      falls back to English where Kokoro has no voice.
- [ ] A settings window for voices, keys and overlay options (the author's idea). Today these
      are a JSON file and the command line.
- [ ] Packaging as a Claude Code plugin, so it installs in one step.
- [ ] A demo video with sound and screenshots for the README, plus a measured comparison with
      tools that only speak after the reply has ended.
- [ ] Making the repo public.
- [ ] An adapter so other coding agents (Codex, Cursor and so on) get a light in the bar. The
      hub already takes plain events from anything that can send them.
- [ ] An overlay for Linux and macOS. Today it is Windows only.
- [ ] A version that runs on Windows itself, without WSL (the author, 2026-11-17, on learning
      that Claude Code started from PowerShell or cmd does not start any of this: it reads
      `C:\Users\<name>\.claude\settings.json`, which has no hooks). This is what a program
      other people download would need. What is tied to Linux today:
      - the hooks are bash scripts with `curl` and `jq`
      - the hub listens on a Unix socket, chosen so that no web page or other machine can
        reach it; the Windows version needs something as closed (a named pipe, or a Unix
        socket if Python on Windows supports it by then)
      - one hub at a time is kept by `flock`
      - sound goes out through `paplay`, and the microphone and the loudness meter read
        through `parec`
      - folders follow the Linux layout (`XDG_RUNTIME_DIR`, `~/.local/state`, `~/.config`)
      - the hub finds and starts the overlay through `wslpath` and `/mnt/c`
      Not tied to Linux: the overlay program, Kokoro and `faster-whisper` (both run on
      Windows), and the hub's logic. A smaller step that was set aside for now: hooks in the
      Windows settings file that call into WSL and run the existing scripts.
- [ ] Voice cloning, if that is what "uploadable" meant (see above). The author asked on
      2026-11-17 how to get a voice of their own choosing ("they're all preset"). Researched
      the same day, nothing tried yet; all routes are free and local except the last:
      - Pocket TTS (Kyutai, MIT, about 100M parameters): clones from a WAV file, runs on the
        CPU, about 0.2 s to first sound by its own README, speaks English and Italian. The
        closest fit as a second engine beside Kokoro; first one to measure.
      - Chatterbox Turbo (Resemble, MIT, 350M, English): more expressive (`[laugh]` tags,
        an exaggeration setting), wants the graphics card (RTX 5070 here). Its repo now says
        it is no longer maintained, and the speed claims are the vendor's.
      - KVoiceWalk (Apache 2.0): searches for a Kokoro voice vector that resembles a
        recording, so no new engine and the result loads through `voice add`. About 4 hours
        on a graphics card per voice, results vary, and it copies the tone, not the manner.
      - ElevenLabs: best quality, about 5 to 6 dollars a month, but the text leaves the
        machine and every line costs credits.
      A cloned voice of a real person needs that person's consent under these tools' terms
      (Pocket TTS and ElevenLabs say so outright), so the feature is "bring your own
      recording" and no cloned voices ship in the repo.
      The author wants this (2026-11-17: a realistic copy of one person's voice, with that
      person's approval; "put this in the to-do list and I'll definitely try something").
      What it takes:
      - from the author: one recording of that person, a single voice with no music or
        noise, about 10 to 30 seconds, as a WAV file, spoken the way the voice should
        sound (the engines copy the manner of the clip, not only the tone) and in the
        language it will speak (an Italian clip made to speak English keeps an accent)
      - to build: a second engine in `hub/tts.py` beside Kokoro, and `voice add` taking a
        recording; choosing a voice per project already works
      - order to try: Pocket TTS first (the only one likely to keep the quick start of
        speech), Chatterbox if it does not sound real enough, ElevenLabs as the paid
        yardstick
      - the recording stays on the author's machine, never in the repo

- [ ] Sessions in an order of your own (the author's idea, 2026-11-17): hold `Ctrl+Alt`,
      take a light with the mouse and drop it where it should sit in the bar. The hub keeps
      the order (by project, so it survives restarts) and new sessions join at the end. Fits
      the dragging the bar already has: with the keys held a drag moves one light, without
      them the whole bar.
- [ ] Usage in the overlay (the author's idea, 2026-11-17: "customizable bar that shows the
      usage, the five-hour window and the weekly usage"): a part of the overlay that shows how
      much of the plan is used up, in the five-hour window and in the week, and when each
      starts again. A setting like the rest: on or off, where it sits, what it shows.
- [ ] Context window per session (same day: "for each session maybe something that indicates
      the context window"): a sign of how full each session's context is, for example a thin
      arc around its light and a figure in its row, with a warning color when it is nearly
      full.
      Nothing looked into yet for either. The hub has no source for these numbers today; to
      check first: what Claude Code hands to a status line command (it gets a JSON about the
      session, which may carry both), and whether context use can be counted from the
      transcript a hook points to.

Away from the PC (the author's idea, 2026-11-17: with sessions open and nobody at the desk,
"is it possible to use like either phone or AirPods interaction to do stuff", for example an
AirPods gesture that starts push-to-talk). Nothing below has been tried; the notes are
guesses to check first.

- [ ] AirPods paired with the PC: a press on the stem reaches Windows as a media key
      (play/pause, next, previous). The overlay could claim one as a talk key: press to start
      recording, press again to send, since a press cannot be held. To check: whether the
      overlay can take the key away from the music player, how to keep it out of the way
      while music plays (only claim it while a session is open?), and how bad the sound gets
      when Windows switches the AirPods to their microphone mode (playback drops to phone
      call quality while the microphone is open). Works only within Bluetooth range.
- [ ] AirPods on the phone, PC out of range: the phone has to be the bridge, because the
      gestures cannot be given to another program there. Candidates:
      - a phone Shortcut ("Hey Siri, tell Claude ...", or the Action button) that dictates a
        sentence and runs `claude-speaks follow-up` on the PC over SSH. Needs no new server,
        only a private way to reach the PC (for example Tailscale).
      - spoken summaries as phone notifications; the phone can read notifications aloud
        into AirPods. This grows out of the "phone notification" idea below.
      - allow and deny from the phone: buttons on the notification, or a Shortcut that runs
        `claude-speaks allow|deny`.
      - a small phone app of our own could read AirPods head movement (nod to allow, shake
        to deny) and stream the voice. By far the most work.
      - Claude Code's own remote control from the phone may already cover typing and
        approving; check what it does before building any of this.
- [ ] Decide the safety line first. The hub listens on a Unix socket on purpose, so that
      nothing outside this machine can make it speak, approve or inject. Anything from a
      phone opens that door a little: it should go through a login that already exists
      (SSH), never a new open port, and approving from afar may deserve its own switch.

Smaller ideas:

- [ ] Easier ways to take back what you said (the author, 2026-11-17: "it would be really
      cool to somehow cancel with a shortcut"; today it is `Ctrl+Alt+Backspace` while the talk
      key is still held, a four-key grip). Ideas offered, none chosen yet:
      - `Esc` while recording throws it away (claimed only while the talk key is down)
      - a short take-back window after letting go: the words show for a second or two and
        `Esc` or `Backspace` alone stops them; no key means sent (`followup_delay` already
        gives the wait, the single key is missing)
      - a spoken ending: "never mind" or "scratch that" as the last words discards it
      - a right click or wheel click while holding the talk key, for a hand on the mouse
      - tap the talk key twice right after sending to unsend; if the session already has
        the words, send "ignore my last message" after them
      - the same single key cuts the line being spoken when nothing is being recorded
- [ ] A setting that keeps every key from other programs while `Ctrl+Alt` is held (the
      author's idea, 2026-11-17, after Space paused a video during push-to-talk). Built so
      far: only the held talk key is kept back. Off by default if built, because it would
      also take other programs' `Ctrl+Alt` shortcuts and the characters some keyboards type
      with those keys, and it needs a keyboard hook for as long as the keys are down.
- [ ] Short sounds for states (done, needs you) for when a full sentence is too much. Push-to-talk
      has them since 2026-11-17 (`hub/sounds.py`: sent, waiting, not sent); the author has
      not said yet whether they sound right. "Allowed." and "Denied." are still spoken.
- [ ] Left or right ear per session
- [ ] Stay quiet for the session whose terminal is in front
- [ ] A key that jumps to the terminal of the session in focus
- [x] Tell the terminals apart (the author, 2026-11-17, with four terminals open in VS Code:
      "I cannot distinguish which", and later "is there a possibility to highlight the
      terminal" of the session selected in the overlay). Built the same day, no extension:
      the terminal of the session in focus takes a faint tint of its overlay color and
      lights up brighter when the focus is moved to it (`hub/terminal.py`, `claude-speaks
      terminal`). The author saw it and said "maybe the flash might be too much", then
      "less tint maybe"; at 0.08 of the color for the tint and 0.15 for the flash (from
      0.14 and 0.42) they said "looks good". Not asked: whether every terminal should
      wear its color all the time (`terminal tint all`).
- [ ] Session names in the terminal's tab. The hub can write "name · title" as the
      terminal's title (`terminal title on`), but a VS Code tab only shows it with
      `"terminal.integrated.tabs.title": "${sequence}"`, and Claude Code overwrites it
      unless started with `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1`. Both are the author's to
      turn on; offered on 2026-11-17, not answered, not tried.
- [ ] The terminal tint on a light theme: the color is mixed into `terminal.background`,
      which defaults to VS Code's dark theme. Read the editor's theme, or offer a light
      default.
- [ ] A small VS Code extension: the only way to color the tab itself and to bring a
      terminal to the front (the jump key above).
- [ ] The focus follows the terminal you click (the author's idea, 2026-11-17: "whenever I
      ... click on a terminal automatically the overlay ... select that ... session"). The
      other way round exists: the terminal of the session in focus is tinted. Looked at
      the same day, nothing built:
      - The hub cannot see which terminal has the keyboard. It can write to a session's
        terminal but not read what the terminal sends back (that goes to Claude Code),
        and the terminal's own "last used" time is only kept to the nearest 8 seconds by
        Linux and moves for the terminal that loses the keyboard too.
      - Claude Code knows when its terminal gains the keyboard, but its session file does
        not say so and no hook reports it (to check in its documentation, in case one
        has been added).
      - Reliable: the small VS Code extension above. VS Code tells an extension which
        terminal is active the moment it changes, with the terminal's process, which
        leads to the session; the extension tells the hub. Only for VS Code; another
        terminal program would need its own way.
      - Without any of that: the focus already goes to a session when it speaks, so one
        you type to gets it with its reply. It could move at the moment you send the
        prompt instead; that is a few lines in the hub.
- [ ] Not tried: ringing a terminal's bell when its session speaks, which VS Code can show
      as a small sign on the tab for a moment (its visual bell setting is off by default).
- [ ] A phone notification when a session needs you and you are away
- [ ] Spoken summaries in the language you spoke (they are always English today; part of
      "Any language" above)
- [ ] Running the speech model on the graphics card to make transcription faster
