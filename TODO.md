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

- [ ] A hub restart forgets the order of the sessions in the bar (they come back in the order
      they next report something) and the titles that came from a prompt (a session Claude
      Code has not named shows only its folder until the next prompt). The author noticed
      both on 2026-11-17. Keep order and titles in a small file, like the waiting follow-ups.
- [ ] A session started by voice keeps Claude Code's placeholder name (the folder plus two
      letters, "claude-speaks-3f"). The hub now ignores that name and uses the prompt, typed
      or spoken, but see the restart item above.
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
- [ ] Voice cloning, if that is what "uploadable" meant (see above).

- [ ] Sessions in an order of your own (the author's idea, 2026-11-17): hold `Ctrl+Alt`,
      take a light with the mouse and drop it where it should sit in the bar. The hub keeps
      the order (by project, so it survives restarts) and new sessions join at the end. Fits
      the dragging the bar already has: with the keys held a drag moves one light, without
      them the whole bar.

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

- [ ] Short sounds for states (done, needs you) for when a full sentence is too much
- [ ] Left or right ear per session
- [ ] Stay quiet for the session whose terminal is in front
- [ ] A key that jumps to the terminal of the session in focus
- [ ] A phone notification when a session needs you and you are away
- [ ] Spoken summaries in the language you spoke (they are always English today)
- [ ] Running the speech model on the graphics card to make transcription faster
