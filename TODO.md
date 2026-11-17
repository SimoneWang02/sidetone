# To do

What is left for claude-speaks, as of 2026-11-17. Everything asked for so far is built; this
is what has not been tried by hand, what is undecided, what is rough, and what has not been
started. `CLAUDE.md` has the details of how things work.

## To try by hand

These work in the automated tests or in pictures taken from WSL, but nobody has pressed the
real keys yet.

- [ ] Push-to-talk in Italian with a real voice (tested only with synthesized Italian voices;
      very short phrases such as "Ciao Claude, mi senti?" were the weak spot)
- [ ] Hold `Ctrl+Alt`: the details panel comes out while the keys are held
- [ ] `Ctrl+Alt` + mouse wheel: the focus moves, and stops at the first and last session
- [ ] `Ctrl+Alt+Y` / `Ctrl+Alt+N` on a real permission prompt
- [ ] `Ctrl+Alt+1` to `4` on a real multiple-choice question
- [ ] `Ctrl+Alt+U` (what did I miss) and `Ctrl+Alt+R` (repeat)
- [ ] `Ctrl+Alt+Backspace` while recording
- [ ] The bar over a game in borderless windowed mode
- [ ] A plain click on the bar reaching the window underneath
- [ ] Sessions started from the VS Code extension showing up in the bar

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
- [ ] A session Claude Code has not named (one started by voice) gets its title from the
      spoken line of its first reply, which is the start of a sentence, not a real title.
      Better: ask Claude for a title of a few words in that first reply.
- [ ] Something said to a busy session waits until its reply ends, and a turn stuck on an
      unanswered dialog in the terminal holds it back for as long as the dialog is open. The
      overlay shows "waiting" for 3.5 s only; the author took it as not heard (2026-11-17).
      Keep the waiting sign on that session's light until the words are delivered, and say
      "Queued." instead of "Sent.".
- [ ] Some push-to-talk holds record sound and come back as "nothing heard". Some were
      Italian before the multilingual model, but at least one was English. Cause not found: the
      microphone delivers signal at once, and loudness made no difference in tests. Next
      step: keep the last failed recording (opt-in) so it can be examined.
- [ ] A misheard sentence is sent straight to the session: there is no pause and no confirming
      tap any more (the author's choice). `followup_delay` and `followup_confirm` bring them back.
- [ ] A permission prompt that waited more than six seconds and is then approved in the
      terminal stays "needs you" until that tool finishes.
- [ ] The number keys only answer single-choice questions with up to four options.
- [ ] The spoken project name is off while the overlay is up; with many sessions and eyes
      away from the screen, the voices alone may not be enough to tell them apart.
- [ ] `hub/hub.py` is over 1,100 lines. Split it (permission requests, push-to-talk, the
      HTTP layer) before adding much more.
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

- [ ] A settings window for voices, keys and overlay options (the author's idea). Today these
      are a JSON file and the command line.
- [ ] Packaging as a Claude Code plugin, so it installs in one step.
- [ ] A demo video with sound and screenshots for the README, plus a measured comparison with
      tools that only speak after the reply has ended.
- [ ] Making the repo public.
- [ ] An adapter so other coding agents (Codex, Cursor and so on) get a light in the bar. The
      hub already takes plain events from anything that can send them.
- [ ] An overlay for Linux and macOS. Today it is Windows only.
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
- [ ] Short sounds for states (done, needs you) for when a full sentence is too much
- [ ] Left or right ear per session
- [ ] Stay quiet for the session whose terminal is in front
- [ ] A key that jumps to the terminal of the session in focus
- [ ] Mark the terminal of the session that is speaking (the author, 2026-11-17, with four
      terminals open in VS Code: "I cannot distinguish which"). Checked the same day: every
      session's terminal can be found from its process and written to by the hub (five
      sessions, each on its own terminal, all inside VS Code). Not tried: what to write.
      - ring that terminal's bell when its line starts: VS Code should show a bell sign on
        the tab for a moment. No extension needed; the sign is small and short.
      - write the session's name and state into the tab title. VS Code only shows such a
        title when its tab title setting includes the sequence, and Claude Code sets a
        title of its own that may overwrite it.
      - a small VS Code extension that gives each tab the session's color from the overlay
        and can bring the speaking terminal to the front. The only way to color a tab, and
        it would also give the jump key above. The most work.
- [ ] A phone notification when a session needs you and you are away
- [ ] Spoken summaries in the language you spoke (they are always English today)
- [ ] Running the speech model on the graphics card to make transcription faster
