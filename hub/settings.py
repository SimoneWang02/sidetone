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
        # One volume for the voice and the sounds (the author, 2026-11-20: "do one thing for both so
        # it's more consistent"); `sound_volume` stays in config.json as the sounds' level beside the voice.
        number("volume", "Volume", "The voice and the short sounds together.", 0, 100, 5),
        number("speed", "Speed", "How fast the voice talks.", 0.7, 1.6, 0.05, "x"),
        {"key": "reply_language", "kind": "pick", "name": "Language of the Summary",
         "help": "The spoken line in the language you wrote or spoke in, or always in one language.",
         "options": [["spoken", "Match My Language"]] + [[code, base.LANGUAGE_NAMES.get(code, "English")] for code in SUMMARY_LANGUAGES]},
        choice("label", "Say the Session Name", "Its name as the overlay shows it, from its folder, said before each of its lines so you know who talks without looking.",
               ("always", "Always"), ("never", "Never")),
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
        switch("clear_by_voice", "Clear the Chat by Voice", "Say \"clear the chat\" and /clear is typed into that session's terminal "
               "once it is at its prompt. Needs the VS Code extension."),
        # Discord's own name for it is "Push to Talk Release Delay" (the author, 2026-11-21: "Is this
        # conventional?"). Was "Listen On After Release".
        number("talk_tail", "Release Delay", "After you let go of the talk key, it keeps listening this long, "
               "so your last word is not cut off.", 0, 1, 0.1, "s"),
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
        choice("overlay.mode", "Details", "Names, titles and figures beside the lights. The details key switches them.",
               ("list", "Always"), ("dots", "On Hover")),
        # "Details Changing Size" (overlay.resize: quick, instant) left the window on 2026-11-21, the
        # author: "the animation is pretty standard". Still read from config.json.
        switch("overlay.panel_drag", "Move It by the Details", "With the details kept out, dragging them moves the whole overlay. A click still goes to what is behind."),
        choice("overlay.hover", "What Opens the Details", "The mouse resting on the lights, or only holding the keys.",
               ("always", "Mouse"), ("keys", "Keys only")),
        switch("overlay.muted_line", "Say When Muted", "\"Voice is muted\" in the details while the voice is off."),
        switch("overlay.muted_icon", "Icon When Muted", "A slashed speaker in the corner of a line that pops out while the voice is off."),
        switch("overlay.muted_card_icon", "Icon in the Figures When Muted", "The same speaker in the corner of the card of figures."),
        switch("overlay.muted_mark", "Mark When Muted", "A small struck-out speaker past the end of the lights while the voice is off."),
        number("overlay.opacity", "Opacity at Rest", "How solid the lights are while nothing happens.", 0.3, 1.0, 0.05),
        choice("overlay.glass", "Glass", "Blur what is behind it, or plain dark glass.",
               ("blur", "Blur"), ("none", "Plain")),
        choice("overlay.row_lines", "Lines Per Session", "How many lines a sentence may take in the details.",
               (1, "1"), (2, "2"), (3, "3")),
        choice("overlay.history", "History Shows", "The lines of the session you are on, or of all of them.",
               ("session", "One session"), ("all", "All")),
        choice("overlay.talk_text", "\"Release to Send\"", "How those words move while you hold the talk key.",
               ("shimmer", "Glint"), ("pulse", "Breathe"), ("still", "Still")),
        choice("overlay.waiting_mark", "Messages That Wait", "The mark on the light of a session that has words of yours waiting.",
               ("number", "Number"), ("clock", "Clock"), ("dot", "Dot")),
    ]),
    ("Figures", [
        choice("context_shown", "Context", "How full each session's context is.",
               ("arc", "Arc"), ("text", "Words"), ("both", "Both"), ("off", "Off")),
        choice("turn_tokens", "Tokens of a Reply", "What counts: newly read and written, only written, or everything.",
               ("new", "New"), ("output", "Written"), ("all", "All"), ("off", "Off")),
        switch("turn_tokens_history", "Tokens in the History", "Each line of the history ends in what its turn used."),
        switch("history_time", "Time in the History", "How long ago each line was said."),
        switch("history_missed", "Mark Lines Not Heard", "A white dot on lines that were cut off or never said."),
        choice("overlay.details_style", "Figures Drawn As", "A tile each, or one line of text.",
               ("tiles", "Tiles"), ("line", "A line")),
        switch("overlay.details_bars", "Bars Under the Figures", "A thin bar under a tile that is a share of a whole, such as context."),
        switch("usage_shown", "Plan Usage", "The five-hour window and the week, at the foot of the figures."),
        choice("overlay.usage_layout", "Usage Bars", "", ("rows", "A row each"), ("line", "Side by side")),
        choice("usage_models", "A Model's Own Week", "A third bar where the plan counts one model apart.",
               ("none", "Off"), ("near", "Near its end"), ("all", "Always")),
    ]),
    ("Terminal", [
        choice("terminal.tint", "Tint", "Whose terminal wears a little of its session's color.",
               ("focus", "In focus"), ("all", "All"), ("off", "Off")),
        number("terminal.strength", "Tint Strength", "How much of the color goes into the background.", 0.0, 0.3, 0.01),
        switch("terminal.pulse", "Flash When the Focus Moves", "The terminal lights up for a moment when you move the focus to it."),
        switch("terminal.follow", "Focus Follows the Terminal", "Going to a terminal in the editor selects its session."),
        switch("terminal.jump", "Terminal Follows the Focus", "Moving the focus with the arrows or the wheel brings that session's terminal to the front in the editor."),
        switch("terminal.title", "Name in the Terminal's Title", "Write the session's name and title as the terminal's title."),
    ]),
    ("Keys", [
        switch("overlay.share_taken_keys", "Share Keys Other Programs Have",
               "When another program already has one of these keys, it still works here too, and both act on it."),
        hotkey("talk", "Talk", "Hold it and speak."),
        hotkey("cancel", "Cancel or Stop", "Drop a recording, take words back, cut a line, or stop a turn."),
        hotkey("toggle", "Details", "Always out, or only on hover."),  # was "Keep the Details Out"; named as the Details setting calls it
        hotkey("mute", "Mute", "Turns the voice off for every session, and on again."),
        hotkey("repeat", "Say It Again"),
        hotkey("layout", "Switch Layout"),
        hotkey("settings", "Settings", "Opens and closes this window."),
        hotkey("allow", "Allow"),
        hotkey("deny", "Deny"),
        hotkey("focus_prev", "Focus Up", "In the bar."),
        hotkey("focus_next", "Focus Down"),
        hotkey("focus_left", "Focus Left", "In the island."),
        hotkey("focus_right", "Focus Right"),
        hotkey("option1", "Answer 1"),
        hotkey("option2", "Answer 2"),
        hotkey("option3", "Answer 3"),
        hotkey("option4", "Answer 4"),
        hotkey("jump", "Go to the Terminal", "Of the session in focus, in the editor."),
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
    if voice and hasattr(hub.speech.engine, "has") and hub.speech.engine.has(voice):
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
        if not voices.get(lang):
            continue
        # Each language's heading has a switch for whether you speak it (`spoken`); one that is
        # off lists no voices and stays closed.
        if lang not in speaking:
            found.append({"kind": "heading", "key": f"heading.{lang}", "name": base.LANGUAGE_NAMES.get(lang, "English"),
                          "help": "", "fold": True, "summary": "", "speak": f"speak.{lang}", "spoken": False,
                          "last": False})
            continue
        # A heading that opens and closes its card (the author, 2026-11-21: "for each language
        # making a drop-down list so I can quickly scroll between the languages"), with how many
        # voices are ticked beside it. It named them first ("Heart, Michael, Bella and 5 more");
        # the author did not like it much, and a count was agreed. "8 voices" read as all it holds
        # while it counted only the ticked (the author, 2026-11-21: "might be misleading"), so it
        # said both, "4 of 12 ticked", which was "not very conventional"; "4 selected", as most
        # programs say it, was agreed the same day.
        shown = listed(lang, chosen, voices[lang])
        everyone += shown
        found.append({"kind": "heading", "key": f"heading.{lang}", "name": base.LANGUAGE_NAMES.get(lang, "English"),
                      "help": "", "fold": True, "summary": f"{len(chosen)} selected", "speak": f"speak.{lang}",
                      "spoken": True, "last": len(speaking) == 1})
        for v in shown:
            name, what = voice_label(v)
            found.append({"key": f"voice_in.{lang}.{v}", "kind": "voice", "name": name, "help": what, "voice": v,
                          "group": lang, "more": v not in chosen, "playing": getattr(hub, "_previewing", "") == v})
            tag = voice_tag(hub, v)
            if tag:
                found[-1].update(tag=tag[0], tag_help=tag[1])
    time_voices(hub, everyone)
    return found


def items(hub) -> dict:
    """Every setting the window has, by its key."""
    found = {item["key"]: item for _, section in SECTIONS for item in section}
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


def default(key: str):
    """What a setting is on a new install; None for one that has no single default (a
    project's voice is handed out from the pool)."""
    if key == "mute":
        return False
    if key.startswith(("voice_in.", "voices_order.", "heading.", "intro.", "speak.")):
        return None
    if key.startswith("overlay.hotkeys."):
        return overlay_mod.DEFAULTS["hotkeys"].get(key[16:], "")
    if key.startswith("overlay."):
        return overlay_mod.DEFAULTS.get(key[8:])
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
                       "value": None if item["kind"] in ("heading", "intro") else read(hub, item["key"])} for item in listed]
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
    elif key.startswith("terminal."):
        hub.set_terminal(**{key[9:]: value})
    else:
        setattr(cfg, key, value)
        if key == "speed" and hasattr(hub.speech.engine, "speed"):
            hub.speech.engine.speed = value
        if key == "volume":
            base.set_volume(hub)
        if key == "usage_shown" and value:
            hub._plan_asked = float("-inf")  # read it now, not in five minutes
        _save(cfg, [key], value)
        hub.publish()
    base.log(cfg, "hub.log", f"setting {key} = {json.dumps(value)}")
    return None
