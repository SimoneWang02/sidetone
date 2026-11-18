# To do

What is left for claude-speaks, as of 2026-11-17. Everything asked for so far is built; this
is what has not been tried by hand, what is undecided, what is rough, and what has not been
started. `CLAUDE.md` has the details of how things work.

## To try by hand

These work in the automated tests or in pictures taken from WSL, but nobody has pressed the
real keys yet.

- [x] Side questions: spoken words that open with "by the way" do not wait for a busy session
      (asked for by the author by voice on 2026-11-17, who compared it to Claude Code's
      `/btw`: "it lets me skip the queue and ask a by the way question"; of a second talk
      key or opening words they chose the words: "starting with the words by the way,
      that's fine"). Built the same evening. A throwaway copy of the session answers from
      what the session knows, in about 5 s, in that session's voice; the session never sees
      the question or the answer. Checked with a real copy of a real session in the middle
      of a turn, through the hub's code but not through the live hub, the microphone or the
      speakers. **Not tried by the author yet.** To try: while a session works, hold the
      talk key and say "by the way, what are you doing right now?". Its light should show
      the moving dots with your words and "Answering on the side", then it answers aloud
      while it goes on working; `Ctrl+Alt+Backspace` in those seconds drops the question.
      Tried by the author on 2026-11-18 with their own voice, while a session worked.
      "Oh, by the way, what time is it right now?" waited for the session like any
      words, because of the "oh". Said again without it, the copy answered in 3.2 s
      and was heard: "I can't read the clock from a side question, but the last time I
      saw in the log was about ten to two". Mended at once: small words before the
      opening ("oh", "so", "alright", "hey") are passed over, and the copy is told the
      day and the time. **Neither fix tried by voice yet**; they have not said how the
      answer sounded or whether they saw "Answering on the side".
      Open:
      - does the speech model write "by the way" reliably at the start (the author's own
        choice came through as "the worst by the way"; both real tries on 2026-11-18
        were written right); other openings go in `aside_words`
      - the copy now runs on the session's own model and reuses what the session has
        saved, as `/btw` does (the author: cost on Fable does not matter, and ideally
        they want the real `/btw`); 4.5 s on a long Fable session. What it adds to the
        plan's usage compared with `/btw` was not measured
      - the real `/btw` typed into the terminal by the VS Code extension: looked at and
        not built. Its answer can be heard by a hook (`SubagentStop`), but its answer
        box stays open and takes the next thing typed, and the hub cannot see whether
        a box, a permission prompt or half a typed line is there. Would need a way to
        know what the terminal shows
      - a `/btw` the author types by hand is not spoken yet; the hook that hears it
        also hears the suggestion for the next prompt, so the two must be told apart
      - only for a session in the middle of a turn (`aside: always` for idle ones too)
      - a question that needs a file read or a command gets "that cannot be checked from
        a side question"; nothing offers to pass it on to the session
      - Italian openings ("a proposito") are not in the default list
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
- [x] The choices of a question each on a line of their own in the overlay (the author,
      2026-11-17, in that same spoken answer: "the choices are not in new lines. I see them
      all in a single line and it's not very readable"; changed at once, seen in pictures
      only). The author, that evening, asked about a question with three choices that was
      on screen: "Yes, one per line." A first try had failed for another reason: the
      overlay was restarted seconds after the question opened and the new window was not
      told about it ("I don't see the prompt box anymore"). Mended the same hour; the hub
      now shows an open question again when a window starts, from its next restart on.
- [x] A question answered in the terminal leaving the overlay at once (mended 2026-11-17
      after the author saw it stay; checked with a real session). The author answered the
      next question in the VS Code terminal and the hub closed it in that second (the log
      says "answered in the terminal" three seconds before the reply went on). They have
      not said whether they watched it leave the overlay.
- [x] `Ctrl+Alt+R` (repeat): the author, 2026-11-17: "good for replay".
- [x] `Ctrl+Alt+R` again after the change they asked for the same day: it now says the last
      line of the session in focus (move the focus with `Ctrl+Alt` + wheel first), and the
      bubble with the voice comes out at that session's light while it is said. The author,
      2026-11-17, right after two repeats: "It's perfect. Yeah, I see it."
- [x] Speaking to a session right after interrupting it (mended 2026-11-17 after the author's
      words to an interrupted session "didn't go through"): interrupt a reply with Esc or
      Ctrl+C, hold the talk key and say something. Done by the author the same day: they
      interrupted a reply and their next words ("I stopped the previous audio, now I'm
      sending another one") arrived, carried by the listener that starts with a prompt.
- [x] Words going to the wrong session (the author, 2026-11-17: "i sent an audio to
      claude-speaks 4 but somehow got here (i didnt notice at first)"). Nothing was broken:
      the voice goes to the session in focus, which is the one that spoke last, and this
      session had just spoken while they were looking at the other one's terminal. The
      listening bubble shows who is being spoken to, but it was not noticed. Ideas, none
      built: the focus following the terminal you click (see below, needs a VS Code
      extension); the focus moving to a session when you type to it; saying the session's
      name when the talk key goes down and the focus is not where you last typed.
      Later that day: the focus now follows the terminal in front, and since the author
      also saw the wrong sign when another session began to speak as they started talking,
      the talk key reaches back: pressed within a second of a session starting to speak,
      it still goes to the session that had the focus before (`focus_reach_back`). Tests
      only; to be watched in use, since the moment cannot be staged.
      The author, asked that evening whether words had still gone to a session they did
      not mean since those fixes: "No, not since." About three hours of use with two to
      four sessions; the reach-back moment itself was never staged.
- [x] Speak, let go, and move the focus at once (arrows, wheel or another terminal): the
      words should still reach the session that was listening, and "sent" should show on its
      light. Fixed 2026-11-17 after the author did exactly that and the words "went to
      another session". The first fix still lost the words when the focus moved in the first
      0.4 s after letting go; the second one is checked by tests only, not with the real keys.
      The author, 2026-11-17, asked to try exactly this: "It works. Seems to be working."
      Those words reached the session they spoke to; the log does not record the arrow
      keys, so the move right after letting go is on their word.
- [x] Take back what was just sent: speak to a session that is in the middle of a reply, and
      within four seconds of "sent" press `Ctrl+Alt+Backspace`. The light should show
      "Taken back" with the two notes going down, and the session should never get the
      words. Then the same to an idle session: it should be told to ignore them, and say
      what it already did instead of undoing it. Built 2026-11-17. The idle half was done by
      the author the same day with the real key and worked; the busy half is still open.
      Also to notice: the "sent" bubble now stays four seconds, and a press meant to cut a
      line being spoken in those seconds takes the words back instead.
      The busy half, done by the author the same day against a session kept busy on
      purpose: the words were queued for it at 14:54:27 and the hub logged "taken back
      before the session got it" a second later; the session never received them. A first
      try had Backspace land before "sent", which is the plain cancel. Not said: whether
      the light showed "Taken back".
- [x] Taking words back while `Ctrl+Alt` stay held from talking: the overlay hides those
      keys from Windows during a hold and believes them held for 3 s after it (`MaskGrace`).
      After that, with the keys never let go, Windows takes them for up, so Backspace is a
      plain Backspace for the program in front and takes nothing back, though the time to
      take words back runs to about 6 s after letting go. Not fixed (read from the code
      2026-11-17, not tried): keep believing them held while the cancel key can still act.
      Mended the same evening: the overlay goes on believing them held for as long as the
      "sent" or "waiting" sign of those words is up, which is as long as they can be taken
      back. Compiled and live; not pressed by anyone. To try: speak, let go of Space only,
      keep `Ctrl+Alt` down, wait for "sent", count to three and press Backspace: it should
      say "Taken back" and type nothing in the window in front.
      The author tried twice that evening and both were taken back, but about two seconds
      after "sent" by the log's whole seconds, where the old three seconds already
      reached, so the late press is not proven. Asked for a third, slower try they did
      not see the point ("I don't get it. Like what's your point?") and chose to skip it:
      a rare case, left open. `hub.log` now gives the time of a take-back to a tenth of
      a second, so a late press in everyday use will show there by itself.
      Closed on the author's word later that evening, once the cancel key had become the
      stop key: "I don't think they are needed anymore, right? Double check it." Checked:
      the take-back is still the first thing the key does in those four seconds, their
      two tries with the keys held worked, and the late press stays unproven. One case
      is left and is rare: `Ctrl+Alt` never let go for longer than the "sent" sign
      shows, then Backspace to stop the session, is a plain Backspace.
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
- [x] `Ctrl+Alt+L`: keeps the details out, and puts them away again (on the list of things
      the author had not pressed yet in `CLAUDE.md`, but never on this one). The author,
      2026-11-17, told to start with this one of five: "Oh, yeah, that works." Taken as
      this key; they did not name it.
- [x] The last lines the sessions said, shown under the rows while the details are kept out
      with `Ctrl+Alt+L` and the mouse rests on them. The author, 2026-11-17: "that works",
      but hovering another session lit it up without showing its history.
- [x] The history of the session under the mouse (changed 2026-11-17 on that remark, seen
      in pictures only): with the details kept out, rest the mouse on one session and
      then on another; the lines under the rows should change to that session's.
      The author, later that day: "hovering each session it says the details of each
      session, which is good."
- [x] A quick tap of the talk key: the focus goes to the next session, without recording.
      The author, 2026-11-17, on trying it: not intuitive, since that key is for talking;
      "better solution might be using the arrow keys". The tap now does nothing unless
      `talk_tap: next` is set.
- [x] `Ctrl+Alt+Up` / `Ctrl+Alt+Down` move the focus (built on that remark; checked only as
      far as the overlay accepting the keys): the frame goes to the session above or below,
      stops at the first and last, and the details come out for a moment. In the island
      layout it is `Ctrl+Alt+Left` / `Right` (the author's wish the same day). The author
      tried them while talking and the recording stopped, which the wheel does not do;
      mended the same day (any second key ended a hold after a second). To watch for:
      VS Code's own use of these keys in the editor (a cursor above or below) no longer
      works while two or more sessions are open.
      The author, 2026-11-17, after the mending, asked to press an arrow while talking and
      go on talking: "It seems to be working. That's good." Repeat after a hub restart the
      same hour: "the replay worked". Left and Right in the island layout: see the layout key above.
- [x] `Ctrl+Alt+K`: switches between the bar and the island, and back. The author,
      2026-11-17, asked to switch and to try Left and Right there: "It works fine. Yeah,
      it's perfect."
- [x] Push-to-talk in Italian from the first word (so far every Italian recording began in
      English). Done by the author on 2026-11-17: "ok vediamo proviamo a me a me sembra che
      funziona sia sia funzionato abbia funzionato in passato" arrived whole, taken as
      Italian, nothing cut at the start. It came without capitals or punctuation, which
      the English recordings have.
- [x] "Release to send" with a glint of light running along it while the talk key is held
      (asked for by the author on 2026-11-17 as "an animation on the text"; which one was
      left open). To look at: is the glint what was meant? The other choices are
      `"talk_text": "pulse"` (the words breathe) and `"still"`, under `overlay` in the
      settings. The words are a soft white since the same day, no longer the microphone's
      pink, which looked like the name of the first session (the author: "I kind of like
      the pink that was before for the first terminal. I think what you should change is
      the action label"). `"talk_text_color": "#RRGGBB"` gives them another color.
      The author looked at both the same day, the glint and the white: "I think it's
      good. Yeah, I like it." The pulse and still styles they have not seen.
- [x] The glint on every push-to-talk label, and more of it (the author, 2026-11-17: "put
      a glint to all action labels", such as "Working out what you said"; done the same
      day, also for "In focus" and for why nothing was sent; wider, brighter against a
      softer white, and back sooner). What a session is doing ("Running the tests") has
      none. The author tried it at once: "It works, I like it. Yeah, that's perfect."
- [x] Dragging the bar: the cursor staying on the spot it took hold of (the author,
      2026-11-17: "whenever I drag and move, sometimes the cursor is not aligned" with the
      bar). Likely cause, mended the same day: the drag measured where the cursor was when
      the press was handled, a moment after the press, so a quick start left the bar
      following from beside the cursor. It now uses the place the press itself reported.
      Not proven: a drag cannot be made from WSL without taking the author's mouse. Both
      monitors are at 100% scaling, so it was not that. The author tried it minutes
      later: "Perfect, it seems to be working."
- [x] The bar over a game in borderless windowed mode. The author, asked on the evening of
      2026-11-17: "It seems to be working." Which game, and whether the keys and
      push-to-talk were used there, was not said.
- [x] A plain click on the bar reaching the window underneath (the author, 2026-11-17: "it
      lands on the window underneath")
- [x] Dragging the bar, which since the same day needs `Ctrl+Alt` held (the author's wish on
      seeing the move cursor whenever the mouse was on the bar): with the keys held the
      move cursor shows on the bar and it can be dragged; without them there is no move
      cursor and clicks and the wheel go to the window underneath. The author, 2026-11-17:
      "Oh yes, it works. Now perfect." The new place was saved to `config.json`.
- [ ] A session's first spoken words before anything was typed to it (mended 2026-11-17:
      the first session after the hub had gone away had no listener until its first
      prompt; the author spoke to it twice and asked "why are you not receiving audio
      inputs?"). Tests only. To try: close every session, wait for the hub to go
      (`claude-speaks hub stop` does it at once), open one session and speak to it
      without typing.
- [x] Sessions started from the VS Code extension showing up in the bar. The author,
      2026-11-17, opened Claude Code in a new editor tab: "it seems to be added below",
      and the hub listed it as a third session, idle, with a voice of its own. Not tried:
      whether such a session speaks and can be spoken to.
- [x] The bar no longer getting taller when the mouse is on it while a long sentence is
      said: since 2026-11-17 the sentence is cut to one line in the details (`row_lines`).
      The author the same day: "It works. It's only one row. I mean you can make it two.
      No, one is fine." So one line stays; two is there as `row_lines: 2` if wanted.
- [x] Clicking while talking (the author, 2026-11-17: "while I talk I cannot right click, so
      for instance I cannot pause the YouTube video"). Not looked into beyond a guess: with
      `Ctrl+Alt` still down the click reaches the browser as Ctrl+Alt+click, which a video
      player may ignore; the overlay passes every click on. To find out: hold only
      `Ctrl+Alt`, without Space, and click the video. If that does not pause it either, it
      is the browser. Since the same day the hold goes on with Space alone, so letting go
      of Ctrl and Alt while talking should give plain clicks.
      The author tried it the same day: with `Ctrl+Alt` held, with or without Space, a
      left click does not pause the video. So it is not the recording. The overlay's mouse
      hook, in while those keys are down, passes on everything but the wheel (read again
      in `OnMouse`), which leaves the video player ignoring a click made with Ctrl and
      Alt down; not proven, since nobody has clicked with the overlay switched off.
      Suggested to the author: let go of Ctrl and Alt once the recording has begun and
      keep Space. Their answer: "It's not really great ... not very intuitive." So, the
      same day, the overlay hides Ctrl and Alt from other programs for as long as you
      talk (`talk_frees_keys`), and a click with all three keys held is a plain click. It
      only ever tells Windows the keys came up, so it cannot leave them stuck. Checked
      from WSL with a stand-in key; to be tried by the author: hold `Ctrl+Alt+Space`, keep
      all three down, click the video (it should pause), and with the keys still down
      press Backspace (it should cancel the recording).
      The author, minutes later, by voice with the keys held: "It does pause." Sending
      still works too, since that message arrived. Backspace with the keys still down,
      which the overlay now has to recognise itself: "Oh yeah, it works."

## To decide

- [x] Which of the two layouts (`bar`, `island`) is the default for new users. The author,
      asked on 2026-11-17 with bar, island and "decide later" to choose from: bar. It
      already was, so nothing changed.
- [x] Voice of this project: it spoke with `bf_isabella` since the voice pool changed. The
      author, 2026-11-17: "I prefer the American one." Pinned `af_heart` for the session
      named `claude-speaks`; the second to fourth sessions of the project keep the voices
      they were given (`af_bella`, `bm_fable`, `bf_emma`).
- [x] "Uploadable" voices: was that cloning a voice from a recording? Kokoro cannot do it; it
      would need a second voice engine. Answered since, without the question being put
      again: the author wants a realistic copy of one person's voice (see "Voice cloning"
      under "Not started", where the building is still open).
- [x] Should the repo default for push-to-talk be the multilingual model? The author,
      2026-11-17, asked with three choices (English only, any language, ask at install):
      "just selecting English it will mean faster answers right? ... What if we let the
      people choose the language they speak? So ... we don't include all languages." Built
      the same day: `install.sh` asks once which languages you will speak, and
      `claude-speaks languages en,it` changes it later, also in a running hub. English
      alone keeps the English-only model; other languages get the multilingual one,
      told which to expect. Not tried by a person: the question in the install script
      (answered by a script in a throwaway home folder), and no language other than
      English and Italian has been spoken to it.
- [x] Should a quick tap of the talk key also stop at the last session, like the wheel?
      Settled another way on 2026-11-17: the tap no longer moves the focus at all; the
      arrow keys do, and they stop at the ends.

## Rough edges

- [x] A hub restart still forgets a few things. Names, colors, voices, titles, the order in
      the bar and the focus are kept since 2026-11-17 (`sessions.json`), and since later
      that day the last 40 lines the sessions said (the author pressed repeat after a
      restart and got "Nothing from ... yet"), but not the task counts of a running turn,
      or a permission prompt that was open (it can then only be answered in the terminal).
      A turn that ends in the second the hub is down comes back as idle, without its check.
      Also forgotten until 2026-11-17: whether the details were kept out (`Ctrl+Alt+L`).
      The author, after a hub restart: "when hovering ... I don't see the history
      anymore"; the history only shows while the details are kept out, and the restart
      had put the overlay back to lights only. The mode is now saved like the layout.
      Closed on the author's word, 2026-11-17: what is still forgotten (the task counts of
      a running turn, an open permission prompt) is only met while the hub is restarted
      to work on it, and they want no code for that ("there's no need in the final
      product"; asked whether to tick this one for the same reason: "Yeah").
- [x] Titles that say what a session is doing (the author, 2026-11-17, could not tell four
      sessions in one folder apart by their titles, which were the start of each one's
      first spoken sentence). Changed the same day: each session now writes its own title
      of a few words into its speak tag and updates it when the work moves on. The author
      on seeing the first one: "that's perfect. Yeah, it's clear now." Still to watch over
      a longer day: whether titles change too often or too rarely.
- [x] Something said to a busy session waits until its reply ends, and a turn stuck on an
      unanswered dialog in the terminal holds it back for as long as the dialog is open. The
      overlay shows "waiting" for 3.5 s only; the author took it as not heard (2026-11-17).
      Keep the waiting sign on that session's light until the words are delivered. (Done
      2026-11-17: a waiting message has its own sound, or "Queued." with `talk_feedback: voice`.)
      Built that evening on the author's go-ahead: a small dot in the microphone's color
      stays at the upper right of that session's light for as long as words are held for
      it, its row in the details says "1 message waiting", and when the session takes
      them the light shows the paper plane. While the words are on screen the light shows
      a clock, where it showed the plane of words that went out. Seen in pictures only.
      To try: speak to a session in the middle of a reply and watch its light until the
      reply ends. Not built: a sound at the moment the words are handed over.
      The author tried it at once, speaking to a session kept busy for half a minute; the
      words waited and arrived when it stopped. "I saw the clock was good. Instead of the
      pink notification icon, maybe a red would be better. It's more intuitive." So the
      dot is red by default (`overlay.waiting_color`; `"#FF6E8A"` is the pink). They have
      not said whether they saw the plane at the handover, nor seen the red one yet.
      On seeing the red dot: "it's not very intuitive. It doesn't feel like there's one
      in queue besides the current one." Of three ideas (the clock kept small on the
      light, a paper plane parked beside it, a second ring behind it) they chose the
      first. So the mark is a small clock whose hand goes round, with the number of
      messages when two or more wait (`overlay.waiting_mark`: `clock`, or `dot`). Seen
      in pictures only; **the author has not seen the clock mark yet.**
      They saw it minutes later: "I don't like the red clock on top right ... it's just
      feel weird ... maybe just the number is fine", without the white border, and no
      clock in the light when the words go into the queue either: "just having the
      number, like covering the whole circle at first and then reducing its size and ...
      move it top right with an animation". Built that way: the number, white on red,
      covers the light for 0.9 s (`overlay.waiting_hold`), then shrinks into the upper
      right and stays; it does so again when another message joins. `waiting_mark` is
      `number` (default), `clock` or `dot`. Seen in pictures of both ends of the
      motion; **the author has not seen it move yet.**
      Having seen "9+" in a picture: "very compact very dense in that circle. Maybe use
      like a funny emoji ... like a shocked emoji". Above nine messages the disc is now
      a shocked face, drawn by the overlay (`overlay.waiting_many`: `face`, or `number`
      for "9+"). In the corner it is three white dots on red, small for a face.
      Shown to the author on the live overlay (eleven messages queued for a busy
      session): "kind of scary face ... it's not funny". Redrawn as a yellow face with
      one wide eye and its tongue out. They also asked which is better, the number
      covering the light each time or staying in the corner and counting up there;
      built as suggested to them: only the first message to wait covers the light, the
      ones that join make the number jump in its corner (`overlay.waiting_cover`:
      `first`, `each`, `never`). Shown live again. On the grinning face: the yellow is
      good, but "it looks like he's mentally ill"; rather "a more like disgusted face
      ... like you have so many requests". Third face, the same evening: lids half
      down, a sideways look, one brow up, a flat mouth. Shown live. The author then put
      a picture in their Downloads folder as the look to go for (a yellow face with
      brows raised in the middle, oval eyes with a line under each and a wavy mouth
      turned down); the face is drawn after it, the fourth, and larger in the corner
      than a digit. And on the first number covering the light: "just put it top
      right", so `waiting_cover` is `never` by default and every number comes up in
      its corner with a small jump. Shown live: "Yeah, that's perfect. That's really
      perfect." They asked whether the digits are centered both ways: across yes, down
      they sat up to a pixel low, mended (placed by their own strokes, measured in
      pictures). And the number's disc is now as large as the face's, their choice
      (`overlay.waiting_size`, a radius of 9.2 where it was 6.6).
      Asked by the author, and left as it is: the number in the middle of the light
      instead of a disc of its own. The middle holds the status sign (the "!", the
      voice bars) in the very states in which words wait; told so, they agreed.
- [x] Some push-to-talk holds record sound and come back as "nothing heard". Some were
      Italian before the multilingual model, but at least one was English. Cause not found: the
      microphone delivers signal at once, and loudness made no difference in tests. Next
      step: keep the last failed recording (opt-in) so it can be examined.
      Explained 2026-11-17 by the author: "sometimes I just click ... and say nothing. So I
      guess that's why they come out as like no text." The log agrees: of the 9 holds that
      came back empty, 6 were in the night between 01:00 and 03:00, when Italian was still
      being dropped by the English-only model, and the 3 since then (out of 124 holds)
      lasted 0.6 to 1.8 s with a peak level of 0.15 or less, which is a press without
      speech. So nothing was built. If a hold with real
      speech comes back empty again, the recording keeper is the next step.
- [x] A misheard sentence is sent straight to the session: there is no pause and no confirming
      tap any more (the author's choice). `followup_delay` and `followup_confirm` bring them back.
      Offered to the author on the evening of 2026-11-17 as a decision to confirm ("the
      next you're saying it's a quick decision. Can you check it?"): it stays as it is.
      Since the same day the cancel key takes words back and stops the session that got them.
- [x] A permission prompt that waited more than six seconds and is then approved in the
      terminal stays "needs you" until that tool finishes.
      Mended on the evening of 2026-11-17 for commands, on the author's "if it's fixable
      ... that would be for the best": the hub sees the command start running and takes
      that as the yes. Tried on a throwaway session (back to "working" half a second
      after Enter in the terminal). Live from the next hub restart; the author has not
      watched it. Other tools (an edit, a web fetch) still wait for their end, which is
      a moment.
- [x] The number keys only answer single-choice questions with up to four options. The same
      limit holds for answering by voice: other questions are only announced, and words
      spoken meanwhile wait until the question is answered in the terminal. A permission
      prompt cannot be answered by voice either (the words wait); "deny, and here is why"
      by voice would be possible, since a deny can carry a message.
      Measured 2026-11-17 with a throwaway session, nothing built yet:
      - `AskUserQuestion` never has more than four options (its own limit), so what is
        left out today is questions where several choices can be ticked.
      - Such a question can be answered by the hook: `answers` takes the chosen labels
        joined by a comma and a space ("Apple, Cherry"), and it takes free words too.
      - A denial's message is not the way to give a reason: the command is not run, but
        Claude takes the message for output of the tool, not for the user's words, and
        ignores what it asks for (it even tried the command again). So "no, and do
        this instead" by voice has to be a denial followed by the words as a spoken
        message, which Claude does take as the user's.
      Built the same evening for questions: the number keys tick and untick a choice
      (a box in front of each shows it), `Ctrl+Alt+Y` hands the ticked ones in, and
      spoken words are the answer in your own words, as the terminal's "type
      something" is (the author: "that's the process I want to go through"). Tried by
      the author at once on a real question with three choices: all three ticked and
      confirmed with the keys, and the session got them. Their remarks on the look,
      mended the same hour: no numbers beside the boxes; the ticked and unticked box
      were not one size, so the words moved; the question on a line of its own under
      the name, not "name asks: question"; no voice at every tick ("it gets
      annoying"); the tick not centered and a gap between the filling and the edge.
      The box is now drawn as one shape. A second question they answered by voice,
      a third with the keys: all three points ticked as right. Then: "when sending
      the answers I don't think you should read the answer"; an answer given with the
      keys now gets the short sound for "sent" (`talk_feedback: voice` says it back
      as before). Heard by the author the same night: "Only a short sound".
      Speaking to a session that waits at a permission prompt, built the same evening.
      The author: "if I use voice it's neither a yes or no ... maybe it's more a no and
      then I give more details", and asked whether Claude then builds on what it was
      doing. It does: the request is turned down for now (it is told that details
      follow), its turn ends, and the words arrive as the next message
      (`voice_at_prompt`: `details`, or `wait` as before). Tried on a real session
      through the live hub: asked for a folder, told by voice "make a file named
      note.txt instead", it made no folder and asked to write the file. Tried by the
      author the same night on a test session set up for it: the folder request was
      turned down by their voice ("deny, voice: more details follow"), the session
      asked to make the file, and they allowed that with the key. Their first try went
      to the session that had just explained the test, which had the focus for having
      spoken last; and the point of the exercise was not clear to them ("What's the
      point? Like what do I have to do right now?"): a check that needs a second
      session and a move of the focus wants a plainer set-up than it got. Not built: the terminal's "chat about this" as such.
- [x] Several questions in one dialog: answered by voice or number key, the overlay moves on
      to the second question, but the terminal goes on showing the first until the last one
      is answered (the author, 2026-11-17: "I sent an audio to answer the first question
      but on the terminal I still view the first question"). Both answers did arrive. The
      hook can only answer a whole dialog at once, so the terminal cannot be moved along;
      what could be done: say and show "question 1 of 2" so it is clear more are coming.
      Done 2026-11-17: the overlay writes "question 1 of 2" beside the name of who asks
      (it stood small at the end of the line about the keys) and the voice reads
      "Question 2 of 2: ..." for the next one. The author, asked in such a dialog the
      same night: "Yes, I see it" and "Yes, heard it".
- [x] With two or more languages, working out which one a recording is costs about 0.6 s,
      nearly as much as writing the sentence down (measured 2026-11-17, see "Numbers to
      publish"). Likely because the recording goes through the first half of the model
      twice, once to find the language and once to write the text; not looked into. If
      that pass can be shared, several languages would cost about the same as one.
      Done the same day: that was the cause, and the pass is now shared (`stt.Named`). A
      sentence of four seconds with English and Italian named went from 1.4 to 0.8 s. It
      leans on how faster-whisper 1.2 works inside; with an older one the hub goes the
      long way as before.
- [x] The spoken project name is off while the overlay is up; with many sessions and eyes
      away from the screen, the voices alone may not be enough to tell them apart.
      Asked on 2026-11-17 whether the name should be said again when many sessions are
      open, the author said: "I don't think it should right now. It's pretty good, pretty
      happy." So it stays off; `label: always` is there if that changes.
- [x] `hub/hub.py` is over 1,100 lines. Split it (permission requests, push-to-talk, the
      HTTP layer) before adding much more.
      Done 2026-11-17, at over 2,100 lines, on the author's choice from a list while they
      were away: whole sections moved unchanged into `hub/base.py`, `permissions.py`,
      `talk.py` and `server.py`; `hub.py` is 710 lines. All tests pass and the live hub
      runs on it. Left for later: `talk.py` is 645 lines and holds more than its name
      says (words on their way, side questions, stopping), and the section headings in
      it are from before.
- [x] The overlay gets in the way of a game (the author, 2026-11-17, by voice): when the
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
      Asked on 2026-11-17, the author first said the details should by default only open
      with `Ctrl+Alt` held, and a minute later, before it was live: "Actually never mind
      ... I like hovering ... opening up its details. It's fine." So the mouse still opens
      them, and the other way is there for whoever wants it: `claude-speaks overlay hover
      keys` (or `"hover": "keys"` under `overlay`). With it a mouse passing over the bar
      changes nothing, not even the light under it. Compiled and covered by a test for
      the command; nobody has looked at `hover: keys` on screen or in a game.
- [x] `first_audio` in `voice.log` is too high for a line whose first sentence is long (3 to
      8 s logged where the sound started within a second, as `heard` shows). The time is
      taken after the sentence was written to the player, and that write waits until the
      player has taken most of it. Take the time before writing. Done 2026-11-17
      (`tests/test_timing.py`); the running hub logs the old way until its next restart.
- [x] A hub that is running old code keeps old faults: a fix only counts once the hub was
      restarted. On 2026-11-17 a reply was cut by the author's own voice message two minutes
      after that fault was fixed and committed, because the hub had not been restarted yet.
      Say in `claude-speaks status` when the running hub is older than the code on disk.
      Done 2026-11-17: `status` adds a note naming the hub's files that changed since it
      started, and one when the overlay on screen is older than its source, each with the
      command that applies it. It shows from the next hub restart on. Not done: saying it
      anywhere but in `status` (the overlay could show it).
- [x] The picture check can catch the live overlay when the two overlap on screen.
      Done 2026-11-17 by another session while the author was away: the pictures are
      asked from the overlay's own windows (`tests/overlay_capture.ps1`) and no longer
      copied from the screen, and each run proves it by laying a colored window over
      the overlay first. The glass views, which only exist on the screen, look for a
      place free of other programs' always-on-top windows. It also has the views built
      that day (waiting marks, tick boxes, a question's place, stopping, queued, a side
      question). A tool for whoever works on the overlay; nothing a user of it meets.
- [ ] Seen in those pictures, not mended: a choice that wraps goes on under its box, not
      under its first word; with the clock mark, "9+" is hardly readable;
      the blur and acrylic glass look the same; a tick question's line about the keys
      wraps when "1 more waiting" is added.
- [x] `install.sh` has only been run in throwaway folders, never with the model download.
      Done on the evening of 2026-11-17: run in an empty home folder with nothing
      cached, so Python, the packages and both models really came from the network (22 s
      on the author's line, 906 MB on disk). A hub started from that install spoke a
      sentence through a stand-in player, and the install's own speech model wrote it
      back word for word. Found on the way: the speech model (464 MB) only came at the
      first hold of the talk key, 21 s in which the key seemed to do nothing; the script
      now fetches it.
- [x] `install.sh` on a machine that has nothing yet: no `jq`, `curl`, `uv` or sound
      tools, a real loudspeaker and microphone, and the overlay's first start. The run
      above was on the author's machine, where all of those were there already. A
      container would cover the tools; Docker is on the author's machine but not switched
      on for this WSL.
      Not done. Ticked on the author's word, 2026-11-17: "you can just tick it because
      we might as well do it in the end after the app is done." It is now part of
      "Making the repo public" below.

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
      - the start: done 2026-11-17 for listening. `install.sh` asks which languages you
        speak and `claude-speaks languages` changes it; the settings window should offer
        it too.
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
- [ ] Numbers to publish with it (the author, 2026-11-17: "in the future when I'll publish
      this tool it'll be great to have some metrics"). Measured so far, to be done again on
      the release and on a second, slower machine before any of it is quoted:
      - Speech to text by choice of languages (`tests/stt_speed.py`, 2026-11-17, Core Ultra 7
        270K with 24 threads, no graphics card, model `small`, median of 5 runs, sentences
        spoken by Kokoro):

        | You speak | 1 s of speech | 4 s | 12 s |
        |---|---|---|---|
        | English only | 0.6 s | 0.7 s | 0.9 s |
        | Italian only | 0.6 s | 0.8 s | 1.0 s |
        | English and Italian | 0.7 s | 0.8 s | 1.0 s |
        | Five languages | 0.7 s | 0.8 s | 1.0 s |
        | Any language | 0.7 s | 0.8 s | 1.0 s |

        One language costs the same whichever it is, and the English-only model is no
        quicker than the multilingual one told "English" (0.64 against 0.61 s). Two or more
        cost about 0.05 s extra. Before the language was found in the same pass as the
        words (same day) they cost 0.6 s extra: 1.2 to 1.4, 1.4 to 1.5 and 1.5 to 1.7 s.
        Every sentence was written correctly under every choice, so accuracy is not
        measured: that needs real, short, untidy recordings.
      - Line written to first sound: about 0.3 s with the hub warm (in `CLAUDE.md`).
      - Still to measure: real voices and a noisy room, the other model sizes, a slower
        CPU, memory, and how often a short recording is taken for the wrong language.
- [ ] Making the repo public. Before that: run `install.sh` on a machine that has nothing
      yet (see the ticked item under "Rough edges"; put off to here by the author).
- [ ] An adapter so other coding agents (Codex, Cursor and so on) get a light in the bar. The
      hub already takes plain events from anything that can send them.
      The author, 2026-11-18, by voice (the recording was cut twice, so only its gist):
      expand to other models "such as Codex, Gemini", and show which one a session is by
      its logo, the Claude logo "in center" of the light. Told in reply, nothing built:
      the middle of the light holds the status sign (check, "!", voice bars), as came up
      with the waiting number, so a small mark at the lower left of the light or before
      the name in the row would fit better; other companies' logos are trademarks, so
      marks of our own drawing or files the user supplies; and it only says something
      once a second agent can be connected. Their answer is open.
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
- [x] Usage in the overlay (the author's idea, 2026-11-17: "customizable bar that shows the
      usage, the five-hour window and the weekly usage"): a part of the overlay that shows how
      much of the plan is used up, in the five-hour window and in the week, and when each
      starts again. A setting like the rest: on or off, where it sits, what it shows.
      Built 2026-11-18 as two thin bars with their percent at the foot of the card of
      figures, read again every five minutes (`usage_shown`, `usage_every`,
      `usage_warn`). Not shown: when each window starts again, and the week of one
      model. **For the author to judge on screen.**
- [ ] Context window per session (same day: "for each session maybe something that indicates
      the context window"): a sign of how full each session's context is, for example a thin
      arc around its light and a figure in its row, with a warning color when it is nearly
      full.
      Looked into on 2026-11-17 by another session (Claude Code 2.1.327, plan Pro; two
      throwaway sessions and three headless calls; nothing built). All of it can be had:
      - plan usage, fresh and free: `claude -p "/usage" --no-session-persistence` answers
        in about a second without a model request, with lines such as "Current session:
        15% used · resets Nov 18, 2:39am", "Current week (all models): 37% used · resets
        ..." and "Current week (Fable): 70% used · ...". Text for people, so to be read
        loosely. It is the only place the week of one model shows.
      - plan usage, per session: what a status line command is handed carries
        `rate_limits.five_hour` and `.seven_day`, each with `used_percentage` and
        `resets_at` (documented). It is what that session's last answer from the model
        said, so an idle session's figures are old; the command is not run while idle.
        A status line command that prints nothing takes no row on screen.
      - context per session: the same report has `context_window` (`used_percentage`,
        `total_input_tokens`, `context_window_size`), keyed by `session_id`. Without
        a status line: the last assistant line of the transcript, input tokens plus both
        cache counts, gave exactly what `/context` showed; after a compaction the
        `compact_boundary` line's `postTokens`. The transcript does not hold the size
        of the window.
      - not to build on: the usage address the program calls with the login token.
      Built the same night for context, as words: each session's row of the details
      ends in "context 56%", counted from its transcript at every reply, step and
      prompt (`context_shown`, `context_window`); the row also carries the figure for
      a sign of its own later. Not built: the arc around the light, a warning color or
      word when it is nearly full, the usage in the overlay. A session that has not
      reported since the hub started shows no figure yet.
      2026-11-18: the author found the words too long beside the running time and chose
      the arc ("try 3", of: only the percent, up beside the title, an arc around the
      light). Built the same night: a thin arc around each light, clockwise from the
      top, orange from 80 percent on (`context_shown`: `arc`, `text`, `both`, `off`;
      `overlay.context_warn`, `context_color`, `context_warn_color`). Live on their
      overlay; **not judged by them yet**. To ask: is the arc readable at a glance, is
      the orange right (it sits close to the amber of "needs you"), and is the exact
      figure missed (it is nowhere on screen now). Still not built: usage in the overlay.
      Suggested first step: usage from the headless `/usage` call (overlay and voice,
      no change to anyone's settings); a status line forwarder and the transcript for
      context per session after that.
- [x] Room for a session's figures (the author, 2026-11-18: "so many metrics for each
      session ... revamp a bit the design of the layout ... to have space for them").
      Built the same night, the first of three ideas, on "let's try your pick": a row
      keeps only its running time, and a line under the rows names the figures of the
      session the mouse is on ("context 21%   last reply 64k   tasks 3/5   waiting 2";
      `row_metrics`, `detail_metrics`). Before judging it they asked for research and
      more thought ("the most important ... the visualization"), and the line became a
      card of four tiles, each a small name, a large figure and, for context and tasks,
      a thin bar (`overlay.details_style`: `tiles`, or `line`). What was read and why
      it looks as it does is in `CLAUDE.md`. The author on the card: "it's not bad",
      then, once the room around it was the same on every side: "Oh, it's perfect."
      Ideas
      from that look, not built: the plan's usage ("5h 41%, week 40%") as a thin line
      at the foot of the card, which would settle "Usage in the overlay" below; a mark
      for the kind of agent; the row dropping its time. If the card is not liked,
      the other two: a small column of two figures at the right of every row, or a
      third line in the row under the mouse (which stretches the bar).
- [ ] The history, reworked on the author's "do all of them" (2026-11-18): in the
      session's card, a mark per line for how the turn ended, time and tokens at the
      right, the newest brightest, a white dot on lines never heard to the end. **For
      them to judge on screen** (keep the details out with `Ctrl+Alt+L` and rest the
      mouse on a session). Since then, on their word: no time on the lines (tokens
      only), the two columns lined up, the missed dot on the mark, the plan's usage at
      the foot of the card, and key caps in requests. Offered and open: showing the
      history on plain hover too, a red step for context near full, hiding a turn's
      half-way word once its last line is there. Bars that glide: built on their
      spoken answer to a question (heard as "barstack live"); the motion is unseen.
- [x] Tokens per request (the author, 2026-11-18, as a side question: "is it possible for
      each request to ... show me the metrics of how much token you've used? Is it
      important?"). Possible: Claude Code's record of a session has the token counts of
      every reply, which the hub already reads for the context arc, so it could add up
      what one turn used (written, and by how much the context grew) and show it in the
      session's row when the turn ends, or say it on request. Not built; nothing was
      agreed about where it shows. On a subscription the plan's percent says more than
      tokens do, so this is mostly for seeing which request was heavy.
      Asked for outright minutes later ("for each reply, display the metrics, the token
      you've used") and built: when a turn has ended, the session's row says "64k
      tokens" at its right end until the next prompt (`turn_tokens`: `new`, `output`,
      `all`, `off`). On seeing it: "the label is good", but only the number, since
      the word takes room from the row's text; so it says "64k" now
      (`turn_tokens_label`). **Still to agree:** which figure they mean (the default
      leaves out what is read again at every step, which would make every figure
      millions) and whether the row is the place. Then asked for "as well in history": each line under the
      rows now has its turn's figure, at its right end since they did not like it
      right after the time; seen in a picture only. Not built: the figure said aloud, or while the turn runs.
- [x] Usage said aloud (the author, 2026-11-17, by voice: "check if in the future it's
      possible to make you say the percentage of the current usage"). Today a session
      cannot answer "what's the current usage?": nothing it can call reports the plan's
      five-hour and weekly windows, and Claude Code keeps no file with those figures (looked
      for in `~/.claude` the same day). The author can see them with `/usage`. It hangs on
      the same question as the two items above: whether the status line report carries
      the figures. If it does, the hub could hold them and answer by voice: a hotkey or a
      spoken "how much have I used?" that says, for example, "forty percent of the five
      hours, resets at three", and a warning by itself when a window is nearly used up.
      Built 2026-11-17 while the author was away, chosen by them from a list ("whenever
      I ask something about the usage ... tell me about the usage I have ... probably
      five hour window", to work like the side questions): spoken words that ask for
      the usage are answered aloud by the hub and reach no session, the five-hour
      window first, e.g. "35 percent of the five hours used, back at 2:39 AM. The week
      is at 40 percent, Fable at 76." `claude-speaks usage` prints it, `usage say`
      speaks it. `hub/usage.py` (by another session) reads it with a headless `/usage`
      call, 0.8 to 1.5 s, no model request. Which sentences count is strict
      (`usage.asks`): "add a usage meter to the overlay" goes to the session. Tried on
      the live hub with words sent as if spoken. The author's first real one,
      2026-11-18, was "Alright, so what's the usage?" and went to the session: no
      sentence opening with "alright" counted. Such openings ("alright", "yeah",
      "sure", "also") are passed over now; **not asked again by their voice yet**. Not built: a key for it, the warning by itself near the limit, Italian.

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

- [ ] A key that stops the session in focus (the author's idea, 2026-11-17: the cancel key
      "could be more universal and stop the process ... of that session", not only take
      words back in the four seconds after sending). It would also make taking back real
      for a session that already has the words: today it is only told to ignore them.
      What can stop a session from outside, measured the same evening with a throwaway
      session (Claude Code 2.1.327):
      - an interrupt signal to its process: no. The whole session exits.
      - a hook: yes, in any terminal. A `PreToolUse` hook that answers `continue: false`
        together with a refusal of that call stops the turn at its next step, and the
        step is not run ("hook stopped Claude"). Without the refusal the step still
        runs first. A step that is already running finishes, and a reply that is only
        being written is not stopped at all.
      - Esc written into its terminal: yes, at once, in the middle of a step
        ("Interrupted"). Done through tmux here. For VS Code the extension would have to
        write it (`Terminal.sendText`), which needs the hub to talk to the extension;
        nobody has tried that. Nothing else can type into a terminal on this machine.
      Offered: a double press, since the same key also cuts a line being spoken and one
      slip would end real work; the author: "double pressing might be too much work".
      Then a key of its own (`Ctrl+Alt+Esc`); the author: "What if Control Alt Backspace
      does the job ... Isn't that better?" Built that way the same evening, through the
      hook (`hooks/stop.sh`, now in `~/.claude/settings.json` on the author's machine).
      One press does the first that applies: throw away a recording; take back what was
      just sent, ending the session's turn if it has the words; cut the line being
      spoken; end the turn of the session in focus while it works. `cancel_stops` is
      `always`, `sent` (not the last of those) or `never` (as before: told to ignore).
      Checked with the real hook on a throwaway session, before a step and during one.
      Pressed by the author that night on a session working in small steps: the hub
      logged "its turn was ended 1.8 s after the key", and they said "It seems to be
      working." Not tried by them: the key right after sending words, on a session
      that has them. How it was tried: give a session something with several
      steps, put the focus on it and press `Ctrl+Alt+Backspace` while nothing is being
      said; its light should show a red stop sign and its turn should end within a step.
      Open:
      - a turn that is only writing, with no step left, cannot be stopped; it ends by
        itself and what it says is not spoken
      - instant stopping through the VS Code extension: built later that night, on the
        author's go-ahead, while they were away. The extension keeps a request open
        with the hub and types one Escape into the terminal the hub names
        (`stop_at_once`). Measured first on a throwaway session: one Escape or one
        Ctrl+C interrupts a working session; a second Ctrl+C closes the session and a
        second Escape at an idle prompt opens its rewind list, hence one Escape, and
        only for a session in a turn. Tested with the real extension code against a
        real hub and a stand-in for the editor. Version 0.2.0 is installed, but
        **VS Code still runs 0.1.0 until its extensions are restarted** (Ctrl+Shift+P,
        "Restart Extension Host"); after that, to try: the cancel key on a session
        that is working should stop it in the same moment, and `hub.log` should say
        "escape asked of the editor". Not known until then: whether VS Code hands
        the Escape to the terminal as typed.
        Tried by the author on 2026-11-18, after VS Code had been restarted: the key,
        pressed while a session ran a command of forty seconds, cut the command off
        and ended the turn, and the log said "escape asked of the editor for its
        terminal". They have not said whether it felt instant.
      - the key is now claimed from every program whenever the session in focus works
      - a session waiting at a permission prompt is not stopped by the key in focus
- [ ] Easier ways to take back what you said (the author, 2026-11-17: "it would be really
      cool to somehow cancel with a shortcut"; today it is `Ctrl+Alt+Backspace` while the talk
      key is still held, a four-key grip). Built the same day: the same key within four
      seconds after sending takes the words back (see "To try by hand"). The spoken ending
      below was turned down by the author: it could throw away a message they meant.
      The other ideas, none chosen:
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
- [x] The focus follows the terminal you go to (the author's idea, 2026-11-17: "if I focus
      on a terminal it would be great to automatically select that" session). Built the
      same day as a small VS Code extension (`vscode/`, `claude-speaks vscode install`):
      VS Code tells it which terminal became the active one, it tells the hub that
      terminal's process, and the hub gives the focus to the session running there
      (`terminal follow off` turns it off). Installed on the author's machine and seen
      starting in VS Code's log; the real extension code is tested against a real hub
      with a stand-in for the editor. In use since: by the evening of the same day
      `hub.log` had 79 lines "focus on ...: its terminal came to the front" from the
      author going from terminal to terminal. They have not said in words that it is right.
- [ ] What following the terminal does not do yet:
      - VS Code only reports a change of the active terminal. Clicking back into the
        terminal you were last in (from the editor, or after another session spoke and
        took the focus) reports nothing, so the focus stays where it was. No extension
        interface says "this terminal got the keyboard". Claude Code knows when its
        terminal gains the keyboard, but no hook reports it.
      - `install.sh` offers the extension since 2026-11-17 (done by another session
        while the author was away): where a `code` command is found it asks once, of a
        person at a terminal on a full install; `--vscode` and `--no-vscode` answer
        ahead; one already installed is brought up to date without asking; from a
        script VS Code is left alone. `uninstall.sh` removes it (`--keep-vscode`
        leaves it). Run end to end in an empty home with real downloads and a stand-in
        for `code`; a fresh install registered exactly the hooks of the snippet,
        `stop.sh` among them (`tests/test_install.py`, 16 tests). Not tried: the
        question itself by a person on a machine that does not have the extension,
        and a "no" is not remembered for the next install.
      - Only VS Code; another terminal program would need its own way.
      - It could also move at the moment you send a typed prompt (a few lines in the hub).
- [ ] More for the VS Code extension, now that it exists: color the tab itself in the
      session's color, and bring the terminal of the session in focus to the front (the
      jump key above). Both need the hub to talk to the extension, which today only
      listens to VS Code and tells the hub.
- [ ] Not tried: ringing a terminal's bell when its session speaks, which VS Code can show
      as a small sign on the tab for a moment (its visual bell setting is off by default).
- [ ] A phone notification when a session needs you and you are away
- [ ] Spoken summaries in the language you spoke (they are always English today; part of
      "Any language" above)
- [ ] Running the speech model on the graphics card to make transcription faster
