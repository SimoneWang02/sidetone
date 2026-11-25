# To do

What is left for Sidetone, in the order to do it (the author, 2026-11-19: "what's the best
course of actions? ... documentation could be done in the end after all features have been
implemented"; the order was offered and they said "Yes, do it"). First try what is built, then
answer the open questions, then make speech work well in the author's languages, then the
small extras, then choose what the first public version needs, release it, and the
documentation last. Everything that is done is at the end, kept for its history.
`CLAUDE.md` has how things fit together, `docs/dev/features.md` the details of each feature.

The author's direction for all of this: people who download the tool should be able to
customize as much of their experience as possible. New looks and behaviours come as settings,
not as replacements.

## 1. Try what is built

Built, and working in the automated tests or in pictures taken from WSL, but not yet tried
by the author with the real keys, voice or eyes. Every untried feature may hide a bug, so
these come before anything new.

- [ ] A spoken line with no `lang` in its tag: the hub now guesses its language from the
      words (2026-11-22, `hub/language.py`, no setting; see `docs/dev/features.md`), so an
      Italian line without the mark gets the Italian voice. Each guess goes to `hub.log`.
      **Not heard by the author yet**: listen for an unmarked Italian or Chinese line read by
      the right voice, and an English one never read by the Italian voice.

- [ ] Clearing progress (2026-11-24, `clear_progress`): a turning ring and "Clearing sidetone 2…"
      until it is done, and no second /clear typed meanwhile. Tests and pictures only, **not yet
      tried by the author**; best tried with VS Code's window covered for some minutes too.

## 2. To decide

Questions for the author; nothing to build until they answer.

- [ ] VS Code types up to a minute late while its window is hidden (`docs/dev/facts.md`): start
      it with `--disable-background-timer-throttling` (to be tried) so that clear, stop and end act
      at once?

## 3. Speech in the author's languages

What gets in the way every day: words heard in the wrong language, lines read by the wrong
voice, and the wait for the transcript.

- [ ] A model of the author's own voice from their kept recordings (`keep_recordings`, on for
      them since 2026-11-22: "register every message I send and create a voice model based on
      my speaking ... you don't have to do the voice model right now"). Chosen the same day: a
      voice that speaks like them ("I want to hear my voice"); Whisper tuned to them is the
      second idea. Kokoro cannot be trained to a voice; a zero-shot cloning model can copy one
      from about ten seconds of clean recording, on the RTX 5070: Chatterbox Multilingual (MIT;
      English, Italian, Chinese) or Qwen3-TTS (Apache-2.0), to try side by side on their
      recordings. Fine-tuning on the kept pairs later if the likeness is not close enough. Their
      first real recording landed in `recordings/` on 2026-11-22.
      For everyone, not just the author ("my ultimate goal is for this tool to be used by people
      so they will have to register their voice"): optional, local only, said plainly where it is
      turned on (nothing leaves the machine). Before building it in, measure how long the
      cloned voice takes to start a line on the GPU and on a CPU: Kokoro starts fast on a CPU,
      and a slower voice works against the whole point. Kokoro stays the default; the cloned
      voice is one more engine to choose.
      Tried 2026-11-22: Chatterbox Multilingual 0.1.7 in its own venv
      (`~/.local/share/voice-clone`, `try.py`; its torch 2.6 pin overridden to 2.8.0+cu128 for
      the RTX 5070, and `setuptools<81` for its watermarker), cloned from one 40 s English
      recording. Loads in 7 s, 3 GB of GPU memory. A 4.4 s English line took 3.4 s to make, the
      Italian one 2.1 s; a short Chinese line came out 10.6 s long (perhaps padding or babble).
      Whole lines only, no streaming yet, so each waits that long before it starts. Every clip
      carries Resemble's inaudible Perth watermark. The author: "really close. That's scary".
      Italian from their Italian recording sounded to them "like a Chinese accent"; Italian from
      their English one was closer, if slower. They want it to get better on its own while they
      work ("mentre uso questo tool miglioro la qualità del modello"). Two steps: (1) with no
      training, the fingerprint averaged over many recordings (`embeds_from_wavs` takes a list)
      and the best 10 s picked as the reference, redone as recordings come in; (2) a fine-tune of
      Chatterbox once there is about an hour of recordings, with the words checked first, run on
      the GPU while the PC is idle. 3.7 minutes kept by then (7 English, 4 Italian).
      Step (1) made by hand the same day (`clone/build_voice.py`, 12
      recordings, 4.6 min); not yet redone on its own as recordings come in. The author agreed
      to both steps and sees it in the product: anyone who turns it on has every message they
      say kept, locally, to build a voice model of their own while they work.
      The author then heard "tipo il microfono ... qualche scratch" at the start and end of
      each line: the cloned voice copies the talk key's click at both ends of every recording
      (bursts of 0.03 to 0.4 s before the first word and after the last). `build_voice.py` now
      leaves out each recording's first 0.35 s and last 0.5 s and any sound under 0.25 s, and
      trims such a burst from what it makes. The author, by ear: no noise left, "perfetto".
      The scripts are in `clone/` (its README says how to set it up).
      The author, 2026-11-22: "that's a side quest, it's not urgent"; so it comes last in
      this step.

## 4. Small extras

Roughly easiest first, the larger ones after.

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
      - Done 2026-11-18, while the author was away and without their word on it: a
        prompt typed to a session gives it the focus (`focus_on_prompt`, on; false
        turns it off). It covers the first point above for whoever types: back in the
        terminal you were in last, the first prompt moves the focus there. Tests
        only; **for the author to notice in use, and to say if it is unwanted**.
        Their try on the evening of 2026-11-18 could not show it: going to the second
        terminal had moved the focus already. Not to be asked for again as a test.
- [ ] One conversation open in two terminals (resumed in a second one; the author, 2026-11-22:
      "two terminals that are pointing into the same session. If I close one, I close ... the one
      in the overlay"): closing one now keeps it, and its terminal becomes the one left
      (`Session.pids`). Still one row for both, since they are one conversation. **Not tried
      by the author.** A rare case (the author, 2026-11-22: "Do you think we should ... move
      on"): left to the full bug hunt before release, which tries it in a lab.
- [x] Bug hunt, 2026-11-22 (the author: "do many combination of things that could happen"), in a
      lab: real haiku sessions in tmux, hooked to a silent hub of their own (no overlay), driven by
      a script. Fine: /clear keeps the row; two sessions in one folder; a conversation resumed in a
      second terminal, either one closed; a terminal killed outright (row gone in 1 s); Ctrl+C
      twice; /resume to another conversation inside a session; the hub restarted mid-turn (and
      words reaching an idle session once its listener is back, 5 s); a terminal closed during a
      permission prompt; Esc mid-turn (idle in 3 s); words to a busy session (read after its next
      step); the cancel key (turn ended 3.6 s after). Fixed: a conversation cleared in one of two
      terminals dropped the other (came back renamed, its reply not spoken); a background
      subagent's permission prompt was dropped when the main turn ended. Learned: Claude Code
      shows a background subagent's dialog only once the hook returns, so the hub can answer it
      only in its first 9 s (docs/dev/facts.md).

- [ ] Try: the VS Code window of the session comes to the front (the author, by voice,
      2026-11-24, with three projects in three VS Code windows: "whenever I switch this session
      in the overlay, I want the Visual Studio Code page to pop up in front"; over a browser:
      "No, another program, no. I have to have focus ... on one Visual Studio page"). Built the
      same day: `terminal.window`, "Switching Brings Its Window", off by default (the default
      was left to Claude), extension 0.7.0. Needs the extension restarted in each window
      (Ctrl+Shift+P, Restart Extension Host). Not tried by the author; the switch between
      windows itself was measured with `code --new-window` (80 ms, no reload), not yet through
      the extension in the real VS Code.

### Larger extras

- [ ] Make more of the overlay a setting: sizes, colors (session palette, status colors, glass
      tint), which keys do what, what the panel rows show, animation speed or none, where the
      bubble goes. Much is fixed in `overlay/Overlay.cs` today.
      Animation: "Reduce Motion" built 2026-11-22 (`overlay.still`, also on with Windows'
      animation effects off). **Not tried by the author.** Size: "Size" 75 to 150 %
      (`overlay.size`), built the same day at their word ("let the user pick ... You decide");
      pictures at 75 and 150. Tried by the author: it follows the slider while dragged, after
      they asked for it "more responsive"; then "Looks good".
      Colors: the five status lights and the glass's own color, built 2026-11-23
      (`overlay.working_color` ... `idle_color`, `glass_color`; defaults as before), pictures
      `own-colors*.png`. In the settings window the same day, a Colors section (the author chose
      ready colors plus a typed code): the five lights, Glass, Microphone. On 2026-11-24 the
      tenth ready color became a color wheel that opens a picker of any color, at their word.
      **Not tried by the author**: pick a ready color, type a code, Reset, drag in the picker
      (the overlay follows; chosen when the list shuts). Still only in `config.json`: the waiting
      mark's and the context arc's colors and the session palette. The rest (the keys held with
      the mouse, what the rows show, where the bubble goes) moved to after the release on
      2026-11-24 (the author: "are this necessary? ... we can skip them").

## 5. What the first public version needs

To choose before release: which of these the first version has, and which wait.

Where it stood on 2026-11-22: everything before this step done or left by choice. Claude's
proposal, not yet decided: version 1 for Windows with WSL only, as a plugin, with the
installer fetching the chosen languages' voices and the hub's own words in any language;
native Windows, the Linux and macOS overlay, other agents and the cloned voice later. The
author: "this is the next step ... I don't have time right now to follow you. And I don't
want you to do it autonomously. I want to follow you in this progress." So this step and
the ones after it are done together with them, not by a session alone.

- [ ] Packaging as a Claude Code plugin, so it installs in one step.
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
      Assessed 2026-11-24 by a Claude agent from the code (read-only; the day counts are rough
      guesses): native Windows moderate to hard, 6 to 10 days (the hub imports `fcntl`, uses a
      Unix socket, `os.killpg`, `/proc`; hooks need `jq` and `setsid`, missing from Git Bash;
      Claude Code's `type: "http"` hooks could replace most scripts, `listen.sh` stays a
      command; the overlay only loses its `wslpath` and `/mnt/c` code). Linux moderate, 8 to 12
      days: the hub and hooks already work there, but there is no overlay and so no keys (a
      keys-only helper first, 1 to 2 days, then a Qt overlay on the same JSON lines; Wayland
      limits always-on-top, blur and global keys). macOS hard: no `setsid`, `paplay` or `parec`,
      about 3 days for hub, hooks and sound plus 4 to 5 for the Qt overlay. Suggested first, about
      2 to 3 days: a `hub/platform.py` (sound in and out through sounddevice, the loudness meter
      fed from what the hub plays, process groups, the lock, folders), the transport behind one
      function, the hub detaching itself in place of `setsid`. Order: Windows, Linux, macOS.
- [ ] An overlay for Linux and macOS. Today it is Windows only on main. The Mac was built the
      night of 2026-11-24 on the branch `mac-overlay` (a native Swift overlay, sound through
      PortAudio), proved on GitHub's Macs but not tried on a real one; that branch's TODO.md and
      docs/dev/features.md ("The Mac") have the details. Report:
      https://claude.ai/artifact/JbET3SN5962skmzHzPwt7j
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
- [ ] Any language, chosen by the person who installs it (the author, 2026-11-17, said in
      Italian: not only English and Italian, the program should be "customizzabile
      dall'utente che lo scarica", so in the end every language). Listening is nearly there:
      `whisper_language` already takes any language codes, or `auto`, with a multilingual
      model. What is still tied to English:
      - the start: done 2026-11-17 for listening. `install.sh` asks which languages you
        speak and `sidetone languages` changes it; the settings window should offer
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
      Asked again 2026-11-19, now with their own voice: "an option of selecting my voice
      for [a] session, and I'll train the model that uses my voice". So the first
      recording is the author's own (their consent is given), and their voice becomes one
      to choose per session in the settings window, Voices.
- [ ] Languages as packs you install, so each person chooses how much storage it takes
      (built 2026-11-23, not yet tried by the author: `hub/packs.py`, `sidetone languages`
      fetching first, the reminder naming the languages on, the English notice, the settings
      window's Install with its size and a bar, Remove, ticking a voice fetching it. The author
      installed Chinese from the window on the second machine (2026-11-23, 20:02); not yet
      heard speaking Chinese there. Also built
      the same night, not yet tried by the author: recorded samples to hear a voice before it
      is downloaded (and Chinese's voices listed before Install), the summary language
      offering only languages installed, Remove for a language that is installed but off)
      (agreed with the author 2026-11-23, from a second machine without Chinese: "for chinese
      i want to install it from settings no?"). Today `install.sh` fetches only English;
      Paola and Kokoro's Chinese model v1.1-zh with `misaki-fork[zh]` were put on the author's
      main machine by hand on 2026-11-19, and nothing fetches them.
      - One switch per language in the settings window's Voices page, the same as now
        (`speak.<lang>`), but it now means installed and on: it listens for it and speaks it.
        A language not installed shows its size and an Install button, then a progress bar,
        then "Remove (frees N MB)". `install.sh` asks the same, with the sizes, and
        `sidetone languages` does the same thing, so all three install the same packs.
      - Only the voices ticked are fetched (the author: "i dont need all 100 chinese
        voices"): Hugging Face has each v1.1-zh voice on its own (`voices/zf_001.pt`, about
        0.5 MB), so a voice ticked later is half a megabyte. The 325 MB model is shared by
        all Chinese voices. Piper voices are a model each (Paola 63 MB, the Piper program
        26 MB once). Italian's two Kokoro voices are already in the English model.
      - ▶ before installing plays a short recorded sample of each listed voice, shipped with
        sidetone (about 15 KB each).
      - The size shown counts the multilingual Whisper model (about 480 MB) when the first
        language other than English is turned on.
      - A language not installed is never spoken (the author: "people who doesnt have
        installed chinese, are not expecting chinese responses"): the voice reminder lists
        the languages that are on, and a line written in another one comes in English;
        Kokoro 1.0's espeak Chinese voices are no longer used. A line still tagged with a
        language that is off (Claude not following) says a short English notice instead.
      - A language off is not listened for, so spoken Chinese cannot come in; only typed
        Chinese, or someone asking for a Chinese answer, gets there.

## 6. Release

- [ ] A full bug hunt once the first public version is built and the code stops changing much
      (the author, 2026-11-22): a clean install on a fresh machine, every feature together,
      long sessions. Also, left to it: one conversation open in two terminals and closed in
      one (step 4).

- [ ] Numbers to publish with it (the author, 2026-11-17: "in the future when I'll publish
      this tool it'll be great to have some metrics"). Measured so far, to be done again on
      the release and on a second, slower machine before any of it is quoted:
      - Speech to text by choice of languages (`tests/stt_speed.py`, 2026-11-17, Core Ultra 7
        270K with 24 threads, on the CPU (the RTX 5070 was not used), model `small`, median of 5 runs, sentences
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
      - Line written to first sound: about 0.3 s with the hub warm (in `docs/dev/facts.md`).
      - Still to measure: real voices and a noisy room, the other model sizes, a slower
        CPU, memory, and how often a short recording is taken for the wrong language.
- [ ] Making the repo public. Before that: run `install.sh` on a machine that has nothing
      yet (see the ticked item under "Rough edges"; put off to here by the author).

## 7. Last

- [ ] Documentation (the author, by voice, 2026-11-19: "make it like well-documented ...
      for each feature having a GIF and in the end putting a video registration on me
      watching a YouTube video while I'm using you, which is the real context of why I'm
      built in this tool"). So: a page per feature, or a section of the README, each with a
      short GIF of it on screen; and, to close, a real recording of the author watching a
      video while sessions speak, get answered by voice and ask for permission, as the
      story of attention latency told in one picture. The overlay's own pictures
      (`tests/overlay_check.py`) cover single views, not motion; GIFs need a screen
      recording from Windows, and the video has the author's sound and voice in it.
      **Last, on the author's word** (2026-11-19: "I would do the doc at the end of
      everything so you know there's more features to document and it's like the final
      completion of the product"). Not to be offered as the next thing before then.
- [ ] A demo video with sound and screenshots for the README, plus a measured comparison with
      tools that only speak after the reply has ended.
- [ ] Practice speaking (the author, by voice, 2026-11-20: "put at the end of the to-do list
      with the documentation stuff like practice voice-[speaking]. I'm not sure if the things I
      say gets transcribed well"). Wording not settled: a way to speak and see what the speech
      model wrote without sending it anywhere, or a guide on speaking to it. To ask when
      this step comes.

## Later: away from the PC

The author's idea, 2026-11-17: with sessions open and nobody at the desk, "is it possible to
use like either phone or AirPods interaction to do stuff", for example an AirPods gesture
that starts push-to-talk. Nothing below has been tried; the notes are guesses to check first.

- [ ] Decide the safety line first. The hub listens on a Unix socket on purpose, so that
      nothing outside this machine can make it speak, approve or inject. Anything from a
      phone opens that door a little: it should go through a login that already exists
      (SSH), never a new open port, and approving from afar may deserve its own switch.
- [ ] AirPods paired with the PC: a press on the stem reaches Windows as a media key
      (play/pause, next, previous). The overlay could claim one as a talk key: press to start
      recording, press again to send, since a press cannot be held. To check: whether the
      overlay can take the key away from the music player, how to keep it out of the way
      while music plays (only claim it while a session is open?), and how bad the sound gets
      when Windows switches the AirPods to their microphone mode (playback drops to phone
      call quality while the microphone is open). Works only within Bluetooth range.
      Asked for again on 2026-11-24 (the author was listening to a message while walking away
      from the PC and wanted to answer), with their AirPods Pro 3 and Bose QC Ultra Headphones 2.
      Read up that day by an agent, nothing tried here and neither headset tested in anything
      found; the main source is one project's logged trials with a Shokz headset on Windows 11
      (github.com/johnjuuljensen/GodMode, `tools/GodMode.HeadsetSpike/README.md`):
      - the press went to Windows' current media session (SMTC), not to the keyboard hook; some
        older reports do see a key (0xB3), perhaps when no media session exists. The overlay
        would hold a media session of its own only while a session waits for a reply, since
        the music player gets no button meanwhile, and takes the session when it starts.
      - with the headset microphone open no press reached SMTC, so the second press (send) is
        the hard part. There, reporting a VoIP call to Windows (24H2 or later) turned it into
        "end call". AirPods may send mute instead. Otherwise: press to start, silence to send.
      - the microphone took 0.7 to 1.1 s to open (so a tone says when to speak), and full
        quality came back about 5 s after closing. Stray presses come during the switch.
      - Bose pauses when taken off, which may look like a press.
      - tried with the Bose on 2026-11-24 (a throwaway logging window, one press each; build
        26300; Spotify paused but open): with a media session of ours, a press came as Play
        while it said paused and Pause while it said playing, a double press as Next; the
        hook saw none of them (without our session the press went to Spotify). Taking the
        headphones off and on sent nothing, with nothing playing. With the Bose microphone
        open (first audio after 0.8 s, the count from one to ten heard whole) no press
        arrived, neither plainly nor with a VoIP call reported (the author pressed in both;
        the test said "Got it" wrongly in the call, for two mute events of its own start). So: press to start works, the second press does not, so far.
        Windows' default microphone is the Nuroum on the desk: the hub would have to
        open the headset's by name. (Later that day the default was the Bose's own, which
        distorted playback while talking, as the author noticed; see `docs/dev/facts.md`. Not
        yet set back: changing it from a session was refused. The Nuroum is the webcam and does
        not follow them to another room, the author objected; tried: the Bose over LE
        Audio, which Windows does not carry the sound over, so far. Paired again, Windows calls
        the headset "Leviathan", and the default is the Nuroum again.) Not tried: Spotify playing, AirPods, through a wall.
      - second test with the Bose, the same evening (`tests/headset/run.sh`; AirPods: `--mic=`
        and part of their name in Windows), one try of each: microphone closed, a press came
        as Play again. Microphone open: one press, two, and a hold all sent nothing. In a
        reported VoIP call: one press nothing (as in the first test), **two quick presses "end
        requested"** (1 s after the tone), a hold nothing. So press to start, double
        press to send can work on this headset; seen once, not yet repeated. The part with
        music playing was skipped by the test (nothing was playing when Start was pressed).
      - the rehearsal with the Bose (`tests/headset/run.sh --rehearse`), the same night: press
        once, microphone and reported call, a tone, talk, two quick presses. **5 of 5 rounds
        started and were sent**; the tone came 0.73 to 0.84 s after the press. Spotify playing:
        with our session saying paused the press went to Spotify (it paused); with ours
        closed and back saying playing, it came to us (Pause) and Spotify played on. Taking
        the headphones off and on with music sent nothing and Spotify played on. So our session
        has to say playing while it wants the press over music, and then the press does not
        pause the music. The taking off (here and in the first test) says nothing about other
        people's headsets: the author has Bose's pause on taking off turned off, for its false
        alarms. Left on, it probably comes as Pause, which is also what a press is while our
        session says playing. While it says paused a press is Play, so a Pause can be ignored:
        say paused when no music plays, and have a recording without words send nothing. Not tried: AirPods, distance, a press while a reply is being spoken.
      - built the same night on the author's word ("we can proceed"; a minute after a session
        speaks was proposed and not objected to), in this repo in files of its own
        (`headset/Headset.cs`, `hub/headset.py`): `headset_button`, "Headset Button", off by
        default, on in their config; the auto pause is in the setting's description ("we can
        notify this to users"). **To try by them**: their first press
        arrived (2026-11-24, 23:56) but the Bose's microphone gave no sound, since it was paired
        again with LE Audio on (see `docs/dev/facts.md`); talking and sending are not tried yet.
        (`tests/headset` needs `--mic=Leviathan` now.) Paired again since, it gives
        sound. The music is left playing while you talk, in call quality: pausing it was offered,
        the author: "we can move on ... It's not a big deal" (2026-11-25).
        **Used by them** at 00:01 that night, start to end: pressed, open after 0.77 s, two
        presses, 4.5 s heard as "Is there a fix to that?" and sent to this session. Left to
        try: from the kitchen, over music, the keyboard's media keys, AirPods.
        Seen live without a press: it took the button from Chrome while that played and gave
        it back, and opened the Bose microphone in 0.6 s, in a call. Keyboard media keys in that
        minute are passed on to the music, also not pressed by anyone. Not built: wired
        headsets, Mac and Linux.
      - to check by hand first, with a small logging window: what the hook, SMTC and the VoIP
        call see for a press with nothing open, with Spotify, and with the microphone open;
        and whether Windows records from the headset at all (there is a Nuroum V11 microphone).
- [ ] AirPods on the phone, PC out of range: the phone has to be the bridge, because the
      gestures cannot be given to another program there. Candidates:
      - a phone Shortcut ("Hey Siri, tell Claude ...", or the Action button) that dictates a
        sentence and runs `sidetone follow-up` on the PC over SSH. Needs no new server,
        only a private way to reach the PC (for example Tailscale).
      - spoken summaries as phone notifications; the phone can read notifications aloud
        into AirPods. This grows out of the "phone notification" idea below.
      - allow and deny from the phone: buttons on the notification, or a Shortcut that runs
        `sidetone allow|deny`.
      - a small phone app of our own could read AirPods head movement (nod to allow, shake
        to deny) and stream the voice. By far the most work.
      - Claude Code's own remote control from the phone may already cover typing and
        approving; check what it does before building any of this.
- [ ] A phone notification when a session needs you and you are away

## After the release

- [ ] The rest of the overlay as settings (from step 4, 2026-11-24, the author: "we can skip
      them"): the keys held with the mouse (`focus_wheel`, `drag_keys`, `reorder_keys`, only in
      `config.json`), what the panel rows show, where the bubble goes.

The two below were step 4's larger extras, moved here on 2026-11-24 when the author chose to go
on to the release ("let's go to publish unless there's something else to implement first"):

- [ ] More layouts as options. Three were built and removed on 2026-11-17 (lights sized by
      importance, a thin line of light at the screen edge, one small window per session); the
      code is in commit `8558c4a`.
- [ ] Pronunciation and English feedback from push-to-talk (the author, by voice,
      2026-11-19: "a feature that let you register my voice and evaluate the correctness
      of my English ... evaluate our pronunciation of the words"; asked "What do you
      think?"). The thought: developers already speak to it all day, so the recordings are
      practice that costs nothing extra. On hearing that: "I think it's a good
      feature." Kept for later, not started. Notes for whoever builds it:
      - Opt in, off by default; recordings and results stay on the machine (a folder
        under `~/.local/state/sidetone/`), with a way to delete them.
      - Never in the way: no correction while you are talking to a session. A report you
        ask for (`sidetone english`, or by voice), said in a few sentences and with the
        details in a page or the settings window.
      - Two separate things. Grammar and wording: the transcript is enough, and a side
        copy (as for side questions) or a small local model can suggest a better
        sentence. Pronunciation: harder, because Whisper is built to guess the intended
        word, so a mispronounced word often comes out spelled right and nothing shows.
        Whisper's per-word probability (`word_timestamps=True`) is a cheap first signal
        of words it found hard. Real scoring needs the sounds: a phoneme recognizer
        (for example wav2vec2 trained on espeak phonemes) run on the clip, compared with
        the expected phonemes of the transcribed words (`espeak-ng --ipa`, already a
        dependency), word by word. Kokoro could then say the word the right way.
      - Measure before promising: synthetic voices are too clean to test it; it needs real
        recordings with known mistakes, the author's own among them.

- [ ] A weekly scheduled task that reads Anthropic's and Claude Code's release notes for
      changes the tool depends on (the author, by voice, 2026-11-22: "when this is published
      ... a schedule task weekly to see if Claude has made any changes to their models and
      stuff ... What if Anthropic in the future they increase the window to 5 hours to 6
      hours? I need to update this tool as well"). Fixed in the code today: the plan's two
      windows (five hours and seven days, the bars' 5H and 7D labels and the spoken
      "five hours" in `hub/usage.py`), the model names in the usage figures (Fable), and the
      hook events and session files the hooks read. The author makes it once the tool is
      published, not before.

## Done

Kept for the history: what was asked, what was found, and the author's words on it.

### Tried by hand

- [x] Ctrl+Alt+Plus opens a terminal beside the
      session in focus, in its folder, with Claude Code started and the keyboard in it, and that
      session gets the focus; Ctrl+Alt+Minus pressed twice ends the session in focus (/exit) and
      closes its terminal ("Ctrl Alt plus and Ctrl Alt minus to add a terminal session and
      remove it"). Needs the extension 0.5.0 (`sidetone vscode install`, then Restart Extension
      Host). The keystrokes measured in tmux; the editor's part (split, typing, closing) not
      seen working yet. Tried by the author the same hour: the new terminal opened beside and its
      session took the focus (log); they ended this session by mistake with the end key.
      Again 2026-11-22 17:04, on purpose: opened beside, focus moved to "sidetone 2"; it showed
      the history of an earlier "sidetone 2" (mended the same hour: lines of an ended session
      leave once its name is taken again).
      Ctrl+Alt+Minus twice on "sidetone 2" closed its session and its terminal (the author:
      "Close there. Nice."). Both keys tried by hand.
- [x] Mixed languages: what happens when one speaks Italian, English and Chinese mixed in
      one recording or one turn ("se tipo iniziasse a parlare in italiano, in inglese, in
      cinese, mischiati, come funzionerà"). To look at: Whisper picks one language per
      half minute of recording (`stt.Named`), so a mixed sentence may come out in one
      language; the reminder asks for "the language of my last message", which is
      unclear when it mixes; the speak tag carries one `lang`, so a mixed line is said
      by one voice (the Chinese model already reads Latin words as English; Kokoro's and
      Piper's Italian voices do not read Chinese). Try it for real first, then decide.
      Seen the same night: a session answered in Italian without `lang="it"` (the user's
      message had come through as English), so the English voice read Italian words. A
      safeguard, built 2026-11-22: when the tag has no `lang`, the hub guesses the language
      of the line itself (step 1).
      Tried by the author 2026-11-22 (Italian, English, Chinese in one message): it came back
      all English. Built the same day (`whisper_mixed`, see `docs/dev/features.md`): an unsure
      long recording is written part by part, each in its language, cut at pauses; the same
      recording then came out right. The spoken reply's single `lang` is unchanged.
- [x] The voice on the graphics card (2026-11-22, `voice_device`, "Voice Made On"): the first
      sentence of a line made in 0.12 s instead of 0.78 s. Built and tested in a scratch venv;
      the hub's environment needs onnxruntime-gpu 1.26.0 in place of onnxruntime and four more
      NVIDIA packages (`gpu.VOICE_PACKAGES`), which the author installed by hand the same
      day. Live after a hub restart: `first_audio` 67 ms for an English line and 90 ms for
      Sara's Italian (0.55 to 1.5 s before).
      The author, by ear the same day: "It sounds the same and I think it starts sooner".
- [x] Push-to-talk on the graphics card (2026-11-22, `whisper_device`, "Transcribe On"):
      `large-v3-turbo` on the RTX 5070, 0.18 s where `small` on the processor took 0.81 s,
      with clearly more words right (`docs/dev/facts.md`). Built and tested with NVIDIA's
      libraries borrowed from the voice-clone venv; installing them into the hub's
      environment was refused by the permission check; the author installed them by hand
      the same day, and the hub was restarted (it loads from them: 0.18 s a message).
      The author, by ear the same day: "it was faster" ("è stato più veloce").
- [x] A session's first spoken words before anything was typed to it (mended 2026-11-17:
      the first session after the hub had gone away had no listener until its first
      prompt; the author spoke to it twice and asked "why are you not receiving audio
      inputs?"). Tests only. 2026-11-20: a new session opened while the hub ran got a spoken
      "Hello." before anything was typed and answered (sidetone 5); the case that was
      broken, the hub gone first, still untried. To try: close every session, wait for the hub to go
      (`sidetone hub stop` does it at once), open one session and speak to it
      without typing. 2026-11-22, checked by Claude at the author's asking ("can you not check
      this by yourself?"): a hub of its own (`CS_RUN` apart, silent voice, no overlay), none
      running, a new haiku session opened in tmux; its SessionStart started the hub and the
      listener was waiting; words handed to it as a heard follow-up, nothing typed, and it
      answered "Yes, I can hear you." Only the microphone was left out.
- [x] The card's figures as totals of the session (2026-11-20, the author's idea after
      "This reply" and "This turn" were "not very intuitive"): "Total tokens" and "Total time"
      are now what the whole session has used and how long Claude worked in it, since it began or
      was cleared; each turn's own tokens stay on its history line. Seen in a picture only.
      Seen by the author on their own sessions 2026-11-22: "I think they look great."
- [x] A settings window for voices, keys and overlay options (the author's idea). Today these
      are a JSON file and the command line.
      A first one built on the evening of 2026-11-18 and put on their screen:
      `Ctrl+Alt+S` or `sidetone settings`. Sections at the left (Voice, Voices,
      Talking, Overlay, Figures, Terminal, Keys), 54 settings, each changed with a
      click and in effect at once; hotkeys are changed by clicking one and pressing the
      new keys. **For the author to judge, none of it agreed beforehand:** the look,
      the wording, which settings are in it, and the key that opens it. **To try by
      hand** (checked from WSL only with pictures and with clicks made inside the
      program): a choice, a switch, a slider, the list of voices, typing a new hotkey
      and getting the old one back, moving the window by its head, Esc.
      Not in it yet: languages, the colors, where the overlay sits and on which
      monitor, which figures a row and the card show, your own voices, voices of
      projects that are not open, a way back to what a new install has, a search.
      Their first look: it must be an ordinary window that can go behind others and be
      put away, the menu at the left on a ground of its own, and the tool's name not
      beside the heading. All three done the same hour and seen by them ("that's
      better"); putting it away and bringing it back from the taskbar: "It works
      perfectly". Still untried by hand: a slider, the list of voices, typing a new
      hotkey.
      On 2026-11-19 the author put it last of the things to try: "the settings are the
      last things to try because there are so many".
      2026-11-20: going through it one section at a time. **Voice is done** (renamed Mute,
      keys named in descriptions, title case, summary language as a dropdown of Match My
      Language, English, Italian, Chinese, Say the Session Name as Always or Never, one
      Volume 0 to 100, progress, the repeat choice and the feedback choice removed, most used
      first). **Next: Talking**, then Overlay, Figures, Terminal, Keys, Voices (the author
      stopped for the night: "We can continue tomorrow").
      2026-11-21: Voices taken first. The author: "Voice" and "Voices" too alike, only the
      open sessions, no label, no preview, narrow in the middle, and a voice per language.
      Agreed and built: Voice renamed **Speech**; the page as wide as the others; English,
      Italian and Chinese, each a card of its voices with readable names ("Heart, American
      woman, quality A"), a ▶ and a tick; sessions take the ticked voices in their order
      (dragged by the dots at the left); unticked ones folded under "More Voices". English
      down to the eight clearest by Kokoro's grades, Piper's voices marked faster. A part
      with each open session's voice came out the same morning ("what is the point of it").
      Later the same night, agreed with the author: each language a row that opens and
      closes (all closed at first, "8 voices" beside it), one sentence for the page that says
      the purpose first, at most twelve voices a language, Chinese ordered by measured clarity
      (the author's four ticked, the eight clearest under More Voices), Piper's voices marked
      faster, "quality A" instead of "grade A", a ▶ pressed again starts over, and a stop
      square while a preview plays. 2026-11-21 noon: the count reads "4 selected" (agreed after "4 of 12 ticked" was "not very conventional") every voice described alike ("American woman, Excellent", "Chinese woman, Good", "Italian woman, Okay, faster"), and an unticked voice stays in place until its language is closed (built, not tried). Speech now plays with a 300 ms buffer and silence around
      it (scratches through AirPods; "still a bit" at 150 ms, and Fenrir and Michael scratched
      while the processor was loaded by the Chinese ranking). **For the author to try**: the
      stop square, dragging, ticking, More Voices, and whether Fenrir and Michael still
      scratch now that nothing else loads the processor. Noon: the scratches left
      were the loudness meter taking the speakers' buffer to 30 ms (measured); it now asks for
      the voice's. Previews heard by the author: "It's perfect". Still to see: whether the wave
      beside a speaking session moves smoothly. Piper's "Faster" became the seconds each voice takes
      to make a sentence, timed on each computer by itself, with an i that explains it (seen
      in a picture only). Each language has a switch for whether you speak it, the same as
      the languages push-to-talk listens for (seen in a picture only). A project keeps its voice
      when the order changes, in every language (Italian and Chinese were dealt out again; the
      author, after swapping Heart and Bella: keep it simple); the order is for new projects. The voices best first, on a new
      install and in the author's own lists ("set my voices ... first the best one"): English
      by Kokoro's grade (the women first, as they are graded higher), Italian Sara, Nicola,
      then Paola, Chinese the four clearest measured instead of the four picked by ear. Tried by
      the author by hand the same afternoon: dragging, unticking and ticking again, the language
      switches (Italian off, then Italian spoken came out as English, as it should), the gap
      under an open language ("That's perfect"). **Voices is done**; still to notice: the wave
      beside a speaking session after the meter change. **Talking, started 2026-11-21:**
      Confirm Before Sending is a switch ("Acting alone" taken out); Time to Cancel Before
      Sending out of the window; Time to Take Words Back out too, waiting words can always be
      taken back; The Cancel Key Stops a Session became the switch Cancel Key Interrupts Claude ("like Ctrl+C"); the repeat key
      pressed again starts over. Words spoken to a busy session are read after its next step
      ("A Busy Session Hears You"), tested with the real hook and a haiku session, **not yet
      tried by the author**. Side Questions became a switch ("Always" taken out). A spoken
      yes or no answers a permission prompt, longer words explain (the setting left the window;
      **not yet tried by the author**). Usage by Voice left the window in another session. A
      clear key, Ctrl+Alt+C pressed twice: asks in a banner like the mute key's, "Clear sidetone?",
      with a bin (seen by the author: "I think it looks good");
      a clear has its own sound, no "sent" sign, and the arc winds back to 0 (**the sound and the
      arc not yet heard and seen by the author**). Typing Takes the Focus out of the
      window (always on), Short Words in Your Last Language too, and Mute Discord While Talking
      (always on; binding the talk key itself in Discord does not work). The README's list of
      what it does still names settings that left the window (`unsend_seconds`, `followup_delay`):
      for the documentation step. Listen On After Release kept, renamed Release Delay (Discord's
      word). The page ordered most important first, names and descriptions polished (seen in a
      picture). **Talking is done.** **Overlay, under way 2026-11-21:**
      Layout and Details name their keys (Details: Always, On Hover); Details Changing Size, Move
      It by the Details, What Opens the Details and the four signs of a muted voice out of the
      window; Opacity at Rest out of the window, its default now 100% (seen at 50%: "standard is
      100%"). Glass is a slider, 0 % plain to 100 % clearest, 50 % the look it had (**not yet
      judged by the author**). Lines Per Session at 3 moves the lights as a sentence grows; every
      row kept as tall as three lines was tried and not liked ("I don't like it"), and reverted.
      Then, the same night, the newest line in full in the card, and a Details choice Selected
      Only (the card and the chosen session's row alone): built, tried by the author, and taken
      back at their word ("let's reverse it as it was before"). Lines Per Session stays, 1 to 3.
      A long sentence floating over the rows below, as a card, was tried too and not liked.
      Then built (2026-11-22): the details key as a zoom of three views, Bar Only, All Sessions
      (one line each), Selected Session (the card and that session alone, its sentence in full);
      Details offers the same three, Lines Per Session left the window (seen in a picture; **not
      yet tried by the author**). In Selected Session the mouse over the card no longer
      picks the first session, and the history is in the card by default (History in Selected
      Session: Always or When the Mouse Rests; **not yet tried by the author**). History Shows: This Session or All Sessions. "Release to
      Send" and Messages That Wait out of the window (Glint, Number). **Overlay is done**
      (Layout, Details, Glass Effect, History Shows). **Figures, under way 2026-11-22:** Usage Labels
      and Context out of the window (the arc is the default); Tokens of a Reply and Tokens in the
      History out too, tokens always shown ("who doesn't want to see tokens?"). Time in the
      History moved to the left end of each line, the tokens alone at the right ("having both
      time and tokens on the right ... it's not very aesthetic"; seen in a picture, turned on for
      the author). With the time shown it takes the place of the mark, always green, to tell the lines
      apart ("replacing the tick icons with the time"; the mark's own colors were tried and
      not kept: "nobody knows what the colors are"); the time column one width whatever it
      holds, "now" or "14m", and times past an hour as "2h", past a day as "3d" ("I want it to
      be ... consistent"); a little more room between the history's lines, 4 px above and below
      each instead of 2, so a sentence's two lines stay apart from the next one ("very dense";
      one line each was tried and not kept: "I still prefer two lines"); the panel and the bubble
      380 px wide instead of 340 (tried live: "I think it's good"); without it the marks stay (seen in a picture, **not yet seen live**). Time in the History
      stays off on a new install (the author). Mark Lines Not Heard, Figures Drawn As (tiles stay) and
      Bars Under the Figures out of the window, then Usage Bars and A Model's Own Week; the two
      left (Time in the History, Plan Usage) moved to the end of Overlay and the Figures page
      gone (the author: "moving them into overlays instead?"). **Figures is done.** **Terminal, under way 2026-11-22:** Tint Strength in percent, 0 to 100
      (100 % is 0.3 of the color, the old top; "a percentage from 0 to 100"; seen in a picture),
      in steps of 5, the default 30 % (0.09; 27 % was "such a weird number").
      The flash when the focus moves stays its own switch, apart from Tint (the author saw it
      flash with Tint off). Focus Follows the Terminal tried by the author ("I checked it. I like
      it"). Terminal Follows the Focus explained (with terminals side by side it only moves the
      keyboard; "I see"), kept. Name in the Terminal's Title tried and taken out of the window (off). Renamed: Terminal
      Color, Color Strength, Clicking a Terminal Selects It, Switching Moves the Keyboard ("yeah,
      go on"). **Keys, under way 2026-11-22:** Share Keys Other Programs Have out of the window
      (on), and Go to the Terminal (no key; Switching Moves the Keyboard does it). The other keys
      checked by the author ("I checked every combination, that looked good"). **Keys is done:
      every page has been gone through.** **Terminal is done.**
      Built on the way: the Reset button under each section (a second click within 4 s
      confirms; none for Voices), the window resized from its edges and maximized by a button
      or a double click on its top, a dropdown that closes on a second click. Checked by Claude
      with the real mouse on a test overlay, at the author's asking ("this one is a task you can
      do by yourself"), 2026-11-22: 22 checks pass after two mends (a double click to restore
      left the window at the top of the screen; a quick tap on an open dropdown opened it again).
- [x] Discord muted while you talk (asked for and built 2026-11-20, `push_to_mute`, on, in the
      settings window under Talking as "Mute Discord While Talking"). While the talk key is
      held, Sidetone holds F24 down; Discord's Push to Mute bound to F24 mutes you. Muting
      Discord's stream in Windows was tried first and did not work (the ring stayed green).
      Tried by the author 2026-11-21 in Discord: the ring stayed dark ("It's perfect, I
      think"). The first recording of the keybind came out as Ctrl + F24, because a key was
      held while Discord recorded; with hands off the keyboard it took F24 alone.
- [x] "Release to send" staying on the light (the author, 2026-11-18: "it got stuck in
      recording wtf"). Found and mended the same hour: a press of the talk key shorter
      than a third of a second left the sign up until the next hold, though nothing was
      being recorded. **Not known whether that is what they saw**; the log had no line for
      it (it has one for a short press now). Asked, they said: "I don't know. I wasn't
      paying attention." So it stays open until it happens again; then `hub.log` will
      show a short press if that was it. If it was a real hold that would not end, the
      place to look is the overlay's keyboard hook losing the release (see `docs/dev/features.md`).
      The author, 2026-11-20, of this and the item on the bubble jumping (heard as "We already
      0.2 and 3 from the muscle before": [did] 2 and 3 from the [list] before). The log
      since has no short press and no words handed over late.
- [x] The bubble no longer jumps to another session when words that waited are handed to
      it while someone is speaking (2026-11-19): only a paper plane on that light. Seen in
      a picture; whether that was the jump the author saw is read from the log.
      The author, 2026-11-20, of this and the item on the bubble jumping (heard as "We already
      0.2 and 3 from the muscle before": [did] 2 and 3 from the [list] before). The log
      since has no short press and no words handed over late.
- [x] "Clear the chat" by voice (asked for and built 2026-11-19). First, once: in VS Code,
      Ctrl+Shift+P, "Restart Extension Host", so that the extension 0.4.0 runs. Then hold
      the talk key and say "clear the chat" to a session that is idle: its terminal should
      show `/clear` and an empty conversation. Said to a session that is working, its light
      should show the struck-out microphone and "Not cleared: it is still working".
      The author cleared one the same night. Asked for then and built: once the chat is
      really cleared, the "sent" notes (or "Chat cleared." with spoken feedback), and
      nothing before; nothing within 10 s gives "Not cleared" and the low notes.
      Tried 2026-11-20: "It seemed to have cleared the [chat]"; it then went to the bottom of
      the bar, mended the same hour (a cleared session keeps its place, name, color and
      voice; tests only). The first try was heard as "I'll clear this hat." and went to
      the session as a prompt.
      Open:
      - does the speech model write the order cleanly enough (it has to be the whole of
        what was said); other phrases go in `clear_words`, Italian ones too
      - an order to a busy session waits for the end of its turn (built the same night,
        tests only); words said to it afterwards, or a typed prompt, drop the clear
        without a sound, which may be surprising
      - one Ctrl+C is typed first, to empty a half-typed line; if you pressed Ctrl+C
        yourself in that terminal a second before, the two together close the session
      - VS Code only
      After the mend, cleared twice more the same night, once heard as "clear the shot" and
      still taken as the order; the session kept its place: "It seems to have worked well."
- [x] Your own words' sign hidden by another session's line (2026-11-19, the author: "I
      just send an audio to session three and I immediately switch to session one, try
      sending an audio, and I don't see the icon for sending the audio. I don't see the
      status update"). In pictures of the same steps: with the details kept out the rows
      show it ("Release to send", then the words and the paper plane); with only the bar,
      session three's reply takes the bubble and session one's paper plane is only on its
      light. That is the choice made earlier the same day (`overlay.sent_first`, off, after
      "you started speaking without like the window popping out"). To ask which they were
      in and which they want.
      Tried 2026-11-20 (words sent to one session, then at once to another): "It seems to
      have worked all [right]." So `overlay.sent_first` stays off.
- [x] A session that starts to speak right after you sent words to another one gets the
      bubble at once (2026-11-19, the author: "you started speaking without like the
      window popping out"); the "sent" sign stays on the other light. To try: talk to one
      session while another has a line ready. `overlay.sent_first: true` is how it was.
      Tried with the item above on 2026-11-20: "It seems to have worked all [right]."
- [x] The history following the mouse from row to row without lag (2026-11-19, the
      author: "if I move it real fast, there's a latency"): the open panel changed height
      in about 60 ms instead of half a second: "That's better ... more responsive". Now it
      takes the new height at once: "super responsive". Then, on their yes, `overlay.resize`
      quick (grows at once, shrinks in about 90 ms; the default) or instant. Quick not
      tried by them.
      Tried with quick on 2026-11-20: "It's pretty responsive, I like it."
- [x] Moving the overlay by its details (2026-11-19, the author: "if it's fully displayed
      with Ctrl+Alt+L, I should be able to move the entire overlay"). Built the same day
      (`overlay.panel_drag`, on): with the details kept out, drag them and the whole
      overlay goes, the panel along with the bar; a click still reaches what is behind.
      A press could leave the drag begun and every press after it ignored ("I cannot
      move the layout right now"); mended the same hour. Then: "That works, perfect."
- [x] The mute key, `Ctrl+Alt+M` (asked for and built 2026-11-19: "I would rather have ... a
      mute shortcut"). Press it while a session speaks: the line stops, two low notes go
      down, and the overlay shows "Voice is muted" with a struck-out speaker for 2.5 s. While
      muted, what sessions say is shown instead. Press again: two low notes go up, "Voice
      on". The same as `sidetone off` and `on`; rebind it in the settings window, Keys.
      The author pressed it the same day: "It works." They asked for M ("M for mute"); it
      was moved there while the NVIDIA overlay was closed, and that overlay came back by
      itself and took the key again ("It's not working"), so it is Q again.
      Their rule for default keys, the same day, on learning that M is the NVIDIA overlay's
      default microphone key: the tool is meant to reach as many people as possible, so a
      default must not clash with a popular program's own keys ("there's no point in
      overriding them"), even where they themselves do not use that program. Q stays.
      For themselves they wanted M anyway, acting in both programs ("it execute both"):
      built at once as `share_taken_keys` (on), a key another program holds is heard through
      the keyboard hook and passed on. Minutes later M became the default for everyone ("if
      there's conflict just do both"), which sets their rule above aside for this key: with
      the NVIDIA overlay, M also switches its microphone. Pressed by them on 2026-11-19
      at 14:45 with the NVIDIA overlay holding the key: off, a spoken message while muted
      got through, on again 25 s later (`hub.log`). Not said: how it looked or sounded.
      While muted: first a small struck-out speaker past the end of the bar, which they did
      not like ("I don't like the icon underneath the sessions"; `muted_mark`, now off);
      now "Voice is muted" in the details (`muted_line`), their idea, and a struck-out speaker
      in the card's top right corner (`muted_icon`), their next one; whether both should stay
      is to be asked. The repeat key no longer speaks while muted (they found it did).
      **Not seen by them yet.**
      Open: mute is for every session, not only the one in focus.
      Seen by them at 15:52: two looks one after the other when muting, "Voice on" out of
      line, and "a reverb, something scratching" after the sounds. The looks made one row
      the same day (see `docs/dev/features.md`). The scratch is not in what Linux plays:
      the two notes recorded from the speakers' output fade cleanly to silence. The likely
      cause is the NVIDIA overlay, which also acts on Ctrl+Alt+M (switching its microphone)
      and may play its own sound; to be heard with our sounds alone.
      Heard alone, they still scratched ("Boodum ... hmm"): it is ours, added on the way
      to Windows as the stream closes. Mended the same hour with silence around each sound
      (`sounds.LEAD`, `TAIL`) and a 150 ms buffer; heard by them: "the last two were
      clean", then a brief scratch on the first after a quiet spell, then with the 0.1 s
      before, twice after 8 s of quiet: "they were clean".
      Then the key itself at 16:02 with the one row and the new sounds: "Oh, that's
      perfect."
- [x] Italian openings for side questions and for asking the usage. `aside_words` and the
      words `usage.asks` accepts are English only, so "a proposito, ..." waits for the session
      and "quanto ho usato?" goes to it. Add Italian (and Chinese, now that it is spoken)
      defaults, and the small words passed over before them (`base.ASIDE_LEAD`).
      Built 2026-11-19 with the author's own words ("comunque", "e comunque che ore
      sono?", "quanto stai consumando? quant'è il contesto al momento?"), and the session's
      context can now be asked in English and Italian too; answers in the language asked
      (see `docs/dev/features.md`). Risk to watch: "comunque, procedi" said to a working
      session becomes a side question.
      The side question tried by the author at 15:32 while the session ran the tests:
      "e comunque, che ore sono?" was written "Comunque ci sono." (heard as Italian), went
      on the side at once, and Paola answered in 3.8 s: "Ho capito solo 'ci sono', ma se
      volevi sapere l'ora, adesso sono le tre e trentadue del pomeriggio". The session never
      got the words. The usage in Italian tried at 15:41: "Quanto sto usando?" (5.2 s) and
      "Quanto usato?" (2.2 s), both heard as Italian, both answered by the hub in Italian
      ("Hai usato il 1 percento delle cinque ore, si azzera alle 20:40 ..."). The context
      at 15:49: "Allora, quanta del contesto?" (3.8 s, written in 2.4 s since the last
      language was English and it was checked against it), answered at once by Paola: "Il
      contesto è al 26 percento." The author: "Perfect."
- [x] Confirmation before a spoken message is sent, as a setting in the settings window
      ("un'opzione nei settings per la gente che vuole la conferma": see the transcript,
      then send). It exists in the hub already, off by default since the author found it
      "too many clicks": `followup_confirm` (false, true, or "auto" for sessions that act
      without asking) and `followup_delay` (seconds the transcript is shown and can be
      cancelled before it goes). Neither is in `settings.SECTIONS`; add both to "Talking",
      and check how the confirming tap and the delay look on the overlay today.
      Built 2026-11-19 on their "proceed": both under Talking, seen in the window's
      picture and clicked there by `tests/overlay_check.py`. Tried by them the same
      minute: set to Always, spoke, tapped to send (sent 7 s after it was written), set
      back to Never: "I tried it. Looks good."
- [x] Sessions in an order of your own (the author's idea, 2026-11-17): hold `Ctrl+Alt`,
      take a light with the mouse and drop it where it should sit in the bar. The hub keeps
      the order (by project, so it survives restarts) and new sessions join at the end. Fits
      the dragging the bar already has: with the keys held a drag moves one light, without
      them the whole bar.
      Built 2026-11-19 (see `docs/dev/features.md`): `drag_keys` is `""` again, so a plain
      drag moves the bar, and with `Ctrl+Alt` held a press on a light lifts it and it
      can be dropped elsewhere; the order is kept in `sessions.json`. Tried by the
      author the same night and mended four times; the last fix (the panel no longer
      folds away while a light is held) tried by the author on 2026-11-19 with two sessions:
      "it's done and working" (`hub.log`: "sessions put in a new order" at 14:48).
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

### Decided

- [x] Short Italian answers heard as English: "procedi" and "sì" came out as "See you
      soon" and "See you" with `whisper_language: "en,it"` (2026-11-19), since a word or two is
      too short to tell the language and English wins. Perhaps lean to the language of the
      session's last line, or of the user's last longer recording.
      Again 2026-11-19 14:53 with `en,it,zh`: a 2.4 s clip came back as Chinese, "是很多的"
      ("it's a lot"), and took 2.9 s to write where 0.8 s is usual; what was said is not known.
      Again 15:04: a 1.9 s clip (peak 1.00) came back as "对了" ("right") in 1.7 s, after a
      question that wanted a yes; perhaps "do it" or "did it", not known.
      Again 15:24, the other way: a 2.6 s clip, surely "quant'è il contesto al momento?"
      just after the Italian context question was built, came back as English "How much
      did you count this moment?", so the hub did not answer it and the session got it.
      Again 15:34: 2.3 s, surely "quanto ho usato?", came back as English "One dosa,
      what the?" and took 2.7 s. Four short clips out of four in the wrong language today.
      Built the same day on their word (`whisper_lean`, see `docs/dev/features.md`): an
      unsure short clip keeps to the language last heard for sure. Fixes Italian after
      Italian on the test clips; a switch to a short, unsure Italian clip right after
      English can still go wrong. **Not tried by them yet.**
      Measured again 2026-11-22 with `large-v3-turbo` on the card (`docs/dev/facts.md`): most
      short Italian now right after Italian; a lone "Sì." still often "See you". A rule that
      turns "See you" from a very short clip back into "Sì" was offered and left out (the
      author: "I don't think it's good"; Claude agreed: a patch for one word). Claude is told a
      word may be off, and "sì, vai" comes through.
- [x] The full transcript and the full message in the overlay (the author, by voice,
      2026-11-19: "I want to be able to see the full transcript and the full message in the
      overlay"). Today the bubble and the rows cut long text (`overlay.row_lines`, 1 to 3
      lines). To ask: whether "the full message" is the whole spoken line or the session's
      whole written reply, and "the full transcript" all of their own words as heard; and
      where (the bubble growing, a click or key that opens it, the history).
      Not needed any more (the author, 2026-11-22: "Having the layout of selected session
      already displays the full transcript and also the answer. So it's not needed anymore").
- [x] A setting that keeps every key from other programs while `Ctrl+Alt` is held (the
      author's idea, 2026-11-17, after Space paused a video during push-to-talk). Built so
      far: only the held talk key is kept back. Off by default if built, because it would
      also take other programs' `Ctrl+Alt` shortcuts and the characters some keyboards type
      with those keys, and it needs a keyboard hook for as long as the keys are down.
      Not wanted (the author, 2026-11-22: "I mean [it] is fine [as] it is"); the video
      pausing it came from was mended on 2026-11-17 and is not back.
- [x] Push-to-talk goes to the session in focus when the key comes up, not when it went down
      (asked 2026-11-22: "should the audio be sent to the initial target session or the final
      ... What's more convenient [or] conventional?"). Claude advised keeping it: scrolling
      while talking is a deliberate change of addressee, as a chat sends to the one open at
      send time; another session speaking cannot take the focus meanwhile. The author: "Alright".
- [x] More for the VS Code extension, now that it exists: color the tab itself in the
      session's color. (Bringing the terminal of the session in focus to the front is
      done, see the jump key above; the hub can ask the extension since 0.2.0.)
      Skipped (the author, 2026-11-22: "Then we can skip this one"). Found first: an
      extension can give a terminal's tab a color only when it creates the terminal
      (`TerminalOptions.color`, any theme color, so the exact palette through
      `contributes.colors`); VS Code's change-color commands for an open terminal always show
      a picker, and the API has no setter. So only terminals opened with the new-session key
      could have had it; the background tint already marks every terminal.
- [x] The session colors stay twenty (2026-11-22). Shown all of them with how they were picked,
      and the convention (8 to 10 categorical colors, then reuse with the name as the cue),
      the author: "I don't mind them"; asked whether to keep twenty or reuse the first eight,
      Claude advised twenty (a repeated color would make two sessions look alike in the
      overlay and their terminals), and they agreed: "yeah sure you can proceed".
- [x] Short sounds for states (done, needs you) for when a full sentence is too much. Push-to-talk
      has them since 2026-11-17 (`hub/sounds.py`: sent, waiting, not sent); the author, on
      hearing them played with their names said first (2026-11-22): "they do [sound right],
      but I don't like them [the names]. I prefer the short sounds". "Allowed." and "Denied."
      are still spoken.
      Sounds in place of "I need your input", "Allowed." and "Denied.": not wanted (the
      author, 2026-11-22, asked: "Uh, no"). Those stay spoken.
- [x] A light mode for the overlay (offered 2026-11-22 after the terminal's light tint): not
      wanted (the author: "No, I don't think it's [needed] either"). The overlay keeps its
      dark glass on any theme.
- [x] A bell on a terminal's tab when its session speaks (VS Code's visual bell): not wanted
      (the author, 2026-11-22: "I don't think it's too useful so I will skip this one as well").
- [x] Left or right ear per session: not wanted (the author, 2026-11-22, offered it as the
      next small extra: "I don't like it. Let's just skip it").
- [x] No mouse buttons as keys in Sidetone itself (the author, 2026-11-22: "I don't think we
      should do anything on our part ... they can just do it with their own program"). A
      mouse's own program (Logitech Options+, G HUB) can send the talk key; for the
      documentation step: say so there, with an F key nobody has (F13) as the tidiest choice.
- [x] Session names in the terminal tabs: turned on 2026-11-20 at the author's yes, and
      turned back off the same hour ("I don't like them this much. I would prefer [Claude's
      own] session [title] ... I think you should revert this"). `terminal.title` stays a
      setting, off; the README says how to turn it on.
- [x] `Ctrl+Alt+U` (what did I miss): removed on 2026-11-20 at the author's word ("You can
      remove it. I will use the replay anyway"), with `sidetone missed` and the catch-up code.
      It replayed every line since the last prompt or hotkey, so it mostly said "Nothing new".
      The version that counts only lines said while you were away stays on the branch
      `away-catch-up` (commit `07c9ff9`). The white dot on lines not heard
      (`history_missed`) stays.
- [x] Another name for the tool (the author, 2026-11-18, on seeing "claude-speaks" in the
      settings window: "I don't like [it] as a name. Maybe we can think about it ...
      Maybe there's a better name"). Open. A new name would touch the repo, the commands
      (`claude-speaks`, `cs`), the folders under `~/.local` and `~/.config`, the VS Code
      extension and the README; and "Claude" in a product's name is Anthropic's mark,
      which is a reason of its own to look for one before the repo is public.
      Asked the same evening with three names that a search had not found on a tool
      for coding agents (Sidetone, Squelch, Tally; Earshot, Switchboard, Hark and
      Heard are taken) and "keep it for now", they answered by voice: "Sidetone is
      cool, but why?" The why was explained; **no name chosen, nothing renamed**. The
      speech model wrote the word as "Saiton". The window shows `settings.NAME`.
      Chosen minutes later: Sidetone. Done that evening, as they asked: the name in the
      window and the README, the GitHub repo (`sidetone`), the project folder
      (`~/personal/sidetone`, with a link left at the old place for the sessions and
      the editor window that were open). The commands followed on their yes: `sidetone` and `st`. The
      logo is in the blue they typed, `#006896`. The sessions that were open are named
      `sidetone` in the bar too (changed by hand in the hub's records). **The logo:** chosen after six pages: the disc in
      their blue with uneven voice bars cut on the slant ("S6 is good"). Before it, a
      disc with plain uneven bars, liked best and found "pretty anonymous". Some
      thirty others were drawn over five pages (waves, a speech bubble, the bar of
      lights, faces, a ghost, headsets and microphones after their own idea) and none
      was liked. What got there: their own direction, to look at the logos of the five
      most valuable startups and take one idea from each. The microphone in the overlay is their blue too, on
      their word, though it is near the blue of "working" (`overlay.mic_color`);
      seen by them while talking ("looks good. Let's see"); to be watched in use for
      the two being mixed up. **Left, for them to decide:** the
      folders for settings, logs and models, the
      `SIDETONE_*` variables, the VS Code extension's name, the words in the
      overlay ("claude-speaks" is nowhere on screen now), and `CLAUDE.md` and this
      file, which still say claude-speaks throughout. And to do once no session is
      left from before: remove the link `~/personal/claude-speaks`, and open the
      editor on the new folder.
      Done 2026-11-19 on their word: the link and the old commands removed, the
      folders and variables renamed, then the VS Code extension and every other
      mention (see `docs/dev/name-and-logo.md`).
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
      `sidetone languages en,it` changes it later, also in a running hub. English
      alone keeps the English-only model; other languages get the multilingual one,
      told which to expect. Not tried by a person: the question in the install script
      (answered by a script in a throwaway home folder), and no language other than
      English and Italian has been spoken to it.
- [x] Should a quick tap of the talk key also stop at the last session, like the wheel?
      Settled another way on 2026-11-17: the tap no longer moves the focus at all; the
      arrow keys do, and they stop at the ends.

### Rough edges mended

- [x] Space still paused YouTube while talking (the author, 2026-11-22: "whenever I watch
      YouTube it pauses the video when I talk ... make it a setting"). The cause: the hook that
      hides the talk key went in only once Ctrl and Alt were both down, so a Space within
      30 ms of the last of them came through as a plain hotkey and its release reached the
      browser. Now it goes in at the first of them, and "Hide the Talk Key" in the window can
      be Always. **Not tried by the author yet**: talk over a playing video, quickly.
      A misreading: the author meant the trouble of 2026-11-17 and has none now ("right now I
      don't have any issues with YouTube"). The window entry was taken out again; the hook
      going in at the first modifier stays, since it only narrows a gap that was known.
- [x] A short bug hunt before the speech work (the author, 2026-11-22, asked when bug hunting is
      best: a short one now on what they have not tried, a full one before release; "Yeah").
      In a key lab: a hub of its own run inside a script with its own overlay and no hotkeys,
      keys handed to it as the overlay hands them (no key pressed on the real keyboard), haiku
      sessions in tmux, a stand-in for the VS Code extension typing into the panes. Fine: clear,
      end and new session in every order; clear next to mute, cancel, repeat, the details key,
      settings and focus; clear on a session at a permission prompt or with a /model picker open
      (waits for the turn's end, nothing approved); end on an idle and on a working session (row
      and pane gone, focus to another); a spoken yes, no and longer words at a permission prompt;
      the three detail views (pictures from the lab overlay's own windows). Fixed: the clear typed
      into Claude Code's auto mode nudge ran /auto-mode-setup (the extension 0.5.1 types Escape
      first; **VS Code needs Restart Extension Host once**); no context arc after a first turn,
      and one reply behind after a turn of one reply (counted again 1.5 s after the Stop). As
      built, to know: the cancel key leaves the clear question up, so a second clear still clears.
- [x] A bug pass, 2026-11-21 (an agent read the code, then the author chose what to do with what
      it found). A sentence Kokoro cannot say no longer ends all speech; a `config.json` that is
      not JSON is no longer written over, and gives the defaults at start; a value of the wrong
      kind gives its default; a voice that fails to load gives way to a system voice;
      one error no longer ends the overlay's update loop or its message reader; `install.sh`
      no longer doubles hooks written as `$HOME/...` and takes a path with `&` or `|`; `parec`
      is waited for when push-to-talk stops; `sidetone say -v` and `follow-up -s` with nothing
      after them print the usage. Not yet heard or seen by the author in use.
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
      (Seen on the evening of 2026-11-18 in its last form, the number coming up in its
      corner: they spoke three times to a session kept busy, all three waited and
      arrived at its end, and the third was "Looks good".)
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
      them, and the other way is there for whoever wants it: `sidetone overlay hover
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
      Say in `sidetone status` when the running hub is older than the code on disk.
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
- [x] Seen in those pictures, not mended: a choice that wraps goes on under its box, not
      under its first word; with the clock mark, "9+" is hardly readable;
      the blur and acrylic glass look the same; a tick question's line about the keys
      wraps when "1 more waiting" is added.
      Mended 2026-11-18 while the author was away ("list me ... the next things to do
      ... and you'll do it"), seen in pictures only: a choice is a row of its own, so
      its second line starts under its first word (numbers, tick boxes and caps alike);
      "1 more waiting" always has a line of its own under the keys, for a permission
      prompt too, where it used to fit at the end; with the clock mark, ten or more
      messages show the face, or "9+" in a disc with room for it. Not mended, because
      there is nothing to mend on our side: blur and acrylic are the same picture on
      this Windows (two pictures over the test card differ by one step of 255 at most,
      outside the spinner). Both names are kept in case an older Windows tells them
      apart, which nobody has checked. **Not seen by the author on a real question.**
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

### Built

- [x] The terminal tint on a light theme (2026-11-22): the VS Code extension 0.6.0 says
      whether its window's theme is light or dark, and light ones are tinted from
      `terminal.light_background` (#F8F8F8). The author uses a dark theme; checked with the real
      extension and a stand-in editor, not on a real light theme.
- [x] Usage in the overlay (the author's idea, 2026-11-17: "customizable bar that shows the
      usage, the five-hour window and the weekly usage"): a part of the overlay that shows how
      much of the plan is used up, in the five-hour window and in the week, and when each
      starts again. A setting like the rest: on or off, where it sits, what it shows.
      Built 2026-11-18 as two thin bars with their percent at the foot of the card of
      figures, read again every five minutes (`usage_shown`, `usage_every`,
      `usage_warn`). Not shown: when each window starts again, and the week of one
      model. **For the author to judge on screen.**
- [x] Context window per session (same day: "for each session maybe something that indicates
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
      it looks as it does is in `docs/dev/features.md`. The author on the card: "it's not bad",
      then, once the room around it was the same on every side: "Oh, it's perfect."
      Ideas
      from that look, not built: the plan's usage ("5h 41%, week 40%") as a thin line
      at the foot of the card, which would settle "Usage in the overlay" below; a mark
      for the kind of agent; the row dropping its time. If the card is not liked,
      the other two: a small column of two figures at the right of every row, or a
      third line in the row under the mouse (which stretches the bar).
- [x] The history, reworked on the author's "do all of them" (2026-11-18): in the
      session's card, a mark per line for how the turn ended, time and tokens at the
      right, the newest brightest, a white dot on lines never heard to the end. **For
      them to judge on screen** (keep the details out with `Ctrl+Alt+L` and rest the
      mouse on a session). Since then, on their word: no time on the lines (tokens
      only), the two columns lined up, the missed dot on the mark, the plan's usage at
      the foot of the card, and key caps in requests. Offered and open: showing the
      history on plain hover too, a red step for context near full, hiding a turn's
      half-way word once its last line is there. Bars that glide: built on their
      spoken answer to a question (heard as "barstack live"); the motion is unseen.
      Judged by the author that evening: history lines "good", usage bars "good", the
      arc around the light "pretty good. It's very intuitive". One fault: the history
      came "a bit later" than the details; it waited two thirds of a second, now a
      tenth (`overlay.history_after`). **The quicker history is not seen by them yet.**
      They asked for more design ideas for the usage bars ("show me"). Built and put
      on their overlay: the week of one model as a third bar ("Fable 89%", which was
      the window nearest its end and not on screen), each of the three on a line of its
      own (`usage_models`). Their answer: "it looks good", but they do not need
      it, since a limit for one model may not stay; it is off by default now. The
      quicker history they did not speak of. Said as further ideas, not built:
      when each window starts again; a tick on each bar for how much of its time has
      passed, to see whether you are ahead of an even pace. The offers above are
      still open. They then asked which is better for the two bars, one line or a
      line each; told a line each, and shown it live (`overlay.usage_layout`: `rows`,
      or `line`). Their choice: "each on their own" row, so it stays. Also said with the command in the middle of that work, so they could
      watch the bubble and wave of such a line: not answered yet.
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
      is at 40 percent, Fable at 76." `sidetone usage` prints it, `usage say`
      speaks it. `hub/usage.py` (by another session) reads it with a headless `/usage`
      call, 0.8 to 1.5 s, no model request. Which sentences count is strict
      (`usage.asks`): "add a usage meter to the overlay" goes to the session. Tried on
      the live hub with words sent as if spoken. The author's first real one,
      2026-11-18, was "Alright, so what's the usage?" and went to the session: no
      sentence opening with "alright" counted. Such openings ("alright", "yeah",
      "sure", "also") are passed over now; **not asked again by their voice yet**. Not built: a key for it, the warning by itself near the limit, Italian.
- [x] A key that stops the session in focus (the author's idea, 2026-11-17: the cancel key
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
- [x] Easier ways to take back what you said (the author, 2026-11-17: "it would be really
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
- [x] Stay quiet for the session whose terminal is in front. Offered on 2026-11-19 and turned
      down: "I don't think I need it ... I would rather have a mute shortcut." Built
      instead: the mute key (see "To try by hand").
- [x] A key that jumps to the terminal of the session in focus
      Built 2026-11-18 while the author was away ("list me ... the next things to do ...
      and you'll do it"; the key and its letter are not agreed with them): `Ctrl+Alt+T`
      (`jump` under `hotkeys`; `""` turns it off), or `sidetone terminal show
      [PROJECT]`. The hub asks the VS Code extension (0.3.0), which shows that terminal
      and puts the keyboard in it. The key is only claimed while an editor with that
      extension holds the terminal of the session in focus. Tested with the real
      extension code against a real hub and a stand-in for the editor. Version 0.3.0 is
      installed, but **VS Code runs 0.2.0 until its extensions are restarted**
      (Ctrl+Shift+P, "Restart Extension Host"); until then the key is not claimed at
      all. **For the author to try** after that: move the focus to another session with
      the arrows, press `Ctrl+Alt+T`, and its terminal should come up ready to type in.
      Asked to try it on the evening of 2026-11-18, the author said "Oh, it works. So
      what is this control... Alt and T?": the log has no press of the key, so "it
      works" was about something else (most likely the usage bars on a line each,
      shown a minute before) and what the key is for had not come across. Explained
      again; **still not pressed**.
      Their decision the same evening: "I think we can just delete this one ... I
      don't think I'll use it." Their terminals are side by side, and the tint
      already shows which one to look at. The key is gone from the defaults (`jump`
      is blank; `sidetone terminal show` and the extension's part stay, for the
      idea below).
- [x] Built 2026-11-19 on the author's word, by voice: "I have two terminals ... they're
      not side by side ... Make it that whenever I scroll between the session and
      automatically set that terminal to focus". `terminal.jump` (off by default, on in
      their config; `sidetone terminal jump on|off`, a switch in the settings window).
      It takes the keyboard, as they asked. Tried by them: "it seems to be working good."
      The terminal comes up by itself when the focus moves (the author's idea,
      2026-11-18, kept on the list on their word, with "I don't think I'm gonna do
      it" soon): for people whose terminals are tabs, one visible at a time, moving
      the focus in the overlay (arrows, wheel) would show that session's terminal in
      VS Code, with no key. A setting, off by default. To build on: the hub can
      already ask the extension to show a terminal. To work out: it must not take the
      keyboard from where you are typing (the extension's `show` can be told to leave
      it), and it should do nothing when the focus moved because a session spoke.
      Open: it works inside VS Code's window only, so with a browser or a game in front
      nothing is seen (the overlay could bring the window forward; not built); whether
      `Ctrl+Alt+T` is free on their machine shows in `hub.log` once the key is claimed.
- [x] Tell the terminals apart (the author, 2026-11-17, with four terminals open in VS Code:
      "I cannot distinguish which", and later "is there a possibility to highlight the
      terminal" of the session selected in the overlay). Built the same day, no extension:
      the terminal of the session in focus takes a faint tint of its overlay color and
      lights up brighter when the focus is moved to it (`hub/terminal.py`, `claude-speaks
      terminal`). The author saw it and said "maybe the flash might be too much", then
      "less tint maybe"; at 0.08 of the color for the tint and 0.15 for the flash (from
      0.14 and 0.42) they said "looks good". Not asked: whether every terminal should
      wear its color all the time (`terminal tint all`).
- [x] The focus follows the terminal you go to (the author's idea, 2026-11-17: "if I focus
      on a terminal it would be great to automatically select that" session). Built the
      same day as a small VS Code extension (`vscode/`, `sidetone vscode install`):
      VS Code tells it which terminal became the active one, it tells the hub that
      terminal's process, and the hub gives the focus to the session running there
      (`terminal follow off` turns it off). Installed on the author's machine and seen
      starting in VS Code's log; the real extension code is tested against a real hub
      with a stand-in for the editor. In use since: by the evening of the same day
      `hub.log` had 79 lines "focus on ...: its terminal came to the front" from the
      author going from terminal to terminal. They have not said in words that it is right.
- [x] Spoken summaries in the language you spoke. Built 2026-11-19 on the author's "yes
      proceed" (`reply_language`, `spoken` by default): the session writes its line in the
      language of your last message with `lang="it"` in the tag, and the hub gives it a voice
      of that language. **To try:** speak or write to a session in Italian and listen.
      Open: the hub's own words are still English; languages without a Kokoro voice
      (German, Russian, ...) are read by the English voice; Japanese and Chinese not heard.
      The author heard Kokoro's Italian (2026-11-19): "non mi piace molto ... non è
      realistica ... sembra troppo robotica". Compared on one sentence (made on the CPU):
      Kokoro Sara 1.0 s and Nicola 1.1 s for about 7 s of speech, Piper `it_IT-paola-medium`
      (from rhasspy/piper-voices, 63 MB) 0.5 s. Their verdict: "Paola di Piper la migliore,
      però non mi fa impazzire". Next, agreed in principle and waiting on their permission:
      Chatterbox Multilingual (`chatterbox-tts` 0.1.7, MIT, `ChatterboxMultilingualTTS`,
      `language_id="it"`), installed in a throwaway venv in a session's scratch folder; it
      needed `setuptools<81` (its watermarker imports `pkg_resources`). Its run, which
      downloads the model from Hugging Face, ran on the author's "proceed": loaded in 6.4 s,
      then 16.8 s and 11.9 s for about 6 s of speech on 16 threads, so twice as slow as
      speech itself; too slow to speak while a reply streams. That was on the CPU: the
      machine has an RTX 5070 (12 GB) that WSL sees, which was missed; Chatterbox on it,
      with a CUDA build of torch: measured the same evening, 2.6 to 2.7 s for about 6 s of
      speech once warm (the first run 23 s), against 12 to 17 s on the CPU. The 5070 needs
      torch 2.7 or newer built for CUDA 12.8; chatterbox-tts 0.1.7 asks for 2.6 and was
      overridden. Pocket TTS (pocket-tts 4.0.1, Kyutai) has Italian models `italian` and
      `italian_24l` with a built-in voice, Giovanni; samples made, speed with the model
      loaded not measured. The trial environments are in `~/.cache/sidetone-voice-trials`
      (outside the repo; `/tmp` is a 7.8 GB tmpfs and filled up). All on the comparison
      page for the author to hear. Their verdict: not Pocket TTS; they keep Paola, Sara and
      Nicola, now shared out between sessions for Italian (`PREFERRED_VOICE` is a list).
      They asked for more ("c'è qualcosa altro?"), and the best English ones on the card
      too. Sampled on the RTX 5070 (time to make one sentence, model loaded):
      azzurra-voice (Cartesia, Italian only, CSM 1B, CC BY-NC-SA: not for a published tool)
      8.7 s for 6.8 s; Qwen3-TTS 1.7B (qwen-tts 0.1.1, no flash-attn) about as long as the
      speech, Italian from a described voice (VoiceDesign) and English speakers Ryan and
      Aiden; Chatterbox English 1.9 s for 4.5 s, Italian 2.6 s for 6 s; Kokoro English
      0.9 s for 5.5 s on the CPU. Loading takes 1.5 to 3 minutes the first time (downloads).
      All on the comparison page, waiting for the author's ears. Only Chatterbox is quick
      enough to speak a sentence at a time while replies stream.
      Their verdict: none of the new Italian ones ("non mi piacciono ... teniamo quelle
      attuali": Paola, Sara, Nicola), and for English Kokoro's Heart is still the best. So
      nothing on the graphics card for voices, for now.
      Chinese (asked the same evening, "anche in cinese?"): it already works in principle
      (`lang="zh"`, Kokoro's 8 Chinese voices through espeak's `cmn`, 0.8 to 0.9 s a
      sentence), but listening knows only `en,it`. Of Kokoro Xiaoxiao and Yunxi and Qwen3's
      Chinese speakers Vivian and Serena, they prefer Qwen3's, "però mi sembrano più lenti":
      6 to 7 s for a sentence of 6 to 7 s on the RTX 5070, and the 0.6B model is no
      quicker (5.7 to 8 s), so the time goes in the step-by-step loop, not the model's
      size. qwen-tts 0.1.1 has no real streaming (`non_streaming_mode=False` only simulates
      streaming input). Using it would mean a second engine in its own GPU environment
      and about one sentence's length of waiting before the first word.
      They chose quality ("preferisco la qualità") and asked for something faster. Qwen3's
      announced streaming (97 ms) is not in the package nor in vLLM yet ("only offline
      inference is supported"). Found and sampled: Kokoro's Chinese model v1.1-zh
      (kokoro-onnx release `model-files-v1.1`: `kokoro-v1.1-zh.onnx`, `voices-v1.1-zh.bin`,
      and `config.json` from hexgrad/Kokoro-82M-v1.1-zh; phonemes from `misaki-fork[zh]`,
      passed with `is_phonemes=True`): 103 voices, 0.5 to 0.7 s for 5 s of speech on the
      CPU. On the Chinese page beside Vivian and Serena for them to compare. Not tried:
      CosyVoice 2 (streaming, about 150 ms by its own account, GPU), MeloTTS.
      Their choice: the four Kokoro v1.1-zh voices ("preferisco questi quattro"). Built in
      the engine (`zh:` voices) and installed on the author's machine on their typed "si"
      (model files, `misaki-fork[zh]` in the hub's environment, `zh` among the listening
      languages); first line 0.4 s with the model loaded at start. Open: `install.sh` does
      none of this yet, nor fetches Paola for Italian. Tried by the author the same evening:
      spoke Chinese, transcribed right, answered in Chinese aloud: "不错，听得到". Added to the comparison page
      for them to hear. They did not like it either: "Paola è quella migliore", keep her
      for now and look for others. Done: Italian lines are said by Paola (`piper:` voices
      in the Kokoro engine, `PREFERRED_VOICE`). Open: `install.sh` should fetch Paola when
      Italian is chosen; every session shares her, so sessions are told apart only by the
      overlay in Italian.
      Searched for others (2026-11-19, blog round-ups, nothing benchmarked for Italian):
      Pocket TTS by Kyutai (100M, said to run on a CPU, Italian listed, clones a voice from
      a short recording; licence and Italian not checked) is the one to sample next;
      Cartesia's azzurra-voice (Italian only, built on a 1B model, likely needs a graphics
      card); Qwen3-TTS (Apache 2.0, GPU preferred); NVIDIA Magpie Multilingual (357M);
      Voxtral TTS (non-commercial). Chatterbox has no Italian voices of its own: its
      variants come from a reference recording. Not built: Piper as
      the engine for Italian lines (the hub already knows Piper as a fallback).
      Seen the same evening: a short Italian answer seems to come out as English. Asked to
      say "procedi" and then "sì", the author's replies were written "See you soon" (twice)
      and "See you." With `whisper_language: "en,it"` a word or two is too short to tell
      the language, and English wins. Not looked into; perhaps lean to the language of
      the session's last line, or of the user's last longer recording.
