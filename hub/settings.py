"""The settings window: what it offers, and what choosing something does.

The window itself (overlay/Overlay.cs) only draws what `describe` hands it and sends back
"this key, this value"; everything else is here, so it can be tested without a screen. A
setting is one entry of SECTIONS:

    key    where it lives: "speed" (the top of config.json), "overlay.layout", "terminal.tint",
           "overlay.hotkeys.talk", and two that are not in that file: "mute" (the voice off for
           every session, which is the file ~/.claude/voice-off) and "voice_in.<language>.<voice>"
           (whether that language's sessions take that voice; see `_voices`)
    kind   choice (a few named values, drawn side by side) | switch | number | key (a hotkey)
           | pick (one of many, drawn as a list that drops down; "play": a ▶ that previews it)
           | color ("#RRGGBB", drawn as a dot; a few ready colors and a box for one's own drop down)
           | voice (a voice of a language with a ▶ and a tick; "more": folded away until asked)
           | heading (a title over the next card; "fold": it opens and closes it, "summary" beside it)
           | intro (a sentence under the section's title; the Voices section only)
    name, help   what the window writes: a few words, and one plain sentence under them

A change takes effect at once and is written to config.json, so it is still there after a
restart. Adding a setting to the window is adding a line here.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import threading
import time

import base
import overlay as overlay_mod
import packs
import stt
import terminal as terminal_mod
import tts


def choice(key: str, name: str, help: str, *options) -> dict:
    """`options`: (value, what the window calls it) each."""
    return {"key": key, "kind": "choice", "name": name, "help": help, "options": [list(o) for o in options]}


def switch(key: str, name: str, help: str) -> dict:
    return {"key": key, "kind": "switch", "name": name, "help": help}


def number(key: str, name: str, help: str, low: float, high: float, step: float, unit: str = "") -> dict:
    return {"key": key, "kind": "number", "name": name, "help": help, "min": low, "max": high, "step": step, "unit": unit}


# The ready colors a color setting drops down, after its own default (2026-11-23, the author
# chose "swatches + hex" over themes only or a color wheel). Nine of them: the tenth place is
# the picker, for any color by eye (2026-11-24, the author: "remove one and make it a color
# picker icon"). Light enough to read on the dark
# glass; the glass's own are dark, so white words stay readable on them.
LIGHT_SWATCHES = ["#4FC3F7", "#FFB300", "#66BB6A", "#EF5350", "#B0B6C0", "#B388FF", "#FF7043", "#26C6DA",
                  "#F06292", "#FFEE58"]
GLASS_SWATCHES = ["#2E3A4A", "#3A2E48", "#2E4038", "#463434", "#3C3C3C", "#1E2A3A", "#403828", "#2A3F4A", "#101010"]
SLATE = "#3A4150"  # what the glass's "" looks like


def color(key: str, name: str, help: str, swatches: list) -> dict:
    """An overlay color. Its default comes first among the swatches; "" (the glass's own
    slate) is drawn as `empty`."""
    first = overlay_mod.DEFAULTS[key[8:]]
    return {"key": key, "kind": "color", "name": name, "help": help, "empty": SLATE,
            "swatches": ([first] + [c for c in swatches if c != first])[:9]}


def heading(key: str, name: str) -> dict:
    """A small title over the settings that follow it, inside a section."""
    return {"key": f"heading.{key}", "kind": "heading", "name": name, "help": ""}


def hotkey(name: str, label: str, help: str = "") -> dict:
    return {"key": f"overlay.hotkeys.{name}", "kind": "key", "name": label, "help": help}


# The languages the summary can be held to: those whose voices have been chosen and heard (the
# author, 2026-11-20: "we can just limit to Italian, English and Chinese ... we can add the rest
# in the future"). Kokoro has voices for es, fr, hi, ja and pt as well, not yet listened to.
SUMMARY_LANGUAGES = ["en", "it", "zh"]

SECTIONS = [
    # Most used first (the author, 2026-11-20: "most use should be on top"): what you reach for
    # every day, then what is set once.
    ("Speech", [
        # Was "Voice", "Speak a short summary of each reply.": the author took it for short or long
        # answers (2026-11-20: "it sounds like it's more like a mute or not").
        switch("mute", "Mute", "No voice for any session. The mute key does the same."),
        # One session muted by its own key (overlay.hotkeys.mute_session) is not a switch here:
        # it belongs to a session, not to the settings. What gets through from it is.
        switch("muted_asks", "Muted Sessions Still Ask", "A session you muted by itself still says when it needs your answer. Off: it only shows it."),
        # One volume for the voice and the sounds (the author, 2026-11-20: "do one thing for both so
        # it's more consistent"); `sound_volume` stays in config.json as the sounds' level beside the voice.
        number("volume", "Volume", "The voice and the short sounds together.", 0, 100, 5),
        number("speed", "Speed", "How fast the voice talks.", 0.7, 1.6, 0.05, "x"),
        {"key": "reply_language", "kind": "pick", "name": "Language of the Summary",
         "help": "The spoken line in the language you wrote or spoke in, or always in one language.",
         "options": [["spoken", "Match My Language"]] + [[code, base.LANGUAGE_NAMES.get(code, "English")] for code in SUMMARY_LANGUAGES]},
        choice("label", "Say the Session Name", "Its name as the overlay shows it, from its folder, said before each of its lines so you know who talks without looking.",
               ("always", "Always"), ("never", "Never")),
        choice("voice_device", "Voice Made On", "Where the voice is made. The graphics card (NVIDIA) starts each line "
               "sooner; Automatic uses it when there is one.", ("auto", "Automatic"), ("cpu", "Processor"), ("gpu", "Graphics Card")),
        # "When Your Words Go Out" (talk_feedback: sound, voice, nothing) left the window on
        # 2026-11-20, the author: "I think the sound is kind of necessary ... only to sound". It is
        # still read from config.json.
    ]),
    ("Voices", []),  # filled in by `describe`: one line for each project, with the voices this machine has
    ("Talking", [
        # Most important first, names and words polished, 2026-11-21 (the author: "polish all the
        # settings in talking ... the title, descriptions, and reorganize them based on the most
        # important first").
        # The author, 2026-11-21, after hearing that Claude Code hands a message typed while it works
        # to Claude after its current step: "instead of queuing audios, I'm putting more info into
        # the request ... Yes". Was "A Busy Session Hears You".
        # Short choices: "After Its Current Step" and "When Its Reply Ends" took half the width (the
        # author, 2026-11-21: "the options are very long").
        choice("followup_when", "Talking to a Busy Session", "Your words reach a session that is working at its next step, "
               "as typed ones do, or at the end of its reply.",
               ("step", "Next Step"), ("end", "End of Reply")),
        # A switch; "Always" (even an idle session never sees them) left the window on 2026-11-21,
        # the author: "isn't it better to have only always and never ... on and off?". On is
        # "While it works"; "always" in config.json still works.
        switch("aside", "Side Questions", "Start with \"by the way\" while a session works: the answer is spoken at once, "
               "and the session neither sees the question nor changes course."),
        # A switch; it had a third choice, "Acting alone" (`"auto"`: only sessions whose permission
        # mode does not ask first), which the author found unclear and then took out (2026-11-21:
        # "If we were to remove it, what do you think?"; time to take words back covers a misheard
        # sentence). "auto" in config.json still works.
        switch("followup_confirm", "Confirm Before Sending", "Your words wait on the light until you tap the talk key again."),
        # A switch named for what it does, Ctrl+C's interrupt (the author, 2026-11-21: "I still don't
        # get it", then "by escape you mean control C ... If it's conventional, yes"). It was "The
        # Cancel Key Stops a Session": Always, After sending (left with the time to take words
        # back) and Never.
        switch("cancel_stops", "Cancel Key Interrupts Claude", "Like Ctrl+C: with nothing else to cancel, the cancel key stops "
               "the work of the session in focus. The session stays open."),
        # Off for a new install, and what it cannot do under the info sign (the author, 2026-11-26:
        # "put it as a setting, default as no ... in the description maybe put a info icon to show
        # the downside of them activating it"). The sentence is short because a line with a tag does
        # not wrap.
        {**switch("words_in_terminal", "Your Words in the Terminal", "What you said is written above the reply."),
         "tag": "Downsides", "tag_help": "The line is only on screen: the saved conversation does not have it, so it is "
         "not there after a resume. It comes with the reply, not when you speak, so the overlay stays the place to check "
         "your words. Claude is given the same words either way."},
        switch("clear_by_voice", "Clear the Chat by Voice", "Say \"clear the chat\" and /clear is typed into that session's terminal "
               "once it is at its prompt. Needs the VS Code extension."),
        switch("clear_progress", "Show Clearing Progress", "While a chat is being cleared, the overlay says so until it is done. "
               "With the editor's window hidden it can take up to a minute."),
        # The model on the card (whisper_gpu_model) is left out, like whisper_model: a model's
        # name, which `large-v3-turbo` fits for nearly everyone with a card.
        switch("whisper_mixed", "Mixed Languages", "When one message goes from one of your languages to another, "
               "each part is written in its own. It splits where you pause."),
        choice("whisper_device", "Transcribe On", "Where your words are written down. The graphics card (NVIDIA) is "
               "faster and uses a larger model that gets more words right; Automatic uses it when there is one.",
               ("auto", "Automatic"), ("cpu", "Processor"), ("gpu", "Graphics Card")),
        switch("keep_recordings", "Keep My Recordings", "Every recording is saved with the words it was heard as, "
               "to train a model of your own voice later. They stay on this computer."),
        # Discord's own name for it is "Push to Talk Release Delay" (the author, 2026-11-21: "Is this
        # conventional?"). Was "Listen On After Release".
        number("talk_tail", "Release Delay", "After you let go of the talk key, it keeps listening this long, "
               "so your last word is not cut off.", 0, 1, 0.1, "s"),
        # The author, 2026-11-24, walking away from the desk with the headphones on. The last sentence
        # is theirs to have ("I guess we can notify this to users who use this headphones").
        switch("headset_button", "Headset Button", "After a session speaks, press your Bluetooth headset's button to talk through its "
               "microphone, and press twice to send. Turn off its auto pause: taking the headset off can look like a press."),
        number("headset_seconds", "Headset Button Time", "How long after a session speaks the button is Sidetone's. Before and after, it is your music's.",
               10, 300, 10, "s"),
        choice("headset_send", "Headset Sends", "Automatic also sends when you stop talking, until two presses have worked on your headset.",
               ("auto", "Automatic"), ("presses", "Two Presses"), ("silence", "Silence")),
        # Out of the window, all on 2026-11-21, and all still read from config.json:
        # "Time to Cancel Before Sending" (followup_delay, 0 to 5 s), the author: "if it's unsure ...
        # they could just toggle the confirmation before sending"; confirming and taking words back
        # cover it.
        # "Time to Take Words Back" (unsend_seconds): once a session has the words the cancel key
        # stops it anyway (`cancel_stops`), and words still waiting for a busy session can now always
        # be taken back (the author: "I would increase into infinity").
        # "Speaking at a Permission Prompt" (voice_at_prompt: deny and explain, or wait): a bare yes
        # or no now answers (`spoken_verdict`), and other words are more to go on, which is what they
        # nearly always mean.
        # "Usage by Voice" (usage_by_voice), the author: "I don't think it's needed anymore since we
        # already put it visually the usage bar". Asking still works.
        # "Typing Takes the Focus" (focus_on_prompt), still on: in VS Code the focus has already
        # followed the terminal by the time you type, so it only adds anything for terminals the
        # extension cannot see; the author: "just remove it".
        # "Short Words in Your Last Language" (whisper_lean), still on, the author: "should we
        # remove this setting? ... by default that is true". It matters only with two or more
        # languages on.
        # "Mute Discord While Talking" (push_to_mute), still on, the author: "I don't think we should
        # have this setting on our side". Holding F24 does nothing until Discord is given it, and no
        # keyboard has it, so there is nothing to turn off; Discord's own keybind on the talk key
        # itself does not work (the overlay keeps that key from other programs). The setup is in the
        # README.
    ]),
    ("Overlay", [
        # The key that switches it named too (the author, 2026-11-21: "in the description of layout
        # put the combination key to switch").
        choice("overlay.layout", "Layout", "A bar of lights at the side, or an island at the top. The layout key switches them.",
               ("bar", "Bar"), ("island", "Island")),
        # The key named and the choices short (the author, 2026-11-21: "the same thing, the shortcut.
        # And maybe shorten the answers"); they were "Under the mouse" and "Always out".
        # Three views, the details key going through them in this order (the author, 2026-11-22:
        # "first only bar, second one row per each detail box, third only one detail box with all
        # the rows of the summary"); it was Always (list) or On Hover (dots).
        choice("overlay.mode", "Details", "What the overlay shows beside the lights. The details key goes through them.",
               ("dots", "Bar Only"), ("list", "All Sessions"), ("focus", "Selected Session")),
        # "Details Changing Size" (overlay.resize: quick, instant) left the window on 2026-11-21, the
        # author: "the animation is pretty standard". Still read from config.json.
        # "Move It by the Details" (overlay.panel_drag) left the window on 2026-11-21, the author:
        # dragging to move "should be default, right? So we can remove this one". Still on, still
        # read from config.json.
        # "What Opens the Details" (overlay.hover: mouse, or keys only) left the window on 2026-11-21,
        # the author: "opening the details by just hovering ... should be by default". Still read
        # from config.json.
        # The four signs of a muted voice (overlay.muted_line, muted_icon: on; muted_card_icon,
        # muted_mark: off) left the window on 2026-11-21, the author: "whenever I'm mute, I should be
        # able to see ... it's fine if we remove all of them". As they were, still read from config.json.
        # "Opacity When Idle" (overlay.opacity, and list_opacity with it; it was "Opacity at Rest")
        # left the window on 2026-11-21, its default now 100%: the author, having seen it at 50%,
        # "standard is 100% ... I don't think people are gonna use this". Still read from config.json.
        # A slider since 2026-11-21; it was Blur or Plain (`overlay.glass`, still read: "none" stays
        # plain). The author: "both are glass-like. Do you think we could do percentage like from 0
        # to 100?"
        # "Glass Effect", the author's name for it the same day: 0 % then reads as no effect.
        number("overlay.glass_clear", "Glass Effect", "How much of what is behind shows through, blurred. "
               "0 is plain dark glass.", 0, 100, 5, "%"),
        # "Lines Per Session" (overlay.row_lines) left the window on 2026-11-22: All Sessions keeps
        # to one line so nothing shifts, and Selected Session shows the sentence in full. Rows that
        # grew pushed the lights apart; rows kept tall, a bubble, and a card floating over the rows
        # below were tried and not liked. Still read from config.json.
        number("overlay.size", "Size", "How big the bar, the details and the bubble are drawn. Windows' own display scale "
               "comes on top of this.", 75, 150, 5, "%"),
        switch("overlay.still", "Reduce Motion", "The overlay opens and changes at once, with no springs, slides or glints. "
               "It is on by itself while Windows' animation effects are off."),
        # From the review of the overlay (docs/dev/overlay-review.md), 2026-11-25. "Working Light"
        # (overlay.working_motion: calm, lively) left the window on 2026-11-26, the author: "I
        # don't think is needed ... just put a single spinning speed". Calm stays; still read from
        # config.json.
        # 2026-11-25, after the previews in docs/dev/looks/: the author chose these two kinds.
        # A list to drop down, not buttons (the author, 2026-11-26: "a select would be better"),
        # with room for more kinds; the hand-drawn operators of the previews are to come.
        {"key": "overlay.character", "kind": "pick", "name": "Character",
         "help": "A small figure beside the bubble that acts what its session is doing: speaking, needing you, done, "
                 "failed. Each session keeps its own.",
         "options": [["none", "None"], ["familiars", "Familiars"], ["operators", "Operators"], ["sketch", "Sketch"]]},
        choice("overlay.character_place", "Character Place", "On the bubble's edge, so the bubble keeps its size, or inside it "
               "beside the words, smaller.", ("edge", "On the Edge"), ("inside", "Inside")),
        switch("overlay.character_details", "Character in the Details", "With the details out too: on their edge in "
               "Selected Session, small beside each session in All Sessions. Only a session with news moves."),
        # From the review of 2026-11-25; off for a new install since the 26th (the author did not like it on the screen).
        switch("overlay.session_tick", "Session Color on the Bar", "A small tick of each session's color beside its light: "
               "the color of its name in the details and of its terminal."),
        switch("overlay.muted_session_mark", "Muted Sessions on the Bar", "A small struck-out speaker on the light of a session you muted by itself. "
               "The one beside its name in the details stays."),
        choice("overlay.history", "History Shows", "What was said last, when the mouse rests on the details: by this session, or by all of them.",
               ("session", "This Session"), ("all", "All Sessions")),
        choice("overlay.focus_history", "History in Selected Session", "In the Selected Session view, what it said last: always in its card, or only when the mouse rests on the details.",
               ("always", "Always"), ("rest", "When the Mouse Rests")),
        # "\"Release to Send\"" (overlay.talk_text: glint, breathe, still) and "Messages That Wait"
        # (overlay.waiting_mark: number, clock, dot) left the window on 2026-11-22, the author: "Yes, go
        # ahead ... also remove messages that wait. Let's just keep number". Glint and Number stay;
        # both still read from config.json.
        # The page "Figures" was folded into this one on 2026-11-22, when two of its settings
        # were left (the author: "moving them into overlays instead?"). What left it:
        # "Context" (context_shown: arc, text, both, off) left the window on 2026-11-22, the
        # author: "remove these settings because arc is by default". Still read from config.json.
        # "Tokens of a Reply" (turn_tokens: new, output, all, off) and "Tokens in the History"
        # (turn_tokens_history) left the window on 2026-11-22, the author: "who doesn't want to
        # see tokens?" Tokens are always shown; both still read from config.json.
        switch("history_time", "Time in the History", "How long ago each line was said."),
        # "Mark Lines Not Heard" (history_missed) left the window on 2026-11-22, the author:
        # "we can remove that" (a white dot nobody would know the meaning of). Still off by
        # default, still read from config.json.
        # "Figures Drawn As" (overlay.details_style: tiles, line) and "Bars Under the Figures"
        # (overlay.details_bars) left the window on 2026-11-22, the author: "keep it tiles by
        # default ... we can remove this setting", the bars "as well". Still read from config.json.
        switch("usage_shown", "Plan Usage", "The five-hour window and the week, at the foot of the details."),
        # "Usage Labels" (usage_labels: short, long) left the window on 2026-11-22, the author:
        # "I don't think that is needed". Still 5H and 7D, still read from config.json.
        # "Usage Bars" (overlay.usage_layout: rows, line) and "A Model's Own Week" (usage_models:
        # none, near, all) left the window on 2026-11-22 (the author: "remove usage bars and A
        # model's own week"). A row each stays; a model's own week stays off. Both still read
        # from config.json.
    ]),
    # Colors of one's own (2026-11-23; they were only in config.json, where nobody would find
    # them). The waiting mark's and the context arc's colors and the session palette (`colors`)
    # are still only there.
    ("Colors", [
        color("overlay.working_color", "Working", "The light of a session at work.", LIGHT_SWATCHES),
        color("overlay.needs_you_color", "Needs You", "A session waiting for an answer, and the edge and keys of its request.", LIGHT_SWATCHES),
        color("overlay.done_color", "Done", "A session that has finished its turn.", LIGHT_SWATCHES),
        color("overlay.failed_color", "Failed", "A session whose turn ended in an error.", LIGHT_SWATCHES),
        color("overlay.idle_color", "Idle", "A session with nothing going on.", LIGHT_SWATCHES),
        color("overlay.glass_color", "Glass", "The color of the glass. Dark ones keep the words readable.", [""] + GLASS_SWATCHES),
        color("overlay.mic_color", "Microphone", "The light, bars and wave of the session you are talking to.", LIGHT_SWATCHES),
    ]),
    ("Terminal", [
        # Names agreed 2026-11-22 (were Tint, Tint Strength, Focus Follows the Terminal and
        # Terminal Follows the Focus; the last two "mirror images" that needed explaining).
        choice("terminal.tint", "Terminal Color", "A little of its session's color in a terminal's background.",
               ("focus", "In Focus"), ("all", "All"), ("off", "Off")),
        # Color Strength in percent (the author, 2026-11-22: "a percentage from 0 to 100"): 100 %
        # is the strongest the window offers, 0.3 of the color in config.json (see STRENGTH_TOP).
        number("terminal.strength", "Color Strength", "How much of the color goes into the background.", 0, 100, 5, "%"),
        switch("terminal.pulse", "Flash When the Focus Moves", "The terminal lights up for a moment when you move the focus to it."),
        switch("terminal.follow", "Clicking a Terminal Selects It", "Going to a terminal in the editor selects its session in the overlay."),
        switch("terminal.jump", "Switching Moves the Keyboard", "Moving between sessions with the keys or the wheel puts the keyboard in its terminal."),
        switch("terminal.window", "Switching Brings Its Window", "With a VS Code window in front, moving to a session whose project is open in another one brings that one up."),
        choice("terminal.new_session", "New Session Opens", "Where the new-session key puts the terminal: split next to the session in focus, "
               "or in a tab of its own, one in sight at a time.", ("beside", "Side by Side"), ("tab", "In a New Tab")),
        # "Name in the Terminal's Title" (terminal.title) left the window on 2026-11-22, the
        # author after trying it: "I don't know how useful it is ... I don't usually look at
        # them". Still off by default, still read from config.json.
    ]),
    ("Keys", [
        # "Share Keys Other Programs Have" (overlay.share_taken_keys) left the window on
        # 2026-11-22, the author: "I think we can just remove it" (off only makes keys stop
        # working). Still on by default, still read from config.json.
        # Grouped by what they are for, every key with a line saying what it does (the author,
        # 2026-11-22, asked whether the names and descriptions were intuitive, then: "do them all").
        heading("keys.speaking", "Speaking"),
        hotkey("talk", "Talk", "Hold it and speak to the session in focus."),
        # "Hide the Talk Key" (overlay.keep_talk_key: held, always) was in the window for an hour on
        # 2026-11-22, added on a misreading: the video pausing was the old trouble of 2026-11-17,
        # and the author had none now ("right now I don't have any issues with YouTube"). Still
        # read from config.json, with off.
        hotkey("cancel", "Cancel or Stop", "Drops a recording, takes back words not yet sent, cuts the line being spoken, or stops the turn."),
        hotkey("mute", "Mute", "Turns the voice off for every session, and on again."),
        hotkey("mute_session", "Mute One Session", "Turns the voice off for the session in focus only, and on again. The others go on speaking."),
        hotkey("repeat", "Say It Again", "Repeats the last line of the session in focus."),
        heading("keys.answering", "Answering"),
        hotkey("allow", "Allow", "Allows what a session asks to do. With answers to tick, it confirms them."),
        hotkey("deny", "Deny", "Refuses what a session asks to do."),
        hotkey("option1", "Answer 1", "Picks an answer when a session asks a question."),
        hotkey("option2", "Answer 2"),
        hotkey("option3", "Answer 3"),
        hotkey("option4", "Answer 4"),
        heading("keys.moving", "Moving Between Sessions"),
        hotkey("focus_prev", "Previous Session (Bar)", "Moves the focus up the bar."),  # was "Focus Up"
        hotkey("focus_next", "Next Session (Bar)", "Moves the focus down the bar."),
        hotkey("focus_left", "Previous Session (Island)", "Moves the focus left in the island."),
        hotkey("focus_right", "Next Session (Island)", "Moves the focus right in the island."),
        heading("keys.window", "Window"),
        hotkey("toggle", "Details", "Steps through: the bar only, every session, the session in focus."),  # was "Keep the Details Out"; named as the Details setting calls it
        hotkey("layout", "Switch Layout", "Swaps the bar and the island."),
        hotkey("settings", "Settings", "Opens and closes this window."),
        # "Go to the Terminal" (jump) left the window on 2026-11-22: no key by default, and
        # Switching Moves the Keyboard does the same at every switch (the author: "okay, remove
        # [it]"). A key can still be given in config.json.
        heading("keys.sessions", "Sessions"),
        hotkey("new_session", "New Session", "Opens a terminal in the folder of the session in focus and starts Claude Code in it. "
               "Beside it or in a tab of its own: New Session Opens, under Terminal."),
        hotkey("end_session", "End Session", "Press it twice: the editor types /exit for the session in focus and closes its terminal."),
        hotkey("clear", "Clear the Chat", "Press it twice: the editor types /clear for the session in focus, at its prompt."),
    ]),
]
KEY_PARTS = {"ctrl", "alt", "shift", "win"}
NAME = "Sidetone"  # what the window calls the tool, beside its mark


# Kokoro names its voices by language and kind: af_heart is an American woman called Heart.
ACCENTS = {"a": "American", "b": "British", "e": "Spanish", "f": "French", "h": "Hindi", "i": "Italian",
           "j": "Japanese", "p": "Brazilian", "z": "Chinese"}
VOICE_LANG = {"a": "en", "b": "en", "i": "it", "z": "zh"}  # the letters of the languages offered here
SAMPLES = {"en": "Hello, this is how I sound.", "it": "Ciao, questa \u00e8 la mia voce.",
           "zh": "\u4f60\u597d\uff0c\u8fd9\u662f\u6211\u7684\u58f0\u97f3\u3002"}
PIPER_PLACES = {"US": "American", "GB": "British", "IT": "Italian", "CN": "Chinese"}
# Chinese: Kokoro's Chinese model has 100 Chinese voices and Kokoro 1.0 eight more (read through
# espeak, graded D by Kokoro, left out). The author: "for Chinese there are too many", then "can
# you rank them in a sort of way? Four are too [few]". Ranked by how well a speech model
# understands them (see docs/dev/features.md), clearest first: each said five sentences, which
# faster-whisper "small" wrote down; fewest wrong characters, then the surest transcript.
# Measured 2026-11-21. The differences are small (7 to 15 % of characters wrong, most of it
# homophones and numbers), so it orders the list, it does not judge taste: the four the author
# picked rank 33, 34, 88 and 98.
CHINESE_CLARITY = [
    "zh:zf_049", "zh:zf_006", "zh:zm_056", "zh:zm_057", "zh:zm_030", "zh:zf_023", "zh:zm_061",
    "zh:zf_094", "zh:zm_062", "zh:zf_092", "zh:zf_059", "zh:zm_097", "zh:zm_013", "zh:zm_033",
    "zh:zm_029", "zh:zf_078", "zh:zm_096", "zh:zm_082", "zh:zm_045", "zh:zm_050", "zh:zm_089",
    "zh:zm_091", "zh:zm_053", "zh:zm_080", "zh:zm_058", "zh:zm_055", "zh:zm_014", "zh:zf_040",
    "zh:zf_073", "zh:zf_028", "zh:zf_087", "zh:zf_088", "zh:zm_009", "zh:zm_010", "zh:zf_017",
    "zh:zm_011", "zh:zf_093", "zh:zm_081", "zh:zf_084", "zh:zf_032", "zh:zf_076", "zh:zf_071",
    "zh:zf_060", "zh:zf_019", "zh:zm_037", "zh:zf_077", "zh:zm_041", "zh:zm_020", "zh:zm_031",
    "zh:zf_074", "zh:zm_015", "zh:zm_025", "zh:zf_085", "zh:zf_072", "zh:zm_012", "zh:zf_046",
    "zh:zm_069", "zh:zm_095", "zh:zf_083", "zh:zf_026", "zh:zf_039", "zh:zm_066", "zh:zf_079",
    "zh:zm_054", "zh:zm_065", "zh:zm_064", "zh:zm_063", "zh:zm_068", "zh:zm_035", "zh:zm_052",
    "zh:zm_100", "zh:zm_016", "zh:zf_038", "zh:zf_043", "zh:zf_024", "zh:zf_042", "zh:zf_004",
    "zh:zf_047", "zh:zf_099", "zh:zf_070", "zh:zm_034", "zh:zf_086", "zh:zf_021", "zh:zf_075",
    "zh:zf_090", "zh:zf_036", "zh:zf_022", "zh:zf_001", "zh:zf_027", "zh:zm_098", "zh:zf_067",
    "zh:zf_003", "zh:zf_044", "zh:zf_051", "zh:zf_018", "zh:zf_048", "zh:zf_005", "zh:zf_002",
    "zh:zf_007", "zh:zf_008",
]
# Piper's voices are quicker to make than Kokoro's and less clear (the author, 2026-11-21: "keep
# some ... that are not so good but are faster"). Measured 2026-11-21 on the author's machine,
# a sentence of about 4 s: Piper 0.29 s (Lessac) and 0.34 s (Paola), Kokoro 0.47 to 0.82 s
# (its English, Italian and Chinese voices alike, and the Chinese model 0.47 s).
PIPER_PEOPLE = {"lessac": "woman", "paola": "woman", "amy": "woman", "ryan": "man", "riccardo": "man", "huayan": "woman"}
# Kokoro's own grades for its English (and Italian) voices graded C or better (VOICES.md of hexgrad/Kokoro-82M,
# read 2026-11-21). The rest, graded D or F, are left out of the window (the author: "just keep
# the best ones ... the most clear"); they still work by name in config.json. All of Kokoro's
# voices are one model, so none is faster than another; Piper's are (PIPER_PEOPLE).
KOKORO_GRADES = {"af_heart": "A", "af_bella": "A-", "af_nicole": "B-", "bf_emma": "B-", "af_aoede": "C+",
                  "af_kore": "C+", "af_sarah": "C+", "am_fenrir": "C+", "am_michael": "C+", "am_puck": "C+",
                  "af_alloy": "C", "af_nova": "C", "bf_isabella": "C", "bm_fable": "C", "bm_george": "C",
                  "if_sara": "C", "im_nicola": "C"}  # Kokoro's two Italian voices, graded C there too
# One word for how good a voice is, the same in every language (the author, 2026-11-21: "in
# English, I see quality A, B, C+ ... in Chinese, I see clarity, X out of Y. Can you make a
# standard?"). Kokoro's letters: A and A- Excellent, the Bs Good, the Cs Okay. Chinese, from the
# measured clarity (CHINESE_CLARITY): the first third Good, the second Okay, the last Basic; under
# Chinese the word is that measure, not a grade of Kokoro's. Piper's voices are less clear (the
# author) and have no grade: Okay. "Fair" was first; the author asked "what is fair though?".
QUALITY_WORDS = {"A": "Excellent", "B": "Good", "C": "Okay"}


def quality(voice: str) -> str:
    """How good a voice sounds, in one word, or "" when nothing is known."""
    if voice in KOKORO_GRADES:
        return QUALITY_WORDS.get(KOKORO_GRADES[voice][0], "Okay")
    if voice in CHINESE_CLARITY:
        third = CHINESE_CLARITY.index(voice) * 3 // len(CHINESE_CLARITY)
        return ("Good", "Okay", "Basic")[third]
    if voice.startswith("piper:"):
        return "Okay"
    return ""


def voice_label(voice: str) -> tuple[str, str]:
    """A voice's name as people read it, and what it is: ("Heart", "American woman, Excellent"),
    and ", faster" for Piper's. It said "quality A" before the words (`quality`), and Kokoro's
    "grade" before that (the author, 2026-11-21: "quality is much more intuitive")."""
    word = quality(voice)
    word = f", {word}" if word else ""
    if voice.startswith("piper:"):  # piper:it_IT-paola-medium
        model = voice[6:].split("-")
        place = model[0].split("_")[-1] if model else ""
        who = model[1] if len(model) > 1 else voice[6:]
        kind = " ".join(w for w in (PIPER_PLACES.get(place, ""), PIPER_PEOPLE.get(who, "")) if w)
        return who.replace("_", " ").title(), f"{kind or 'Piper'}{word}"
    if voice.startswith("zh:"):  # zh:zf_001, Kokoro's Chinese model, whose voices are numbered
        m = re.fullmatch(r"z([fm])_(\d+)", voice[3:])
        if m:
            return f"{'Woman' if m.group(1) == 'f' else 'Man'} {int(m.group(2))}", f"Chinese {'woman' if m.group(1) == 'f' else 'man'}{word}"
        return voice[3:], "Chinese (Kokoro's Chinese model)"
    m = re.fullmatch(r"([a-z])([fm])_(\w+)", voice)
    if m and m.group(1) in ACCENTS:
        return m.group(3).replace("_", " ").title(), f"{ACCENTS[m.group(1)]} {'woman' if m.group(2) == 'f' else 'man'}{word}"
    return voice, "Your own voice"


# After each voice's description, how long it takes to make a sentence, timed on this computer,
# with an i that says so under the mouse. It was a "Faster" on Piper's voices alone; the author,
# 2026-11-21: "faster might not mean a lot to people ... give the seconds for each model", and
# "they're all evaluated on my PC, right? It could change on different devices": so each computer
# times its own, once, without a sound, the first time the window lists a voice. Piper's lead is
# 0.05 to 0.15 s in Italian and up to half a second in English (docs/dev/facts.md).
TIMED = {"en": "I moved the tag down a pixel, so it now sits on the same line as the description.",
         "it": "Ho spostato l'etichetta di un pixel, così ora sta sulla stessa riga della descrizione.",
         "zh": "我把标签往下移了一个像素，现在它和描述在同一行上。"}
TIME_HELP = ("How long this voice takes to get a sentence ready before it speaks, timed on this computer. "
             "Lower starts talking sooner.")
TIMES_FILE = "voice-times.json"


def timing_group(voice: str) -> str:
    """Voices that take the same time: all of Kokoro's for one accent are one model with another
    style, as are those of its Chinese model; each of Piper's is a model of its own. Timed one by
    one, Kokoro's English voices ranged from 0.50 to 0.71 s on the same sentence, which was noise."""
    if voice.startswith("piper:"):
        return voice
    if voice.startswith("zh:"):
        return "zh"
    return "kokoro:" + tts.voice_lang(voice)


def times(hub) -> dict:
    """Seconds each `timing_group` took to make its language's TIMED sentence here."""
    found = getattr(hub, "_voice_times", None)
    if found is None:
        try:
            with open(os.path.join(hub.cfg.state, TIMES_FILE)) as f:
                found = json.load(f)
        except (OSError, ValueError):
            found = {}
        hub._voice_times = found = found if isinstance(found, dict) else {}
    return found


def time_voices(hub, voices: list) -> None:
    """Times, in the background, the voices given whose group has no time yet: one voice of
    each makes its sentence once to load what it needs, then five times, and the middle time is
    kept. Not while a line is being spoken; the window is drawn again as each one is known."""
    engine = hub.speech.engine
    known = times(hub)
    todo = {}
    for v in voices:
        if timing_group(v) not in known and hasattr(engine, "time") and engine.has(v):
            todo.setdefault(timing_group(v), v)
    if not todo or getattr(hub, "_timing", False):
        return
    hub._timing = True

    def run():
        try:
            for group, v in todo.items():
                while hub.speech.current is not None:
                    time.sleep(0.5)
                text = TIMED.get(voice_language(v), TIMED["en"])
                try:
                    engine.time(text, v)
                    took = sorted(engine.time(text, v) for _ in range(5))
                except Exception as e:  # a voice that cannot speak here shows no time
                    base.log(hub.cfg, "hub.log", f"could not time the voice {v}: {e}")
                    continue
                known[group] = round(took[2], 2)
                try:
                    with open(os.path.join(hub.cfg.state, TIMES_FILE), "w") as f:
                        json.dump(known, f, indent=1)
                except OSError:
                    pass
                if getattr(hub, "_settings_open", False) and hub.overlay:
                    hub.overlay.send({"type": "settings", "open": True, "title": NAME, "sections": describe(hub)})
        finally:
            hub._timing = False

    threading.Thread(target=run, name="voice-times", daemon=True).start()


def voice_tag(hub, voice: str) -> tuple[str, str] | None:
    """What is shown after a voice's description, with what it means: its time, once known."""
    took = times(hub).get(timing_group(voice))
    return (f"{took:.1f} s", TIME_HELP) if isinstance(took, (int, float)) else None


def voice_language(voice: str) -> str:
    """The language a voice speaks: "en", "it", "zh", or "" for one not offered here."""
    if voice.startswith("zh:"):
        return "zh"
    if voice.startswith("piper:"):
        return voice[6:8]
    m = re.fullmatch(r"([a-z])[fm]_\w+", voice)
    return VOICE_LANG.get(m.group(1), "") if m else "en"  # one's own voices speak English


def catalog(hub) -> dict:
    """Every voice this machine has, by the language it speaks (`SUMMARY_LANGUAGES` only)."""
    known = hub.voices()
    names = set(known.get("builtin", [])) | set(known.get("custom", [])) | set(known.get("piper", [])) | set(known.get("zh", []))
    found = {lang: [] for lang in SUMMARY_LANGUAGES}
    for v in sorted(names):
        lang = voice_language(v)
        if lang == "en" and re.fullmatch(r"[ab][fm]_\w+", v) and v not in KOKORO_GRADES:
            continue  # graded D or F by Kokoro
        if lang == "zh" and re.fullmatch(r"z[fm]_\w+", v):
            continue  # Kokoro 1.0's Chinese, through espeak, graded D; the Chinese model is better
        if lang in found:
            found[lang].append(v)
    return found


def in_use(hub, lang: str) -> list:
    """The voices a language's sessions take in turn: for English the pool new projects get
    theirs from, for another language `language_voices` or else `tts.PREFERRED_VOICE`."""
    have = set(catalog(hub).get(lang, []))
    if lang == "en":
        return [v for v in hub.voices().get("pool", hub.cfg.voice_pool) if v in have]
    wanted = hub.cfg.language_voices.get(lang) or tts.PREFERRED_VOICE.get(lang) or []
    return [v for v in ([wanted] if isinstance(wanted, str) else wanted) if v in have]


def set_in_use(hub, lang: str, voices: list) -> str | None:
    """Which voices a language uses, in their order. Returns what is wrong, or None."""
    have = set(catalog(hub).get(lang, []))
    if not voices:
        return "keep at least one voice for each language"
    if any(v not in have for v in voices):
        return "no such voice for " + base.LANGUAGE_NAMES.get(lang, "English")
    if lang == "en":
        hub.cfg.voice_pool[:] = voices  # in place: the sessions hold this same list
        _save(hub.cfg, ["voice_pool"], voices)
    else:
        hub.cfg.language_voices[lang] = voices
        _save(hub.cfg, ["language_voices", lang], voices)
        # A session keeps its voice while it stays ticked, as English projects do; the order is
        # for sessions that have none yet. It was shared out again at once, which English did
        # not do (the author, 2026-11-21, after swapping Heart and Bella and asking whether they
        # would now hear Bella: keep the voices, "too much logic" otherwise).
    return None


def preview(hub, voice: str) -> None:
    """A voice says a sentence in its language, and nothing is changed (the ▶ in the window)."""
    engine = hub.speech.engine
    if voice and hasattr(engine, "has") and not engine.has(voice) and engine.has("sample:" + voice):
        voice = "sample:" + voice  # not downloaded yet: its recording (tts.SAMPLES_DIR)
    if voice and hasattr(engine, "has") and engine.has(voice):
        hub.speech.drop_src("preview")  # pressed again, or another one: the last press is heard
        hub.speech.put(tts.Utterance(text=SAMPLES.get(voice_language(voice), SAMPLES["en"]), voice=voice,
                                     kind="notice", src="preview"))


# At most this many voices for a language in the window (the author, 2026-11-21: "for each
# language we can keep maximum 10 or 15"): the ticked ones, then the best of the rest.
MOST_VOICES = 12


def rank(voice: str) -> tuple:
    """Best first: Kokoro's grade for English, the measured clarity for Chinese, then Piper's
    faster voices, then the rest by name."""
    if voice in KOKORO_GRADES:
        return (0, list(KOKORO_GRADES).index(voice), voice)
    if voice in CHINESE_CLARITY:
        return (0, CHINESE_CLARITY.index(voice), voice)
    return (1 if voice.startswith("piper:") else 2, 0, voice)


def listed(lang: str, chosen: list, have: list) -> list:
    """A language's voices as the window lists them: the ticked in their order, then the best
    of the rest up to MOST_VOICES; one's own voices always."""
    rest = sorted((v for v in have if v not in chosen), key=rank)
    own = [v for v in rest if voice_label(v)[1] == "Your own voice"]
    rest = [v for v in rest if v not in own][:max(0, MOST_VOICES - len(chosen))]
    return chosen + rest + own


def spoken(hub) -> list:
    """The languages you speak, of those the window lists: what push-to-talk listens for
    (`whisper_language`, asked by install.sh and `sidetone languages`). "auto" is all of them."""
    named = stt.codes(hub.cfg.whisper_language)
    return [lang for lang in SUMMARY_LANGUAGES if not named or lang in named]


def set_spoken(hub, lang: str, on: bool) -> str | None:
    """A language's switch on the Voices page: the languages push-to-talk listens for, with
    this one added or taken out; others named in config.json (Spanish, say) are kept. Returns
    what is wrong, or None. The author, 2026-11-21: "if someone speaks only English, they should
    be able to disable the other languages ... the fewer the languages to detect, the less
    ambiguous the words are"."""
    if lang not in SUMMARY_LANGUAGES:
        return f"no language {lang} here"
    if on and not has_pack(hub, lang) and hasattr(hub.speech.engine, "zh_voices"):
        return f"install {base.LANGUAGE_NAMES.get(lang, lang)} first"
    named = stt.codes(hub.cfg.whisper_language) or list(SUMMARY_LANGUAGES)
    wanted = [c for c in named if c != lang] + ([lang] if on else [])
    wanted = [c for c in SUMMARY_LANGUAGES if c in wanted] + [c for c in wanted if c not in SUMMARY_LANGUAGES]
    if not wanted:
        return "keep at least one language"
    try:
        stt.save_languages(hub.cfg.config_path, wanted)
    except (OSError, ValueError) as e:
        return str(e)
    hub.reload_languages()
    base.log(hub.cfg, "hub.log", f"setting speak.{lang} = {json.dumps(on)}")
    return None


# ---- packs: a language or a voice installed from the window (hub/packs.py) ----
# Agreed 2026-11-23 ("for chinese i want to install it from settings no?"): a language not
# installed shows its size and an Install button on its heading, then a bar while it comes; a
# voice not downloaded is listed with its size and fetched when it is ticked.

def _dirs(hub) -> tuple:
    engine = hub.speech.engine
    return getattr(engine, "dir", hub.cfg.kokoro_dir) or packs.KOKORO_DIR, getattr(engine, "piper_dir", packs.PIPER_DIR)


def has_pack(hub, lang: str) -> bool:
    """Whether a language needing a pack (Chinese) is installed; every other one is."""
    if lang != "zh":
        return True
    engine = hub.speech.engine
    return bool(engine.zh_voices()) if hasattr(engine, "zh_voices") else False


def fetchable(hub, lang: str) -> list:
    """Voices of `lang` that are not here but can be fetched: the clearest Chinese ones once the
    Chinese model is, Piper's Italian."""
    have = set(catalog(hub).get(lang, []))
    if lang == "zh":
        if not has_pack(hub, "zh"):
            return []
        wanted = list(dict.fromkeys(list(tts.PREFERRED_VOICE["zh"]) + CHINESE_CLARITY[:MOST_VOICES]))
    else:
        wanted = [v for v in packs.PIPER if voice_language(v) == lang]
    return [v for v in wanted if v not in have]


def jobs(hub) -> dict:
    """What is being installed, by language ("zh") or voice ("zh:zf_001"): how far, and the
    error of one that failed (kept until it is tried again)."""
    return hub.__dict__.setdefault("_packs", {})


def _show(hub) -> None:
    if getattr(hub, "_settings_open", False) and hub.overlay:
        hub.overlay.send({"type": "settings", "open": True, "title": NAME, "sections": describe(hub)})


def install(hub, what: str) -> str | None:
    """Start installing a language's pack ("zh") or one voice ("zh:zf_001", "piper:..."), in
    the background; the window follows it. Returns what is wrong, or None."""
    if what != "zh" and what not in packs.PIPER and not (what.startswith("zh:") and what in fetchable(hub, "zh")):
        return f"nothing to install called {what}"
    job = jobs(hub).get(what)
    if job and job.get("busy"):
        return None
    job = jobs(hub)[what] = {"busy": True, "done": 0, "total": 0, "step": "", "error": ""}
    kokoro_dir, piper_dir = _dirs(hub)
    engine = hub.speech.engine

    def run():
        shown = [0.0]

        def progress(done, total):
            job["done"], job["total"] = done, total
            if time.monotonic() - shown[0] > 0.3:  # the window drawn again at most about three times a second
                shown[0] = time.monotonic()
                _show(hub)

        def step(what_now):
            job["step"] = what_now
            _show(hub)

        try:
            if what == "zh":
                packs.install_zh([v[3:] for v in tts.PREFERRED_VOICE["zh"]], kokoro_dir, progress, step)
            elif what.startswith("zh:"):
                packs.add_zh_voices([what[3:]], kokoro_dir, progress)
            else:
                packs.install_piper(what, piper_dir, progress)
            if hasattr(engine, "reload_zh"):
                engine.reload_zh()
            if hasattr(engine, "reload_piper"):
                engine.reload_piper()
            jobs(hub).pop(what, None)
            if what == "zh":
                set_spoken(hub, "zh", True)  # installed means on
            else:
                lang = voice_language(what)
                set_in_use(hub, lang, in_use(hub, lang) + [what])  # it was ticked to be fetched
            base.log(hub.cfg, "hub.log", f"installed {what}")
        except Exception as e:  # noqa: BLE001 - a failed download is said in the window, the hub goes on
            job.update(busy=False, error=str(e) if isinstance(e, packs.Failed) else f"could not install it: {e}")
            base.log(hub.cfg, "hub.log", f"installing {what} failed: {e}")
        hub.publish()
        _show(hub)

    base.log(hub.cfg, "hub.log", f"installing {what}")
    threading.Thread(target=run, daemon=True, name=f"install {what}").start()
    return None


def remove(hub, lang: str) -> str | None:
    """Take a language's pack away (its files; Chinese then is off). Returns what is wrong, or None."""
    if lang != "zh":
        return f"{base.LANGUAGE_NAMES.get(lang, lang)} has nothing to remove"
    kokoro_dir, _ = _dirs(hub)
    if lang in spoken(hub) and len(spoken(hub)) > 1:
        set_spoken(hub, lang, False)
    if base.fixed_language(hub.cfg) == lang:  # the summary language can only be one installed
        apply(hub, "reply_language", "spoken")
    freed = packs.remove_zh(kokoro_dir)
    if hasattr(hub.speech.engine, "reload_zh"):
        hub.speech.engine.reload_zh()
    base.log(hub.cfg, "hub.log", f"removed Chinese, {packs.megabytes(freed)} freed")
    hub.publish()
    return None


def _pack_heading(hub, lang: str, found: dict) -> None:
    """A heading for a language not installed: its size and Install, a bar while it comes, or
    what went wrong and Try Again."""
    job = jobs(hub).get(lang) or {}
    found.update(spoken=False, speak="", install=f"install.{lang}")
    if job.get("busy"):
        total = job.get("total") or 0
        found.update(pack="installing", progress=round(job["done"] / total, 3) if total else 0.0,
                     # How far only: which part is coming ("Chinese model") was beside it, and was not
                     # needed (the author, 2026-11-23).
                     summary=f"{packs.megabytes(job['done'])} of {packs.megabytes(total)}" if total else "Starting")
    elif job.get("error"):
        found.update(pack="failed", summary=job["error"])
    else:
        size = packs.needs(lang, list(tts.PREFERRED_VOICE.get(lang, [])), *_dirs(hub)[:1])
        found.update(pack="missing", summary=f"Not installed, {packs.megabytes(size)}")


def _listen_only(hub, lang: str) -> list:
    """The voices of a language not installed, to hear from their recordings before Install
    (agreed 2026-11-23): those Install brings first, then the clearest; no switches yet."""
    voices = list(dict.fromkeys(list(tts.PREFERRED_VOICE.get(lang, [])) + CHINESE_CLARITY[:MOST_VOICES]))
    found = []
    for v in voices:
        if not os.path.isfile(tts.sample_path(v)):
            continue
        name, what = voice_label(v)
        found.append({"key": f"voice_in.{lang}.{v}", "kind": "voice", "name": name, "help": what, "voice": v,
                      "group": lang, "more": False, "switch": False,
                      "playing": getattr(hub, "_previewing", "") == v})
        if v in tts.PREFERRED_VOICE.get(lang, []):
            found[-1].update(tag="Comes with it", tag_help="Install brings this voice; the others are half a megabyte each, once it is installed.")
    return found


def _remove_item(hub, lang: str, always: bool = False) -> dict:
    """Remove, under a language's card, or under its heading while it is off."""
    return {"key": f"remove.{lang}", "kind": "pack", "name": f"Remove {base.LANGUAGE_NAMES[lang]}",
            "help": f"Frees {packs.megabytes(packs.removable(lang, _dirs(hub)[0]))}. You can install it again.",
            "group": lang, "always": always}


def _voices(hub) -> list:
    """The Voices section: for each language the voices its lines are said in, ticked and in
    order; sessions take them in turn. There was a part for each open project's own voice
    above them, taken out the same day (the author, 2026-11-21: "what is the point of it ...
    each language has its order ... three, they can do one, two, three, one, two, three");
    a project is still given a voice by hand with `sidetone voice PROJECT VOICE`."""
    known = hub.voices()
    if not known.get("choosable"):
        return []
    voices = catalog(hub)
    # One sentence for the page, not one per language: they said the same (the author,
    # 2026-11-21: "do they all have the same description beneath the language?").
    found = [{"kind": "intro", "key": "intro.voices", "name": "",
              # Two sentences; it was five in one paragraph (the author, 2026-11-21: "it's so long and
              # it's a single paragraph"). The rest is said where it applies: the switches, the dots
              # and the play buttons say what they do under the mouse, and the quality words are plain.
              "help": "Each session speaks in its own voice, so you know who is talking. "
                      "New projects take the ticked voices in order, and keep the one they get."}]
    everyone = []
    speaking = spoken(hub)
    for lang in SUMMARY_LANGUAGES:
        chosen = in_use(hub, lang)
        if not has_pack(hub, lang) and hasattr(hub.speech.engine, "zh_voices"):
            heading = {"kind": "heading", "key": f"heading.{lang}", "name": base.LANGUAGE_NAMES.get(lang, "English"),
                       "help": "", "fold": True, "last": False}
            _pack_heading(hub, lang, heading)
            found.append(heading)
            found += _listen_only(hub, lang)
            continue
        if not voices.get(lang):
            continue
        # Each language's heading has a switch for whether you speak it (`spoken`); one that is
        # off lists no voices and stays closed.
        if lang not in speaking:
            found.append({"kind": "heading", "key": f"heading.{lang}", "name": base.LANGUAGE_NAMES.get(lang, "English"),
                          "help": "", "fold": True, "summary": "", "speak": f"speak.{lang}", "spoken": False,
                          "last": False})
            if lang == "zh" and hasattr(hub.speech.engine, "zh_voices"):  # installed but off: it can still go
                found.append(_remove_item(hub, lang, always=True))
            continue
        # A heading that opens and closes its card (the author, 2026-11-21: "for each language
        # making a drop-down list so I can quickly scroll between the languages"), with how many
        # voices are ticked beside it. It named them first ("Heart, Michael, Bella and 5 more");
        # the author did not like it much, and a count was agreed. "8 voices" read as all it holds
        # while it counted only the ticked (the author, 2026-11-21: "might be misleading"), so it
        # said both, "4 of 12 ticked", which was "not very conventional"; "4 selected", as most
        # programs say it, was agreed the same day.
        coming = fetchable(hub, lang)
        shown = listed(lang, chosen, voices[lang] + coming)
        everyone += [v for v in shown if v not in coming]
        found.append({"kind": "heading", "key": f"heading.{lang}", "name": base.LANGUAGE_NAMES.get(lang, "English"),
                      "help": "", "fold": True, "summary": f"{len(chosen)} selected", "speak": f"speak.{lang}",
                      "spoken": True, "last": len(speaking) == 1})
        for v in shown:
            name, what = voice_label(v)
            found.append({"key": f"voice_in.{lang}.{v}", "kind": "voice", "name": name, "help": what, "voice": v,
                          "group": lang, "more": v not in chosen, "playing": getattr(hub, "_previewing", "") == v})
            tag = voice_tag(hub, v)
            if v in coming:  # not here yet: its size, fetched when ticked; nothing to hear yet
                job = jobs(hub).get(v) or {}
                size = packs.voice_size(v, _dirs(hub)[1])
                if job.get("busy"):
                    tag = (f"{int(100 * job['done'] / job['total']) if job.get('total') else 0} %", "Downloading it")
                elif job.get("error"):
                    tag = ("Failed", job["error"] + ". Tick it to try again.")
                else:
                    tag = (packs.megabytes(size), "Not downloaded yet. Ticking it downloads it.")
                found[-1].update(fetch=True, preview=os.path.isfile(tts.sample_path(v)))
            if tag:
                found[-1].update(tag=tag[0], tag_help=tag[1])
        if lang == "zh" and hasattr(hub.speech.engine, "zh_voices"):  # a pack: how to take it away again
            found.append(_remove_item(hub, lang))
    time_voices(hub, everyone)
    return found


def items(hub) -> dict:
    """Every setting the window has, by its key."""
    found = {item["key"]: item for _, section in SECTIONS for item in section if item["kind"] != "heading"}
    found.update({item["key"]: item for item in _voices(hub)})
    return found


def read(hub, key: str):
    """What a setting is now."""
    cfg = hub.cfg
    if key == "mute":
        return os.path.exists(cfg.mute_file)
    if key.startswith("voice_in."):  # voice_in.it.if_sara: whether Italian lines may be said in it
        lang, voice = key[9:].split(".", 1)
        return voice in in_use(hub, lang)
    if key.startswith("overlay.hotkeys."):
        return cfg.overlay.get("hotkeys", {}).get(key[16:], "")
    if key.startswith("overlay."):
        return cfg.overlay.get(key[8:])
    if key == "terminal.strength":
        return _percent(cfg.terminal.get("strength"))
    if key.startswith("terminal."):
        return cfg.terminal.get(key[9:])
    if key == "context_shown":
        return base.context_mode(cfg)
    if key == "aside":  # on or off; "busy", "always" and "off" from before
        return base.aside_mode(cfg) != "off"
    if key == "cancel_stops":  # on or off; "always", "sent" and "never" from before
        return base.interrupts(cfg)
    if key == "label":
        return "always" if cfg.label == "always" else "never"  # "auto" is gone
    if key == "reply_language":
        return base.fixed_language(cfg) or "spoken"
    value = getattr(cfg, key)
    if key == "turn_tokens" and isinstance(value, bool):  # from when it was on or off
        return "new" if value else "off"
    return value


STRENGTH_TOP = 0.3  # the tint at 100 % in the window: the share of the color mixed into the background


def _percent(strength) -> int:
    """A tint's share of the color as the window shows it, 0 to 100 %."""
    try:
        return max(0, min(100, round(float(strength) / STRENGTH_TOP * 100)))
    except (TypeError, ValueError):
        return _percent(terminal_mod.DEFAULTS["strength"])


def default(key: str):
    """What a setting is on a new install; None for one that has no single default (a
    project's voice is handed out from the pool)."""
    if key == "mute":
        return False
    if key.startswith(("voice_in.", "voices_order.", "heading.", "intro.", "speak.", "remove.")):
        return None
    if key.startswith("overlay.hotkeys."):
        return overlay_mod.DEFAULTS["hotkeys"].get(key[16:], "")
    if key.startswith("overlay."):
        return overlay_mod.DEFAULTS.get(key[8:])
    if key == "terminal.strength":
        return _percent(terminal_mod.DEFAULTS["strength"])
    if key.startswith("terminal."):
        return terminal_mod.DEFAULTS.get(key[9:])
    found = {f.name: f for f in dataclasses.fields(base.Config)}[key]
    return found.default_factory() if found.default is dataclasses.MISSING else found.default


def _same(item: dict, now, then) -> bool:
    try:
        return _fit(item, now) == _fit(item, then)
    except ValueError:
        return False


def _with_keys(hub, help: str) -> str:
    """"the mute key" in a sentence gets the key it is now, "the mute key (Ctrl+Alt+M)" (the
    author, 2026-11-20: "in the description ... include also the shortcut key"). A key left
    without a combination gets nothing."""
    keys = hub.cfg.overlay.get("hotkeys", {})

    def named(m):
        combo = keys.get({"details": "toggle"}.get(m.group(2).lower(), m.group(2).lower()), "")
        return f"{m.group(0)} ({combo})" if combo else m.group(0)
    return re.sub(r"\b(the) (mute|talk|cancel|repeat|layout|clear|settings|details) key\b", named, help, flags=re.I)


def describe(hub) -> list:
    """The sections as the window draws them: every setting with what it is now, and whether
    any of them differs from a new install's (`changed`, for the section's reset button)."""
    sections = []
    for name, section in SECTIONS:
        listed = _voices(hub) if name == "Voices" else section
        if listed:
            values = [{**item, "help": _with_keys(hub, item["help"]),
                       "value": None if item["kind"] in ("heading", "intro", "pack") else read(hub, item["key"])} for item in listed]
            for item in values:
                if item["key"] == "reply_language":  # only languages installed (and the one chosen, if it is not)
                    item["options"] = [o for o in item["options"] if has_pack(hub, o[0]) or o[0] == item["value"]
                                       or not hasattr(hub.speech.engine, "zh_voices")]
            resettable = [i for i in values if default(i["key"]) is not None]
            sections.append({"name": name, "items": values, "resettable": bool(resettable),
                             "changed": any(not _same(i, i["value"], default(i["key"])) for i in resettable)})
    return sections


def reset(hub, section: str) -> str | None:
    """Put every setting of one section back as a new install has it (the author, 2026-11-20:
    "for each category ... a reset button at the end"). Each goes through `apply`, so it takes
    effect at once as if chosen by hand. Returns what is wrong, or None."""
    listed = next((s for name, s in SECTIONS if name.lower() == section.lower()), None)
    if listed is None:
        return f"no section called {section}"
    changed = [item for item in listed if default(item["key"]) is not None
               and not _same(item, read(hub, item["key"]), default(item["key"]))]
    for item in changed:
        error = apply(hub, item["key"], default(item["key"]))
        if error:
            return error
    base.log(hub.cfg, "hub.log", f"settings of {section} reset: {len(changed)} changed back")
    return None


def _fit(item: dict, value):
    """`value` as this setting takes it; ValueError when it cannot be one."""
    kind = item["kind"]
    if kind in ("choice", "pick"):
        for allowed, _ in item["options"]:
            if value == allowed or str(value) == str(allowed):
                return allowed
        raise ValueError(f"{item['key']} is one of: " + ", ".join(str(o[0]) for o in item["options"]))
    if kind in ("switch", "voice"):
        if isinstance(value, str):
            if value.lower() not in ("true", "false", "on", "off"):
                raise ValueError(f"{item['key']} is on or off")
            return value.lower() in ("true", "on")
        return bool(value)
    if kind == "color":
        text = str(value or "").strip().upper()
        if text and not text.startswith("#"):
            text = "#" + text
        if re.fullmatch(r"#[0-9A-F]{6}", text) or (text == "" and default(item["key"]) == ""):
            return text
        raise ValueError(f"{item['key']} is a color like #4FC3F7")
    if kind == "number":
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{item['key']} is a number from {item['min']} to {item['max']}") from None
        step = item["step"]
        value = min(item["max"], max(item["min"], round(value / step) * step))
        return round(value, 4)
    combo = str(value or "").strip()  # a hotkey: "" turns it off
    parts = [p.strip() for p in combo.split("+")] if combo else []
    if combo and (not all(parts) or sum(p.lower() not in KEY_PARTS for p in parts) != 1):
        raise ValueError(f"{item['key']} is a key with the keys held, like Ctrl+Alt+L, or nothing")
    return "+".join(parts)


_saving = threading.Lock()  # one change at a time: each reads the file, adds to it and writes it back


def _save(cfg, path: list, value) -> None:
    """Write one value into the user's config.json at `path`, keeping everything else in it."""
    save_all(cfg, [(path, value)])


def save_all(cfg, changes: list) -> None:
    """Write values into the user's config.json, each (path, value) as in `_save`, keeping
    everything else in it. A file that is there but cannot be read as settings (a slip while
    editing it by hand) is left as it is: written over, every other setting in it was lost."""
    if not cfg.config_path or not changes:
        return
    named = ", ".join(".".join(map(str, path)) for path, _ in changes)
    with _saving:
        try:
            with open(cfg.config_path) as f:
                saved = json.load(f)
        except FileNotFoundError:
            saved = {}
        except (OSError, ValueError) as e:
            base.log(cfg, "hub.log", f"could not save the setting {named}: {cfg.config_path} cannot be read ({e}); left as it is")
            return
        if not isinstance(saved, dict):
            base.log(cfg, "hub.log", f"could not save the setting {named}: {cfg.config_path} is not a set of settings; left as it is")
            return
        for path, value in changes:
            at = saved
            for name in path[:-1]:
                if not isinstance(at.get(name), dict):
                    at[name] = {}
                at = at[name]
            at[path[-1]] = value
        try:
            os.makedirs(os.path.dirname(cfg.config_path), exist_ok=True)
            with open(cfg.config_path, "w") as f:
                json.dump(saved, f, indent=2)
        except OSError as e:
            base.log(cfg, "hub.log", f"could not save the setting {named}: {e}")


def apply(hub, key: str, value) -> str | None:
    """Change a setting: at once, and remembered. Returns what is wrong with it, or None."""
    if key.startswith("speak."):  # the switch on a language's heading: whether you speak it
        return set_spoken(hub, key[6:], bool(value))
    if key == "reply_language" and not has_pack(hub, str(value)) and hasattr(hub.speech.engine, "zh_voices"):
        return f"install {base.LANGUAGE_NAMES.get(str(value), value)} first"
    if key.startswith("install."):  # Install on a language's heading (or Try Again)
        return install(hub, key[8:])
    if key.startswith("remove."):  # Remove at the end of a language's card
        return remove(hub, key[7:])
    if key.startswith("voice_in.") and value:  # a voice not downloaded, ticked: fetched first, ticked after
        lang, voice = key[9:].split(".", 1)
        if voice in fetchable(hub, lang):
            return install(hub, voice)
    if key.startswith("voices_order."):  # a voice dragged to another place in its language's list
        error = set_in_use(hub, key[13:], [str(v) for v in value] if isinstance(value, list) else [])
        if not error:
            base.log(hub.cfg, "hub.log", f"setting {key} = {json.dumps(value)}")
            hub.publish()
        return error
    item = items(hub).get(key)
    if not item:
        return f"no setting called {key}"
    try:
        value = _fit(item, value)
    except ValueError as e:
        return str(e)
    cfg = hub.cfg
    if key == "mute":
        if not value:
            try:
                os.remove(cfg.mute_file)
            except OSError:
                pass
        else:
            os.makedirs(os.path.dirname(cfg.mute_file), exist_ok=True)
            open(cfg.mute_file, "a").close()
            hub.speech.stop_all()
        hub.publish()
    elif key.startswith("voice_in."):
        lang, voice = key[9:].split(".", 1)
        now = in_use(hub, lang)
        error = set_in_use(hub, lang, now + [voice] if value and voice not in now else [v for v in now if v != voice or value])
        if error:
            return error
        hub.publish()
    elif key.startswith("overlay.hotkeys."):
        cfg.overlay.setdefault("hotkeys", {})[key[16:]] = value
        if hub.overlay and hasattr(hub.overlay, "reconfigure"):
            hub.overlay.reconfigure()
        _save(cfg, ["overlay", "hotkeys", key[16:]], value)
        hub.publish()
    elif key.startswith("overlay."):
        hub.place_overlay(**{key[8:]: value})
        hub.publish()
    elif key == "terminal.strength":  # percent in the window, a share of the color in config.json
        hub.set_terminal(strength=round(value * STRENGTH_TOP / 100, 4))
    elif key.startswith("terminal."):
        hub.set_terminal(**{key[9:]: value})
    else:
        setattr(cfg, key, value)
        if key == "speed" and hasattr(hub.speech.engine, "speed"):
            hub.speech.engine.speed = value
        if key == "volume":
            base.set_volume(hub)
        if key == "voice_device" and hasattr(hub.speech.engine, "set_device"):
            def move(engine=hub.speech.engine):
                engine.set_device(value)
                hub._voice_loaded(engine)
            threading.Thread(target=move, daemon=True).start()  # about a second; the window does not wait
        if key == "whisper_device" and getattr(hub, "transcriber", None):
            hub.transcriber.device = value
            hub.transcriber.unload()  # loaded again where it now belongs, on the next press of the talk key
        if key == "usage_shown" and value:
            hub._plan_asked = float("-inf")  # read it now, not in five minutes
        _save(cfg, [key], value)
        hub.publish()
    base.log(cfg, "hub.log", f"setting {key} = {json.dumps(value)}")
    return None
