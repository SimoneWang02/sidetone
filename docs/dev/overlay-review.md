# Overlay review

A critical review of today's overlay and of the three looks in `docs/dev/looks/`, written
2026-11-25 by a session opened for it (the author asked the session making the aquarium to open
one). Analysis only: nothing was changed, restarted or run on the author's screen. The 50 designs
from Claude Design are not in here yet; their part is at the end, waiting for screenshots.

## How it was scored

Six things, 1 to 5 each, the ones the redesign prompt asks of every design:
one-second glance (does anyone need me, who, who is speaking), clear with 20 sessions, small
footprint, motion with meaning, buildable in Windows, charm. Footprint is counted against
today's closed bar: 5 is that size, each point down is about twice as much screen.

Every claim below is marked by where it comes from:

- **seen**: in a picture. Today's overlay: pictures other sessions took with
  `tests/overlay_check.py` on 2026-11-24 and 25 (closed bar, speaking bubble, open details,
  clearing, settings). The looks: rendered for this review in a headless browser, at 5, 12 and 20
  sessions, at page size and at 460 px wide.
- **code**: read in the source, not seen in a picture.
- **guess**: my judgement, to be checked.

Not seen at all, so not scored from sight: a permission request, a question, listening, the
island layout, Selected Session, history, and today's overlay with more than five sessions.
`overlay_check.py` would show them; it was not run (it opens a test overlay on the screen).
Motion was read in the code and in stills, never watched.

## Scores

| | Today | Plushies | Aquarium | Living aquarium |
|---|---|---|---|---|
| One-second glance | 4 | 3 | 3 | 3 |
| Clear with 20 sessions | 2 | 2 | 2 | 3 |
| Small footprint | 5 | 4 | 1 | 2 |
| Motion with meaning | 3 | 4 | 3 | 2 |
| Buildable in Windows | 5 | 4 | 4 | 2 |
| Charm | 2 | 4 | 4 | 5 |
| **Total of 30** | **21** | **21** | **17** | **17** |

None of the three looks beats today's overlay. The plushies tie it: they bring the charm it
lacks and lose the glance it has. The two aquariums are the most charming and the furthest from
what an overlay is for. The other session's quick score for today's, from one picture, was 22;
this 21 was reached before comparing, and only its total is known here.

## Today's overlay: 21

- **One-second glance, 4.** Seen: five states, each with its own shape and color on dark glass
  (check, turning arc, "!", cross, small ring), 26 px discs in a 52 by 228 px bar. "Does anyone
  need me" is answered at once, and without color vision. "Who is speaking" is answered by the
  bubble: name in its color, title, sentence, the voice behind the words. "Who" is the weak part:
  the closed bar carries no name and no session color, only a place in the column. Small, seen:
  api-server's orange name sits one step from the amber of "needs you".
- **Clear with 20 sessions, 2.** Code, not seen: one light per session at 44 px
  (`Overlay.cs:2650`), in a plain stack (`:2834`) placed with no check on its height (`:5001`).
  Twenty sessions make a bar 888 px tall: it fits a 1080p screen at 100 % with 48 px to spare
  and runs off the bottom at 125 %, at a larger Size, or on a laptop. No fold, no group, no
  count by state. The details for 20 rows are taller than the screen too (`:5045` holds the top,
  not the bottom). Place cannot name the thirteenth of twenty lights. The shapes stay distinct,
  which is why this is not a 1.
- **Small footprint, 5.** Seen: 52 by 228 px closed, about half a percent of a 1080p screen;
  details and bubble only when wanted; clicks pass through. That it grows 44 px a session is
  counted under 20 sessions, not twice.
- **Motion with meaning, 3.** Code: every state has a motion of its own, and the best are very
  good (the check drawn stroke by stroke, the ring on a change, bars that follow the real
  voice). The order of loudness is wrong. Working, the commonest and least urgent state, is the
  busiest thing on the bar: an arc at 0.73 turns a second (`:465`). "Needs you" pulses at 0.72 a
  second (`:479`) and never settles. The routine and the urgent move at the same tempo and differ
  only in hue and shape, and shape is what the corner of the eye loses first (guess: how much
  this matters in use is the author's to say). Both keep the frames running for as long as any
  session works or waits (`:417`), which is most of the day.
- **Buildable in Windows, 5.** It is built, tested and in daily use.
- **Charm, 2.** Seen: clean, even, well made, and anonymous. The five signs are the ones every
  build dashboard uses; nothing in the closed bar says Sidetone, not even its blue. It is the
  "glass pill with dots" the redesign prompt bans. The charming parts exist (the dismayed face
  past nine messages, the paper plane) but are rare states, not seen here.

### The three biggest problems

1. **It stops working past about eight sessions.** No fold, group or count; the bar and the
   details outgrow the screen; place alone cannot identify.
2. **The closed bar says what, not who.** Twenty session colors were worked out with care and
   none of them shows until the details are out. Who needs you depends on the request coming
   out, on counting lights, or on knowing the voice.
3. **Motion is spent on the wrong state.** Working spins all day at the tempo of "needs you",
   so motion cannot be the signal for attention, and nothing ever rests.

Any redesign has to fix these three. A new skin on the same bar fixes none of them.

### What must not be lost

- State by shape as well as color, each one readable alone at 26 px.
- An order and a place that never change; rows level with their lights; rows of one height.
- The size: closed by default, details on demand, clicks through, never the keyboard's focus.
- The voice made visible from the real loudness, in the light and behind the words.
- The bubble at the speaker's own light, with name, title and sentence.
- Requests that stay until answered, with their keys drawn as caps.
- The context arc and the waiting number on the light: two more facts with no more room.
- Everything a setting (size, motion, colors, glass), and all logic in the hub, so a look is a
  skin over one state that tests can reach.

## Plushies: 21

`plushies.html` as of `a7bcae6`. It shows five seats at 84 px with name and state written under
each, the twelve at 184 px, and 24, 32 and 48 px in idle only.

- **One-second glance, 3.** Seen at 84 px: face and prop read well (sign with "?", star, slump).
  At the size a bar uses, the page shows no states, so its own drawing code was run at 24, 32
  and 44 px (my test, not the page): idle, working and speaking share one outline; "needs you"
  is a sign 6 to 9 px across; done is a star of 5 px; only failed changes the whole shape. The
  session color fills the body, so identity becomes the loudest signal and state the quietest:
  the reverse of today. It fixes "who" and weakens "does anyone need me".
- **Clear with 20 sessions, 2.** The page has no crowded view. My test, a column of twenty at
  36 px: twenty balls of fluff with the state in details too small to find. Same structure as
  today, so the same limits.
- **Small footprint, 4.** Guess: in today's bar they need 44 to 48 px each to show a prop,
  where a light needs 26. The page itself shows only a strip 1090 px wide.
- **Motion with meaning, 4.** Code: the best behaved of the four, and to the letter of the
  prompt. Idle blinks every 7 s, working leans slowly, "needs you" sways once a second for 5 s
  and stops, done settles once in 0.4 s, failed slumps once and stays. One point off: speaking
  is a fixed loop, not the voice.
- **Buildable in Windows, 4.** The fur is painted pixel by pixel (an outline blurred into a
  height, lit, hairs drawn on). WPF has nothing like it, but it is plain arithmetic that C# can
  do once per session color into a picture; the motion is only turning, scaling and fading,
  which WPF does. Guess: a day or two to port the painter; not tried.
- **Charm, 4.** Seen: the materials and outlines are lovely (Pouch, Knot, Spool, Bell, Comma).
  Held back by sameness underneath: one face on all twelve, one sign, one star, one slump. The
  trick each note promises (the mouth that opens, the corner that lifts, the pod that unzips) is
  not drawn. Not checked: likeness to existing characters.

## Aquarium: 17

`aquarium.html` as of `a7bcae6`, the plush fish.

- **One-second glance, 3.** Seen at five: readable and friendly, every fish named. But it is a
  scene to read, not a signal to catch: weeds, coral, rays and bubbles around five things that
  all move. The "?" floats beside the fish, not on it, and the name tag does not say why.
- **Clear with 20 sessions, 2.** Seen: past six sessions only those that need you, speak or are
  selected keep a name; seventeen are anonymous, the failed one among them. Tags land on the
  wrong fish ("web-app" over a green neighbor). With three needing at once it took me several
  seconds to pair each "?" with its fish. Working fish wander, so place means nothing.
- **Small footprint, 1.** Seen: 428 by 330 px at its smallest, plus 90 for a request: twelve to
  sixteen times today's closed bar, opaque, always there.
- **Motion with meaning, 3.** Code: the state moves are good (to the glass and a 5 s sway, one
  somersault, sinking to the sand). They sit on top of motion that never stops: every tail, the
  weeds, the working fish crossing their cells. The place changes with the state, which the
  prompt rules out.
- **Buildable in Windows, 4.** The same painted pictures as the plushies, moved and turned, and
  text pills. Guess: a large see-through window redrawn every frame is heavier in WPF than
  today's small one.
- **Charm, 4.** The ideas are the best on any of the three pages: glasses to work, a pearl when
  done, a plaster when failed. The picture is busier than the ideas deserve.

## Living aquarium: 17

`living-aquarium.html` as of `59fff5a` (it changed three times during this review; the calmer
default background helps and moves no score).

- **One-second glance, 3.** Seen: the three questions are answered, by text. An amber pill says
  "web-app needs you", dark ones say who speaks and who failed. Cover the fish and nothing is
  lost; cover the pills and nothing is left. Real fish have no faces, so working, idle and done
  look alike, and done leaves no mark once the leap is over: the state that means "your turn"
  is invisible. Today's check stays.
- **Clear with 20 sessions, 3.** Seen, with three needing at once among twenty: three amber
  pills, each with its name, found at once. The tank does not grow. Everything else is a shoal:
  no names, no count by state, and at 460 px the pills overlap each other and hide the fish
  they name.
- **Small footprint, 2.** Seen: 460 by 200 px in its "Overlay" size, eight times today's closed
  bar, and an opaque moving picture.
- **Motion with meaning, 2.** Code and stills: the leap out of the water on done is the single
  best animation idea in all four. But every pixel moves always (surface, light on the sand,
  plants, every fish), so motion cannot mean anything, and a bright moving scene at the edge of
  the eye is the distraction this tool exists to remove. Failed is a pale fish on its side:
  clear, and grim.
- **Buildable in Windows, 2.** It is WebGL with shaders written for it. WPF cannot run that, and
  the overlay's compiler has no web engine. In Windows at all: guess, through a WebView2
  window, which means shipping its library, a browser running all day, and untested trouble
  with see-through, click-through windows. Under today's rule (Windows' own compiler, nothing
  installed) it is a 1.
- **Charm, 5.** Seen: beautiful. Six real species, light through the water, waves to stir.

## What this says before the 50 arrive

- The structure is worth more than the skin. Today's fixed column, closed by default, is right;
  its three problems are what a redesign should spend itself on.
- Characters belong in it only if state stays as large as it is today. A plushie whose six
  states are six outlines, or one that sits inside today's state ring, would keep the glance and
  add the charm. As drawn they trade one for the other.
- The aquarium is a different kind of thing: something to look at, where the overlay is
  something not to look at. If it is kept, it fits as a scene behind the details or a window to
  open for pleasure, not as the bar. That is worth deciding before more hours go into it.
- Worth taking whatever wins: the plushies' motion rules, the aquarium's state ideas (glasses,
  pearl, plaster, the leap), and the living aquarium's amber pill that names who needs you.

## The 50 designs

Waiting for the author's screenshots. For each: the idle overlay with five sessions, the crowded
twelve, and the permission request, at full size, with the design's number in view. They will be
scored on the same six plus difference from the others, then the best five, the parts worth
combining, and whether any beats today's 21 on the six shared scores.
