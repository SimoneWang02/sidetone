# Overlay redesign: the prompt for Claude Design

Written 2026-11-25 from four research passes (layouts, motion, characters, customization and
prompting). Paste everything under "The prompt" in a new conversation, with no design system and
no screenshot attached (a picture of today's overlay pulls every design towards it). Then one
line at a time from "After it". Nothing here is built or decided.

## The prompt

Design 50 radically different versions of a desktop overlay. Be bold about form, graphics,
materials, characters and motion; be strict about what must be shown. I will pick and mix, so
I want range, not 50 polished versions of one idea.

**What it is.** Sidetone is a Windows overlay for someone running several AI coding sessions at
once. A voice reads one sentence per turn and the person answers by voice, so their eyes stay on
their own work. The overlay is seen from the corner of the eye. At a glance it must say: does
anyone need me, who, and who is speaking?

**Show the same content in every design**
- Five sessions, in an order that never changes: "sidetone" (done: "Pushed, all up to date."),
  "api-server" (working: "Running the tests", 6m, context 56%, tasks 3/5), "web-app" (needs you:
  "Which drink would you like?", context 83%), "data-pipeline" (failed: "error: rate limit"),
  "notes" (idle). Each has its own color, a name and a short title. One is selected.
- Those five are only a sample with one session per state. Every design must work from 1 to 20
  sessions (draw 5 and 12 in the rough round, 1 and 20 as well in later ones): several can be in the same state, three can need me at
  once, and two can share a project name. Say what happens as they grow (shrink, fold, group,
  page) and where it breaks. Sessions that need me, speak or are selected never fold away; folded
  ones keep their place and a count by state. The footprint may not grow in step with the number.
  Past about 8 sessions color cannot identify them, so name, place or shape must.
- Speaking: api-server says "All forty two tests pass." with a voice-reactive element.
- A permission request: web-app wants to push to the remote, `git push origin main`, with
  Ctrl+Alt+Y allow and Ctrl+Alt+N deny, and "2 more waiting". Keep allow and deny well apart.
- A question with four options and, separately, one with boxes to tick.
- Push-to-talk: listening, transcribing, sent, didn't catch that, and one message waiting for a
  busy session. A session being stopped.
- Two subagents of api-server: appearing, working, finishing. Context emptying after a clear.
- History of the last spoken lines, some missed. Plan usage: 5-hour and week.

**Characters.** Many rows use an original plushie family: one per session in that session's
color, smaller ones (60%) for subagents, with props per task (magnifier to search, needle and
thread to edit, spring to test, books to research, measuring tape to review, paper plane to
deploy, teacup to wait). Invent them. No existing characters or lookalikes, and nothing like
Anthropic's Clawd: no crab, claws, boxy clay-orange body, slit eyes or starburst. No Claude or
Anthropic logos. Must read at 24 px (body, two eyes, one state change), 32 (one prop), 48
(costume), 64 (stitching, mouth). Every state must be recognizable as a black silhouette.

**Motion**
- Only "needs you" may loop noticeably: a slow sway in place, about once a second, for 5 seconds,
  then a still, obvious sign; a short reminder at 30 seconds and 2 minutes, then no more.
- Working is barely moving. Idle is still, with a rare blink. Done settles once (0.4 s). Failed
  slumps once and stays down: no shaking, no flashing. Listening reacts within 0.1 s. Speaking
  follows the voice, in place.
- One thing moves at a time. Nothing travels across the screen, follows the cursor, covers work,
  begs for care or celebrates for over 2 seconds. A short flight on sending is fine.
- Every design has Reduce Motion and Off, and every state survives as a still frame.

**Rules**
- Never color alone. Attention changes form or motion, never the order. It never steals keyboard
  focus. Readable over light, dark and busy desktops.
- Customizable through slots, each with "none" and a default: frame (form, place, size, density),
  skin (material, palette, type), session token, state map, motion level, character (family,
  face, outfit, accessory, color, size, per session), scene, event effects. Presets to duplicate,
  plus lock-and-shuffle and import/export.
- Banned: glass pills with dots, neon on black dashboards, grids of rounded cards, purple
  gradients, sparkle icons, Inter, Roboto, Arial or Space Grotesk, a mascot pasted in a corner,
  and recolors of another design. Already tried and refused: rows that grow, and a card floating
  over the rows below it.

**How to work**
1. Now: write one line per row of the table, the idea and what makes it unlike the others. For
   each, think of several and take one you would not have reached for first. If a combination
   clashes, use the clash; change a value only if it is impossible, and say so. Then stop.
2. When I say "batch N", draw rows 5N-4 to 5N, each on its own artboard, rough: the idle overlay
   on a desktop, all five sessions, a crowded 12, the permission request, listening, and a gray 64 px
   silhouette. Animate one moment per design in code. Before drawing, list the forms already used.
3. After each batch, score every design 1 to 5 on: difference from all the others, one-second
   glance, still clear with 20 sessions, small footprint, motion with meaning, can be built in
   WPF, charm. Redo any with less than 3 on difference or on 20 sessions. This round, a low WPF score is fine: just say why.

**The table** (form / a session is a / material / world / state shown by / motion / density / characters)

1. screen-edge light / planet / clay / theatre / pose or tilt / hand-drawn frames / on demand / holds the marker: Unfolding triangles
2. badges on each window / plushie / ceramic / botany / face / weight and gravity / on demand / is the session: Stacked felt stones
3. tiny diorama / voice waveform / pure light / Bauhaus / silhouette / fluid / card / holds the marker: Pom-poms
4. tiny diorama / plushie / paper / toy shop / fill level / breathing / peripheral only / is the session: Banded ear puffs
5. radial dial / lit window in a building / pixels / Memphis / brightness / mechanical ticks / stacked cards / none
6. top island / plushie / ink / theatre / position / breathing / stacked cards / is the session: Felt bells
7. taskbar strip / plushie / clay / illuminated manuscript / pose or tilt / breathing / one line / is the session: Folded-corner beanbags
8. free-floating objects / paper card / ceramic / Memphis / pose or tilt / soft spring / card / holds the marker: Patchwork cushions
9. free-floating objects / train on a line / paper / aviation / texture / still frames / stacked cards / none
10. taskbar strip / train on a line / pure light / cartography / line weight / mechanical ticks / card / none
11. badges on each window / paper card / pure light / illuminated manuscript / face / still frames / icon / speaks the bubble: Thread spools
12. tiny diorama / planet / CRT glass / cartography / face / soft spring / stacked cards / holds the marker: Wobbling teardrops
13. radial dial / train on a line / ceramic / transit signs / pose or tilt / stop-motion / icon / none
14. badges on each window / voice waveform / clay / Memphis / line weight / breathing / icon / none
15. pull-out drawer / instrument / pure light / botany / brightness / soft spring / one line / none
16. pull-out drawer / plushie / paper / theatre / texture / fluid / one line / is the session: Fat-cord knots
17. top island / planet / woven fabric / botany / silhouette / breathing / card / none
18. screen-edge bar / train on a line / brushed metal / night market / texture / fluid / icon / conductor of all: Bolster cushions
19. tiny diorama / lit window in a building / clay / aviation / position / weight and gravity / on demand / speaks the bubble: Quilted domes
20. screen-edge bar / plushie / woven fabric / toy shop / face / still frames / card / is the session: Hot-water bottles
21. top island / light / CRT glass / cartography / pose or tilt / still frames / on demand / conductor of all: Rolled cuffs
22. badges on each window / voice waveform / felt / cartography / fill level / mechanical ticks / one line / speaks the bubble: Felt tags
23. top island / plushie / felt / transit signs / face / hand-drawn frames / full board / is the session: Unzipping seed pods
24. free-floating objects / instrument / ceramic / illuminated manuscript / line weight / weight and gravity / full board / none
25. radial dial / instrument / CRT glass / theatre / face / breathing / card / desk pet: Pincushions
26. screen-edge bar / plushie / CRT glass / illuminated manuscript / line weight / soft spring / icon / is the session: Drawstring pouches
27. free-floating objects / plushie / ink / toy shop / line weight / stop-motion / one line / is the session: Duffel toggles
28. radial dial / lit window in a building / woven fabric / transit signs / line weight / hand-drawn frames / on demand / conductor of all: Comma curls
29. corner cluster / light / pixels / Bauhaus / fill level / soft spring / full board / none
30. taskbar strip / paper card / CRT glass / botany / texture / still frames / one line / desk pet: invent a family
31. screen-edge bar / paper card / ink / night market / position / still frames / full board / none
32. screen-edge light / plushie / brushed metal / aviation / texture / mechanical ticks / full board / is the session: invent a family
33. free-floating objects / instrument / ink / Memphis / brightness / fluid / peripheral only / speaks the bubble: invent a family
34. screen-edge light / paper card / felt / toy shop / silhouette / soft spring / stacked cards / none
35. radial dial / planet / pixels / Bauhaus / silhouette / stop-motion / on demand / speaks the bubble: invent a family
36. taskbar strip / voice waveform / ink / toy shop / position / mechanical ticks / icon / conductor of all: invent a family
37. corner cluster / plushie / pixels / cartography / position / hand-drawn frames / peripheral only / is the session: invent a family
38. top island / train on a line / paper / night market / brightness / mechanical ticks / full board / desk pet: invent a family
39. screen-edge bar / plushie / clay / Bauhaus / silhouette / weight and gravity / full board / is the session: invent a family
40. screen-edge light / voice waveform / brushed metal / theatre / position / fluid / peripheral only / none
41. screen-edge light / plushie / pure light / night market / face / fluid / stacked cards / is the session: invent a family
42. taskbar strip / lit window in a building / paper / botany / fill level / stop-motion / on demand / none
43. pull-out drawer / light / pixels / transit signs / silhouette / weight and gravity / one line / desk pet: invent a family
44. pull-out drawer / light / woven fabric / aviation / brightness / mechanical ticks / card / holds the marker: invent a family
45. badges on each window / instrument / brushed metal / Bauhaus / texture / stop-motion / card / none
46. corner cluster / plushie / woven fabric / transit signs / brightness / breathing / icon / is the session: invent a family
47. pull-out drawer / planet / brushed metal / night market / fill level / hand-drawn frames / peripheral only / desk pet: invent a family
48. tiny diorama / light / ceramic / Memphis / silhouette / hand-drawn frames / peripheral only / none
49. corner cluster / lit window in a building / felt / illuminated manuscript / pose or tilt / stop-motion / peripheral only / conductor of all: invent a family
50. corner cluster / plushie / felt / aviation / fill level / weight and gravity / stacked cards / is the session: invent a family

## After it

- `batch 1` up to `batch 10`.
- `Put all 50 side by side as gray silhouettes and name the pairs that look alike.`
- `Take numbers A, B, C, D and E further, and make two blends: the form of X with the characters
  of Y. These must be buildable in WPF (.NET Framework, C# 5): vector shapes, transforms and
  opacity, no web engine. Full state sets, with sliders for size, density and motion.`
- `Animate the best two: every state change, Reduce Motion, and the character creator.`
