# Status and roadmap, as written in the first days

Moved here unchanged from `CLAUDE.md` on 2026-11-19. What is left now is in `TODO.md`.

## Status (as of 2026-11-18)

- Working day to day on the author's machine (WSL2 Linux). Since 2026-11-16 the live hooks run
  **from this repo**: `~/.claude/settings.json` points at `~/personal/sidetone/hooks/`.
  Rollback: `~/.claude/settings.json.bak-before-hub` plus the old scripts in `~/.claude/hooks/`.
- Not yet packaged as a plugin. Paths outside the repo: `~/.local/share/{kokoro,piper}`.
- `README.md`, `LICENSE` (MIT) and `install.sh` / `uninstall.sh` exist since 2026-11-16. The
  install script merges the hooks into an existing `settings.json` (tested on a throwaway home
  folder). Its download and environment steps ran on 2026-11-17 in an empty home folder
  with nothing cached (22 s, 906 MB; the hub from that install spoke and its speech model
  wrote the sentence back), not yet on a machine without the apt tools and `uv`. It also
  fetches the Whisper model since then; before, the first push-to-talk waited for it.
- Private GitHub repo: github.com/SimoneWang02/sidetone. Claude may commit and push.

## Roadmap (decided with the author 2026-11-16)

1. **Hub and voice queue**: done; the author confirmed it by ear on 2026-11-16.
2. **Windows overlay**: built 2026-11-16; waiting for the author's check by eye (look, position,
   `Ctrl+Alt+L`, behaviour over a game). Native window (PowerShell + WPF, started by the hub, JSON
   lines over stdin/stdout), see-through and click-through. Two modes: faint dots that expand to
   one line on a change, and a full list.
3. **Allow or deny by hotkey**: built 2026-11-16 and verified end to end against a real session
   through `sidetone allow|deny`; the author still has to try the actual `Ctrl+Alt+Y` /
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
- Overlay polish: monitor choice, drag to move (`sidetone overlay move`), history on hover.
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
- `sidetone` and `st` (then `claude-speaks` and `cs`) are linked into `~/.local/bin` by `install.sh`

Decisions: overlay is Windows-native (must be usable over games; no browser chrome);
sessions are told apart by a spoken label plus a stable voice per project.
What is left (things to try by hand, open decisions, rough edges, ideas not started) is kept in
`TODO.md`; the author asked for that list to live in its own file. Update it when something
on it is done or a new idea comes up.
