# The name and the logo

How Sidetone got its name, its color and its logo, with the author's words at each step. Moved here unchanged from `CLAUDE.md` on 2026-11-19.

The author chose the name on the evening of 2026-11-18, of three offered after they said of
the old one "I don't like [it] as a name": sidetone is the sound of your own line in a headset,
which tells you it is alive while you work. Renamed that evening, on their word ("call it
Sidetone and also rename the project folder as well as the repo"): the name in the settings
window (`settings.NAME`) and the README's heading; the GitHub repo, now
github.com/SimoneWang02/sidetone; the folder, now `~/personal/sidetone`, with a link left at
`~/personal/claude-speaks` because sessions that were open, their listeners and the editor's
window still go by the old path (remove it once none does). With the folder went: the hooks in
`~/.claude/settings.json` (backup: `settings.json.bak-before-sidetone`), the links in
`~/.local/bin`, the hub (restarted from the new place), Claude's memory for the project (copied
to the folder's new name under `~/.claude/projects`), and the voice `af_heart` for sessions
that will be named `sidetone` after the folder. Minutes later, asked whether the commands
should follow, they said yes ("Yeah, rename those"; written down as "renamed though"): the
command is `bin/sidetone`, linked as `sidetone` and `st` (was `claude-speaks` and `cs`; on the
author's machine the two old names are still linked to it), and every mention of a command in
the code, the help, the README and these notes was changed with it. **Still called
claude-speaks**, not asked for and so not touched: the folders under `~/.config`,
`~/.local/state`, `~/.local/share` and the run folder, the `CLAUDE_SPEAKS_*` variables, the
VS Code extension, the overlay program's file name, and the name in these notes wherever
it is not a command. Sessions opened before the change keep `claude-speaks` as their name
in the bar.

On 2026-11-19 the leftovers went, on their word. The link `~/personal/claude-speaks` and the
commands `claude-speaks` and `cs` were removed (nothing used them; "removed them"). Then the
folders, asked "if it doesn't change anything, that's good": `~/.config/sidetone`,
`~/.local/state/sidetone`, `~/.local/share/sidetone`, the run folder `$XDG_RUNTIME_DIR/sidetone`,
`%LOCALAPPDATA%\sidetone` with `sidetone-overlay-*.exe`, and the `SIDETONE_*` variables (were
`CLAUDE_SPEAKS_*`). The author's folders were moved, not copied, with the hub stopped; no code
looks for the old ones, since nobody else has them. Then the rest, "my goal was just to
rename all the previous stuff ... just for coherency": the VS Code extension is `sidetone.sidetone`
(shown as Sidetone; the old one uninstalled by hand), and the comments, test data and examples
say sidetone. The old name is left only where it is history or the author's own words.

The mark's color is theirs too: on seeing the logo in the microphone's pink they typed
"#006896", taken as the color for it (they said nothing else). The logo runs from a lighter
step of that blue to it, and the settings window's switches and sliders use it.
A spoken message that had waited behind that turn said what it was for: "I don't like the
brand color which is ... currently it's pink ... I'll give you a color. Let me know if it's
good." Told (measured): white on it reads well (6.1 to 1), so it is right for the logo and
for filled things; on the dark glass it is 2.7 to 1, too faint for thin lines and words,
which need a lighter step of it (`#2E9CC9`, 5.4 to 1); and in the overlay it would be taken
for the blue of "working" (`#4FC3F7`; 34 apart by `state.color_distance`, the lighter step
15, where 40 is the least kept between two sessions' colors, and the pink is 89). So the
microphone in the overlay stayed pink (`Ui.Mic`) until they decided, offered pink, violet
or white: "use the brand color. I want the hex code to be the brand color." So the
microphone is `#006896` too (`overlay.mic_color`; `"#FF6E8A"` is the pink). The light of
the session you talk to is filled with it; what is drawn thin on the glass, the wave of
your voice above all, uses it lifted two fifths toward white (`Ui.MicLine`), since in the
blue itself the wave could hardly be seen (a picture showed it). The nearness to the blue
of "working" was their call to take. Seen in a picture (`talk-listening.png`), and by
them while talking: "okay, looks good. Let's see", so it stays and is to be watched in use.

The taskbar's icon is the mark in white on a rounded square of that blue which fills the
whole icon (`Logo.Draw(dc, s, tile)`, `assets/icon.png`). The plain mark, a small disc in a
thin arc with air around it, looked smaller there than its neighbours (the author: "it's
still pretty small. It doesn't have the circumference of the other apps"). In the window's
menu and the README it is still the plain mark. On seeing that square: "I would prefer a
round one and the wave inside the circle are not very clear. Could you provide another
solution?" So the icon is a disc that fills the side, with nothing on it but three broad
white bars (no arc; five thin bars were under two pixels wide at taskbar size), and the
plain mark has the same bars in its disc. On the three: "might not be enough. Maybe
increase." Five now, even on both sides of the tallest, each 0.088 of the disc wide
(2.8 px at 32). Then: "Do you think having a symmetric one is good?" Answered: even bars
read as sound at a glance and sit calmly in a circle, but that is the picture nearly
every voice program has; bars of uneven heights look like a spoken word and are more its
own. To let them judge by eye both are on screen at once: the taskbar's icon is uneven
(`Logo.Uneven`), the mark in the window's menu and the README even. Their answer:
"Currently I'm preferring the uneven one but it doesn't make me crazy. I'll prefer [other]
design, maybe not a round one, just a custom design". So the uneven bars are in both for
now, and four other ideas were drawn as one page and opened in their browser (kept outside
the repo, in the session's scratch folder; drawn as SVG and turned into a picture with
Edge's `--headless --screenshot`, which is a quick way to look at a drawing from WSL):
A, a bold S that is also a wave; B, a speech bubble with the uneven bars in it; C, the bar
of lights itself, three lights in a capsule with the middle one sounding to the side;
D, bars whose middles ride a wave. Of these and the round one (E): "I prefer D and E.
Give me an opinion about D and E, and maybe do more variants about D." The opinion given:
D is the more its own, a free shape nobody else has, but thin and airy at taskbar size
and faint in the deep blue on dark glass, the very thing they found small before; E is
the clearest small but the most ordinary. Six variants of D on a second page (bolder with
five bars, in white on the disc, equal bars on a pure wave, seven bars, growing louder,
a lighter blue for dark glass); the one recommended is D on the disc, which joins the two
they like. They left it to the session ("[what] should we choose out of all of this?"),
so that one is the logo now, one drawing for the taskbar, the window's menu and the README
(`assets/logo.png`, `assets/icon.png`): a disc in their blue with five white bars riding a
wave. The arc and the even and uneven bars are gone from `Logo`. **Chosen by the session
on their asking.** Their answer on seeing it: it "seems like stocks going up and down.
That's the issue". Right: bars pushed up and down are how prices are drawn, and bars on
one middle line are how sound is. A third page, all on the disc and on the middle line or
a line of their own: F1 uneven bars, F2 the same leaning forward, F3 one wave (an S lying
down), F4 a wave that swells and fades, F5 bars that end in a round light, F6 seven
bars. Recommended: F5, the voice and the lights of the tool in one mark; F3 second.
Their answer: "I would probably prefer E ... but it's not very creative, it's pretty
anonymous. I want you to be very bizarre." A fourth page, the voice bars as part of
something with a face, all on the disc: G1 a closed eye whose lashes are the bars
(eyes-free), G2 a wink with the other eye a light, G3 a ghost at your side with a wave for
a hem, G4 a face singing through a mouth of bars, G5 a crescent that speaks, G6 a grin with
teeth of sound, G7 a cockatoo with a crest of bars. Recommended: the ghost (it keeps its
face at taskbar size and says "a voice beside you that you do not look at"), the closed
eye second (the tool's own story, but it can read as tears). They came back with an idea
of their own: "a microphone ... because we speak ... Otherwise, the headphones, such as
TeamSpeak, will be cool because it has both microphones [and] listening." A fifth page,
drawn from scratch and not after that program's logo: H1 a headset with the voice bars
between its cups, H2 a plain headset whose microphone ends in a light, H3 one ear from the
side, H4 a microphone whose grille is the bars, H5 the ghost wearing the headset, H6 the
round one made the head of a microphone. Told them: sidetone is itself a headset word
(your own voice in your headset), so the headset is the name drawn; H1 recommended.
(In SVG a gradient does not fill the stroke of a straight line, which has no box: the
stand of H6 was missing in the first picture.) Their answer: "I don't like any of them."
So after five pages and some thirty drawings: the round one with uneven bars on the middle
line (E) is the logo again, as the one they like best, and the guessing has stopped. Asked
of them instead, as worked for the face of ten waiting messages: a logo or picture whose
look they like, in their Downloads folder, or a word on what is wrong with these (the
idea, or how they are drawn: flat, simple shapes are what a session can draw by hand in
SVG). Their direction instead: "look at the top 5 startups right now ... and look at their
logo. Take inspiration from each one of them." By Crunchbase's list of June 2026 (the
newest a search found): SpaceX, Anthropic, OpenAI, ByteDance, Stripe. A sixth page, one
mark after the idea each logo is built on, not after the logo: S1 a sweep leaving the
voice bars, S2 a burst of uneven rays, S3 five bars turned into a knot, S4 bars with
slanted ends in five blues and no disc, S5 a leaning S that is a wave, and S6, the round
one they like with its bars cut on the slant. Said to them plainly: S2, S3 and S4 came
out too near the marks they were taken from (Claude's spark, OpenAI's blossom, ByteDance's
bars) to be used; S1 reads as a smile; S6 and S5 are the two that are ours. Their answer:
"S6 is good. What's the original logo?" So S6 is the logo, in the taskbar, the window and
the README: the disc with five uneven white bars, each cut on the slant at both ends
(`Logo.Draw`). The slant is the idea taken from ByteDance's mark, which is a few bars
with slanted ends in blues and teal and no disc; ours has five white bars inside a blue
disc, and they were told so. **In place; they have said it is good on the page, not yet
on the taskbar.**
While it was on screen the picture check could not take the settings window: the live
window stood at the same place in the middle of the screen, and the check refuses when two
windows have one rectangle. Close the live one first (`sidetone settings close`).

In the same message: "I still see [claude-speaks] as a name on the top left of each session
... you just have to [restart] the hub." A restart would not have done it: a session's name
is its folder's as Claude Code gave it when the session began, and the hub keeps it. Done
once by hand, no code: with the hub stopped, the names in `sessions.json` and the voices in
`voices.json` were changed from `claude-speaks N` to `sidetone N`.
