# Product

<!-- impeccable:product-schema 1 -->

Written by `/impeccable init` on 2026-11-26 from `README.md`, `CLAUDE.md`, `TODO.md`,
`docs/dev/name-and-logo.md` and the author's spoken answer that day. It is read by the
Impeccable design skill; `CLAUDE.md` stays the authority for everything else.

## Platform

web

## Users

People who code next to Claude Code, often with several sessions open, and want to keep their
eyes on their own work while the sessions run. The author built it for themself and uses it
every day on Windows 11 with WSL2. It is not public yet; a public version is planned.

Two kinds of web page exist or are planned here, each with its own reader:

- **Preview pages.** Read by the author, to choose a look before it is built in the overlay.
  The author listens more than reads and judges by what is shown.
- **Documentation about the tool** (future). The author, 2026-11-26: "documentation about this
  tool". Who exactly reads it has not been discussed.

## Product Purpose

Eyes-free Claude Code. A local voice says, in one or two sentences, what each session just
did, and starts while the reply is still streaming. A small overlay shows each session's
state, and you answer by hotkey or by talking, without changing windows.

It exists because of attention latency: the model is fast, and the slow part is the person
noticing a session and switching to it. Sidetone cuts that delay in both directions. Success
is that you keep your eyes on your own work.

## Positioning

- Everything runs on your machine: no cloud speech service and no extra model call. Claude
  writes its own spoken line as the first line of its reply.
- It speaks early: sound comes out about 0.3 s after the line is written (measured on the
  speakers' own output), often before the rest of the reply has printed.
- Several sessions take turns, one line at a time, each with its own voice and color, and
  "needs you" goes before "done".

## Operating Context

- The person works in their own windows; Claude Code sessions run in terminals or VS Code
  beside them. The overlay is a slim glass bar that never takes focus.
- How a look gets decided: it is agreed first, then shown (pictures from
  `tests/overlay_check.py`, or live), with gaps measured in pixels. Preview pages in
  `docs/dev/looks/` show candidate looks side by side before one is built
  (`characters.html` is the one the characters were built from).
- The overlay itself is not a web page. It is WPF, drawn by `overlay/Overlay.cs` (C# 5).
  A preview is only useful when it shows what the overlay can really draw.

## Capabilities and Constraints

- What Impeccable can work on here: the preview pages, and the documentation once it is a
  web page. It cannot read or check the overlay's own code.
- New looks and behaviours come as settings with sensible defaults, not replacements (agreed
  2026-11-21): people who download it should be able to customize as much as possible.
- Words the product uses: session, hub, overlay (bar, panel, bubble), spoken line,
  "needs you", push-to-talk, follow-up, side question.
- Status: works day to day on one machine. Not yet a plugin, not yet public, Windows overlay
  only.
- Impeccable's hooks are on (the author, 2026-11-26: "turn them on"). Its telemetry is off
  and live mode's Apply step is off.

Undecided:

- The documentation's form. The author plans Markdown and asked whether there is a better
  option. It is the last step of the plan (`TODO.md`, step 7), on the author's word, and is
  not to be offered before then.
- Which features the first public version has (`TODO.md`, step 5).

## Brand Commitments

- The name is Sidetone: the sound of your own line in a headset, which tells you it is alive
  while you work. It was called claude-speaks until November 2026.
- The color is `#006896`, chosen by the author. White on it reads well (6.1 to 1). On dark
  glass it is too faint for thin lines and words, which use a lighter step, `#2E9CC9`.
- The logo is `assets/logo.png`: a round light with voice bars in it and an arc around it.
  Its history is in `docs/dev/name-and-logo.md`.
- Writing: first person, plain words, claims with their measurements. Labels and setting
  names in title case; descriptions stay sentences.

## Evidence on Hand

- `README.md`: what the tool does, with measured numbers.
- `docs/dev/features.md` and `docs/dev/facts.md`: how each part works, and what was measured.
- `docs/dev/looks/`: nine preview pages.
- `tests/overlay_check.py OUT_DIR`: a picture of every overlay view, taken from the overlay's
  own windows. Single views, not motion.
- Absent, and not to be made up: a demo video, GIFs of features, screenshots in the README,
  a measured comparison with other tools, testimonials, numbers of users.

## Product Principles

1. Eyes stay on your own work. Anything that makes the person look or switch windows needs a
   reason.
2. Short over complete. One or two sentences, never the full output.
3. Local. No cloud speech service and no extra model call.
4. Settings, not replacements. A new look or behaviour is an option with a sensible default.
5. Show it and measure it. A look is agreed on what is shown, and a claim comes with its
   measurement.
