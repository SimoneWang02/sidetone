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

- [ ] Voice of this project: it speaks with `bf_isabella` since the voice pool changed. Pin
      the earlier `af_heart` back? (`claude-speaks voice claude-speaks af_heart`)
- [ ] "Uploadable" voices: was that cloning a voice from a recording? Kokoro cannot do it; it
      would need a second voice engine.
- [ ] Should the repo default for push-to-talk be the multilingual model? Today the default is
      English-only and the author's own settings switch it to English plus Italian.
- [ ] Should a quick tap of the talk key also stop at the last session, like the wheel? It
      still goes round.

## Rough edges

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

Bigger pieces:

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

Smaller ideas:

- [ ] Short sounds for states (done, needs you) for when a full sentence is too much
- [ ] Left or right ear per session
- [ ] Stay quiet for the session whose terminal is in front
- [ ] A key that jumps to the terminal of the session in focus
- [ ] A phone notification when a session needs you and you are away
- [ ] Spoken summaries in the language you spoke (they are always English today)
- [ ] Running the speech model on the graphics card to make transcription faster
