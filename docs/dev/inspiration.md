# Inspiration from similar products

Features from other voice tools, coding-agent notch apps and Windows overlays that Sidetone
could borrow. Researched on 2026-11-22 from the products' own sites, docs and changelogs,
plus reviews and Product Hunt pages where nothing better exists. Each line links its source.
Where a source is a third party, or something could not be checked, the line says so.

Things Sidetone already has (push-to-talk, confirm before sending, take back, side questions,
clear by voice, release delay, Discord push to mute, allow and deny keys, answering questions,
usage, history, mute, repeat, glass, bar and island) are left out. Ideas already on `TODO.md`
get one line saying so. Each idea is marked **Fits well**, **Maybe** or **Not for us**.

## Top picks

Ranked by how much they cut attention latency or would delight someone using it.

1. **Lower Other Sound While Sidetone Speaks** (Superwhisper, Wispr Flow, Aqua Voice). The
   author's own setup is a YouTube video playing while sessions talk. Turning the video down
   for the length of a spoken line and while the talk key is held means a summary is heard the
   first time, with no repeat key and no glance at the bubble. Superwhisper offers Keep
   Playing, Pause, Mute, Lower and Muffle
   ([modes](https://superwhisper.com/docs/modes/modes)). Wispr Flow mutes by default on Windows
   ([auto-mute](https://docs.wisprflow.ai/articles/7231650589-auto-mute-music-while-dictating-on-macos-how-audio-detection-works)).
   On Windows the overlay could lower other apps' playback sessions. The Discord attempt that
   failed was on a capture stream; playback streams are what the Volume Mixer itself changes
   ([ISimpleAudioVolume](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nn-audioclient-isimpleaudiovolume)).
   The WSL voice stream (`msrdc`) must be left alone. **Built 2026-11-26** for the spoken
   line (`other_volume`, see `docs/dev/features.md`); not while the talk key is held.
2. **Session-Aware Dictionary** (Wispr Flow Dictionary and Variable Recognition, Aqua Deep
   Context). Give faster-whisper the words this session is likely to hear: session names,
   the project folder, file and function names in its working folder, and words you corrected
   before. faster-whisper takes `hotwords` and `initial_prompt`
   ([transcribe.py](https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/faster_whisper/transcribe.py)).
   A misheard name means another round trip to the session. Aqua matches dictionary terms
   by how they sound ([changelog](https://aquavoice.com/changelog)), and `espeak-ng` is
   already installed.
3. **Hands-Free Lock** (Wispr Flow). Start recording without holding three keys, for a long
   instruction or a hand on the mouse. Wispr starts it with a double tap of the push-to-talk
   key within half a second, or with a separate key, and stops it with one more press
   ([hands-free](https://docs.wisprflow.ai/articles/6391241694-Use-Flow-hands-free)). In
   Sidetone a quick tap already moves the focus, so a key of its own (or the talk key plus a
   second key while held) fits better than a double tap.
4. **Waiting Clock and Reminders** (AgentValley, CodeIsland, Chimlo). A light that needs you
   shows how long it has waited, the oldest comes first, and after a few minutes the voice
   says it again, shorter. AgentValley shows a red badge with the wait time, oldest first
   ([Product Hunt](https://www.producthunt.com/products/agentvalley)). CodeIsland has opt-in
   follow-up reminders for approvals and questions nobody answered
   ([README](https://github.com/wxtsky/CodeIsland)). This deals with a session that waits
   20 minutes on a prompt, the problem Notchcode's maker built his app for
   ([Product Hunt](https://www.producthunt.com/products/notchcode)).
5. **Always Allow, and Hold for Risky Commands** (AgentPeek, CodeIsland, Chimlo, Coder Island,
   ClaudeNotch). A third answer beside Allow and Deny, by key or by saying "always". Claude Code's
   PermissionRequest hook can return `updatedPermissions`, and it hands the hook the
   `permission_suggestions` to send back
   ([hooks docs](https://code.claude.com/docs/en/hooks.md)). ClaudeNotch asks for a
   press-and-hold for `rm -rf`, `sudo` and force-push, and shows them on a card of their own
   ([site](https://rawsun007.github.io/claude-notch/)). The same safeguard would stop a
   quick spoken "yes" from allowing a destructive command.
6. **Copied Text Goes With Your Words** (Superwhisper). Copy an error from the browser, hold
   the talk key, say "fix this", and the session gets the words and the copied text. You
   don't have to switch to the terminal and paste. Superwhisper takes clipboard text copied
   within 3 seconds before or during a recording, and a sign lights up when it does
   ([recording window](https://superwhisper.com/docs/get-started/interface-rec-window)). The
   overlay runs on Windows and can read the clipboard. Show a small sign on the light when it
   is attached.
7. **Resend or Retry the Last Words** (Wispr Flow, Aqua Voice). Keep the last recording. One
   key sends the same words to the session in focus, for words that went to the wrong one.
   Another runs the recording again through a bigger model or in another language. Wispr has
   Paste Last Transcript, an Undo after a cancel, and retry from history
   ([shortcuts](https://docs.wisprflow.ai/articles/2612050838-supported-unsupported-keyboard-hotkey-shortcuts),
   [hands-free](https://docs.wisprflow.ai/articles/6391241694-Use-Flow-hands-free),
   [what's new](https://wisprflow.ai/whats-new)). Aqua can rerun a transcription from history
   ([changelog](https://aquavoice.com/changelog)). It is also a quick fix for the wrong
   language heard on short clips (`TODO.md` step 3).
8. **Your Attention Latency** (Wispr Flow Insights). A weekly page or spoken line with how
   long sessions waited for you, median and worst, and how many were answered without opening
   the terminal. Wispr's Insights tab shows words per minute, a daily streak heatmap and a
   "Your Voice" profile ([what's new](https://wisprflow.ai/whats-new)). Sidetone's version
   would measure its own pitch, and give the numbers `TODO.md` step 6 wants to publish.

## Wispr Flow

A dictation app for Mac, Windows, iOS and Android
([what is Flow](https://docs.wisprflow.ai/articles/2772472373-what-is-flow)). It processes speech
in the cloud. Details of how the Flow Bar looks come partly from a
[third-party design reference](https://cdn.jsdelivr.net/npm/@agent-native/core@0.124.6/corpus/templates/clips/desktop/design-refs/wispr-ux.md)
written for another project, not from Wispr; those lines say so.

### The Flow Bar: how it looks and moves

- **Idle Bubble** (Maybe). A small bubble stays on screen when idle. It shows that Flow is
  ready, and clicking it starts dictation
  ([hands-free](https://docs.wisprflow.ai/articles/6391241694-Use-Flow-hands-free); size,
  colors and motion are not published, per the
  [design reference](https://cdn.jsdelivr.net/npm/@agent-native/core@0.124.6/corpus/templates/clips/desktop/design-refs/wispr-ux.md)).
  Sidetone's bar already does this job.
- **White Bars That Follow Your Voice** (already built). While listening the bar widens and
  shows white bars that stay low in silence and rise as you speak, the same widget as the
  microphone test in onboarding (design reference above). Sidetone's voice bars in the light
  match this.
- **No Separate Processing State** (Maybe). On release the bars stop and the text is pasted;
  the paste is the success signal (design reference above). Sidetone shows a "transcribing"
  sign. Once transcription is under about half a second, that sign could be dropped too.
- **Shrinks and Fades When Unused** (Maybe). Flow's Android bubble shrinks after 5 seconds of
  inactivity and has an opacity slider from 20 to 100 percent
  ([what's new](https://wisprflow.ai/whats-new), April 24, 2026). In Sidetone, the bar could
  dim when nothing is happening and come back to full strength when a session speaks or
  needs you, as a setting.
- **Drag to Any Edge, Remembered** (already built). The bar can be dragged to the left, right
  or bottom edge and stays there ([what's new](https://wisprflow.ai/whats-new), July 9, 2026).
- **Language Picker in the Bar** (Maybe). One click on the bar switches the dictation
  language, among the languages chosen in settings
  ([what's new](https://wisprflow.ai/whats-new), March 31, 2026). For Sidetone, a key or a
  click on the light could fix the language of the next recording. That deals with the
  short-clip problem in `TODO.md` step 3 without guessing.
- **Quiet Start on Windows** (already built). Flow starts at login with the tray icon and
  bar ready, and its hub window does not open
  ([what's new](https://wisprflow.ai/whats-new), August 21, 2026).

### Hotkeys

- **Hold or Toggle** (Fits well, top pick 3). Hold to talk, or start hands-free with its own
  key or a double tap, and stop with one more press
  ([hands-free](https://docs.wisprflow.ai/articles/6391241694-Use-Flow-hands-free)).
- **Cancel Within Half a Second** (Maybe). Pressing the hands-free key again within half a
  second of starting cancels instead of pasting, and the cancel notice offers Undo
  ([hands-free](https://docs.wisprflow.ai/articles/6391241694-Use-Flow-hands-free)). An Undo
  after Sidetone's cancel key during a recording would send the words after all.
- **Keys Ignored While Busy** (Maybe). Presses are ignored while Flow is stopping,
  processing or retrying (same page). Worth checking that Sidetone handles a talk press
  during transcription on purpose.
- **Mouse Buttons as Keys** (Fits well). Middle click and mouse buttons 4 and 5 can be the
  push-to-talk key, alone or with modifiers, and they no longer reach other apps
  ([shortcuts](https://docs.wisprflow.ai/articles/2612050838-supported-unsupported-keyboard-hotkey-shortcuts)).
  Aqua and Raycast added the same ([Aqua changelog](https://aquavoice.com/changelog),
  [Raycast changelog](https://www.raycast.com/changelog/windows/2)). With a hand on the mouse
  during a video, a side button as the talk key saves reaching for Ctrl+Alt+Space. The
  overlay's mouse hook could take it.
- **Up to Four Keys per Action, Conflict Warning** (Maybe). Each action takes up to four
  bindings, and a hands-free key inside the push-to-talk key saves but warns for five
  seconds (same page). Sidetone's settings window could warn the same way when one key
  contains another.
- **Rebindable Cancel and Enter** (already built). Cancel and Enter can be rebound, for Vim
  and terminals ([what's new](https://wisprflow.ai/whats-new), March 31, 2026).

### Command Mode

- **A Key for Instructions, Not Words** (Maybe). A separate key: hold it, say an instruction,
  and Flow edits the selected text, drafts a reply, or searches with Perplexity
  ([Command Mode](https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode)).
  Sidetone does this today with spoken openings ("by the way", usage, clear the chat). A
  separate "talk to Sidetone" key would let any wording reach the hub instead of the session
  ("allow all", "stop everything", "which one is waiting?"), with no magic phrases.
- **Result Where You Can See It** (Not for us). With no text field focused, Flow shows the
  result in a notification and copies it (same page). Sidetone speaks.

### Auto-Editing and Filler Removal

- **Backtrack** (Not for us). "Coffee at 2 actually 3" becomes "coffee at 3", and "scratch
  that" drops the abandoned part
  ([Smart Formatting & Backtrack](https://docs.wisprflow.ai/articles/5373093536-how-do-i-use-smart-formatting-backtrack)).
  Claude reads a correction in a raw transcript without help. A spoken discard was also
  turned down for Sidetone ("never mind" could throw away a message meant).
- **Cleanup Levels** (Not for us). None, Light (removes fillers, fixes grammar) and Medium
  (also rewrites for clarity) (same page). It would add a model call before sending, and
  Claude does not need it.
- **Spoken Punctuation and Lists** (Not for us). "New line", "question mark", and numbers
  spoken in a row become a list (same page).
- **Prompt Engineer Transform** (Not for us). Rewrites a dictation into a structured AI
  prompt ([what's new](https://wisprflow.ai/whats-new), May 1, 2026). Claude is the reader
  already.

### Personal Dictionary and Context

- **Dictionary That Learns** (Fits well, top pick 2). Correct a misheard word and Flow adds
  it; terms can be added by hand ([features](https://wisprflow.ai/features)). Sidetone could
  learn from a recording that is taken back and then typed the right way, or offer
  `sidetone word add NAME`, as Raycast has "Add Word to Vocabulary"
  ([Raycast changelog](https://www.raycast.com/changelog/windows/2)).
- **Variable Recognition** (Fits well, part of top pick 2). Flow reads function, class and
  variable names from the editor and wraps them in backticks
  ([variable recognition](https://docs.wisprflow.ai/articles/8554805225-variable-recognition),
  [IDEs](https://docs.wisprflow.ai/articles/6434410694-use-flow-with-cursor-vs-code-and-other-ides)).
  The hub knows each session's working folder, so it can collect names from it without
  reading the screen.
- **File Tagging** (Fits well). Saying a file name with its extension, or "at" before it,
  makes an @-tag in Cursor and Windsurf (same IDE page). Claude Code reads `@path` too: the
  hub could turn "at hub dot py" into `@hub/hub.py` when the file exists in that session's
  folder.
- **Context Awareness** (Not for us as built). Flow sends app info, the text box and on-screen
  text with each dictation ([context awareness](https://docs.wisprflow.ai/articles/4678293671-feature-context-awareness);
  the page's two versions disagree on what is sent when it is off). Reading the screen
  is more than Sidetone needs, and one review reports controversy over screenshots
  ([Spokenly review](https://spokenly.app/blog/wispr-flow-review), a competitor's blog, not
  verified).

### Snippets and Styles

- **Snippets** (Fits well). A spoken cue inserts a longer saved text
  ([features](https://wisprflow.ai/features)). Sidetone version: "run the checks" expands
  to a saved instruction or a slash command before the hub hands it over, with a list in
  the settings window. Long requests you repeat every day get shorter to say.
- **Styles per App** (Not for us). Tone set per kind of app, casual to formal, English and
  desktop only ([features](https://wisprflow.ai/features),
  [AlternativeTo news](https://alternativeto.net/news/2025/10/wispr-flow-introduces-personalized-text-formatting-by-app-type)).
  The spoken line could go the other way, with its length and tone chosen per project.
  Maybe, later.

### Whispering

- **Works When You Whisper** (Maybe). Flow keeps working when you speak quietly
  ([features](https://wisprflow.ai/features)). One guide puts accuracy at 92 to 95 percent
  against 97 at normal volume ([Sid Saladi](https://sidsaladi.substack.com/p/wispr-flow-101-the-complete-guide);
  not verified). For Sidetone, raise the gain of a quiet recording before Whisper, and
  measure whether short whispered words still come through.

### The Hub, History and Insights

- **Searchable History With Retry and Playback** (Fits well, top pick 7). History is grouped
  by date, entries can be copied, flagged or retried, and audio from the last 14 days can be
  played back ([navigating the app](https://docs.wisprflow.ai/articles/5096240724-navigating-the-wispr-flow-app-desktop-ios-and-android),
  [what's new](https://wisprflow.ai/whats-new), August 5, 2026). Hearing your own clip next to
  what Whisper wrote is also the "practice speaking" item, already on `TODO.md` step 7.
- **Recover After Quitting** (Not for us). Audio from a dictation cut off by quitting is kept
  and can be finished from history ([what's new](https://wisprflow.ai/whats-new), May 1,
  2026). That is a development-time fault for Sidetone.
- **Insights** (Fits well, top pick 8). Words per minute against other users, words cleaned
  up, top apps, a daily streak heatmap, a "Your Voice" profile after 2,000 words, team
  leaderboards ([what's new](https://wisprflow.ai/whats-new), April 24, 2026).
- **Usage Dashboards for Teams** (Not for us) ([features](https://wisprflow.ai/features)).

### Errors and Latency

- **Silent Microphone Warning** (Fits well). If the microphone picks up nothing when you
  start, Flow warns at once, so you don't learn it after letting go
  ([what's new](https://wisprflow.ai/whats-new), October 9, 2026). In Sidetone, after about a
  second of a flat level while the key is held, the light could show a struck microphone and
  play the "not sent" sound, before the hold is wasted.
- **"Speaking a Different Language?"** (Maybe). When it hears a language outside the chosen
  set, Flow offers to add it ([what's new](https://wisprflow.ai/whats-new), September 28 and
  October 9, 2026). It ties to `TODO.md` step 3.
- **One-Tap Retry, Marked in Orange** (Fits well, top pick 7). Failed transcripts are marked
  and have a retry button ([what's new](https://wisprflow.ai/whats-new), June 17, 2026).
- **Latency Down 30 Percent** (for comparison). Wispr published a 30 percent drop since
  January, with no absolute figure ([what's new](https://wisprflow.ai/whats-new), July 9,
  2026). Flow publishes no end-to-end latency figure
  (design reference above), so a measured number from Sidetone would stand out on release.
- **Time Limit Warnings** (Not for us). A warning at 19 minutes and a stop at 20, keeping the
  audio ([hands-free](https://docs.wisprflow.ai/articles/6391241694-Use-Flow-hands-free)).

### Sounds

- **Interaction Sounds** (Maybe). A ping when Flow is ready to listen, as a setting
  ([auto-mute page](https://docs.wisprflow.ai/articles/7231650589-auto-mute-music-while-dictating-on-macos-how-audio-detection-works);
  the design reference says there is no stop sound). Sidetone has sent, waiting and not sent,
  but no "listening" sound. A very short tick when the recorder is really open would tell an
  eyes-free user when to start talking. Short sounds for states are already on `TODO.md`
  step 4.
- **Mute or Pause Media While Dictating** (Fits well, top pick 1). Mute is off by default on
  Mac and on by default on Windows, and "Pause music while dictating" is an alternative
  (same page).
- **Notification Categories Muted One by One** (Maybe). Tips, reminders and milestones can be
  muted separately ([what's new](https://wisprflow.ai/whats-new), March 31, 2026).

### Coding Agents and Sending

- **"Press Enter"** (Not for us). Ending a dictation with "press enter" submits it; it is
  off by default because it sends at once
  ([prommer.net](https://prommer.net/en/productivity/wispr-flow-press-enter/), which measured
  106 of 145 hits, 73 percent; one report says it did not register in Claude Code
  ([issue](https://claudeissues.com/issue/39983-simulated-enter-keypress-from-voice-tools-wispr-flow-not-registered-in-raw-mode))).
  Sidetone sends on release already.
- **Long Dictations Stay Visible in Claude Code** (Not for us). Flow stopped long pastes
  collapsing into "[Pasted N lines]" in Claude Code and Codex
  ([what's new](https://wisprflow.ai/whats-new), May 1, 2026). Sidetone does not paste into
  the terminal.

### Onboarding

- **Try It Yourself Sandbox** (already on `TODO.md` step 7, "practice speaking"). Setup
  ends in a practice area with a pretend Gmail and Notion, after a microphone test with the
  same bars as the Flow Bar (third-party
  [design reference](https://cdn.jsdelivr.net/npm/@agent-native/core@0.124.6/corpus/templates/clips/desktop/design-refs/wispr-ux.md),
  not verified with Wispr). New detail: Sidetone's made-up sessions (`hub/demo.py`) could be
  that sandbox, with one demo session that speaks, asks permission and answers by voice.
- **Sign-In Slides** (Not for us). The login screen shows what Flow can do
  ([what's new](https://wisprflow.ai/whats-new), August 21, 2026).

## Superwhisper

A Mac dictation app, local or cloud, built around modes.

- **Modes per App** (Maybe). A mode (voice only, message, mail, note, custom instructions)
  turns on by itself in chosen apps or websites, and each mode has its own speech model
  ([modes](https://superwhisper.com/docs/modes/modes)). For Sidetone: talking settings per
  project, such as a bigger model or confirm before sending for one repo.
- **What Happens to Other Sound** (Fits well, top pick 1). Keep Playing, Pause, Mute, Lower
  or Muffle, per mode (same page).
- **Clipboard and Selection as Context** (Fits well, top pick 6). Text copied within 3 seconds
  before or during a recording is taken along, with a sign that lights when it is
  ([recording window](https://superwhisper.com/docs/get-started/interface-rec-window)).
- **Confirm Before Throwing Away a Long Recording** (Fits well). Esc cancels a recording under
  30 seconds at once and asks first for a longer one (same page). Sidetone's cancel key could
  do the same, so a long instruction is not lost to a slip.
- **Mini Window** (already built). A compact indicator that, on hover, shows the mode and a
  stop button; right click opens settings and history (same page). Like Sidetone's bar.
- **Live Words While Recording** (Maybe). With a realtime model, words appear as you speak
  (same page). Sidetone would need streaming Whisper. On the graphics card (`TODO.md` step 3)
  it might fit; measure the cost first.

## Aqua Voice

Dictation focused on accuracy, with its own model, Avalon, for English
([Aqua vs Wispr](https://aquavoice.com/blog/aqua-voice-vs-wispr-flow)).

- **Deep Context** (Fits well as a dictionary, part of top pick 2). Reads the active screen to
  get a variable name, a teammate's handle or a CLI flag right
  ([voice coding](https://aquavoice.com/blog/voice-coding-cursor-claude-code)).
- **Custom Dictionary, Matched by Sound** (Fits well, top pick 2). Up to 800 entries on Pro,
  and terms matched by how they sound (same page,
  [changelog](https://aquavoice.com/changelog), October 6, 2026).
- **Microphone Start From 298 to 122 ms** (Fits well, as a measurement). Aqua measured and cut
  the time to open the microphone on Windows ([changelog](https://aquavoice.com/changelog),
  September 14, 2026). Sidetone should measure the time from key press to the first recorded
  sample (`parec` start), since words said in that gap are lost.
- **Aqua Pet** (Maybe). A pet sits where the floating bar is, listens while you talk and
  "throws your words into the text field" (changelog, October 15, 2026). A delight option
  for a layout setting.
- **Liquid Glass Bar With an Orb and Waveform** (already built, close). Mac, September 22,
  2026 (changelog).
- **Send It** (Not for us). Saying "send it" ends a hands-free dictation and presses a key you
  choose (changelog, July 26 and 29, 2026).
- **Ignore Virtual Microphones** (Maybe). Virtual inputs can be blacklisted so a real
  microphone is picked (changelog, September 4, 2026). Sidetone records the default source
  (`mic_source`); a check that it is not a monitor or virtual device would help new users.
- **Edit Mode** (Not for us). Select text and say the change (changelog, July 20, 2026).

## OpenWhispr

Open source dictation for Mac, Windows and Linux, local or cloud
([llms.txt](https://openwhispr.com/llms.txt)).

- **Call the Agent by Name** (Maybe). Saying the agent's name at the start of a dictation
  sends it to the agent instead of typing it ([agent mode](https://docs.openwhispr.com/guides/agent-mode.md)).
  For Sidetone: start with a session's name ("docs, run the tests") to reach it without
  moving the focus. Names that sound alike could send words to the wrong session, so it
  needs care.
- **Tap or Hold** (Fits well, top pick 3). The hotkey works as tap-to-record or
  hold-to-talk ([scriptbyai](https://www.scriptbyai.com/openwhispr-dictation-meeting-notes/),
  third party).
- **Answer in a Floating Panel** (Not for us). A spoken command's answer streams into a
  panel ([v1.9.0 release](https://newreleases.io/project/github/OpenWhispr/openwhispr/release/v1.9.0)).

## PipeVoice

Free, open source Windows dictation. Only directory pages were found, not the project's own
site, so none of this is verified.

- **Profile Chosen by the Window in Front** (Maybe). Per-app settings picked from the focused
  window ([similarlabs](https://similarlabs.com/p/pipevoice)).
- **Read Selected Text Aloud** (Maybe). Windows OCR reads selected screen text with a local
  voice (same page). For Sidetone, a key that reads the whole reply of the session in
  focus, not just its summary. It relates to "the full message" on `TODO.md` step 4 (Larger
  extras), for a listener rather than a reader.
- **Local Whisper Plus Local Ollama** (already built, the local part) (same page).

## Willow Voice

- **Style Matching** (Not for us). Learns to sound like you, adjustable in a Style Matching
  tab ([Product Hunt](https://www.producthunt.com/products/willow-voice?page=1),
  [YC launch](https://www.ycombinator.com/launches/NT7-willow-voice-voice-is-your-new-keyboard)).
  Sources disagree on whether it runs locally or in the cloud.
- **Context-Aware Names** (part of top pick 2)
  ([YC launch](https://www.ycombinator.com/launches/NT7-willow-voice-voice-is-your-new-keyboard)).

## MacWhisper

- **Always on Top, as a Toggle** (already built). The Global window floats over every app,
  and can be set not to ([Global](https://macwhisper.helpscoutdocs.com/article/16-global)).
- **AI Prompts per App** (Not for us)
  ([Sweet Bits review](https://thesweetbits.com/tools/macwhisper-review/)).
- **Send Transcripts to Webhooks, Notion, Obsidian** (Maybe, not verified on the official site)
  ([Gumroad](https://goodsnooze.gumroad.com/l/macwhisper)). For Sidetone, a webhook out for
  events, see CodeIsland below.

## Talon

Hands-free control by voice, noises and eye tracking.

- **Noises as Commands** (Maybe). A "pop" or "hiss" can be bound to an action
  ([docs](https://talonvoice.com/docs/), [1.0 changelog](https://talonvoice.com/dl/latest/changelog.html)).
  A mouth click to allow would be fun, but with a video playing it would fire by mistake.
- **Sleep Mode** (already built, as mute). Talon ignores everything until a wake command
  ([wiki mirror](https://scour.ing/@abnv/p/https://talon.wiki/Basic%20Usage/basic_usage)).
- **Eye Tracking** (Not for us). Needs a Tobii tracker (1.0 changelog).

## Notch and Overlay Apps for Coding Agents

All Mac, all silent, all fed by hooks like Sidetone. Several are on
`docs/dev/similar-projects.md` already. Product Hunt pages were the only source for some,
so those lines are the makers' claims.

### CodeIsland (wxtsky)

The fullest of them ([README](https://github.com/wxtsky/CodeIsland)).

- **Follow-Up Reminders** (Fits well, top pick 4). Opt-in reminders for approvals, questions
  and finished work nobody looked at.
- **Quiet Hours, and Mute While Away** (Fits well). Sounds stop in set hours and while the
  screen is locked or asleep. In Sidetone, lines said to a locked screen are lost. The
  overlay could tell the hub when Windows locks, and the hub would hold the lines and mark
  them not heard for catching up.
- **Push Only While Away** (new detail for `TODO.md` "phone notification"). Pushes to ntfy,
  Telegram, Slack and others go out only while you are away, and never for subagents.
- **Silence Rules per Folder** (Maybe). No alerts for chosen directories. A per-project
  "quiet" switch beside the per-project voice.
- **A Glance Dot Instead of a Sound** (Maybe). A quieter way to say a turn is done. The
  settings window could choose, per state, between voice, sound and light only.
- **Error Sound Only for a Failed Turn** (Fits well, check). A failed tool call makes no sound;
  only a turn that fails does. Worth checking Sidetone treats `PostToolUseFailure` the same.
- **Auto-Expand for Approvals and Questions, With a Hover Delay** (Maybe). Separate switches.
- **Mascot per Tool, Animated by State; a Desk Buddy** (Maybe). Pixel mascots, and an ESP32
  desk toy that sleeps, types and waves.
- **Git Branch and Worktree on Each Card** (Fits well). Tells two sessions of the same repo
  apart at a glance. The hub knows the working folder; the branch is one `git` call.
- **Short Window Labels: "5h" and "7d"** (for the usage labels). CodeIsland shows "5h and 7d
  usage percentages" ([dev.to](https://dev.to/krisying/i-turned-my-macbooks-notch-into-a-control-center-for-ai-coding-agents-2o57)),
  and AgentPeek writes "5-hour and 7-day windows" ([site](https://agentpeek.app/)).
- **Webhook Forwarding of Raw Events** (Maybe). For people's own automations.
- **SSH Remote Hosts** (Maybe). Sessions on a server beside local ones.

### Coder Island

([site](https://luokebi.github.io/coder-island/))

- **Sound Presets and Your Own Files** (Maybe, adds to `TODO.md` step 4 "short sounds").
  Mario, Pop and Chime presets, per-event toggles, and imported audio files.
- **Don't Expand for the Terminal in Front** (Not for us). Close to "stay quiet for the
  session whose terminal is in front", which the author turned down for a mute key
  (`TODO.md`, Built).
- **Usage Inline Next to Each Agent, Reset Time on Hover** (already built, close).

### ClaudeNotch

([site](https://rawsun007.github.io/claude-notch/))

- **Red and Green Diff in the Permission Card** (Fits well). Edits show their diff before you
  allow them. Sidetone's card shows the command. For an edit, a few lines of diff (or "12
  lines in hub.py") would make Allow from the overlay safe without switching.
- **Hold for Risky Commands** (Fits well, top pick 5).
- **Enter Allows, Esc Denies** (already built, as Ctrl+Alt+Y and N).
- **Limit Projection** (Fits well). Estimates when you will hit the cap at the current rate.
  Spoken with Sidetone's usage line: "at this pace the five-hour limit runs out at 16:40".
- **Spend Cap, Skill Costs, Usage Heatmap** (Not for us; the author is on a subscription).
- **Drag a Folder Onto the Notch to Start a Session** (Maybe).
- **Pet Mode** (Maybe). A creature that backflips when booped.

### Vibe Island

([Claude Code page](https://vibeisland.app/claude-code/))

- **Plan Review in the Notch** (Fits well). On ExitPlanMode the full plan shows with Markdown,
  and you approve it or send feedback. Sidetone never offers plan approvals to the keys. A
  spoken plan summary, a key to approve, and push-to-talk for feedback would cover it.
- **Jump to the Exact Tab and Split Pane in 20+ Terminals** (already built for VS Code).
- **Usage Alerts Before the Limit** (already built, `usage_warn`).

### AgentValley

([Product Hunt](https://www.producthunt.com/products/agentvalley))

- **Waiting Time Badge, Oldest First, "3 Need You"** (Fits well, top pick 4).
- **A Character That Waves and Says What It Needs** (already built, as the voice).
- **A Fishing Break at the Usage Limit** (Maybe). At the limit the crew goes fishing until
  it resets. A small delight for the light when usage runs out.
- **Finished Subagent Reports in a "Green Book"** (Maybe). Shows how many are new.

### Chimlo

([Product Hunt](https://www.producthunt.com/products/chimlo-agents-in-your-macbook-notch))

- **Allow Once or Allow for This Session** (Fits well, with top pick 5).
- **Needs-Attention Rows Move to the Top** (Maybe). Sidetone keeps your own order on purpose;
  a setting could float waiting sessions up.
- **Reopen Completed Work** (Maybe).

### AgentPeek

([site](https://agentpeek.app/), [Product Hunt](https://www.producthunt.com/products/agentpeek))

- **Always Allow Saved Into Claude Code's Own Settings** (Fits well, top pick 5). The maker
  says the rule goes back to Claude Code
  ([Product Hunt search summary](https://www.producthunt.com/products/agentpeek/launches), not
  read in full).
- **Pending Prompts Stack** (already built). Sidetone shows the oldest.
- **Local Dev Servers in the Notch** (Not for us).
- **Agent Board by Status** (Maybe). A reviewer asked for clearer priority between needs you,
  working and idle (Product Hunt page).

### Agent Notch, Notchcode, Vibe Notch, Claude Island

- **Green "Finished Since You Last Looked," Cleared by Focusing the Terminal** (already built,
  close: the white dot on lines not heard) ([Agent Notch](https://www.producthunt.com/products/agent-notch)).
- **Notchcode on Windows as a Top-Center Pill That Glows When an Agent Needs Input**
  (already built) ([Product Hunt](https://www.producthunt.com/products/notchcode)).
- **Vibe Notch, Formerly Claude Island: Approve and Deny, Chat History With Markdown**
  (already built, close) ([SourceForge](https://sourceforge.net/mirror/vibe-notch/),
  [Homebrew](https://formulae.brew.sh/cask/vibe-notch)).

## Windows Islands and Overlays

### Notchify, Isle Notch, WinIsland, DynamicWin

Media and notification islands, not for agents. The Windows Central articles could not be
read past the headline, so these come from listings.

- **Island or Notch Look** (already built, as bar and island). Notchify has a detached island
  and a notch joined to the screen top
  ([AlternativeTo](https://alternativeto.net/software/notchify/about/)).
- **Hide in Full Screen or on Chosen Apps, a Key to Show or Hide** (Maybe). Isle Notch
  ([toolradar](https://toolradar.com/tools/isle-notch)). Sidetone already handles games; a
  list of apps to hide over could be a setting.
- **One Island per Monitor, Each Set on Its Own** (Maybe). Isle Notch (same page).
- **Scroll to Switch Views** (already built, as the wheel moving the focus). DynamicWin
  ([GitHub](https://github.com/FlorianButz/DynamicWin)).

### Xbox Game Bar

- **Two Transparencies: Click-Through and Interactive** (Fits well). Pinned widgets have one
  opacity while clicks pass through and another while they take clicks
  ([transparency](https://learn.microsoft.com/en-us/gaming/game-bar/guide/transparency),
  [click-through](https://learn.microsoft.com/en-us/gaming/game-bar/guide/click-through)). For
  Sidetone: fainter while you only watch, solid while Ctrl+Alt is held. That pairs with
  "Shrinks and Fades When Unused" above.
- **Hide Input Boxes While Click-Through** (already built, close). Microsoft's own advice for
  widgets (same click-through page).

### Discord Overlay

- **Show People Always or Only While Speaking** (Fits well). The voice widget can list
  everyone or only who is talking, and names can show only while speaking
  ([Game Overlay](https://support.discord.com/hc/en-us/articles/217659737)). For Sidetone: a
  setting where idle sessions' lights fade out and only the one speaking or needing you is
  shown, for full-screen video.

### Raycast for Windows

([changelog](https://www.raycast.com/changelog/windows/2))

- **Import Settings From Wispr Flow, Aqua and Handy** (Maybe). Hotkeys included. On release,
  reading a Wispr Flow user's talk key would make switching easy.
- **Single or Double Tap of Modifiers as Hotkeys; the Recorder Warns of Conflicts** (Maybe).
- **Diagnostics Flag a Missing Microphone or Sticky Keys Conflict** (Fits well).
  `sidetone status` could check the microphone too: a short recording, and its level.
- **Background Notification When a Reply Finishes or Needs Input** (already built, by voice).

### PowerToys Command Palette Dock

([Dock docs](https://learn.microsoft.com/windows/powertoys/command-palette/dock))

- **Reserves Screen Space Like the Taskbar** (Maybe). The Dock uses the AppBar API so windows
  don't go under it. A bar along an edge would no longer cover a window's title bar.
- **Auto-Hide Until You Touch the Edge, Pinned if the Edge Is Taken** (Maybe).
- **A Key That Walks the Items** (already built, as the focus keys). Win+Alt+J focuses the
  Dock, again moves on, Shift goes back, Enter acts, Esc leaves.
- **Tint From the Windows Accent Color, Custom Color or Image** (already on `TODO.md` step 4,
  "glass tint"). New detail: "Accent Color" as one of the choices.

## What could not be verified

- The Flow Bar's exact size, colors and animation timing: Wispr does not publish them, and
  the only description is a third-party design reference.
- PipeVoice, Isle Notch, Notchify: only directory or listing pages were found; the Windows
  Central articles on Notchify could not be read past their headlines.
- AgentValley, Chimlo, Agent Notch, Notchcode and AgentPeek's Always Allow: the makers' own
  words on Product Hunt only.
- Willow's processing: its own launch post says cloud, a directory page says local.
- WinIsland: several projects share the name; the GitHub mirror that was found is gone.
